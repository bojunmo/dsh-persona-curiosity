# -*- coding: utf-8 -*-
"""intent_guard —— 判断 QQ 消息要不要回 + 主动提问积累人格

功能：
  1. on_llm_request：给 LLM 加一条「要不要回」的判定提示
  2. on_llm_response：模型回 [SKIP] 就不发
  3. 后台定时：每 30 分钟从问题池挑一个发到群里（每天最多 12 次）

问题来源（按优先级）：
  1. $DSH_HOME/persona-curiosity/questions.json 里 status=pending 的问题
  2. 内置问题池（30 个）——云端没有 questions.json 时用这个

发送方式：直接调 NapCat 的 HTTP API（http://127.0.0.1:3000/send_group_msg）
"""
import asyncio
import json
import os
import random
import time
import urllib.request
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

SKIP_MARK = "[SKIP]"

# 目标：默认发到「欧鲸鲸的大鱼塘」
GROUP_ID = 1134833735
NAPCAT_API = "http://127.0.0.1:3000"

HOME = os.environ.get("DSH_HOME", os.path.join(os.path.expanduser("~"), ".dsh"))
CURIOSITY_DIR = os.path.join(HOME, "persona-curiosity")
QUESTIONS_FILE = os.path.join(CURIOSITY_DIR, "questions.json")

# 内置问题池（问人格的，不查户口）
QUESTIONS_POOL = [
    "你最近一次觉得「这事值了」是什么时候？",
    "你现在最想搞懂的一件事是什么？",
    "如果明天不用上班，你会干嘛？",
    "你有没有过「明明很累但就是不想睡」的时候？",
    "你最近一次被人说「你想多了」是什么情况？",
    "你觉得「活得舒服」和「活得体面」，哪个更让你在意？",
    "你上一次特别想找个人说话，是因为什么？",
    "你怎么判断一个人值不值得深交？",
    "你最近有没有为了什么事「忍」下来？",
    "如果让你给三年前的自己一句话，你会说什么？",
    "你觉得自己身上最像父母的地方是什么？",
    "你最近一次「破防」是因为什么？",
    "你更怕「做错」还是「错过」？",
    "你有没有一件事，坚持了很久但其实没什么用？",
    "你怎么花钱最不心疼？",
    "你最近有没有突然想起很久以前的人？",
    "你觉得「被理解」和「被需要」，哪个更难得到？",
    "你上一次认真夸别人是什么时候？",
    "你有没有那种「说不上好但就是离不开」的习惯？",
    "你最近一次觉得「我不属于这里」是什么场合？",
    "你心里有没有一个「以后一定要做」的事？",
    "你怎么看「躺平」这个词？",
    "你最近有没有因为一句话高兴一整天的经历？",
    "你觉得自己最大的缺点是啥？",
    "你有没有那种「明明不想去但还是去了」的饭局？",
    "你上一次哭是因为什么？",
    "你觉得人到了什么年纪，就不该再折腾了？",
    "你有没有一件「说出来怕被笑」的梦想？",
    "你最近一次觉得「时间过得真快」是什么时候？",
    "如果现在能立刻拥有一项技能，你选什么？",
]


# 提取问题关键词（用于判断「有没有人回答问题」）
_STOPWORDS = set([
    "什么", "怎么", "为什么", "哪个", "一次", "觉得", "时候",
    "如果", "你会", "你了", "会选", "一下", "自己", "有没有",
    "是不是", "能不能", "可不可以", "什么时候", "这个", "那个",
])


def extract_keywords(question):
    """从问题里提取实词（先按标点/符号分割，再过滤虚词）"""
    if not question:
        return []
    # 先按标点、空格、引号等分割
    parts = re.split(
        r"[，。？！、；：「」『』（）()\[\]【】\s,\.\?!/\\|~～“”\"']+", question
    )
    words = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2 and p not in _STOPWORDS:
            words.append(p)
    return words


