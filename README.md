# 🔮 SkillEditor — สตูดิโอตัดคลิปโซเชียลด้วย Claude

ส่งวิดีโอยาว (ไลฟ์ดูดวง, ดวง 12 ราศี, เลือกกอง, คลิปพูด, พอดแคสต์) → ได้คลิปสั้นพร้อมโพสต์ **TikTok · Instagram Reels · YouTube Shorts · Facebook Reels**
ทีมเอเจนต์ 8 ตัวทำงานขนานกัน: ถอดเสียงไทย → หาเทรนด์ → เลือก moment → ใส่เอฟเฟกต์/จังหวะ → ตัดต่อ → ปก → แคปชัน → QA
ได้ไฟล์พร้อมโพสต์ทันที **หรือ** ส่งต่อไปแต่งใน **CapCut** ก็ได้

## ได้อะไรบ้าง
| | |
|---|---|
| 🎙️ ถอดเสียงไทยระดับคำ | faster-whisper + ศัพท์ไพ่/ราศี + แก้คำผิดอัตโนมัติ + เอเจนต์พิสูจน์อักษร |
| ✂️ ตัดอัตโนมัติ | ตัดช่วงเงียบแบบ jump-cut, แบ่งคลิปตามราศี/กอง/วันเกิดอัตโนมัติ, cold open, punch-in zoom, เร่งสปีด |
| 📱 แนวตั้ง 9:16 | fit + พื้นหลังเบลอ / crop ตามจุดสนใจ / stack (หน้า + กองไพ่) · 4:5 · 1:1 · 16:9 |
| 💬 ซับไทย | ไฮไลต์ทีละคำ · karaoke · pop ทีละคำ · plain — ตัดบรรทัดตามคำไทยจริง ไม่ขาดกลางคำ |
| 🃏 ป้ายเปิดไพ่ | ใส่แค่ `"card": "the-tower"` → ขึ้นชื่อไพ่ + ความหมายสั้นอัตโนมัติ (ข้อมูล 78 ใบ) |
| ✨ เอฟเฟกต์ & จังหวะ | 3 สไตล์ `calm` · `dynamic` · `viral` — transition สมูท 30+ แบบ (crossfade, zoom, whip, slide, blur, circle…), กล้อง push-in/punch-in/shake, แฟลช, ประกายดาว, glow, glitch, vignette, ซับเด้ง + คำสำคัญสีเด่น, ภาพไม่นิ่งเกิน 2.5–4 วิ |
| 🔔 เสียงเอฟเฟกต์ | whoosh, chime, sparkle, pop, impact, riser, shimmer — สังเคราะห์เอง ไม่ติดลิขสิทธิ์ วางอัตโนมัติตอน transition / เปิดไพ่ / hook |
| 🎬 CapCut | `capcut` → วิดีโอไม่มีตัวหนังสือ + ซับ .srt (บรรทัด/ทีละคำ) + PNG โปร่งใส (hook, ป้ายไพ่, CTA) วางตำแหน่งแล้ว + เสียงเอฟเฟกต์ + คู่มือไทยว่าใส่อะไรตรงไหน |
| 🎨 แบรนด์ | hook บนจอ, CTA ท้ายคลิป (เปลี่ยนตามประเภทคลิป), watermark, progress bar, สีแบรนด์, ฟอนต์ Kanit |
| 🔊 เสียง | ลด noise, compressor, เพลงประกอบลดเสียงอัตโนมัติเมื่อพูด, loudness -14 LUFS (two-pass) |
| 🖼️ ปก | ปก 9:16 และ thumbnail 16:9 ตัวอักษรเรืองแสง |
| ✍️ แคปชัน | แยกตามแพลตฟอร์ม + แฮชแท็ก + คอมเมนต์ปักหมุด + ตารางโพสต์ |
| ✅ QA | สเปกแพลตฟอร์ม, loudness, dead air, safe zone, คำเสี่ยงผิดนโยบาย (เลขเด็ด, การันตีผล) |

## เริ่มใช้งาน
```bash
bash setup.sh                       # ติดตั้ง ffmpeg (ผ่าน pip), faster-whisper, pythainlp, Pillow แล้วรัน doctor
```
แก้ `channel.config.json`: ชื่อช่อง, `handle`, แพลตฟอร์ม, เวลาโพสต์ (สี/ตำแหน่งซับเพิ่มได้ — ดู `clipstudio/config.py`)

