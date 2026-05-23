"""Read todos.txt — one line per item. Lines starting with '#' are comments.

Format
------
  [x] done item
  [ ] open item
  any other text  — shown as a plain bullet
"""
from __future__ import annotations

from pathlib import Path

TODOS_FILE = Path(__file__).parent / "todos.txt"


def load() -> list[dict]:
    if not TODOS_FILE.exists():
        return []
    items: list[dict] = []
    for raw in TODOS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        s = line.lstrip()
        if s.startswith("[x]") or s.startswith("[X]"):
            items.append({"text": s[3:].strip(), "done": True})
        elif s.startswith("[ ]") or s.startswith("[]"):
            items.append({"text": s[3:].strip() if s.startswith("[ ]") else s[2:].strip(),
                          "done": False})
        else:
            items.append({"text": s, "done": False})
    return items


if __name__ == "__main__":
    for it in load():
        mark = "✓" if it["done"] else "·"
        print(f"  {mark}  {it['text']}")
