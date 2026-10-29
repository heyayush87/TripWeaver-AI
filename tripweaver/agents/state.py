"""Shared LangGraph state."""

from langchain_core.messages import AnyMessage
from typing import Annotated
from typing import Any
from typing import TypedDict
import operator


class TravelState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str

    # Supervisor + guardrail state
    guardrail_allowed: bool
    guardrail_reason: str
    selected_agents: list[str]
    trip_constraints: dict[str, Any]
    supervisor_reasoning: str

    # Original specialist results
    flight_results: str
    hotel_results: str
    weather_results: str
    itinerary: str
    flight_options: list[dict[str, Any]]
    flight_notice: str

    # New budget + HITL state
    budget_results: str
    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    # Parallel agents each add their own calls, so the counts are summed.
    llm_calls: Annotated[int, operator.add]

    # APIs that hit a quota or rate limit during this run (shown as a popup).
    api_limits: Annotated[list[dict[str, str]], operator.add]


KNOWN_AGENTS = {
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
}


AGENT_ORDER = [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
]


def empty_constraints() -> dict[str, Any]:
    return {
        "destination": "",
        "origin": "",
        "duration": "",
        "travel_date": "",
        "budget": "",
        "travel_style": "",
        "special_preferences": [],
    }
