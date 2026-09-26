# SkillEditor — Social Clip Studio

สตูดิโอตัดคลิปสั้นด้วย Claude: วิดีโอยาว → คลิป TikTok / Reels / Shorts / Facebook Reels พร้อมซับไทย, ปก, แคปชัน, ตารางโพสต์
ค่าเริ่มต้นตั้งไว้สำหรับช่องดูดวงไพ่ทาโรต์ (preset `tarot`) แต่ใช้กับ niche อื่นได้ด้วย `presets/`

## เมื่อผู้ใช้ส่งวิดีโอหรือขอให้ตัดคลิป
โหลด skill **`social-clip-studio`** แล้วทำหน้าที่ผู้กำกับ: แตกงานให้ subagent ใน `.claude/agents/` (ขนานกันได้ตามที่ skill ระบุ)
subagent เรียก subagent ต่อไม่ได้ — การประสานงานอยู่ที่ main thread เสมอ

## โครงสร้าง
- `clipstudio/` — engine (Python + ffmpeg + faster-whisper + libass). CLI: `python3 -m clipstudio <cmd>` จาก repo root
  - `render.py` ตัด/reframe/concat/loudness · `captions.py` ASS overlay ทุกชั้น · `textutil.py` ตัดคำไทย+วัดความกว้าง
  - `analyze.py` silence/chapters/candidates/risk flags · `transcribe.py` whisper/srt · `qa.py` · `review.py` · `thumbnail.py`
  - `data/cards.json` ไพ่ 78 ใบ (ไทย+อังกฤษ) · `data/zodiac.json` ราศี/วันเกิด/กอง
- `.claude/skills/` — social-clip-studio (ผู้กำกับ), clip-transcribe, clip-plan, clip-render, clip-thumbnail, clip-copywriting, clip-qa, tarot-reading-knowledge
- `.claude/agents/` — clip-transcriber, clip-trend-scout, clip-story-producer, clip-video-editor, clip-copywriter, clip-thumbnail-artist, clip-qa-reviewer
- `channel.config.json` — brand kit ของช่อง (merge ทับ `presets/<preset>.json` ทับค่า default ใน `clipstudio/config.py`)
- `projects/<slug>/` — งานแต่ละวิดีโอ (ไม่ commit) · `input/` — ไฟล์ต้นฉบับ (ไม่ commit) · `assets/fonts` — Kanit (OFL)

## กติกาการพัฒนา engine
- ตรวจทุกการเปลี่ยนแปลงด้วยวิดีโอจริง: `init` → `transcribe --srt` (หรือ whisper) → `analyze` → `render --draft` → `snapshot` แล้ว **ดูภาพ**
- ข้อความบนจอทั้งหมดผ่าน `AssBuilder` (ห้ามใช้ drawtext — ffmpeg ของ imageio ไม่มี และตัดคำไทยไม่ได้)
- เส้นทางไฟล์ใน filter ffmpeg: รันด้วย `cwd=project.dir` + path สัมพัทธ์ผ่าน `ff.filter_path`
- เวลาใน plan (`segments`, `labels.at`) เป็นเวลาของไฟล์ต้นฉบับเสมอ; `Timeline` แปลงเป็นเวลาในคลิป
- อย่า commit ไฟล์วิดีโอ/เสียง/โปรเจกต์