def _load_questions():
    try:
        with open(QUESTIONS_FILE, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {"items": []}


def _pending_questions():
    """先读 questions.json 的 pending，没有就用内置池"""
    data = _load_questions()
    pend = [q for q in data.get("items", []) if q.get("status") == "pending"]
    if pend:
        return pend
    # 内置池：转成统一格式
    return [{"id": f"builtin_{i}", "question": q, "builtin": True} for i, q in enumerate(QUESTIONS_POOL)]


def _mark_asked(qid):
    """标记 questions.json 里的问题（内置的不需要标记）"""
    if str(qid).startswith("builtin_"):
        return
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
    except Exception as e:
        logger.warning(f"intent_guard: mark asked 失败 {e}")


@register("intent_guard", "鲸鱼娘", "判断 QQ 消息要不要回 + 主动提问积累人格", "0.2.0")
class IntentGuard(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._ask_task = None
        self._last_ask = 0.0
        # 主动提问间隔（秒）：30 分钟
        self.ask_interval = 1800
        # 每天最多问几次
        self.daily_limit = 12
        self._today = ""
        self._today_count = 0
        self._used_builtin = set()  # 今天用过的内置问题（避免重复）
        # 当前「问了但还没人回」的问题。存在时不再问新的，直到有人回或第二天
        self._awaiting_question = None
        # 这个问题的关键词（用来判断消息是否「真的在回答它」）
        self._awaiting_keywords = []

    async def initialize(self):
        if self._ask_task is None or self._ask_task.done():
            self._ask_task = asyncio.create_task(self._ask_loop())
            logger.info("intent_guard: 主动提问任务已启动（30分钟/12次/天）")

    async def _ask_loop(self):
        while True:
            try:
                await asyncio.sleep(120)  # 每 2 分钟检查一次
                now = time.time()
                today = datetime.now().strftime("%Y-%m-%d")
                if today != self._today:
                    self._today = today
                    self._today_count = 0
                    self._used_builtin = set()
                    # 第二天重置「等回复」状态
                    if self._awaiting_question:
                        logger.info(
                            f"intent_guard: 新的一天，重置等回复状态"
                            f"（上一个还在等：{self._awaiting_question}）"
                        )
                        self._awaiting_question = None

                # ⭐ 上一个问题还没人回 → 不再问新的（直到有人回或第二天）
                if self._awaiting_question:
                    continue

                if now - self._last_ask < self.ask_interval:
                    continue
                if self._today_count >= self.daily_limit:
                    continue

                cands = [q for q in _pending_questions() if q.get("id") not in self._used_builtin]
                if not cands:
                    continue

                q = random.choice(cands)
                sent = await self._send_question(q)
                if sent:
                    _mark_asked(q["id"])
                    self._used_builtin.add(q["id"])
                    self._last_ask = now
                    self._today_count += 1
                    # ⭐ 记下「正在等回复」——在此之前不再问新问题
                    self._awaiting_question = q["question"]
                    self._awaiting_keywords = extract_keywords(q["question"])
                    logger.info(
                        f"intent_guard: 主动提问 「{q['question']}」"
                        f"（等回复中，关键词={self._awaiting_keywords}，不回就不再问）"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"intent_guard ask loop: {e}")

    async def _send_question(self, q):
        """直接调 NapCat 的 HTTP API 发到群里"""
        try:
            text = f"【问一下】{q['question']}"
            body = json.dumps(
                {
                    "group_id": GROUP_ID,
                    "message": [{"type": "text", "data": {"text": text}}],
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                NAPCAT_API + "/send_group_msg",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            ok = result.get("status") == "ok"
            if not ok:
                logger.warning(f"intent_guard: 发送失败 {result}")
            return ok
        except Exception as e:
            logger.warning(f"intent_guard: _send_question 失败 {e}")
            return False

    def _is_answer_to_awaiting(self, text):
        """判断消息是否在回答当前问题（先快筛，再调 DeepSeek）"""
        import urllib.request

        # ── 快筛：明显不是回答的，直接跳过（不调 API）──────────
        text = (text or "").strip()
        if len(text) < 5:
            return False
        if not re.search(r"[\u4e00-\u9fa5a-zA-Z]", text):
            return False
        GARBAGE = [
            "哈哈", "hhh", "666", "收到", "好的", "嗯", "哦", "行",
            "可以", "算了", "+1", "路过", "打卡", "笑死", "绝了",
        ]
        if len(text) < 10 and any(g in text for g in GARBAGE):
            return False

        # ── 快筛通过 → 调 DeepSeek 精确判断 ─────────────────
        try:
            cfg = json.load(open("/opt/bili-duty/config.json", encoding="utf-8"))
            key = cfg["deepseek"]["api_key"]
            base = cfg["deepseek"].get("base_url", "https://api.deepseek.com")
            model = cfg["deepseek"].get("model", "deepseek-chat")
        except Exception as e:
            logger.warning(f"intent_guard: 读不到 deepseek 配置，宽松处理：{e}")
            return True

        prompt = (
            "判断下面这条消息是不是在回答那个问题。只回一个字：是 或 否。\n"
            f"问题：{self._awaiting_question}\n"
            f"消息：{text}"
        )
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 4,
        }).encode("utf-8")
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
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            ans = data["choices"][0]["message"]["content"].strip()
            return ans.startswith("是")
        except Exception as e:
            logger.warning(f"intent_guard: 判断失败，宽松处理：{e}")
            return True

    @filter.on_llm_request()
    async def add_intent_hint(self, event: AstrMessageEvent, req):
        """在 LLM 请求前加一条判定提示：要不要回这条消息。"""
        try:
            # ⭐ 只有「真的回答了问题」才清除等待状态
            if self._awaiting_question:
                text = (event.message_str or "").strip()
                if text and self._is_answer_to_awaiting(text):
                    logger.info(
                        f"intent_guard: 收到疑似回答「{text[:20]}」，清除等回复状态"
                        f"（之前问的是：{self._awaiting_question}）"
                    )
                    self._awaiting_question = None
                    self._awaiting_keywords = []

            hint = (
                "\n\n【回复判定】先判断这条消息是不是在跟你说话 / 问你问题：\n"
                "- 是在问你（提问、求助、接你的话、直接叫你）→ 正常回复\n"
                "- 不是（自言自语、在对别人说、无意义灌水、纯表情）→ 只输出 "
                + SKIP_MARK
                + "，不要输出任何别的字\n"
            )
            if hasattr(req, "system_prompt"):
                req.system_prompt = (req.system_prompt or "") + hint
        except Exception:
            pass

    @filter.on_llm_response()
    async def filter_skip(self, event: AstrMessageEvent, resp):
        """如果模型判定不回（[SKIP]），就清空回复并阻止发送。"""
        try:
            text = (getattr(resp, "completion_text", "") or "").strip()
            if text == SKIP_MARK or text.startswith(SKIP_MARK):
                if hasattr(resp, "completion_text"):
                    resp.completion_text = ""
                event.stop_event()
        except Exception:
            pass
