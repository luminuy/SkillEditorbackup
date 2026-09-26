"""Finishing: colour looks / LUTs, clean-up, encoder choice (incl. Apple VideoToolbox)."""
from __future__ import annotations

import os
import platform
from functools import lru_cache

from . import ff
from .config import ROOT

# Gentle, skin-safe grades. Each is one ffmpeg filter chain applied to the whole frame.
LOOKS = {
    "none": "",
    "clean": "eq=contrast=1.04:saturation=1.05:gamma=1.01",
    "warm": "colortemperature=temperature=5600:mix=0.35,eq=contrast=1.05:saturation=1.08",
    "mystic": ("colorbalance=rs=-0.02:gs=-0.01:bs=0.07:rm=0.02:gm=-0.02:bm=0.04:rh=0.04:gh=0.01:bh=-0.02,"
               "eq=contrast=1.07:saturation=1.1:gamma=0.98,vibrance=intensity=0.12"),
    "moody": "eq=contrast=1.12:saturation=0.9:brightness=-0.025,colorbalance=bs=0.05:bm=0.02:rh=0.02",
    "vibrant": "eq=contrast=1.06:saturation=1.12,vibrance=intensity=0.28",
}
LOOK_NOTES = {
    "clean": "แก้แสงสีเล็กน้อย เป็นธรรมชาติ — ใช้ได้ทุกคลิป",
    "warm": "อบอุ่น ผิวดูดี — คลิปพูดคุย ให้กำลังใจ",
    "mystic": "เงาม่วง/น้ำเงิน ไฮไลต์อุ่น — บรรยากาศดูดวงลึกลับ แต่ผิวคนยังเป็นธรรมชาติ",
    "moody": "คอนทราสต์สูง สีหม่น — ไพ่หนัก เรื่องจริงจัง",
    "vibrant": "สีสด — คลิปพลังบวก ข่าวดี",
}


def look_chain(clip: dict, cfg: dict, draft: bool = False) -> str:
    """Build the finishing chain for a clip: denoise -> look -> LUT -> sharpen (drafts skip denoise/sharpen)."""
    fin = dict(cfg.get("finish", {}))
    look = clip.get("look", fin.get("look", "none")) or "none"
    if look not in LOOKS:
        raise SystemExit(f"clip {clip.get('id')}: unknown look '{look}' (use {', '.join(LOOKS)})")
    parts = []
    if not draft and clip.get("denoise", fin.get("denoise", False)):
        parts.append("hqdn3d=1.5:1.5:6:6")
    if LOOKS[look]:
        # Bake the look into a 3D LUT once (Hald CLUT -> .cube): one table lookup per pixel instead of
        # several float filters — the same approach colourists use.
        parts.append(f"lut3d=file={ff.filter_path(look_lut(look))}:interp=tetrahedral")
    lut = clip.get("lut", fin.get("lut"))
    if lut:
        lpath = lut if os.path.isabs(lut) else os.path.join(ROOT, lut)
        if not os.path.exists(lpath):
            raise SystemExit(f"LUT not found: {lpath}")
        parts.append(f"lut3d=file={ff.filter_path(lpath)}:interp=tetrahedral")
    sharpen = float(clip.get("sharpen", fin.get("sharpen", 0.0)) or 0.0)
    if sharpen and not draft:
        parts.append(f"unsharp=5:5:{min(1.5, sharpen):.2f}:3:3:0")
    return ",".join(parts)


LUT_CACHE = os.path.join(ROOT, "assets", "luts", ".cache")


def look_lut(look: str, level: int = 6) -> str:
    """Return a cached .cube file equivalent to LOOKS[look] (built from a Hald CLUT through ffmpeg)."""
    import hashlib

    import numpy as np  # type: ignore
    from PIL import Image  # type: ignore

    key = hashlib.sha1(LOOKS[look].encode()).hexdigest()[:10]
    out = os.path.join(LUT_CACHE, f"{look}-{key}.cube")
    if os.path.exists(out):
        return out
    os.makedirs(LUT_CACHE, exist_ok=True)
    png = os.path.join(LUT_CACHE, f"{look}-{key}.png")
    ff.run(["-y", "-f", "lavfi", "-i", f"haldclutsrc=level={level}", "-vf", f"format=rgb24,{LOOKS[look]},format=rgb24",
            "-frames:v", "1", png])
    size = level * level
    img = np.asarray(Image.open(png).convert("RGB"), dtype=np.float64).reshape(-1, 3) / 255.0
    # Hald order is red fastest, then green, then blue — the same order .cube expects.
    with open(out, "w") as f:
        f.write(f"TITLE \"clipstudio {look}\"\nLUT_3D_SIZE {size}\n")
        f.write("\n".join(f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in img[: size ** 3]))
        f.write("\n")
    os.remove(png)
    return out


@lru_cache(maxsize=1)
def encoders() -> str:
    try:
        return ff.run(["-encoders"], quiet=False).stdout
    except Exception:  # noqa: BLE001
        return ""


def is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64")


def video_encoder_args(cfg: dict, fps: int, draft: bool) -> list[str]:
    """libx264 by default (best quality per bit); Apple VideoToolbox for fast drafts on a Mac,
    or for finals when edit.encoder = "videotoolbox"."""
    ed = cfg["edit"]
    enc = ed.get("encoder", "auto")
    has_vt = "h264_videotoolbox" in encoders()
    use_vt = has_vt and (enc == "videotoolbox" or (enc == "auto" and draft))
    if use_vt:
        return ["-c:v", "h264_videotoolbox", "-b:v", "6M" if draft else "16M", "-maxrate", "24M",
                "-profile:v", "high", "-allow_sw", "1", "-g", str(fps * 2)]
    if draft:
        return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"]
    if ed.get("quality") == "max":
        return ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-tune", "film", "-profile:v", "high",
                "-maxrate", "25M", "-bufsize", "50M", "-g", str(fps * 2), "-bf", "3"]
    return ["-c:v", "libx264", "-preset", ed["preset"], "-crf", str(ed["crf"]), "-profile:v", "high",
            "-g", str(fps * 2), "-bf", "2"]


def pick_fps(clip: dict, cfg: dict, meta: dict) -> int:
    """edit.fps: a number, or "source" = keep the camera's rate (24/25/30/50/60)."""
    want = clip.get("fps") or cfg["edit"].get("fps", 30)
    if want != "source":
        return int(want)
    src = float(meta.get("fps") or 30)
    for std in (24, 25, 30, 50, 60):
        if abs(src - std) < 1.2:
            return std
    return 60 if src > 45 else 30
