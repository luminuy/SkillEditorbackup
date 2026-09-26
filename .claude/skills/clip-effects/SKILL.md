---
name: clip-effects
description: ออกแบบจังหวะและเอฟเฟกต์ของคลิปสั้นให้น่าดูจนจบ — transition แบบสมูท (crossfade, zoom, whip, slide, blur ฯลฯ), กล้องเคลื่อน (push-in, punch-in, shake), เอฟเฟกต์ภาพ (แฟลช, ประกายดาว, glow, glitch), เสียงเอฟเฟกต์ (whoosh, chime, sparkle, pop, impact), ซับเด้ง/คำสำคัญสีเด่น และสไตล์จังหวะ calm/dynamic/viral. ใช้ทุกครั้งที่ผู้ใช้พูดถึง เอฟเฟกต์, effect, transition, ทรานสิชัน, จังหวะ, pacing, ให้คลิปไม่น่าเบื่อ, เพิ่ม retention, ซับเด้ง, เสียงประกอบ, sound effect หรือหลังเขียน plan.json เสร็จก่อน render.
---

# เอฟเฟกต์ & จังหวะ (Effects Designer)

engine ใส่เอฟเฟกต์ให้อัตโนมัติจาก **style** ของคลิป แล้วคุณปรับเพิ่มเฉพาะจุดใน `plan.json`
ทุกอย่างอยู่ในไฟล์เดียว render ครั้งเดียว — ไม่ต้องใช้โปรแกรมอื่น (หรือส่งต่อ CapCut ด้วย skill `clip-capcut`)

## 1. เลือก style (ตั้งต่อคลิป `"style"` หรือค่าเริ่มต้นใน `channel.config.json` → `effects.style`)

| style | ความรู้สึก | อัตโนมัติ |
|---|---|---|
| `calm` | ลึกลับ อบอุ่น ช้า — ข้อความจากจักรวาล, ฮีลใจ | push-in ช้า 5%, crossfade 0.45s, glow + ประกายตอนเปิดไพ่, chime, ซับ fade, vignette |
| `dynamic` (ค่าเริ่มต้น) | มีพลัง อ่านง่าย — ดวงราศี, เลือกกอง | push-in 6%, transition zoom, punch-in สลับทุก jump cut, แฟลช+ประกาย+punch ตอนเปิดไพ่, whoosh/sparkle/pop, ซับ pop, ไม่นิ่งเกิน 4s |
| `pro` | สไตล์ช่องใหญ่: คม สะอาด ไม่รก — ทุกประเภท | push 4%, crossfade สั้น 0.2s, punch-in สลับทุก jump cut, punch+ประกายตอนเปิดไพ่, punch ที่คำสำคัญ, ไม่นิ่งเกิน 3s, ไม่มี vignette/pop เสียงเยอะ |
| `viral` | เร็ว เร้าใจ — hook แรง ๆ, คลิป < 30s | push 8%, whip, punch แรงขึ้น, แฟลช+shake+ประกาย ตอนเปิดไพ่, impact+sparkle, ซับ bounce, punch ที่คำสำคัญ, ไม่นิ่งเกิน 2.5s |
| `none` | ตัดเปล่า ๆ | ไม่มีเอฟเฟกต์ (ยังมีซับ/hook/label) |

เลือกตามอารมณ์เนื้อหา ไม่ใช่ใส่แรงสุดทุกคลิป: ข่าวร้าย/ไพ่หนัก (The Tower, Death, 10 ดาบ) → `calm` หรือ `dynamic` ไม่ใส่ impact/shake จนดูน่ากลัว

## 2. Transition ระหว่าง segment
ใช้เมื่อคลิปมีหลาย segment (ข้ามช่วงในต้นฉบับ) — jump cut จากการตัดเงียบภายใน segment เดียวยังเป็นการตัดตรง (สไตล์คลิปพูด)
```jsonc
"transition": "crossfade",                                   // ทั้งคลิป
"segments": [{...}, {"start": 89, "end": 101, "transition_in": {"type": "circle", "duration": 0.5}}]   // เฉพาะรอยต่อนี้
```
| ชื่อ | ลักษณะ | เหมาะกับ |
|---|---|---|
| `crossfade` / `dissolve` | ละลายเข้าหากันนุ่ม ๆ | calm, เปลี่ยนหัวข้อเบา ๆ |
| `zoom` | ซูมทะลุเข้าภาพถัดไป | dynamic — ค่าเริ่มต้น |
| `whip` / `slide` / `slideright` / `slideup` | ปัด/เลื่อนเร็ว | viral, เรื่องต่อเนื่อง |
| `blur` · `circle` · `radial` · `wipe` · `squeeze` · `wind` · `pixelize` | สไตล์พิเศษ | ใช้ 1 ครั้งต่อคลิปพอ |
| `dip` (ดำ) / `flashfade` (ขาว) | ดับ/สว่างผ่าน | ขึ้นช่วงใหม่, ก่อนเฉลย |
| `cut` · `punch` · `flash` · `shake` · `glitchcut` | ตัดตรง (+เอฟเฟกต์ที่รอยต่อ) | ไม่ทำให้คลิปยาวขึ้น |

transition แบบ overlap (ทุกตัวยกเว้นกลุ่ม cut) ทำให้คลิปสั้นลงเท่าความยาว transition (0.25–0.5s) — `plan-check` คำนวณให้แล้ว

