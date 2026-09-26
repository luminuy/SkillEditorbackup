"""Technical + policy QA of rendered clips and their post copy."""
from __future__ import annotations

import os
import re

from . import ff
from .analyze import RISK_PATTERNS
from .config import FORMATS, PLATFORMS, Project, load_config, read_json, write_json


def check_clip(project: Project, clip: dict, cfg: dict) -> dict:
    cid = clip["id"]
    path = project.path("renders", f"{cid}.mp4")
    issues: list[dict] = []

    def add(level, msg):
        issues.append({"level": level, "msg": msg})

    platforms = clip.get("platforms") or cfg.get("platforms", [])
    if not os.path.exists(path):
        draft = project.path("renders", f"{cid}.draft.mp4")
        if not os.path.exists(draft):
            add("fail", "not rendered yet — run: render <slug> --clip " + cid)
            _check_copy(project, clip, cfg, platforms, add)
            return {"id": cid, "status": "fail", "issues": issues}
        add("fail", "only a DRAFT exists (low quality) — render the final: render <slug> --clip " + cid)
        path = draft

    info = ff.probe(path)
    W, H = FORMATS[clip.get("format", "vertical")]
    if (info["width"], info["height"]) != (W, H):
        add("fail", f"resolution {info['width']}x{info['height']} != {W}x{H}")
    if info["vcodec"] != "h264":
        add("fail", f"video codec {info['vcodec']} (want h264)")
    if not info["has_audio"]:
        add("fail", "no audio track")
    elif info["acodec"] != "aac":
        add("warn", f"audio codec {info['acodec']} (want aac)")
    if info["fps"] and not (23 <= info["fps"] <= 61):
        add("warn", f"unusual fps {info['fps']}")
    size_mb = os.path.getsize(path) / 1e6
    if size_mb > 250:
        add("warn", f"file is {size_mb:.0f} MB (some apps reject > 250 MB)")

    dur = info["duration"]
    fmt = clip.get("format", "vertical")
    for p in platforms:
        spec = PLATFORMS.get(p)
        if not spec or spec["format"] != fmt:
            continue
        if dur > spec["max_seconds"]:
            add("fail", f"{spec['label']}: {dur:.1f}s is over the {spec['max_seconds']}s limit")
        lo, hi = spec["sweet_spot"]
        if not lo <= dur <= hi:
            add("info", f"{spec['label']}: {dur:.1f}s is outside the {lo}-{hi}s sweet spot")

    loud = ff.loudness(path)
    target = cfg["audio"]["target_lufs"]
    if "integrated" in loud and abs(loud["integrated"] - target) > 1.5:
        add("warn", f"loudness {loud['integrated']:.1f} LUFS (target {target})")
    if loud.get("true_peak", -99) > -0.5:
        add("warn", f"true peak {loud['true_peak']:.1f} dBFS (clipping risk)")

    sil = ff.silences(path, -40, 0.6)
    if sil and sil[0]["start"] < 0.1:
        add("warn", f"dead air at the start ({(sil[0]['end'] or 0):.1f}s) — the first second must hook")
    long_sil = [s for s in sil if s["end"] and s["end"] - s["start"] > 1.5]
    if long_sil:
        add("info", f"{len(long_sil)} pause(s) > 1.5s remain")

    if not clip.get("hook"):
        add("warn", "no on-screen hook text")

    _check_copy(project, clip, cfg, platforms, add)

    status = "fail" if any(i["level"] == "fail" for i in issues) else "warn" if any(
        i["level"] == "warn" for i in issues) else "pass"
    return {"id": cid, "status": status, "duration": round(dur, 2), "loudness": loud, "issues": issues}


def _check_copy(project: Project, clip: dict, cfg: dict, platforms: list[str], add) -> None:
    cid = clip["id"]
    copy_path = project.path("copy", f"{cid}.json")
    if not os.path.exists(copy_path):
        add("warn", "no post copy yet (copy/<id>.json)")
        return
    copy = read_json(copy_path)
    blob = " ".join(_strings(copy))
    for pat, why in RISK_PATTERNS:
        if re.search(pat, blob):
            add("warn", f"post copy contains risky wording: {why}")
    have = set((copy.get("platforms") or {}).keys())
    missing = [p for p in platforms if p not in have]
    if missing:
        add("warn", f"post copy missing for: {', '.join(missing)}")
    for p, pc in (copy.get("platforms") or {}).items():
        spec = PLATFORMS.get(p, {})
        tags = pc.get("hashtags") or []
        if spec.get("hashtags") and len(tags) > spec["hashtags"][1]:
            add("info", f"{p}: {len(tags)} hashtags (recommended {spec['hashtags'][0]}-{spec['hashtags'][1]})")
        low = [t.lower() for t in tags]
        if len(low) != len(set(low)):
            add("warn", f"{p}: duplicate hashtags")
        title = pc.get("title") or ""
        if "#shorts" in title.lower() and "#shorts" in low:
            add("info", f"{p}: #shorts appears in both title and hashtags (shows twice)")
        if spec.get("title_limit") and len(title) > spec["title_limit"]:
            add("fail", f"{p}: title {len(title)} chars > {spec['title_limit']}")
        cap = (pc.get("caption") or "") + " " + (pc.get("description") or "") + " " + " ".join(tags)
        if spec.get("caption_limit") and len(cap) > spec["caption_limit"]:
            add("fail", f"{p}: caption {len(cap)} chars > {spec['caption_limit']}")
    if cfg.get("niche") == "tarot" and not re.search(r"วิจารณญาณ|ความบันเทิง|แนวทาง|entertainment", blob):
        add("info", "no disclaimer line in post copy (recommended for tarot content)")


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def run(slug: str, only: list[str] | None = None) -> dict:
    project = Project(slug)
    cfg = load_config()
    plan = read_json(project.path("plan.json"))
    results = [check_clip(project, c, cfg) for c in plan["clips"] if not only or c["id"] in only]
    report = {"project": slug, "clips": results,
              "summary": {s: sum(1 for r in results if r["status"] == s) for s in ("pass", "warn", "fail")}}
    write_json(project.path("qa.json"), report)
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    lines = [f"# QA {slug}: {report['summary']}"]
    for r in results:
        lines.append(f"{icon[r['status']]} {r['id']} ({r.get('duration', '-')}s, "
                     f"{r.get('loudness', {}).get('integrated', '-')} LUFS)")
        lines += [f"    [{i['level']}] {i['msg']}" for i in r["issues"]]
    with open(project.path("qa.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return report
