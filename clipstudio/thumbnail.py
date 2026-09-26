"""Frame contact sheets (for agents to *look* at footage) and cover/thumbnail images."""
from __future__ import annotations

import os
import tempfile

from . import ff
from .captions import AssBuilder
from .config import FONTS_DIR, Project, hex_to_ass, load_config
from .textutil import Measurer, ass_escape, wrap_text
from .transcribe import mmss


def contact_sheet(video: str, times: list[float], out: str, cols: int = 4, width: int = 360) -> str:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    tiles = []
    with tempfile.TemporaryDirectory() as td:
        for i, t in enumerate(times):
            p = os.path.join(td, f"f{i}.jpg")
            try:
                ff.extract_frame(video, t, p, width)
                tiles.append((t, Image.open(p).convert("RGB")))
            except ff.FFmpegError:
                continue
        if not tiles:
            raise SystemExit("could not extract any frames")
        tw, th = tiles[0][1].size
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw, rows * (th + 28)), (18, 12, 30))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype(os.path.join(FONTS_DIR, "Kanit-Bold.ttf"), 20)
        except Exception:
            font = ImageFont.load_default()
        for i, (t, im) in enumerate(tiles):
            x, y = (i % cols) * tw, (i // cols) * (th + 28)
            sheet.paste(im.resize((tw, th)), (x, y + 28))
            draw.text((x + 8, y + 3), f"#{i}  {mmss(t)}  ({t:.1f}s)", fill=(245, 197, 66), font=font)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        sheet.save(out, quality=85)
    return out


def frames(slug: str, times: list[float] | None = None, every: float | None = None, count: int = 16,
           video: str | None = None, tag: str = "source") -> str:
    project = Project(slug)
    src = video or project.source()
    dur = ff.probe(src)["duration"]
    if not times:
        step = every or max(1.0, dur / (count + 1))
        times, t = [], step
        while t < dur and len(times) < 48:
            times.append(round(t, 2))
            t += step
    out = project.path("work", f"frames_{tag}.jpg")
    contact_sheet(src, times, out, cols=4 if len(times) > 6 else len(times), width=360 if len(times) > 6 else 480)
    print(out)
    return out


def snapshot(slug: str, clip_id: str) -> str:
    """Contact sheet of a rendered clip (first second, quarters, CTA) for visual QA."""
    project = Project(slug)
    path = project.path("renders", f"{clip_id}.mp4")
    if not os.path.exists(path):
        path = project.path("renders", f"{clip_id}.draft.mp4")
    d = ff.probe(path)["duration"]
    times = [0.6, d * 0.25, d * 0.5, d * 0.75, max(0.0, d - 1.0)]
    out = project.path("work", f"snap_{clip_id}.jpg")
    contact_sheet(path, times, out, cols=5, width=300)
    print(out)
    return out


def thumbnail(slug: str, t: float, title: str, sub: str = "", size: str = "1080x1920", x: float = 0.5,
              out_name: str | None = None, video: str | None = None) -> str:
    project = Project(slug)
    cfg = load_config()
    W, H = (int(v) for v in size.lower().split("x"))
    src = video or project.source()
    meta = ff.probe(src)
    sw, sh = meta["width"], meta["height"]
    s = max(W / sw, H / sh)
    w2, h2 = int(sw * s) // 2 * 2, int(sh * s) // 2 * 2
    cx = int(max(0, min(w2 - W, w2 * x - W / 2)))

    b = cfg["brand"]
    ab = AssBuilder(W, H, cfg)
    k = min(W, H) / 1080
    big = int((150 if H > W else 175) * k)
    meas = Measurer(cfg["fonts"]["title"], big)
    lines = wrap_text(title, meas, W * 0.9, 3)
    body = "\\N".join(ass_escape(l) for l in lines)
    ty = H * (0.30 if H > W else 0.12)
    anchor = f"\\an8\\pos({W / 2:.0f},{ty:.0f})"
    font = cfg["fonts"]["title"]
    ab.add(0, 10, "Title", f"{{{anchor}\\fn{font}\\fs{big}\\bord{int(22 * k)}\\blur{int(14 * k)}\\3c{hex_to_ass(b['accent'])}"
                          f"\\1a&HFF&\\shad0\\4a&HFF&}}{body}", 0)
    ab.add(0, 10, "Title", f"{{{anchor}\\fn{font}\\fs{big}\\bord{int(8 * k)}\\3c{hex_to_ass(b['outline'])}"
                          f"\\1c{hex_to_ass(b['text'])}\\shad{int(6 * k)}\\4c&H000000&\\4a&H60&}}{body}", 1)
    if sub:
        sy = ty + len(lines) * big * 1.18 + 40 * k
        ab.add(0, 10, "Label", f"{{\\an8\\pos({W / 2:.0f},{sy:.0f})\\fs{int(64 * k)}}}{ass_escape(sub)}", 2)
    ab.watermark(cfg["watermark"].get("text"), 10)

    tdir = project.ensure("thumbs")
    name = out_name or f"thumb_{int(t)}s_{W}x{H}.jpg"
    ass_rel = os.path.join("work", f"{os.path.splitext(name)[0]}.ass")
    project.ensure("work")
    with open(project.path(ass_rel), "w", encoding="utf-8") as f:
        f.write(ab.render())
    fonts_rel = os.path.relpath(FONTS_DIR, project.dir)
    vf = (f"scale={w2}:{h2}:flags=lanczos,crop={W}:{H}:{cx}:{(h2 - H) // 2},eq=contrast=1.08:saturation=1.2:"
          f"brightness=-0.03,vignette=PI/5,ass=filename={ff.filter_path(ass_rel)}:fontsdir={ff.filter_path(fonts_rel)}")
    out_rel = os.path.join("thumbs", name)
    ff.run(["-y", "-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", "1", "-vf", vf, "-q:v", "2", out_rel],
           cwd=project.dir)
    print(os.path.join(tdir, name))
    return os.path.join(tdir, name)
