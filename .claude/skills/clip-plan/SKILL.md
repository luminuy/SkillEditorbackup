---
name: clip-plan
description: เลือกช่วงวิดีโอที่จะกลายเป็นคลิปสั้นไวรัลและเขียนแผนตัดต่อ plan.json (segments, hook บนจอ, ป้ายเปิดไพ่, reframe 9:16, สไตล์ซับ). ใช้เมื่อต้องหา highlight, ตัดดวงรายราศี/รายกอง, เลือก moment ที่คนจะดูจนจบ, คิด hook 3 วินาทีแรก, หรือวางโครงคลิปจาก transcript — ใช้ก่อนการ render ทุกครั้ง.
---

# วางแผนคลิป (Story Producer)

อินพุต: `projects/<slug>/transcript.txt`, `analysis.md` (chapters, candidates, risk flags), `project.json`
เอาต์พุต: `projects/<slug>/plan.json` (schema เต็ม: `.claude/skills/social-clip-studio/references/engine-cli.md`)

มาตรฐานงาน: อ่าน `.claude/skills/social-clip-studio/references/pro-playbook.md` (โครงเรื่อง, hook, re-hook, loop) ก่อนเลือกช่วง

## ขั้นตอน
1. อ่าน `analysis.md` → รู้โครง (chapters) และจุดเสี่ยง
2. อ่าน `transcript.txt` ทั้งหมด — heuristic score เป็นแค่จุดเริ่ม คุณคือบรรณาธิการตัวจริง
3. ดูภาพ: `python3 -m clipstudio frames <slug> --count 16` แล้ว Read `work/frames_source.jpg`
   เพื่อรู้ว่าหน้าผู้พูด/กองไพ่อยู่ตรงไหน → เลือก reframe (fit / crop x / stack regions)
   ต้องการดูช่วงเฉพาะ: `frames <slug> --times 312,318,325 --tag reveal`
4. เขียน `plan.json` → `python3 -m clipstudio plan-check <slug>` (ดูความยาวหลังตัด silence)

## ฟิลด์ที่ต้องใส่ต่อคลิป (นอกจาก segments)
- `kind`: `zodiac` / `pile` / `weekday` / `message` / `highlight` — ใช้เลือก CTA อัตโนมัติ (`cta_by_kind` ใน preset) เช่น คลิปราศีจะไม่ขึ้น "เลือกกองต่อ"
- `platforms`: ถ้าผู้กำกับสั่งเฉพาะบางแพลตฟอร์ม เช่น `["tiktok", "shorts"]` (ไม่ใส่ = ทุกแพลตฟอร์มใน config) — copywriter/QA/review ใช้ค่านี้
- `hook`, `labels`, `title`, `notes` ตามด้านล่าง · เอฟเฟกต์/จังหวะเป็นงานของ clip-effects-designer (skill `clip-effects`)

## เวลาแม่น ๆ
- `python3 -m clipstudio find <slug> "The Lovers"` → เวลาเริ่มของคำในไฟล์ต้นฉบับ (ใช้กับ `labels.at`, จุดเริ่ม segment)
- เวลาระดับคำทั้งหมดอยู่ใน `transcript.json` → `segments[].words[]` (`text`, `start`, `end`)
- เจอคำผิดใน transcript → `python3 -m clipstudio fix <slug> <id> "ข้อความที่ถูก"` ก่อนเขียน hook/labels

## เกณฑ์เลือกช่วง (ตามลำดับความสำคัญ)
1. **จบในตัว** — คนที่ไม่เคยดูช่องต้องเข้าใจโดยไม่ต้องดูต้นฉบับ (มีบริบท: ราศี/กอง/หัวข้อ)
2. **เปิดแรงใน 1–2 วินาที** — ประโยคแรกคือคำตอบ/คำทำนายที่น่าสนใจที่สุด ไม่ใช่ "สวัสดีค่ะ" หรือ "ต่อไปเป็น…"
   → ตัดคำเกริ่นทิ้ง, หรือใช้ cold open (`"sort": false`, segment แรก = จังหวะเปิดไพ่/ประโยคพีค แล้วค่อยย้อนเล่า)
