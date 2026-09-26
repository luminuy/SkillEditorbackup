"""CapCut hand-off kit.

For editors who finish in CapCut (desktop or mobile) we export, per clip:
  <id>_video.mp4        cut + reframed + cleaned audio, transitions/motion/SFX baked in, NO burned text
                        (--raw: no effects at all, just the cut)
  <id>.srt              caption lines on the clip's own timeline (CapCut: import captions)
  <id>_words.srt        one word per cue (for word-by-word caption animations)
  overlays/*.png        full-frame 1080x1920 transparent PNGs (hook, card labels, CTA, watermark) —
                        drop on an overlay track and stretch to fill; they are already positioned
  sfx/*.wav + sfx.csv   the sound effects and where they go
  markers.csv           every beat (cut, transition, reveal, effect, sfx) with a CapCut suggestion
  EDIT_GUIDE.md         step-by-step Thai guide for this clip
"""
from __future__ import annotations

import csv
import os
import shutil

from . import effects, ff, sfx
from .captions import AssBuilder
from .config import FONTS_DIR, FORMATS, Project, load_config
from .render import load_plan, prepare_clip, raw_clip, render_clip
from .transcribe import fmt_ts, mmss

CAPCUT_HINTS = {
    "flash": "Effects → ค้นหา 'Flash' / 'แฟลช' (ความยาว ~0.3 วิ)",
    "flash-strong": "Effects → 'Flash' แบบเต็มจอ",
    "sparkle": "Effects → ค้นหา 'Sparkle' / 'Star' / 'ประกาย' วางทับช่วงเปิดไพ่ ~1 วิ",
    "stars": "Effects → 'Stars' / 'Starry' / 'ดาว' ~1.5 วิ",
    "glow": "Effects → 'Glow' / 'Light' / 'แสง' แบบนุ่ม ~1.5 วิ",
    "punch": "Keyframe: Scale 100% → 112% → 100% ภายใน ~0.4 วิ (หรือ Effects → 'Zoom' / 'Shake' สั้นๆ)",
    "zoom": "Keyframe: Scale 100% → 115% ค้างไว้ แล้วกลับ 100%",
    "shake": "Effects → ค้นหา 'Shake' / 'สั่น' ~0.4 วิ",
    "glitch": "Effects → ค้นหา 'Glitch' ~0.2 วิ",
}
TRANSITION_HINTS = {
    "fade": "Transition → 'Dissolve' / 'Mix'", "dissolve": "Transition → 'Dissolve'",
    "fadeblack": "Transition → 'Black fade'", "fadewhite": "Transition → 'Flash' / 'White flash'",
    "zoomin": "Transition → 'Pull in' / 'Zoom in'", "smoothleft": "Transition → 'Swipe left' / 'Whip'",
    "slideleft": "Transition → 'Slide left'", "hblur": "Transition → 'Blur'", "circleopen": "Transition → 'Circle'",
    "pixelize": "Transition → 'Glitch' / 'Pixelate'",
}


def _srt(cues: list[tuple[float, float, str]], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, t) in enumerate(cues, 1):
            f.write(f"{i}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{t}\n\n")


