// sync-persona.cjs —— 合并三个来源的人格洞察到本地
//
// 来源：
//   1. 云端 QQ：  /opt/astrbot/data/persona-curiosity/insights.json
//   2. 云端 B站： /opt/bili-duty/bili_insights.json
//   3. 本地已有： $DSH_HOME/persona-curiosity/insights.json
//
// 逻辑：按 id 去重合并，云端有本地没有的追加到本地。
//
// 用法：
//   node sync-persona.cjs            # 真同步
//   node sync-persona.cjs --dry-run  # 只看不写
const fs = require('fs')
const path = require('path')

const HOME = process.env.DSH_HOME || path.join(process.env.USERPROFILE || '.', '.dsh')
const LOCAL = path.join(HOME, 'persona-curiosity', 'insights.json')

const SERVERS = {
  qq: '/opt/astrbot/data/persona-curiosity/insights.json',
  bili: '/opt/bili-duty/bili_insights.json',
}

const DEPLOY = 'C:\\Users\\admin\\Documents\\deepseek-harness\\default-workspace\\.ssh-deploy'
const { Client } = require(path.join(DEPLOY, 'node_modules', 'ssh2'))

const dryRun = process.argv.includes('--dry-run')

function readRemote(sftp, remote) {
  return new Promise((resolve) => {
    sftp.readFile(remote, (err, buf) => {
      if (err) return resolve(null) // 文件不存在就跳过
      try {
        resolve(JSON.parse(buf.toString('utf8')))
      } catch {
        resolve(null)
      }
    })
  })
}

const conn = new Client()
conn.on('ready', async () => {
  try {
    const sftp = await new Promise((res, rej) => conn.sftp((e, s) => (e ? rej(e) : res(s))))

    // 读本地
    let local = { items: [] }
    try {
      local = JSON.parse(fs.readFileSync(LOCAL, 'utf8'))
    } catch {}
    local.items = local.items || []
    const before = local.items.length

    // 读三个来源
    const remotes = {}
    for (const [name, remote] of Object.entries(SERVERS)) {
      const data = await readRemote(sftp, remote)
      remotes[name] = data ? data.items || [] : []
      console.log(`${name}: ${remotes[name].length} 条`)
    }
    console.log(`本地原有: ${before} 条`)

    // 合并（按 id 去重）
    const seen = new Set(local.items.map((i) => i.id))
    const added = []
    for (const [name, items] of Object.entries(remotes)) {
      for (const item of items) {
        if (item.id && !seen.has(item.id)) {
          local.items.push({ ...item, _from: name })
          seen.add(item.id)
          added.push({ ...item, _from: name })
        }
      }
    }

    console.log(`新增: ${added.length} 条`)
    for (const a of added.slice(0, 8)) {
      console.log(`  · [${a._from}] ${a.answerer || '?'}: ${(a.answer || '').slice(0, 35)} → ${(a.signals || []).join(',')}`)
    }
    if (added.length > 8) console.log(`  ... 还有 ${added.length - 8} 条`)

    if (dryRun) {
      console.log('[dry-run] 不写入')
      conn.end()
      return
    }

    fs.mkdirSync(path.dirname(LOCAL), { recursive: true })
    fs.writeFileSync(LOCAL, JSON.stringify(local, null, 2), 'utf8')
    console.log(`✅ 已写入 ${LOCAL}（共 ${local.items.length} 条）`)
    conn.end()
  } catch (e) {
    console.error('失败:', e.message)
    conn.end()
  }
})
conn.on('error', (e) => console.error('连接失败:', e.message))
conn.connect({ host: '121.43.81.15', port: 22, username: 'root', password: 'Mo28323932' })
