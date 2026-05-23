"""Generate a Clawd sprite — ears protrude from the SIDES at the EYE row.

KEY USER INSIGHT: "耳朵应该是和眼睛在一行的"
  → The ears are NOT on top of the body. They're at the SAME vertical row
    as the eyes, sticking OUTWARD from the left and right sides of the
    body. The body's TOP is flat and narrower than the eye row.

Geometry:
  - Body proper is 14 cells wide (cols 1-14)
  - At the EYE ROW, the figure widens to 16 cells — the extra cells at
    cols 0-1 and 14-15 are the EARS sticking out sideways
  - Eyes (transparent holes) at cols 4-5 and 10-11, inside the body
  - 4 stubby black legs at the bottom

This puts the figure's WIDEST POINT at the eye line, with the head
narrowing above and the body narrowing below — exactly like the user's
reference image #2.
"""
from pathlib import Path
from PIL import Image, ImageDraw

# Pixel legend
#   . = transparent
#   # = solid black
GRID = [
    "..##############..",  # 0  body top (14 wide, cols 2-15) in 18-col grid
    "..##############..",  # 1
    "#####..####..#####",  # 2  EAR + EYE ROW: ears protrude 2 cells beyond body
    "#####..####..#####",  # 3  (cols 0-1 and 16-17)
    "..##############..",  # 4  body narrows back to 14 wide
    "..##############..",  # 5
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
