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

from . import effects, ff, sfx
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


def raw_clip(clip: dict) -> dict:
    """The same cut with every effect removed (for hand-finishing in CapCut)."""
    segs = [{k: v for k, v in sg.items() if k != "transition_in"} for sg in clip["segments"]]
    return dict(clip, style="none", transition="cut", fx=[], sfx=[], segments=segs, auto_fx=False)


def prepare_clip(project: Project, clip: dict, cfg: dict, meta: dict) -> dict:
    """Resolve pieces, timeline, words, labels and effect events for one clip (no rendering)."""
    ed = cfg["edit"]
    speed = float(clip.get("speed") or 1.0)
    st = effects.style_for(clip, cfg)
    segments = sorted(clip["segments"], key=lambda s: s["start"]) if clip.get("sort", True) else list(clip["segments"])
    segments = [dict(s, _seg=i) for i, s in enumerate(segments)]
    remove_sil = clip.get("remove_silence", ed["remove_silence"])
    pieces = [dict(s) for s in segments]
    if remove_sil and os.path.exists(project.path("silences.json")):
        pieces = subtract(segments, read_json(project.path("silences.json")), ed["pad"], ed["min_piece"])
    if not pieces:
        raise SystemExit(f"clip {clip['id']}: nothing left after silence removal")
    seen = set()
    for p in pieces:
        p["_first_of_seg"] = p["_seg"] not in seen
        seen.add(p["_seg"])
    effects.assign_transitions(pieces, segments, clip, st)
    effects.clamp_overlaps(pieces)
    tl = Timeline(pieces)
    total = tl.duration / speed

    words = _clip_words(project, tl)
    for w in words:
        w["start"] /= speed
        w["end"] /= speed
    labels_out = []
    for lb in clip.get("labels", []):
        text = resolve_label(lb)
        if text:
            at = (tl.map_nearest(lb["at"]) if "at" in lb else float(lb.get("out_at", 0))) / speed
            labels_out.append({"t": at, "end": min(total, at + float(lb.get("duration", 3.0))), "text": text,
                               "y": cfg["labels"]["y"] + 0.03, "card": lb.get("card")})
    cta = clip.get("cta", None)
    if cta is None and cfg["cta"].get("enabled"):
        cta = (cfg.get("cta_by_kind") or {}).get(clip.get("kind", ""), cfg["cta"]["text"])
    cta_secs = float(clip.get("cta_seconds", cfg["cta"]["seconds"]))
    clip = dict(clip, _cta_start=max(0.0, total - cta_secs) if cta else None)
    emphasis = list(cfg.get("effects", {}).get("emphasis_words", [])) + list(clip.get("emphasis", []))
    ev = effects.build_events(clip, st, tl, labels_out, total, speed, words, emphasis)
    return {"clip": clip, "style": st, "segments": segments, "tl": tl, "total": total, "speed": speed,
            "words": words, "labels": labels_out, "cta": cta, "cta_secs": cta_secs, "events": ev,
            "emphasis": emphasis}


def build_ass(prep: dict, cfg: dict, W: int, H: int, text_layers: bool = True) -> AssBuilder:
    clip, total, st = prep["clip"], prep["total"], prep["style"]
    ass = AssBuilder(W, H, cfg)
    if text_layers:
        cap_over = clip.get("captions")
        if cap_over is not False:
            ass.captions(prep["words"], cap_over if isinstance(cap_over, dict) else None,
                         anim=clip.get("caption_anim", st.get("caption_anim", "none")), emphasis=prep["emphasis"])
        ass.hook(clip.get("hook", ""), total, clip.get("hook_seconds", cfg["hook"].get("seconds")))
        for lb in prep["labels"]:
            ass.label(lb["text"], lb["t"], lb["end"])
        if prep["cta"]:
            ass.cta(prep["cta"], total, prep["cta_secs"])
        ass.watermark(cfg["watermark"].get("text"), total)
        if clip.get("disclaimer", cfg["disclaimer"].get("burn_in")):
            ass.disclaimer(cfg["disclaimer"]["text"], cfg["disclaimer"]["seconds"])
        ass.progress_bar(total)
    ass.fx(prep["events"]["ass"])
    return ass


