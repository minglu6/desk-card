"""Find any rate-limit / reset info stored in Claude Code's JSONL files."""
import glob, json, os

base = os.path.expanduser("~/.claude/projects")
files = sorted(glob.glob(os.path.join(base, "*", "*.jsonl")),
               key=lambda p: os.path.getmtime(p), reverse=True)

def find_rl(obj, path=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if "rate" in kl or "limit" in kl or "reset" in kl:
                hits.append((f"{path}.{k}", v))
            hits.extend(find_rl(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:5]):
            hits.extend(find_rl(item, f"{path}[{i}]"))
    return hits

for f in files[:3]:
    print(f"=== {f} ===")
    with open(f, encoding="utf-8") as fp:
        for line in fp:
            if "atelimit" not in line and "eset" not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            hits = find_rl(d)
            # filter rate/reset only
            relevant = [(p, v) for p, v in hits if any(t in p.lower() for t in ("rate", "reset", "limit"))]
            if relevant:
                ts = d.get("timestamp")
                typ = d.get("type")
                print(f"  type={typ} ts={ts}")
                for p, v in relevant[:20]:
                    val = json.dumps(v) if not isinstance(v, (str, int, float, bool)) else v
                    val_str = str(val)
                    if len(val_str) > 120:
                        val_str = val_str[:120] + "…"
                    print(f"    {p} = {val_str}")
                print()
                break
    print()
