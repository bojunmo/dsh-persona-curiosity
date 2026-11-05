"""表情库：收集 + 随机挑一张表情图，用于 B站 评论/私信附图。"""
import hashlib
import json
import os
import random
import urllib.request

EMOTE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emotes")
INDEX = os.path.join(EMOTE_DIR, "index.json")


def _ensure():
    os.makedirs(EMOTE_DIR, exist_ok=True)


def _load_index():
    try:
        with open(INDEX, encoding="utf-8") as f:
            v = json.load(f)
            return v if isinstance(v, list) else []
    except Exception:
        return []


def _save_index(items):
    _ensure()
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_emote(url):
    """下载一张表情图到表情库。返回本地路径或 None。"""
    _ensure()
    if not url or not str(url).startswith("http"):
        return None
    items = _load_index()
    if any(it.get("url") == url for it in items):
        return None
    name = "e_" + hashlib.md5(str(url).encode()).hexdigest()[:12] + ".png"
    path = os.path.join(EMOTE_DIR, name)
    if not os.path.exists(path):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": "https://www.bilibili.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) < 200 or len(data) > 2 * 1024 * 1024:
                return None
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            return None
    items.append({"url": url, "path": path})
    _save_index(items)
    return path


def _list_local(include_gif=False):
    """直接扫描表情目录；默认排除 gif（B站 评论不能发动图）。"""
    _ensure()
    exts = (".png", ".jpg", ".jpeg", ".webp")
    if include_gif:
        exts = exts + (".gif",)
    out = []
    for f in os.listdir(EMOTE_DIR):
        if f.lower().endswith(exts):
            out.append(os.path.join(EMOTE_DIR, f))
    return out


def pick_emote():
    """随机返回一张静态表情图路径（不含 gif），没有则 None。"""
    files = _list_local()
    if not files:
        items = _load_index()
        files = [it.get("path", "") for it in items if os.path.exists(it.get("path", ""))]
    if not files:
        return None
    return random.choice(files)


def count_emotes():
    return len(_list_local(include_gif=True))


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        for u in sys.argv[2:]:
            p = add_emote(u)
            print("added:", p if p else "skip")
    print("emotes:", count_emotes())
