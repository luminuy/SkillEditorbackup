"""Hand-off to professional NLEs: Final Cut Pro, DaVinci Resolve, Premiere Pro.

`nle SLUG` writes projects/<slug>/nle/:
  <slug>.fcpxml      one event, one vertical project per clip; the cut is a spine of asset-clips that
                     point at the ORIGINAL source (non-destructive, full handles for trimming), markers
                     for card reveals / fx / sfx / transitions, PNG overlays (hook, labels, CTA) on lane 1
                     → Final Cut Pro: File ▸ Import ▸ XML · DaVinci Resolve: File ▸ Import ▸ Timeline
  <clip>.edl         CMX3600 cut list per clip → Premiere Pro / Resolve / Avid (File ▸ Import)
  <clip>.srt         captions on the clip timeline → FCP: File ▸ Import ▸ Captions · Resolve/Premiere: import SRT
  overlays/<clip>/*  transparent PNGs (same as the CapCut kit)
  markers_<clip>.csv every beat with a note
"""
from __future__ import annotations

import os
from fractions import Fraction
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

from .captions import AssBuilder
from .config import FORMATS, Project, load_config
from .render import load_plan, prepare_clip, raw_clip

STD_RATES = [(23.976, Fraction(1001, 24000)), (24, Fraction(1, 24)), (25, Fraction(1, 25)),
             (29.97, Fraction(1001, 30000)), (30, Fraction(1, 30)), (50, Fraction(1, 50)),
             (59.94, Fraction(1001, 60000)), (60, Fraction(1, 60))]


def frame_duration(fps: float) -> Fraction:
    best = min(STD_RATES, key=lambda r: abs(r[0] - fps))
    return best[1] if abs(best[0] - fps) < 0.6 else Fraction(1, 30)


def rt(seconds: float, fd: Fraction) -> str:
    """Seconds -> FCPXML rational time snapped to the frame grid."""
    frames = round(seconds / fd)
    v = fd * frames
    return f"{v.numerator}/{v.denominator}s" if v.denominator != 1 else f"{v.numerator}s"


def tc(seconds: float, fps_int: int) -> str:
    f = int(round(seconds * fps_int))
    h, f = divmod(f, 3600 * fps_int)
    m, f = divmod(f, 60 * fps_int)
    s, f = divmod(f, fps_int)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def _file_url(path: str) -> str:
    return "file://" + quote(os.path.abspath(path))


