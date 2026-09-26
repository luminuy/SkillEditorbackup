"""Speech-to-text (faster-whisper) or subtitle import -> transcript.json.

transcript.json:
  {"language": "th", "backend": "...", "segments": [
     {"id": 0, "start": 1.2, "end": 4.8, "text": "...",
      "words": [{"text": "ราศีเมษ", "start": 1.2, "end": 1.9}, ...]}]}
"""
from __future__ import annotations

import os
import re

from . import ff
from .config import Project, load_config, read_json, write_json
from .textutil import retime_words, segment_words


def fmt_ts(t: float, sep: str = ",") -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int(round((s - int(s)) * 1000)) % 1000:03d}"


def mmss(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m):02d}:{s:04.1f}"


def proportional_words(text: str, start: float, end: float) -> list[dict]:
    words = segment_words(text)
    if not words:
        return []
    weights = [max(1, len(w.strip())) for w in words]
    total = sum(weights)
    out, t = [], start
    for w, wt in zip(words, weights):
        d = (end - start) * wt / total
        out.append({"text": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def _words_text(words: list[dict]) -> str:
    return re.sub(r"\s+", "", "".join(w["text"] for w in words))


def resync(transcript: dict) -> int:
    """Re-derive word timings for segments whose text was edited by hand. Returns count fixed."""
    fixed = 0
    for seg in transcript["segments"]:
        if _words_text(seg.get("words") or []) != re.sub(r"\s+", "", seg["text"]):
            seg["words"] = proportional_words(seg["text"], seg["start"], seg["end"])
            fixed += 1
    return fixed


def apply_fixes(transcript: dict, fixes: dict) -> int:
    n = 0
    if not fixes:
        return 0
    for seg in transcript["segments"]:
        new = seg["text"]
        for wrong, right in fixes.items():
            new = new.replace(wrong, right)
        if new != seg["text"]:
            seg["text"] = new
            n += 1
    resync(transcript)
    return n


def parse_subtitles(path: str) -> list[dict]:
    """Parse .srt or .vtt into [{start,end,text}]."""
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    ts = re.compile(r"(\d+:)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d+:)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
    out = []

    def secs(h, m, s, ms):
        return (int(h[:-1]) if h else 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000

    for b in blocks:
        lines = [ln for ln in b.strip().split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            m = ts.search(ln)
            if m:
                g = m.groups()
                text = " ".join(re.sub(r"<[^>]+>", "", x).strip() for x in lines[i + 1:]).strip()
                if text:
                    out.append({"start": secs(*g[0:4]), "end": secs(*g[4:8]), "text": text})
                break
    return out


def from_subtitles(path: str, language: str) -> dict:
    segs = []
    for i, s in enumerate(parse_subtitles(path)):
        segs.append({"id": i, "start": round(s["start"], 3), "end": round(s["end"], 3), "text": s["text"],
                     "words": proportional_words(s["text"], s["start"], s["end"])})
    return {"language": language, "backend": f"import:{os.path.basename(path)}", "segments": segs}


def whisper(src: str, language: str, model_name: str, prompt: str | None, device: str = "auto") -> dict:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is not installed. `pip install faster-whisper`, or import subtitles with --srt FILE "
            "(export them from CapCut / YouTube Studio)."
        ) from exc
    compute = "auto"
    model = WhisperModel(model_name, device=device, compute_type=compute)
    try:  # Silero VAD needs onnxruntime, which has no wheels for some Macs (Intel + new Python)
        import onnxruntime  # type: ignore  # noqa: F401

        vad = True
    except ImportError:
        vad = False
        print("  (onnxruntime not installed: transcribing without VAD — slightly slower, same result)", flush=True)
    seg_iter, info = model.transcribe(
        src, language=language or None, word_timestamps=True, vad_filter=vad,
        vad_parameters={"min_silence_duration_ms": 400} if vad else None, initial_prompt=prompt or None,
        condition_on_previous_text=False, beam_size=5,
    )
    segs = []
    for i, s in enumerate(seg_iter):
        tokens = [{"text": w.word, "start": float(w.start), "end": float(w.end)} for w in (s.words or [])]
        words = retime_words(tokens) if tokens else proportional_words(s.text, s.start, s.end)
        segs.append({"id": i, "start": round(float(s.start), 3), "end": round(float(s.end), 3),
                     "text": s.text.strip(), "words": words})
        print(f"  [{mmss(s.start)}] {s.text.strip()[:70]}", flush=True)
    return {"language": info.language, "backend": f"faster-whisper:{model_name}", "segments": segs}


MLX_REPOS = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
}


def mlx(src: str, language: str, model_name: str, prompt: str | None) -> dict:
    """Apple Silicon (M1–M4) GPU transcription via mlx-whisper — several times faster than CPU."""
    try:
        import mlx_whisper  # type: ignore
    except ImportError as exc:
        raise SystemExit("mlx-whisper is not installed: pip install mlx-whisper (Apple Silicon Macs only)") from exc
    repo = MLX_REPOS.get(model_name, model_name)
    res = mlx_whisper.transcribe(src, path_or_hf_repo=repo, language=language or None, word_timestamps=True,
                                 initial_prompt=prompt or None, condition_on_previous_text=False)
    segs = []
    for i, s in enumerate(res.get("segments", [])):
        tokens = [{"text": w["word"], "start": float(w["start"]), "end": float(w["end"])} for w in s.get("words", [])]
        words = retime_words(tokens) if tokens else proportional_words(s["text"], s["start"], s["end"])
        segs.append({"id": i, "start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3),
                     "text": s["text"].strip(), "words": words})
        print(f"  [{mmss(s['start'])}] {s['text'].strip()[:70]}", flush=True)
    return {"language": res.get("language", language), "backend": f"mlx-whisper:{repo}", "segments": segs}


def pick_backend(backend: str) -> str:
    if backend != "auto":
        return backend
    import platform

    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # type: ignore  # noqa: F401

            return "mlx"
        except ImportError:
            pass
    return "faster"


def write_sidecars(project: Project, transcript: dict):
    srt, txt = [], []
    for i, s in enumerate(transcript["segments"], 1):
        srt.append(f"{i}\n{fmt_ts(s['start'])} --> {fmt_ts(s['end'])}\n{s['text']}\n")
        txt.append(f"[{mmss(s['start'])}-{mmss(s['end'])}] #{s['id']} {s['text']}")
    with open(project.path("transcript.srt"), "w", encoding="utf-8") as f:
        f.write("\n".join(srt))
    with open(project.path("transcript.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(txt) + "\n")


def run(slug: str, *, srt: str | None = None, model: str | None = None, language: str | None = None,
        device: str = "auto", resync_only: bool = False, backend: str = "auto") -> dict:
    project = Project(slug)
    meta = project.load_meta()
    cfg = load_config()
    language = language or cfg.get("language", "th")
    out_path = project.path("transcript.json")

    if resync_only:
        tr = read_json(out_path)
        n = resync(tr)
        write_json(out_path, tr)
        write_sidecars(project, tr)
        print(f"resynced {n} edited segment(s)")
        return tr

    if srt:
        tr = from_subtitles(srt, language)
    else:
        src = project.source()
        wav = project.path("audio16k.wav")
        if not os.path.exists(wav):
            ff.run(["-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])
        model = model or cfg.get("asr", {}).get("model", "large-v3-turbo")
        be = pick_backend(backend or cfg.get("asr", {}).get("backend", "auto"))
        print(f"transcribing with {'mlx-whisper' if be == 'mlx' else 'faster-whisper'} {model} ({language}) ...", flush=True)
        if be == "mlx":
            tr = mlx(wav, language, model, cfg.get("asr", {}).get("prompt"))
        else:
            tr = whisper(wav, language, model, cfg.get("asr", {}).get("prompt"), device)
    fixed = apply_fixes(tr, cfg.get("asr", {}).get("fixes", {}))
    write_json(out_path, tr)
    write_sidecars(project, tr)
    meta["transcribed"] = tr["backend"]
    project.save_meta(meta)
    print(f"transcript: {len(tr['segments'])} segments ({fixed} auto-fixed) -> {out_path}")
    return tr
