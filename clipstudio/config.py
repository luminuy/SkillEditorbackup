"""Channel brand kit, platform specs and project paths."""
from __future__ import annotations

import copy
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(ROOT, "assets", "fonts")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROJECTS_DIR = os.environ.get("CLIPSTUDIO_PROJECTS", os.path.join(ROOT, "projects"))
CONFIG_PATH = os.environ.get("CLIPSTUDIO_CONFIG", os.path.join(ROOT, "channel.config.json"))

# Output canvases. Keys are what a plan's "format" field accepts.
FORMATS = {
    "vertical": (1080, 1920),    # TikTok, Reels, Shorts, Facebook Reels
    "portrait": (1080, 1350),    # Instagram / Facebook feed 4:5
    "square": (1080, 1080),
    "horizontal": (1920, 1080),  # YouTube long-form, Facebook feed video
}

# Platform delivery specs used by QA and the review sheet. Durations are the
# *recommended* windows for reach, plus the hard upload cap where known.
PLATFORMS = {
    "tiktok":   {"label": "TikTok",           "format": "vertical",   "max_seconds": 600, "sweet_spot": [20, 60],
                 "caption_limit": 4000, "hashtags": [3, 6]},
    "reels":    {"label": "Instagram Reels",  "format": "vertical",   "max_seconds": 180, "sweet_spot": [15, 60],
                 "caption_limit": 2200, "hashtags": [3, 5]},
    "shorts":   {"label": "YouTube Shorts",   "format": "vertical",   "max_seconds": 180, "sweet_spot": [20, 58],
                 "title_limit": 100, "caption_limit": 5000, "hashtags": [3, 5]},
    "facebook": {"label": "Facebook Reels",   "format": "vertical",   "max_seconds": 90,  "sweet_spot": [15, 60],
                 "caption_limit": 5000, "hashtags": [2, 4]},
    "youtube":  {"label": "YouTube (long)",   "format": "horizontal", "max_seconds": 43200, "sweet_spot": [480, 1200],
                 "title_limit": 100, "caption_limit": 5000, "hashtags": [2, 3]},
}

