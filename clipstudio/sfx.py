"""Sound-effect library.

Every effect is synthesised with ffmpeg on first use (no licensing issues)
and cached in assets/sfx/. Drop your own file named <name>.wav/.mp3/.m4a
into assets/sfx/custom/ to override one.
"""
from __future__ import annotations

import os

from . import ff
from .config import ROOT

SFX_DIR = os.path.join(ROOT, "assets", "sfx")
CUSTOM_DIR = os.path.join(SFX_DIR, "custom")

# name -> (description, ffmpeg lavfi source + filter chain)
LIBRARY: dict[str, tuple[str, list[str]]] = {
    "whoosh": ("ลมพัดเร็ว — ใช้กับ transition",
               ["-f", "lavfi", "-i", "anoisesrc=d=0.55:c=pink:a=0.9:r=48000",
                "-af", "highpass=f=350,lowpass=f=6000,volume='min(1,t/0.30)*if(gt(t,0.30),max(0,1-(t-0.30)/0.25),1)':eval=frame,"
                       "apulsator=hz=1.6:amount=0.6,aformat=channel_layouts=stereo"]),
    "whoosh-soft": ("ลมพัดนุ่ม — transition แบบ calm",
                    ["-f", "lavfi", "-i", "anoisesrc=d=0.8:c=brown:a=0.9:r=48000",
                     "-af", "highpass=f=200,lowpass=f=2500,volume='0.8*sin(PI*t/0.8)':eval=frame,aformat=channel_layouts=stereo"]),
    "chime": ("ระฆังแก้วใส — เปิดไพ่ / ข้อความสำคัญ",
              ["-f", "lavfi", "-i",
               "aevalsrc='0.22*sin(2*PI*1568*t)*exp(-4*t)+0.18*sin(2*PI*2093*t)*exp(-4*(t-0.07))*gte(t,0.07)"
               "+0.15*sin(2*PI*2637*t)*exp(-4*(t-0.14))*gte(t,0.14)+0.12*sin(2*PI*3136*t)*exp(-4*(t-0.21))*gte(t,0.21)':d=1.6:s=48000",
               "-af", "aecho=0.8:0.6:90|170:0.35|0.2,aformat=channel_layouts=stereo"]),
    "sparkle": ("ประกายวิบวับ — เปิดไพ่แบบสดใส",
                ["-f", "lavfi", "-i",
                 "aevalsrc='0.10*sin(2*PI*(3500+900*sin(40*t))*t)*exp(-3*t)+0.08*sin(2*PI*5200*t)*exp(-9*mod(t,0.11))*lt(t,0.9)':d=1.2:s=48000",
                 "-af", "aecho=0.7:0.5:40|80:0.3|0.2,highpass=f=1500,aformat=channel_layouts=stereo"]),
    "pop": ("ป๊อปสั้น — ข้อความเด้งขึ้น / hook",
            ["-f", "lavfi", "-i", "aevalsrc='0.7*sin(2*PI*(420+900*exp(-35*t))*t)*exp(-22*t)':d=0.22:s=48000",
             "-af", "aformat=channel_layouts=stereo"]),
    "impact": ("เสียงกระแทกทุ้ม — จังหวะพีค / ไพ่แรง",
               ["-f", "lavfi", "-i", "aevalsrc='0.9*sin(2*PI*(48+60*exp(-8*t))*t)*exp(-3.5*t)':d=1.4:s=48000",
                "-af", "lowpass=f=900,aformat=channel_layouts=stereo"]),
    "riser": ("เสียงไต่ขึ้น — ก่อนเฉลย",
              ["-f", "lavfi", "-i", "aevalsrc='0.35*(t/1.4)^2*sin(2*PI*(180*t+260*t*t))':d=1.4:s=48000",
               "-af", "aecho=0.7:0.5:50:0.3,aformat=channel_layouts=stereo"]),
    "shimmer": ("บรรยากาศลึกลับ — พื้นหลังช่วงเปิดไพ่",
                ["-f", "lavfi", "-i",
                 "aevalsrc='(0.10*sin(2*PI*523*t)+0.08*sin(2*PI*659*t)+0.07*sin(2*PI*784*t)+0.05*sin(2*PI*1046*t))"
                 "*(0.6+0.4*sin(2*PI*5*t))*sin(PI*t/2.5)':d=2.5:s=48000",
                 "-af", "aecho=0.8:0.7:120|240:0.3|0.2,aformat=channel_layouts=stereo"]),
    "click": ("คลิกเบา — ซับ/ป้ายขึ้น",
              ["-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*2400*t)*exp(-120*t)':d=0.06:s=48000",
               "-af", "aformat=channel_layouts=stereo"]),
}


def path(name: str) -> str:
    """Return a playable file for the effect, synthesising it if needed."""
    for ext in (".wav", ".mp3", ".m4a", ".ogg"):
        p = os.path.join(CUSTOM_DIR, name + ext)
        if os.path.exists(p):
            return p
    if name not in LIBRARY:
        raise SystemExit(f"unknown sfx '{name}' (have: {', '.join(LIBRARY)}; or add assets/sfx/custom/{name}.wav)")
    out = os.path.join(SFX_DIR, name + ".wav")
    if not os.path.exists(out):
        os.makedirs(SFX_DIR, exist_ok=True)
        ff.run(["-y", *LIBRARY[name][1], "-ar", "48000", "-c:a", "pcm_s16le", out])
    return out


def build_all() -> list[str]:
    return [path(n) for n in LIBRARY]
