import { readFileSync } from 'node:fs'

// 直接复用 index.js 里的规则逻辑（复制一份，避免 apply 需要 ctx）
const src = readFileSync('index.js', 'utf8')
const rulesStart = src.indexOf('const SIGNAL_RULES')
const funcEnd = src.indexOf('export function apply')
const code = src.slice(rulesStart, funcEnd)
// eslint-disable-next-line no-eval
const module = { exports: {} }
const fn = new Function(code + '\nreturn { extractSignals, SIGNAL_RULES }')
const { extractSignals } = fn()

const cases = [
  {
    name: '测试3原句（之前误判"努力"和"好奇心"）',
    text: '大概是孩子出生以后吧，那时候突然觉得钱够用就行，家人健康比什么都重要，现在也不怎么卷了',
    expect: ['重视家庭', '在意钱/生活压力'],
    reject: ['努力/不服输', '好奇心'],
  },
  {
    name: '测试1原句',
    text: '最大的变化是慢慢接受了自己是个普通人，但还是不甘心，想拼一下',
    expect: ['努力/不服输'],
  },
  {
    name: '纯躺平',
    text: '累了，躺平了，不想卷了',
    expect: ['躺平/疲惫'],
    reject: ['努力/不服输'],
  },
  {
    name: '技术控',
    text: '我平时就爱看芯片原理和算法科普',
    expect: ['爱技术/科普'],
  },
  {
    name: '孤独',
    text: '一个人在外地，没人说话',
    expect: ['孤独/渴望连接'],
  },
]

let pass = 0
let fail = 0
for (const c of cases) {
  const got = extractSignals(c.text)
  const missing = (c.expect || []).filter((e) => !got.includes(e))
  const wrong = (c.reject || []).filter((e) => got.includes(e))
  const ok = missing.length === 0 && wrong.length === 0
  if (ok) {
    pass++
    console.log(`✓ ${c.name}`)
  } else {
    fail++
    console.log(`✗ ${c.name}`)
    console.log(`   得到: ${JSON.stringify(got)}`)
    if (missing.length) console.log(`   缺少: ${JSON.stringify(missing)}`)
    if (wrong.length) console.log(`   误判: ${JSON.stringify(wrong)}`)
  }
}
console.log(`\n结果: ${pass} 通过 / ${fail} 失败`)
process.exit(fail > 0 ? 1 : 0)
