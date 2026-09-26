"""Find structure and clip candidates in a transcribed video.

Outputs analysis.json:
  silences   – silent stretches (used for jump-cuts)
  chapters   – detected sections (zodiac sign / pile / weekday / custom regex)
  candidates – scored windows that could stand alone as a short clip
  flags      – risky phrases (lottery numbers, guarantees…) to review
The story-producer agent reads this *plus* transcript.txt and makes the real
editorial choices; the scores here are only a starting point.
"""
from __future__ import annotations

import os
import re

from . import ff
from .config import DATA_DIR, Project, load_config, read_json, write_json
from .transcribe import mmss

THAI_DIGITS = {"หนึ่ง": 1, "แรก": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5, "หก": 6}

FALLBACK_SIGNS = [
    ("aries", "ราศีเมษ", ["เมษ"]), ("taurus", "ราศีพฤษภ", ["พฤษภ"]), ("gemini", "ราศีเมถุน", ["เมถุน", "มิถุน"]),
    ("cancer", "ราศีกรกฎ", ["กรกฎ"]), ("leo", "ราศีสิงห์", ["สิงห์", "สิงห"]), ("virgo", "ราศีกันย์", ["กันย์", "กันยา", "กันย"]),
    ("libra", "ราศีตุลย์", ["ตุลย์", "ตุล"]), ("scorpio", "ราศีพิจิก", ["พิจิก"]), ("sagittarius", "ราศีธนู", ["ธนู"]),
    ("capricorn", "ราศีมังกร", ["มังกร"]), ("aquarius", "ราศีกุมภ์", ["กุมภ์", "กุมภ"]), ("pisces", "ราศีมีน", ["มีน"]),
]

# Words that tend to make a moment worth clipping (tarot + general short-form).
HOOK_WORDS = {
    3: ["เนื้อคู่", "คนเก่า", "กลับมา", "รีเทิร์น", "ข่าวดี", "โชคลาภ", "เงินก้อน", "ปัง", "เซอร์ไพรส์", "สมหวัง",
        "ขอแต่งงาน", "งานใหม่", "เลื่อนตำแหน่ง", "ความลับ", "ข้อความ", "จักรวาล", "ไพ่ใบนี้", "ออกไพ่", "เปิดไพ่"],
    2: ["ความรัก", "คนโสด", "คนมีคู่", "การเงิน", "การงาน", "โชค", "ระวัง", "เตือน", "คนที่คิดถึง", "แอบชอบ",
        "ทัก", "ติดต่อ", "โอกาส", "เปลี่ยนแปลง", "ตัดสินใจ", "สำเร็จ", "เดินทาง", "สัญญาณ", "ยินดีด้วย"],
    1: ["คุณ", "เธอ", "ตัวเอง", "ช่วงนี้", "เร็วๆ นี้", "อาทิตย์นี้", "เดือนนี้", "ไพ่", "ทาโรต์", "ดวง"],
}
RISK_PATTERNS = [
    (r"หวย|เลขเด็ด|เลขนำโชค|งวดนี้|ลอตเตอรี่", "lottery/gambling"),
    (r"100\s*%|ร้อยเปอร์เซ็นต์|แน่นอน\s*100|การันตี|รับประกัน", "guaranteed-outcome claim"),
    (r"ไม่แชร์.*(โชคร้าย|ซวย)|ถ้าไม่กด.*(ซวย|โชคร้าย)", "chain-message threat"),
    (r"ตาย|อุบัติเหตุ|ป่วยหนัก|มะเร็ง", "health/death prediction"),
    (r"ลงทุน.*(หุ้น|คริปโต|crypto)|ซื้อหุ้น", "financial advice"),
]


def _load_zodiac():
    p = os.path.join(DATA_DIR, "zodiac.json")
    if os.path.exists(p):
        try:
            data = read_json(p)
            signs = [(s["id"], s["name_th"], sorted(set(s.get("aliases", []) + [s.get("short_th", "")]) - {""}, key=len,
                                                    reverse=True))
                     for s in data.get("signs", [])]
            days = [(d["id"], d["name_th"], d.get("aliases", [])) for d in data.get("weekdays", [])]
            if len(signs) == 12:
                return signs, days
        except Exception:
            pass
    return FALLBACK_SIGNS, []


