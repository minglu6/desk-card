# desk-card

一块挂在桌上的 e-ink 信息卡——把 Likebook K78W（Android 6.0.1，1404×1872 灰阶屏）改造成 always-on 的桌面 dashboard。

显示内容：
- 顶部刊头 + 当前时间（巨大）
- 时间两翼：合肥实时天气（彩云 API）
- 公历 + 农历 + 节气
- 每日轮换的编程 / AI 冷知识
- Claude Code 用量条（5h / 7d 真实百分比，自带 Clawd 像素吉祥物作 marker，随用量左右移动）

## 架构

```
[Windows host]                      [Likebook K78W (WiFi / USB)]
─────────────                       ───────────────────────────
render.py (Pillow)                  com.desk.card APK
   ├─ usage_api.py  ──┐                ↑ HTTP poll /etag.json 每 30s
   ├─ weather_api.py  │                │ 变了 → GET /current.png
   ├─ quotes.py       │                │
   └─ cnlunar         │                │
        │             │                │
        ▼             │                │
 out/current.png   ◀──┴── Flask 8765 ──┘
        ▲
        │ 每 60s
   server.py
   ├─ render loop (60s)
   ├─ adb watchdog (15s, 自动重绑 reverse)
   ├─ /health, /etag.json, /current.png, POST /render
   └─ 夜间 0:00–7:00 暂停渲染
```

## 关键文件

| 文件 | 作用 |
|---|---|
| `render.py` | 主渲染脚本，1404×1872 PNG，PIL 单文件 |
| `server.py` | Flask + 后台 render loop + adb watchdog，开机自启入口 |
| `usage_api.py` | Anthropic OAuth `/api/oauth/usage` 直连 + 5min cache |
| `usage_reader.py` | usage_api → claude-hud cache 兜底链 |
| `weather_api.py` | 彩云天气 API + 1h cache |
| `quotes.py` | 50+ 条编程 / AI 冷知识，每 2h 轮换 |
| `assets/make_clawd.py` | Clawd 像素吉祥物生成器 |
| `android/` | 极简 Kotlin APK（≈ 150 行），全屏 ImageView + 轮询 |

## 运行

需要：Python 3.10+、Pillow、Flask、cnlunar。

```bash
pip install pillow flask cnlunar
$env:CAIYUN_WEATHER_API_TOKEN = "你自己的彩云 token"   # 必填
python server.py
```

server 启动后默认监听 `0.0.0.0:8765`，APK 端会找两个 baseUrl：先试 LAN IP，再回退到 `127.0.0.1`（走 `adb reverse`）。

## Claude Code Skill

仓库带 `~/.claude/skills/desk-card/SKILL.md`（在主机另一处），让 Claude Code / Codex 能用对话触发渲染、查用量等。

## 隐私 / 凭据

- **从不**把 OAuth token、Caiyun token 写进代码。Caiyun 通过 `CAIYUN_WEATHER_API_TOKEN` 环境变量读取。
- Claude OAuth token 取自 `~/.claude/.credentials.json`（系统自管），项目不读不写。

## License

个人玩具，无 license。Fork 随意，但**别用我的 Caiyun token**——它已经从代码里清掉了。
