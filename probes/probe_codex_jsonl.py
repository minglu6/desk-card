"""Find what fields a Codex rollout JSONL actually contains — especially usage / tokens."""
import json, glob, os
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.codex/sessions"))
files = sorted(ROOT.rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
print(f"latest {len(files)} rollout files:")
for f in files:
    print(f"  {f.relative_to(ROOT)}  ({f.stat().st_size} B)")

if not files:
    raise SystemExit("no rollout files")

target = files[0]
print(f"\n=== sampling lines from {target.name} ===\n")

# Collect a sample of distinct line `type`s and any usage-related fields
types_seen = {}
usage_examples = []
total_lines = 0
with open(target, encoding="utf-8") as fh:
    for line in fh:
        total_lines += 1
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("type") or d.get("kind") or d.get("event") or "?"
        if t not in types_seen:
            types_seen[t] = d
        # Find any nested usage-like key
        s = json.dumps(d)
        if any(k in s for k in ("usage", "total_tokens", "input_tokens", "output_tokens", "tokens")):
            if len(usage_examples) < 5:
                usage_examples.append(d)

print(f"total lines: {total_lines}")
print(f"\ndistinct top-level types ({len(types_seen)}):")
for t, sample in types_seen.items():
    print(f"  type={t!r}  keys={list(sample.keys())[:10]}")

print(f"\nfirst {len(usage_examples)} usage-bearing lines (truncated):")
for i, e in enumerate(usage_examples):
    print(f"\n--- example {i+1} ---")

    def find(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if any(t in k.lower() for t in ("token", "usage", "cost")):
                    print(f"  {path}.{k} = {v!r}"[:200])
                find(v, path + "." + k)
        elif isinstance(o, list):
            for j, x in enumerate(o[:2]):
                find(x, path + f"[{j}]")
    find(e)
    # also dump top-level
    print(f"  top keys: {list(e.keys())}")
    if "type" in e:
        print(f"  type: {e['type']}")
    if "timestamp" in e:
        print(f"  ts: {e['timestamp']}")
