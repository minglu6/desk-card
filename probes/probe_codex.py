"""Inspect Codex local data — what's available, what fields, what schemas."""
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.codex"))

print("=" * 70)
print("auth.json — top-level keys (no values for secrets)")
print("=" * 70)
try:
    with open(ROOT / "auth.json", encoding="utf-8") as f:
        auth = json.load(f)

    def walk(o, p=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    print(f"{p}{k}:")
                    walk(v, p + "  ")
                else:
                    s = str(v)
                    if len(s) > 20:
                        s = s[:8] + "…" + s[-4:] + f" (len={len(str(v))})"
                    print(f"{p}{k}: {s}")
    walk(auth)
except Exception as e:
    print("err:", e)

print()
print("=" * 70)
print(".codex-global-state.json — keys + any usage/rate hints")
print("=" * 70)
try:
    with open(ROOT / ".codex-global-state.json", encoding="utf-8") as f:
        gs = json.load(f)
    print("top-level keys:", list(gs.keys()))
    for k, v in gs.items():
        if any(t in k.lower() for t in ("limit", "rate", "usage", "quota", "plan", "tier", "subscription", "cap", "balance", "credit")):
            print(f"  RELEVANT {k} =", v)
except Exception as e:
    print("err:", e)

print()
print("=" * 70)
print("config.toml — content")
print("=" * 70)
try:
    print((ROOT / "config.toml").read_text(encoding="utf-8")[:1500])
except Exception as e:
    print("err:", e)

print()
print("=" * 70)
print("sessions directory layout")
print("=" * 70)
sess = ROOT / "sessions"
if sess.exists():
    for p in sorted(sess.rglob("*"))[:15]:
        rel = p.relative_to(sess)
        size = p.stat().st_size if p.is_file() else "-"
        print(f"  {rel}  ({size})")

print()
print("=" * 70)
print("session_index.jsonl — first 3 + last 3")
print("=" * 70)
idx = ROOT / "session_index.jsonl"
if idx.exists():
    lines = idx.read_text(encoding="utf-8").splitlines()
    print(f"total {len(lines)} sessions")
    for line in (lines[:3] + ["..."] + lines[-3:]):
        if line != "...":
            try:
                e = json.loads(line)
                print(f"  {e.get('id', '?')[:36]}  {e.get('updated_at', '?')}  {e.get('thread_name', '?')[:30]}")
            except Exception:
                print(" ", line[:80])
        else:
            print("  ...")

print()
print("=" * 70)
print("logs_2.sqlite schema")
print("=" * 70)
try:
    db = sqlite3.connect(str(ROOT / "logs_2.sqlite"))
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur]
    print("tables:", tables)
    for t in tables:
        info = db.execute(f"PRAGMA table_info({t})").fetchall()
        cnt = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  TABLE {t} ({cnt} rows):", [c[1] for c in info])
    # Sample a row from each table for shape
    for t in tables[:3]:
        sample = db.execute(f"SELECT * FROM {t} LIMIT 1").fetchone()
        print(f"  sample {t}:", str(sample)[:200])
    db.close()
except Exception as e:
    print("err:", e)
