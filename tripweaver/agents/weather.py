"""Weather agent."""

from langchain_core.messages import AIMessage
import asyncio
from tripweaver.agents.state import TravelState
from tripweaver.limits import OPENWEATHER
from tripweaver.limits import classify_exception
from tripweaver.limits import limit_update
from tripweaver.streaming import get_emitter
from tripweaver.services.mcp_client import extract_destination
from tripweaver.services.mcp_client import forecast_mcp_search
from tripweaver.services.mcp_client import weather_mcp_search
from tripweaver.utils import cached
from tripweaver.utils import run_async


def weather_agent(state: TravelState):
    city = extract_destination(
        state["user_query"]
    )

    limit_update_fields: dict = {}

    try:
        async def fetch_weather():
            return await asyncio.gather(
                weather_mcp_search(city),
                forecast_mcp_search(city),
            )

        weather_data, forecast_data = cached(
            ("weather", city.lower()),
            1800,
            lambda: run_async(fetch_weather()),
        )

        weather_results = f"""
Current Weather:
{weather_data}

Forecast:
{forecast_data}
"""

    except Exception as exc:
        print(
            f"WEATHER AGENT MCP ERROR: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        limit = classify_exception(exc, OPENWEATHER)
        if limit:
            limit_update_fields = limit_update(limit, get_emitter())

        weather_results = (
            f"Live weather information for {city} "
            "is temporarily unavailable. Give general "
            "seasonal guidance and advise the traveler "
            "to verify the forecast before departure."
        )

    return {
        "weather_results": weather_results,
        "messages": [
            AIMessage(
                content="Weather information processed."
            )
        ],
        **limit_update_fields,
    }
