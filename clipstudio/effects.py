"""Effects & pacing: transitions, camera motion, overlay fx, sound effects.

A clip's "style" (calm | dynamic | viral | none) expands into automatic
events (transition at every segment boundary, reveal fx on every card
label, a pop on the hook, punch-ins on jump cuts…). Manual `fx` / `sfx`
items in the plan are added on top. Everything is resolved to *output*
time here, then render.py turns it into ffmpeg filters (xfade, zoompan,
rgbashift) and captions.py into ASS layers (flash, sparkle, glow).
"""
from __future__ import annotations

import random

# Friendly transition names -> ffmpeg xfade transition.
XFADE = {
    "crossfade": "fade", "fade": "fade", "dissolve": "dissolve", "dip": "fadeblack", "fadeblack": "fadeblack",
    "flashfade": "fadewhite", "fadewhite": "fadewhite", "zoom": "zoomin", "zoomin": "zoomin",
    "slide": "slideleft", "slideleft": "slideleft", "slideright": "slideright", "slideup": "slideup",
    "slidedown": "slidedown", "whip": "smoothleft", "smoothleft": "smoothleft", "smoothright": "smoothright",
    "smoothup": "smoothup", "blur": "hblur", "hblur": "hblur", "circle": "circleopen", "circleopen": "circleopen",
    "circleclose": "circleclose", "radial": "radial", "pixelize": "pixelize", "glitch": "pixelize",
    "wipe": "wipeleft", "wipeleft": "wipeleft", "wiperight": "wiperight", "squeeze": "squeezev",
    "wind": "hlwind", "cover": "coverleft", "reveal": "revealleft", "diagonal": "diagtl",
}
# Transitions that happen on a hard cut (no overlap): done with fx events instead of xfade.
CUT_TRANSITIONS = {"cut", "none", "punch", "flash", "shake", "glitchcut"}

STYLES: dict[str, dict] = {
    "none": {"motion": "none", "transition": "cut", "transition_duration": 0.0, "cut_punch": 0.0,
             "reveal_fx": [], "sfx": {}, "caption_anim": "none", "vignette": False, "emphasis_punch": False,
             "max_static": 0},
    "calm": {"motion": "push", "motion_amount": 0.05, "transition": "crossfade", "transition_duration": 0.45,
             "cut_punch": 0.0, "reveal_fx": ["glow", "sparkle"],
             "sfx": {"transition": "whoosh-soft", "reveal": "chime", "hook": None, "cta": None},
             "caption_anim": "fade", "vignette": True, "emphasis_punch": False, "max_static": 0},
    "dynamic": {"motion": "push", "motion_amount": 0.06, "transition": "zoom", "transition_duration": 0.3,
                "cut_punch": 0.08, "reveal_fx": ["flash", "sparkle", "punch"],
                "sfx": {"transition": "whoosh", "reveal": "sparkle", "hook": "pop", "cta": "pop"},
                "caption_anim": "pop", "vignette": True, "emphasis_punch": False, "max_static": 4.0},
    "viral": {"motion": "push", "motion_amount": 0.08, "transition": "whip", "transition_duration": 0.25,
              "cut_punch": 0.1, "reveal_fx": ["flash", "shake", "sparkle", "punch"],
              "sfx": {"transition": "whoosh", "reveal": "impact", "reveal2": "sparkle", "hook": "pop", "cta": "pop"},
              "caption_anim": "bounce", "vignette": True, "emphasis_punch": True, "max_static": 2.5},
}

SFX_GAIN = {"whoosh": 0.55, "whoosh-soft": 0.5, "chime": 0.7, "sparkle": 1.2, "pop": 0.45, "impact": 0.5,
            "riser": 0.6, "shimmer": 0.6, "click": 0.4}


def style_for(clip: dict, cfg: dict) -> dict:
    name = clip.get("style") or cfg.get("effects", {}).get("style", "dynamic")
    if name not in STYLES:
        raise SystemExit(f"clip {clip.get('id')}: unknown style '{name}' (use {', '.join(STYLES)})")
    st = dict(STYLES[name])
    st["name"] = name
    st.update({k: v for k, v in (cfg.get("effects", {}).get("overrides", {}) or {}).items()})
    return st


def parse_transition(spec, st: dict) -> tuple[str, float]:
    """-> (kind, duration). kind is an xfade name, or one of CUT_TRANSITIONS."""
    if spec is None:
        spec = st["transition"]
    dur = st.get("transition_duration", 0.3)
    if isinstance(spec, dict):
        dur = float(spec.get("duration", dur))
        spec = spec.get("type", "cut")
    spec = str(spec).lower()
    if spec in CUT_TRANSITIONS:
        return spec, 0.0
    if spec not in XFADE:
        raise SystemExit(f"unknown transition '{spec}' (use one of: cut, punch, flash, shake, {', '.join(sorted(XFADE))})")
    return XFADE[spec], max(0.1, min(1.0, dur))


