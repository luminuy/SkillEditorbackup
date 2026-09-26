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


class EffectsTests(unittest.TestCase):
    def test_transition_names(self):
        from clipstudio import effects
        st = effects.STYLES["dynamic"]
        self.assertEqual(effects.parse_transition("whip", st), ("smoothleft", 0.3))
        self.assertEqual(effects.parse_transition({"type": "crossfade", "duration": 0.5}, st), ("fade", 0.5))
        self.assertEqual(effects.parse_transition("punch", st), ("punch", 0.0))
        with self.assertRaises(SystemExit):
            effects.parse_transition("nope", st)

    def test_timeline_overlap_shortens(self):
        tl = Timeline([{"start": 0, "end": 5}, {"start": 10, "end": 15, "overlap": 0.4}])
        self.assertAlmostEqual(tl.duration, 9.6)
        self.assertAlmostEqual(tl.pieces[1]["out_start"], 4.6)

    def test_events_and_zoompan(self):
        from clipstudio import effects
        st = effects.style_for({"id": "x", "style": "viral"}, DEFAULTS)
        pieces = [{"start": 0, "end": 4, "_seg": 0, "_first_of_seg": True},
                  {"start": 4.5, "end": 9, "_seg": 0, "_first_of_seg": False},
                  {"start": 20, "end": 26, "_seg": 1, "_first_of_seg": True}]
        segs = [{"start": 0, "end": 9}, {"start": 20, "end": 26}]
        effects.assign_transitions(pieces, segs, {}, st)
        effects.clamp_overlaps(pieces)
        self.assertEqual(pieces[2]["trans"], "smoothleft")
        tl = Timeline(pieces)
        clip = {"id": "x", "hook": "h", "_cta_start": None}
        ev = effects.build_events(clip, st, tl, [{"t": 2.0, "y": 0.3}], tl.duration, 1.0, [], [])
        names = [s["name"] for s in ev["sfx"]]
        self.assertIn("whoosh", names)
        self.assertIn("impact", names)
        self.assertTrue(ev["shake"])
        zp = effects.zoompan_filter(ev, st, 1080, 1920, 30, tl.duration, 2)
        self.assertIn("zoompan=z='1+", zp)
        self.assertIn("scale=2160:3840", zp)

    def test_style_none_is_quiet(self):
        from clipstudio import effects
        st = effects.style_for({"id": "x", "style": "none"}, DEFAULTS)
        tl = Timeline([{"start": 0, "end": 10}])
        ev = effects.build_events({"id": "x", "hook": "h"}, st, tl, [{"t": 1}], 10, 1.0, [], [])
        self.assertEqual((ev["sfx"], ev["ass"], ev["zoom"]), ([], [], []))
        self.assertIsNone(effects.zoompan_filter(ev, st, 1080, 1920, 30, 10, 1))


class ScheduleTests(unittest.TestCase):
    def test_priority_slots(self):
        import datetime as dt
        from clipstudio.review import schedule_slots
        cfg = {"posting": {"slots": ["19:30", "12:00", "07:30"], "per_day": 2}}
        out = schedule_slots(cfg, 3, dt.date(2026, 10, 1))
        self.assertEqual(out, ["2026-10-01 19:30", "2026-10-01 12:00", "2026-10-02 19:30"])


class ProFeatureTests(unittest.TestCase):
    def test_fcpxml_time_grid(self):
        from fractions import Fraction
        from clipstudio.nle import frame_duration, rt, tc
        self.assertEqual(frame_duration(29.97), Fraction(1001, 30000))
        self.assertEqual(rt(1.0, Fraction(1, 30)), "1s")
        self.assertEqual(rt(19.17, Fraction(1, 30)), "115/6s")  # 575 frames at 30fps
        self.assertEqual(tc(3723.5, 30), "01:02:03:15")

    def test_looks_and_fps(self):
        from clipstudio import finish
        cfg = deep_merge(DEFAULTS, {})
        self.assertEqual(finish.look_chain({"id": "a"}, cfg), "")
        chain = finish.look_chain({"id": "a", "look": "mystic", "sharpen": 0.4}, cfg)
        self.assertIn("lut3d=file=", chain)
        self.assertIn("unsharp", chain)
        cube = chain.split("lut3d=file=")[1].split(":interp")[0]
        with open(cube) as f:
            head = [next(f) for _ in range(2)]
        self.assertIn("LUT_3D_SIZE 36", head[1])
        with self.assertRaises(SystemExit):
            finish.look_chain({"id": "a", "look": "nope"}, cfg)
        self.assertEqual(finish.pick_fps({"fps": "source"}, cfg, {"fps": 59.94}), 60)
        self.assertEqual(finish.pick_fps({}, cfg, {"fps": 59.94}), 30)

    def test_bold_captions_limit_words(self):
        cfg = deep_merge(DEFAULTS, {})
        ab = AssBuilder(1080, 1920, cfg)
        words = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25, "seg": 0}
                 for i, t in enumerate(["หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด"])]
        cards_ = ab.caption_cards(words, {"style": "bold"})
        self.assertTrue(all(sum(len(ln) for ln in c["lines"]) <= 3 for c in cards_))
        self.assertEqual(sum(sum(len(ln) for ln in c["lines"]) for c in cards_), 7)