## 3. เอฟเฟกต์ ณ เวลาที่กำหนด (`fx`, เวลาเป็นวินาทีของไฟล์ต้นฉบับ)
```jsonc
"fx": [
  {"at": 95.5, "type": "stars", "duration": 1.6, "sfx": "shimmer"},   // ประกายดาวทั้งจอ + เสียง
  {"at": 71.2, "type": "zoom", "duration": 2.0, "amount": 0.15},      // ซูมค้าง (เน้นประโยคสำคัญ)
  {"at": 72.5, "type": "zoom", "amount": 0.25, "x": 0.3, "y": 0.6},  // ซูมเข้าหาจุด (เช่น ไพ่บนโต๊ะ) — x,y = สัดส่วนของเฟรมผลลัพธ์
  {"at": 60.0, "type": "punch"}, {"at": 62.3, "type": "shake"}, {"at": 64.0, "type": "glitch"},
  {"at": 30.1, "type": "flash-strong"}, {"at": 40.0, "type": "glow", "y": 0.4}
]
```
หาเวลาแม่น ๆ: `python3 -m clipstudio find <slug> "คำ"` (เวลาเริ่มของคำ)
types: `punch` (ซูมเด้ง) · `zoom` (ซูมค้าง) · `shake` (สั่น) · `glitch` (RGB แยก) · `flash` / `flash-strong` (แฟลชขาว — อยู่ใต้ตัวหนังสือ) ·
`sparkle` (ประกายรอบป้าย) · `stars` (ดาวทั้งจอ) · `glow` (แสงนุ่มสีทอง)

## 4. เสียงเอฟเฟกต์
อัตโนมัติตาม style (transition → whoosh, เปิดไพ่ → sparkle/chime/impact, hook/CTA → pop) + เพิ่มเอง:
```jsonc
"sfx": [{"at": 70.8, "name": "riser", "offset": -1.2}, {"at": 72.0, "name": "impact", "volume": 0.4}]
```
คลัง: `whoosh`, `whoosh-soft`, `chime`, `sparkle`, `pop`, `impact`, `riser`, `shimmer`, `click` (`python3 -m clipstudio sfx`)
สังเคราะห์เองทั้งหมด ไม่ติดลิขสิทธิ์ · เปลี่ยนเสียงได้โดยวางไฟล์ชื่อเดียวกันใน `assets/sfx/custom/`
ปิดเสียงเอฟเฟกต์ทั้งคลิป: `"sfx_enabled": false` · เปลี่ยนเสียงตาม event: `"sfx_map": {"reveal": "chime"}` · ปิดเอฟเฟกต์อัตโนมัติ: `"auto_fx": false`

## 5. ซับให้น่าดู
- `"caption_anim"`: `none` · `fade` · `pop` · `bounce` (ค่าเริ่มต้นตาม style)
- คำสำคัญเป็นสีเด่น (`brand.emphasis`): รายการใน preset → `effects.emphasis_words` + ต่อคลิป `"emphasis": ["เนื้อคู่", "The Sun"]`
- สไตล์ซับ `bold` (2–3 คำต่อการ์ด ตัวใหญ่ ขอบหนา — แบบช่องใหญ่) + style `pro` = มาตรฐานงานโปร · `max_words` กำหนดจำนวนคำต่อการ์ดได้กับทุกสไตล์
- สไตล์ซับ `pop` (คำเดียวใหญ่) + style `viral` = พลังสูงสุด; `karaoke` 2 บรรทัด + `calm` = นุ่มนวล
- หลักการระดับโปรทั้งหมด: `.claude/skills/social-clip-studio/references/pro-playbook.md`

## 6. หลักจังหวะ (ทำไมถึงได้ผล)
- **ภาพต้องเปลี่ยนทุก 2–4 วินาที** (ตัด, ซูม, ป้าย, เอฟเฟกต์) — engine เติม punch ให้เองเมื่อนิ่งนานเกิน `max_static`
- **จุดพีค = เปิดไพ่** — ใส่แรงสุดตรงนั้น (label + แฟลช + ประกาย + เสียง) แล้วปล่อยให้ผู้พูดเล่าต่อแบบนิ่งขึ้น
- **riser ก่อนเฉลย 1–1.5s** แล้ว impact/sparkle ตอนเฉลย = สร้างความคาดหวัง
- อย่าใส่เอฟเฟกต์ทับคำพูดสำคัญจนฟังไม่รู้เรื่อง; เสียงเอฟเฟกต์ต้องเบากว่าเสียงพูด (engine ตั้งให้แล้ว ~ -8 ถึง -15 dB)
- ความสม่ำเสมอของช่องสำคัญกว่าความหวือหวา: เลือก style หลัก 1 แบบให้ทั้งซีรีส์

## 7. ตรวจผล
```bash
python3 -m clipstudio plan-check <slug>                 # นับ fx/sfx ต่อคลิป + ความยาวหลัง transition
python3 -m clipstudio render <slug> --clip <id> --draft
python3 -m clipstudio frames <slug> --video projects/<slug>/renders/<id>.draft.mp4 --times 3.4,3.6,12.0,12.2 --tag fx
```
Read ภาพ: แฟลชไม่ทำให้ตัวหนังสืออ่านไม่ออก, ประกายไม่บังหน้า, transition ไม่ตัดกลางคำ
