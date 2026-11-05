# dsh-persona-curiosity · 人格好奇心

>



---

 它解决什么

**预设的**

**人格是问出来的**

-
`在意钱/生活压力``现实/务实`
-

---

## 四个工具

| 工具 | 作用 |
| --- | --- |
| `curiosity_ask` ||
| `curiosity_answer` |
 `curiosity_list` ||
| `curiosity_persona` ||

---

## 人格信号（内置 10 类）

回答会被正则匹配，提取"这个人在意什么"：

| 标签 | 触发词示例 |
| --- | --- |
|||
|||
|||
|||
|||
|||
|||
|||
|||
|||

>`index.js``SIGNAL_RULES`

---

## 和已有插件联动

`$DSH_HOME/persona-curiosity/`

**联合积累**`curiosity_persona``tags`

- `bili_humanism_personality`
- `memory_add`
- `bili_humanism_journal`

这样"问出来的"和"读出来的"人格会汇到同一处。

---

## 安装

```
# 在 DSH 里
plugin_manager install_bundle --target <本目录绝对路径>
```

安装后重启（或 HMR）生效，工具立刻可用。或者你可以让你的dsh帮你安装

---

## 存储结构

```
$DSH_HOME/persona-curiosity/
├── questions.json   # 问题队列（最近 200 条）
├── insights.json    # 洞察（最近 3000 条）
└── profile.json     # 画像（标签计数）
```

---

## 设计原则

1. **问得真诚**
2. **落库才叫积累**`curiosity_answer`
3. **可以和别人共存**

---

## 许可

MIT
