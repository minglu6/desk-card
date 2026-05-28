"""Self-contained Codex (ChatGPT subscription) usage fetcher for desk-card.

Reads the Codex OAuth access token from ~/.codex/auth.json and calls
GET https://chatgpt.com/backend-api/wham/usage to retrieve real account-level
rate-limit usage (primary_window = 5h, secondary_window = weekly). Caches the
response locally for 3 minutes. Token only sent in Authorization header.

Endpoint is internal to ChatGPT (not a stable public API); on schema drift or
auth failure ``get_usage`` returns None and callers should fall back to local
data (see ``usage_reader.read_codex``).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

AUTH = Path(os.path.expanduser("~/.codex/auth.json"))
CACHE = Path(__file__).parent / "out" / ".codex_usage_cache.json"

API_URL = "https://chatgpt.com/backend-api/wham/usage"
USER_AGENT = "desk-card/0.1 (+codex usage)"

CACHE_TTL_S = 180   # 3 minutes — same cadence as Anthropic usage_api
FAIL_TTL_S = 30
RL_TTL_S = 180


def _read_token() -> str | None:
    if not AUTH.exists():
        return None
    try:
        with open(AUTH, encoding="utf-8") as f:
            blob = json.load(f)
        return (blob.get("tokens") or {}).get("access_token") or None
    except Exception:
        return None


def _load_cache() -> dict | None:
    if not CACHE.exists():
        return None
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(payload: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, CACHE)
    except Exception:
        pass


def _fetch(token: str, timeout: float = 8.0) -> tuple[dict | None, str | None]:
    req = urllib.request.Request(
        API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body), None
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return None, "rate-limited"
        if e.code in (401, 403):
            return None, "auth"
        return None, f"http-{e.code}"
    except urllib.error.URLError as e:
        return None, f"network:{e.reason}"
    except Exception as e:
        return None, f"err:{type(e).__name__}"


def _normalize(api: dict) -> dict:
    rl = api.get("rate_limit") or {}
    primary = rl.get("primary_window") or {}
    secondary = rl.get("secondary_window") or {}
    return {
        "plan": api.get("plan_type"),
        "five_hour_pct": _to_pct(primary.get("used_percent")),
        "seven_day_pct": _to_pct(secondary.get("used_percent")),
        "five_hour_reset_at": primary.get("reset_at"),
        "seven_day_reset_at": secondary.get("reset_at"),
        "five_hour_window_s": primary.get("limit_window_seconds"),
        "seven_day_window_s": secondary.get("limit_window_seconds"),
        "limit_reached": bool(rl.get("limit_reached")),
    }


def _to_pct(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def get_usage(force: bool = False) -> dict | None:
    """Return normalized Codex usage dict, using local cache when fresh.

    Schema:
        {
            "plan": "plus" | "pro" | None,
            "five_hour_pct": float|None,         # 0..100, real account-level
            "seven_day_pct": float|None,         # 0..100, real account-level
            "five_hour_reset_at": int|None,      # unix seconds
            "seven_day_reset_at": int|None,      # unix seconds
            "five_hour_window_s": int|None,      # 18000 for plus
            "seven_day_window_s": int|None,      # 604800 for plus
            "limit_reached": bool,
        }
    """
    now = time.time()
    if not force:
        cached = _load_cache()
        if cached and isinstance(cached.get("ts"), (int, float)):
            age = now - cached["ts"]
            ttl = cached.get("ttl_s", CACHE_TTL_S)
            if age < ttl and cached.get("data"):
                return cached["data"]

    token = _read_token()
    if not token:
        cached = _load_cache()
        return cached.get("data") if cached else None

    data, err = _fetch(token)
    if err or not data:
        ttl = RL_TTL_S if err == "rate-limited" else FAIL_TTL_S
        cached = _load_cache()
        if cached and cached.get("data"):
            _save_cache({"ts": now, "ttl_s": ttl, "data": cached["data"], "stale": True, "error": err})
            return cached["data"]
        _save_cache({"ts": now, "ttl_s": ttl, "data": None, "error": err})
        return None

    normalized = _normalize(data)
    _save_cache({"ts": now, "ttl_s": CACHE_TTL_S, "data": normalized})
    return normalized


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    raw = "--raw" in sys.argv
    if raw:
        tok = _read_token()
        if not tok:
            print("no token")
            sys.exit(1)
        data, err = _fetch(tok)
        if err:
            print(f"error: {err}")
            sys.exit(1)
        print(json.dumps(data, indent=2))
    else:
        u = get_usage(force=force)
        print(json.dumps(u, indent=2, default=str))
