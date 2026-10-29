"""Hotel agent."""

from langchain_core.messages import AIMessage
from tripweaver.agents.state import TravelState
from tripweaver.services.mcp_client import tavily_mcp_search
from tripweaver.utils import cached
from tripweaver.utils import run_async


def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    hotel_results = cached(
        ("hotels", query.lower()),
        1800,
        lambda: run_async(tavily_mcp_search(query)),
    )

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content="Hotel information fetched.")
        ],
        "llm_calls": 1
    }
