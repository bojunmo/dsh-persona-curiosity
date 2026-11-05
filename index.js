/**
 * dsh-persona-curiosity —— 人格好奇心
 * ============================================================================
 * 让 AI 通过**主动问人**来长大。
 *
 *   1. 它从刷视频 / 看评论 / 回复里，攒出"想问的问题"
 *   2. 挑时机把问题问出去（主人 / 陌生人 / 粉丝）
 *   3. 收到回答 → 提取「这个人在意什么 / 他觉得什么重要」
 *   4. 写进人格洞察库，并同步给已有的人格插件
 *      （bili_humanism_personality / memory_add，存在就联动）
 *
 * 存储（$DSH_HOME/persona-curiosity/）：
 *   questions.json  问题队列
 *   insights.json   人格洞察
 *   profile.json    积累画像（标签计数）
 * ============================================================================
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'

export const name = 'persona-curiosity'
export const inject = ['tools']

const HOME = process.env.DSH_HOME || join(homedir(), '.dsh')
const DIR = join(HOME, 'persona-curiosity')
const Q_FILE = join(DIR, 'questions.json')
const I_FILE = join(DIR, 'insights.json')
const P_FILE = join(DIR, 'profile.json')

function ensureDir() {
  if (!existsSync(DIR)) mkdirSync(DIR, { recursive: true })
}

function loadJson(file, fallback) {
  try {
    if (!existsSync(file)) return fallback
    return JSON.parse(readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}

function saveJson(file, data) {
  ensureDir()
  const tmp = file + '.tmp'
  writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8')
  renameSync(tmp, file)
}

function loadQuestions() {
  return loadJson(Q_FILE, { items: [] })
}
function loadInsights() {
  return loadJson(I_FILE, { items: [] })
}
function loadProfile() {
  return loadJson(P_FILE, { tags: {}, total: 0, updated: null })
}

function textOutput(schemaDesc) {
  return {
    schema: { type: 'object', description: schemaDesc },
    render: (_args, value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }],
  }
}

/** 从回答里粗提取"人格信号"：关键词 → 标签 */
const SIGNAL_RULES = [
  { tag: '重视家庭', re: /(家人|父母|妈|爸|孩子|老婆|老公|亲人|回家)/ },
  { tag: '在意钱/生活压力', re: /(钱|工资|房贷|房租|穷|涨价|生活费|养家)/ },
  { tag: '努力/不服输', re: /(努力|拼|熬|坚持|不认输|干就完了|卷)/ },
  { tag: '躺平/疲惫', re: /(躺平|摆烂|累|麻了|算了|无所谓|不卷了|不想卷)/ },
  { tag: '爱技术/科普', re: /(技术|原理|代码|芯片|算法|科普|科学)/ },
  { tag: '爱游戏/二次元', re: /(游戏|动漫|番|二游|原神|崩铁|抽卡)/ },
  { tag: '重感情/温柔', re: /(谢谢|感动|温柔|陪|惦记|心疼)/ },
  { tag: '现实/务实', re: /(现实|实用|赚钱|效率|性价比|值得)/ },
  { tag: '孤独/渴望连接', re: /(一个人|孤独|没人|寂寞|找人说)/ },
  { tag: '好奇心', re: /(为什么|想知道|好奇|原理|搞不懂)/ },
]

/** 否定词：出现在关键词前面时，该关键词不算数 */
const NEGATIONS = ['不', '没', '别', '无', '未', '不怎么', '不太', '没有', '不是', '不想']

function extractSignals(text) {
  const hits = []
  for (const r of SIGNAL_RULES) {
    // 找出所有匹配位置
    const re = new RegExp(r.re.source, 'g')
    let m
    let hit = false
    while ((m = re.exec(text)) !== null) {
      // 看前面 4 个字符里有没有否定词
      const before = text.slice(Math.max(0, m.index - 4), m.index)
      const negated = NEGATIONS.some((n) => before.endsWith(n))
      if (!negated) {
        hit = true
        break
      }
    }
    if (hit) hits.push(r.tag)
  }
  return hits
}