def _png_overlay(ab: AssBuilder, out: str, W: int, H: int, work_dir: str):
    """Render an ASS layer to a transparent PNG (difference matting: over black and over white)."""
    import numpy as np  # type: ignore
    from PIL import Image  # type: ignore

    ass_path = os.path.join(work_dir, "overlay.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ab.render())
    shots = []
    fonts_rel = os.path.relpath(FONTS_DIR, work_dir)
    for bg in ("black", "white"):
        png = os.path.join(work_dir, f"ov_{bg}.png")
        ff.run(["-y", "-f", "lavfi", "-i", f"color=c={bg}:s={W}x{H}:d=1", "-vf",
                f"ass=filename=overlay.ass:fontsdir={ff.filter_path(fonts_rel)}", "-ss", "0.5", "-frames:v", "1",
                os.path.basename(png)], cwd=work_dir)
        shots.append(np.asarray(Image.open(png).convert("RGB"), dtype=np.float32))
    b, w = shots
    alpha = np.clip(255.0 - (w - b).max(axis=2), 0, 255)
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    rgb = np.clip(b * 255.0 / safe, 0, 255)
    rgba = np.dstack([rgb, alpha]).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(out)


def export_clip(project: Project, clip: dict, cfg: dict, meta: dict, raw: bool = False, draft: bool = False) -> str:
    cid = clip["id"]
    W, H = FORMATS[clip.get("format", "vertical")]
    kit = project.ensure("capcut", cid)
    os.makedirs(os.path.join(kit, "overlays"), exist_ok=True)
    variant = "raw" if raw else "clean"
    clip_used = raw_clip(clip) if raw else clip
    prep = prepare_clip(project, clip_used, cfg, meta)
    render_clip(project, clip, cfg, meta, draft=draft, variant=variant,
                out_rel=os.path.join("capcut", cid, f"{cid}_video.mp4"))

    # captions
    ab = AssBuilder(W, H, cfg)
    cap_over = clip.get("captions") if isinstance(clip.get("captions"), dict) else None
    cards = ab.caption_cards(prep["words"], cap_over)
    _srt([(c["start"], c["end"], "\n".join("".join(w["text"] for w in ln).strip() for ln in c["lines"]))
          for c in cards], os.path.join(kit, f"{cid}.srt"))
    _srt([(w["start"], max(w["end"], w["start"] + 0.12), w["text"].strip()) for w in prep["words"] if w["text"].strip()],
         os.path.join(kit, f"{cid}_words.srt"))

    # overlays (full-frame transparent PNGs)
    work = project.ensure("work", f"capcut_{cid}")
    made = []
    if clip.get("hook"):
        o = AssBuilder(W, H, cfg)
        o.hook(clip["hook"], 5, None)
        _png_overlay(o, os.path.join(kit, "overlays", "hook.png"), W, H, work)
        made.append(("hook.png", mmss(0), "ตลอดคลิป (หรือ 3–5 วิแรก)"))
    for i, lb in enumerate(prep["labels"], 1):
        o = AssBuilder(W, H, cfg)
        o.label(lb["text"], 0, 5)
        name = f"label_{i:02d}.png"
        _png_overlay(o, os.path.join(kit, "overlays", name), W, H, work)
        made.append((name, mmss(lb["t"]), f"{lb['end'] - lb['t']:.1f} วิ — {lb['text']}"))
    if prep["cta"]:
        o = AssBuilder(W, H, cfg)
        o.cta(prep["cta"], 5, 5)
        _png_overlay(o, os.path.join(kit, "overlays", "cta.png"), W, H, work)
        made.append(("cta.png", mmss(max(0.0, prep["total"] - prep["cta_secs"])), f"{prep['cta_secs']:.1f} วิสุดท้าย"))
    if cfg["watermark"].get("enabled") and cfg["watermark"].get("text"):
        o = AssBuilder(W, H, cfg)
        o.watermark(cfg["watermark"]["text"], 5)
        _png_overlay(o, os.path.join(kit, "overlays", "watermark.png"), W, H, work)
        made.append(("watermark.png", mmss(0), "ตลอดคลิป"))
    shutil.rmtree(work, ignore_errors=True)

    # sfx + markers. In raw mode the video has no effects, so the markers describe the *intended*
    # design (style + fx + sfx) on the raw timeline: same plan with hard cuts only -> identical timing.
    intended = {}
    if raw:
        segs_nt = [{k: v for k, v in sg.items() if k != "transition_in"} for sg in clip["segments"]]
        hint = prepare_clip(project, dict(clip, transition="cut", segments=segs_nt), cfg, meta)
        ev = hint["events"]
        st = hint["style"]
        ordered = sorted(clip["segments"], key=lambda sg: sg["start"]) if clip.get("sort", True) else clip["segments"]
        for i, sg in enumerate(ordered):
            if i:
                intended[i] = effects.parse_transition(sg.get("transition_in", clip.get("transition")), st)[0]
        tsfx = dict(st.get("sfx", {}), **(clip.get("sfx_map") or {})).get("transition")
        if tsfx and clip.get("auto_fx", True):
            for p in prep["tl"].pieces[1:]:
                if p.get("_first_of_seg") and intended.get(p.get("_seg")) not in (None, "cut", "none"):
                    ev["sfx"].append({"name": tsfx, "t": max(0.0, p["out_start"] / prep["speed"] - 0.2),
                                      "volume": effects.SFX_GAIN.get(tsfx, 0.5)})
            ev["sfx"].sort(key=lambda c: c["t"])
    else:
        ev = prep["events"]
    os.makedirs(os.path.join(kit, "sfx"), exist_ok=True)
    with open(os.path.join(kit, "sfx.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "seconds", "file", "volume"])
        for c in ev["sfx"]:
            src = sfx.path(c["name"])
            dst = os.path.join(kit, "sfx", os.path.basename(src))
            if not os.path.exists(dst):
                shutil.copy(src, dst)
            w.writerow([mmss(c["t"]), f"{c['t']:.2f}", f"sfx/{os.path.basename(src)}", f"{c['volume']:.2f}"])

    markers = []
    for p in prep["tl"].pieces[1:]:
        t = p["out_start"] / prep["speed"]
        if raw and p.get("_first_of_seg") and intended.get(p.get("_seg")) not in (None, "cut", "none"):
            k = intended[p["_seg"]]
            markers.append((t, "transition", k, TRANSITION_HINTS.get(k, CAPCUT_HINTS.get(k, f"Transition → '{k}'"))))
        elif p.get("trans") and p["trans"] != "cut":
            markers.append((t, "transition", p["trans"], TRANSITION_HINTS.get(p["trans"], f"Transition → '{p['trans']}'")))
        else:
            markers.append((t, "jump cut", "", "ตัดแล้ว (ไม่ต้องทำอะไร) — ใส่ Zoom 108% สลับได้ถ้าอยากให้จังหวะเร็วขึ้น"))
    for i, lb in enumerate(prep["labels"], 1):
        extra = CAPCUT_HINTS["sparkle"] if raw else "ประกาย/แฟลชอยู่ในวิดีโอแล้ว"
        markers.append((lb["t"], "card reveal", lb["text"], f"วาง overlays/label_{i:02d}.png · {extra}"))
    for a in ev["ass"]:
        markers.append((a["t"], "effect", a["kind"], CAPCUT_HINTS.get(a["kind"], a["kind"])))
    for z in ev["zoom"]:
        markers.append((z["t"], "effect", "punch" if z["shape"] == "kick" else "zoom", CAPCUT_HINTS["punch" if z["shape"] == "kick" else "zoom"]))
    for s in ev["shake"]:
        markers.append((s["t"], "effect", "shake", CAPCUT_HINTS["shake"]))
    for c in ev["sfx"]:
        markers.append((c["t"], "sfx", c["name"], f"Audio → นำเข้า sfx/{c['name']}.wav ระดับเสียง ~{int(c['volume'] * 100)}%"))
    markers.sort(key=lambda m: m[0])
    with open(os.path.join(kit, "markers.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "seconds", "type", "detail", "capcut"])
        for t, typ, det, hint in markers:
            w.writerow([mmss(t), f"{t:.2f}", typ, det, hint])

    baked = "ไม่มีเอฟเฟกต์ใด ๆ (โหมด --raw)" if raw else (
        f"ใส่ transition / motion / เสียงเอฟเฟกต์ (สไตล์ `{prep['style']['name']}`) ไว้ในวิดีโอแล้ว — "
        "ถ้าจะใส่เอฟเฟกต์เองทั้งหมดใน CapCut ให้ export ใหม่ด้วย `--raw`")
    fx_rows = [m for m in markers if m[1] not in ("jump cut",)] if raw else [m for m in markers if m[1] in ("card reveal",)]
    guide = [
        f"# CapCut kit — {cid}",
        "",
        f"ความยาว {prep['total']:.1f} วิ · {W}x{H} · {clip.get('hook', '')}",
        f"วิดีโอ `{cid}_video.mp4`: ตัดต่อ + ครอป + เสียงสะอาด (−14 LUFS) แล้ว, **ยังไม่มีตัวหนังสือ** · {baked}",
        "",
        "## ขั้นตอน",
        f"1. CapCut → New project → นำเข้า `{cid}_video.mp4` (สัดส่วน 9:16 อยู่แล้ว)",
        f"2. **ซับ**: Desktop → Text/Captions → Import captions → เลือก `{cid}.srt` "
        f"(อยากได้ซับเด้งทีละคำ ใช้ `{cid}_words.srt`) · Mobile → ใช้ Auto captions (ภาษาไทย) ได้เลย เสียงสะอาดแล้ว",
        "   แนะนำสไตล์: ฟอนต์หนา (Kanit ExtraBold อยู่ใน `assets/fonts`), ขอบดำหนา, คำสำคัญสีทอง/ชมพู, ตำแหน่ง ~2/3 ของจอ",
        "3. **Overlay**: Overlay → Add overlay → เลือก PNG ใน `overlays/` แล้วลากให้เต็มจอ (ไฟล์วางตำแหน่งไว้แล้ว)",
        "4. **เสียงเอฟเฟกต์**: " + ("อยู่ในวิดีโอแล้ว (ไฟล์แยกใน `sfx/` เผื่อต้องการปรับ)" if not raw else
                               "Audio → Extracted/Local → นำเข้าไฟล์ใน `sfx/` ตามเวลาใน `sfx.csv`"),
        "5. เพลง: เลือกจากคลังเพลงของ CapCut/TikTok (Commercial-safe ถ้าเป็นบัญชีธุรกิจ) เสียงเพลง ~10–15%",
        "6. Export: 1080p · 30 fps · bitrate แนะนำ (Recommended) → โพสต์",
        "",
        "## Overlay",
        "| ไฟล์ | เริ่ม | ระยะ |",
        "|---|---|---|",
        *[f"| overlays/{n} | {t} | {d} |" for n, t, d in made],
        "",
        "## จุดที่ต้องทำ" + (" (ทั้งหมด — โหมด raw)" if raw else " (จังหวะเปิดไพ่)"),
        "| เวลา | อะไร | ทำใน CapCut |",
        "|---|---|---|",
        *[f"| {mmss(t)} | {typ} {det} | {hint} |" for t, typ, det, hint in fx_rows],
        "",
        "ดูทุกจังหวะ (cut, transition, effect, sfx) ได้ใน `markers.csv`",
    ]
    with open(os.path.join(kit, "EDIT_GUIDE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(guide) + "\n")
    print(f"  ✓ CapCut kit: {kit} ({len(markers)} markers)")
    return kit


def run(slug: str, only: list[str] | None = None, raw: bool = False, draft: bool = False,
        zip_: bool = False) -> list[str]:
    project = Project(slug)
    meta = project.load_meta()
    cfg = load_config()
    plan = load_plan(project)
    clips = [c for c in plan["clips"] if not only or c["id"] in only]
    if not clips:
        raise SystemExit(f"no clips match {only}")
    kits = [export_clip(project, c, cfg, meta, raw, draft) for c in clips]
    if zip_:
        for k in kits:
            z = shutil.make_archive(k, "zip", root_dir=os.path.dirname(k), base_dir=os.path.basename(k))
            print(f"  ✓ {z}")
    return kits
