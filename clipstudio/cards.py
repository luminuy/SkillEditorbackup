"""Tarot card library lookup (data/cards.json)."""
from __future__ import annotations

import json
import os
from functools import lru_cache

from .config import DATA_DIR


@lru_cache(maxsize=1)
def all_cards() -> list[dict]:
    p = os.path.join(DATA_DIR, "cards.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def get(card_id: str) -> dict | None:
    cid = (card_id or "").strip().lower().replace(" ", "-")
    for c in all_cards():
        if c["id"] == cid or c["name_en"].lower() == card_id.strip().lower():
            return c
    return None


def search(q: str) -> list[dict]:
    q = q.strip().lower()
    out = []
    for c in all_cards():
        hay = " ".join([c["id"], c["name_en"], c["name_th"], " ".join(c.get("upright", [])),
                        " ".join(c.get("reversed", [])), " ".join(c.get("aliases", []))]).lower()
        if q in hay:
            out.append(c)
    return out


def label_text(card_id: str, reversed_: bool = False) -> str:
    c = get(card_id)
    if not c:
        return card_id
    tag = " (กลับหัว)" if reversed_ else ""
    mean = (c.get("reversed") or [""])[0] if reversed_ else c.get("overlay") or (c.get("upright") or [""])[0]
    return f"{c['name_en']}{tag} · {mean}" if mean else f"{c['name_en']}{tag}"


def describe(c: dict) -> str:
    return (f"{c['name_en']} / {c['name_th']} [{c['id']}] ({c.get('arcana')}, {c.get('element', '')})\n"
            f"  upright : {', '.join(c.get('upright', []))}\n"
            f"  reversed: {', '.join(c.get('reversed', []))}\n"
            f"  love    : {c.get('love', '')}\n  money   : {c.get('money_work', '')}\n"
            f"  overlay : {c.get('overlay', '')}")
