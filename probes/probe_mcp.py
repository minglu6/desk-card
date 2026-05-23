import json, os
p = os.path.expanduser("~/.claude.json")
with open(p, encoding="utf-8") as f:
    d = json.load(f)
cfg = d.get("mcpServers", {}).get("caiyun-weather")
print(json.dumps(cfg, indent=2, ensure_ascii=False))
