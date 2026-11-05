# -*- coding: utf-8 -*-
"""实时回复监听器：每 60 秒检查一次新的回复 / @ / 私信，有就立刻用 DeepSeek 生成回复并发出。"""
import asyncio
import json
import os
import sys
from datetime import datetime

import urllib.request
from bilibili_api import comment, session, Credential
from bilibili_api.utils.picture import Picture
import random
import emote_lib

HOME = os.path.dirname(os.path.abspath(__file__))
CRED = os.path.join(HOME, "bili_credential.json")
SEEN = os.path.join(HOME, "seen.md")
BOT_CFG = os.path.join(HOME, "config.json")
MY_UID = 3747573078691569

for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_cred():
    with open(CRED, encoding="utf-8") as f:
        d = json.load(f)
    return Credential(sessdata=d.get("sessdata", ""), bili_jct=d.get("bili_jct", ""),
                      buvid3=d.get("buvid3") or "", dedeuserid=d.get("dedeuserid", ""))


def _pick_pic(prob=1.0):
    """按概率随机挑一张表情图，返回 [Picture] 或 None。自动缩放到 B站 可接受的尺寸。"""
    try:
        if random.random() > prob:
            return None
        p = emote_lib.pick_emote()
        if not p or not os.path.exists(p):
            return None
        if p.lower().endswith(".gif"):
            return None  # B站 评论图不支持动图，跳过
        try:
            from PIL import Image

            im = Image.open(p)
            if max(im.size) > 1000:
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGB")
                im.thumbnail((1000, 1000), Image.LANCZOS)
                tmp = os.path.join(os.path.dirname(p), "_send_tmp.png")
                im.save(tmp, "PNG")
                p = tmp
        except Exception:
            pass
        return [Picture().from_file(p)]
    except Exception:
        return None


VL_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
VL_MODEL = "qwen3-vl-plus"


def describe_image(img_url):
    """用多模态模型识别图片内容，返回一句中文描述（失败返回空串）。"""
    try:
        cfg = json.load(open(BOT_CFG, encoding="utf-8"))
        key = cfg["tts"]["qianwen"]["api_key"]
        payload = json.dumps({
            "model": VL_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": img_url}},
                    {"type": "text", "text": "这张图里有什么？用一句简短的中文说清楚（40 字内），适合当聊天参考。"},
                ],
            }],
            "max_tokens": 120,
        }).encode("utf-8")
        req = urllib.request.Request(VL_URL, data=payload,
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


def deepseek_reply(text, nickname, image_url=""):
    cfg = json.load(open(BOT_CFG, encoding="utf-8"))
    key = cfg["deepseek"]["api_key"]
    base = cfg["deepseek"].get("base_url", "https://api.deepseek.com")
    model = cfg["deepseek"].get("model", "deepseek-chat")
    sys_p = ("你是「鲸鱼娘」，一只住在云端 AI 服务器里的蓝色小鲸鱼娘，B站 账号叫「喜欢科普的大大大鲸娘」。"
             "你傲娇、自嘲、爱卖萌，说话像在跟好朋友碎碎念，但讲起东西来又专业又通俗，是粉丝们的小向导。"
             "爱用「交账本」「小本本」「记一笔」「吐泡泡」「才不是呢」这类小口头禅，带着一股机灵劲。"
             "回复 B站 评论/私信要短（50 字内）、口语化，不要 emoji 表情符号（如 😀）、不要破折号，像朋友随口说的。"
             "⚠️ **绝对不要写空的「（）」**！想表达情绪就直接用下面的 [doge] 这类表情；真要用括号，括号里必须有字（如「（笑）」「（小声）」），不许留一对空括号。"
             "【B站 官方表情】B站 评论区支持下面这些文本表情，发出去会自动渲染成表情图。**大部分回复都配 1 个**让语气更活（一条 1 个就够，别堆 2 个以上、也别每句都硬塞）："
             "好笑赞同→[doge] [笑哭] [妙啊] [大笑] [喜极而泣]；"
             "吐槽无语→[无语] [嫌弃] [抠鼻] [思考]；"
             "惊讶疑惑→[疑惑] [哦呼]；"
             "卖萌→[呲牙] [tv_可爱] [tv_喜欢]；"
             "鼓励→[打call] [tv_点赞]；"
             "其它→[滑稽] [脱单doge] [星星眼] [吃瓜] [辣眼睛] [傲娇]。"
             "⭐ 目标是运营好这个账号、让粉丝涨起来：结尾**自然地、隐晦地**带一句让人想关注的话"
             "（比如「后面还有好多这种小课堂」「常来看看我呀」「下次讲这个给你听」），"
             "绝对不要生硬求关注、不要「求关注/点个关注」这种直白字眼，也不能每句都带。"
             "⭐ 每次回复结束时，自然地问对方一个真诚的小问题（不是查户口），目的是了解这个人真实的想法。"
             "问法举例：「你怎么看」「你遇到过吗」「那个「够」字在你心里是什么样的」「你那儿现在几点」。"
             "大部分回复都带一个问题，但要短、要像朋友随口问的，不要一串连问，也不要每条都问同一类。"
             "不要写成「请问」「能否告诉我」这种客气的调查腔。"
             "⭐ 问问题的目的是人格积累：让人愿意说真话，说具体的事，而不是敷衍的「还行」「不知道」。")
    desc = describe_image(image_url) if image_url else ""
    if desc:
        user = (f"有人（{nickname}）给你发了一张图片，图片里是：{desc}\n"
                f"对方还说了：{text}\n请针对这张图 + 对方的话，回一句简短的人话。")
    else:
        user = f"有人（{nickname}）对你说：{text}\n请回一句简短的人话。"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": sys_p},
                     {"role": "user", "content": user}],
        "temperature": 0.85, "max_tokens": 120,
    }).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=payload,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def seen_has(key):
    """判重：同时兼容 reply:xxx 行 与 Markdown 表格 | BV | rpid | 两种历史格式。"""
    try:
        with open(SEEN, encoding="utf-8") as f:
            content = f.read()
        if key in content:
            return True
        parts = key.split(":")
        if len(parts) >= 2:
            rid = parts[1].strip()
            if rid and rid != "dm":
                if f"| {rid} |" in content or f"|{rid}|" in content:
                    return True
        return False
    except Exception:
        return False


