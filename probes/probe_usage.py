import json, os, glob

base = os.path.expanduser("~/.claude/projects")
files = sorted(glob.glob(os.path.join(base, "*", "*.jsonl")),
               key=lambda p: os.path.getmtime(p), reverse=True)[:1]
for f in files:
    print("file:", f)
    with open(f, encoding="utf-8") as fp:
        for line in fp:
            try:
                d = json.loads(line)
            except Exception:
                continue
            msg = d.get("message")
            if isinstance(msg, dict) and "usage" in msg:
                print("type:", d.get("type"))
                print("timestamp:", d.get("timestamp"))
                print("role:", msg.get("role"))
                print("model:", msg.get("model"))
                print("usage:", json.dumps(msg.get("usage"), indent=2))
                break
