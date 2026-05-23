"""Caiyun Weather fetcher with local cache.

10-minute cache to stay friendly to API. Reads token from env or hardcoded.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

TOKEN = os.environ.get("CAIYUN_WEATHER_API_TOKEN", "")
DEFAULT_LNG = 117.227
DEFAULT_LAT = 31.820
DEFAULT_LOCATION_NAME = "Hefei"

CACHE = Path(__file__).parent / "out" / ".weather_cache.json"
CACHE_TTL_S = 3600  # 1 hour — weather rarely changes minute-to-minute
FAIL_TTL_S = 60


def _fetch(lng: float, lat: float, timeout: float = 8.0):
    url = (
        f"https://api.caiyunapp.com/v2.6/{TOKEN}/{lng},{lat}/weather"
        "?dailysteps=3&hourlysteps=12&alert=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "desk-card/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"http-{e.code}"
    except urllib.error.URLError as e:
        return None, f"net:{e.reason}"
    except Exception as e:
        return None, f"err:{type(e).__name__}"


_SKYCON_ZH = {
    "CLEAR_DAY": "晴",
    "CLEAR_NIGHT": "晴",
    "PARTLY_CLOUDY_DAY": "多云",
    "PARTLY_CLOUDY_NIGHT": "多云",
    "CLOUDY": "阴",
    "LIGHT_HAZE": "轻度雾霾",
    "MODERATE_HAZE": "中度雾霾",
    "HEAVY_HAZE": "重度雾霾",
    "LIGHT_RAIN": "小雨",
    "MODERATE_RAIN": "中雨",
    "HEAVY_RAIN": "大雨",
    "STORM_RAIN": "暴雨",
    "FOG": "雾",
    "LIGHT_SNOW": "小雪",
    "MODERATE_SNOW": "中雪",
    "HEAVY_SNOW": "大雪",
    "STORM_SNOW": "暴雪",
    "DUST": "浮尘",
    "SAND": "沙尘",
    "WIND": "大风",
}

_SKYCON_EN = {
    "CLEAR_DAY": "Clear", "CLEAR_NIGHT": "Clear",
    "PARTLY_CLOUDY_DAY": "Partly cloudy", "PARTLY_CLOUDY_NIGHT": "Partly cloudy",
    "CLOUDY": "Cloudy",
    "LIGHT_HAZE": "Light haze", "MODERATE_HAZE": "Haze", "HEAVY_HAZE": "Heavy haze",
    "LIGHT_RAIN": "Light rain", "MODERATE_RAIN": "Rain", "HEAVY_RAIN": "Heavy rain",
    "STORM_RAIN": "Storm",
    "FOG": "Fog",
    "LIGHT_SNOW": "Light snow", "MODERATE_SNOW": "Snow", "HEAVY_SNOW": "Heavy snow",
    "STORM_SNOW": "Snow storm",
    "DUST": "Dust", "SAND": "Sand", "WIND": "Windy",
}


def skycon_zh(s: str) -> str:
    return _SKYCON_ZH.get(s or "", s or "—")


def skycon_en(s: str) -> str:
    return _SKYCON_EN.get(s or "", (s or "—").title())


def _normalize(raw: dict, name: str) -> dict | None:
    if not raw or raw.get("status") != "ok":
        return None
    res = raw.get("result") or {}
    rt = res.get("realtime") or {}
    daily = res.get("daily") or {}
    daily_temp = daily.get("temperature") or []
    daily_sky = daily.get("skycon") or []
    daily_prec = daily.get("precipitation") or []
    astro = daily.get("astro") or []

    today_temp = daily_temp[0] if daily_temp else {}
    today_astro = astro[0] if astro else {}

    aq = rt.get("air_quality") or {}
    chn_aqi = (aq.get("aqi") or {}).get("chn")
    aqi_desc = (aq.get("description") or {}).get("chn")

    forecast_lines = []
    for i, t in enumerate(daily_temp[:3]):
        date = t.get("date", "")[5:10]
        sk = (daily_sky[i].get("value") if i < len(daily_sky) else None) or ""
        prec = daily_prec[i] if i < len(daily_prec) else {}
        forecast_lines.append({
            "date": date,
            "max": t.get("max"),
            "min": t.get("min"),
            "skycon": sk,
            "rain_prob": prec.get("probability"),
        })

    return {
        "location_name": name,
        "temp": rt.get("temperature"),
        "feels": rt.get("apparent_temperature"),
        "humidity": rt.get("humidity"),
        "skycon": rt.get("skycon"),
        "aqi": chn_aqi,
        "aqi_desc": aqi_desc,
        "pm25": aq.get("pm25"),
        "today_max": today_temp.get("max"),
        "today_min": today_temp.get("min"),
        "sunrise": (today_astro.get("sunrise") or {}).get("time"),
        "sunset": (today_astro.get("sunset") or {}).get("time"),
        "comfort_desc": ((rt.get("life_index") or {}).get("comfort") or {}).get("desc"),
        "forecast_keypoint": res.get("forecast_keypoint"),
        "daily": forecast_lines,
    }


def _load_cache():
    if not CACHE.exists():
        return None
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(payload):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, CACHE)
    except Exception:
        pass


def get_weather(lng: float = DEFAULT_LNG, lat: float = DEFAULT_LAT,
                name: str = DEFAULT_LOCATION_NAME, force: bool = False):
    now = time.time()
    if not force:
        cached = _load_cache()
        if cached and isinstance(cached.get("ts"), (int, float)):
            if now - cached["ts"] < cached.get("ttl_s", CACHE_TTL_S) and cached.get("data"):
                return cached["data"]

    raw, err = _fetch(lng, lat)
    if err or not raw:
        cached = _load_cache()
        if cached and cached.get("data"):
            _save_cache({"ts": now, "ttl_s": FAIL_TTL_S, "data": cached["data"], "stale": True, "error": err})
            return cached["data"]
        return None

    normalized = _normalize(raw, name)
    if normalized:
        _save_cache({"ts": now, "ttl_s": CACHE_TTL_S, "data": normalized})
    return normalized


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(get_weather(force=True), indent=2, ensure_ascii=False))
