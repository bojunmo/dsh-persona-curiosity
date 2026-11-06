# -*- coding: utf-8 -*-
"""persona_collector —— 把 QQ 聊天里的人格信号记进人格库

监听每条消息，用规则提取「这个人在意什么」，写进
  $DSH_HOME/persona-curiosity/insights.json

如果这个人的平台身份在 links.json 里有关联（canonical），会打上标记，
方便本地 persona-curiosity 按人聚合。
"""
import json
import os
import re
import uuid
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 信号规则（和 index.js 的 SIGNAL_RULES 保持一致）
SIGNAL_RULES = [
    (r"家人|父母|爸|妈|孩子|老婆|老公|媳妇|儿子|女儿|家庭|孝顺", "重视家庭"),
    (r"钱|工资|房贷|房租|存款|穷|富|赚|省|够用|生活压力|生活费", "在意钱/生活压力"),
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
    """从文本提取人格信号（带否定词排除，前 4 字符）"""
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


@register(
    "persona_collector",
    "鲸鱼娘",
    "把 QQ 聊天里的人格信号记进 persona-curiosity 人格库",
    "0.1.0",
)
class PersonaCollector(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.home = os.environ.get(
            "DSH_HOME", os.path.join(os.path.expanduser("~"), ".dsh")
        )
        self.dir = os.path.join(self.home, "persona-curiosity")
        self.insights_file = os.path.join(self.dir, "insights.json")
        self.links_file = os.path.join(self.dir, "links.json")

    def _load(self, path, default):
        try:
            with open(path, encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _resolve(self, platform, uid):
        """查这个平台身份是否关联到某个 canonical"""
        links = self._load(self.links_file, {"links": []})
        for link in links.get("links", []):
            for ident in link.get("identities", []):
                if (
                    str(ident.get("platform")) == platform
                    and str(ident.get("uid")) == str(uid)
                ):
                    return link.get("canonical")
        return None

    @filter.on_llm_request()
    async def collect(self, event: AstrMessageEvent, req):
        """每条消息都记一次信号（不阻断流程）"""
        try:
            text = (event.message_str or "").strip()
            logger.debug(f"persona_collector: 收到消息 [{text[:20]}] ({len(text)}字)")
            if len(text) < 2:  # 短到没信息量才跳过
                return

            signals = extract_signals(text)
            if not signals:
                return

            sender = event.get_sender_name() or "unknown"
            uid = event.get_sender_id()
            canonical = self._resolve("qq", uid)

            ins = self._load(self.insights_file, {"items": []})
            ins.setdefault("items", []).append(
                {
                    "id": "qq_" + uuid.uuid4().hex[:10],
                    "question": "",
                    "answer": text[:200],
                    "answerer": sender,
                    "signals": signals,
                    "source": "qq" + (f" ({canonical})" if canonical else ""),
                    "canonical": canonical or "",
                    "at": datetime.now().astimezone().isoformat(),
                }
            )
            if len(ins["items"]) > 500:
                ins["items"] = ins["items"][-500:]
            self._save(self.insights_file, ins)
            logger.info(
                f"persona_collector: {sender} → {signals}"
                + (f" (canonical={canonical})" if canonical else "")
            )
        except Exception as e:
            logger.warning(f"persona_collector: {e}")
