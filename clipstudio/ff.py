"""ffmpeg discovery, execution and probing.

Works with a system ffmpeg or the static binary bundled by the `imageio-ffmpeg`
pip package (which has no ffprobe), so probing falls back to parsing
`ffmpeg -i` output.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from functools import lru_cache


class FFmpegError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    env = os.environ.get("FFMPEG")
    if env and os.path.exists(env):
        return env
    found = shutil.which("ffmpeg")
    bundled = None
    try:
        import imageio_ffmpeg  # type: ignore

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - depends on env
        pass
    # Prefer the system ffmpeg, but only if it can render captions (libass); a half-finished or
    # minimal build would silently break Thai subtitles.
    if found and (bundled is None or _has_filter(found, "ass")):
        return found
    if bundled:
        return bundled
    raise FFmpegError(
        "ffmpeg not found. Mac: bash setup-mac.sh --quick (or brew install ffmpeg) · "
        "Linux: apt install ffmpeg · anywhere: pip install imageio-ffmpeg"
    )


def _has_filter(binary: str, name: str) -> bool:
    try:
        out = subprocess.run([binary, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
        return f" {name} " in out
    except Exception:  # noqa: BLE001
        return False


@lru_cache(maxsize=1)
def ffprobe_bin() -> str | None:
    env = os.environ.get("FFPROBE")
    if env and os.path.exists(env):
        return env
    return shutil.which("ffprobe")


def run(args: list[str], *, quiet: bool = True, check: bool = True, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run ffmpeg with the given args (without the binary)."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin"]
    if quiet:
        cmd += ["-loglevel", "error"]
    cmd += args
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", cwd=cwd)
    if check and proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise FFmpegError(f"ffmpeg failed ({proc.returncode}):\n{tail}")
    return proc


def run_log(args: list[str]) -> str:
    """Run ffmpeg at info level and return stderr (used by analysis filters)."""
    proc = run(["-loglevel", "info"] + args, quiet=False, check=False)
    if proc.returncode != 0 and "Output file is empty" not in proc.stderr:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise FFmpegError(f"ffmpeg failed ({proc.returncode}):\n{tail}")
    return proc.stderr


def _parse_rate(txt: str) -> float:
    if "/" in txt:
        a, b = txt.split("/", 1)
        return float(a) / float(b) if float(b) else 0.0
    return float(txt)


def probe(path: str) -> dict:
    """Return {duration, width, height, fps, rotation, has_audio, audio_rate, vcodec, acodec}.

    width/height are the *displayed* dimensions (rotation applied), which is
    what ffmpeg filters see because ffmpeg auto-rotates on decode.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if ffprobe_bin():
        return _probe_ffprobe(path)
    return _probe_ffmpeg(path)


def _probe_ffprobe(path: str) -> dict:
    out = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    info = {"duration": float(data.get("format", {}).get("duration", 0) or 0), "width": 0, "height": 0,
            "fps": 0.0, "rotation": 0, "has_audio": False, "audio_rate": 0, "vcodec": None, "acodec": None}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not info["vcodec"]:
            if s.get("disposition", {}).get("attached_pic"):
                continue
            info["vcodec"] = s.get("codec_name")
            info["width"], info["height"] = int(s.get("width", 0)), int(s.get("height", 0))
            info["fps"] = _parse_rate(s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1")
            rot = 0
            for sd in s.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = int(float(sd["rotation"]))
            rot = rot or int(float(s.get("tags", {}).get("rotate", 0) or 0))
            info["rotation"] = rot
        elif s.get("codec_type") == "audio" and not info["acodec"]:
            info["acodec"] = s.get("codec_name")
            info["has_audio"] = True
            info["audio_rate"] = int(s.get("sample_rate", 0) or 0)
    if abs(info["rotation"]) % 180 == 90:
        info["width"], info["height"] = info["height"], info["width"]
    return info


def _probe_ffmpeg(path: str) -> dict:
    proc = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace")
    err = proc.stderr
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "rotation": 0, "has_audio": False,
            "audio_rate": 0, "vcodec": None, "acodec": None}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    for line in err.splitlines():
        if "Video:" in line and not info["vcodec"] and "attached pic" not in line:
            info["vcodec"] = line.split("Video:", 1)[1].strip().split()[0].rstrip(",")
            dm = re.search(r",\s*(\d{2,5})x(\d{2,5})", line)
            if dm:
                info["width"], info["height"] = int(dm.group(1)), int(dm.group(2))
            fm = re.search(r"([\d.]+)\s*fps", line) or re.search(r"([\d.]+)\s*tbr", line)
            if fm:
                info["fps"] = float(fm.group(1))
        elif "Audio:" in line and not info["acodec"]:
            info["acodec"] = line.split("Audio:", 1)[1].strip().split()[0].rstrip(",")
            info["has_audio"] = True
            am = re.search(r"(\d{4,6})\s*Hz", line)
            if am:
                info["audio_rate"] = int(am.group(1))
    rm = re.search(r"rotation of (-?[\d.]+) degrees", err) or re.search(r"rotate\s*:\s*(-?\d+)", err)
    if rm:
        info["rotation"] = int(float(rm.group(1)))
    if abs(info["rotation"]) % 180 == 90:
        info["width"], info["height"] = info["height"], info["width"]
    if not info["vcodec"] and not info["acodec"]:
        raise FFmpegError(f"Could not read media file: {path}")
    return info


def loudness(path: str) -> dict:
    """Integrated loudness (LUFS), loudness range and true peak via ebur128."""
    err = run_log(["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else err
    out = {}
    for key, pat in (("integrated", r"I:\s*(-?[\d.]+|-inf)\s*LUFS"), ("lra", r"LRA:\s*(-?[\d.]+)\s*LU"),
                     ("true_peak", r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS")):
        m = re.search(pat, summary)
        if m:
            out[key] = float("-inf") if m.group(1) == "-inf" else float(m.group(1))
    return out


def silences(path: str, noise_db: float = -35.0, min_dur: float = 0.45) -> list[dict]:
    """Detect silent stretches in the audio track: [{start, end}] in seconds."""
    err = run_log(["-i", path, "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"])
    out, start = [], None
    for line in err.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = re.search(r"silence_end:\s*(-?[\d.]+)", line)
        if m and start is not None:
            out.append({"start": round(start, 3), "end": round(float(m.group(1)), 3)})
            start = None
    if start is not None:
        out.append({"start": round(start, 3), "end": None})
    return out


def extract_frame(src: str, t: float, out: str, width: int | None = None) -> str:
    vf = ["-vf", f"scale={width}:-2"] if width else []
    run(["-y", "-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", "1", *vf, "-q:v", "2", out])
    return out


def filter_path(path: str) -> str:
    """Escape a (preferably relative) path for use as a filter option value.

    Callers run ffmpeg with cwd set to the project so paths stay short and
    free of drive letters; this escapes what is left for both the option
    parser and the filtergraph parser.
    """
    p = path.replace("\\", "/")
    for ch in ("\\", ":", "'", ",", "[", "]", ";", "="):
        p = p.replace(ch, "\\" + ch)
    return p
