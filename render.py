"""Desk Card renderer — JSON in, PNG out (1404x1872 for Likebook K78W)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import usage_reader
import weather_api
import quotes
import todos as todos_module

try:
    import cnlunar  # type: ignore
except ImportError:
    cnlunar = None

W, H = 1404, 1872
MARGIN = 90
BLACK, WHITE = 0, 255
GREY = 90
CHIP_BG = 0xD8        # 浅灰 code-chip 底色（GitHub inline-code 风）；e-ink 上配黑描边保边界

if sys.platform == "darwin":
    # macOS：宋体/楷体/Segoe Script 等 Windows 字体我们从 Win 复制到 ~/Library/Fonts/；
    # 黑体走系统自带的 Hiragino Sans GB；等宽走 Menlo。
    # .ttc 必须显式指定 index 拿对字重 —— Songti SC Black (idx=0) 不含 〇 (U+3007)，
    # 用 idx=6 (SC Regular) 才能正常渲染年份；Hiragino idx=0=W3, idx=1=W6。
    _MAC_USER_FONTS = str(Path.home() / "Library" / "Fonts")
    _SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
    _HIRAGINO = "/System/Library/Fonts/Hiragino Sans GB.ttc"
    _MENLO = "/System/Library/Fonts/Menlo.ttc"
    FONTS = {
        "sans":       (_HIRAGINO, 0),       # W3 Regular
        # sans_bold 故意用 W3 而不是 W6：Hiragino W6 比 Win 端 msyhbd 粗得多，
        # 会挤占大时钟两侧的天气列空间。Mac 上没有 medium 字重，W3 视觉更接近原排版。
        "sans_bold":  (_HIRAGINO, 0),
        "sans_light": "/System/Library/Fonts/STHeiti Light.ttc",
        "serif":      (_SONGTI, 6),         # SC Regular，含 〇
        "serif_zh":   (_SONGTI, 6),
        "kai":        f"{_MAC_USER_FONTS}/STKAITI.TTF",
        "quote_body": (_SONGTI, 6),
        "quote_attr": f"{_MAC_USER_FONTS}/STKAITI.TTF",
        "geo":        f"{_MAC_USER_FONTS}/segoescb.ttf",
        "geo_b":      f"{_MAC_USER_FONTS}/segoescb.ttf",
        "geo_i":      f"{_MAC_USER_FONTS}/segoescb.ttf",
        "mono":       (_MENLO, 0),          # Regular
        "mono_bold":  (_MENLO, 1),          # Bold
    }
else:
    FONTS = {
        "sans":       r"C:\Windows\Fonts\msyh.ttc",
        "sans_bold":  r"C:\Windows\Fonts\msyhbd.ttc",
        "sans_light": r"C:\Windows\Fonts\msyhl.ttc",
        "serif":      r"C:\Windows\Fonts\STSONG.TTF",
        "serif_zh":   r"C:\Windows\Fonts\STZHONGS.TTF",
        "kai":        r"C:\Windows\Fonts\STKAITI.TTF",
        # 书摘专用：正文沉稳书页感（华文中宋），署名走手写题字感（楷体小字）
        "quote_body": r"C:\Windows\Fonts\STZHONGS.TTF",
        "quote_attr": r"C:\Windows\Fonts\STKAITI.TTF",
        # English: single connected script (Segoe Script Bold) for visual consistency
        "geo":        r"C:\Windows\Fonts\segoescb.ttf",
        "geo_b":      r"C:\Windows\Fonts\segoescb.ttf",
        "geo_i":      r"C:\Windows\Fonts\segoescb.ttf",
        "mono":       r"C:\Windows\Fonts\consola.ttf",
        "mono_bold":  r"C:\Windows\Fonts\consolab.ttf",
    }

# Per-render font overrides (set by render() when payload has a "fonts" dict).
_FONT_OVERRIDES: dict[str, str] = {}

# Module-level reference to the current PIL image during a render call so deep
# helpers (e.g. _draw_usage_row → Clawd marker overlay) can paste sprites.
_CURRENT_IMG: Image.Image | None = None

CN_MONTH = "一二三四五六七八九十"
CN_NUM = "〇一二三四五六七八九"
WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

# 农历 / 节气文本中可能出现的简繁差异字。专为 _lunar_line 输出做简体→繁体转换，
# 不涉及其他界面文本（保持英文 + 简体混排不变）。
_S2T = str.maketrans({
    "龙": "龍", "马": "馬", "鸡": "雞", "猪": "豬",      # 生肖
    "惊": "驚", "蛰": "蟄", "谷": "穀", "满": "滿",      # 节气
    "种": "種", "处": "處",                              # 节气续
    "腊": "臘", "闰": "閏",                              # 农历月名
    "节": "節", "气": "氣", "余": "餘",                  # 其他词
})


def _s2t(s: str) -> str:
    return s.translate(_S2T)


# ---- Pixel-art weather icons (matching Clawd's monochrome shadow-puppet style) ----
WEATHER_ICONS = {
    "SUN": [
        ".....#.....",
        ".....#.....",
        ".#...#...#.",
        "...#####...",
        "..#######..",
        ".#########.",
        "###########",
        ".#########.",
        "..#######..",
        "...#####...",
        ".#...#...#.",
        ".....#.....",
        ".....#.....",
    ],
    "CLOUD": [
        "......######......",
        "....##########....",
        "...############...",
        ".###############..",
        "##################",
        "##################",
        "##################",
        ".################.",
        "..##############..",
        "....##########....",
    ],
    "SUN_CLOUD": [
        "...#..........",
        "...#...####...",
        "#..#..######..",
        ".#####.####...",
        "..####.####...",
        "...##.###.####",
        "..#############",
        ".###############",
        "################",
        "################",
        ".##############.",
        "...############.",
    ],
    "RAIN": [
        "......######......",
        "....##########....",
        "...############...",
        ".###############..",
        "##################",
        "##################",
        "##################",
        ".################.",
        "..##############..",
        "..................",
        "..#....#....#...#.",
        ".#....#....#...#..",
        "#....#....#...#...",
    ],
    "SNOW": [
        "......######......",
        "....##########....",
        "...############...",
        ".###############..",
        "##################",
        "##################",
        "##################",
        ".################.",
        "..##############..",
        "..................",
        "..#...#...#...#...",
        ".###.###.###.###..",
        "..#...#...#...#...",
    ],
    "HAZE": [
        "...########...",
        "..##########..",
        "##############",
        ".############.",
        "..............",
        ".############.",
        "##############",
        ".############.",
        "..............",
        "...########...",
        "..##########..",
    ],
}

SKYCON_TO_ICON = {
    "CLEAR_DAY": "SUN",
    "CLEAR_NIGHT": "SUN",
    "PARTLY_CLOUDY_DAY": "SUN_CLOUD",
    "PARTLY_CLOUDY_NIGHT": "SUN_CLOUD",
    "CLOUDY": "CLOUD",
    "LIGHT_HAZE": "HAZE",
    "MODERATE_HAZE": "HAZE",
    "HEAVY_HAZE": "HAZE",
    "LIGHT_RAIN": "RAIN",
    "MODERATE_RAIN": "RAIN",
    "HEAVY_RAIN": "RAIN",
    "STORM_RAIN": "RAIN",
    "FOG": "HAZE",
    "LIGHT_SNOW": "SNOW",
    "MODERATE_SNOW": "SNOW",
    "HEAVY_SNOW": "SNOW",
    "STORM_SNOW": "SNOW",
    "DUST": "HAZE",
    "SAND": "HAZE",
    "WIND": "CLOUD",
}


def draw_skycon_icon(d: "ImageDraw.ImageDraw", *, x_right: int, y: int,
                     skycon: str, scale: int = 7) -> int:
    """Draw a pixel-art weather icon right-aligned at x_right.
    Returns the icon's WIDTH so callers can lay out adjacent text."""
    icon_name = SKYCON_TO_ICON.get(skycon or "")
    if not icon_name:
        return 0
    grid = WEATHER_ICONS.get(icon_name)
    if not grid:
        return 0
    rows = len(grid)
    cols = max(len(row) for row in grid)
    icon_w = cols * scale
    icon_h = rows * scale
    x_start = x_right - icon_w
    for ry, row in enumerate(grid):
        for cx, ch in enumerate(row.ljust(cols, ".")):
            if ch != "#":
                continue
            x0 = x_start + cx * scale
            y0 = y + ry * scale
            d.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=BLACK)
    return icon_w


