---
name: clip-nle
description: ส่งต่องานไปตัดต่อแบบมืออาชีพบน Mac/PC — Final Cut Pro (FCPXML), DaVinci Resolve (FCPXML/EDL), Adobe Premiere Pro (EDL) พร้อมซับ .srt, markers ทุกจังหวะ และ PNG overlay — โดยคลิปในไทม์ไลน์อ้างอิงไฟล์ต้นฉบับ (non-destructive, ตัดต่อ/เลื่อนจุดตัดต่อได้เต็มที่). ใช้เมื่อผู้ใช้พูดถึง Final Cut, FCP, FCPX, DaVinci, Resolve, Premiere, XML, EDL, ตัดต่อบน Mac, อยากเกลี่ยจุดตัดเอง, color grade เอง หรือทำงานร่วมกับมือตัดต่อมืออาชีพ.
---

# ส่งต่อ Final Cut Pro / DaVinci Resolve / Premiere

engine ตัดสินใจ "ตัดตรงไหน" ให้แล้ว (จาก plan.json) — ไฟล์ NLE ให้มือตัดต่อเกลี่ยทุกจุดตัด ทำสี ทำเสียงต่อได้โดยไม่เสียคุณภาพ

```bash
python3 -m clipstudio nle <slug>                 # ทุกคลิป
python3 -m clipstudio nle <slug> --clip 01-aries
```
ผลลัพธ์ `projects/<slug>/nle/`:
| ไฟล์ | ใช้กับ |
|---|---|
| `<slug>.fcpxml` | **Final Cut Pro** (File ▸ Import ▸ XML) · **DaVinci Resolve** (File ▸ Import ▸ Timeline) — 1 event, 1 project แนวตั้งต่อคลิป, asset-clip ชี้ไฟล์ต้นฉบับพร้อม handles, markers (เปิดไพ่/FX/SFX/TRANSITION), PNG overlay บน lane 1 |
| `<clip>.edl` | **Premiere Pro** / Resolve / Avid (CMX3600 cut list) — import แล้ว relink ไปที่ไฟล์ต้นฉบับ |
| `<clip>.srt` | ซับตามไทม์ไลน์ของ cut list (FCP: File ▸ Import ▸ Captions · Resolve/Premiere: import SRT) |
| `markers_<clip>.csv` | ทุกจังหวะพร้อม timecode (ใช้ทำ markers เองใน Premiere) |
| `overlays/<clip>/*.png` | hook / ป้ายไพ่ / CTA แบบโปร่งใส 1080x1920 |

## ข้อควรรู้ (บอกผู้ใช้ตามจริง)
- **path ในไฟล์เป็น path เต็มของเครื่องที่รันคำสั่ง** — รัน `nle` บน Mac เครื่องที่มีไฟล์ต้นฉบับ (แนะนำ) ถ้าย้ายเครื่อง FCP/Resolve จะให้ Relink
- ไทม์ไลน์ใน NLE เป็น **ตัดตรงล้วน** (ไม่มี transition/เอฟเฟกต์/speed/สี) — ทุกอย่างที่ engine จะใส่ถูกบอกไว้เป็น marker ให้ทำตามในโปรแกรม
  (FCP: ⌘T = cross dissolve ที่จุดตัด, Resolve: Ctrl/⌘T) · speed ที่ตั้งใน plan ให้ใส่ Retime เอง
- การครอป 9:16: FCPXML ตั้ง conform = fit (โหมด fit) หรือ fill (โหมด crop) — ปรับ Transform/Position ต่อได้
- ทดสอบว่าไฟล์เป็น XML ถูกต้องตามโครงสร้าง FCPXML 1.9 แล้ว แต่ยังไม่ได้ทดสอบเปิดใน Final Cut/Resolve ทุกเวอร์ชัน — ถ้า import ไม่ผ่าน ให้ใช้ EDL + SRT แทน และแจ้งข้อความ error กลับมา
- ต้องการไฟล์พร้อมโพสต์ทันที → ใช้ `render` ปกติ (เอฟเฟกต์ครบ) ; NLE hand-off คือทางเลือกสำหรับงานที่จะ finish เอง

## workflow บน Mac (แนะนำ)
1. `bash setup-mac.sh` ครั้งเดียว (Homebrew ffmpeg + VideoToolbox, mlx-whisper สำหรับ M1–M4, ฟอนต์ Kanit ลง `~/Library/Fonts`)
2. Claude Code บน Mac สั่ง: "ตัดคลิป input/x.mov เป็นคลิปละราศี ส่งเข้า Final Cut" → pipeline ปกติ + `nle`
3. เปิด `.fcpxml` ใน FCP → เกลี่ยจุดตัด → ใส่ transition ตาม marker → Color (หรือ LUT เดียวกับ `finish.lut`) → Share 1080x1920
4. หรือใช้ `render` ของ engine เป็นเวอร์ชันส่งเร็ว แล้วใช้ FCP เฉพาะคลิปสำคัญ

แนวทางตัดต่อระดับมืออาชีพ: `.claude/skills/social-clip-studio/references/pro-playbook.md`