DEFAULTS: dict = {
    "channel_name": "My Channel",
    "handle": "@mychannel",
    "language": "th",
    "niche": "tarot",
    "brand": {
        "primary": "#2B1055",     # deep mystic purple (boxes, progress bar bg)
        "accent": "#F5C542",      # gold (highlight word, progress bar)
        "text": "#FFFFFF",
        "outline": "#12051F",
        "hook_text": "#FFFFFF",
        "hook_box": "#2B1055",
        "emphasis": "#FF9EE5",    # keyword colour in captions (ความรัก, เนื้อคู่ …)
    },
    "fonts": {"caption": "Kanit ExtraBold", "title": "Kanit ExtraBold", "body": "Kanit"},
    "captions": {
        "enabled": True,
        "style": "highlight",     # highlight | karaoke | pop | plain
        "size": 80,               # px at 1080 wide; scaled for other widths
        "y": 0.64,                # vertical centre of caption block (fraction of height)
        "max_width": 0.82,        # fraction of frame width per line
        "lines": 1,               # 1 or 2 lines per caption card
        "outline": 6,
        "shadow": 2,
        "max_card_seconds": 3.2,
    },
    "hook": {"enabled": True, "seconds": None, "y": 0.16, "size": 80, "max_width": 0.86},
    "labels": {"y": 0.78, "size": 54},
    # Positions used instead when the canvas is wider than tall (16:9 YouTube / FB feed).
    "landscape": {"captions_y": 0.86, "captions_max_width": 0.7, "hook_y": 0.05, "labels_y": 0.17, "cta_y": 0.5},
    "watermark": {"enabled": True, "text": None, "opacity": 0.55, "size": 34, "position": "top-left"},
    "progress_bar": {"enabled": True, "height": 10},
    "cta": {"enabled": True, "text": "กดติดตามไว้ แล้วมาดูดวงด้วยกันนะคะ", "seconds": 2.5},
    # CTA used automatically when a clip's chapter kind matches (set by the producer via clip["kind"])
    "cta_by_kind": {},
    "disclaimer": {"burn_in": False, "text": "ดูดวงเพื่อเป็นแนวทางและความบันเทิง โปรดใช้วิจารณญาณ", "seconds": 3.0},
    "audio": {"target_lufs": -14.0, "true_peak": -1.5, "voice_enhance": True, "music": None,
              "music_volume": 0.12, "duck": True, "sfx": True, "sfx_volume": 1.0},
    # Pacing & effects. style: none | calm | dynamic | viral (see clipstudio/effects.py STYLES)
    "effects": {"style": "dynamic", "motion_oversample": 2, "emphasis_words": [], "overrides": {}},
    # fps: number or "source" · quality: standard | max · encoder: auto (x264; VideoToolbox drafts on Mac) | x264 | videotoolbox
    "edit": {"remove_silence": True, "silence_db": -35.0, "min_silence": 0.45, "pad": 0.12,
             "min_piece": 0.25, "fps": 30, "crf": 19, "preset": "medium", "fade_out": 0.35,
             "quality": "standard", "encoder": "auto", "remove_fillers": False,
             "fillers": ["เอ่อ", "เออ", "อ่า", "อ้า", "อืม", "อืมม", "เอ้อ", "um", "uh", "umm", "erm", "hmm"]},
    # look: none | clean | warm | mystic | moody | vibrant ; lut: path to .cube ; sharpen 0–1.5 ; denoise bool
    "finish": {"look": "none", "lut": None, "sharpen": 0.0, "denoise": False},
    "platforms": ["tiktok", "reels", "shorts", "facebook"],
    # slots in PRIORITY order (best first); plan order = clip priority; per_day clips per day
    "posting": {"timezone": "Asia/Bangkok", "slots": ["19:30", "12:00", "21:30", "07:30"], "per_day": 2},
}


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path: str | None = None) -> dict:
    path = path or CONFIG_PATH
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        preset = user.get("preset")
        if preset:
            ppath = os.path.join(ROOT, "presets", f"{preset}.json")
            if os.path.exists(ppath):
                with open(ppath, encoding="utf-8") as pf:
                    cfg = deep_merge(cfg, json.load(pf))
        cfg = deep_merge(cfg, user)
    if not cfg["watermark"].get("text"):
        cfg["watermark"]["text"] = cfg.get("handle")
    return cfg


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", os.path.splitext(os.path.basename(name))[0].strip().lower(), flags=re.UNICODE)
    return re.sub(r"-{2,}", "-", s).strip("-") or "project"


class Project:
    """Filesystem layout of one source video's working folder."""

    def __init__(self, slug: str):
        self.slug = slug
        self.dir = os.path.join(PROJECTS_DIR, slug)

    def path(self, *parts: str) -> str:
        return os.path.join(self.dir, *parts)

    @property
    def meta_path(self):
        return self.path("project.json")

    def exists(self) -> bool:
        return os.path.exists(self.meta_path)

    def load_meta(self) -> dict:
        if not self.exists():
            raise SystemExit(f"Project '{self.slug}' not found. Run: python3 -m clipstudio init <video>")
        return read_json(self.meta_path)

    def save_meta(self, meta: dict):
        write_json(self.meta_path, meta)

    def source(self) -> str:
        src = self.load_meta()["source"]
        return src if os.path.isabs(src) else os.path.join(ROOT, src)

    def ensure(self, *sub: str) -> str:
        p = self.path(*sub)
        os.makedirs(p, exist_ok=True)
        return p


def read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def hex_to_ass(color: str, alpha: float = 0.0) -> str:
    """#RRGGBB (+ transparency 0..1) -> ASS &HAABBGGRR."""
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = c[0:2], c[2:4], c[4:6]
    a = max(0, min(255, int(round(alpha * 255))))
    return f"&H{a:02X}{b}{g}{r}".upper()