def assign_transitions(pieces: list[dict], segments: list[dict], clip: dict, st: dict) -> None:
    """Mark the first piece of every segment after the first with its incoming transition.

    Sets piece["overlap"] (seconds, for xfade) and piece["trans"] (kind).
    """
    seg_starts = {}
    for i, s in enumerate(segments):
        seg_starts[(s["start"])] = i
    seen_first = False
    for p in pieces:
        seg_idx = p.get("_seg")
        p["overlap"], p["trans"] = 0.0, None
        if seg_idx is None:
            continue
        if p.get("_first_of_seg"):
            if seen_first:
                seg = segments[seg_idx]
                kind, d = parse_transition(seg.get("transition_in", clip.get("transition")), st)
                p["trans"] = kind
                p["overlap"] = d
            seen_first = True


def clamp_overlaps(pieces: list[dict]) -> None:
    for i, p in enumerate(pieces):
        if p.get("overlap"):
            prev = pieces[i - 1]
            lim = 0.45 * min(p["end"] - p["start"], prev["end"] - prev["start"])
            p["overlap"] = round(max(0.0, min(p["overlap"], lim)), 3)
            if p["overlap"] < 0.08:
                p["overlap"] = 0.0
                p["trans"] = "cut"


def build_events(clip: dict, st: dict, tl, labels_out: list[dict], total: float, speed: float,
                 words: list[dict], emphasis: list[str]) -> dict:
    """Resolve every effect to output time.

    Returns {"zoom": [...], "shake": [...], "glitch": [...], "ass": [...], "sfx": [...], "pieces_zoom": [...]}.
    """
    rnd = random.Random(clip.get("id", "x"))
    ev = {"zoom": [], "shake": [], "glitch": [], "ass": [], "sfx": [], "pieces_zoom": []}
    auto = clip.get("auto_fx", True)
    sfx_map = dict(st.get("sfx", {}))
    sfx_map.update(clip.get("sfx_map") or {})

    def add_sfx(name, t, vol=None):
        if name:
            ev["sfx"].append({"name": name, "t": max(0.0, t), "volume": vol if vol is not None else SFX_GAIN.get(name, 0.5)})

    def add_fx(kind, t, dur=None, **kw):
        t = max(0.0, min(total - 0.05, t))
        if kind == "punch":
            ev["zoom"].append({"t": t, "dur": dur or 0.45, "amount": kw.get("amount", 0.12), "shape": "kick"})
        elif kind == "zoom":
            ev["zoom"].append({"t": t, "dur": dur or 2.0, "amount": kw.get("amount", 0.15), "shape": "hold"})
        elif kind == "shake":
            ev["shake"].append({"t": t, "dur": dur or 0.4, "amount": kw.get("amount", 14)})
        elif kind == "glitch":
            ev["glitch"].append({"t": t, "dur": dur or 0.2})
        elif kind in ("flash", "sparkle", "glow", "flash-strong", "stars"):
            ev["ass"].append({"kind": kind, "t": t, "dur": dur, "seed": rnd.random(), **kw})
        else:
            raise SystemExit(f"unknown fx '{kind}' (punch, zoom, shake, glitch, flash, flash-strong, sparkle, glow, stars)")

    # --- transitions at segment boundaries ---------------------------------
    for p in tl.pieces:
        kind = p.get("trans")
        if not kind or kind in ("none",):
            continue
        tb = p["out_start"] / speed
        if kind == "cut":
            continue
        if kind == "punch":
            add_fx("punch", tb, amount=0.14)
        elif kind == "flash":
            add_fx("flash", tb - 0.05, 0.3)
        elif kind == "shake":
            add_fx("shake", tb, 0.35)
        elif kind == "glitchcut":
            add_fx("glitch", tb, 0.18)
        if auto:
            ov = p.get("overlap", 0) / speed
            add_sfx(sfx_map.get("transition"), tb - 0.2 + ov / 2)

    # --- jump-cut punch-ins (pacing) ----------------------------------------
    cp = float(clip.get("cut_punch", st.get("cut_punch", 0)))
    if cp:
        level = 0
        for i, p in enumerate(tl.pieces):
            if p.get("trans"):  # new segment: reset
                level = 0
            elif i:
                level = 1 - level
            ev["pieces_zoom"].append({"t0": p["out_start"] / speed, "t1": p["out_end"] / speed, "amount": cp * level})

    # --- hook / CTA ----------------------------------------------------------
    if auto and clip.get("hook"):
        add_sfx(sfx_map.get("hook"), 0.05)
    if auto and clip.get("_cta_start") is not None:
        add_sfx(sfx_map.get("cta"), clip["_cta_start"])

    # --- card reveals / labels ----------------------------------------------
    if auto:
        for lb in labels_out:
            t = lb["t"]
            for kind in st.get("reveal_fx", []):
                if kind == "sparkle":
                    add_fx("sparkle", t, 1.0, y=lb.get("y"))
                elif kind == "flash":
                    add_fx("flash", t - 0.04, 0.28)
                elif kind == "glow":
                    add_fx("glow", t, 1.4)
                else:
                    add_fx(kind, t)
            add_sfx(sfx_map.get("reveal"), t - 0.03)
            add_sfx(sfx_map.get("reveal2"), t + 0.05)

    # --- emphasis words -> small punch (viral) -------------------------------
    last = -99.0
    if auto and st.get("emphasis_punch") and emphasis:
        for w in words:
            if any(e in w["text"] for e in emphasis) and w["start"] - last > 2.5:
                add_fx("punch", w["start"], 0.35, amount=0.07)
                last = w["start"]

    # --- manual items (source time -> output time) ----------------------------
    for item in clip.get("fx", []):
        t = (tl.map_nearest(item["at"]) if "at" in item else float(item.get("out_at", 0))) / speed
        add_fx(item["type"], t, item.get("duration"), **{k: v for k, v in item.items()
                                                          if k in ("amount", "y", "x", "color")})
        if item.get("sfx"):
            add_sfx(item["sfx"], t, item.get("sfx_volume"))
    for item in clip.get("sfx", []):
        t = (tl.map_nearest(item["at"]) if "at" in item else float(item.get("out_at", 0))) / speed
        add_sfx(item["name"], t + float(item.get("offset", 0)), item.get("volume"))

    # --- keep something moving: never more than max_static seconds without a visual beat
    ms = float(st.get("max_static") or 0)
    if auto and ms:
        beats = sorted([0.0, total] + [z["t"] for z in ev["zoom"]] + [p["t0"] for p in ev["pieces_zoom"]]
                       + [a["t"] for a in ev["ass"]])
        for a, b in zip(beats, beats[1:]):
            if b - a > ms:
                n = int((b - a) // ms)
                for k in range(1, n + 1):
                    t = a + (b - a) * k / (n + 1)
                    near = [w["start"] for w in words if abs(w["start"] - t) < 0.8]
                    add_fx("punch", near[0] if near else t, 0.4, amount=0.06)

    ev["sfx"].sort(key=lambda s: s["t"])
    return ev


def zoompan_filter(ev: dict, st: dict, W: int, H: int, fps: int, total: float, oversample: int) -> str | None:
    """Single zoompan pass for push-in motion, punch-ins, holds and shakes (None if nothing moves)."""
    terms = []
    motion = st.get("motion", "none")
    amt = float(st.get("motion_amount", 0.05))
    if motion == "push":
        terms.append(f"{amt}*it/{max(total, 0.1):.3f}")
    elif motion == "pull":
        terms.append(f"{amt}*(1-it/{max(total, 0.1):.3f})")
    for pz in ev["pieces_zoom"]:
        if pz["amount"]:
            terms.append(f"{pz['amount']}*between(it,{pz['t0']:.3f},{pz['t1']:.3f})")
    for z in ev["zoom"]:
        t0, d, a = z["t"], z["dur"], z["amount"]
        if z["shape"] == "kick":  # jump in, ease back out
            terms.append(f"{a}*between(it,{t0:.3f},{t0 + d:.3f})*pow(1-(it-{t0:.3f})/{d:.3f},2)")
        else:  # ease in 0.2s, hold, ease out 0.2s
            terms.append(f"{a}*between(it,{t0:.3f},{t0 + d:.3f})*min(1,min((it-{t0:.3f})/0.2,({t0 + d:.3f}-it)/0.2))")
    shake_x, shake_y = [], []
    for s in ev["shake"]:
        t0, d, a = s["t"], s["dur"], s["amount"] * oversample
        env = f"between(it,{t0:.3f},{t0 + d:.3f})*(1-(it-{t0:.3f})/{d:.3f})"
        terms.append(f"0.05*{env}")
        shake_x.append(f"{a}*sin(it*71)*{env}")
        shake_y.append(f"{a}*cos(it*53)*{env}")
    if not terms:
        return None
    z = "1+" + "+".join(terms)
    x = "iw/2-iw/zoom/2" + ("+" + "+".join(shake_x) if shake_x else "")
    y = "ih/2-ih/zoom/2" + ("+" + "+".join(shake_y) if shake_y else "")
    pre = f"scale={W * oversample}:{H * oversample}:flags=bicubic," if oversample > 1 else ""
    return f"{pre}zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={fps}"


def glitch_filter(ev: dict) -> str | None:
    if not ev["glitch"]:
        return None
    win = "+".join(f"between(t,{g['t']:.3f},{g['t'] + g['dur']:.3f})" for g in ev["glitch"])
    return f"rgbashift=rh=10:bh=-10:gv=4:enable='{win}'"
