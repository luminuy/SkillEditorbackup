# ใช้งานบน macOS

## ติดตั้ง (ครั้งเดียว)
```bash
# 1) ติดตั้ง Homebrew ถ้ายังไม่มี: https://brew.sh
# 2) โคลน repo แล้ว
cd SkillEditor
bash setup-mac.sh
source .venv/bin/activate          # ทุกครั้งที่เปิด Terminal ใหม่
```
สคริปต์จะติดตั้ง:
| อะไร | ทำไม |
|---|---|
| ffmpeg (Homebrew) | มี libass (ซับไทย), VideoToolbox (เข้ารหัสด้วยชิป Mac), ffprobe |
| faster-whisper, pythainlp, Pillow, numpy | ถอดเสียง, ตัดคำไทย, ทำภาพ |
| **mlx-whisper** (เฉพาะ M1/M2/M3/M4) | ถอดเสียงด้วย GPU ของ Apple Silicon — เร็วกว่า CPU หลายเท่า (เลือกอัตโนมัติ) |
| ฟอนต์ Kanit → `~/Library/Fonts` | ใช้ฟอนต์แบรนด์เดียวกันใน CapCut / Final Cut / Resolve |

ตรวจ: `python -m clipstudio doctor` → ต้องขึ้น `READY`, `mlx_whisper: ok`, `videotoolbox: ok`

## ใช้กับ Claude Code บน Mac
เปิด Claude Code (แอป Desktop หรือ `claude` ใน Terminal) ในโฟลเดอร์ `SkillEditor` แล้วพิมพ์เช่น
> ตัดคลิป ~/Movies/ดวงรายสัปดาห์.mov เป็นคลิปละราศี งานระดับโปร ส่งเข้า Final Cut ด้วย

ไฟล์วิดีโอวางที่ไหนก็ได้ (ใส่ path เต็ม) หรือคัดลอกไว้ใน `input/`

## เลือกเส้นทางการ finish
| เส้นทาง | คำสั่ง | เหมาะกับ |
|---|---|---|
| ไฟล์พร้อมโพสต์ | `render` (ค่าเริ่มต้น) | โพสต์ทุกวัน เร็วที่สุด — ซับ/เอฟเฟกต์/เสียง/สีครบ |
| CapCut for Mac | `capcut --zip` | อยากใช้เพลง/เอฟเฟกต์/สติกเกอร์ในแอป |
| Final Cut Pro | `nle` → File ▸ Import ▸ XML | เกลี่ยจุดตัด, ทำสีละเอียด, คลิปสำคัญ |
| DaVinci Resolve | `nle` → File ▸ Import ▸ Timeline (.fcpxml) + import `.srt` | color grade ระดับสูง, Fairlight เสียง |
| Premiere Pro | `nle` → import `.edl` + `.srt` | ทีมที่ใช้ Adobe |

## ความเร็วบน Mac (โดยประมาณ)
- ถอดเสียง: mlx-whisper turbo บน M-series เร็วกว่า faster-whisper บน CPU มาก (ขึ้นกับรุ่นชิป)
- draft: ใช้ VideoToolbox อัตโนมัติ (เร็วมาก คุณภาพพอสำหรับตรวจ)
- final: ใช้ x264 (คุณภาพต่อขนาดไฟล์ดีที่สุด) — อยากเร็วสุดตั้ง `"edit": {"encoder": "videotoolbox"}`

## เปิดผลลัพธ์
```bash
open projects/<slug>/review.html          # ดูทุกคลิป + คัดลอกแคปชัน
open projects/<slug>/renders               # ไฟล์ mp4 → AirDrop เข้า iPhone แล้วโพสต์
open projects/<slug>/nle/<slug>.fcpxml     # เปิดใน Final Cut Pro
```

## ปัญหาที่พบบ่อย
| อาการ | แก้ |
|---|---|
| `doctor` บอก filter `ass` MISSING | ffmpeg ไม่ใช่ของ Homebrew — `brew reinstall ffmpeg` แล้วเปิด Terminal ใหม่ |
| FCP ขึ้น missing media | ไฟล์ต้นฉบับถูกย้าย — Relink ไปที่ไฟล์เดิม หรือรัน `nle` ใหม่ |
| mlx-whisper ช้าครั้งแรก | กำลังดาวน์โหลดโมเดล (~1.6 GB) ครั้งเดียว |
| ฟอนต์ไทยในแอปไม่ใช่ Kanit | ปิด-เปิดแอปใหม่หลังรัน `setup-mac.sh` |
