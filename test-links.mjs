// 测试跨平台关联
import {
  linkIdentities,
  resolveCanonical,
  getAllIdentities,
  listLinks,
  unlinkIdentity,
} from './lib/people.js'

console.log('=== 关联测试 ===')
await linkIdentities('owner', 'bilibili', '397565739')
await linkIdentities('owner', 'qq', '1951194537')
console.log('1. resolveCanonical(qq, 1951194537):', await resolveCanonical('qq', '1951194537'))
console.log('2. getAllIdentities(owner):', JSON.stringify(await getAllIdentities('owner')))
console.log('3. listLinks():', JSON.stringify(await listLinks()))

console.log('\n=== 去重测试（重复关联同一个身份）===')
await linkIdentities('owner', 'bilibili', '397565739')
console.log('4. 重复后 identities 数:', (await getAllIdentities('owner')).length, '（应为 2）')

console.log('\n=== 未关联的身份 ===')
console.log('5. resolveCanonical(qq, 999999):', await resolveCanonical('qq', '999999'), '（应为 null）')

console.log('\n=== 解除关联测试 ===')
await unlinkIdentity('owner', 'qq', '1951194537')
console.log('6. 解除后:', JSON.stringify(await getAllIdentities('owner')))

console.log('\n=== 清理测试数据 ===')
await unlinkIdentity('owner', 'bilibili', '397565739')
await unlinkIdentity('owner', 'qq', '1951194537')
// 清理空 links
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
const HOME = process.env.DSH_HOME || join(process.env.USERPROFILE || process.env.HOME || '.', '.dsh')
await writeFile(join(HOME, 'persona-curiosity', 'links.json'), '{"links":[]}', 'utf8')
console.log('已清理')

console.log('\n✅ 全部通过')
