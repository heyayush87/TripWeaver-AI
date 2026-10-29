"""Hotel agent."""

from langchain_core.messages import AIMessage
from tripweaver.agents.state import TravelState
from tripweaver.limits import TAVILY
from tripweaver.limits import classify_exception
from tripweaver.limits import limit_update
from tripweaver.streaming import get_emitter
from tripweaver.services.mcp_client import tavily_mcp_search
from tripweaver.utils import cached
from tripweaver.utils import run_async


def hotel_agent(state: TravelState):
    limit_update_fields: dict = {}
    query = f"Best hotels for {state['user_query']}"
    try:
        hotel_results = cached(
            ("hotels", query.lower()),
            6 * 3600,
            lambda: run_async(tavily_mcp_search(query)),
        )
    except Exception as exc:
        # A search outage or rate limit should not fail the whole plan.
        print(f"HOTEL AGENT ERROR: {type(exc).__name__}: {exc}", flush=True)
        limit = classify_exception(exc, TAVILY)
        if limit:
            limit_update_fields = limit_update(limit, get_emitter())
        hotel_results = (
            "Live hotel search is unavailable right now. Suggest suitable "
            "areas and hotel types from general knowledge, avoid naming "
            "prices as facts, and tell the traveler to check current rates."
        )

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content="Hotel information fetched.")
        ],
        "llm_calls": 1,
        **limit_update_fields,
    }
