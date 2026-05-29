"""生成 desk-card 用的 Claude / Codex 单色透明 logo（近黑剪影 + 透明底）。

- Claude：从 app icon 截图抠 sunburst（亮前景）+ 居中圆 mask 去边角弧线。
- Codex：从高清官方 app icon（codex_src.png ~304px，蓝紫云朵 + 白色 ">_"）按
  "到白色的色差"抠图 —— 云朵(蓝紫)离白远被保留；白色 >_ 与近白背景离白近被
  排除，>_ 自然成为云朵内的镂空。全程在原生分辨率做 mask（高分辨率下羽化占比
  小、几乎不侵蚀 >_ 镂空，边缘也更平滑），再 LANCZOS 高质量降采样。比手搓几何
  更还原原图真实瓣形与 >_ 设计（3 个对比 agent 验证：瓣数/位置高度吻合）。

源图已固化在 assets/（claude_src.png / codex_src.png），不依赖临时 image-cache。
输出统一 LA 模式（纯黑 FG + alpha），render.py 的 draw_logo() 直接贴。
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageChops

OUT_DIR = Path(__file__).parent
STORE = 256   # 存储分辨率（render 时再缩到行高 ~88，越高边缘越平滑）
FG = 0        # 前景填充：纯黑


def circle_mask(size, r_frac):
    m = Image.new("L", size, 0)
    w, h = size
    r = min(w, h) * r_frac
    ImageDraw.Draw(m).ellipse([w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r], fill=255)
    return m


def extract(src, out_name, fg, thresh, r_frac, pad=1.0):
    """从截图抠单色剪影：阈值二值化 + 圆 mask 去边角 + 裁到图形紧边界 + pad 控占比
    （Claude sunburst 用）。pad 让 sunburst 在画布中的占比可控 —— 之前不裁、四周留白
    使它显小，裁紧 + pad 后可调到与 Codex 云朵视觉等大。"""
    im = Image.open(src).convert("RGBA")
    bbox = im.split()[-1].getbbox()
    if bbox:
        im = im.crop(bbox)
    lum = im.convert("RGB").convert("L")
    if fg == "light":
        mask = lum.point(lambda p: 255 if p >= thresh else 0)
    else:
        mask = lum.point(lambda p: 255 if p <= thresh else 0)
    w, h = mask.size
    side = max(w, h)
    sq = Image.new("L", (side, side), 0)
    sq.paste(mask, ((side - w) // 2, (side - h) // 2))
    sq = ImageChops.multiply(sq, circle_mask((side, side), r_frac))
    # 裁到图形紧边界（去掉 sunburst 四周留白），再按 pad 居中缩放，占画布比例可控
    bb = sq.getbbox()
    if bb:
        sq = sq.crop(bb)
    cw, ch = sq.size
    cs = max(cw, ch)
    canvas = Image.new("L", (cs, cs), 0)
    canvas.paste(sq, ((cs - cw) // 2, (cs - ch) // 2))
    canvas = canvas.filter(ImageFilter.GaussianBlur(max(0.8, cs / 200.0)))
    inner = round(STORE * pad)
    glyph = Image.merge("LA", (Image.new("L", (cs, cs), FG), canvas)).resize((inner, inner), Image.LANCZOS)
    out = Image.new("LA", (STORE, STORE), (0, 0))
    out.paste(glyph, ((STORE - inner) // 2, (STORE - inner) // 2))
    out.save(OUT_DIR / out_name)
    print(f"  {out_name}: extracted (thresh={thresh}, r_frac={r_frac}, pad={pad})")


def extract_codex_hires(src, out_name, T=55, pad=0.74):
    """高清原图色差抠图：diff-to-white 分离云朵，>_ 自然成镂空。
    全程在原生分辨率(~304)做 mask：轻中值去毛刺 + 小幅羽化（高分辨率下 blur 占比
    小、几乎不侵蚀 >_），最后 LANCZOS 降采样到 STORE，边缘平滑。pad 控制占画布比例
    使其与 Claude sunburst 视觉等大。"""
    im = Image.open(src).convert("RGB")
    white = Image.new("RGB", im.size, (255, 255, 255))
    diff = ImageChops.difference(im, white).convert("L")
    mask = diff.point(lambda p: 255 if p > T else 0)
    mask = mask.filter(ImageFilter.MedianFilter(3))          # 轻去毛刺（高分辨率下温和，不啃 >_）
    bbox = mask.getbbox()
    mask = mask.crop(bbox)
    mw, mh = mask.size
    side = int(max(mw, mh) * 1.04)                           # 四周留一点边
    sq = Image.new("L", (side, side), 0)
    sq.paste(mask, ((side - mw) // 2, (side - mh) // 2))
    sq = sq.filter(ImageFilter.GaussianBlur(side / 220.0))   # 小幅羽化，少侵蚀 >_ 镂空
    glyph = Image.merge("LA", (Image.new("L", (side, side), FG), sq))
    inner = int(STORE * pad)
    out = Image.new("LA", (STORE, STORE), (0, 0))
    out.paste(glyph.resize((inner, inner), Image.LANCZOS), ((STORE - inner) // 2, (STORE - inner) // 2))
    out.save(OUT_DIR / out_name)
    print(f"  {out_name}: extracted from hires (T={T}, pad={pad}, src={im.size}, side={side})")


print("Claude (抠图 sunburst):")
extract(OUT_DIR / "claude_src.png", "claude_logo.png", fg="light", thresh=185, r_frac=0.42, pad=0.90)
print("Codex (高清原图色差抠图 + >_ 镂空):")
extract_codex_hires(OUT_DIR / "codex_src.png", "codex_logo.png")
print("done")
