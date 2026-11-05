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
