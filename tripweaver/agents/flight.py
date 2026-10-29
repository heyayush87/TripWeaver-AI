"""Flight agent: real flight options plus guidance."""

from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from typing import Any
from tripweaver.agents.state import TravelState
from tripweaver.llm import fast_llm
from tripweaver.limits import ANTHROPIC
from tripweaver.limits import AVIATIONSTACK
from tripweaver.limits import classify_text
from tripweaver.limits import limit_update
from tripweaver.limits import raise_if_limit
from tripweaver.streaming import get_emitter
from tripweaver.services.flights import DEFAULT_ORIGIN_IATA
from tripweaver.services.flights import cached_flight_options
from tripweaver.services.flights import parse_route
from tripweaver.services.flights import resolve_location_to_iata
from tripweaver.utils import content_text


FLIGHT_AGENT_PROMPT = """
You are a travel flight expert.

User Query:
{query}

Route: {route}
Requested travel date: {travel_date}

Real flights found for this route (airport local times):
{options_text}

Notes:
{notice}

Write short markdown guidance with a bold heading and bullet points:
- Which of the listed flights suit the traveller and why (only use the real
  flights above; never invent flight numbers or times)
- Typical flight duration
- Estimated return airfare range, clearly marked as an estimate
- Peak season pricing warning
- Booking advice: prefer refundable or free-cancellation fares until any
  required visa is approved; confirm visa rules with the embassy

End with this line: "Fares, schedules and visa rules are indicative, so confirm
before booking."
"""


FLIGHT_SCHEDULE_NOTICE = (
    "Times shown are the airline's recent daily schedule in airport local time. "
    "Live schedules for a specific future date are not available, so confirm "
    "the flight on your travel date with the airline."
)


def _resolve_route(state: TravelState) -> tuple[str | None, str | None]:
    constraints = state.get("trip_constraints", {}) or {}
    dep = resolve_location_to_iata(str(constraints.get("origin", "")))
    arr = resolve_location_to_iata(str(constraints.get("destination", "")))

    if not (dep and arr):
        parsed_dep, parsed_arr = parse_route(state["user_query"])
        dep = dep or resolve_location_to_iata(str(parsed_dep or ""))
        arr = arr or resolve_location_to_iata(str(parsed_arr or ""))

    return dep, arr


def flight_agent(state: TravelState):
    emit = get_emitter()
    print("\nINSIDE FLIGHT AGENT\n")
    constraints = state.get("trip_constraints", {}) or {}
    travel_date = str(constraints.get("travel_date", "")).strip() or "not given"

    dep, arr = _resolve_route(state)
    options: list[dict[str, Any]] = []
    notice = ""
    limit_fields: dict = {}
    assumed_origin = False

    # No departure city given: fall back to DEFAULT_ORIGIN_IATA.
    if arr and not dep:
        dep = resolve_location_to_iata(DEFAULT_ORIGIN_IATA)
        assumed_origin = dep is not None

    if dep and arr and dep == arr:
        notice = "The departure and arrival airports are the same, so no flights are shown."
    elif dep and arr:
        lookup = cached_flight_options(dep, arr)
        options = lookup["options"][:10]

        if not lookup["ok"]:
            print("Flight lookup failed:", lookup["error"])
            notice = "Live flight data is unavailable right now."
            limit = classify_text(AVIATIONSTACK, lookup["error"])
            if limit:
                notice = "The flight data API limit was reached, so no live flights are shown."
                limit_fields = limit_update(limit, emit)
        elif not options:
            notice = f"No flights were found for {dep} to {arr}."
        else:
            notice = FLIGHT_SCHEDULE_NOTICE

        if assumed_origin:
            notice = (
                f"No departure city was given, so {dep} is assumed. "
                "Mention where you are flying from to change it. " + notice
            )
    else:
        notice = (
            "The departure or arrival city could not be identified. "
            "Mention both cities to see flight options."
        )

    # Show the flight table right away; the guidance text below takes longer.
    emit({"type": "flights", "options": options, "notice": notice})

    options_text = "\n".join(
        f"- {o['airline']} {o['flight_number']}: departs {o['departs']}, "
        f"arrives {o['arrives']} ({o['date']})"
        for o in options
    ) or "None"

    try:
        response = fast_llm.invoke(
            [
                SystemMessage(content="You are an expert travel flight planner."),
                HumanMessage(
                    content=FLIGHT_AGENT_PROMPT.format(
                        query=state["user_query"],
                        route=f"{dep or '?'} to {arr or '?'}",
                        travel_date=travel_date,
                        options_text=options_text,
                        notice=notice,
                    )
                ),
            ]
        )
        flight_data = content_text(response.content)
    except Exception as exc:
        raise_if_limit(exc, ANTHROPIC)  # a Claude limit stops the whole request
        flight_data = f"Flight guidance unavailable: {exc}"

    return {
        "flight_results": flight_data,
        "flight_options": options,
        "flight_notice": notice,
        "messages": [AIMessage(content="Flight recommendations generated")],
        "llm_calls": 1,
        **limit_fields,
    }
