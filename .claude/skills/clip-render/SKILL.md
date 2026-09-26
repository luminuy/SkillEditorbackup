---
name: clip-render
description: เรนเดอร์คลิปสั้นแนวตั้ง 9:16 (และ 4:5, 1:1, 16:9) จาก plan.json ด้วย clipstudio engine — ตัด silence แบบ jump-cut, reframe (blur/crop/stack), ซับไทยไฮไลต์ทีละคำ, hook, ป้ายไพ่, CTA, watermark, progress bar, ลดเสียงรบกวน, เพลงประกอบ ducking, loudness -14 LUFS. ใช้เมื่อต้อง render, export, แก้ตำแหน่งซับ/ขนาดตัวอักษร/สี, หรือซ่อมคลิปที่ QA ตีกลับ.
---

# เรนเดอร์ (Video Editor)

## Loop มาตรฐาน: draft → ดู → แก้ → final
```bash
python3 -m clipstudio plan-check <slug>
python3 -m clipstudio render <slug> --draft                 # เร็ว (ultrafast) ทุกคลิป
python3 -m clipstudio snapshot <slug> <clip-id>             # แล้ว Read projects/<slug>/work/snap_<id>.jpg
python3 -m clipstudio render <slug> --clip <id> [--clip <id2>]   # final เฉพาะที่ผ่าน
```
ทดสอบแล้ว: คลิป 24s ใช้ ~11s (draft) / ~17s (final) บน CPU 4 คอร์

## สิ่งที่ต้องตรวจใน snapshot (ทุกคลิป)
- [ ] ซับอ่านออก ไม่ล้นขอบ ไม่ทับหน้า/มือ/ไพ่ที่เป็นจุดสนใจ
- [ ] hook ไม่ถูกตัด 2 บรรทัดสมดุล
- [ ] ภาพหลัก (หน้า/ไพ่) อยู่ในเฟรม — ถ้า crop ตัดหน้า → ปรับ `reframe.x` หรือเปลี่ยนเป็น `fit`
- [ ] label ขึ้นตรงจังหวะเปิดไพ่ (ช้า/เร็วเกิน → ปรับ `at`)
- [ ] เฟรมสุดท้าย CTA ไม่ทับซับ

## แก้อะไร ที่ไหน
| ปัญหา | แก้ที่ |
|---|---|
| ซับ/hook/label ตำแหน่ง ขนาด สี ทุกคลิป | `channel.config.json` (`captions.y/size`, `hook.y`, `brand.*`) — ไม่ใช่ใน plan |
| เฉพาะคลิปเดียว | `plan.json` → `captions: {...}`, `reframe`, `hook_seconds`, `cta` |
| คำในซับผิด | ส่งกลับ transcriber: `python3 -m clipstudio fix <slug> <id> "..."` แล้ว render ใหม่ |
| ตัดเงียบแรงไป (คำขาด) | `channel.config.json` → `edit.pad` 0.12→0.18 หรือ `edit.min_silence` 0.45→0.7; หรือ `"remove_silence": false` ในคลิปนั้น |
| เสียงเบา/ดังไม่เท่ากัน | engine ทำ two-pass loudnorm ให้แล้ว (-14 LUFS); ถ้าเสียงก้อง/ซ่ามาก ปิด `voice_enhance` แล้วลองเทียบ |
| เพลงกลบเสียงพูด | `music_volume` 0.12 → 0.08 |
| ภาพต้นฉบับแนวตั้งอยู่แล้ว | ใช้ `reframe: {"mode":"crop"}` (ไม่มีขอบเบลอ) |

## ข้อควรรู้ของ engine
- ทุกข้อความบนจอถูกรวมเป็นไฟล์ `.ass` เดียว (`work/<id>.ass`) — แก้ด้วยมือได้เพื่อทดลอง แต่จะถูกเขียนทับเมื่อ render ใหม่
- ตัดบรรทัดภาษาไทยด้วย pythainlp + วัดความกว้างจริงจากฟอนต์ → ไม่ตัดกลางคำ
- อิโมจิถูกลบจากข้อความบนจอโดยอัตโนมัติ (ใส่อิโมจิในแคปชันโพสต์แทน)
- ฟอนต์: Kanit (Regular/Bold/ExtraBold) ใน `assets/fonts` — วางฟอนต์ .ttf อื่นแล้วเรียกด้วยชื่อ family ใน `fonts.*`
- output: H.264 High, yuv420p, 30fps, AAC 192k 48kHz, +faststart — ผ่านสเปกทุกแพลตฟอร์ม
- ไฟล์ final อยู่ที่ `projects/<slug>/renders/<id>.mp4`; draft คือ `<id>.draft.mp4` (ลบได้)

## รายงานกลับ
ตาราง: id · ความยาว · วินาทีที่ตัดเงียบ · ปัญหาที่เจอ+วิธีแก้ · path ไฟล์