จากนั้นเปิด Claude Code ในโฟลเดอร์นี้แล้วพิมพ์เช่น:
> ตัดคลิป input/ดวงรายสัปดาห์.mp4 เป็นคลิปละราศี ลง TikTok กับ Shorts สไตล์ dynamic
> ทำเป็น CapCut kit ด้วย จะไปใส่เพลงในแอปเอง

หรือเรียกสกิลตรง ๆ: `/social-clip-studio input/live-0926.mp4`

## ผลลัพธ์ (`projects/<ชื่อ>/`)
```
renders/<clip>.mp4          คลิปพร้อมโพสต์ (H.264 1080x1920 30fps AAC, -14 LUFS)
thumbs/<clip>_1080x1920.jpg ปก
capcut/<clip>/              ชุดส่งต่อ CapCut (ถ้าสั่ง)
copy/<clip>.json            แคปชันทุกแพลตฟอร์ม
publish/<clip>/<platform>.txt   ข้อความพร้อมคัดลอกไปวาง
review.html                 หน้ารวมดูคลิป + ปุ่มคัดลอกแคปชัน + สถานะ QA
schedule.csv                ตารางโพสต์
```

## ทีมเอเจนต์
```
ผู้กำกับ (skill social-clip-studio)
 ├─ ขนาน:  clip-transcriber  ‖  clip-trend-scout
 ├─ analyze (engine)
 ├─ clip-story-producer     → plan.json (ช่วงตัด, hook, ป้ายไพ่, reframe)
 ├─ clip-effects-designer   → style, transition, แฟลช/ประกาย/ซูม, เสียงเอฟเฟกต์
 ├─ ขนาน:  clip-video-editor (render final / CapCut kit) ‖ clip-copywriter ‖ clip-thumbnail-artist
 ├─ clip-qa-reviewer        → ตรวจเทคนิค + ภาพ + นโยบาย
 └─ review / capcut         → review.html, schedule.csv, capcut/<clip>/
```

## ใช้ engine ด้วยมือ
```bash
python3 -m clipstudio init input/reading.mp4 --name weekly
python3 -m clipstudio transcribe weekly            # หรือ --srt ซับจาก CapCut
python3 -m clipstudio fix weekly 12 "ข้อความที่ถูก"
python3 -m clipstudio analyze weekly               # chapters + candidates + risk flags
# เขียน projects/weekly/plan.json (ตัวอย่าง: .claude/skills/social-clip-studio/references/engine-cli.md)
python3 -m clipstudio find weekly "The Tower"      # เวลาแม่น ๆ ของคำ (ใส่ label / fx)
python3 -m clipstudio plan-check weekly
python3 -m clipstudio render weekly --draft && python3 -m clipstudio snapshot weekly 01-aries
python3 -m clipstudio render weekly
python3 -m clipstudio thumbnail weekly --clip 01-aries --time 22.6 --title "ราศีเมษ มีข่าวดี"
python3 -m clipstudio qa weekly && python3 -m clipstudio review weekly
python3 -m clipstudio capcut weekly --zip           # ส่งต่อ CapCut
python3 -m clipstudio cards --search tower
```

## ส่วนเสริมภายนอก (ไม่บังคับ)
ffmpeg-llm plugin · Post Bridge (โพสต์อัตโนมัติ) · vidIQ (เทรนด์) · Canva (ปกจาก template) · Marketing plugin — รายละเอียด:
`.claude/skills/social-clip-studio/references/external-addons.md`

## เพิ่ม niche อื่น
คัดลอก `presets/general.json` → `presets/<niche>.json` ปรับสี, CTA, `asr.prompt` (ศัพท์เฉพาะ), `asr.fixes`, `chapter_patterns`
แล้วตั้ง `"preset": "<niche>"` ใน `channel.config.json`

---
ฟอนต์ Kanit © The Kanit Project Authors — SIL Open Font License 1.1 (`assets/fonts/OFL-Kanit.txt`)
เนื้อหาดูดวงควรมีข้อความ "เพื่อเป็นแนวทาง/ความบันเทิง" และหลีกเลี่ยงเลขเด็ด/การันตีผล ตามนโยบายแพลตฟอร์ม