def f(key: str, size: int) -> ImageFont.FreeTypeFont:
    """Resolve a font by logical key; checks per-render overrides first.

    FONTS / _FONT_OVERRIDES values may be a plain path string or a
    ``(path, index)`` tuple for .ttc collections where the default index=0
    sub-font lacks needed glyphs (e.g. macOS Songti SC Black is missing 〇).
    """
    entry = _FONT_OVERRIDES.get(key) or FONTS[key]
    if isinstance(entry, tuple):
        path, idx = entry
        return ImageFont.truetype(path, size, index=idx)
    return ImageFont.truetype(entry, size)


def cn_day(n: int) -> str:
    """1..31 → 一/二.../十一/.../三十一."""
    if n < 10:
        return CN_NUM[n]
    if n < 20:
        return "十" + (CN_NUM[n - 10] if n > 10 else "")
    tens, ones = divmod(n, 10)
    return CN_NUM[tens] + "十" + (CN_NUM[ones] if ones else "")


def cn_month(n: int) -> str:
    return (CN_MONTH[n - 1] if n <= 10 else "十" + (CN_MONTH[n - 11] if n > 10 else "")) + "月"


def hrule(d: ImageDraw.ImageDraw, y: int, x1: int = MARGIN, x2: int = W - MARGIN, width: int = 2):
    d.line([(x1, y), (x2, y)], fill=BLACK, width=width)


def double_rule(d: ImageDraw.ImageDraw, y: int, gap: int = 6, thick: int = 3, thin: int = 1, **kw):
    hrule(d, y, width=thick, **kw)
    hrule(d, y + gap + thick, width=thin, **kw)


def double_rule_thin_thick(d: ImageDraw.ImageDraw, y: int, gap: int = 6, thin: int = 1, thick: int = 3, **kw):
    hrule(d, y, width=thin, **kw)
    hrule(d, y + gap + thin, width=thick, **kw)


def text_w(d: ImageDraw.ImageDraw, s: str, font) -> int:
    b = d.textbbox((0, 0), s, font=font)
    return b[2] - b[0]


def draw_spaced(d: ImageDraw.ImageDraw, xy, text: str, font, fill=BLACK, spacing: int = 12):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += text_w(d, ch, font) + spacing
    return x


