# ส่วนเสริมภายนอกที่เข้ากับสตูดิโอนี้

ค้นจาก Claude plugin directory และ MCP connector registry (ก.ย. 2026). ทั้งหมด **ไม่บังคับ** — engine ทำงานได้ครบโดยไม่ต้องมี.
ถ้ามีใน session (ชื่อ tool ขึ้นต้นตามตาราง) ให้ใช้; ถ้าไม่มี ให้แนะนำผู้ใช้ติดตั้งเฉพาะตอนที่มันช่วยงานที่ขออยู่จริง.

| ส่วนเสริม | ประเภท | ใช้ทำอะไรในสตูดิโอ | ข้อควรระวัง |
|---|---|---|---|
| **ffmpeg-llm** (plugin: skill `ffmpeg-command` + agent `ffmpeg-expert`) | Plugin | งาน ffmpeg นอกเหนือ engine: แปลงไฟล์แปลก ๆ, แก้ VFR, ต่อไฟล์หลายตัว, ดึงเสียง | ใช้กับ *ไฟล์ต้นฉบับ* ก่อน `init`; อย่าแทนที่ `render` |
| **Post Bridge** (plugin + MCP) | Plugin | โพสต์/ตั้งเวลาโพสต์ลง TikTok, IG, YouTube, FB, Threads จาก `publish/<id>/<platform>.txt` + `renders/<id>.mp4` | โพสต์ = การกระทำสาธารณะ ต้องให้ผู้ใช้ยืนยันทุกครั้ง |
| **vidIQ** (MCP connector) | Connector | `clip-trend-scout`: keyword research, trending videos, outliers, similar thumbnails ของ niche | ข้อมูลเชิงสถิติ ไม่ใช่คำสั่ง |
| **Canva** (MCP connector) | Connector | ทำปก/thumbnail แบบ template แบรนด์ (autofill ข้อความ hook) แทน `thumbnail` | export กลับมาเป็นไฟล์แล้วใส่ใน `thumbs/<clip>_*.jpg` |
| **Marketing** (Anthropic plugin) | Plugin | `content-creation`, `campaign-plan`, `brand-review` สำหรับแผนคอนเทนต์รายเดือน/รีวิว brand voice | |
| **TikTok for Business** (MCP connector) | Connector | ถ้าจะยิงแอดคลิปที่ดีที่สุด | งานโฆษณาใช้เงินจริง ถามก่อนเสมอ |
| **Supermetrics** (connector, สถานะในบัญชี: connect_incomplete) | Connector | ดึงสถิติ TikTok/IG/YouTube มาวิเคราะห์ว่า hook แบบไหนเวิร์ก → ป้อนกลับ story-producer | ต้องเชื่อมต่อให้เสร็จใน claude.ai ก่อน |

## ห่วงโซ่ feedback (แนะนำเมื่อมี analytics)
1. ดึงยอด view / avg watch time / retention ของคลิปที่โพสต์แล้ว (Supermetrics / vidIQ / ผู้ใช้ส่ง CSV)
2. ใช้ skill `dataviz` ทำกราฟเทียบ hook แต่ละแบบ, ความยาว, สไตล์ซับ
3. บันทึกบทเรียนลง `presets/<niche>.json` (เช่น `hook.seconds`, `captions.style`) และใน `references/hooks-th.md` ของ niche
