"""Fast unit tests for the pure-Python parts of clipstudio (no video needed).

Run:  python3 -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipstudio import cards  # noqa: E402
from clipstudio.analyze import detect_chapters, risk_flags  # noqa: E402
from clipstudio.captions import AssBuilder, ts  # noqa: E402
from clipstudio.config import DEFAULTS, deep_merge, hex_to_ass  # noqa: E402
from clipstudio.textutil import Measurer, retime_words, segment_words, strip_emoji, wrap_text  # noqa: E402
from clipstudio.timeline import Timeline, subtract  # noqa: E402
from clipstudio.transcribe import parse_subtitles, proportional_words, resync  # noqa: E402


class TimelineTests(unittest.TestCase):
    def test_subtract_keeps_padding(self):
        out = subtract([{"start": 0, "end": 10, "zoom": 1.2}], [{"start": 4, "end": 6}], pad=0.1, min_piece=0.25)
        self.assertEqual([(p["start"], p["end"]) for p in out], [(0, 4.1), (5.9, 10)])
        self.assertTrue(all(p["zoom"] == 1.2 for p in out))

    def test_subtract_drops_tiny_pieces(self):
        out = subtract([{"start": 0, "end": 5}], [{"start": 0.1, "end": 4.95}], pad=0.0, min_piece=0.25)
        self.assertEqual(out, [])

    def test_map_and_words(self):
        tl = Timeline([{"start": 10, "end": 12}, {"start": 20, "end": 23}])
        self.assertAlmostEqual(tl.duration, 5)
        self.assertAlmostEqual(tl.map(21), 3)
        self.assertIsNone(tl.map(15))
        self.assertAlmostEqual(tl.map_nearest(15), 2)
        words = tl.map_words([{"text": "a", "start": 10.5, "end": 11}, {"text": "cut", "start": 14, "end": 15},
                              {"text": "b", "start": 20.2, "end": 20.6}])
        self.assertEqual([w["text"] for w in words], ["a", "b"])
        self.assertAlmostEqual(words[1]["start"], 2.2)


class ThaiTextTests(unittest.TestCase):
    def test_repetition_mark_never_starts_a_word(self):
        words = segment_words("ยาวมากๆ สามบรรทัด (จริงๆ) นะ!")
        self.assertFalse(any(w.strip().startswith(("ๆ", ")", "!")) for w in words))
        self.assertEqual("".join(words).replace(" ", ""), "ยาวมากๆสามบรรทัด(จริงๆ)นะ!")

    def test_balanced_wrap(self):
        m = Measurer("Kanit ExtraBold", 80)
        lines = wrap_text("ราศีเมษ คนที่คิดถึงกำลังจะทักมา", m, 1080 * 0.86)
        self.assertEqual(len(lines), 2)
        w = [m.width(line) for line in lines]
        self.assertLess(max(w) / min(w), 1.6, lines)

    def test_retime_merges_subword_tokens(self):
        toks = [{"text": "ราศี", "start": 0.0, "end": 0.4}, {"text": "เม", "start": 0.4, "end": 0.6},
                {"text": "ษ", "start": 0.6, "end": 0.7}, {"text": "ช่วงนี้", "start": 0.8, "end": 1.2}]
        words = retime_words(toks)
        self.assertEqual("".join(w["text"] for w in words), "ราศีเมษช่วงนี้")
        self.assertAlmostEqual(words[-1]["end"], 1.2)

    def test_strip_emoji(self):
        self.assertEqual(strip_emoji("ราศีเมษ 💌✨ ปัง"), "ราศีเมษ ปัง")


class TranscriptTests(unittest.TestCase):
    def test_parse_srt_and_vtt(self):
        with tempfile.NamedTemporaryFile("w", suffix=".vtt", delete=False, encoding="utf-8") as f:
            f.write("WEBVTT\n\n00:01.000 --> 00:03.500\n<b>สวัสดี</b>ค่ะ\n\n1\n00:00:04,000 --> 00:00:06,000\nline two\n")
        segs = parse_subtitles(f.name)
        os.unlink(f.name)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0]["text"], "สวัสดีค่ะ")
        self.assertAlmostEqual(segs[1]["start"], 4.0)

    def test_resync_after_edit(self):
        tr = {"segments": [{"id": 0, "start": 0, "end": 2, "text": "ไพ่ The Lovers",
                            "words": proportional_words("ไพ้ THE LOVE WORK", 0, 2)}]}
        self.assertEqual(resync(tr), 1)
        self.assertIn("Lovers", "".join(w["text"] for w in tr["segments"][0]["words"]))
        self.assertAlmostEqual(tr["segments"][0]["words"][-1]["end"], 2)


class AnalyzeTests(unittest.TestCase):
    def _segs(self, texts, step=30):
        return [{"id": i, "start": i * step, "end": i * step + step - 1, "text": t} for i, t in enumerate(texts)]

    def test_zodiac_chapters(self):
        segs = self._segs(["สวัสดีค่ะ", "มาดูราศีเมษกัน", "ความรักดีมาก", "ต่อไปชาวราศีพฤษภ", "การเงินปัง", "จบแล้วค่ะ"])
        ch = detect_chapters(segs)
        self.assertEqual([c["id"] for c in ch], ["aries", "taurus"])

    def test_month_name_is_not_a_sign(self):
        segs = self._segs(["เดือนมีนาคมนี้", "ตุลาคมจะดี", "มิถุนายนเดินทาง"])
        self.assertEqual(detect_chapters(segs), [])

    def test_piles(self):
        segs = self._segs(["เลือกกองกันค่ะ", "กองที่ 1 ความรัก", "ยังอยู่กองหนึ่ง", "กองที่สอง", "ต่อ", "กอง 3"])
        self.assertEqual([c["id"] for c in detect_chapters(segs)], ["pile-1", "pile-2", "pile-3"])

    def test_risk_flags(self):
        flags = risk_flags(self._segs(["เลขเด็ดงวดนี้", "รับประกันสมหวัง 100%", "ปกติ"]))
        self.assertEqual({f["issue"] for f in flags}, {"lottery/gambling", "guaranteed-outcome claim"})


class OverlayTests(unittest.TestCase):
    def test_ass_has_layers(self):
        cfg = deep_merge(DEFAULTS, {"watermark": {"text": "@me"}})
        ab = AssBuilder(1080, 1920, cfg)
        words = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.35, "seg": 0}
                 for i, t in enumerate(["ราศี", "เมษ ", "ช่วงนี้", "ความรัก", "ดีมาก"])]
        ab.captions(words)
        ab.hook("ราศีเมษ มีข่าวดี", 5)
        ab.label(cards.label_text("the-sun"), 1, 3)
        ab.cta("กดติดตาม", 5, 2)
        ab.watermark("@me", 5)
        ab.progress_bar(5)
        out = ab.render()
        self.assertIn("PlayResX: 1080", out)
        for style in ("Caption", "Hook", "Label", "CTA", "Mark", "Bar"):
            self.assertIn(f",{style},", out)
        self.assertEqual(out.count(",Caption,"), 5)  # highlight: one event per word

    def test_colors_and_time(self):
        self.assertEqual(hex_to_ass("#F5C542"), "&H0042C5F5")
        self.assertEqual(ts(3723.456), "1:02:03.46")


class CardDataTests(unittest.TestCase):
    def test_78_cards(self):
        all_c = cards.all_cards()
        self.assertEqual(len(all_c), 78)
        self.assertEqual(len({c["id"] for c in all_c}), 78)
        self.assertIsNotNone(cards.get("the-tower"))
        self.assertTrue(cards.search("ทาวเวอร์"))


if __name__ == "__main__":
    unittest.main()