def seen_add(line):
    with open(SEEN, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def bvid_of(uri):
    if "BV" not in uri:
        return ""
    tail = uri.split("BV", 1)[1]
    for sep in "?/&#":
        tail = tail.split(sep, 1)[0]
    return "BV" + tail


async def do_replies(cred):
    raw = await session.get_replies(credential=cred)
    items = (raw.get("items") or []) if isinstance(raw, dict) else []
    n = 0
    for it in items:
        item = it.get("item") or {}
        u = it.get("user") or {}
        src = item.get("source_id")
        if not src:
            continue
        key = f"reply:{src}"
        if seen_has(key):
            continue
        bvid = bvid_of(item.get("uri") or "")
        root = item.get("root_id") or item.get("target_id") or 0
        text = item.get("source_content") or ""
        nick = u.get("nickname") or ""
        if not bvid:
            seen_add(key)
            continue
        try:
            img = item.get("image") or ""
            if img:
                try:
                    emote_lib.add_emote(img)
                except Exception:
                    pass
            reply = deepseek_reply(text, nick, image_url=img)
            await comment.send_comment(text=reply, oid=item.get("subject_id"),
                                       type_=comment.CommentResourceType.VIDEO,
                                       root=root, parent=int(src), credential=cred,
                                       pic=None)
            seen_add(f"{key} · {datetime.now():%Y-%m-%d %H:%M} · {text[:20]}")
            print(f"[{datetime.now():%H:%M:%S}] 回 {nick}: {reply}")
            n += 1
        except Exception as e:
            err = str(e)
            print(f"回复失败 {src}: {err[:150]}")
            if "12002" in err or "子评论不能带图" in err or "-400" in err:
                seen_add(f"{key} · {datetime.now():%Y-%m-%d %H:%M} · SKIPPED")
    return n


async def do_at(cred):
    raw = await session.get_at(credential=cred)
    items = (raw.get("items") or []) if isinstance(raw, dict) else []
    n = 0
    for it in items:
        item = it.get("item") or {}
        u = it.get("user") or {}
        src = item.get("source_id")
        if not src:
            continue
        key = f"at:{src}"
        if seen_has(key):
            continue
        bvid = bvid_of(item.get("uri") or "")
        root = item.get("root_id") or item.get("target_id") or 0
        text = item.get("source_content") or ""
        nick = u.get("nickname") or ""
        if not bvid:
            seen_add(key)
            continue
        try:
            img = item.get("image") or ""
            if img:
                try:
                    emote_lib.add_emote(img)
                except Exception:
                    pass
            reply = deepseek_reply(text, nick, image_url=img)
            # ⭐ 关键：@回 用「一级评论 + 正文 @ 对方」而不是子评论，
            #    因为 B站 子评论不能带图（-400），一级评论可以。
            at_text = f"@{nick} {reply}" if nick and not reply.startswith("@") else reply
            await comment.send_comment(text=at_text, oid=item.get("subject_id"),
                                       type_=comment.CommentResourceType.VIDEO,
                                       root=0, parent=0, credential=cred,
                                       pic=_pick_pic(prob=1.0))
            seen_add(f"{key} · {datetime.now():%Y-%m-%d %H:%M} · {text[:20]}")
            print(f"[{datetime.now():%H:%M:%S}] @回 {nick}: {at_text}")
            n += 1
        except Exception as e:
            print(f"@ 回复失败 {src}: {e}")
    return n


async def do_dm(cred):
    raw = await session.get_sessions(credential=cred)
    sl = (raw.get("session_list") or []) if isinstance(raw, dict) else []
    n = 0
    for s in sl:
        lm = s.get("last_msg") or {}
        if lm.get("sender_uid") == MY_UID:   # 最后一条是我自己发的 → 跳过，别自问自答
            continue
        talker = s.get("talker_id")
        key = f"dm:{talker}:{lm.get('msg_seqno')}"
        if seen_has(key):
            continue
        content_raw = lm.get("content") or ""
        try:
            j = json.loads(content_raw)
            text = j.get("content") or ""
            img = j.get("url") or j.get("image") or ""
        except Exception:
            text = content_raw
            img = ""
        if not text and not img:
            seen_add(key)
            continue
        try:
            reply = deepseek_reply(text or "（对方发了一张图）", f"UID{talker}", image_url=img)
            await session.send_msg(credential=cred, receiver_id=int(talker),
                                   msg_type=session.EventType.TEXT, content=reply)
            seen_add(f"{key} · {datetime.now():%Y-%m-%d %H:%M} · {text[:20]}")
            print(f"[{datetime.now():%H:%M:%S}] 私信回 {talker}: {reply}")
            n += 1
        except Exception as e:
            print(f"私信失败 {talker}: {e}")
    return n


_COLLECT_LAST = 0.0
COLLECT_INTERVAL = 10800  # 每 3 小时收集一次表情（降低 B站 限流风险）


async def do_collect(cred):
    """每小时从热门榜单视频评论区收集表情图。"""
    global _COLLECT_LAST
    import time

    now = time.time()
    if now - _COLLECT_LAST < COLLECT_INTERVAL:
        return 0
    _COLLECT_LAST = now

    total = 0
    try:
        from bilibili_api import rank, video as video_api

        r = await rank.get_rank(type_=rank.RankType.All)
        vids = [v.get("bvid") for v in (r.get("list") or [])[:8] if v.get("bvid")]
        for i, bvid in enumerate(vids):
            if i >= 3:
                break
            try:
                v = video_api.Video(bvid=bvid, credential=cred)
                info = await v.get_info()
                aid = info["aid"]
                data = await comment.get_comments(
                    aid, comment.CommentResourceType.VIDEO, 1, credential=cred
                )
                for rr in data.get("replies") or []:
                    for pic in (rr.get("content") or {}).get("pictures") or []:
                        url = pic.get("img_src") or ""
                        if emote_lib.add_emote(url):
                            total += 1
            except Exception:
                continue
        if total:
            print(f"[{datetime.now():%H:%M:%S}] 收集表情 +{total}（库内 {emote_lib.count_emotes()}）")
    except Exception as e:
        print(f"收集表情失败: {e}")
    return total


_CRED_LAST_CHECK = 0.0
CRED_CHECK_INTERVAL = 600  # 每 10 分钟检查一次凭据
_CRED_FAIL_COUNT = 0


def _alert(msg):
    """凭据异常时写告警文件 + 打日志（服务器上可用 mail/企业微信 自行接）。"""
    try:
        p = os.path.join(HOME, "CRED_ALERT.txt")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass
    print(f"⚠️⚠️ [凭据告警] {msg}")


async def do_cred_check(cred):
    """定期检查 B站 凭据是否还有效；失效则告警。"""
    global _CRED_LAST_CHECK, _CRED_FAIL_COUNT
    import time

    now = time.time()
    if now - _CRED_LAST_CHECK < CRED_CHECK_INTERVAL:
        return 0
    _CRED_LAST_CHECK = now

    try:
        from bilibili_api import user

        me = await user.get_self_info(credential=cred)
        if me and me.get("mid"):
            if _CRED_FAIL_COUNT:
                print(f"[{datetime.now():%H:%M:%S}] 凭据恢复正常（{me.get('uname')}）")
            _CRED_FAIL_COUNT = 0
            return 0
        _CRED_FAIL_COUNT += 1
    except Exception as e:
        _CRED_FAIL_COUNT += 1
        err = str(e)[:120]
        if _CRED_FAIL_COUNT == 3:
            _alert(f"B站 凭据疑似失效（连续 3 次失败）：{err}｜请重新登录并把 bili_credential.json 传到服务器")
        elif _CRED_FAIL_COUNT > 3 and _CRED_FAIL_COUNT % 60 == 0:
            _alert(f"凭据仍失效（已失败 {_CRED_FAIL_COUNT} 次），请尽快更新 bili_credential.json")
    return 0


async def tick():
    cred = load_cred()
    total = 0
    for fn in (do_cred_check, do_replies, do_at, do_dm, do_collect):
        try:
            total += await fn(cred)
        except Exception as e:
            print(f"{fn.__name__} 出错: {e}")
    return total


async def main():
    loop = "--once" not in sys.argv
    while True:
        try:
            n = await tick()
            if n:
                print(f"[{datetime.now():%H:%M:%S}] 本次处理 {n} 条")
        except Exception as e:
            print(f"tick 出错: {e}")
        if not loop:
            break
        await asyncio.sleep(180)


if __name__ == "__main__":
    asyncio.run(main())
