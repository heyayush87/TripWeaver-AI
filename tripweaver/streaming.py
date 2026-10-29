"""Progress events for the streaming API.

Nodes call get_emitter() and send small dicts (flight table, draft text) that
LangGraph forwards when the graph is streamed with stream_mode="custom".
Outside a streamed run the emitter does nothing, so nodes work unchanged.
"""

from collections.abc import Callable
from typing import Any

from langgraph.config import get_stream_writer


def get_emitter() -> Callable[[dict[str, Any]], None]:
    try:
        return get_stream_writer()
    except Exception:
        return lambda event: None
