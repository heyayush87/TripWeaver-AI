"""LangGraph workflow: routing, parallel fan-out and compilation."""

from langgraph.graph import END
from langgraph.graph import START
from langgraph.graph import StateGraph
from tripweaver.agents.approval import human_approval_agent
from tripweaver.agents.budget import budget_agent
from tripweaver.agents.final import final_agent
from tripweaver.agents.flight import flight_agent
from tripweaver.agents.hotel import hotel_agent
from tripweaver.agents.itinerary import itinerary_agent
from tripweaver.agents.state import AGENT_ORDER
from tripweaver.agents.state import TravelState
from tripweaver.agents.supervisor import guardrail_blocked_agent
from tripweaver.agents.supervisor import supervisor_agent
from tripweaver.agents.weather import weather_agent
from tripweaver.db import checkpointer


ROUTE_MAP = {
    "guardrail_blocked": "guardrail_blocked",
    "flight_agent": "flight_agent",
    "hotel_agent": "hotel_agent",
    "weather_agent": "weather_agent",
    "budget_agent": "budget_agent",
    "itinerary_agent": "itinerary_agent",
}


PARALLEL_AGENTS = ["flight_agent", "hotel_agent", "weather_agent"]


def _selected_agents(state: TravelState) -> list[str]:
    selected = state.get("selected_agents", [])
    return [agent for agent in AGENT_ORDER if agent in selected]


def route_from_supervisor(state: TravelState):
    """Fan out: flight, hotel and weather run at the same time."""
    if not state.get("guardrail_allowed", True):
        return "guardrail_blocked"

    selected = _selected_agents(state)
    parallel = [agent for agent in PARALLEL_AGENTS if agent in selected]

    if parallel:
        return parallel

    return "budget_agent" if "budget_agent" in selected else "itinerary_agent"


def route_after_parallel(state: TravelState) -> str:
    """Join: the budget agent needs the parallel results, so it runs next."""
    return "budget_agent" if "budget_agent" in _selected_agents(state) else "itinerary_agent"


graph = StateGraph(TravelState)

graph.add_node("supervisor", supervisor_agent)
graph.add_node("guardrail_blocked", guardrail_blocked_agent)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent", weather_agent)
graph.add_node("budget_agent", budget_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("human_approval", human_approval_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", route_from_supervisor, ROUTE_MAP)

for parallel_agent in PARALLEL_AGENTS:
    graph.add_conditional_edges(parallel_agent, route_after_parallel, ROUTE_MAP)

graph.add_edge("budget_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "human_approval")
graph.add_edge("human_approval", "final_agent")
graph.add_edge("final_agent", END)
graph.add_edge("guardrail_blocked", END)


travel_graph = graph.compile(checkpointer=checkpointer)
