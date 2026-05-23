"""Self-contained Anthropic OAuth usage fetcher for desk-card.

Reads the Claude Code OAuth access token from ~/.claude/.credentials.json,
calls GET https://api.anthropic.com/api/oauth/usage, caches the response
locally for 5 minutes. No plugin dependency.

The token is only ever sent in the Authorization header to api.anthropic.com.
It is not logged, printed, or written to disk.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

CREDS = Path(os.path.expanduser("~/.claude/.credentials.json"))
CACHE = Path(__file__).parent / "out" / ".usage_cache.json"

API_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"
USER_AGENT = "desk-card/0.1 (+claude-code statusline data)"

CACHE_TTL_S = 300        # 5 minutes — Anthropic's usage endpoint rate-limits aggressively
FAIL_TTL_S = 30          # short retry on failure
RL_TTL_S = 180           # 3 minutes when we get 429 (be polite)


def _read_creds() -> dict | None:
    if not CREDS.exists():
        return None
    try:
        with open(CREDS, encoding="utf-8") as f:
            blob = json.load(f)
    except Exception:
        return None
    oauth = blob.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token:
        return None
    return {
        "access_token": token,
        "expires_at_ms": oauth.get("expiresAt"),
        "subscription": oauth.get("subscriptionType"),
        "rate_limit_tier": oauth.get("rateLimitTier"),
    }


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


def _fetch(access_token: str, timeout: float = 8.0) -> tuple[dict | None, str | None]:
    req = urllib.request.Request(
        API_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": BETA_HEADER,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            return data, None
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return None, "rate-limited"
        return None, f"http-{e.code}"
    except urllib.error.URLError as e:
        return None, f"network:{e.reason}"
    except Exception as e:
        return None, f"err:{type(e).__name__}"


def _normalize(api: dict, creds: dict | None) -> dict:
    """Anthropic OAuth usage response → flat dict (superset of claude-hud shape)."""
    five = api.get("five_hour") or {}
    seven = api.get("seven_day") or {}
    seven_opus = api.get("seven_day_opus") or {}
    seven_sonnet = api.get("seven_day_sonnet") or {}
    extra = api.get("extra_usage") or {}
    return {
        "plan": (creds or {}).get("subscription") or api.get("plan"),
        "rate_limit_tier": (creds or {}).get("rate_limit_tier"),
        "five_hour_pct": _to_pct(five.get("utilization")),
        "seven_day_pct": _to_pct(seven.get("utilization")),
        "five_hour_reset_at": five.get("resets_at"),
        "seven_day_reset_at": seven.get("resets_at"),
        "seven_day_opus_pct": _to_pct(seven_opus.get("utilization")) if seven_opus else None,
        "seven_day_sonnet_pct": _to_pct(seven_sonnet.get("utilization")) if seven_sonnet else None,
        "extra_usage": {
            "enabled": bool(extra.get("is_enabled")),
            "monthly_limit": extra.get("monthly_limit"),
            "used_credits": extra.get("used_credits"),
            "pct": _to_pct(extra.get("utilization")),
            "currency": extra.get("currency"),
        } if extra else None,
    }


def _to_pct(v):
    """Anthropic OAuth usage endpoint returns utilization as 0..100 (not 0..1)."""
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def get_usage(force: bool = False) -> dict | None:
    """Return normalized usage dict, using local cache when fresh."""
    now = time.time()
    if not force:
        cached = _load_cache()
        if cached and isinstance(cached.get("ts"), (int, float)):
            age = now - cached["ts"]
            ttl = cached.get("ttl_s", CACHE_TTL_S)
            if age < ttl and cached.get("data"):
                return cached["data"]

    creds = _read_creds()
    if not creds:
        # No creds → fall back to whatever cache we have, however stale
        cached = _load_cache()
        return cached.get("data") if cached else None

    data, err = _fetch(creds["access_token"])
    if err or not data:
        ttl = RL_TTL_S if err == "rate-limited" else FAIL_TTL_S
        # On failure, surface stale cache rather than nothing
        cached = _load_cache()
        if cached and cached.get("data"):
            _save_cache({"ts": now, "ttl_s": ttl, "data": cached["data"], "stale": True, "error": err})
            return cached["data"]
        _save_cache({"ts": now, "ttl_s": ttl, "data": None, "error": err})
        return None

    normalized = _normalize(data, creds)
    _save_cache({"ts": now, "ttl_s": CACHE_TTL_S, "data": normalized})
    return normalized


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    raw = "--raw" in sys.argv
    if raw:
        creds = _read_creds()
        if not creds:
            print("no credentials")
            sys.exit(1)
        data, err = _fetch(creds["access_token"])
        if err:
            print(f"error: {err}")
            sys.exit(1)
        print(json.dumps(data, indent=2))
    else:
        u = get_usage(force=force)
        print(json.dumps(u, indent=2, default=str))
