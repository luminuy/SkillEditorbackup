"""clipstudio CLI — run from the repo root:  python3 -m clipstudio <command> ...

  doctor                         check ffmpeg / whisper / fonts / pythainlp
  init VIDEO [--name SLUG]       create projects/SLUG from a source video
  transcribe SLUG [--srt F] [--model M] [--backend auto|faster|mlx] [--resync]
  fix SLUG ID "text" [ID "text"]  correct transcript segments (keeps timings)
  analyze SLUG                   silences, chapters, clip candidates, risk flags
  frames SLUG [--times 1,2] [--every S] [--count N]   contact sheet to look at
  find SLUG "text"               exact source time of a word/phrase (for labels, fx)
  plan-check SLUG                validate plan.json (durations, hooks, card ids, styles); exit 1 on errors
  render SLUG [--clip ID ...] [--draft]
  capcut SLUG [--clip ID] [--raw] [--zip]  CapCut kit: clean video + .srt + PNG overlays + sfx + edit guide
  nle SLUG [--clip ID]           Final Cut Pro / DaVinci Resolve (FCPXML) + Premiere (EDL) + SRT + overlays
  sfx                            list / build the sound-effect library
  snapshot SLUG CLIP             contact sheet of a rendered clip (visual QA)
  thumbnail SLUG --time T --title TEXT [--sub TEXT] [--size 1080x1920] [--clip ID] [--x 0.5]
  qa SLUG [--clip ID ...]
  review SLUG [--start YYYY-MM-DD]   review.html + schedule.csv + publish/*.txt
  cards [--search Q] [--id ID] [--json]
  status SLUG
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import ff
from .config import FONTS_DIR, ROOT, Project, load_config, read_json, slugify


def cmd_doctor(_a):
    ok = True
    try:
        print(f"ffmpeg      : {ff.ffmpeg_bin()}")
        out = ff.run(["-filters"], quiet=False).stdout
        for flt in ("ass", "loudnorm", "silencedetect", "sidechaincompress", "afftdn"):
            has = f" {flt} " in out
            ok &= has
            print(f"  filter {flt:18}: {'ok' if has else 'MISSING'}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"ffmpeg      : MISSING ({e})")
    print(f"ffprobe     : {ff.ffprobe_bin() or 'not found (fallback parser is used)'}")
    for mod, why in (("faster_whisper", "speech-to-text"), ("pythainlp", "Thai word breaks"),
                     ("PIL", "text measuring + contact sheets")):
        try:
            __import__(mod)
            print(f"{mod:12}: ok ({why})")
        except ImportError:
            print(f"{mod:12}: missing — pip install -r requirements.txt ({why})")
            ok &= mod != "PIL"
    import platform

    from . import finish

    if platform.system() == "Darwin":
        try:
            __import__("mlx_whisper")
            mlx_ok = "ok (Apple Silicon GPU)"
        except ImportError:
            mlx_ok = "not installed — pip install mlx-whisper (much faster on M-series)"
        print(f"mlx_whisper : {mlx_ok}")
        print(f"videotoolbox: {'ok (fast drafts)' if 'h264_videotoolbox' in finish.encoders() else 'not in this ffmpeg'}")
    fonts = sorted(f for f in os.listdir(FONTS_DIR) if f.endswith((".ttf", ".otf")))
    print(f"fonts       : {', '.join(fonts) or 'NONE'}")
    cfg = load_config()
    print(f"config      : {cfg.get('channel_name')} {cfg.get('handle')} niche={cfg.get('niche')} "
          f"platforms={','.join(cfg.get('platforms', []))}")
    print("READY" if ok else "NOT READY — fix the items above")
    return 0 if ok else 1


def cmd_init(a):
    src = os.path.abspath(a.video)
    if not os.path.exists(src):
        sys.exit(f"not found: {src}")
    slug = a.name or slugify(src)
    project = Project(slug)
    os.makedirs(project.dir, exist_ok=True)
    info = ff.probe(src)
    rel = os.path.relpath(src, ROOT)
    meta = {"slug": slug, "source": rel if not rel.startswith("..") else src, **info}
    project.save_meta(meta)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"project: {project.dir}")


def cmd_transcribe(a):
    from . import transcribe

    transcribe.run(a.slug, srt=a.srt, model=a.model, language=a.lang, device=a.device, resync_only=a.resync,
                   backend=a.backend)


def cmd_fix(a):
    """Replace the text of transcript segments: fix SLUG ID "new text" [ID "text" ...]."""
    from . import transcribe
    from .config import write_json

    project = Project(a.slug)
    tr = read_json(project.path("transcript.json"))
    by_id = {s["id"]: s for s in tr["segments"]}
    pairs = a.pairs
    if len(pairs) % 2:
        sys.exit("usage: fix SLUG ID \"text\" [ID \"text\" ...]")
    for i in range(0, len(pairs), 2):
        sid = int(pairs[i])
        if sid not in by_id:
            sys.exit(f"no segment #{sid}")
        print(f"#{sid}: {by_id[sid]['text']}\n  -> {pairs[i + 1]}")
        by_id[sid]["text"] = pairs[i + 1]
    n = transcribe.resync(tr)
    write_json(project.path("transcript.json"), tr)
    transcribe.write_sidecars(project, tr)
    print(f"updated {n} segment(s); transcript.txt/.srt refreshed")


def cmd_analyze(a):
    from . import analyze

    analyze.run(a.slug)


def cmd_frames(a):
    from . import thumbnail

    times = [float(x) for x in a.times.split(",")] if a.times else None
    thumbnail.frames(a.slug, times, a.every, a.count, video=a.video, tag=a.tag)


def cmd_plan_check(a):
    """Validate plan.json: structure, card ids, styles/transitions, durations per platform, hook length."""
    from . import cards
    from .config import PLATFORMS
    from .render import load_plan, prepare_clip
    from .textutil import EMOJI_RE, visible_len

    project = Project(a.slug)
    plan = load_plan(project)
    cfg = load_config()
    meta = project.load_meta()
    errors = warns = 0
    for c in plan["clips"]:
        msgs = []
        try:
            prep = prepare_clip(project, c, cfg, meta)
            d = prep["total"]
        except SystemExit as e:
            msgs.append(("ERROR", str(e)))
            d = 0.0
            prep = None
        for lb in c.get("labels", []):
            if lb.get("card") and not cards.get(lb["card"]):
                msgs.append(("ERROR", f"unknown card id '{lb['card']}' (python3 -m clipstudio cards --search ...)"))
            if "at" in lb and not any(s["start"] - 0.5 <= lb["at"] <= s["end"] + 0.5 for s in c["segments"]):
                msgs.append(("WARN", f"label at {lb['at']}s is outside every segment (it will snap to the next piece)"))
        sp = float(c.get("speed") or 1.0)
        if not 0.8 <= sp <= 1.2:
            msgs.append(("ERROR", f"speed {sp} out of range 0.8–1.2"))
        hook = c.get("hook", "")
        if not hook:
            msgs.append(("WARN", "no hook text"))
        elif visible_len(hook) > 40:
            msgs.append(("WARN", f"hook is {visible_len(hook)} visible chars (> 40; tone/vowel marks not counted)"))
        if EMOJI_RE.search(hook):
            msgs.append(("WARN", "emoji in hook will be removed (no emoji on video)"))
        for p in c.get("platforms") or cfg.get("platforms", []):
            spec = PLATFORMS.get(p)
            if not spec:
                msgs.append(("ERROR", f"unknown platform '{p}' (use {', '.join(PLATFORMS)})"))
                continue
            if d and d > spec["max_seconds"]:
                msgs.append(("ERROR", f"{spec['label']}: {d:.1f}s > {spec['max_seconds']}s limit"))
            elif d and not spec["sweet_spot"][0] <= d <= spec["sweet_spot"][1]:
                msgs.append(("WARN", f"{spec['label']}: {d:.1f}s outside sweet spot {spec['sweet_spot'][0]}-{spec['sweet_spot'][1]}s"))
        fx = ""
        if prep:
            ev = prep["events"]
            fx = (f" style={prep['style']['name']} fx={len(ev['ass']) + len(ev['zoom']) + len(ev['shake'])}"
                  f" sfx={len(ev['sfx'])}")
        print(f"{c['id']:22} {c.get('format', 'vertical'):9} ~{d:5.1f}s{fx}  hook: {hook[:40]}")
        for lvl, m in msgs:
            print(f"    {lvl}: {m}")
            errors += lvl == "ERROR"
            warns += lvl == "WARN"
    print(f"plan: {len(plan['clips'])} clip(s), {errors} error(s), {warns} warning(s)")
    return 1 if errors else 0


def cmd_find(a):
    """Find words/phrases in the transcript and print exact source times (for labels / fx 'at')."""
    project = Project(a.slug)
    tr = read_json(project.path("transcript.json"))
    q = a.query.replace(" ", "").lower()
    hits = 0
    for seg in tr["segments"]:
        words = seg.get("words") or []
        joined, starts = "", []
        for w in words:
            for ch in w["text"]:
                if not ch.isspace():
                    starts.append(w["start"])
                    joined += ch.lower()
        i = joined.find(q)
        while i >= 0:
            hits += 1
            print(f"#{seg['id']:<4} at {starts[i]:8.2f}s   {seg['text']}")
            i = joined.find(q, i + 1)
    if not hits:
        print("no match (try a shorter query, or check transcript.txt)")


def cmd_render(a):
    from . import render

    render.run(a.slug, a.clip, a.draft)


def cmd_capcut(a):
    from . import capcut

    capcut.run(a.slug, a.clip, raw=a.raw, draft=a.draft, zip_=a.zip)


def cmd_nle(a):
    from . import nle

    nle.build(a.slug, a.clip)


def cmd_sfx(a):
    from . import sfx

    for name, (desc, _) in sfx.LIBRARY.items():
        print(f"{name:12} {desc}  -> {sfx.path(name)}")


def cmd_snapshot(a):
    from . import thumbnail

    thumbnail.snapshot(a.slug, a.clip)


def cmd_thumbnail(a):
    from . import thumbnail

    name = f"{a.clip}_{a.size}.jpg" if a.clip else None
    thumbnail.thumbnail(a.slug, a.time, a.title, a.sub or "", a.size, a.x, name, video=a.video)


def cmd_qa(a):
    from . import qa

    rep = qa.run(a.slug, a.clip)
    return 1 if rep["summary"]["fail"] else 0


def cmd_review(a):
    from . import review

    review.run(a.slug, a.start)


def cmd_cards(a):
    from . import cards

    if a.id:
        items = [c for c in [cards.get(a.id)] if c]
    elif a.search:
        items = cards.search(a.search)
    else:
        items = cards.all_cards()
    if a.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for c in items:
            print(cards.describe(c) if (a.id or a.search) else f"{c['id']:22} {c['name_en']:22} {c['name_th']}")
    if not items:
        print("no match")


def cmd_status(a):
    project = Project(a.slug)
    meta = project.load_meta()
    steps = [("transcript.json", "transcribe"), ("analysis.json", "analyze"), ("plan.json", "plan (story-producer)"),
             ("renders/manifest.json", "render"), ("copy", "copy (copywriter)"), ("thumbs", "thumbnail"),
             ("qa.json", "qa"), ("review.html", "review")]
    print(f"{a.slug}: {meta.get('source')} {meta.get('width')}x{meta.get('height')} {meta.get('duration', 0):.0f}s")
    for f, label in steps:
        p = project.path(f)
        done = os.path.exists(p) and (not os.path.isdir(p) or os.listdir(p))
        print(f"  [{'x' if done else ' '}] {label}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="clipstudio", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("init"); s.add_argument("video"); s.add_argument("--name"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("transcribe"); s.add_argument("slug"); s.add_argument("--srt"); s.add_argument("--model")
    s.add_argument("--lang"); s.add_argument("--device", default="auto"); s.add_argument("--resync", action="store_true")
    s.add_argument("--backend", default="auto", choices=["auto", "faster", "mlx"])
    s.set_defaults(fn=cmd_transcribe)
    s = sub.add_parser("fix"); s.add_argument("slug"); s.add_argument("pairs", nargs="+"); s.set_defaults(fn=cmd_fix)
    s = sub.add_parser("analyze"); s.add_argument("slug"); s.set_defaults(fn=cmd_analyze)
    s = sub.add_parser("frames"); s.add_argument("slug"); s.add_argument("--times"); s.add_argument("--every", type=float)
    s.add_argument("--count", type=int, default=16); s.add_argument("--video"); s.add_argument("--tag", default="source")
    s.set_defaults(fn=cmd_frames)
    s = sub.add_parser("plan-check"); s.add_argument("slug"); s.set_defaults(fn=cmd_plan_check)
    s = sub.add_parser("find"); s.add_argument("slug"); s.add_argument("query"); s.set_defaults(fn=cmd_find)
    s = sub.add_parser("render"); s.add_argument("slug"); s.add_argument("--clip", action="append")
    s.add_argument("--draft", action="store_true"); s.set_defaults(fn=cmd_render)
    s = sub.add_parser("capcut"); s.add_argument("slug"); s.add_argument("--clip", action="append")
    s.add_argument("--raw", action="store_true"); s.add_argument("--draft", action="store_true")
    s.add_argument("--zip", action="store_true"); s.set_defaults(fn=cmd_capcut)
    sub.add_parser("sfx").set_defaults(fn=cmd_sfx)
    s = sub.add_parser("nle"); s.add_argument("slug"); s.add_argument("--clip", action="append"); s.set_defaults(fn=cmd_nle)
    s = sub.add_parser("snapshot"); s.add_argument("slug"); s.add_argument("clip"); s.set_defaults(fn=cmd_snapshot)
    s = sub.add_parser("thumbnail"); s.add_argument("slug"); s.add_argument("--time", type=float, required=True)
    s.add_argument("--title", required=True); s.add_argument("--sub"); s.add_argument("--size", default="1080x1920")
    s.add_argument("--clip"); s.add_argument("--x", type=float, default=0.5); s.add_argument("--video")
    s.set_defaults(fn=cmd_thumbnail)
    s = sub.add_parser("qa"); s.add_argument("slug"); s.add_argument("--clip", action="append"); s.set_defaults(fn=cmd_qa)
    s = sub.add_parser("review"); s.add_argument("slug"); s.add_argument("--start"); s.set_defaults(fn=cmd_review)
    s = sub.add_parser("cards"); s.add_argument("--search"); s.add_argument("--id"); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_cards)
    s = sub.add_parser("status"); s.add_argument("slug"); s.set_defaults(fn=cmd_status)
    a = p.parse_args(argv)
    try:
        rc = a.fn(a)
    except ff.FFmpegError as e:
        sys.exit(str(e))
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
