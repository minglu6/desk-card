"""Probe Caiyun Weather API to see realtime + daily structure."""
import json
import urllib.request

import os
TOKEN = os.environ.get("CAIYUN_WEATHER_API_TOKEN", "")
assert TOKEN, "set CAIYUN_WEATHER_API_TOKEN env var"
LNG, LAT = 117.227, 31.820  # Hefei

url = f"https://api.caiyunapp.com/v2.6/{TOKEN}/{LNG},{LAT}/weather?dailysteps=3&hourlysteps=12&alert=true"
req = urllib.request.Request(url, headers={"User-Agent": "desk-card/0.1"})
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode("utf-8"))

print("status:", data.get("status"))
print("location:", data.get("location"))

result = data.get("result") or {}
realtime = result.get("realtime") or {}
print("\n=== realtime ===")
print("  temp           :", realtime.get("temperature"))
print("  apparent       :", realtime.get("apparent_temperature"))
print("  humidity       :", realtime.get("humidity"))
print("  skycon         :", realtime.get("skycon"))
print("  wind speed/dir :", (realtime.get("wind") or {}).get("speed"), (realtime.get("wind") or {}).get("direction"))
print("  pressure       :", realtime.get("pressure"))
print("  visibility     :", realtime.get("visibility"))
aqi = (realtime.get("air_quality") or {})
print("  aqi (chn)      :", (aqi.get("aqi") or {}).get("chn"))
print("  pm25           :", aqi.get("pm25"))
print("  description    :", (aqi.get("description") or {}).get("chn"))
print("  comfort        :", (realtime.get("life_index") or {}).get("comfort"))

daily = result.get("daily") or {}
print("\n=== daily.temperature (first 3) ===")
for d in (daily.get("temperature") or [])[:3]:
    print(" ", d)
print("\n=== daily.skycon (first 3) ===")
for d in (daily.get("skycon") or [])[:3]:
    print(" ", d)
print("\n=== daily.precipitation (first 3) ===")
for d in (daily.get("precipitation") or [])[:3]:
    print(" ", d)
print("\n=== daily.astro ===")
for d in (daily.get("astro") or [])[:3]:
    print(" ", d)

minutely = result.get("minutely") or {}
print("\n=== minutely description ===")
print(" ", minutely.get("description"))
print(" probability 2h :", minutely.get("probability"))

forecast = result.get("forecast_keypoint")
print("\nforecast_keypoint:", forecast)