def draw_centered(d: ImageDraw.ImageDraw, y: int, text: str, font, fill=BLACK):
    w = text_w(d, text, font)
    d.text(((W - w) // 2, y), text, font=font, fill=fill)


def draw_masthead(d: ImageDraw.ImageDraw, now: datetime, issue: str) -> int:
    """Top: double rule, masthead text, double rule."""
    top = 64
    double_rule(d, top, gap=4, thick=3, thin=1)

    band_y = top + 16
    left = "Desk · Card"
    mid_date = now.strftime("%b %d, %Y")
    right = f"No. {issue}"
    f_mast = f("geo_b", 48)
    f_mid = f("geo_i", 36)

    d.text((MARGIN, band_y), left, font=f_mast, fill=BLACK)
    mw = text_w(d, mid_date, f_mid)
    d.text(((W - mw) // 2, band_y + 14), mid_date, font=f_mid, fill=BLACK)
    rw = text_w(d, right, f_mid)
    d.text((W - MARGIN - rw, band_y + 14), right, font=f_mid, fill=BLACK)

    bottom_rule_y = band_y + 78
    double_rule_thin_thick(d, bottom_rule_y, gap=4, thin=1, thick=3)
    return bottom_rule_y + 26


def draw_time_band(d: ImageDraw.ImageDraw, now: datetime, y: int, *,
                   bake_time: bool = True) -> int:
    """Massive sans-serif HH:MM centered, with weather flanks on L/R, then Chinese date + lunar.

    `y` must stay 194 to match the APK's hard-coded clock overlay — it can't be
    moved up without rebuilding the APK, so removing the masthead just leaves
    the 0–194 strip above the clock blank. If `bake_time` is False we still
    compute the time bbox (so the weather flanks + date below position
    correctly) but skip drawing the digits — the APK paints the live clock as a
    TextView overlay there.
    """
    f_time = f("sans_bold", 280)
    time_str = now.strftime("%H:%M")
    tw = text_w(d, time_str, f_time)
    tx = (W - tw) // 2
    tb = d.textbbox((tx, y), time_str, font=f_time)
    if bake_time:
        d.text((tx, y), time_str, font=f_time, fill=BLACK)
    time_bottom = tb[3]

    # Weather flanks: left and right of the time digits
    _draw_weather_flanks(d, y, time_left=tb[0], time_right=tb[2])

    # 中文日期在时钟下方。下限 = 时钟起笔 y + overlay 盒高(300) + 余量，确保落在
    # APK 时钟 overlay 底边之下、不被白底盖住。
    y2 = max(time_bottom + 38, y + 308)
    date_text = f"二〇{cn_year_short(now.year)} 年 {cn_month(now.month)} {cn_day(now.day)} 日 · 星期{WEEKDAYS[now.weekday()]}"
    f_date = f("serif_zh", 38)
    spacing = 10
    total_w = sum(text_w(d, ch, f_date) + spacing for ch in date_text) - spacing
    draw_spaced(d, ((W - total_w) // 2, y2), date_text, f_date, spacing=spacing)

    # Lunar line
    y3 = y2 + 56
    lunar = _lunar_line(now)
    if lunar:
        # 换中宋 + 加大 + 字色加深，e-ink 上更清晰
        f_lunar = f("serif_zh", 34)
        lspacing = 8
        lw = sum(text_w(d, ch, f_lunar) + lspacing for ch in lunar) - lspacing
        draw_spaced(d, ((W - lw) // 2, y3), lunar, f_lunar, fill=50, spacing=lspacing)
        y_rule = y3 + 56
    else:
        y_rule = y2 + 70

    hrule(d, y_rule, width=1)
    return y_rule + 28


def _lunar_line(now: datetime) -> str:
    if cnlunar is None:
        return ""
    try:
        l = cnlunar.Lunar(now, godType="8char")
    except Exception:
        return ""
    parts = [
        f"{l.year8Char}{l.chineseYearZodiac}年",
        l.lunarMonthCn.rstrip("大小") + l.lunarDayCn,
    ]
    # If today is a solar term, show it; otherwise show next one with distance.
    today_term = getattr(l, "todaySolarTerms", "")
    if today_term and today_term != "无":
        parts.append(f"节气 · {today_term}")
    else:
        nxt = getattr(l, "nextSolarTerm", None)
        nd = getattr(l, "nextSolarTermDate", None)
        ny = getattr(l, "nextSolarTermYear", None)
        if nxt and nd and ny:
            try:
                target = datetime(ny, nd[0], nd[1])
                days = (target.date() - now.date()).days
                if days >= 0:
                    parts.append(f"次{nxt} · 余 {cn_day(days)} 日")
            except Exception:
                pass
    return _s2t("  ·  ".join(parts))



def cn_year_short(y: int) -> str:
    s = str(y)[2:]
    return "".join(CN_NUM[int(c)] for c in s)


def _draw_usage_section_header(d: ImageDraw.ImageDraw, y: int,
                               en: str, right_meta: str | None,
                               logo_key: str | None = None) -> int:
    """Section header: [logo] + name as a mono "code chip" (left) + meta (right) + hrule.

    Name is set in mono_bold inside a light-grey rounded chip (GitHub inline-code
    look), preceded by the agent's app logo when ``logo_key`` is given.
    """
    f_chip = f("mono_bold", 28)
    row_h = 92           # 行加高以容纳放大后的 logo（约原 2 倍）
    logo_sz = 88         # logo ~2x（原 48）
    x = MARGIN

    # Agent app-logo, square, vertically centered in the (taller) row.
    if logo_key and _CURRENT_IMG is not None:
        ly = y + (row_h - logo_sz) // 2
        lw = draw_logo(_CURRENT_IMG, x, ly, logo_sz, logo_key)
        if lw:
            x += lw + 18

    # Section name as a mono code-chip: light-grey rounded bg + thin black edge
    # (e-ink can't render the grey fill reliably alone) + black bold text.
    asc, desc = f_chip.getmetrics()
    pad_x, pad_y = 16, 8
    chip_h = asc + desc + pad_y * 2
    chip_y = y + (row_h - chip_h) // 2
    tw = text_w(d, en, f_chip)
    d.rounded_rectangle([x, chip_y, x + tw + pad_x * 2, chip_y + chip_h],
                        radius=12, fill=CHIP_BG, outline=BLACK, width=1)
    d.text((x + pad_x, chip_y + pad_y), en, font=f_chip, fill=BLACK)

    # plan（max/plus/pro）紧跟 chip 右侧、放大、垂直居中，比原来右上角小灰字醒目；
    # 长说明（如 codex 的 "(local · …)" 标注）仍放右上角小字，避免大字挤占整行。
    if right_meta:
        if len(right_meta) <= 6 and " " not in right_meta:
            f_plan = f("mono_bold", 32)
            chip_x2 = x + tw + pad_x * 2
            ma, md = f_plan.getmetrics()
            d.text((chip_x2 + 18, y + (row_h - (ma + md)) // 2),
                   right_meta, font=f_plan, fill=50)
        else:
            f_meta = f("mono", 20)
            rw = text_w(d, right_meta, f_meta)
            d.text((W - MARGIN - rw, y + (row_h - 22) // 2 + 2),
                   right_meta, font=f_meta, fill=GREY)

    y += row_h
    hrule(d, y, width=1)
    return y + 10


def draw_big_usage(d: ImageDraw.ImageDraw, y: int, *,
                   show_extra: bool = False,
                   show_codex: bool = True,
                   codex_quota_5h: int | None = None,
                   codex_quota_7d: int | None = None,
                   **_) -> int:
    """Compact dual-agent usage widget: Claude Code + Codex CLI.

    Claude rows use the official Anthropic OAuth pct + reset time (with Clawd
    riding the bar). Codex rows use local ~/.codex/state_5.sqlite token counts
    against a soft quota — labelled ``(local)`` since OpenAI exposes no
    account-level usage endpoint."""

    # ---- Claude ----
    official = usage_reader.read_official() or {}
    plan = official.get("plan")

    try:
        local = usage_reader.scan(window_hours=(5, 168))
    except Exception:
        local = {}
    msg_5h = (local.get(5) or {}).get("messages", 0)
    msg_7d = (local.get(168) or {}).get("messages", 0)

    y = _draw_usage_section_header(d, y, "Claude Code", plan, logo_key="claude")

    y = _draw_usage_row(d, y,
                        label_en="Current Session",
                        pct=official.get("five_hour_pct"),
                        right_lines=_reset_lines(official.get("five_hour_reset_at"), fmt="hm"),
                        extra=f"{msg_5h} msg (local)")

    y = _draw_usage_row(d, y,
                        label_en="Weekly Limits",
                        pct=official.get("seven_day_pct"),
                        right_lines=_reset_lines(official.get("seven_day_reset_at"), fmt="dh"),
                        extra=f"{msg_7d} msg total (local)")

    # ---- Codex ----
    if show_codex:
        codex = usage_reader.read_codex(window_hours=(5, 168),
                                        quota_5h=codex_quota_5h,
                                        quota_7d=codex_quota_7d)
        source = codex.get("source", "none")
        c5 = codex.get(5) or {}
        c7 = codex.get(168) or {}

        model = codex.get("model") or "gpt-5"
        if source == "oauth":
            header_meta = codex.get("plan")
            right_5h = _reset_lines(c5.get("reset_at"), fmt="hm")
            right_7d = _reset_lines(c7.get("reset_at"), fmt="dh")
            extra_5h = f"{model}  ·  chatgpt subscription"
            extra_7d = "real account-level usage"
        else:
            header_meta = "(local · this machine only)"
            right_5h = _codex_right_lines(c5)
            right_7d = _codex_right_lines(c7)
            extra_5h = f"{model}  ·  soft cap {usage_reader.fmt_tokens(c5.get('quota') or 0)} tok"
            extra_7d = f"soft cap {usage_reader.fmt_tokens(c7.get('quota') or 0)} tok  ·  not authoritative"

        y += 46
        y = _draw_usage_section_header(d, y, "Codex", header_meta, logo_key="codex")

        y = _draw_usage_row(d, y,
                            label_en="Current Session",
                            pct=c5.get("pct"),
                            right_lines=right_5h,
                            extra=extra_5h,
                            show_clawd=False)

        y = _draw_usage_row(d, y,
                            label_en="Weekly Limits",
                            pct=c7.get("pct"),
                            right_lines=right_7d,
                            extra=extra_7d,
                            show_clawd=False)

    # ---- Extra credits (opt-in, rare) ----
    extra_usage = official.get("extra_usage") or {}
    if show_extra and extra_usage.get("enabled") and extra_usage.get("pct") is not None:
        used = extra_usage.get("used_credits") or 0
        limit = extra_usage.get("monthly_limit") or 0
        cur = extra_usage.get("currency") or "USD"
        right_lines = (
            "monthly cap",
            f"${used:.0f} / ${limit:.0f}",
            f"{cur}",
        )
        y += 12
        y = _draw_usage_row(d, y,
                            label_en="Extra  Credits",
                            pct=extra_usage.get("pct"),
                            right_lines=right_lines,
                            extra="overflow / pay-as-you-go")
    return y


def _codex_right_lines(c: dict) -> tuple[str, str, str]:
    """3-line right block for a Codex window: tokens label / token count / thread count."""
    if not c:
        return ("tokens", "—", "—")
    tokens = c.get("tokens") or 0
    threads = c.get("threads") or 0
    return ("tokens", usage_reader.fmt_tokens(tokens), f"{threads} threads")


def _reset_lines(reset_at, *, fmt: str) -> tuple[str, str, str]:
    """Three lines for the right side: label, time, countdown."""
    from datetime import datetime, timezone
    if not reset_at:
        return ("resets at", "—", "—")
    now = datetime.now(timezone.utc)
    delta = reset_at - now
    local_reset = reset_at.astimezone()
    if fmt == "dh":
        countdown = usage_reader.fmt_elapsed_dh(delta)
        time_str = local_reset.strftime("%a  %H:%M")
    else:
        countdown = usage_reader.fmt_elapsed_hm(delta)
        time_str = local_reset.strftime("%H:%M")
    return ("resets at", time_str, f"in {countdown}")


def _draw_usage_row(d: ImageDraw.ImageDraw, y: int, *, label_en: str,
                    pct, right_lines: tuple, extra: str,
                    show_clawd: bool = True) -> int:
    """Compact usage row: label + huge %, 3-line right block, progress bar.

    Layout (~192 px with Clawd, ~168 px without):
        [label]                          [r_top]
        [42 %]                           [r_mid]
                                         [r_bot]
        (clawd reserve, optional)
        [============ bar ============]
        [extra]
    """
    # 用量区英文/数字统一走等宽 mono（Menlo）—— 比 Segoe Script 花体好辨认。
    f_label_en = f("mono_bold", 27)   # was geo_b 30
    f_pct = f("mono_bold", 46)        # 大百分比数字
    f_pct_sign = f("mono_bold", 22)   # was 32
    f_r_top = f("mono", 23)           # "resets at" caption
    f_r_mid = f("mono_bold", 33)      # 时间数字 14:20 / Wed 19:00
    f_r_bot = f("mono", 25)           # "in 4h 23m"
    f_extra = f("mono", 22)           # "380 msg (local)" caption

    right_x = W - MARGIN
    top_s, mid_s, bot_s = right_lines

    # Sub-row 1: label_en (left) + right_top (right, small caption)
    d.text((MARGIN, y), label_en, font=f_label_en, fill=BLACK)
    d.text((right_x - text_w(d, top_s, f_r_top), y + 6),
           top_s, font=f_r_top, fill=GREY)
    y += 36

    # Pct normalization
    if pct is None:
        pct_str = "—"
        pct_norm = 0.0
    else:
        pct_str = f"{int(round(pct))}"
        pct_norm = max(0.0, min(1.0, pct / 100.0))

    # Sub-row 2: huge pct (left) + right_mid (right, medium emphasis)
    pw = text_w(d, pct_str, f_pct)
    px = MARGIN + 12
    d.text((px, y), pct_str, font=f_pct, fill=BLACK)
    if pct is not None:
        d.text((px + pw + 4, y + 14), "%", font=f_pct_sign, fill=GREY)
    d.text((right_x - text_w(d, mid_s, f_r_mid), y + 2),
           mid_s, font=f_r_mid, fill=BLACK)
    y += 46

    # Sub-row 3: right_bot only
    d.text((right_x - text_w(d, bot_s, f_r_bot), y),
           bot_s, font=f_r_bot, fill=BLACK)
    y += 22

    # Clawd reserve (Claude rows only); Codex rows still get a small gap so
    # the bar doesn't crowd the right_bot text.
    y += 26 if show_clawd else 14

    # Progress bar
    bar_x1, bar_x2 = MARGIN, W - MARGIN
    bar_h = 16
    d.rectangle([bar_x1, y, bar_x2, y + bar_h], outline=BLACK, width=2)
    fill_x = bar_x1 + int((bar_x2 - bar_x1) * pct_norm)
    if fill_x > bar_x1 + 2:
        d.rectangle([bar_x1 + 2, y + 2, fill_x, y + bar_h - 2], fill=BLACK)

    if show_clawd and _CURRENT_IMG is not None and pct is not None:
        # Clawd rides the bar for Claude rows.
        clawd_h = 34
        clawd_w_est = int(clawd_h * 236 / 166)
        marker_x = bar_x1 + int((bar_x2 - bar_x1) * pct_norm) - clawd_w_est // 2
        marker_x = max(bar_x1, min(bar_x2 - clawd_w_est, marker_x))
        marker_y = y - clawd_h + 3
        draw_clawd(_CURRENT_IMG, d, x=marker_x, y=marker_y, size=clawd_h)
    elif not show_clawd and pct is not None:
        # Codex rows: simple solid triangle pointer above the bar at the fill edge.
        tip_x = bar_x1 + int((bar_x2 - bar_x1) * pct_norm)
        tip_x = max(bar_x1 + 6, min(bar_x2 - 6, tip_x))
        d.polygon(
            [(tip_x - 6, y - 9), (tip_x + 6, y - 9), (tip_x, y - 1)],
            fill=BLACK,
        )

    # Extra small line below the bar
    d.text((MARGIN + 12, y + bar_h + 5), extra, font=f_extra, fill=GREY)

    # Return the y *below* the extra line — extra glyphs (~28 px tall for the
    # 24 px italic) need clearance, otherwise the next row's label overprints.
    return y + bar_h + 36


def _wrap_chinese(d: ImageDraw.ImageDraw, text: str, font, avail_w: int,
                  max_lines: int = 4) -> list[str]:
    """Per-character word wrap for CJK with hanging punctuation.

    End-of-sentence punctuation (。，？！；：、 etc.) never starts a new line —
    it gets glued onto the previous line, overhanging the right margin a bit.
    Truncates with ellipsis if the text doesn't fit within max_lines.
    """
    NO_LINE_START = "。，！？；：、）】」』·…—"
    lines: list[str] = []
    buf = ""
    for ch in text:
        trial = buf + ch
        if text_w(d, trial, font) <= avail_w:
            buf = trial
        else:
            # Would overflow — but if this char is a no-line-start punctuation,
            # let it hang on the current line rather than orphan it.
            if ch in NO_LINE_START and buf:
                buf = trial
            else:
                if buf:
                    lines.append(buf)
                buf = ch
    if buf:
        lines.append(buf)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and text_w(d, last + "…", font) > avail_w:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def draw_quote(d: ImageDraw.ImageDraw, y_top: int, y_bottom: int,
               *, x_left: int, x_right: int) -> None:
    """Book quote centered; attribution right-aligned at the bottom-right."""
    picked = quotes.pick_for()
    # tolerate both 3- and 4-tuple (older schema) shapes
    text = picked[0]
    author = picked[1] if len(picked) > 1 else ""
    work = picked[2] if len(picked) > 2 else ""
    year = picked[3] if len(picked) > 3 else ""

    avail_w = x_right - x_left - 60
    band_h = y_bottom - y_top

    # 自适应字号：从大到小挑能放进书摘带的最大字号 —— 短句用大字醒目，长句自动缩小
    # 正好塞进带内、不撞下方用量区；版式各项比例随字号同步缩放，始终协调。
    f_quote = f_author = None
    line_h = attr_gap = attr_line_h = 0
    lines: list[str] = []
    for q_size in (56, 52, 48, 44, 40, 36):
        f_quote = f("quote_body", q_size)
        f_author = f("quote_attr", round(q_size * 0.78))
        line_h = round(q_size * 1.32)
        attr_gap = round(q_size * 0.50)
        attr_line_h = round(q_size * 0.85)
        lines = _wrap_chinese(d, text, f_quote, avail_w, max_lines=2)
        total_h = line_h * len(lines) + attr_gap + attr_line_h
        if total_h <= band_h:
            break

    quote_h = line_h * len(lines)
    total_h = quote_h + attr_gap + attr_line_h
    start_y = y_top + max(0, (band_h - total_h) // 2)
    cx = (x_left + x_right) // 2

    # Quote — centered
    for i, line in enumerate(lines):
        lw = text_w(d, line, f_quote)
        d.text((cx - lw // 2, start_y + i * line_h), line, font=f_quote, fill=BLACK)

    # Attribution — right-aligned, author only.
    # e-ink 灰阶屏上 GREY=90 几乎隐形；用 30 比 BLACK 略淡以保层次但仍清晰可读。
    author_line = f"——  {author}"
    aw = text_w(d, author_line, f_author)
    d.text((x_right - aw, start_y + quote_h + attr_gap),
           author_line, font=f_author, fill=30)


def draw_notes(d: ImageDraw.ImageDraw, y_top: int, y_bottom: int,
               *, x_left: int, x_right: int) -> None:
    """Todo / notes board on the RIGHT half of the band.

    Reads ./todos.txt — edit that file and the card updates within a minute.
    """
    items = todos_module.load()
    if not items:
        return

    f_title = f("kai", 28)
    f_item = f("kai", 26)
    f_item_done = f("kai", 26)

    title = "便  签"
    title_h = 36
    item_h = 40
    avail_w = x_right - x_left
    max_items = max(0, (y_bottom - y_top - title_h - 16) // item_h)
    shown = items[:max_items] if max_items else []
    total_h = title_h + 16 + item_h * len(shown)
    band_h = y_bottom - y_top
    start_y = y_top + max(0, (band_h - total_h) // 2)

    # Title with thin underline
    tw = text_w(d, title, f_title)
    d.text((x_left, start_y), title, font=f_title, fill=BLACK)
    d.line([(x_left, start_y + 34), (x_left + tw + 12, start_y + 34)],
           fill=BLACK, width=1)

    # Items
    y = start_y + title_h + 12
    box = 20
    text_avail = avail_w - box - 14
    for it in shown:
        text = it["text"]
        done = it["done"]
        bx, by = x_left, y + 4
        # checkbox
        d.rectangle([bx, by, bx + box, by + box], outline=BLACK, width=2)
        if done:
            d.line([(bx + 5, by + box // 2), (bx + box // 2, by + box - 5)],
                   fill=BLACK, width=3)
            d.line([(bx + box // 2, by + box - 5), (bx + box - 3, by + 4)],
                   fill=BLACK, width=3)

        # text (truncate if too wide for the right column)
        wrapped = _wrap_chinese(d, text, f_item, text_avail, max_lines=1)
        text_str = wrapped[0] if wrapped else ""
        fill = GREY if done else BLACK
        d.text((bx + box + 12, y), text_str, font=f_item_done if done else f_item,
               fill=fill)
        if done and text_str:
            tw_done = text_w(d, text_str, f_item_done)
            sy = y + 18
            d.line([(bx + box + 12, sy), (bx + box + 12 + tw_done, sy)],
                   fill=GREY, width=2)

        y += item_h


def _draw_weather_flanks(d: ImageDraw.ImageDraw, y: int, *, time_left: int, time_right: int):
    """Weather data on left/right of the big time digits. Labels in Chinese (kai)."""
    w = weather_api.get_weather()
    if not w:
        return

    GAP = 24
    left_x_end = time_left - GAP
    right_x_start = time_right + GAP

    # E-ink 灰度屏上 sans_light 和 kai 都偏糊；换成华文中宋（笔画自然就实，
    # 已在书摘验证可接受）+ sans_bold 数字。所有数字（主温度、体感、右侧）
    # 共用同一字体族（sans_bold），与时间 17:58 一致；不再混用 sans 与 sans_bold。
    f_temp     = f("sans_bold", 96)     # 主温度
    f_temp_deg = f("sans_bold", 68)     # 度数符号：从 52→68，与主数字比例 1:1.4，不再"飘"
    f_label    = f("serif_zh", 32)      # 中文标签
    f_label_sm = f("serif_zh", 30)
    f_cond_zh  = f("serif_zh", 48)      # 天气状况 "晴/阴/雨"
    f_num      = f("sans_bold", 32)     # 所有小字数字（体感/最高最低/空气/湿度/日出日落）
    NUM_DY     = -2                     # 数字相对中文 label 的视觉基线微调，全局统一

    # ---------- LEFT: 大温度 + 体感 + 天气状况 ----------
    temp = w.get("temp")
    feels = w.get("feels")
    skycon = w.get("skycon")

    if temp is not None:
        temp_str = f"{round(temp)}"
        tw = text_w(d, temp_str, f_temp)
        tx = left_x_end - text_w(d, "°", f_temp_deg) - 6 - tw
        d.text((tx, y + 30), temp_str, font=f_temp, fill=BLACK)
        # ° 字号 68 时，与数字 96 的视觉对齐：° 顶部约对齐数字 x-height 起点
        d.text((tx + tw + 6, y + 36), "°", font=f_temp_deg, fill=BLACK)

    # 天气区灰度专用：GREY=90 在 e-ink 上接近隐形，本块统一加深到 50
    SOFT = 50

    # ---------- RIGHT: 高低温 · 空气 · 湿度 · 日出日落 (4 行) ----------
    items = []
    if w.get("today_max") is not None and w.get("today_min") is not None:
        items.append(("最高 ", f"{round(w['today_max'])}°",
                      "  最低 ", f"{round(w['today_min'])}°"))
    if w.get("aqi") is not None:
        items.append(("空气 ", f"{w['aqi']}",
                      " " + (w.get("aqi_desc") or ""), ""))
    if w.get("humidity") is not None:
        items.append(("湿度 ", f"{round(w['humidity'] * 100)}%", "", ""))
    # 日出 / 日落各占一行 —— 比合并到一行更舒展，也避免逼近右边距。
    if w.get("sunrise"):
        items.append(("日出 ", w["sunrise"], "", ""))
    if w.get("sunset"):
        items.append(("日落 ", w["sunset"], "", ""))

    line_h = 50
    rstart_y = y + 36
    # 可用右侧宽度：到画布右边距为止
    avail_w = (W - MARGIN) - right_x_start

    def _seg_is_num(seg: str) -> bool:
        # ⚠️ 不能用 c.isascii()：度数符号 ° 是 U+00B0，不在 ASCII 范围，
        # 否则 "25°" / "22°" 会被错判为非数字，用上中文宋体导致字体不一致。
        return all(c.isdigit() or c in "°%:.→ " for c in seg)

    # 全局统一字号：按最宽的一行决定，避免逐行字号不一致带来的视觉跳跃。
    max_row_w = 0
    for parts in items:
        rw = sum(text_w(d, seg, f_num if _seg_is_num(seg) else f_label)
                 for seg in parts if seg)
        max_row_w = max(max_row_w, rw)
    if max_row_w > avail_w:
        scale = avail_w / max_row_w
        sz = max(26, int(32 * scale))
        lbl_font = f("serif_zh", sz)
        # ⚠️ 必须用 sans_bold（与 f_num 同字体族）—— 旧代码这里用 f("sans", sz)
        # 在 Win 端（sans=msyhl light, sans_bold=msyhbd bold）会让数字突然变细，
        # 跟左侧体感、时间数字字体不一致。Mac 端虽然同字体但保持代码意图一致。
        num_font = f("sans_bold", sz)
    else:
        lbl_font = f_label
        num_font = f_num

    for i, parts in enumerate(items):
        ly = rstart_y + i * line_h
        x = right_x_start
        for j, seg in enumerate(parts):
            if not seg:
                continue
            is_num = _seg_is_num(seg)
            font_use = num_font if is_num else lbl_font
            fill = BLACK if (is_num or j == 0) else SOFT
            d.text((x, ly + (NUM_DY if is_num else 0)), seg, font=font_use, fill=fill)
            x += text_w(d, seg, font_use)

    # ---------- LEFT (续): 体感 + 天气状况 — 锚定到右侧基线 ----------
    # 5 行布局: [最高最低, 空气, 湿度, 日出, 日落]
    # 体感对齐第 3 行（湿度），多云对齐第 5 行（日落）。
    if feels is not None:
        s_zh = "体感  "
        s_num = f"{round(feels)}°"
        zw = text_w(d, s_zh, f_label_sm)
        nw = text_w(d, s_num, f_num)
        x0 = left_x_end - (zw + nw)
        y_feels = rstart_y + 2 * line_h  # 第 3 行（湿度）基线
        d.text((x0, y_feels), s_zh, font=f_label_sm, fill=SOFT)
        d.text((x0 + zw, y_feels + NUM_DY), s_num, font=f_num, fill=SOFT)

    cond_zh = weather_api.skycon_zh(skycon or "")
    if cond_zh:
        sw = text_w(d, cond_zh, f_cond_zh)
        y_cond = rstart_y + 4 * line_h - 12  # 第 5 行（日落）基线，48px 字号微上调以收齐底
        d.text((left_x_end - sw, y_cond), cond_zh, font=f_cond_zh, fill=BLACK)


def draw_weather(d: ImageDraw.ImageDraw, y: int) -> int:
    """Compact weather card: heading + big temp + secondary stats + one-line forecast.

    Notes on fonts: cursive Segoe Script doesn't have CJK glyphs; mix in kai/sans for
    anything containing Chinese (AQI level, skycon zh, forecast keypoint).
    """
    w = weather_api.get_weather()
    if not w:
        return y

    f_section_en = f("geo_b", 52)
    f_loc = f("geo_i", 34)
    f_temp = f("sans_light", 88)
    f_temp_deg = f("sans_light", 42)
    f_cond = f("geo_b", 42)
    f_cond_zh = f("kai", 34)
    f_feels = f("geo_i", 30)
    f_kv = f("geo_b", 28)
    f_kv_zh = f("kai", 26)
    f_kp = f("kai", 28)

    # Heading
    d.text((MARGIN, y), "Weather", font=f_section_en, fill=BLACK)
    hw = text_w(d, "Weather", f_section_en)
    loc = f"·  {w.get('location_name', '')}"
    d.text((MARGIN + hw + 14, y + 12), loc, font=f_loc, fill=GREY)
    y += 70
    hrule(d, y, width=1)
    y += 24

    # Big temp left, condition right
    temp = w.get("temp")
    feels = w.get("feels")
    skycon = w.get("skycon")

    temp_str = f"{round(temp)}" if temp is not None else "—"
    tw = text_w(d, temp_str, f_temp)
    px = MARGIN + 20
    d.text((px, y), temp_str, font=f_temp, fill=BLACK)
    d.text((px + tw + 6, y + 22), "°", font=f_temp_deg, fill=BLACK)
    if feels is not None:
        d.text((px + tw + 60, y + 50), f"feels  {round(feels)}°",
               font=f_feels, fill=GREY)

    cond_en = weather_api.skycon_en(skycon or "")
    cond_zh = weather_api.skycon_zh(skycon or "")
    right_x = W - MARGIN
    cw = text_w(d, cond_en, f_cond)
    d.text((right_x - cw, y + 4), cond_en, font=f_cond, fill=BLACK)
    czw = text_w(d, cond_zh, f_cond_zh)
    d.text((right_x - czw, y + 56), cond_zh, font=f_cond_zh, fill=GREY)

    y += 110

    # Secondary line: H/L | AQI | humidity | sunrise/sunset — mix fonts to render zh glyph
    parts = []
    if w.get("today_max") is not None and w.get("today_min") is not None:
        parts.append(("en", f"H  {round(w['today_max'])}°   L  {round(w['today_min'])}°"))
    if w.get("aqi") is not None:
        aqi_text = f"AQI  {w['aqi']}"
        parts.append(("en", aqi_text))
        if w.get("aqi_desc"):
            parts.append(("zh", w["aqi_desc"]))
    if w.get("humidity") is not None:
        parts.append(("en", f"hum  {round(w['humidity'] * 100)}%"))
    if w.get("sunrise") and w.get("sunset"):
        parts.append(("en", f"{w['sunrise']} → {w['sunset']}"))

    x = MARGIN + 20
    sep_w = text_w(d, "  ·  ", f_kv)
    for i, (kind, s) in enumerate(parts):
        if i > 0:
            d.text((x, y), "  ·  ", font=f_kv, fill=GREY)
            x += sep_w
        font_use = f_kv if kind == "en" else f_kv_zh
        d.text((x, y + (2 if kind == "zh" else 0)), s, font=font_use, fill=BLACK)
        x += text_w(d, s, font_use)
    y += 50

    # Forecast keypoint
    kp = w.get("forecast_keypoint")
    if kp:
        d.text((MARGIN + 20, y), kp, font=f_kp, fill=GREY)
        y += 40

    return y


def draw_section_title(d: ImageDraw.ImageDraw, y: int, en: str, zh: str) -> int:
    f_en = f("geo_i", 30)
    f_zh = f("serif_zh", 84)

    # English caption above
    d.text((MARGIN, y), en, font=f_en, fill=GREY)
    # Chinese title
    d.text((MARGIN, y + 40), zh, font=f_zh, fill=BLACK)

    # Thin rule under title
    title_w = text_w(d, zh, f_zh)
    hrule(d, y + 40 + 100, x1=MARGIN, x2=MARGIN + title_w + 80, width=2)

    return y + 40 + 130


def draw_todo(d: ImageDraw.ImageDraw, y: int, items: list):
    f_idx = f("geo_i", 38)
    f_item = f("serif", 56)
    f_strike = f("serif", 56)

    line_gap = 92
    idx_w = 80
    for i, it in enumerate(items, 1):
        if isinstance(it, str):
            text, done = it, False
        else:
            text, done = it.get("text", ""), bool(it.get("done"))

        # roman-style index number
        idx_str = f"{i:02d}"
        d.text((MARGIN, y + 6), idx_str, font=f_idx, fill=GREY)

        # item text
        x = MARGIN + idx_w
        fill = GREY if done else BLACK
        d.text((x, y), text, font=f_item, fill=fill)

        if done:
            # strikethrough
            w = text_w(d, text, f_item)
            sy = y + 36
            d.line([(x, sy), (x + w, sy)], fill=GREY, width=2)

        y += line_gap

    return y


def draw_clawd(img: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int,
               size: int = 64, asset_path: Path | None = None) -> tuple[int, int]:
    """Paste the prepared Clawd pixel-sprite onto the card.

    Clawd is the Claude Code mascot — a small pixel-art creature with two
    angled eyes and stubby legs. The asset at ``assets/clawd.png`` is an
    LA-mode (gray + alpha) image, so we use its alpha channel as a paste
    mask to keep the surrounding card pure white.

    ``size`` is the target *height* in device pixels (width is derived to
    preserve aspect ratio). NEAREST resampling keeps the pixels crisp on
    e-ink — bilinear would leave a grey halo that prints muddy.

    Silently no-ops if the asset is missing, so the rest of the card
    still renders. Returns the (x, y) top-left where the sprite was
    placed, for caller-side bookkeeping / tests.
    """
    if asset_path is None:
        asset_path = Path(__file__).parent / "assets" / "clawd.png"
    if not asset_path.exists():
        return (x, y)

    sprite = Image.open(asset_path)
    sw, sh = sprite.size
    # Fit by height; derive width to preserve aspect ratio.
    scale = size / sh
    new_w = max(1, int(round(sw * scale)))
    new_h = max(1, int(round(sh * scale)))
    sprite = sprite.resize((new_w, new_h), Image.NEAREST)

    if sprite.mode == "LA":
        l_channel, a_channel = sprite.split()
    elif sprite.mode == "RGBA":
        l_channel = sprite.convert("RGB").convert("L")
        a_channel = sprite.split()[-1]
    else:
        l_channel = sprite.convert("L")
        a_channel = None

    if a_channel is not None:
        img.paste(l_channel, (x, y), a_channel)
    else:
        img.paste(l_channel, (x, y))
    return (x, y)


_LOGO_FILES = {"claude": "claude_logo.png", "codex": "codex_logo.png"}


def draw_logo(img: Image.Image, x: int, y: int, size: int, key: str) -> int:
    """Paste a prepared grayscale app-logo (LA mode) fit by height; return its
    drawn width (0 if missing) for caller layout. LANCZOS keeps the icon curves
    smooth on e-ink (Clawd uses NEAREST because it's pixel art; logos aren't)."""
    asset = Path(__file__).parent / "assets" / _LOGO_FILES.get(key, "")
    if not key or not asset.exists():
        return 0
    logo = Image.open(asset)
    sw, sh = logo.size
    scale = size / sh
    nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
    logo = logo.resize((nw, nh), Image.LANCZOS)
    if logo.mode == "LA":
        l_channel, a_channel = logo.split()
    elif logo.mode == "RGBA":
        l_channel = logo.convert("RGB").convert("L")
        a_channel = logo.split()[-1]
    else:
        l_channel, a_channel = logo.convert("L"), None
    if a_channel is not None:
        img.paste(l_channel, (x, y), a_channel)
    else:
        img.paste(l_channel, (x, y))
    return nw


def draw_footer(d: ImageDraw.ImageDraw, label: str):
    y = H - 100
    double_rule(d, y, gap=5, thick=3, thin=1)

    fy = y + 22
    f_foot = f("geo_i", 32)
    f_mono = f("mono", 26)
    left = label
    right = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    d.text((MARGIN, fy), left, font=f_foot, fill=GREY)
    rw = text_w(d, right, f_mono)
    d.text((W - MARGIN - rw, fy + 2), right, font=f_mono, fill=GREY)

    # tiny centered ornament
    orn = "—   ·   —"
    f_orn = f("geo_i", 24)
    ow = text_w(d, orn, f_orn)
    d.text(((W - ow) // 2, fy + 2), orn, font=f_orn, fill=GREY)


def issue_string(now: datetime) -> str:
    return now.strftime("%y%m%d")


def render(payload: dict, out: Path) -> Path:
    # Apply per-render font overrides (payload.fonts maps logical keys to paths).
    global _FONT_OVERRIDES
    _FONT_OVERRIDES = {}
    fonts_cfg = payload.get("fonts") or {}
    if isinstance(fonts_cfg, dict):
        for k, v in fonts_cfg.items():
            if isinstance(v, str) and v and Path(v).exists():
                _FONT_OVERRIDES[k] = v

    img = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    global _CURRENT_IMG
    _CURRENT_IMG = img

    now = datetime.now()

    # 时钟贴顶：删掉 Desk·Card 报头，时钟成为最上元素、从 y=64 起笔（顶部仅留正常边距）。
    # 64 必须与 APK MainActivity.TIME_DRAW_TOP 一致——APK 时钟 overlay 硬编码该坐标，
    # 白底覆盖 (316,64)→(1088,364)；服务端图把日期农历/书摘排到 364 之下避让。
    y = draw_time_band(d, now, 64, bake_time=payload.get("bake_time", True))

    widget = payload.get("widget", "usage")
    if widget == "usage":
        # Anchor usage to the bottom of the card (above footer) so the
        # middle stays as whitespace breathing room.
        FOOTER_TOP = H - 100
        USAGE_HEIGHT_ESTIMATE = 945   # +95：两个 section header 放大 logo 后各加高 ~44
        usage_y = FOOTER_TOP - 30 - USAGE_HEIGHT_ESTIMATE
        # Don't push above the time band area though
        usage_y = max(usage_y, y + 40)

        # Book quote centered in the empty band between time and usage.
        if payload.get("show_quote", True):
            draw_quote(d, y_top=y + 20, y_bottom=usage_y - 30,
                       x_left=MARGIN, x_right=W - MARGIN)

        draw_big_usage(d, usage_y,
                       show_extra=bool(payload.get("show_extra", False)))
    elif widget == "todo":
        items = payload.get("items", [])
        en = payload.get("section_en", "Things to do")
        zh = payload.get("title", "今 日 待 办")
        y = draw_section_title(d, y, en, zh)
        draw_todo(d, y + 10, items)
    elif widget == "clock":
        pass
    else:
        d.text((MARGIN, y), f"unknown widget: {widget}", font=f("sans", 60), fill=BLACK)

    draw_footer(d, payload.get("footer", "desk-card · likebook K78W"))

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="inline JSON payload")
    ap.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out" / "current.png"))
    args = ap.parse_args()

    if args.stdin:
        payload = json.load(sys.stdin)
    elif args.json:
        payload = json.loads(args.json)
    else:
        payload = {
            "widget": "usage",
            "footer": "desk-card · likebook K78W",
        }

    out = render(payload, Path(args.out))
    print(out)


if __name__ == "__main__":
    main()
