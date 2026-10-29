"""Detect exhausted quotas and rate limits of the external APIs.

Two kinds of failure are handled differently:

* The language model (Anthropic) is needed for every plan. If its limit is hit
  the request stops and the page shows a "Token limit exceeded" popup that
  names the API.
* Search, flight and weather APIs only add data. If one of them hits its limit
  the plan still completes with general suggestions, and the popup tells the
  user which API ran out.
"""

from typing import Any

ANTHROPIC = "Anthropic (Claude)"
TAVILY = "Tavily (hotel search)"
AVIATIONSTACK = "AviationStack (flights)"
OPENWEATHER = "OpenWeather (weather)"

# Phrases that APIs use when a quota or rate limit is hit.
LIMIT_PHRASES = (
    "429",
    "rate limit",
    "rate_limit",
    "usage_limit",
    "usage limit",
    "quota",
    "too many requests",
    "excessive requests",
    "limit reached",
    "limit exceeded",
    "maximum calls",
    "credit balance",
    "exceeded your",
)


class ApiLimitError(Exception):
    """An external API refused the call because a limit was reached."""

    def __init__(self, api: str, kind: str = "quota", message: str = ""):
        self.api = api
        self.kind = kind  # "quota" (used up) or "rate_limit" (too fast, wait)
        self.message = message or friendly_message(api, kind)
        super().__init__(f"{api}: {self.message}")

    def as_dict(self) -> dict[str, str]:
        return {"api": self.api, "kind": self.kind, "message": self.message}


def friendly_message(api: str, kind: str) -> str:
    if kind == "rate_limit":
        return f"{api} is receiving too many requests. Wait a minute and try again."
    return f"{api} usage limit reached. Add credits or wait for the quota to reset."


def classify_text(api: str, text: str) -> ApiLimitError | None:
    """Return an ApiLimitError if the text looks like a limit failure."""
    lowered = str(text).lower()

    if not any(phrase in lowered for phrase in LIMIT_PHRASES):
        return None

    rate_limited = any(
        phrase in lowered
        for phrase in ("rate limit", "rate_limit", "too many", "excessive", "429")
    )
    return ApiLimitError(api, "rate_limit" if rate_limited else "quota")


def classify_exception(exc: BaseException, api: str | None = None) -> ApiLimitError | None:
    """Return an ApiLimitError for a limit failure, otherwise None.

    Anthropic errors are recognised by their type. For other APIs pass `api`
    and the message text is checked.
    """
    if isinstance(exc, ApiLimitError):
        return exc

    try:
        import anthropic
    except ImportError:  # pragma: no cover
        anthropic = None

    if anthropic is not None:
        if isinstance(exc, anthropic.RateLimitError):
            return ApiLimitError(ANTHROPIC, "rate_limit")

        if isinstance(exc, anthropic.APIStatusError):
            found = classify_text(ANTHROPIC, str(exc))
            if found and getattr(exc, "status_code", 0) in (400, 402, 403, 429):
                return ApiLimitError(ANTHROPIC, found.kind)

    if api:
        return classify_text(api, str(exc))

    return None


def raise_if_limit(exc: BaseException, api: str | None = None) -> None:
    """Call inside `except` blocks that would otherwise hide a limit failure."""
    found = classify_exception(exc, api)

    if found:
        raise found from exc


def limit_update(error: ApiLimitError, emit) -> dict[str, Any]:
    """State update plus a live event for a non-fatal tool limit."""
    emit({"type": "limit", **error.as_dict()})
    return {"api_limits": [error.as_dict()]}


def unique(limits: list[dict[str, str]]) -> list[dict[str, str]]:
    """One entry per API, keeping the first message."""
    seen: dict[str, dict[str, str]] = {}

    for item in limits or []:
        seen.setdefault(item.get("api", ""), item)

    return list(seen.values())
