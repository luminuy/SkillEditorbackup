"""Render the clips described in projects/<slug>/plan.json.

One ffmpeg pass per clip: seek to the clip's window, trim every kept piece
(segments minus silences), reframe each piece to the target canvas, concat,
burn the .ass overlay, process the voice, optionally duck music, then a
second, cheap pass applies two-pass loudness normalisation with the video
stream copied.
"""
from __future__ import annotations

import json
import math
import os
import re
import time

from . import ff
from .captions import AssBuilder, resolve_label
from .config import FONTS_DIR, FORMATS, ROOT, Project, load_config, read_json, write_json
from .timeline import Timeline, subtract


def _even(x: float) -> int:
    return max(2, int(math.ceil(x / 2.0)) * 2)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def reframe_chain(inp: str, out: str, sw: int, sh: int, W: int, H: int, spec: dict, piece: dict, tag: str) -> str:
    """Filter chain turning [inp] (source frame) into [out] (W x H canvas)."""
    mode = piece.get("mode") or spec.get("mode") or "fit"
    zoom = float(piece.get("zoom") or spec.get("zoom") or 1.0)
    cx = float(piece.get("x", spec.get("x", 0.5)))
    cy = float(piece.get("y", spec.get("y", 0.5)))

    if mode == "crop":
        s = max(W / sw, H / sh) * zoom
        w2, h2 = _even(sw * s), _even(sh * s)
        x = int(_clamp(w2 * cx - W / 2, 0, w2 - W))
        y = int(_clamp(h2 * cy - H / 2, 0, h2 - H))
        return f"[{inp}]scale={w2}:{h2}:flags=lanczos,crop={W}:{H}:{x}:{y}[{out}]"

    if mode == "stack":
        regions = spec.get("regions") or piece.get("regions")
        if not regions or len(regions) < 2:
            raise SystemExit("reframe.mode=stack needs reframe.regions: [{x,y,w,h}, ...] (fractions of the source)")
        weights = [float(r.get("weight", 1)) for r in regions]
        heights = [_even(H * w / sum(weights)) for w in weights]
        heights[-1] = H - sum(heights[:-1])
        parts = [f"[{inp}]split={len(regions)}" + "".join(f"[{tag}r{i}]" for i in range(len(regions)))]
        for i, (r, hh) in enumerate(zip(regions, heights)):
            rw, rh = _even(sw * r["w"]), _even(sh * r["h"])
            rx, ry = int(sw * r["x"]), int(sh * r["y"])
            s = max(W / rw, hh / rh)
            w2, h2 = _even(rw * s), _even(rh * s)
            parts.append(f"[{tag}r{i}]crop={rw}:{rh}:{rx}:{ry},scale={w2}:{h2}:flags=lanczos,"
                         f"crop={W}:{hh}:{(w2 - W) // 2}:{(h2 - hh) // 2}[{tag}s{i}]")
        parts.append("".join(f"[{tag}s{i}]" for i in range(len(regions))) + f"vstack=inputs={len(regions)}[{out}]")
        return ";".join(parts)

    # fit: whole frame (optionally zoomed) over a blurred or solid background
    fs = min(W / sw, H / sh) * zoom
    fw, fh = _even(sw * fs), _even(sh * fs)
    cw, ch = min(fw, W), min(fh, H)
    crop = ""
    if cw < fw or ch < fh:
        crop = f",crop={cw}:{ch}:{int(_clamp(fw * cx - cw / 2, 0, fw - cw))}:{int(_clamp(fh * cy - ch / 2, 0, fh - ch))}"
    fg_y = float(spec.get("fg_y", 0.5))
    oy = int(_clamp(H * fg_y - ch / 2, 0, H - ch))
    ox = (W - cw) // 2
    bg = spec.get("bg", "blur")
    if bg == "blur":
        bs = max(W / sw, H / sh)
        bw, bh = _even(sw * bs / 4), _even(sh * bs / 4)
        return (f"[{inp}]split=2[{tag}a][{tag}b];"
                f"[{tag}a]scale={bw}:{bh},crop={W // 4}:{H // 4},boxblur=12:2,scale={W}:{H},"
                f"eq=brightness=-0.10:saturation=1.15[{tag}bg];"
                f"[{tag}b]scale={fw}:{fh}:flags=lanczos{crop}[{tag}fg];"
                f"[{tag}bg][{tag}fg]overlay={ox}:{oy}[{out}]")
    color = bg if re.match(r"^#?[0-9a-fA-F]{6}$", str(bg)) else "#000000"
    return (f"[{inp}]scale={fw}:{fh}:flags=lanczos{crop},"
            f"pad={W}:{H}:{ox}:{oy}:color=0x{color.lstrip('#')}[{out}]")


