"""Small helpers shared by the agents."""

from typing import Any
import asyncio
import json
import time


_CACHE: dict[tuple, tuple[float, Any]] = {}

# Optional second level that survives restarts and is shared by all workers.
# db.py plugs a PostgreSQL store in; unit tests leave it off.
_shared_store = None


def enable_shared_cache(store) -> None:
    global _shared_store
    _shared_store = store


def cached(key: tuple, ttl_seconds: int, compute, store_if=lambda value: True):
    """Return a recent result for `key`, or compute and remember it.

    Lookup order: this process's memory, the shared store, then `compute()`.
    Shared-store errors are logged and ignored, so a cache problem never
    breaks a request.
    """
    now = time.monotonic()
    hit = _CACHE.get(key)

    if hit and now - hit[0] < ttl_seconds:
        return hit[1]

    shared_key = ":".join(str(part) for part in key)

    if _shared_store is not None:
        try:
            shared = _shared_store.get(shared_key)
            if shared is not None:
                _CACHE[key] = (now, shared)
                return shared
        except Exception as exc:
            print(f"Shared cache read failed: {exc}")

    value = compute()

    if store_if(value):
        _CACHE[key] = (now, value)

        if _shared_store is not None:
            try:
                _shared_store.set(shared_key, value, ttl_seconds)
            except Exception as exc:
                print(f"Shared cache write failed: {exc}")

    return value


def run_async(coro):
    """Run a coroutine to completion from a sync graph node, thread-safe."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def content_text(content: Any) -> str:
    """Flatten LLM content (str or list of content blocks) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in content
            if isinstance(block, (str, dict))
        )
    return str(content)


def json_from_llm(text: str) -> dict[str, Any]:
    """Extract the first complete JSON object returned by the model."""
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("The model did not return a JSON object.")

    return json.loads(text[start : end + 1])
