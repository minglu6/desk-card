"""Programming tips and CS trivia for the desk card. One per day, rotates by date.

Format kept as 4-tuple `(text, source, "", "")` for backward compat with the
existing render code; only the source label is used in the attribution.
"""
from __future__ import annotations

import hashlib
import time
from datetime import date

ROTATION_SECONDS = 2 * 3600   # 2 hours

# (tip_text, source_label, "", "")
QUOTES: list[tuple[str, str, str, str]] = [
    # Vim
    (":w !sudo tee % 可以在没用 sudo 打开 vim 的情况下保存系统文件。",
     "vim 技巧", "", ""),
    ("Vim 里 gv 重新选中上次的可视模式选区，u 撤销，U 大写整行。",
     "vim 技巧", "", ""),
    ("Vim 里 . 重复上一次修改，是单键最强武器。",
     "vim 技巧", "", ""),
    ("Vim 中 ci\" 删除当前引号内内容并进入插入模式，ci( ci{ 同理。",
     "vim 技巧", "", ""),

    # Git
    ("git commit --fixup=<sha> 配合 git rebase -i --autosquash 可自动整理修补提交。",
     "git 实用", "", ""),
    ("git reflog 是反悔药——所有 HEAD 变化都被记录，hard reset 也能找回。",
     "git 实用", "", ""),
    ("git switch -c new-branch 是 git checkout -b 的现代替代，语义更清楚。",
     "git 实用", "", ""),
    ("git bisect 用二分查找定位引入 bug 的提交，几步就能从几百次提交里揪出元凶。",
     "git 实用", "", ""),
    ("git stash push -m '说明' 可以给暂存起的修改加注释，list 时看得清楚。",
     "git 实用", "", ""),
    ("git log --oneline --graph --all --decorate 一键看完整提交树。",
     "git 实用", "", ""),

    # Shell / Bash
    ("Bash 里 !! 重复上条命令，sudo !! 是「忘加 sudo」的标准解药。",
     "Shell 提示", "", ""),
    ("Bash 中 cd - 跳回上一次的目录，比记路径方便。",
     "Shell 提示", "", ""),
    ("Ctrl+R 反向搜索命令历史；连按多次可继续往前找。",
     "Shell 提示", "", ""),
    ("2>&1 把 stderr 合并进 stdout；&> 是它的简写（仅 bash/zsh）。",
     "Shell 提示", "", ""),
    ("$_ 是上条命令的最后一个参数，比按上箭头编辑更快。",
     "Shell 提示", "", ""),

    # Python
    ("Python 的 for/while 有个鲜为人知的 else 分支——循环未被 break 时才执行。",
     "Python 冷知识", "", ""),
    ("Python 中 a, b = b, a 不需要中间变量，因为右侧先求值成元组。",
     "Python 冷知识", "", ""),
    ("collections.Counter 一行统计列表元素频次：Counter(words).most_common(10)。",
     "Python 标准库", "", ""),
    ("Python 中 [] is [] 是 False，但 () is () 是 True——空元组是被缓存的单例。",
     "Python 冷知识", "", ""),
    ("Python 3.8+ 海象运算符 := 可在表达式里赋值：while (n := next(it)) is not None:。",
     "Python 语法", "", ""),
    ("functools.lru_cache 一行加缓存，调试性能优化首选。",
     "Python 标准库", "", ""),

    # 正则
    ("(?P<name>...) 是命名捕获组；m.group('name') 比按序号取更可读。",
     "正则技巧", "", ""),
    ("正则中 .*? 是「懒匹配」，碰到第一个满足条件的位置就停，避免贪婪吃过界。",
     "正则技巧", "", ""),
    ("(?=foo) 前瞻断言不消耗字符；(?<=foo) 后瞻断言匹配「在 foo 后面的位置」。",
     "正则技巧", "", ""),

    # HTTP / Web
    ("HTTP 状态码 418 是真实存在的：I'm a teapot——RFC 2324 的茶壶协议彩蛋。",
     "Web 冷知识", "", ""),
    ("HTTP 304 Not Modified 没有响应体——浏览器复用本地缓存，省流量。",
     "Web 冷知识", "", ""),
    ("Cookie 三件套：HttpOnly 防 XSS 偷，Secure 强制 HTTPS，SameSite 防 CSRF。",
     "Web 安全", "", ""),
    ("CORS 不是「禁止跨域请求」——请求总能发出去，只是 JS 读不到响应。",
     "Web 冷知识", "", ""),

    # 网络
    ("TCP 三次握手：SYN → SYN-ACK → ACK；四次挥手才能优雅断开。",
     "网络基础", "", ""),
    ("DNS 默认走 UDP 53，响应超过 512 字节会回退到 TCP。",
     "网络冷知识", "", ""),
    ("IPv4 地址 32 位 ≈ 42 亿，1998 年就有人喊不够用，现在靠 NAT 撑着。",
     "网络冷知识", "", ""),
    ("traceroute 的工作原理：发 TTL=1, 2, 3... 的包，每一跳的路由器都得回 ICMP。",
     "网络冷知识", "", ""),

    # 历史
    ("「bug」一词出处：1947 年 Grace Hopper 在 Mark II 计算机里抓到一只飞蛾，贴进了日志本。",
     "编程史", "", ""),
    ("JavaScript 是 Brendan Eich 在 1995 年用 10 天写出来的——名字蹭 Java 的热度。",
     "编程史", "", ""),
    ("Python 命名灵感是 Monty Python 喜剧团，不是蛇——文档里早期梗特别多。",
     "编程史", "", ""),
    ("Unix 纪元 1970-01-01 00:00:00 UTC，32 位 time_t 会在 2038-01-19 溢出（Y2K38）。",
     "编程史", "", ""),
    ("Linux 内核第一版 1991 年发布，作者邮件原话：「只是个爱好，不会大也不会专业」。",
     "编程史", "", ""),

    # 字符编码
    ("UTF-8 是变长 1–4 字节，前 128 个码点跟 ASCII 完全相同——所以英文文档跨编码也安全。",
     "字符编码", "", ""),
    ("ASCII 中 'A'=65, 'a'=97，差 32（0x20）；这一位就是 case bit，按位翻转能转大小写。",
     "字符编码", "", ""),
    ("Unicode BOM (U+FEFF) 在 UTF-8 里是字节 EF BB BF——不少 bug 是它隐式出现搞的。",
     "字符编码", "", ""),

    # 算法 / 数据结构
    ("Quicksort 平均 O(n log n)，最坏 O(n²)；现代标准库通常用 Introsort 切换到 heapsort 保底。",
     "算法", "", ""),
    ("Hash table 的 load factor 一般 0.7 左右；超过就触发 rehash，所以 insert 偶尔会很慢。",
     "数据结构", "", ""),
    ("Bloom filter 能用很少的内存判断「肯定不在集合」或「可能在」——CDN、爬虫去重的常客。",
     "数据结构", "", ""),
    ("Skip list 用概率代替平衡——Redis 的 sorted set 就是它的实现。",
     "数据结构", "", ""),

    # 工具 / IDE
    ("VS Code 中 Ctrl+P 模糊找文件，Ctrl+Shift+P 打开命令面板——80% 操作都不需要鼠标。",
     "VS Code", "", ""),
    ("VS Code 的 Alt+Click 加多光标，Ctrl+Alt+Down 在下方追加；批量改名超快。",
     "VS Code", "", ""),
    ("tmux 的 Ctrl+B z 把当前 pane 临时放大成全屏，再按一次还原。",
     "tmux 提示", "", ""),

    # 系统
    ("Linux 的 /proc/<pid>/fd/ 能看到一个进程打开的所有文件描述符——调试卡死神器。",
     "Linux 系统", "", ""),
    ("strace -p <pid> 实时看一个进程在调啥系统调用；卡在哪儿一目了然。",
     "Linux 系统", "", ""),
    ("kill -0 <pid> 不真杀，只检查进程是否存在——shell 脚本里探活用。",
     "Linux 系统", "", ""),

    # 类型 / 软件工程
    ("函数返回 Result 而不是抛异常，调用方就必须显式处理失败——Rust 推广开的范式。",
     "软件工程", "", ""),
    ("「先让它跑通，再让它跑对，最后再让它跑快」——Kent Beck 的工程节奏。",
     "软件工程", "", ""),
    ("命名是计算机科学两大难题之一，另一个是缓存失效——Phil Karlton 名言。",
     "软件工程", "", ""),

    # AI / LLM 基础
    ("GPT 三个字母：Generative（生成）、Pre-trained（预训练）、Transformer（架构）。",
     "AI 名词", "", ""),
    ("Transformer 出自 2017 年 Google 论文《Attention Is All You Need》——彻底淘汰了 RNN。",
     "AI 历史", "", ""),
    ("BERT 是 encoder-only，GPT 是 decoder-only，T5 是 encoder+decoder——三种范式同时存在。",
     "AI 架构", "", ""),
    ("LLM 的 temperature=0 是确定性输出，>1 越来越随机；写代码常用 0.2 左右。",
     "LLM 调参", "", ""),
    ("top_p=0.9 表示「从累计概率 90% 的候选里采样」，比 top_k 更自适应。",
     "LLM 调参", "", ""),
    ("KV cache 让 Transformer 推理时不必重算前面的 token，长上下文的关键优化。",
     "LLM 推理", "", ""),

    # AI 应用与技巧
    ("Chain of Thought：让模型「一步步想」能显著提升数学和推理题正确率。",
     "Prompt 技巧", "", ""),
    ("Few-shot：prompt 里放 3-5 个示例，模型几乎可以零样本学会新任务。",
     "Prompt 技巧", "", ""),
    ("RAG = Retrieval-Augmented Generation：先检索文档，再让 LLM 生成；解决知识过时和私有数据。",
     "AI 应用", "", ""),
    ("Embedding 把文本变成几百到几千维的向量，语义相近的向量在余弦距离上靠得近。",
     "AI 基础", "", ""),
    ("Fine-tuning 修改模型权重；RAG 只改输入。前者贵且慢，后者灵活且可解释。",
     "AI 工程", "", ""),
    ("LoRA：在大模型旁边训一组小矩阵，参数量从 70B 降到 0.1B，单卡就能微调。",
     "AI 工程", "", ""),

    # AI 风险 / 局限
    ("Hallucination（幻觉）：LLM 优化的是「听起来对」而非「实际对」，所以会自信地编造。",
     "AI 局限", "", ""),
    ("Prompt Injection 是 LLM 应用的头号安全风险——用户输入可以覆盖系统指令。",
     "AI 安全", "", ""),
    ("「Stochastic Parrot」（随机鹦鹉）是 LLM 怀疑论者著名比喻：再大的模型也只是高级模仿。",
     "AI 哲学", "", ""),
    ("Context window 不是越大越好——模型注意力容易在长上下文里「中间迷失」。",
     "AI 局限", "", ""),

    # AI 名场面
    ("AlphaGo 2016 年战胜李世石；AlphaGo Zero 2017 年不学人类棋谱，自我对弈 3 天就反超。",
     "AI 历史", "", ""),
    ("Diffusion model 从纯噪声反向去噪生成图像；Stable Diffusion / DALL-E / Midjourney 同源。",
     "AI 架构", "", ""),
    ("MoE（专家混合）：一个 token 只激活几个专家子网络，总参数大、单次计算却小。",
     "AI 架构", "", ""),
    ("Rich Sutton《Bitter Lesson》：长期来看，更多算力 + 更多数据，比任何聪明算法都强。",
     "AI 哲学", "", ""),
    ("\"Artificial Intelligence\" 这个词在 1956 年 Dartmouth 暑期研讨会上首次被提出。",
     "AI 历史", "", ""),

    # Anthropic / Claude
    ("Constitutional AI 是 Anthropic 的对齐方案：让 AI 用一组原则自我批评，替代部分 RLHF。",
     "Anthropic", "", ""),
    ("MCP（Model Context Protocol）：Anthropic 2024 年提出的标准，让 LLM 调工具像调 API 一样统一。",
     "Anthropic", "", ""),
    ("Claude 的 Opus / Sonnet / Haiku 是按罗马诗体命名的：长诗、十四行、短诗——分别对应能力档位。",
     "Anthropic", "", ""),
    ("Prompt caching：把不变的系统提示哈希存住，下次调 API 不收费——长文档场景能省 90%。",
     "Claude API", "", ""),
]


def pick_for(d: date | None = None) -> tuple[str, str, str, str]:
    """Deterministic rotation: a new tip every 2 hours.

    Uses wall-clock seconds // ROTATION_SECONDS as the slot index so all
    desk-card renders within the same 2-hour window show the same tip.
    """
    slot = int(time.time()) // ROTATION_SECONDS
    h = hashlib.sha256(str(slot).encode()).digest()
    idx = int.from_bytes(h[:4], "big") % len(QUOTES)
    return QUOTES[idx]