def build(slug: str, only: list[str] | None = None) -> str:
    from .capcut import _png_overlay, _srt

    project = Project(slug)
    meta = project.load_meta()
    cfg = load_config()
    plan = load_plan(project)
    clips = [c for c in plan["clips"] if not only or c["id"] in only]
    if not clips:
        raise SystemExit(f"no clips match {only}")
    out_dir = project.ensure("nle")
    src = project.source()
    fd_src = frame_duration(meta.get("fps") or 30)
    fps_int = round(1 / fd_src)
    dur_src = meta.get("duration") or 0

    res = [
        f'<format id="fsrc" name="SourceFormat" frameDuration="{fd_src.numerator}/{fd_src.denominator}s" '
        f'width="{meta["width"]}" height="{meta["height"]}"/>',
        f'<asset id="asrc" name={quoteattr(os.path.basename(src))} start="0s" duration="{rt(dur_src, fd_src)}" '
        f'hasVideo="1" hasAudio="{1 if meta.get("has_audio", True) else 0}" format="fsrc" audioSources="1" '
        f'audioChannels="2" audioRate="48000"><media-rep kind="original-media" src={quoteattr(_file_url(src))}/></asset>',
        '<format id="fstill" name="FFVideoFormatRateUndefined" width="1080" height="1920"/>',
    ]
    fmt_ids: dict[tuple, str] = {}
    projects_xml = []
    asset_n = 0

    for clip in clips:
        W, H = FORMATS[clip.get("format", "vertical")]
        key = (W, H)
        if key not in fmt_ids:
            fid = f"fseq{len(fmt_ids)}"
            fmt_ids[key] = fid
            res.append(f'<format id="{fid}" name="Vertical{W}x{H}" frameDuration="{fd_src.numerator}/{fd_src.denominator}s" '
                       f'width="{W}" height="{H}"/>')
        prep = prepare_clip(project, raw_clip(clip), cfg, meta)   # pure cuts: same timing as the edit decisions
        hint = prepare_clip(project, dict(clip, transition="cut", segments=[
            {k: v for k, v in s.items() if k != "transition_in"} for s in clip["segments"]]), cfg, meta)
        tl, speed = prep["tl"], prep["speed"]
        pieces = tl.pieces
        conform = "fill" if (clip.get("reframe") or {}).get("mode") == "crop" else "fit"

        # markers (output time) -> the piece that contains them
        marks = []
        for lb in hint["labels"]:
            marks.append((lb["t"], f"เปิดไพ่: {lb['text']}"))
        ev = hint["events"]
        for a in ev["ass"]:
            marks.append((a["t"], f"FX {a['kind']}"))
        for z in ev["zoom"]:
            marks.append((z["t"], "FX punch-in" if z["shape"] == "kick" else "FX zoom"))
        for sh in ev["shake"]:
            marks.append((sh["t"], "FX shake"))
        for c in ev["sfx"]:
            marks.append((c["t"], f"SFX {c['name']}"))
        ordered = sorted(clip["segments"], key=lambda s: s["start"]) if clip.get("sort", True) else clip["segments"]
        from . import effects
        for p in pieces[1:]:
            if p.get("_first_of_seg"):
                k = effects.parse_transition(ordered[p["_seg"]].get("transition_in", clip.get("transition")),
                                             hint["style"])[0]
                if k not in ("cut", "none"):
                    marks.append((p["out_start"] / speed, f"TRANSITION {k}"))

        def locate(t_out):
            t = t_out * speed
            for p in pieces:
                if p["out_start"] - 1e-6 <= t < p["out_end"] + 1e-6:
                    return p, p["start"] + (t - p["out_start"])
            return pieces[-1], pieces[-1]["end"] - 0.04

        by_piece: dict[int, list[str]] = {}
        for t, name in sorted(marks):
            p, src_t = locate(t)
            by_piece.setdefault(id(p), []).append(
                f'<marker start="{rt(src_t, fd_src)}" duration="{rt(fd_src, fd_src)}" value={quoteattr(name)}/>')

        # overlays as connected stills
        ov_dir = os.path.join(out_dir, "overlays", clip["id"])
        os.makedirs(ov_dir, exist_ok=True)
        work = project.ensure("work", f"nle_{clip['id']}")
        overlays = []
        if clip.get("hook"):
            o = AssBuilder(W, H, cfg)
            o.hook(clip["hook"], 5, None)
            _png_overlay(o, os.path.join(ov_dir, "hook.png"), W, H, work)
            hs = clip.get("hook_seconds", cfg["hook"].get("seconds"))
            overlays.append(("hook.png", 0.0, prep["total"] if hs in (None, 0, "full") else float(hs)))
        for i, lb in enumerate(hint["labels"], 1):
            o = AssBuilder(W, H, cfg)
            o.label(lb["text"], 0, 5)
            _png_overlay(o, os.path.join(ov_dir, f"label_{i:02d}.png"), W, H, work)
            overlays.append((f"label_{i:02d}.png", lb["t"], lb["end"] - lb["t"]))
        if prep["cta"]:
            o = AssBuilder(W, H, cfg)
            o.cta(prep["cta"], 5, 5)
            _png_overlay(o, os.path.join(ov_dir, "cta.png"), W, H, work)
            overlays.append(("cta.png", max(0.0, prep["total"] - prep["cta_secs"]), prep["cta_secs"]))
        import shutil
        shutil.rmtree(work, ignore_errors=True)
        by_piece_ov: dict[int, list[str]] = {}
        for name, t, d in overlays:
            asset_n += 1
            aid = f"aov{asset_n}"
            res.append(f'<asset id="{aid}" name={quoteattr(clip["id"] + "_" + name)} start="0s" duration="0s" hasVideo="1" '
                       f'format="fstill" videoSources="1"><media-rep kind="original-media" '
                       f'src={quoteattr(_file_url(os.path.join(ov_dir, name)))}/></asset>')
            p, src_t = locate(t)
            by_piece_ov.setdefault(id(p), []).append(
                f'<video ref="{aid}" lane="1" offset="{rt(src_t, fd_src)}" name={quoteattr(name)} start="0s" '
                f'duration="{rt(max(d, 0.1) * speed, fd_src)}"/>')

        # spine
        spine = []
        for i, p in enumerate(pieces):
            inner = [f'<adjust-conform type="{conform}"/>'] + by_piece_ov.get(id(p), []) + by_piece.get(id(p), [])
            piece_name = quoteattr(clip["id"] + " #" + str(i + 1))
            spine.append(
                f'<asset-clip ref="asrc" offset="{rt(p["out_start"], fd_src)}" name={piece_name} '
                f'start="{rt(p["start"], fd_src)}" duration="{rt(p["end"] - p["start"], fd_src)}" format="fsrc" '
                f'tcFormat="NDF">' + "".join(inner) + "</asset-clip>")
        seq_dur = rt(tl.duration, fd_src)
        note = f"hook: {clip.get('hook', '')} · style: {hint['style']['name']} · speed {speed}"
        projects_xml.append(
            f'<project name={quoteattr(clip["id"])}><sequence format="{fmt_ids[key]}" duration="{seq_dur}" '
            f'tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k"><note>{escape(note)}</note>'
            f'<spine>{"".join(spine)}</spine></sequence></project>')

        # EDL (cut list) + SRT + markers csv
        lines = [f"TITLE: {clip['id']}", "FCM: NON-DROP FRAME", ""]
        for i, p in enumerate(pieces, 1):
            lines.append(f"{i:03d}  AX       B     C        {tc(p['start'], fps_int)} {tc(p['end'], fps_int)} "
                         f"{tc(p['out_start'], fps_int)} {tc(p['out_end'], fps_int)}")
            lines.append(f"* FROM CLIP NAME: {os.path.basename(src)}")
            lines.append("")
        with open(os.path.join(out_dir, f"{clip['id']}.edl"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        ab = AssBuilder(W, H, cfg)
        cap_over = clip.get("captions") if isinstance(clip.get("captions"), dict) else None
        # SRT on the *unsped* edit timeline (NLE timeline = cut list; apply speed in the NLE if wanted)
        words = [dict(w, start=w["start"] * speed, end=w["end"] * speed) for w in prep["words"]]
        cards = ab.caption_cards(words, cap_over)
        _srt([(c["start"], c["end"], "\n".join("".join(w["text"] for w in ln).strip() for ln in c["lines"]))
              for c in cards], os.path.join(out_dir, f"{clip['id']}.srt"))
        with open(os.path.join(out_dir, f"markers_{clip['id']}.csv"), "w", encoding="utf-8-sig") as f:
            f.write("timecode,seconds,marker\n")
            for t, name in sorted(marks):
                f.write(f"{tc(t * speed, fps_int)},{t * speed:.2f},\"{name}\"\n")

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.9">\n'
           f'<resources>\n{chr(10).join(res)}\n</resources>\n'
           f'<library><event name={quoteattr("clipstudio " + slug)}>\n{chr(10).join(projects_xml)}\n</event></library>\n'
           '</fcpxml>\n')
    path = os.path.join(out_dir, f"{slug}.fcpxml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"  ✓ FCPXML  {path}  ({len(clips)} project(s))")
    print(f"  ✓ EDL/SRT/markers/overlays in {out_dir}")
    return path