3. **จบแบบมีจุดหมาย** — จบที่ข้อความให้กำลังใจ/สรุป/คำถามชวนคอมเมนต์ ไม่ตัดกลางประโยค (ใช้เวลาจบ segment)
4. **ความยาว** 20–60 วินาที (หลังตัด silence) — ราศี/กอง ≤ 75s ได้ถ้าเนื้อแน่น; Facebook Reels ≤ 90s
   - chapter ที่สั้นกว่า 20s หลังตัด: ยอมรับได้ถึง 15s (Reels/Facebook โอเค, TikTok/Shorts จะเตือน info) — อย่ายืดด้วยการใส่คำเกริ่น;
     ถ้าต่ำกว่า 15s ให้รวมกับคลิป teaser/รวมราศี หรือปิด `remove_silence` เฉพาะคลิปนั้น
   - คลิปราศี/กอง: เริ่มที่ **ประโยคแรกที่เป็นเนื้อหาของราศีนั้น** ("ชาวราศีเมษ ไพ่ใบแรก…") ตัด "ต่อไปเป็นราศี…" ทิ้ง — ชื่อราศีอยู่บน hook แล้ว
5. **ไม่ติด risk flag** — ช่วงเลขเด็ด/หวย/การันตีผล/ขู่ให้แชร์/สุขภาพ → ตัดออก หรือไม่เลือกเลย

## hook บนจอ
- ≤ 40 ตัวอักษร (นับเฉพาะตัวที่มีความกว้าง ไม่นับวรรณยุกต์/สระบน-ล่าง — `plan-check` นับให้), 1–2 บรรทัด, ไม่มีอิโมจิ (libass แสดงอิโมจิไม่ได้)
- บอก **ใคร + ได้อะไร**: "ราศีเมษ คนที่คิดถึงกำลังจะทักมา", "กอง 2 ใครกำลังจะกลับมา"
- ต้องตรงกับเนื้อหาในคลิปจริง (ไม่ clickbait เกินจริง — ผิดนโยบายและทำให้คนเลื่อนผ่าน)
- niche ดูดวง: ดูสูตรใน skill `tarot-reading-knowledge` → `references/hooks-th.md`

## labels
- จังหวะเปิดไพ่ทุกใบที่มีผลต่อคำทำนาย: `{"at": <วินาทีต้นฉบับ>, "card": "<id>"}` — หา id ด้วย `python3 -m clipstudio cards --search <ชื่อ>`
- badge หัวข้อ: `{"at": ..., "text": "คนโสด", "duration": 2.5}`
- ไม่เกิน 1 label ต่อ 3 วินาที

## ตัวเลือกอื่น
- `speed: 1.05–1.1` เมื่อผู้พูดช้า (ห้ามเกิน 1.15 เสียงจะแปลก)
- per-segment `zoom: 1.12–1.2` สลับกันระหว่าง segment = jump-cut punch-in ช่วยกันคนเลื่อนผ่าน
- `captions.style`: highlight (ค่าเริ่มต้น อ่านง่าย) · pop (คำเดียวใหญ่ พลังสูง เหมาะคลิปสั้น <30s) · karaoke (2 บรรทัด นุ่มนวล) · plain
- `music`: ใช้เฉพาะไฟล์ที่มีสิทธิ์ใช้ใน `assets/music/` (เพลงติดลิขสิทธิ์ → ปล่อยว่างแล้วให้ผู้ใช้ใส่เพลงในแอปตอนโพสต์)

## ตั้งชื่อ id / ลำดับ
`NN-<topic>` เรียงตาม **ความแรง** (คลิปแรงสุด = 01): `review` จะจัด 01 ลงช่วง prime time วันแรก (`posting.slots` เรียงตามความสำคัญ)

## ก่อนส่งต่อ
`python3 -m clipstudio plan-check <slug>` ต้องไม่มี ERROR; WARN เรื่องความยาว/hook ให้แก้หรืออธิบายในรายงาน
การ render final เป็นงานของ clip-video-editor — producer render แค่ draft เพื่อเช็ก reframe

## รายงานกลับ
ตาราง: id · ช่วงเวลาต้นฉบับ · ความยาวประมาณ · hook · เหตุผลที่เลือก — และช่วงที่ตั้งใจ *ไม่* เลือกเพราะติด flag
