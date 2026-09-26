"""Source-time <-> output-time mapping for a clip made of several pieces."""
from __future__ import annotations


class Timeline:
    def __init__(self, pieces: list[dict]):
        """pieces: [{"start": src_a, "end": src_b, ...}] in playback order."""
        self.pieces = []
        t = 0.0
        for p in pieces:
            d = p["end"] - p["start"]
            if d <= 0:
                continue
            q = dict(p)
            q["out_start"] = t
            q["out_end"] = t + d
            self.pieces.append(q)
            t += d
        self.duration = t

    def map(self, t: float) -> float | None:
        """Exact mapping; None if t was cut out."""
        for p in self.pieces:
            if p["start"] <= t <= p["end"]:
                return p["out_start"] + (t - p["start"])
        return None

    def map_nearest(self, t: float) -> float:
        """Map t, snapping into the next kept piece if it falls in a gap."""
        m = self.map(t)
        if m is not None:
            return m
        for p in self.pieces:
            if t < p["start"]:
                return p["out_start"]
        return self.duration

    def map_words(self, words: list[dict]) -> list[dict]:
        """Map word timings; words cut in half are clipped, words fully cut are dropped."""
        out = []
        for w in words:
            for p in self.pieces:
                a, b = max(w["start"], p["start"]), min(w["end"], p["end"])
                mid = (w["start"] + w["end"]) / 2
                if b > a and (p["start"] <= mid <= p["end"] or (b - a) >= 0.5 * (w["end"] - w["start"])):
                    q = dict(w)
                    q["start"] = round(p["out_start"] + (a - p["start"]), 3)
                    q["end"] = round(p["out_start"] + (b - p["start"]), 3)
                    out.append(q)
                    break
        out.sort(key=lambda w: w["start"])
        return out


def subtract(intervals: list[dict], holes: list[dict], pad: float, min_piece: float) -> list[dict]:
    """Remove `holes` (silences) from `intervals`, keeping `pad` seconds of air at each cut."""
    out = []
    for iv in intervals:
        pieces = [(iv["start"], iv["end"])]
        for h in holes:
            hs, he = h["start"] + pad, (h["end"] if h["end"] is not None else iv["end"]) - pad
            if he - hs <= 0.05:
                continue
            nxt = []
            for a, b in pieces:
                if he <= a or hs >= b:
                    nxt.append((a, b))
                    continue
                if hs > a:
                    nxt.append((a, hs))
                if he < b:
                    nxt.append((he, b))
            pieces = nxt
        for a, b in pieces:
            if b - a >= min_piece:
                q = {k: v for k, v in iv.items() if k not in ("start", "end")}
                q.update(start=round(a, 3), end=round(b, 3))
                out.append(q)
    return out
