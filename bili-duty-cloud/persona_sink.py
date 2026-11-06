# -*- coding: utf-8 -*-
"""persona_sink —— 把 B站 互动里的人格信号记进 bili_insights.json

用法（在 reply_watcher.py / auto_comment.py 里调用）：
    import persona_sink
    persona_sink.record("某粉丝昵称", "对方说的话", "bilibili comment")
"""
import json
import os
import re
import uuid
from datetime import datetime

HOME = os.path.dirname(os.path.abspath(__file__))
INSIGHTS = os.path.join(HOME, "bili_insights.json")

# 和 persona_collector 保持一致的信号规则
SIGNAL_RULES = [
    (r"家人|父母|爸|妈|孩子|老婆|老公|媳妇|儿子|女儿|家庭|孝顺", "重视家庭"),
    (r"钱|工资|房贷|房租|存款|穷|富|赚|省|够用|生活压力|生活费|养家", "在意钱/生活压力"),
    (r"努力|拼|卷|加班|奋斗|坚持|不服输|上进|学|咬牙|死磕", "努力/不服输"),
    (r"躺平|摆烂|累了|疲惫|不想动|没劲|佛系|累死|好累|太累|累成|好困|困死|想睡|歇会|喘口气|撑不住|累趴", "躺平/疲惫"),
    (r"技术|代码|编程|AI|算法|程序|开发|开源|debug|Bug", "爱技术"),
    (r"游戏|打游戏|Steam|原神|王者|LOL|开黑|手游|上分", "爱游戏"),
    (r"朋友|兄弟|闺蜜|感情|喜欢|恋爱|分手|在一起|爱人|想他|想她|舍不得", "重感情"),
    (r"现实|社会|人性|生存|残酷|内卷|内耗|认命", "现实"),
    (r"孤独|一个人|寂寞|没人|孤单|独处|无人|孤立|空荡荡", "孤独"),
    (r"为什么|想知道|好奇|原理|搞不懂|研究|原因|怎么回事", "好奇心"),
    (r"烦|焦虑|压力大|难受|崩溃|不开心|郁闷|憋屈|心累|慌|怕", "压力/负面情绪"),
]

NEGATIONS = [
    "不", "没", "别", "无", "未", "不怎么", "不太", "没有",
    "不是", "不想", "不再", "没在", "不会", "从没", "从不",
]


def extract_signals(text):
    if not text:
        return []
    found = []
    for pattern, signal in SIGNAL_RULES:
        for m in re.finditer(pattern, text):
            head = text[max(0, m.start() - 4):m.start()]
            if any(neg in head for neg in NEGATIONS):
                continue
            if signal not in found:
                found.append(signal)
            break
    return found


def _load():
    try:
        with open(INSIGHTS, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {"items": []}


def _save(data):
    tmp = INSIGHTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INSIGHTS)


def record(answerer, text, source="bilibili"):
    """提取信号并写入。返回写入的信号列表（空表示没匹配上）。"""
    text = (text or "").strip()
    if len(text) < 2:
        return []
    signals = extract_signals(text)
    if not signals:
        return []

    data = _load()
    data.setdefault("items", []).append({
        "id": "bili_" + uuid.uuid4().hex[:10],
        "question": "",
        "answer": text[:200],
        "answerer": answerer or "unknown",
        "signals": signals,
        "source": source,
        "canonical": "",
        "at": datetime.now().astimezone().isoformat(),
    })
    if len(data["items"]) > 500:
        data["items"] = data["items"][-500:]
    _save(data)
    return signals