def detect_chapters(segments: list[dict], custom: list[dict] | None = None, min_len: float = 20.0) -> list[dict]:
    signs, days = _load_zodiac()
    marks: list[tuple[float, str, str, str]] = []  # (time, kind, id, label)
    for seg in segments:
        txt = seg["text"]
        for sid, label, aliases in signs:
            for a in aliases:
                short = a.replace("ราศี", "").replace("ชาว", "")
                if re.search(rf"(ราศี|ชาว|ลัคนา)\s*{re.escape(short)}", txt):
                    marks.append((seg["start"], "zodiac", sid, label))
                    break
        for did, label, aliases in days:
            if any(a and a in txt for a in aliases):
                marks.append((seg["start"], "weekday", did, label))
        m = re.search(r"กอง\s*(?:ที่)?\s*(\d|หนึ่ง|แรก|สอง|สาม|สี่|ห้า|หก)", txt)
        if m:
            g = m.group(1)
            n = int(g) if g.isdigit() else THAI_DIGITS.get(g)
            if n:
                marks.append((seg["start"], "pile", f"pile-{n}", f"กอง {n}"))
        for c in custom or []:
            if re.search(c["pattern"], txt):
                marks.append((seg["start"], c.get("kind", "custom"), c.get("id", c["pattern"]), c.get("label", c["pattern"])))

    # Which kind dominates? Use it as the chapter axis.
    kinds: dict[str, set] = {}
    for _, k, i, _ in marks:
        kinds.setdefault(k, set()).add(i)
    if not kinds:
        return []
    axis = max(kinds, key=lambda k: len(kinds[k]))
    if len(kinds[axis]) < 2:
        return []
    seq = [(t, i, lab) for t, k, i, lab in marks if k == axis]
    # Collapse to the first mention of each new id in order; intro lists ("เมษ พฤษภ มิถุน…") are
    # removed later by the minimum-length rule.
    chapters: list[dict] = []
    for t, i, lab in seq:
        if chapters and chapters[-1]["id"] == i:
            continue
        chapters.append({"kind": axis, "id": i, "label": lab, "start": t})
    end_t = segments[-1]["end"] if segments else 0
    for idx, ch in enumerate(chapters):
        ch["end"] = chapters[idx + 1]["start"] if idx + 1 < len(chapters) else end_t
    kept = [c for c in chapters if c["end"] - c["start"] >= min_len]
    # Merge repeated ids (a sign mentioned again later) keeping the longest run.
    best: dict[str, dict] = {}
    for c in kept:
        if c["id"] not in best or (c["end"] - c["start"]) > (best[c["id"]]["end"] - best[c["id"]]["start"]):
            best[c["id"]] = c
    out = sorted(best.values(), key=lambda c: c["start"])
    for c in out:
        c["duration"] = round(c["end"] - c["start"], 2)
        c["start"], c["end"] = round(c["start"], 2), round(c["end"], 2)
    return out


def score_text(text: str) -> float:
    s = 0.0
    for w, words in HOOK_WORDS.items():
        s += w * sum(text.count(x) for x in words)
    s += 1.5 * text.count("?")
    return s


def candidates(segments: list[dict], min_len=20.0, max_len=58.0, top=12) -> list[dict]:
    """Sliding windows aligned to segment boundaries, scored by hook density."""
    out = []
    n = len(segments)
    for i in range(n):
        text, j = "", i
        while j < n and segments[j]["end"] - segments[i]["start"] <= max_len:
            text += segments[j]["text"] + " "
            dur = segments[j]["end"] - segments[i]["start"]
            if dur >= min_len:
                first = segments[i]["text"]
                s = score_text(text) / (dur ** 0.5) + 2.0 * score_text(first)
                out.append({"start": segments[i]["start"], "end": segments[j]["end"], "duration": round(dur, 2),
                            "score": round(s, 2), "first_line": first[:80], "seg_ids": [i, j]})
            j += 1
    out.sort(key=lambda c: -c["score"])
    picked: list[dict] = []
    for c in out:
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
        if len(picked) >= top:
            break
    return sorted(picked, key=lambda c: c["start"])


def risk_flags(segments: list[dict]) -> list[dict]:
    flags = []
    for seg in segments:
        for pat, why in RISK_PATTERNS:
            if re.search(pat, seg["text"]):
                flags.append({"t": seg["start"], "segment": seg["id"], "issue": why, "text": seg["text"][:90]})
    return flags


def run(slug: str) -> dict:
    project = Project(slug)
    meta = project.load_meta()
    cfg = load_config()
    src = project.source()
    ed = cfg["edit"]
    sil_path = project.path("silences.json")
    sil = ff.silences(src, ed["silence_db"], ed["min_silence"]) if meta.get("has_audio", True) else []
    for s in sil:
        if s["end"] is None:
            s["end"] = meta.get("duration")
    write_json(sil_path, sil)

    tpath = project.path("transcript.json")
    segs = read_json(tpath)["segments"] if os.path.exists(tpath) else []
    chapters = detect_chapters(segs, cfg.get("chapter_patterns"))
    cands = candidates(segs)
    flags = risk_flags(segs)
    speech = sum(s["end"] - s["start"] for s in segs)
    result = {
        "duration": meta.get("duration"),
        "speech_seconds": round(speech, 1),
        "silence_seconds": round(sum((s["end"] or 0) - s["start"] for s in sil), 1),
        "chapters": chapters, "candidates": cands, "flags": flags,
    }
    write_json(project.path("analysis.json"), result)

    lines = [f"# Analysis: {slug}", f"duration {mmss(meta.get('duration', 0))}, speech {speech:.0f}s, "
             f"silences {len(sil)}", "", "## Chapters"]
    lines += [f"- {c['label']} ({c['kind']}) {mmss(c['start'])}–{mmss(c['end'])} ({c['duration']:.0f}s)"
              for c in chapters] or ["- none detected"]
    lines += ["", "## Top candidates (heuristic)"]
    lines += [f"- {mmss(c['start'])}–{mmss(c['end'])} ({c['duration']:.0f}s) score {c['score']}: {c['first_line']}"
              for c in sorted(cands, key=lambda c: -c["score"])]
    lines += ["", "## Risk flags"] + ([f"- {mmss(f['t'])} [{f['issue']}] {f['text']}" for f in flags] or ["- none"])
    with open(project.path("analysis.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return result