export function apply(ctx) {
  ensureDir()

  // ── 工具 1：提一个问题 ──────────────────────────────────────────────
  ctx.tools.register({
    name: 'curiosity_ask',
    description:
      '从当下看到的视频/评论/回复里，攒一个"值得问人"的问题放进队列。' +
      '问题要具体、真诚、能引出对方真实想法（不是查户口）。' +
      '问出去后，等对方回答，再用 curiosity_answer 记录。',
    parameters: {
      question: { type: 'string', description: '要问的问题（一句，20-60字）' },
      target: { type: 'string', description: '问谁：owner=主人 / stranger=陌生人 / fan=粉丝' },
      channel: { type: 'string', description: '从哪问：qq / bili_comment / bili_dm' },
      source: { type: 'string', description: '问题从哪来的（BV号/评论/事件），方便回溯' },
    },
    output: textOutput('问题已入队'),
    async execute(args) {
      const qs = loadQuestions()
      const item = {
        id: 'q' + Date.now().toString(36),
        question: String(args.question || '').trim(),
        target: String(args.target || 'owner'),
        channel: String(args.channel || 'qq'),
        source: String(args.source || ''),
        status: 'pending',
        asked: null,
        answer: null,
        signals: [],
        created: new Date().toISOString(),
      }
      if (!item.question) return { ok: false, error: '问题不能为空' }
      qs.items.push(item)
      // 只保留最近 200 条
      if (qs.items.length > 200) qs.items = qs.items.slice(-200)
      saveJson(Q_FILE, qs)
      return {
        ok: true,
        id: item.id,
        question: item.question,
        target: item.target,
        channel: item.channel,
        pending: qs.items.filter((q) => q.status === 'pending').length,
      }
    },
  })

  // ── 工具 2：记录回答 → 提取人格信号 ─────────────────────────────────
  ctx.tools.register({
    name: 'curiosity_answer',
    description:
      '把收到的回答记下来（按问题 id 或直接给问题文本），' +
      '自动提取人格信号（他在意什么/价值观），存进洞察库。' +
      '这是"人格积累"真正落库的那一步。',
    parameters: {
      question_id: { type: 'string', description: '问题 id（来自 curiosity_list 或 curiosity_ask 的返回）' },
      answer: { type: 'string', description: '对方的回答原文' },
      answerer: { type: 'string', description: '回答者（昵称或 owner/stranger/fan）' },
    },
    output: textOutput('回答已记录并提取洞察'),
    async execute(args) {
      const qs = loadQuestions()
      const id = String(args.question_id || '')
      const answer = String(args.answer || '').trim()
      if (!answer) return { ok: false, error: '回答不能为空' }

      const q = qs.items.find((x) => x.id === id) || qs.items.filter((x) => x.status === 'pending').pop()
      if (!q) return { ok: false, error: '没找到对应的问题（先用 curiosity_ask 提一个）' }

      const signals = extractSignals(answer)
      q.status = 'answered'
      q.answer = answer
      q.answerer = String(args.answerer || q.target || '')
      q.answered_at = new Date().toISOString()
      q.signals = signals
      saveJson(Q_FILE, qs)

      // 写洞察
      const ins = loadInsights()
      ins.items.push({
        id: 'i' + Date.now().toString(36),
        question: q.question,
        answer,
        answerer: q.answerer,
        signals,
        source: q.source,
        at: new Date().toISOString(),
      })
      if (ins.items.length > 3000) ins.items = ins.items.slice(-3000)
      saveJson(I_FILE, ins)

      // 更新画像计数
      const prof = loadProfile()
      for (const s of signals) prof.tags[s] = (prof.tags[s] || 0) + 1
      prof.total = (prof.total || 0) + 1
      prof.updated = new Date().toISOString()
      saveJson(P_FILE, prof)

      return {
        ok: true,
        question: q.question,
        answer,
        signals,
        insight_total: ins.items.length,
        top_tags: Object.entries(prof.tags)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 5)
          .map(([k, v]) => `${k}×${v}`),
      }
    },
  })

  // ── 工具 3：看队列 ───────────────────────────────────────────────
  ctx.tools.register({
    name: 'curiosity_list',
    description: '看当前有哪些"待问 / 已问 / 已回答"的问题，以及积累的画像概览。',
    parameters: {
      status: { type: 'string', description: 'pending=待问（默认）/ asked=已问 / answered=已回答 / all=全部' },
      limit: { type: 'number', description: '返回几条（默认 10）' },
    },
    output: textOutput('问题队列'),
    async execute(args) {
      const qs = loadQuestions()
      const st = String(args.status || 'pending')
      const limit = Math.max(1, Math.min(Number(args.limit) || 10, 50))
      let items = qs.items
      if (st !== 'all') items = items.filter((x) => x.status === st)
      items = items.slice(-limit).reverse()
      const prof = loadProfile()
      return {
        ok: true,
        counts: {
          pending: qs.items.filter((x) => x.status === 'pending').length,
          asked: qs.items.filter((x) => x.status === 'asked').length,
          answered: qs.items.filter((x) => x.status === 'answered').length,
        },
        items: items.map((x) => ({
          id: x.id,
          q: x.question,
          target: x.target,
          status: x.status,
          signals: x.signals,
        })),
        profile: {
          total: prof.total || 0,
          top_tags: Object.entries(prof.tags || {})
            .sort((a, b) => b[1] - a[1])
            .slice(0, 8)
            .map(([k, v]) => `${k}×${v}`),
        },
      }
    },
  })

  // ── 工具 4：人格画像 ────────────────────────────────────────────
  ctx.tools.register({
    name: 'curiosity_persona',
    description:
      '看"问出来的那个我"长成什么样了——人格画像（标签权重 + 最近洞察）。' +
      '也可以用它把画像喂给别的人格插件（bili_humanism_personality / memory_add）。',
    parameters: {
      recent: { type: 'number', description: '带几条最近的洞察（默认 5）' },
    },
    output: textOutput('人格画像'),
    async execute(args) {
      const prof = loadProfile()
      const ins = loadInsights()
      const n = Math.max(0, Math.min(Number(args.recent) || 5, 20))
      return {
        ok: true,
        total_answers: prof.total || 0,
        tags: Object.entries(prof.tags || {})
          .sort((a, b) => b[1] - a[1])
          .map(([k, v]) => ({ tag: k, count: v })),
        recent: ins.items.slice(-n).reverse().map((x) => ({
          q: x.question,
          answer: x.answer,
          signals: x.signals,
          answerer: x.answerer,
          at: x.at,
        })),
        hint:
          '想同步到人格插件：把 tags 里权重高的标签，用 bili_humanism_personality 的 select 或 memory_add 写进去。',
      }
    },
  })
}
