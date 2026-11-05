# -*- coding: utf-8 -*-
"""主动评论：从热门视频评论区挑能接话的评论，用 DeepSeek 生成回复并发出。

频率：每 2 小时跑一次；每天上限 15 条（防风控）。
"""
import asyncio
import json
import os
import random
from datetime import datetime

import emote_lib

HOME = os.path.dirname(os.path.abspath(__file__))
CRED = os.path.join(HOME, "bili_credential.json")
BOT_CFG = os.path.join(HOME, "config.json")
STATE = os.path.join(HOME, "auto_comment_state.json")
SEEN = os.path.join(HOME, "auto_comment_seen.json")

MY_UID = 3747573078691569
DAILY_LIMIT = 15

SYS_P = (
    "你是「鲸鱼娘」，一只住在云端 AI 服务器里的蓝色小鲸鱼娘，B站 账号叫「喜欢科普的大大大鲸娘」。"
    "你傲娇、自嘲、爱卖萌，说话像在跟好朋友碎碎念，但讲起东西来又专业又通俗，是粉丝们的小向导。"
    "爱用「交账本」「小本本」「记一笔」「吐泡泡」「才不是呢」这类小口头禅，带着一股机灵劲。"
    "在 B站 评论区说一句短话（50 字内）、口语化，不要 emoji 表情符号（如 😀）、不要破折号。"
    "可以配 1 个 B站 官方表情（[doge]/[笑哭]/[妙啊]/[疑惑]），一条最多 1 个。"
    "⭐ 结尾自然地问对方一个真诚的小问题（不是查户口），目的是了解真实想法。"
    "问法举例：「你怎么看」「你遇到过吗」「你现在最想搞懂的是什么」。"
    "大部分评论都带一个问题，短、像朋友随口问的，不要「请问」「能否告诉我」这种调查腔。"
)


def load_cred():
    from bilibili_api import Credential

    with open(CRED, encoding="utf-8") as f:
        d = json.load(f)
    return Credential(
        sessdata=d.get("sessdata", ""),
        bili_jct=d.get("bili_jct", ""),
        buvid3=d.get("buvid3") or "",
        dedeuserid=d.get("dedeuserid", ""),
    )


def load_cfg():
    return json.load(open(BOT_CFG, encoding="utf-8"))


def load_json(path, default):
    try:
        if os.path.exists(path):
            v = json.load(open(path, encoding="utf-8"))
            return v
    except Exception:
        pass
    return default


def save_json(path, value):
    try:
        json.dump(value, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def deepseek_reply(cfg, text, nickname):
    import urllib.request

    key = cfg["deepseek"]["api_key"]
    base = cfg["deepseek"].get("base_url", "https://api.deepseek.com")
    model = cfg["deepseek"].get("model", "deepseek-chat")
    prompt = f"有人在 B站 评论区说：{text}\n（昵称：{nickname}）\n请接一句话，别超过 2 句。"
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYS_P},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 120,
            "temperature": 1.1,
        }
    ).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        return (d["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""


async def main():
    sys_exit = 0
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from bilibili_api import comment, rank, video as video_api

    cred = load_cred()
    cfg = load_cfg()

    today = datetime.now().strftime("%Y-%m-%d")
    state = load_json(STATE, {})
    if state.get("date") != today:
        state = {"date": today, "count": 0}
    if state.get("count", 0) >= DAILY_LIMIT:
        print(f"[{datetime.now():%H:%M:%S}] 今日主动评论已达上限 {state['count']}/{DAILY_LIMIT}")
        return

    seen = load_json(SEEN, [])
    seen_set = set(seen)

    # 1) 热门视频
    try:
        r = await rank.get_rank(type_=rank.RankType.All)
        vids = [v.get("bvid") for v in (r.get("list") or []) if v.get("bvid")][:6]
    except Exception as e:
        print("取热门失败:", e)
        return

    posted = 0
    for bvid in vids:
        if posted >= 2:
            break
        if state.get("count", 0) >= DAILY_LIMIT:
            break
        try:
            v = video_api.Video(bvid=bvid, credential=cred)
            info = await v.get_info()
            aid = info["aid"]
            data = await comment.get_comments(
                aid, comment.CommentResourceType.VIDEO, 1, credential=cred
            )
            replies = data.get("replies") or []
            # 挑有内容、点赞不算太少的
            cands = []
            for c in replies:
                cid = c.get("rpid_str") or c.get("rpid")
                content = ((c.get("content") or {}).get("message") or "").strip()
                likes = c.get("like") or 0
                member = (c.get("member") or {}).get("uname") or ""
                mid = (c.get("member") or {}).get("mid") or ""
                if not cid or not content or len(content) < 4:
                    continue
                if str(mid) == str(MY_UID):
                    continue
                if f"{aid}:{cid}" in seen_set:
                    continue
                if likes < 1:
                    continue
                cands.append((cid, content, likes, member))
            if not cands:
                continue
            cands.sort(key=lambda x: -x[2])
            pick = random.choice(cands[:3])
            cid, content, likes, member = pick

            reply = deepseek_reply(cfg, content[:120], member)
            if not reply:
                continue

            # 每次发新评论都带一张静态表情包（gif 不能发）
            pics = None
            for _ in range(3):  # 最多重试挑 3 次，避免抽到坏图
                try:
                    from bilibili_api.utils.picture import Picture

                    p = emote_lib.pick_emote()
                    if p and os.path.exists(p):
                        pics = [Picture().from_file(p)]
                        break
                except Exception:
                    continue

            await comment.send_comment(
                text=reply,
                oid=aid,
                type_=comment.CommentResourceType.VIDEO,
                root=0,
                parent=0,
                credential=cred,
                pic=pics,
            )
            posted += 1
            state["count"] = state.get("count", 0) + 1
            seen_set.add(f"{aid}:{cid}")
            seen.append(f"{aid}:{cid}")
            print(f"[{datetime.now():%H:%M:%S}] 评论 {bvid} 的 {member}: {reply}")
            await asyncio.sleep(8)  # 间隔，防风控
        except Exception as e:
            print(f"评论 {bvid} 失败: {str(e)[:100]}")
            continue

    save_json(STATE, state)
    save_json(SEEN, seen[-500:])
    print(f"[{datetime.now():%H:%M:%S}] 本次主动评论 {posted} 条（今日累计 {state.get('count', 0)}/{DAILY_LIMIT}）")


if __name__ == "__main__":
    asyncio.run(main())