def load_plan(project: Project) -> dict:
    path = project.path("plan.json")
    if not os.path.exists(path):
        raise SystemExit(f"No plan at {path}. The story-producer writes it (see skill clip-plan).")
    plan = read_json(path)
    duration = project.load_meta().get("duration") or 0
    ids = set()
    for c in plan.get("clips", []):
        if not c.get("id") or c["id"] in ids:
            raise SystemExit(f"clip ids must be unique and non-empty (got {c.get('id')!r})")
        ids.add(c["id"])
        if not c.get("segments"):
            raise SystemExit(f"clip {c['id']}: no segments")
        for s in c["segments"]:
            if not (0 <= s["start"] < s["end"]) or (duration and s["start"] > duration):
                raise SystemExit(f"clip {c['id']}: bad segment {s}")
            if duration:
                s["end"] = min(s["end"], duration)
        fmt = c.get("format", "vertical")
        if fmt not in FORMATS:
            raise SystemExit(f"clip {c['id']}: unknown format {fmt} (use {', '.join(FORMATS)})")
    return plan


def _clip_words(project: Project, tl: Timeline) -> list[dict]:
    tpath = project.path("transcript.json")
    if not os.path.exists(tpath):
        return []
    words = []
    for seg in read_json(tpath)["segments"]:
        for w in seg.get("words") or []:
            q = dict(w)
            q["seg"] = seg["id"]
            words.append(q)
    return tl.map_words(words)


