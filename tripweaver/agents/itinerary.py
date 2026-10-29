"""Itinerary agent (draft).

Long trips are written with a map-reduce pattern: a quick outline fixes the
plan for every day, then blocks of days are written in parallel and joined.
Short trips use a single call.
"""

import contextvars
import math
import re
from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from tripweaver.agents.state import TravelState
from tripweaver.llm import fast_llm
from tripweaver.llm import llm
from tripweaver.streaming import get_emitter
from tripweaver.utils import content_text

# Trips up to this many days are written in one call.
SINGLE_CALL_MAX_DAYS = 4
DAYS_PER_BLOCK = 2
MAX_BLOCKS = 4

SYSTEM_PROMPT = "You are an expert travel planner."


def _trip_days(state: TravelState) -> int | None:
    """Read the trip length from the constraints, or from the request text."""
    constraints = state.get("trip_constraints", {}) or {}
    for text in (str(constraints.get("duration", "")), state.get("user_query", "")):
        match = re.search(r"(\d{1,2})\s*[- ]?\s*(?:days?|nights?)", text, re.I)
        if match:
            return int(match.group(1))
    return None


def _context(state: TravelState) -> str:
    return f"""
User Query:
{state['user_query']}

Trip Constraints:
{state.get('trip_constraints', {})}

Flight Results:
{state.get('flight_results', '')}

Hotel Results:
{state.get('hotel_results', '')}

Weather Results:
{state.get('weather_results', '')}
"""


def _ask(model, prompt: str, on_delta=None) -> str:
    """Call the model; when on_delta is given, pass each text piece to it."""
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]

    if on_delta is None:
        return content_text(model.invoke(messages).content)

    pieces = []
    for chunk in model.stream(messages):
        piece = content_text(chunk.content)
        if piece:
            pieces.append(piece)
            on_delta(piece)
    return "".join(pieces)


def _single_call(state: TravelState, emit) -> str:
    return _ask(
        llm,
        f"""
Create a complete travel itinerary.
{_context(state)}
Make the itinerary practical, budget-aware (respect the budget in the trip
constraints and label costs as estimates), and easy to follow.
Create a clear draft that is ready for human review.
""",
        on_delta=lambda piece: emit({"type": "draft_delta", "text": piece}),
    )


def _day_blocks(days: int) -> list[tuple[int, int]]:
    """Split 1..days into at most MAX_BLOCKS consecutive (first, last) blocks."""
    blocks = min(MAX_BLOCKS, math.ceil(days / DAYS_PER_BLOCK))
    size = math.ceil(days / blocks)
    return [
        (start, min(start + size - 1, days)) for start in range(1, days + 1, size)
    ]


def _parallel_draft(state: TravelState, days: int, emit) -> tuple[str, int]:
    """Outline first, then write blocks of days at the same time."""
    outline = _ask(
        fast_llm,
        f"""
Plan a {days}-day trip at a high level. Do not write the detailed days yet.
{_context(state)}
Return markdown with:
1. A short trip overview (route, style, budget approach).
2. A table or list with exactly one line per day (Day 1 to Day {days}):
   the area or theme and the main sights. Every sight and day trip may appear
   on one day only; never repeat a place on two days.
3. Where to stay in each city and for how many nights.
""",
    )

    blocks = _day_blocks(days)
    total_parts = len(blocks) + 1
    emit({"type": "draft_part", "index": 0, "total": total_parts, "text": outline})

    def write_block(position: int) -> str:
        first, last = blocks[position]
        text = _ask(
            llm,
            f"""
Write the detailed itinerary for Day {first} to Day {last} only.
{_context(state)}
Agreed outline for the whole trip:
{outline}

Use exactly the title and sights the outline gives for each of your days. Do not
add sights or day trips that the outline assigns to other days.

Keep each day to about 120 words: morning, afternoon and evening plans, one
food idea, local transport, a rain backup only when the weather suggests it, and
an estimated spend. Label costs as estimates. Start each day with the heading "Day N: title". Do not write an
overview, a summary or days outside Day {first} to Day {last}.
""",
        )
        if position == 0:
            text = "## Day-by-day plan\n\n" + text
        # Show each block as soon as it is done; the page orders them by index.
        emit({"type": "draft_part", "index": position + 1, "total": total_parts, "text": text})
        return text

    # copy_context() lets worker threads reach LangGraph's stream writer.
    with ThreadPoolExecutor(max_workers=len(blocks)) as pool:
        futures = [
            pool.submit(contextvars.copy_context().run, write_block, position)
            for position in range(len(blocks))
        ]
        written = [future.result() for future in futures]

    draft = outline + "\n\n" + "\n\n".join(written)
    return draft, 1 + len(blocks)


def itinerary_agent(state: TravelState):
    days = _trip_days(state)
    emit = get_emitter()

    if days and days > SINGLE_CALL_MAX_DAYS:
        try:
            itinerary, calls = _parallel_draft(state, days, emit)
        except Exception as exc:
            print(f"Parallel itinerary failed, using one call: {exc}")
            itinerary, calls = _single_call(state, emit), 1
    else:
        itinerary, calls = _single_call(state, emit), 1

    approval_request = (
        "Please review the generated draft itinerary. Approve it to create the "
        "final polished plan, or provide feedback for revision."
    )

    return {
        "itinerary": itinerary,
        "approval_request": approval_request,
        "messages": [AIMessage(content="Draft itinerary created for human review.")],
        "llm_calls": calls,
    }
