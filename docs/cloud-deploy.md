# 云端部署（AstrBot + QQ 机器人）

把 `intent_guard` 插件和 AstrBot 一起搭到云服务器上，让 QQ 机器人在云端 24 小时在线。

---

## 服务器要求

| 项 | 要求 |
| --- | --- |
| 系统 | Ubuntu 22.04+（Debian 系也行） |
| 内存 | ≥ 1 GB 可用（AstrBot 约占 380 MB） |
| 磁盘 | ≥ 10 GB |
| Python | 3.10+ |
| 网络 | 能出网（QQ 官方机器人用 websocket，**不需要公网 IP**） |

---

## 部署步骤

### 1. 装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

### 2. 装 AstrBot（**必须换国内镜像**）

```bash
export PATH="$HOME/.local/bin:$PATH"
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
  uv tool install astrbot
```

> ⚠️ **不换镜像会非常慢**：实测直连 PyPI 44 分钟只下了 333 MB，换清华镜像 20 秒就编译了。
>
> 也可以换阿里：`https://mirrors.aliyun.com/pypi/simple`

### 3. 初始化 AstrBot 根目录

```bash
mkdir -p /opt/astrbot
cd /opt/astrbot
echo "" | astrbot init
```

这会创建 `.astrbot` 标记文件。

> ⚠️ `astrbot run` 会检查根目录标记，没有 `.astrbot` 会报
> `xxx 不是有效的 AstrBot 根目录`

### 4. 跳过「管理面板」交互询问

```bash
mkdir -p /opt/astrbot/data/dist/assets
echo "v4.14.6" > /opt/astrbot/data/dist/assets/version
```

> ⚠️ 不建这个文件，每次启动都会问「是否安装管理面板？」，
> 而 systemd 没有终端 → `click.exceptions.Abort` → 启动失败。

版本号要和 `astrbot --version` 输出一致。

### 5. 上传数据（配置 + 插件）

把本地 `data/` 整个上传到 `/opt/astrbot/data/`：

```
data/
├── cmd_config.json      # 平台 / 提供商 / 人格配置
├── data_v4.db           # 人格库
├── plugins/
│   └── intent_guard/    # 本仓库 astrbot-plugin/ 的内容
│       ├── main.py
│       └── metadata.yaml
└── ...
```

> ⚠️ `cmd_config.json` 带 UTF-8 BOM，读取时用 `utf-8-sig`。

### 6. 配 systemd 服务

```ini
[Unit]
Description=AstrBot QQ Bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/astrbot
Environment=PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONIOENCODING=utf-8
ExecStart=/root/.local/bin/astrbot run -p 6186
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now astrbot
```

### 7. 验证

```bash
systemctl is-active astrbot
ss -lntp | grep 6186
journalctl -u astrbot -n 30 --no-pager
```

日志里应该看到：

```
Plugin intent_guard (0.1.0) by 鲸鱼娘: ...
载入 qq_official(default_xxx) 平台适配器 ...
载入 openai_chat_completion(deepseek) 服务提供商 ...
AstrBot 启动完成。
```

---

## 踩坑记录

| 问题 | 原因 | 解决 |
| --- | --- | --- |
| `uv tool install` 跑 44 分钟没完 | 直连 PyPI 慢（125 KB/s） | 换清华镜像 |
| `xxx 不是有效的 AstrBot 根目录` | 缺 `.astrbot` 标记 | `astrbot init` |
| 启动卡在「是否安装管理面板」 | `click.confirm(abort=True)` 无终端 | 建 `data/dist/assets/version` |
| QQ 收不到群消息 | QQ 官方机器人**群聊只推 @ 消息** | 平台限制，只能换 NapCat/OneBot |
| 本地和云端同时连 QQ | 两个实例抢连接 | 停掉本地 |

---

## ⚠️ AstrBot 4.14.6 隐藏规则（2026-11-06 踩坑记录）

这两个配置**语法上看起来对，语义正好相反**，报错信息还完全误导，排查了 2 小时：

### ① `wake_prefix = []` 是「没有任何唤醒词」

```python
# AstrBot 源码 core/pipeline/waking_check/stage.py
wake_prefixes = self.ctx.astrbot_config["wake_prefix"]
is_wake = False
for wake_prefix in wake_prefixes:        # 空列表 → 循环一次都不执行
    if event.message_str.startswith(wake_prefix):
        is_wake = True
```

| 写法 | 行为 | 结果 |
| --- | --- | --- |
| `["/"]` | 只有 `/` 开头的消息才唤醒 | 正常（默认） |
| `[]` | 循环一次都不执行 | ❌ **所有消息都被丢弃** |
| `[""]` | `startswith("")` 恒真 | ✅ **所有消息都唤醒** |

**结论：要「所有消息都唤醒」必须写 `[""]`，不能写 `[]`。**
后者会让 `is_wake` 永远是 `False`，消息在 `waking_check` 阶段就被丢掉，根本进不了 LLM。

### ② `provider_sources[].key` 必须是数组

```python
# 基类 core/provider/provider.py
def get_keys(self) -> list[str]:
    keys = self.provider_config.get("key", [""])   # 期望 list
    return keys or [""]

# 子类 core/provider/sources/openai_source.py:493
available_api_keys = self.api_keys.copy()   # 如果是 str 就崩
```

| 写法 | 结果 |
| --- | --- |
| `"key": "sk-xxx"` | ❌ 运行时崩溃：`'str' object has no attribute 'copy'` |
| `"key": ["sk-xxx"]` | ✅ 正常 |

崩溃发生在**调用 LLM 的那一刻**，所以现象是「收到消息了、也显示『准备发送』，但发出去的是错误提示」。

### ③ 排查方法（收到消息但不回复时）

```bash
# 1. 开 DEBUG 日志
python3 - <<'EOF'
import json
p = "/opt/astrbot/data/cmd_config.json"
d = json.load(open(p, encoding="utf-8-sig"))
d["log_level"] = "DEBUG"
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
EOF
systemctl restart astrbot

# 2. 让用户在群里发一条，然后看
journalctl -u astrbot --since "2 minutes ago" --no-pager | grep -vE "Task was destroyed"
```

判断方法：

| 日志现象 | 结论 |
| --- | --- |
| `pipeline 执行完毕` 后**什么都没有** | ❌ `wake_prefix` 问题（消息被丢掉） |
| 出现 `Prepare to send` 但内容是错误提示 | ❌ provider 配置问题（key 格式） |
| 出现 `Prepare to send` 且内容是正常回复 | ✅ 正常 |

排查完**记得把 `log_level` 改回 `INFO`**（DEBUG 日志量很大）。

---

## 平台限制（重要）

| 场景 | 能否收到非 @ 消息 |
| --- | --- |
| **私聊（C2C）** | ✅ 可以（所有消息都推） |
| **群聊** | ❌ 不行（只推 `GROUP_AT_MESSAGE_CREATE`） |

所以插件里的「判断是不是在问你」：
- **私聊**：真正生效（不是问你就不回）
- **群聊**：只能做到「@ 之后判断这条值不值得回」

---

## 运维

```bash
# 看状态
systemctl status astrbot

# 看日志
journalctl -u astrbot -f

# 重启
systemctl restart astrbot

# 改配置
vim /opt/astrbot/data/cmd_config.json
systemctl restart astrbot
```

---

## 迁移到本仓库

本仓库的 `astrbot-plugin/` 就是 `/opt/astrbot/data/plugins/intent_guard/` 的内容：

```bash
scp -r astrbot-plugin/* root@<server>:/opt/astrbot/data/plugins/intent_guard/
systemctl restart astrbot
```
