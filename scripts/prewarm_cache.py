"""Fill the shared cache for the quick-prompt examples on the home page.

Run it once after a deploy so the demo prompts answer without waiting for the
flight, hotel and weather services:

    uv run python scripts/prewarm_cache.py

Each run makes real API calls (AviationStack, Tavily, OpenWeather), so do not
schedule it often: the free AviationStack plan has a small monthly quota.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tripweaver.db  # noqa: E402,F401  (turns on the shared Postgres cache)
from tripweaver.agents.hotel import hotel_agent  # noqa: E402
from tripweaver.agents.weather import weather_agent  # noqa: E402
from tripweaver.services.flights import (  # noqa: E402
    DEFAULT_ORIGIN_IATA,
    cached_flight_options,
    parse_route,
    resolve_location_to_iata,
)

TEMPLATE = ROOT / "tripweaver" / "web" / "templates" / "index.html"


def quick_prompts() -> list[str]:
    html = TEMPLATE.read_text(encoding="utf-8")
    return re.findall(r"setPrompt\('([^']*)'\)", html)


def main() -> None:
    for prompt in quick_prompts():
        print("Warming:", prompt[:70])
        dep, arr = parse_route(prompt)
        dep = resolve_location_to_iata(str(dep or "")) or resolve_location_to_iata(
            DEFAULT_ORIGIN_IATA
        )
        arr = resolve_location_to_iata(str(arr or ""))

        if dep and arr and dep != arr:
            result = cached_flight_options(dep, arr)
            print(f"   flights {dep}->{arr}: {len(result['options'])} options")

        hotel_agent({"user_query": prompt})
        weather_agent({"user_query": prompt})
        print("   hotels and weather cached")


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    # The connection pool keeps worker threads alive, so exit explicitly.
    import os

    os._exit(0)
