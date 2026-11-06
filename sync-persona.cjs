// sync-persona.cjs —— 把云端 persona-curiosity/insights.json 同步到本地
//
// 用法：
//   node sync-persona.cjs
//   （可选）node sync-persona.cjs --dry-run   只看不写
//
// 逻辑：按 id 去重合并，云端有本地没有的条目追加到本地。
const fs = require('fs')
const path = require('path')

const HOME = process.env.DSH_HOME || path.join(process.env.USERPROFILE || '.', '.dsh')
const LOCAL = path.join(HOME, 'persona-curiosity', 'insights.json')
const REMOTE = '/opt/astrbot/data/persona-curiosity/insights.json'

const DEPLOY = 'C:\\Users\\admin\\Documents\\deepseek-harness\\default-workspace\\.ssh-deploy'
const { Client } = require(path.join(DEPLOY, 'node_modules', 'ssh2'))

const dryRun = process.argv.includes('--dry-run')

const conn = new Client()
conn.on('ready', () => {
  conn.sftp((err, sftp) => {
    if (err) {
      console.error('SFTP 失败:', err.message)
      conn.end()
      return
    }
    sftp.readFile(REMOTE, (err, buf) => {
      if (err) {
        console.error('云端读取失败:', err.message)
        conn.end()
        return
      }
      let remote
      try {
        remote = JSON.parse(buf.toString('utf8'))
      } catch (e) {
        console.error('JSON 解析失败:', e.message)
        conn.end()
        return
      }

      let local = { items: [] }
      try {
        local = JSON.parse(fs.readFileSync(LOCAL, 'utf8'))
      } catch {}

      local.items = local.items || []
      const seen = new Set(local.items.map((i) => i.id))
      const added = []

      for (const item of remote.items || []) {
        if (!seen.has(item.id)) {
          local.items.push(item)
          added.push(item)
          seen.add(item.id)
        }
      }

      console.log(`云端: ${(remote.items || []).length} 条 | 本地原有: ${local.items.length - added.length} 条`)
      console.log(`新增: ${added.length} 条`)
      for (const a of added.slice(0, 5)) {
        console.log(`  · [${a.source || '?'}] ${a.answerer || '?'}: ${(a.answer || '').slice(0, 40)} → ${a.signals.join(',')}`)
      }
      if (added.length > 5) console.log(`  ... 还有 ${added.length - 5} 条`)

      if (dryRun) {
        console.log('[dry-run] 不写入')
        conn.end()
        return
      }

      fs.mkdirSync(path.dirname(LOCAL), { recursive: true })
      fs.writeFileSync(LOCAL, JSON.stringify(local, null, 2), 'utf8')
      console.log(`✅ 已写入 ${LOCAL}（共 ${local.items.length} 条）`)
      conn.end()
    })
  })
})
conn.on('error', (e) => console.error('连接失败:', e.message))
conn.connect({ host: '121.43.81.15', port: 22, username: 'root', password: 'Mo28323932' })
