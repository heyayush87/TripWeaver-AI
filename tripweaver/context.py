"""Context stripping: give each model call only the data it needs.

Fewer input tokens means lower cost and a little less time to the first token,
and it keeps the model focused on the facts that matter. Latency is mostly the
time to write the answer, so the main gain is cost.
"""

import re
from typing import Any

URL_LINE = re.compile(r"^\s*https?://\S+\s*$")


def clip(text: str, max_chars: int) -> str:
    """Cut text at a word boundary and mark the cut."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].rstrip() + " ..."


def trim_search_results(text: str, max_results: int = 3, snippet_chars: int = 220) -> str:
    """Keep the top search results, drop bare URL lines and shorten snippets.

    Works on the numbered text produced by parse_tavily_result: entries are
    separated by a blank line, and each starts with "N. title".
    """
    entries = [entry for entry in re.split(r"\n\s*\n", text.strip()) if entry.strip()]
    kept = []

    for entry in entries:
        if len(kept) >= max_results:
            break

        lines = [line for line in entry.split("\n") if not URL_LINE.match(line)]

        if not lines:
            continue

        title, snippet = lines[0], " ".join(lines[1:])

        # Skip junk such as an error message from another site's page: the model
        # may repeat it as if it were a fact about this trip.
        if snippet.lstrip().startswith(("{", "[")):
            continue

        kept.append(f"{title}\n{clip(snippet, snippet_chars)}".rstrip())

    return "\n\n".join(kept)


def build_context(state: dict[str, Any], spec: list[tuple[str, str, int]]) -> str:
    """Build a prompt section from state.

    spec is a list of (state key, label, max characters). Empty values are
    skipped completely, so the prompt has no blank headings.
    """
    parts = []

    for key, label, limit in spec:
        value = state.get(key, "")
        text = value if isinstance(value, str) else str(value)

        if not text.strip() or text.strip() in ("{}", "[]"):
            continue

        parts.append(f"{label}:\n{clip(text.strip(), limit)}")

    return "\n\n".join(parts)


# What each model call receives: (state key, label, max characters).
OUTLINE_SPEC = [
    ("user_query", "User request", 500),
    ("trip_constraints", "Trip constraints", 600),
    ("flight_results", "Flights", 600),
    ("hotel_results", "Hotels", 900),
    ("weather_results", "Weather", 600),
]

# Day blocks follow the outline, so they do not need the flight text.
BLOCK_SPEC = [
    ("user_query", "User request", 500),
    ("trip_constraints", "Trip constraints", 600),
    ("hotel_results", "Hotels", 700),
    ("weather_results", "Weather", 500),
]

BUDGET_SPEC = [
    ("user_query", "User request", 500),
    ("trip_constraints", "Trip constraints", 600),
    ("flight_results", "Flights", 800),
    ("hotel_results", "Hotels", 900),
    ("weather_results", "Weather", 600),
]

# The draft already used the hotel and weather facts, so only short notes follow it.
FINAL_SPEC = [
    ("user_query", "User request", 500),
    ("trip_constraints", "Trip constraints", 600),
    ("flight_results", "Flights", 800),
    ("hotel_results", "Hotels", 700),
    ("weather_results", "Weather", 500),
    ("budget_results", "Budget analysis", 1500),
    ("itinerary", "Draft itinerary", 20000),
]


def prepare(state: dict[str, Any]) -> dict[str, Any]:
    """Copy of the state with the hotel search text reduced to the top results."""
    trimmed = dict(state)
    trimmed["hotel_results"] = trim_search_results(str(state.get("hotel_results", "")))
    return trimmed

