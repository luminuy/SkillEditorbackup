"""Text helpers: Thai word segmentation, width measurement, emoji stripping.

Thai has no spaces between words and libass only wraps on spaces, so every
line break in burned-in text is decided here, by measured pixel width, and
never inside a word.
"""
from __future__ import annotations

import os
import re
import unicodedata
from functools import lru_cache

from .config import FONTS_DIR

THAI_RE = re.compile(r"[฀-๿]")
# Thai characters that cannot start a word/token (vowels and marks that attach to the previous consonant).
THAI_NON_INITIAL = set("ะัาำิีึืฺุู็่้๊๋์ํๅ๎")
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0000200D\U000020E3]"
)


def has_thai(text: str) -> bool:
    return bool(THAI_RE.search(text or ""))


def strip_emoji(text: str) -> str:
    """libass renders emoji as monochrome boxes with our fonts; keep them for post captions only."""
    return re.sub(r"\s{2,}", " ", EMOJI_RE.sub("", text or "")).strip()


def ass_escape(text: str) -> str:
    return (text or "").replace("\\", "⧵").replace("{", "(").replace("}", ")").replace("\n", " ")


def font_file(family: str) -> str | None:
    """Map an ASS font family name to a bundled file (Kanit ExtraBold -> Kanit-ExtraBold.ttf)."""
    parts = family.split()
    candidates = ["-".join(parts) + ".ttf", "".join(parts) + ".ttf", parts[0] + "-Regular.ttf"]
    for c in candidates:
        p = os.path.join(FONTS_DIR, c)
        if os.path.exists(p):
            return p
    return None


class Measurer:
    """Pixel width of a string for a given font family/size (falls back to an estimate)."""

    def __init__(self, family: str, size: int):
        self.size = size
        self.font = None
        path = font_file(family)
        if path:
            try:
                from PIL import ImageFont  # type: ignore

                self.font = ImageFont.truetype(path, size)
            except Exception:
                self.font = None

    def width(self, text: str) -> float:
        if self.font is not None:
            try:
                return float(self.font.getlength(text))
            except Exception:
                pass
        # Estimate: combining marks have no advance; Thai glyphs ~0.55em, Latin ~0.58em (bold).
        n = sum(1 for ch in text if unicodedata.category(ch) not in ("Mn", "Me"))
        return n * self.size * 0.56


@lru_cache(maxsize=1)
def _thai_tokenizer():
    try:
        from pythainlp.tokenize import word_tokenize  # type: ignore

        return lambda s: word_tokenize(s, engine="newmm", keep_whitespace=True)
    except Exception:
        return None


def segment_words(text: str) -> list[str]:
    """Split text into display words. Thai via pythainlp (if installed), else spaces + heuristics."""
    text = text.strip()
    if not text:
        return []
    return _attach_trailing(_segment(text))


# Tokens that must never start a line: repetition mark, closing punctuation.
NO_LINE_START = ("ๆ", "ฯ", ")", "]", "}", ",", ".", "!", "?", ":", ";", "%", "”", "’", "…")


def _attach_trailing(words: list[str]) -> list[str]:
    out: list[str] = []
    for w in words:
        if out and w.strip() and (w.lstrip().startswith(NO_LINE_START) or out[-1].rstrip().endswith(("(", "[", "“", "‘"))):
            out[-1] = out[-1].rstrip() + w.strip() + (" " if w.endswith(" ") else "")
            continue
        out.append(w)
    return out


def _segment(text: str) -> list[str]:
    tok = _thai_tokenizer() if has_thai(text) else None
    if tok:
        out: list[str] = []
        for w in tok(text):
            if w.isspace():
                if out:
                    out[-1] = out[-1] + " "
                continue
            out.append(w)
        return [w for w in out if w.strip()]
    # No tokenizer: split on spaces; chop very long Thai runs into ~8-char pieces at safe boundaries.
    words: list[str] = []
    for chunk in text.split(" "):
        if not chunk:
            continue
        if has_thai(chunk) and len(chunk) > 10:
            words.extend(_chop_thai(chunk, 8))
            words[-1] += " "
        else:
            words.append(chunk + " ")
    if words:
        words[-1] = words[-1].rstrip()
    return words


def _chop_thai(s: str, target: int) -> list[str]:
    pieces, cur = [], ""
    for ch in s:
        if len(cur) >= target and ch not in THAI_NON_INITIAL and not unicodedata.category(ch).startswith("M"):
            pieces.append(cur)
            cur = ""
        cur += ch
    if cur:
        pieces.append(cur)
    return pieces


def retime_words(tokens: list[dict]) -> list[dict]:
    """Turn ASR tokens ({text,start,end}) into real display words with times.

    Whisper splits Thai into sub-word tokens. We rebuild the text, segment it
    into words, and give each word the time span of the characters it covers.
    """
    tokens = [t for t in tokens if t.get("text")]
    if not tokens:
        return []
    chars: list[tuple[str, float, float]] = []
    for t in tokens:
        txt = t["text"]
        n = max(1, len(txt))
        dur = max(0.0, t["end"] - t["start"])
        for i, ch in enumerate(txt):
            chars.append((ch, t["start"] + dur * i / n, t["start"] + dur * (i + 1) / n))
    full = "".join(c[0] for c in chars)
    lead = len(full) - len(full.lstrip())
    words = segment_words(full)
    out, pos = [], lead
    for w in words:
        core = w.strip()
        idx = full.find(core, pos)
        if idx < 0:
            continue
        span = chars[idx: idx + len(core)]
        out.append({"text": w, "start": round(span[0][1], 3), "end": round(span[-1][2], 3)})
        pos = idx + len(core)
    return out


def wrap_text(text: str, measurer: Measurer, max_px: float, max_lines: int = 3) -> list[str]:
    """Balanced word wrap by pixel width (used for hooks/labels/CTA).

    Greedy wrapping leaves orphans ("...กำลังจะ / ทักมา"); we find the
    narrowest width that still needs the same number of lines.
    """
    words = segment_words(strip_emoji(text))
    greedy = _greedy(words, measurer, max_px)
    if len(greedy) <= 1:
        return _cap_lines(greedy, max_lines)
    lo, hi = max_px * 0.4, max_px
    for _ in range(12):
        mid = (lo + hi) / 2
        if len(_greedy(words, measurer, mid)) <= len(greedy):
            hi = mid
        else:
            lo = mid
    return _cap_lines(_greedy(words, measurer, hi), max_lines)


def _cap_lines(lines: list[str], max_lines: int) -> list[str]:
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return lines


def _greedy(words: list[str], measurer: Measurer, max_px: float) -> list[str]:
    lines, cur = [], ""
    for w in words:
        cand = cur + w
        if cur and measurer.width(cand.strip()) > max_px:
            lines.append(cur.strip())
            cur = w
        else:
            cur = cand
    if cur.strip():
        lines.append(cur.strip())
    return lines


def visible_len(text: str) -> int:
    return sum(1 for ch in text if unicodedata.category(ch) not in ("Mn", "Me") and not ch.isspace())
