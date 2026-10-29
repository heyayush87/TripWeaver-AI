"""Token usage tracking for every Claude call.

A callback attached to each model records the input and output tokens of each
call. Use it to find the largest prompts before trimming context, and to check
the effect afterwards.
"""

import logging
from collections import deque
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger("tripweaver.usage")

# Recent calls only, so memory stays bounded in a long-running server.
RECENT_CALLS: deque[dict[str, Any]] = deque(maxlen=500)


class UsageLogger(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs) -> None:
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None)

                if not usage:
                    continue

                record = {
                    "model": (getattr(message, "response_metadata", {}) or {}).get(
                        "model_name", "unknown"
                    ),
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                }
                RECENT_CALLS.append(record)
                logger.info(
                    "llm usage model=%s in=%s out=%s",
                    record["model"],
                    record["input_tokens"],
                    record["output_tokens"],
                )


USAGE_LOGGER = UsageLogger()


def totals(calls: list[dict[str, Any]] | None = None) -> dict[str, int]:
    calls = list(RECENT_CALLS) if calls is None else calls
    return {
        "calls": len(calls),
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
    }
