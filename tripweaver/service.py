"""Entry points used by the API layer."""

from langchain_core.messages import HumanMessage
from langgraph.types import Command
import traceback
import uuid
from collections.abc import Iterator
from typing import Any
from tripweaver.agents.graph import travel_graph
from tripweaver.agents.state import empty_constraints
from tripweaver.utils import content_text


def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None

    first_interrupt = interrupts[0]
    payload = getattr(first_interrupt, "value", first_interrupt)
    return payload if isinstance(payload, dict) else {"value": payload}


def _serialize_result(
    result: dict[str, Any],
    thread_id: str,
) -> dict[str, Any]:
    messages = result.get("messages", [])
    last_message = content_text(messages[-1].content) if messages else ""
    answer = content_text(result.get("final_response") or last_message)
    interrupt_payload = _interrupt_payload(result)

    if interrupt_payload:
        answer = interrupt_payload.get("draft_itinerary") or result.get(
            "itinerary", ""
        )

    return {
        "thread_id": thread_id,
        "answer": answer,
        "requires_approval": interrupt_payload is not None,
        "approval_request": (
            interrupt_payload.get("approval_request", "")
            if interrupt_payload
            else result.get("approval_request", "")
        ),
        "flight_results": result.get("flight_results", ""),
        "flight_options": result.get("flight_options", []),
        "flight_notice": result.get("flight_notice", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "budget_results": result.get("budget_results", ""),
        "itinerary": (
            interrupt_payload.get("draft_itinerary", "")
            if interrupt_payload
            else result.get("itinerary", "")
        ),
        "selected_agents": result.get("selected_agents", []),
        "trip_constraints": result.get("trip_constraints", {}),
        "supervisor_reasoning": result.get("supervisor_reasoning", ""),
        "guardrail_allowed": result.get("guardrail_allowed", True),
        "guardrail_reason": result.get("guardrail_reason", ""),
        "approved": result.get("approved"),
        "human_feedback": result.get("human_feedback", ""),
        "llm_calls": result.get("llm_calls", 0),
    }


def _initial_state(user_input: str) -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content=user_input)],
        "user_query": user_input,
        "guardrail_allowed": True,
        "guardrail_reason": "",
        "selected_agents": [],
        "trip_constraints": empty_constraints(),
        "supervisor_reasoning": "",
        "flight_results": "",
        "flight_options": [],
        "flight_notice": "",
        "hotel_results": "",
        "weather_results": "",
        "budget_results": "",
        "itinerary": "",
        "approval_request": "",
        "approved": False,
        "human_feedback": "",
        "final_response": "",
        "llm_calls": 0,
    }


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def run_travel_agent(user_input: str, thread_id: str | None = None):
    """Start a new travel-planning run and pause at human approval."""
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    result = travel_graph.invoke(_initial_state(user_input), config=_config(thread_id))
    return _serialize_result(result, thread_id)


def resume_travel_agent(
    thread_id: str,
    approved: bool,
    feedback: str = "",
):
    """Resume the paused LangGraph thread after human review."""
    if not thread_id:
        raise ValueError("thread_id is required to resume a travel plan.")

    result = travel_graph.invoke(
        Command(resume={"approved": approved, "feedback": feedback.strip()}),
        config=_config(thread_id),
    )
    return _serialize_result(result, thread_id)


def _stream_graph(graph_input: Any, thread_id: str) -> Iterator[dict[str, Any]]:
    """Run the graph and yield small events, ending with a "done" event.

    Events: stage (a node finished), flights, draft_part, draft_delta,
    final_delta, done (full result) and error.
    """
    config = _config(thread_id)
    interrupts = None

    try:
        for mode, chunk in travel_graph.stream(
            graph_input, config=config, stream_mode=["updates", "custom"]
        ):
            if mode == "custom":
                yield chunk
                continue

            for node, update in chunk.items():
                if node == "__interrupt__":
                    interrupts = update
                else:
                    yield {"type": "stage", "node": node}

        result = dict(travel_graph.get_state(config).values)
        if interrupts:
            result["__interrupt__"] = list(interrupts)

        yield {"type": "done", "result": _serialize_result(result, thread_id)}

    except Exception:
        traceback.print_exc()
        yield {
            "type": "error",
            "error": "Something went wrong while planning. Please try again.",
        }


def stream_travel_agent(
    user_input: str, thread_id: str | None = None
) -> Iterator[dict[str, Any]]:
    thread_id = thread_id or f"user_{uuid.uuid4().hex}"
    return _stream_graph(_initial_state(user_input), thread_id)


def stream_resume_travel_agent(
    thread_id: str, approved: bool, feedback: str = ""
) -> Iterator[dict[str, Any]]:
    return _stream_graph(
        Command(resume={"approved": approved, "feedback": feedback.strip()}),
        thread_id,
    )
