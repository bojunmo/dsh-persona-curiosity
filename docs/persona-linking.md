# 跨平台人格关联

## 问题

同一个人在 B站 和 QQ 上是**两个身份**：

| 平台 | 身份 |
| --- | --- |
| B站 | uid `397565739` |
| QQ | uid `1951194537` |

如果不关联，这两份画像会分开 —— **同一个人被拆成两个人**。

## 设计

### 数据结构

```
$DSH_HOME/persona-curiosity/
├── links.json          ← 跨平台关联表
├── questions.json      ← 问题队列
├── insights.json       ← 人格洞察
└── profile.json        ← 累计画像
```

### links.json 格式

```json
{
  "links": [
    {
      "canonical": "owner",
      "identities": [
        { "platform": "bilibili", "uid": "397565739" },
        { "platform": "qq", "uid": "1951194537" }
      ]
    }
  ]
}
```

- `canonical`：主身份名（给人起的小名，如 `owner`、`friend_xxx`）
- `identities`：这个人在所有平台的身份

### 新增工具

| 工具 | 作用 |
| --- | --- |
| `curiosity_link` | 把某个平台身份挂到 canonical 名下（幂等） |
| `curiosity_identities` | 查关联（不传 canonical 就列全部） |

### 用法

```javascript
curiosity_link({ canonical: 'owner', platform: 'bilibili', uid: '397565739' })
curiosity_link({ canonical: 'owner', platform: 'qq', uid: '1951194537' })

curiosity_identities({ canonical: 'owner' })
// → [{ platform: 'bilibili', uid: '397565739' },
//    { platform: 'qq', uid: '1951194537' }]
```

### 代码结构

```
dsh-persona-curiosity/
├── lib/
│   └── people.js       ← 关联模块（linkIdentities / resolveCanonical / getAllIdentities）
├── index.js            ← 加了 2 个工具
└── test-links.mjs      ← 关联测试
```

## 测试

```bash
$env:DSH_HOME = '<临时目录>'
node test-links.mjs
```

6 项全过：

1. 关联成功（B站 + QQ → owner）
2. `resolveCanonical('qq', '1951194537')` → `owner`
3. `getAllIdentities('owner')` → 2 个身份
4. 重复关联去重（还是 2 个）
5. 未关联的身份 → `null`
6. 解除关联 → 剩 1 个

## 设计上的取舍

### 为什么用「canonical」而不是「自动识别」

自动识别很难：B站 uid 和 QQ uid 之间**没有天然映射**。所以用**人工指定 canonical**，由使用者（或 AI）决定「这两个身份是同一个人」。

### 为什么不是「一个人一条记录」

同一个人可能有**多个平台身份**，如果一条记录只存一个平台，就丢了关联。用 `links.json` + `identities` 数组可以动态扩展（以后加微信、Discord 都行）。

### 为什么不自动合并画像

合并需要**重新计算**（标签权重）。当前的设计是：
- 关联只记「谁是谁」
- 合并发生在**查询时**（`curiosity_persona` 可以按 canonical 聚合）

这样原始数据不会被破坏，随时可以改关联关系。
