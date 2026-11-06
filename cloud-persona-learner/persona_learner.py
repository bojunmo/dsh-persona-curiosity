# -*- coding: utf-8 -*-
"""persona_learner —— 云端自动刷 B站，学习网络用语，扩充人格提示词

每天跑 2 次（由 systemd timer 触发）：
  1. 用 bilibili_api 搜索热门视频（多个关键词轮流）
  2. 抓取视频评论
  3. 交给 DeepSeek 提取「网络用语/黑话/梗/口头禅」
  4. 对比人格里已有的词，只加新词
  5. 追加到 AstrBot 的 personas 表
  6. 写日志（可回滚）

为什么用 DeepSeek：简单的 n-gram 提取出来全是句子碎片（「鼻屎弄得」「白菜对我」），
不可用。DeepSeek 能理解上下文，只挑真正的网络用语。

安全阀：
  - 每次最多加 MAX_WORDS 个
  - 人格总长 <= MAX_PERSONA_CHARS
  - 黑名单过滤
  - 日志记录每次的增量（/opt/persona-learner/learn.log）
"""
import asyncio
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────
BIli_DIR = "/opt/bili-duty"
CRED_FILE = os.path.join(BIli_DIR, "bili_credential.json")
BILLI_CONFIG = os.path.join(BIli_DIR, "config.json")
DB = "/opt/astrbot/data/data_v4.db"
PERSONA_ID = "whale"
LOG_DIR = "/opt/persona-learner"
LOG_FILE = os.path.join(LOG_DIR, "learn.log")

KEYWORDS = [
    "网络热梗 2026",
    "2026 流行语",
    "B站 热梗 盘点",
    "群聊 黑话",
    "2026 新手机 评测",
    "游戏 新版本 2026",
    "动漫 新番 2026",
]

MAX_WORDS = 20
MAX_PERSONA_CHARS = 6000
COMMENTS_PER_VIDEO = 20
VIDEOS_PER_RUN = 3
MAX_COMMENTS_FOR_LLM = 120


def log(msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_bili_config():
    with open(BILLI_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def load_credential():
    with open(CRED_FILE, encoding="utf-8") as f:
        return json.load(f)


async def fetch_comments(keyword):
    """搜视频 + 取评论"""
    sys.path.insert(0, BIli_DIR)
    from bilibili_api import comment, search, Credential

    d = load_credential()
    cred = Credential(
        sessdata=d["sessdata"],
        bili_jct=d["bili_jct"],
        buvid3=d.get("buvid3", ""),
        dedeuserid=d["dedeuserid"],
    )

    texts = []
    try:
        res = await search.search_by_type(
            keyword, search_type=search.SearchObjectType.VIDEO, page=1
        )
        videos = (res.get("result") or [])[:VIDEOS_PER_RUN]
    except Exception as e:
        log(f"搜索失败 {keyword}: {str(e)[:80]}")
        return texts

    for v in videos:
        bvid = v.get("bvid")
        if not bvid:
            continue
        try:
            cmts = await comment.get_comments(
                oid=bvid,
                type_=comment.CommentResourceType.VIDEO,
                page_index=1,
                credential=cred,
            )
            for c in (cmts.get("replies") or [])[:COMMENTS_PER_VIDEO]:
                txt = c.get("content", {}).get("message", "")
                if txt:
                    texts.append(txt)
            log(f"  {bvid} 取到 {len(cmts.get('replies') or [])} 条")
        except Exception as e:
            log(f"  {bvid} 失败: {str(e)[:60]}")
    return texts


def deepseek_extract(comments):
    """让 DeepSeek 从评论里挑出真正的网络用语"""
    cfg = load_bili_config()
    key = cfg["deepseek"]["api_key"]
    base = cfg["deepseek"].get("base_url", "https://api.deepseek.com")
    model = cfg["deepseek"].get("model", "deepseek-chat")

    sample = "\n".join(comments[:MAX_COMMENTS_FOR_LLM])
    prompt = f"""从下面这些B站评论里，挑出真正的**网络用语 / 黑话 / 梗 / 口头禅**。

要求：
1. 只要短词（2-6 字），比如「绷不住了」「难绷」「典」「麻了」「闹麻了」「夯」「真香」
2. 不要普通词汇（「今天」「吃饭」「不知道」「为什么」）
3. 不要句子碎片（比如「鼻屎弄得」「白菜对我」这种半截话）
4. 只要你在评论区真见过、有辨识度的
5. 最多 20 个
6. 只返回 JSON 数组，不要解释，格式：["词1","词2"]

评论：
{sample}"""

    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        # 提取 JSON 数组
        m = re.search(r"\[[\s\S]*?\]", content)
        if not m:
            log(f"DeepSeek 输出不是 JSON: {content[:100]}")
            return []
        words = json.loads(m.group(0))
        # 校验
        clean = []
        for w in words:
            if not isinstance(w, str):
                continue
            w = w.strip()
            if 2 <= len(w) <= 6 and re.fullmatch(r"[\u4e00-\u9fa5a-zA-Z]+", w):
                clean.append(w)
        return clean
    except Exception as e:
        log(f"DeepSeek 调用失败: {str(e)[:100]}")
        return []


def update_persona(words):
    """把新词追加到人格"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    row = cur.execute(
        "SELECT system_prompt FROM personas WHERE persona_id=?", (PERSONA_ID,)
    ).fetchone()
    if not row:
        conn.close()
        return 0, 0, []
    base = row[0]
    old_len = len(base)

    added = []
    for w in words:
        if w in base or w in added:
            continue
        added.append(w)
        if len(added) >= MAX_WORDS:
            break

    if not added:
        conn.close()
        return old_len, old_len, []

    block = (
        f"\n\n-[自动学习 {datetime.now().strftime('%Y-%m-%d')}]\n"
        + " / ".join(added)
    )
    new = base + block
    if len(new) > MAX_PERSONA_CHARS:
        log(f"人格将超过 {MAX_PERSONA_CHARS} 字，跳过")
        conn.close()
        return old_len, old_len, []

    cur.execute(
        "UPDATE personas SET system_prompt=? WHERE persona_id=?", (new, PERSONA_ID)
    )
    conn.commit()
    conn.close()
    return old_len, len(new), added


async def main():
    log("=" * 50)
    log("开始学习")

    all_comments = []
    for kw in KEYWORDS:
        texts = await fetch_comments(kw)
        all_comments.extend(texts)
        log(f"关键词「{kw}」→ {len(texts)} 条")

    if not all_comments:
        log("没抓到评论，退出")
        return

    log(f"共 {len(all_comments)} 条评论，交给 DeepSeek 提取")
    words = deepseek_extract(all_comments)
    log(f"DeepSeek 提取到 {len(words)} 个词: {words}")

    old_len, new_len, added = update_persona(words)
    if added:
        log(f"人格: {old_len} → {new_len} (+{new_len - old_len} 字)")
        log(f"加入: {' / '.join(added)}")
    else:
        log("没有新词可加")


if __name__ == "__main__":
    asyncio.run(main())