def render_clip(project: Project, clip: dict, cfg: dict, meta: dict, draft: bool = False,
                variant: str = "final", out_rel: str | None = None) -> dict:
    """variant: final (everything burned in) | clean (no text layers; effects kept) | raw (no text, no effects)."""
    t0 = time.time()
    src = project.source()
    W, H = FORMATS[clip.get("format", "vertical")]
    ed = cfg["edit"]
    fps = int(clip.get("fps") or ed["fps"])
    if variant == "raw":
        clip = raw_clip(clip)
    prep = prepare_clip(project, clip, cfg, meta)
    tl, total, speed, st, ev = prep["tl"], prep["total"], prep["speed"], prep["style"], prep["events"]
    spec = dict(clip.get("reframe") or {})
    sw, sh = meta["width"], meta["height"]

    project.ensure("work")
    project.ensure("renders")
    tag = "" if variant == "final" else f".{variant}"
    ass_rel = os.path.join("work", f"{clip['id']}{tag}.ass")
    with open(project.path(ass_rel), "w", encoding="utf-8") as f:
        f.write(build_ass(prep, cfg, W, H, text_layers=(variant == "final")).render())

    # --- inputs ---------------------------------------------------------------
    pieces = tl.pieces
    win_a = max(0.0, min(p["start"] for p in pieces) - 1.0)
    win_b = max(p["end"] for p in pieces) + 0.5
    has_audio = meta.get("has_audio", True)
    inputs = ["-ss", f"{win_a:.3f}", "-t", f"{win_b - win_a:.3f}", "-i", src]
    next_idx = 1
    n = len(pieces)
    g = [f"[0:v]split={n}" + "".join(f"[vs{i}]" for i in range(n)) if n > 1 else "[0:v]null[vs0]"]
    if has_audio:
        g.append(f"[0:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)) if n > 1 else "[0:a]anull[as0]")
    else:
        inputs += ["-f", "lavfi", "-t", f"{win_b - win_a:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        g.append(f"[{next_idx}:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)) if n > 1 else f"[{next_idx}:a]anull[as0]")
        next_idx += 1

    # --- pieces ---------------------------------------------------------------
    for i, p in enumerate(pieces):
        a, b = p["start"] - win_a, p["end"] - win_a
        d = b - a
        g.append(f"[vs{i}]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[vt{i}]")
        g.append(reframe_chain(f"vt{i}", f"vr{i}", sw, sh, W, H, spec, p, f"p{i}"))
        g.append(f"[vr{i}]fps={fps},setsar=1,format=yuv420p,settb=1/{fps * 1000}[v{i}]")
        fade = min(0.02, d / 4)
        g.append(f"[as{i}]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                 f"aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"afade=t=in:d={fade:.3f},afade=t=out:st={d - fade:.3f}:d={fade:.3f}[a{i}]")

    # --- join: hard cuts inside groups (concat), smooth transitions between groups (xfade) ----
    groups: list[list[int]] = [[0]]
    for i in range(1, n):
        if pieces[i].get("overlap", 0) > 0:
            groups.append([i])
        else:
            groups[-1].append(i)
    for gi, idxs in enumerate(groups):
        if len(idxs) == 1:
            g.append(f"[v{idxs[0]}]null[gv{gi}];[a{idxs[0]}]anull[ga{gi}]")
        else:  # concat may change the timebase; xfade needs identical ones
            g.append("".join(f"[v{i}][a{i}]" for i in idxs) + f"concat=n={len(idxs)}:v=1:a=1[gc{gi}][ga{gi}]")
            g.append(f"[gc{gi}]settb=1/{fps * 1000}[gv{gi}]")
    acc_v, acc_a = "gv0", "ga0"
    acc_len = pieces[groups[0][-1]]["out_end"]
    for gi in range(1, len(groups)):
        first = pieces[groups[gi][0]]
        d = first["overlap"]
        off = acc_len - d
        g.append(f"[{acc_v}][gv{gi}]xfade=transition={first['trans']}:duration={d:.3f}:offset={off:.3f}[xv{gi}]")
        g.append(f"[{acc_a}][ga{gi}]acrossfade=d={d:.3f}:c1=tri:c2=tri[xa{gi}]")
        acc_v, acc_a = f"xv{gi}", f"xa{gi}"
        acc_len = pieces[groups[gi][-1]]["out_end"]

    # --- video post: speed, motion, vignette, glitch, overlay text/fx ---------------------
    vchain = []
    if speed != 1.0:
        vchain.append(f"setpts=PTS/{speed}")
    oversample = 1 if draft else int(cfg.get("effects", {}).get("motion_oversample", 2))
    zp = effects.zoompan_filter(ev, st, W, H, fps, total, oversample)
    if zp:
        vchain.append(zp)
    if st.get("vignette") and clip.get("vignette", True):
        vchain.append("vignette=angle=PI/5:mode=forward")
    gl = effects.glitch_filter(ev)
    if gl:
        vchain.append(gl)
    fonts_rel = os.path.relpath(FONTS_DIR, project.dir)
    vchain.append(f"ass=filename={ff.filter_path(ass_rel)}:fontsdir={ff.filter_path(fonts_rel)}")
    vchain.append("format=yuv420p")
    g.append(f"[{acc_v}]{','.join(vchain)}[vout]")

    # --- audio: voice -> music (ducked) -> sfx -> fade ----------------------------------
    au = cfg["audio"]
    apost = [f"atempo={speed}"] if speed != 1.0 else []
    if clip.get("voice_enhance", au["voice_enhance"]):
        apost += ["highpass=f=70", "afftdn=nf=-25", "acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2"]
    g.append(f"[{acc_a}]{','.join(apost) or 'anull'}[voice]")
    last = "voice"
    music = clip.get("music", au.get("music"))
    if music:
        mpath = music if os.path.isabs(music) else os.path.join(ROOT, music)
        if not os.path.exists(mpath):
            raise SystemExit(f"music file not found: {mpath}")
        inputs += ["-stream_loop", "-1", "-i", mpath]
        midx = next_idx
        next_idx += 1
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
    cues = [c for c in ev["sfx"] if c["t"] < total - 0.05] if clip.get("sfx_enabled", au.get("sfx", True)) else []
    if cues:
        by_name: dict[str, list[dict]] = {}
        for c in cues:
            by_name.setdefault(c["name"], []).append(c)
        labels = []
        master = float(au.get("sfx_volume", 1.0))
        for name, items in by_name.items():
            inputs += ["-i", sfx.path(name)]
            idx = next_idx
            next_idx += 1
            outs = [f"s{idx}_{j}" for j in range(len(items))]
            g.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit={len(items)}"
                     + "".join(f"[{o}r]" for o in outs) if len(items) > 1 else
                     f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo[{outs[0]}r]")
            for o, c in zip(outs, items):
                ms = int(max(0.0, c["t"]) * 1000)
                g.append(f"[{o}r]adelay={ms}|{ms},volume={c['volume'] * master:.3f}[{o}]")
                labels.append(o)
        g.append(f"[{last}]" + "".join(f"[{o}]" for o in labels)
                 + f"amix=inputs={1 + len(labels)}:duration=first:normalize=0:dropout_transition=0[withsfx]")
        last = "withsfx"
    fo = min(float(ed.get("fade_out", 0.35)), total / 4)
    g.append(f"[{last}]afade=t=out:st={max(0.0, total - fo):.3f}:d={fo:.3f}[aout]")

    graph = ";".join(g)
    tmp = os.path.join("work", f"{clip['id']}{tag}.pre.mp4")
    if out_rel is None:
        out_rel = os.path.join("renders", f"{clip['id']}{tag}{'.draft' if draft else ''}.mp4")
    venc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"] if draft else
            ["-c:v", "libx264", "-preset", ed["preset"], "-crf", str(ed["crf"]), "-profile:v", "high",
             "-g", str(fps * 2), "-bf", "2"])
    graph_args = ["-filter_complex", graph]
    if len(graph) > 60000:
        gpath = project.path("work", f"{clip['id']}{tag}.graph.txt")
        with open(gpath, "w", encoding="utf-8") as f:
            f.write(graph)
        graph_args = ["-/filter_complex", os.path.relpath(gpath, project.dir)]
    with open(project.path("work", f"{clip['id']}{tag}.graph.debug.txt"), "w", encoding="utf-8") as f:
        f.write(graph.replace(";", ";\n"))  # human-readable copy for debugging
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
    os.makedirs(os.path.dirname(project.path(out_rel)), exist_ok=True)
    ff.run(["-y", "-i", tmp, "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", f"{ln},aresample=48000",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out_rel], cwd=project.dir)
    os.remove(project.path(tmp))

    trans = [p["trans"] for p in pieces if p.get("trans") and p["trans"] != "cut"]
    info = {"id": clip["id"], "file": project.path(out_rel), "variant": variant, "duration": round(total, 2),
            "pieces": n, "cut_seconds": round(sum(s["end"] - s["start"] for s in prep["segments"]) - tl.duration, 2),
            "format": clip.get("format", "vertical"), "size": [W, H], "style": st["name"],
            "transitions": trans, "fx": len(ev["ass"]) + len(ev["zoom"]) + len(ev["shake"]) + len(ev["glitch"]),
            "sfx": len(cues), "render_seconds": round(time.time() - t0, 1)}
    print(f"  ✓ {clip['id']}{tag}: {info['duration']}s, {n} piece(s), {info['cut_seconds']}s silence removed, "
          f"style={st['name']}, {len(trans)} transition(s), {info['fx']} fx, {len(cues)} sfx "
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