def render_clip(project: Project, clip: dict, cfg: dict, meta: dict, draft: bool = False) -> dict:
    t0 = time.time()
    src = project.source()
    W, H = FORMATS[clip.get("format", "vertical")]
    ed = cfg["edit"]
    fps = int(clip.get("fps") or ed["fps"])
    speed = float(clip.get("speed") or 1.0)
    spec = dict(clip.get("reframe") or {})
    sw, sh = meta["width"], meta["height"]

    segments = sorted(clip["segments"], key=lambda s: s["start"]) if clip.get("sort", True) else clip["segments"]
    remove_sil = clip.get("remove_silence", ed["remove_silence"])
    pieces = segments
    if remove_sil and os.path.exists(project.path("silences.json")):
        pieces = subtract(segments, read_json(project.path("silences.json")), ed["pad"], ed["min_piece"])
    if not pieces:
        raise SystemExit(f"clip {clip['id']}: nothing left after silence removal")
    tl = Timeline(pieces)
    total = tl.duration / speed

    # --- overlay (.ass) -------------------------------------------------------
    ass = AssBuilder(W, H, cfg)
    words = _clip_words(project, tl)
    for w in words:
        w["start"] /= speed
        w["end"] /= speed
    cap_over = clip.get("captions")
    if cap_over is not False:
        ass.captions(words, cap_over if isinstance(cap_over, dict) else None)
    ass.hook(clip.get("hook", ""), total, clip.get("hook_seconds", cfg["hook"].get("seconds")))
    for lb in clip.get("labels", []):
        text = resolve_label(lb)
        if not text:
            continue
        at = (tl.map_nearest(lb["at"]) if "at" in lb else float(lb.get("out_at", 0))) / speed
        ass.label(text, at, min(total, at + float(lb.get("duration", 3.0))))
    cta = clip.get("cta", None)
    if cta is None and cfg["cta"].get("enabled"):
        cta = cfg["cta"]["text"]
    if cta:
        ass.cta(cta, total, float(clip.get("cta_seconds", cfg["cta"]["seconds"])))
    ass.watermark(cfg["watermark"].get("text"), total)
    if clip.get("disclaimer", cfg["disclaimer"].get("burn_in")):
        ass.disclaimer(cfg["disclaimer"]["text"], cfg["disclaimer"]["seconds"])
    ass.progress_bar(total)

    work = project.ensure("work")
    renders = project.ensure("renders")
    ass_rel = os.path.join("work", f"{clip['id']}.ass")
    with open(project.path(ass_rel), "w", encoding="utf-8") as f:
        f.write(ass.render())

    # --- filter graph ---------------------------------------------------------
    win_a = max(0.0, min(p["start"] for p in pieces) - 1.0)
    win_b = max(p["end"] for p in pieces) + 0.5
    has_audio = meta.get("has_audio", True)
    inputs = ["-ss", f"{win_a:.3f}", "-t", f"{win_b - win_a:.3f}", "-i", src]
    n = len(tl.pieces)
    g = [f"[0:v]split={n}" + "".join(f"[vs{i}]" for i in range(n)) if n > 1 else "[0:v]null[vs0]"]
    if has_audio:
        g.append(f"[0:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)) if n > 1 else "[0:a]anull[as0]")
    else:
        inputs += ["-f", "lavfi", "-t", f"{win_b - win_a:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        g.append(f"[1:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)) if n > 1 else "[1:a]anull[as0]")
    for i, p in enumerate(tl.pieces):
        a, b = p["start"] - win_a, p["end"] - win_a
        d = b - a
        g.append(f"[vs{i}]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[vt{i}]")
        g.append(reframe_chain(f"vt{i}", f"vr{i}", sw, sh, W, H, spec, p, f"p{i}"))
        g.append(f"[vr{i}]fps={fps},setsar=1,format=yuv420p[v{i}]")
        fade = min(0.02, d / 4)
        g.append(f"[as{i}]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                 f"aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"afade=t=in:d={fade:.3f},afade=t=out:st={d - fade:.3f}:d={fade:.3f}[a{i}]")
    g.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")

    fonts_rel = os.path.relpath(FONTS_DIR, project.dir)
    vpost = f"setpts=PTS/{speed}," if speed != 1.0 else ""
    g.append(f"[vc]{vpost}ass=filename={ff.filter_path(ass_rel)}:fontsdir={ff.filter_path(fonts_rel)}[vout]")

    au = cfg["audio"]
    apost = [f"atempo={speed}"] if speed != 1.0 else []
    if clip.get("voice_enhance", au["voice_enhance"]):
        apost += ["highpass=f=70", "afftdn=nf=-25", "acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2"]
    g.append(f"[ac]{','.join(apost) or 'anull'}[voice]")

    music = clip.get("music", au.get("music"))
    if music:
        mpath = music if os.path.isabs(music) else os.path.join(ROOT, music)
        if not os.path.exists(mpath):
            raise SystemExit(f"music file not found: {mpath}")
        midx = 2 if not has_audio else 1
        inputs += ["-stream_loop", "-1", "-i", mpath]
        vol = float(clip.get("music_volume", au["music_volume"]))
        g.append(f"[{midx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol},atrim=0:{total:.3f},"
                 f"afade=t=in:d=0.8,afade=t=out:st={max(0.0, total - 1.2):.3f}:d=1.2[mus]")
        if au.get("duck", True):
            g.append("[voice]asplit=2[vo1][vo2]")
            g.append("[mus][vo2]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[mduck]")
            g.append("[vo1][mduck]amix=inputs=2:duration=first:normalize=0[amix]")
        else:
            g.append("[voice][mus]amix=inputs=2:duration=first:normalize=0[amix]")
        last = "amix"
    else:
        last = "voice"
    fo = min(float(ed.get("fade_out", 0.35)), total / 4)
    g.append(f"[{last}]afade=t=out:st={max(0.0, total - fo):.3f}:d={fo:.3f}[aout]")

    graph = ";".join(g)
    tmp = os.path.join("work", f"{clip['id']}.pre.mp4")
    out_rel = os.path.join("renders", f"{clip['id']}{'.draft' if draft else ''}.mp4")
    venc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"] if draft else
            ["-c:v", "libx264", "-preset", ed["preset"], "-crf", str(ed["crf"]), "-profile:v", "high",
             "-g", str(fps * 2), "-bf", "2"])
    graph_args = ["-filter_complex", graph]
    if len(graph) > 60000:
        gpath = project.path("work", f"{clip['id']}.graph.txt")
        with open(gpath, "w", encoding="utf-8") as f:
            f.write(graph)
        graph_args = ["-/filter_complex", os.path.relpath(gpath, project.dir)]
    ff.run(["-y", *inputs, *graph_args, "-map", "[vout]", "-map", "[aout]", *venc, "-pix_fmt", "yuv420p",
            "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}", tmp],
           cwd=project.dir)

    # --- two-pass loudness (video copied) -----------------------------------
    target, tp = au["target_lufs"], au["true_peak"]
    stat = ff.run_log(["-i", os.path.join(project.dir, tmp), "-vn",
                       "-af", f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"])
    mj = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stat, re.S)
    m = json.loads(mj.group(0)) if mj else None

    def _finite(v):
        try:
            return float(v) > -70
        except (TypeError, ValueError):
            return False

    if m and not _finite(m.get("input_i")):
        ln = "anull"  # silent (or no) audio: nothing to normalise
    elif m:
        ln = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
              f"linear=true")
    else:
        ln = f"loudnorm=I={target}:TP={tp}:LRA=11"
    ff.run(["-y", "-i", tmp, "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", f"{ln},aresample=48000",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out_rel], cwd=project.dir)
    os.remove(project.path(tmp))

    info = {"id": clip["id"], "file": project.path(out_rel), "duration": round(total, 2), "pieces": n,
            "cut_seconds": round(sum(s["end"] - s["start"] for s in segments) - tl.duration, 2),
            "format": clip.get("format", "vertical"), "size": [W, H], "render_seconds": round(time.time() - t0, 1)}
    print(f"  ✓ {clip['id']}: {info['duration']}s, {n} piece(s), {info['cut_seconds']}s silence removed "
          f"-> {out_rel} ({info['render_seconds']}s)", flush=True)
    return info


def run(slug: str, only: list[str] | None = None, draft: bool = False) -> list[dict]:
    project = Project(slug)
    meta = project.load_meta()
    cfg = load_config()
    plan = load_plan(project)
    clips = [c for c in plan["clips"] if not only or c["id"] in only]
    if only and not clips:
        raise SystemExit(f"no clips match {only}")
    print(f"rendering {len(clips)} clip(s) from {slug}{' [draft]' if draft else ''}", flush=True)
    results = []
    manifest_path = project.path("renders", "manifest.json")
    manifest = read_json(manifest_path) if os.path.exists(manifest_path) else {}
    for c in clips:
        info = render_clip(project, c, cfg, meta, draft)
        info["title"] = c.get("title", "")
        manifest[c["id"] + (".draft" if draft else "")] = info
        results.append(info)
        write_json(manifest_path, manifest)
    return results
