"""Read Claude Code rate limit / usage data.

Primary source: usage_api.get_usage() — calls the Anthropic OAuth endpoint
directly using the local credentials. Self-contained, no plugin required.

Secondary source: per-session JSONL files (token counts, message counts) for
extras we don't get from the official endpoint.

Codex source: ~/.codex/state_5.sqlite threads.tokens_used (single-machine
only — OpenAI exposes no account-level usage endpoint, so cross-machine
totals will undercount; the UI tags Codex rows as ``(local)``).
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import usage_api
import codex_api

PROJECTS_DIR = Path(os.path.expanduser("~/.claude/projects"))
CODEX_STATE_DB = Path(os.path.expanduser("~/.codex/state_5.sqlite"))

# Soft quota references for Codex windows (no official OpenAI endpoint).
# Approximated from ChatGPT Plus GPT-5 limits (~200 msg / 5h, ~10-50k tok/msg).
# Tune via payload["codex_quota_5h"] / ["codex_quota_7d"] if needed.
CODEX_QUOTA_5H_TOKENS = 10_000_000
CODEX_QUOTA_7D_TOKENS = 200_000_000


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
    """Get authoritative Anthropic rate-limit data via usage_api (direct
    API call + 5min cache). Returns None if the call fails or is rate-limited.
    """
    raw = usage_api.get_usage()
    if not raw:
        return None
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


def read_codex_top_model(window_hours: int = 168) -> str | None:
    """Return the Codex model (e.g. ``"gpt-5.5"``) that contributed the most
    tokens in the last ``window_hours``, or None if state_5.sqlite is missing.
    """
    if not CODEX_STATE_DB.exists():
        return None
    cutoff = int(datetime.now(tz=timezone.utc).timestamp()) - window_hours * 3600
    try:
        conn = sqlite3.connect(f"file:{CODEX_STATE_DB}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT model, COALESCE(SUM(tokens_used), 0) AS tok FROM threads "
            "WHERE updated_at >= ? AND model IS NOT NULL "
            "GROUP BY model ORDER BY tok DESC LIMIT 1",
            (cutoff,),
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def read_codex(window_hours=(5, 168),
               prefer_oauth: bool = True,
               quota_5h: int | None = None,
               quota_7d: int | None = None) -> dict:
    """Read Codex usage with OAuth-first, sqlite-fallback strategy.

    Returns::

        {
            "source": "oauth" | "sqlite" | "none",
            "plan": "plus" | "pro" | None,
            5:   {"pct": float|None, "reset_at": datetime|None,
                  "tokens": int|None, "threads": int|None, "quota": int|None},
            168: {...},
        }

    - ``source="oauth"``: real account-level pct + reset time from
      chatgpt.com/backend-api/wham/usage (covers cross-machine subscription).
    - ``source="sqlite"``: local token counts vs. soft quota from
      ~/.codex/state_5.sqlite; only counts threads on this machine.
    - ``source="none"``: neither path worked.
    """
    out: dict = {"source": "none", "plan": None,
                 "model": read_codex_top_model(window_hours=168)}

    # ---- OAuth (authoritative) ----
    if prefer_oauth:
        oauth = codex_api.get_usage()
        if oauth:
            out["source"] = "oauth"
            out["plan"] = oauth.get("plan")
            for h in window_hours:
                if h == 5:
                    pct = oauth.get("five_hour_pct")
                    reset_unix = oauth.get("five_hour_reset_at")
                elif h == 168:
                    pct = oauth.get("seven_day_pct")
                    reset_unix = oauth.get("seven_day_reset_at")
                else:
                    pct, reset_unix = None, None
                reset_at = (datetime.fromtimestamp(reset_unix, tz=timezone.utc)
                            if reset_unix else None)
                out[h] = {
                    "pct": pct,
                    "reset_at": reset_at,
                    "tokens": None,
                    "threads": None,
                    "quota": None,
                }
            return out

    # ---- Local sqlite fallback ----
    q5 = quota_5h if quota_5h is not None else CODEX_QUOTA_5H_TOKENS
    q7 = quota_7d if quota_7d is not None else CODEX_QUOTA_7D_TOKENS
    quotas = {5: q5, 168: q7}

    if not CODEX_STATE_DB.exists():
        for h in window_hours:
            out[h] = None
        return out

    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    try:
        conn = sqlite3.connect(f"file:{CODEX_STATE_DB}?mode=ro", uri=True)
        cur = conn.cursor()
        for h in window_hours:
            cutoff = now_ts - h * 3600
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(tokens_used), 0) "
                "FROM threads WHERE updated_at >= ?",
                (cutoff,),
            )
            cnt, tokens = cur.fetchone()
            tokens = int(tokens or 0)
            quota = quotas.get(h)
            pct = (tokens / quota * 100.0) if quota else None
            out[h] = {
                "pct": pct,
                "reset_at": None,
                "tokens": tokens,
                "threads": int(cnt or 0),
                "quota": quota,
            }
        conn.close()
        out["source"] = "sqlite"
    except Exception:
        for h in window_hours:
            out[h] = None
    return out


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
