"""Deliverables: review.html gallery, per-platform caption files and a posting schedule CSV."""
from __future__ import annotations

import csv
import datetime as dt
import glob
import html
import os

from .config import PLATFORMS, Project, load_config, read_json


def _post_text(pc: dict) -> str:
    parts = []
    if pc.get("title"):
        parts.append(pc["title"])
    if pc.get("caption"):
        parts.append(pc["caption"])
    if pc.get("description"):
        parts.append(pc["description"])
    if pc.get("hashtags"):
        parts.append(" ".join(pc["hashtags"]))
    return "\n\n".join(parts)


def schedule_slots(cfg: dict, n: int, start: dt.date | None = None) -> list[str]:
    """Clip i (plan order = priority) -> datetime. Each day uses the best `per_day` slots
    (posting.slots is in priority order), so the strongest clip lands in prime time on day one."""
    slots = cfg["posting"].get("slots") or ["19:30"]
    per_day = max(1, min(len(slots), int(cfg["posting"].get("per_day", 2))))
    day0 = start or (dt.date.today() + dt.timedelta(days=1))
    out = []
    for i in range(n):
        d = day0 + dt.timedelta(days=i // per_day)
        out.append(f"{d.isoformat()} {slots[i % per_day]}")
    return out


def run(slug: str, start: str | None = None) -> str:
    project = Project(slug)
    cfg = load_config()
    plan = read_json(project.path("plan.json"))
    qa = read_json(project.path("qa.json")) if os.path.exists(project.path("qa.json")) else {"clips": []}
    qa_by = {r["id"]: r for r in qa["clips"]}
    clips = plan["clips"]
    start_date = dt.date.fromisoformat(start) if start else None
    slots = schedule_slots(cfg, len(clips), start_date)

    pub = project.ensure("publish")
    rows, cards = [], []
    for c, slot in zip(clips, slots):
        cid = c["id"]
        copy_path = project.path("copy", f"{cid}.json")
        copy = read_json(copy_path) if os.path.exists(copy_path) else {}
        slot = copy.get("posting_slot") or slot
        video_rel = f"renders/{cid}.mp4"
        thumbs = sorted(glob.glob(project.path("thumbs", f"{cid}_*.jpg")))
        cdir = os.path.join(pub, cid)
        os.makedirs(cdir, exist_ok=True)
        blocks = []
        for p, pc in (copy.get("platforms") or {}).items():
            if p not in (c.get("platforms") or cfg.get("platforms", [])):
                continue
            text = _post_text(pc)
            with open(os.path.join(cdir, f"{p}.txt"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
            rows.append({"slot": slot, "clip": cid, "platform": PLATFORMS.get(p, {}).get("label", p),
                         "video": project.path(video_rel), "text": text})
            blocks.append(f"<div class='post'><div class='ph'><b>{html.escape(PLATFORMS.get(p, {}).get('label', p))}</b>"
                          f"<button onclick=\"navigator.clipboard.writeText(this.parentNode.nextElementSibling.innerText)\">"
                          f"คัดลอก</button></div><pre>{html.escape(text)}</pre></div>")
        q = qa_by.get(cid, {})
        badge = {"pass": "✅ ผ่าน", "warn": "⚠️ มีข้อควรดู", "fail": "❌ ต้องแก้"}.get(q.get("status"), "— ยังไม่ตรวจ")
        issues = "".join(f"<li>[{html.escape(i['level'])}] {html.escape(i['msg'])}</li>" for i in q.get("issues", []))
        thumb_html = "".join(f"<img src='{os.path.relpath(t, project.dir)}'>" for t in thumbs[:2])
        cards.append(f"""
<section class='clip'>
  <div class='media'><video controls preload='metadata' src='{video_rel}'></video>{thumb_html}</div>
  <div class='meta'>
    <h2>{html.escape(cid)} <small>{html.escape(c.get('title', ''))}</small></h2>
    <p class='hook'>{html.escape(c.get('hook', ''))}</p>
    <p>โพสต์: <b>{html.escape(slot)}</b> · QA: {badge}</p>
    <ul class='issues'>{issues}</ul>
    {''.join(blocks) or '<p><i>ยังไม่มีแคปชัน (copy/%s.json)</i></p>' % html.escape(cid)}
  </div>
</section>""")

    rows.sort(key=lambda r: r["slot"])
    missing = [c["id"] for c in clips if not os.path.exists(project.path("renders", f"{c['id']}.mp4"))]
    if missing:
        print(f"WARNING: no final render for: {', '.join(missing)} (run: render {slug} --clip <id>)")
    with open(project.path("schedule.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["slot", "clip", "platform", "video", "text"])
        w.writeheader()
        w.writerows(rows)

    page = f"""<!doctype html><html lang='th'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(slug)} – Clip Review</title>
<style>
:root{{--bg:#0f0a1a;--card:#1b1230;--ink:#f3eefc;--muted:#b9a9d9;--acc:{cfg['brand']['accent']}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:Kanit,system-ui,sans-serif}}
header{{padding:20px 16px;border-bottom:1px solid #2e2150}} h1{{margin:0;font-size:22px}}
main{{max-width:1200px;margin:auto;padding:16px}}
.clip{{display:grid;grid-template-columns:minmax(220px,300px) 1fr;gap:20px;background:var(--card);
border-radius:14px;padding:16px;margin-bottom:18px}}
@media (max-width:700px){{.clip{{grid-template-columns:1fr}}}}
video{{width:100%;border-radius:10px;background:#000}} .media img{{width:48%;margin:6px 1% 0 0;border-radius:6px}}
h2{{margin:0 0 6px;font-size:18px}} small{{color:var(--muted);font-weight:400}}
.hook{{color:var(--acc);font-weight:700}} .issues{{color:var(--muted);font-size:13px}}
.post{{border:1px solid #33245a;border-radius:10px;margin:8px 0}} .ph{{display:flex;justify-content:space-between;
padding:6px 10px;background:#241942;border-radius:10px 10px 0 0}}
pre{{white-space:pre-wrap;margin:0;padding:10px;font-family:inherit;font-size:14px}}
button{{background:var(--acc);border:0;border-radius:6px;padding:3px 10px;cursor:pointer;font-family:inherit}}
</style></head><body><header><h1>{html.escape(cfg.get('channel_name', ''))} · {html.escape(slug)}</h1>
<div style='color:var(--muted)'>{len(clips)} คลิป · schedule.csv · publish/&lt;clip&gt;/&lt;platform&gt;.txt</div></header>
<main>{''.join(cards)}</main></body></html>"""
    out = project.path("review.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(out)
    return out
