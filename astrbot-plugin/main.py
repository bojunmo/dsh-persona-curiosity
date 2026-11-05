"""
intent_guard —— 意图守卫 + 主动提问

两件事：
1. 私聊/群聊里，判断"这条消息是不是在问机器人"。不是就不回（省 token、不打扰）。
2. 定时从 persona-curiosity 的问题队列里取一条，主动发出去问人（人格积累）。

原理：
- 用 on_llm_request 往上下文里塞一条判定提示，让模型先决定"要不要回"。
- 用 on_llm_response 拦住回复：模型回 [SKIP] 就不发。
- 主动提问用定时任务，读 $DSH_HOME/persona-curiosity/questions.json。

注意：QQ 官方机器人**群聊只能收到 @ 消息**（平台限制）。私聊能收到全部消息。
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, register

SKIP_MARK = "[SKIP]"

HOME = os.path.expanduser("~")
CURIOSITY_DIR = os.path.join(os.environ.get("DSH_HOME", os.path.join(HOME, ".dsh")), "persona-curiosity")
QUESTIONS_FILE = os.path.join(CURIOSITY_DIR, "questions.json")


def _load_questions():
    try:
        if not os.path.exists(QUESTIONS_FILE):
            return {"items": []}
        with open(QUESTIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"items": []}


def _pending_questions():
    data = _load_questions()
    return [q for q in data.get("items", []) if q.get("status") == "pending"]


def _mark_asked(qid):
    try:
        data = _load_questions()
        for q in data.get("items", []):
            if q.get("id") == qid and q.get("status") == "pending":
                q["status"] = "asked"
                q["asked"] = datetime.now().isoformat()
                break
        os.makedirs(CURIOSITY_DIR, exist_ok=True)
        tmp = QUESTIONS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, QUESTIONS_FILE)
        return True
    except Exception as e:
        logger.warning(f"intent_guard: mark asked failed: {e}")
        return False


@register(
    "intent_guard",
    "鲸鱼娘",
    "判断消息是否在问机器人 + 主动提问积累人格",
    "0.1.0",
)
class IntentGuard(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._ask_task = None
        self._last_ask = 0.0
        # 主动提问间隔（秒）：默认 2 小时
        self.ask_interval = 7200
        # 每天最多主动问几次
        self.daily_limit = 3
        self._today = ""
        self._today_count = 0

    async def initialize(self):
        """插件加载后启动主动提问的后台任务。"""
        if self._ask_task is None or self._ask_task.done():
            self._ask_task = asyncio.create_task(self._ask_loop())
            logger.info("intent_guard: 主动提问任务已启动")

    async def _ask_loop(self):
        """后台循环：间隔到了一天限内，就从队列里取一个问题发出去。"""
        while True:
            try:
                await asyncio.sleep(300)  # 每 5 分钟检查一次
                now = time.time()
                today = datetime.now().strftime("%Y-%m-%d")
                if today != self._today:
                    self._today = today
                    self._today_count = 0

                if now - self._last_ask < self.ask_interval:
                    continue
                if self._today_count >= self.daily_limit:
                    continue

                pend = _pending_questions()
                if not pend:
                    continue

                q = random.choice(pend)
                # 找目标会话：优先最近活跃的（这里简单用第一个可用平台）
                sent = await self._send_question(q)
                if sent:
                    _mark_asked(q["id"])
                    self._last_ask = now
                    self._today_count += 1
                    logger.info(f"intent_guard: 主动提问 「{q['question']}」")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"intent_guard ask loop: {e}")

    async def _send_question(self, q):
        """把问题发出去。优先发到最近有互动的会话。"""
        try:
            # AstrBot 的 Star 没有直接"广播"能力，用平台管理器找会话
            pm = self.context.platform_manager
            platforms = getattr(pm, "platform_insts", [])
            if not platforms:
                return False

            # 用 curiosity 里记录的 target 选平台：owner=私聊，其他=群
            for p in platforms:
                try:
                    # 尽量找最近活跃会话；拿不到就跳过
                    sessions = getattr(p, "recent_sessions", None) or getattr(p, "sessions", None)
                    if not sessions:
                        continue
                    sess_id = list(sessions.keys())[0] if isinstance(sessions, dict) else None
                    if not sess_id:
                        continue
                    await p.send_message(sess_id, q["question"])
                    return True
                except Exception:
                    continue
            return False
        except Exception as e:
            logger.warning(f"intent_guard send question: {e}")
            return False

    @filter.on_llm_request()
    async def add_intent_hint(self, event: AstrMessageEvent, req):
        """在 LLM 请求前加一条判定提示：要不要回这条消息。"""
        try:
            text = event.message_str or ""
            # 群聊里没有被 @ 的消息（理论上收不到），私聊是全部
            hint = (
                "\n\n【回复判定】先判断这条消息是不是在跟你说话 / 问你问题：\n"
                "- 是在问你（提问、求助、接你的话、直接叫你）→ 正常回复\n"
                "- 不是（自言自语、在对别人说、无意义灌水、纯表情）→ 只输出 "
                + SKIP_MARK
                + "，不要输出任何别的字\n"
            )
            # 往 system prompt 追加
            if hasattr(req, "system_prompt"):
                req.system_prompt = (req.system_prompt or "") + hint
        except Exception:
            pass

    @filter.on_llm_response()
    async def filter_skip(self, event: AstrMessageEvent, response: LLMResponse):
        """如果模型判定不回（[SKIP]），就清空回复并阻止发送。"""
        try:
            text = (response.completion_text or "").strip()
            if text == SKIP_MARK or text.startswith(SKIP_MARK):
                response.completion_text = ""
                # 阻止这条回复发出去
                event.stop_event()
                logger.debug("intent_guard: 判定不回，已跳过")
        except Exception:
            pass
