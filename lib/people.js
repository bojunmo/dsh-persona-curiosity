// people.js - 人格跨平台关联模块
//
// 用途：把同一个人在多个平台的身份串起来，画像合并。
//
// 用法：
//   await linkIdentities('owner', 'bilibili', '397565739')   // 主人 B站
//   await linkIdentities('owner', 'qq', '1951194537')       // 主人 QQ
//   await resolveCanonical('qq', '1951194537')              // → 'owner'
//   await getAllIdentities('owner')                         // → [{platform,uid}, ...]
//
// 数据文件：$DSH_HOME/persona-curiosity/links.json
//   {
//     "links": [
//       { "canonical": "owner",
//         "identities": [
//           { "platform": "bilibili", "uid": "397565739" },
//           { "platform": "qq", "uid": "1951194537" }
//         ] }
//     ]
//   }

import { join } from 'node:path'
import { readFile, writeFile, mkdir } from 'node:fs/promises'

const HOME =
  process.env.DSH_HOME ||
  join(process.env.USERPROFILE || process.env.HOME || '.', '.dsh')

const DIR = join(HOME, 'persona-curiosity')
const LINKS_FILE = join(DIR, 'links.json')

/** 统一的身份 key：`qq:1951194537` */
export function personKey(platform, uid) {
  return `${platform}:${uid}`
}

async function readJson(file, fallback) {
  try {
    return JSON.parse(await readFile(file, 'utf8'))
  } catch {
    return fallback
  }
}

async function writeJson(file, data) {
  await mkdir(DIR, { recursive: true })
  await writeFile(file, JSON.stringify(data, null, 2), 'utf8')
}

export async function loadLinks() {
  return readJson(LINKS_FILE, { links: [] })
}

/** 把某个身份挂到 canonical 名下（幂等） */
export async function linkIdentities(canonical, platform, uid) {
  const data = await loadLinks()
  let link = data.links.find((l) => l.canonical === canonical)
  if (!link) {
    link = { canonical, identities: [] }
    data.links.push(link)
  }
  const key = personKey(platform, uid)
  if (!link.identities.some((i) => personKey(i.platform, i.uid) === key)) {
    link.identities.push({ platform: String(platform), uid: String(uid) })
  }
  await writeJson(LINKS_FILE, data)
  return link
}

/** 解除某个身份的关联 */
export async function unlinkIdentity(canonical, platform, uid) {
  const data = await loadLinks()
  const link = data.links.find((l) => l.canonical === canonical)
  if (!link) return null
  const key = personKey(platform, uid)
  link.identities = link.identities.filter(
    (i) => personKey(i.platform, i.uid) !== key
  )
  await writeJson(LINKS_FILE, data)
  return link
}

/** 查这个身份属于谁（返回 canonical 或 null） */
export async function resolveCanonical(platform, uid) {
  const data = await loadLinks()
  const key = personKey(platform, uid)
  for (const l of data.links) {
    if (l.identities.some((i) => personKey(i.platform, i.uid) === key)) {
      return l.canonical
    }
  }
  return null
}

/** 查 canonical 名下的所有身份 */
export async function getAllIdentities(canonical) {
  const data = await loadLinks()
  return data.links.find((x) => x.canonical === canonical)?.identities || []
}

/** 列出所有关联 */
export async function listLinks() {
  return (await loadLinks()).links
}
