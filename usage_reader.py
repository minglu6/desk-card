"""Read Claude Code rate limit / usage data.

Primary source: usage_api.get_usage() — calls the Anthropic OAuth endpoint
directly using the local credentials. Self-contained, no plugin required.

Fallback: if our API call is rate-limited or fails, fall back to claude-hud's
local cache (~/.claude/plugins/claude-hud/.usage-cache.json) — claude-hud
hits the same endpoint on its own (slower) cadence, so its cache may still
be fresh when ours is blacklisted.

Secondary source: per-session JSONL files (token counts, message counts) for
extras we don't get from the official endpoint.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import usage_api

PROJECTS_DIR = Path(os.path.expanduser("~/.claude/projects"))
HUD_CACHE = Path(os.path.expanduser("~/.claude/plugins/claude-hud/.usage-cache.json"))


def _parse_ts_str(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def read_official() -> dict | None:
    """Get authoritative Anthropic rate-limit data.

    Primary: our own usage_api (direct API call + 5min cache).
    Fallback: claude-hud's local cache, if our call returns nothing
    (e.g. we're 429-rate-limited and don't yet have a good cache).
    """
    raw = usage_api.get_usage()
    if raw:
        return {
            "plan": raw.get("plan"),
            "rate_limit_tier": raw.get("rate_limit_tier"),
            "five_hour_pct": raw.get("five_hour_pct"),
            "seven_day_pct": raw.get("seven_day_pct"),
            "five_hour_reset_at": _parse_ts_str(raw.get("five_hour_reset_at")),
            "seven_day_reset_at": _parse_ts_str(raw.get("seven_day_reset_at")),
            "seven_day_opus_pct": raw.get("seven_day_opus_pct"),
            "seven_day_sonnet_pct": raw.get("seven_day_sonnet_pct"),
            "extra_usage": raw.get("extra_usage"),
        }

    # Fallback: claude-hud cache
    return _read_hud_cache()


def _read_hud_cache() -> dict | None:
    if not HUD_CACHE.exists():
        return None
    try:
        blob = json.loads(HUD_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None
    data = blob.get("data") or blob.get("lastGoodData")
    if not isinstance(data, dict):
        return None
    return {
        "plan": data.get("planName"),
        "rate_limit_tier": None,
        "five_hour_pct": data.get("fiveHour"),
        "seven_day_pct": data.get("sevenDay"),
        "five_hour_reset_at": _parse_ts_str(data.get("fiveHourResetAt")),
        "seven_day_reset_at": _parse_ts_str(data.get("sevenDayResetAt")),
        "seven_day_opus_pct": None,
        "seven_day_sonnet_pct": None,
        "extra_usage": None,
    }


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def scan(window_hours=(5, 24)) -> dict:
    """Aggregate usage for each window.
    Returns {hours: {input, output, cache_read, cache_create, messages, by_model,
                     window_start (datetime|None), elapsed (timedelta)}}.
    window_start = oldest assistant message timestamp within the window.
    """
    now = datetime.now(tz=timezone.utc)
    cutoffs = {h: now - timedelta(hours=h) for h in window_hours}

    results = {
        h: {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_create": 0,
            "messages": 0,
            "by_model": {},
            "window_start": None,
        }
        for h in window_hours
    }

    if not PROJECTS_DIR.exists():
        return results

    min_cutoff = min(cutoffs.values())
    files = glob.glob(str(PROJECTS_DIR / "*" / "*.jsonl"))
    for fp in files:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(fp), tz=timezone.utc)
            if mtime < min_cutoff:
                continue
        except OSError:
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    msg = d.get("message")
                    if not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    ts = _parse_ts(d.get("timestamp", ""))
                    if not ts:
                        continue

                    model = msg.get("model") or "?"
                    in_t = int(usage.get("input_tokens") or 0)
                    out_t = int(usage.get("output_tokens") or 0)
                    cr_t = int(usage.get("cache_read_input_tokens") or 0)
                    cc_t = int(usage.get("cache_creation_input_tokens") or 0)

                    for h, threshold in cutoffs.items():
                        if ts >= threshold:
                            r = results[h]
                            r["input"] += in_t
                            r["output"] += out_t
                            r["cache_read"] += cr_t
                            r["cache_create"] += cc_t
                            r["messages"] += 1
                            r["by_model"][model] = r["by_model"].get(model, 0) + out_t
                            if r["window_start"] is None or ts < r["window_start"]:
                                r["window_start"] = ts
        except Exception:
            continue

    # Annotate elapsed = now - window_start (or 0)
    for h, r in results.items():
        r["elapsed"] = (now - r["window_start"]) if r["window_start"] else timedelta(0)
        r["now"] = now

    return results


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def fmt_elapsed_hm(td: timedelta) -> str:
    """1h 52m / 0m 12s style."""
    total = int(td.total_seconds())
    if total < 0:
        total = 0
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def fmt_elapsed_dh(td: timedelta) -> str:
    """4d 2h / 12h 5m style."""
    total = int(td.total_seconds())
    if total < 0:
        total = 0
    d, rem = divmod(total, 86400)
    h, rem2 = divmod(rem, 3600)
    m, _ = divmod(rem2, 60)
    if d > 0:
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


if __name__ == "__main__":
    data = scan()
    for h, r in data.items():
        total = r["input"] + r["output"] + r["cache_read"] + r["cache_create"]
        print(f"=== last {h}h ===")
        print(f"  messages : {r['messages']}")
        print(f"  input    : {fmt_tokens(r['input'])}")
        print(f"  output   : {fmt_tokens(r['output'])}")
        print(f"  cache_rd : {fmt_tokens(r['cache_read'])}")
        print(f"  cache_cr : {fmt_tokens(r['cache_create'])}")
        print(f"  TOTAL    : {fmt_tokens(total)}")
        print(f"  by model : { {k: fmt_tokens(v) for k, v in r['by_model'].items()} }")
