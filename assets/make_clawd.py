"""Generate a Clawd sprite — ears protrude from the SIDES, ONE ROW BELOW the eyes.

KEY USER INSIGHT (2026-05-25 revision): "把两边的耳朵往下移动一行"
  → Ears remain at the SIDES (not on top of the head), but the whole ear
    cluster is shifted DOWN BY ONE ROW. The top ear row now overlaps the
    bottom eye row; the bottom ear row sits one cell below the eyes,
    where the body would normally be.

Geometry:
  - Body proper is 14 cells wide (cols 2-15)
  - Eye row (row 2): eye holes only, NO ears
  - Ear rows (rows 3-4): ears protrude 2 cells (cols 0-1 and 16-17);
    row 3 still has the eye holes carved out, row 4 has solid body underneath
  - 4 stubby black legs at the bottom
"""
from pathlib import Path
from PIL import Image, ImageDraw

# Pixel legend
#   . = transparent
#   # = solid black
GRID = [
    "..##############..",  # 0  body top (14 wide, cols 2-15) in 18-col grid
    "..##############..",  # 1
    "..###..####..###..",  # 2  EYE ROW: eye holes, NO ears
    "#####..####..#####",  # 3  EAR + EYE: ears protrude 2 cells (cols 0-1 / 16-17)
    "##################",  # 4  EAR + BODY: ears continue, body fills behind
    "..##############..",  # 5  body narrows back to 14 wide
    "..##############..",  # 6
    "..##############..",  # 7
    "..##############..",  # 8  body bottom
    "..##..##..##..##..",  # 9  4 legs
    "..##..##..##..##..",  # 10
]

COLS = max(len(r) for r in GRID)
GRID = [r.ljust(COLS, ".") for r in GRID]
ROWS = len(GRID)

PX = 14
PAD = 4
INK = 0


def main() -> Path:
    w = COLS * PX + PAD * 2
    h = ROWS * PX + PAD * 2

    img = Image.new("LA", (w, h), (255, 0))
    d = ImageDraw.Draw(img)

    for ry, row in enumerate(GRID):
        for cx, ch in enumerate(row):
            if ch != "#":
                continue
            x0 = PAD + cx * PX
            y0 = PAD + ry * PX
            x1 = x0 + PX - 1
            y1 = y0 + PX - 1
            d.rectangle([x0, y0, x1, y1], fill=(INK, 255))

    out_path = Path(__file__).parent / "clawd.png"
    img.save(out_path, "PNG", optimize=True)
    print(f"wrote {out_path}  ({w}×{h}, {out_path.stat().st_size} bytes)")
    return out_path


if __name__ == "__main__":
    main()
