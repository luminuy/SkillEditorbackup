"""Build one .ass subtitle file holding every burned-in layer of a clip:
captions, hook title, labels (card reveals, pile/zodiac badges), CTA,
watermark, disclaimer and progress bar. libass renders it in one pass.
"""
from __future__ import annotations

from . import cards
from .config import hex_to_ass
from .textutil import Measurer, ass_escape, strip_emoji, wrap_text

SENTENCE_END = ("?", "!", ".", "ค่ะ ", "ครับ ", "นะคะ ", "นะ ")


def ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


class AssBuilder:
    def __init__(self, width: int, height: int, cfg: dict):
        self.W, self.H = width, height
        if width > height:  # landscape canvas: lower-third captions, hook in the top band
            import copy as _copy

            cfg = _copy.deepcopy(cfg)
            ls = cfg.get("landscape", {})
            cfg["captions"]["y"] = ls.get("captions_y", 0.86)
            cfg["captions"]["max_width"] = ls.get("captions_max_width", 0.7)
            cfg["hook"]["y"] = ls.get("hook_y", 0.05)
            cfg["labels"]["y"] = ls.get("labels_y", 0.17)
        self.cfg = cfg
        self.cta_y = cfg.get("landscape", {}).get("cta_y", 0.5) if width > height else 0.44
        self.k = min(width, height) / 1080.0
        self.events: list[str] = []
        b, f = cfg["brand"], cfg["fonts"]
        cap = cfg["captions"]
        k = self.k

        def style(name, font, size, primary, secondary, outline_c, back, bold, border_style, outline, shadow,
                  align=5, spacing=0):
            return (f"Style: {name},{font},{int(size)},{primary},{secondary},{outline_c},{back},{bold},0,0,0,100,100,"
                    f"{spacing},0,{border_style},{outline},{shadow},{align},20,20,20,1")

        cap_primary, cap_secondary = hex_to_ass(b["text"]), hex_to_ass(b["accent"])
        if cap.get("style") == "karaoke":  # karaoke sweeps from Secondary to Primary
            cap_primary, cap_secondary = hex_to_ass(b["accent"]), hex_to_ass(b["text"])
        self.styles = [
            style("Caption", f["caption"], cap["size"] * k, cap_primary, cap_secondary, hex_to_ass(b["outline"]),
                  hex_to_ass("#000000", 0.45), 0, 1, round(cap["outline"] * k, 1), round(cap["shadow"] * k, 1)),
            style("Hook", f["title"], cfg["hook"]["size"] * k, hex_to_ass(b["hook_text"]), hex_to_ass(b["accent"]),
                  hex_to_ass(b["hook_box"], 0.08), hex_to_ass("#000000", 0.6), 0, 3, round(18 * k), round(4 * k), 8),
            style("Title", f["title"], cfg["hook"]["size"] * k, hex_to_ass(b["text"]), hex_to_ass(b["accent"]),
                  hex_to_ass(b["outline"]), hex_to_ass("#000000", 0.5), 0, 1, round(8 * k), round(6 * k), 8),
            style("Label", f["title"], cfg["labels"]["size"] * k, hex_to_ass(b["primary"]), hex_to_ass(b["text"]),
                  hex_to_ass(b["accent"]), hex_to_ass("#000000", 0.6), 0, 3, round(12 * k), round(3 * k), 8),
            style("CTA", f["title"], 66 * k, hex_to_ass(b["text"]), hex_to_ass(b["accent"]),
                  hex_to_ass(b["primary"], 0.1), hex_to_ass("#000000", 0.6), 0, 3, round(20 * k), round(4 * k), 5),
            style("Mark", f["body"], cfg["watermark"]["size"] * k, hex_to_ass(b["text"], 1 - cfg["watermark"]["opacity"]),
                  hex_to_ass(b["text"]), hex_to_ass("#000000", 0.6), hex_to_ass("#000000", 1), 0, 1, round(2 * k, 1), 0, 7),
            style("Small", f["body"], 30 * k, hex_to_ass(b["text"], 0.15), hex_to_ass(b["text"]),
                  hex_to_ass("#000000", 0.3), hex_to_ass("#000000", 1), 0, 1, round(3 * k, 1), 0, 2),
            style("Bar", f["body"], 20, hex_to_ass(b["accent"]), hex_to_ass(b["accent"]), hex_to_ass("#000000", 1),
                  hex_to_ass("#000000", 1), 0, 1, 0, 0, 7),
        ]

    # ---- low level -------------------------------------------------------
    def add(self, start: float, end: float, style: str, text: str, layer: int = 0):
        if end - start < 0.03:
            return
        self.events.append(f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}")

    def render(self) -> str:
        head = [
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {self.W}", f"PlayResY: {self.H}", "WrapStyle: 2",
            "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding",
            *self.styles, "", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
        return "\n".join(head + self.events) + "\n"

    # ---- layers ----------------------------------------------------------
    def captions(self, words: list[dict], override: dict | None = None):
        cap = dict(self.cfg["captions"])
        cap.update(override or {})
        if not cap.get("enabled", True) or not words:
            return
        style = cap.get("style", "highlight")
        size = cap["size"] * self.k * (1.25 if style == "pop" else 1.0)
        meas = Measurer(self.cfg["fonts"]["caption"], int(size))
        max_px = self.W * cap["max_width"]
        n_lines = 1 if style == "pop" else max(1, int(cap.get("lines", 1)))
        x, y = self.W / 2, self.H * cap["y"]
        accent = hex_to_ass(self.cfg["brand"]["accent"])

        if style == "pop":
            for i, w in enumerate(words):
                end = words[i + 1]["start"] if i + 1 < len(words) and words[i + 1]["start"] - w["end"] < 0.4 else w["end"] + 0.15
                txt = ass_escape(strip_emoji(w["text"]).strip())
                if txt:
                    self.add(w["start"], end, "Caption",
                             f"{{\\an5\\pos({x:.0f},{y:.0f})\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)}}{txt}", 2)
            return

        for card in self._cards(words, meas, max_px, n_lines, cap["max_card_seconds"]):
            lines = card["lines"]  # list of lists of words
            flat = [w for ln in lines for w in ln]
            c_start, c_end = card["start"], card["end"]
            pos = f"\\an5\\pos({x:.0f},{y:.0f})"
            if style == "plain":
                txt = "\\N".join(ass_escape("".join(w["text"] for w in ln).strip()) for ln in lines)
                self.add(c_start, c_end, "Caption", f"{{{pos}}}{txt}", 2)
            elif style == "karaoke":
                parts = []
                for i, w in enumerate(flat):
                    nxt = flat[i + 1]["start"] if i + 1 < len(flat) else c_end
                    dur_cs = max(1, int(round((nxt - (w["start"] if i else c_start)) * 100)))
                    sep = "\\N" if i and any(w is ln[0] for ln in lines[1:]) else ""
                    parts.append(f"{sep}{{\\kf{dur_cs}}}{ass_escape(w['text'])}")
                self.add(c_start, c_end, "Caption", f"{{{pos}}}" + "".join(parts).strip(), 2)
            else:  # highlight: whole card visible, current word in accent colour
                for i, w in enumerate(flat):
                    a = c_start if i == 0 else w["start"]
                    b = flat[i + 1]["start"] if i + 1 < len(flat) else c_end
                    out_lines = []
                    for ln in lines:
                        seg = ""
                        for v in ln:
                            t = ass_escape(v["text"])
                            seg += f"{{\\c{accent}}}{t}{{\\r}}" if v is w else t
                        out_lines.append(seg.strip())
                    self.add(a, b, "Caption", f"{{{pos}}}" + "\\N".join(out_lines), 2)

    def _cards(self, words, meas, max_px, n_lines, max_secs):
        cards_out, cur_lines, cur = [], [], []

        def flush():
            nonlocal cur_lines, cur
            if cur:
                cur_lines.append(cur)
            if cur_lines:
                flat = [w for ln in cur_lines for w in ln]
                cards_out.append({"lines": cur_lines, "start": flat[0]["start"], "end": flat[-1]["end"]})
            cur_lines, cur = [], []

        for w in words:
            if not w["text"].strip():
                continue
            if cur or cur_lines:
                flat_prev = (cur_lines[-1] if cur_lines and not cur else cur)[-1]
                first = (cur_lines[0] if cur_lines else cur)[0]
                gap = w["start"] - flat_prev["end"]
                if (gap > 0.65 or w["end"] - first["start"] > max_secs or w.get("seg") != flat_prev.get("seg")
                        or flat_prev["text"].endswith(SENTENCE_END)):
                    flush()
            line_txt = "".join(v["text"] for v in cur) + w["text"]
            if cur and meas.width(line_txt.strip()) > max_px:
                cur_lines.append(cur)
                cur = []
                if len(cur_lines) >= n_lines:
                    flush()
            cur.append(w)
        flush()
        # Close small gaps so captions don't flicker; hold briefly after the last word.
        for i, c in enumerate(cards_out):
            nxt = cards_out[i + 1]["start"] if i + 1 < len(cards_out) else None
            if nxt is not None and nxt - c["end"] < 0.35:
                c["end"] = nxt
            else:
                c["end"] = c["end"] + 0.2 if nxt is None else min(c["end"] + 0.2, nxt)
        return cards_out

    def hook(self, text: str, duration: float, seconds: float | None = None):
        hk = self.cfg["hook"]
        if not text or not hk.get("enabled", True):
            return
        meas = Measurer(self.cfg["fonts"]["title"], int(hk["size"] * self.k))
        lines = wrap_text(text, meas, self.W * hk["max_width"], 3)
        body = "\\N".join(ass_escape(l) for l in lines)
        end = duration if seconds in (None, 0, "full") else min(duration, float(seconds))
        self.add(0, end, "Hook",
                 f"{{\\an8\\pos({self.W / 2:.0f},{self.H * hk['y']:.0f})\\fad(120,150)\\fscx85\\fscy85"
                 f"\\t(0,180,\\fscx100\\fscy100)}}{body}", 3)

    def label(self, text: str, start: float, end: float):
        lb = self.cfg["labels"]
        meas = Measurer(self.cfg["fonts"]["title"], int(lb["size"] * self.k))
        lines = wrap_text(text, meas, self.W * 0.84, 2)
        body = "\\N".join(ass_escape(l) for l in lines)
        self.add(start, end, "Label",
                 f"{{\\an8\\pos({self.W / 2:.0f},{self.H * lb['y']:.0f})\\fad(100,120)\\fscx70\\fscy70"
                 f"\\t(0,160,\\fscx100\\fscy100)}}{body}", 4)

    def cta(self, text: str, duration: float, seconds: float):
        if not text:
            return
        meas = Measurer(self.cfg["fonts"]["title"], int(66 * self.k))
        lines = wrap_text(text, meas, self.W * 0.8, 3)
        body = "\\N".join(ass_escape(l) for l in lines)
        start = max(0.0, duration - seconds)
        self.add(start, duration, "CTA",
                 f"{{\\an5\\pos({self.W / 2:.0f},{self.H * self.cta_y:.0f})\\fad(150,0)\\fscx60\\fscy60"
                 f"\\t(0,200,\\fscx100\\fscy100)}}{body}", 5)

    def watermark(self, text: str, duration: float):
        wm = self.cfg["watermark"]
        if not wm.get("enabled") or not text:
            return
        m = 0.06 * self.W
        pos = {"top-left": (7, m, self.H * 0.105), "top-right": (9, self.W - m, self.H * 0.105),
               "bottom-left": (1, m, self.H * 0.76)}.get(wm.get("position", "top-left"), (7, m, self.H * 0.105))
        self.add(0, duration, "Mark", f"{{\\an{pos[0]}\\pos({pos[1]:.0f},{pos[2]:.0f})}}{ass_escape(text)}", 1)

    def disclaimer(self, text: str, seconds: float):
        if text:
            self.add(0, seconds, "Small", f"{{\\an2\\pos({self.W / 2:.0f},{self.H * 0.765:.0f})\\fad(0,200)}}"
                                          f"{ass_escape(strip_emoji(text))}", 1)

    def progress_bar(self, duration: float):
        pb = self.cfg["progress_bar"]
        if not pb.get("enabled"):
            return
        h = max(4, int(pb["height"] * self.k))
        y0 = 0 if pb.get("position", "top") == "top" else self.H - h
        shape = f"m 0 0 l {self.W} 0 {self.W} {h} 0 {h}"
        dur_ms = int(duration * 1000)
        self.add(0, duration, "Bar",
                 f"{{\\an7\\pos(0,{y0})\\p1\\clip(0,{y0},1,{y0 + h})\\t(0,{dur_ms},\\clip(0,{y0},{self.W},{y0 + h}))}}"
                 f"{shape}{{\\p0}}", 6)


def resolve_label(item: dict) -> str:
    if item.get("text"):
        return strip_emoji(item["text"])
    if item.get("card"):
        return cards.label_text(item["card"], bool(item.get("reversed")))
    return ""
