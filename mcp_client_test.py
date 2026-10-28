import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import certifi
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient

# CHANGED: added the missing imports above (asyncio, shutil, sys, Path, Any,
# ChatAnthropic) and removed the stray `from tkinter import NONE`.

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# CHANGED: TAVILY_API_KEY was used but never defined.
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# CHANGED: your .env uses AVIATION_API_KEY, so it is checked first.
AVIATION_STACK_API_KEY = (
    os.getenv("AVIATION_API_KEY")
    or os.getenv("AVIATION_STACK_API_KEY")
    or os.getenv("AVIATIONSTACK_API_KEY")
)

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# CHANGED: the file in your project is custom_weather_mcp.py (no "_server").
WEATHER_SERVER_PATH = BASE_DIR / "custom_weather_mcp.py"

# CHANGED: UVX_COMMAND was used but never defined.
UVX_COMMAND = shutil.which("uvx") or "uvx"

# =========================================================
# Claude LLM
# =========================================================

# CHANGED: added the Claude model (reads ANTHROPIC_API_KEY from .env).
llm = ChatAnthropic(model="claude-sonnet-5-5")


def _require_env(name: str, value: str | None) -> None:
    # CHANGED: this helper was called but never defined.
    if not value:
        raise RuntimeError(f"{name} is missing. Add it to your .env file.")


def _subprocess_env(**updates: str | None) -> dict[str, str]:
    """
    Preserve the current Windows environment and add MCP API keys.
    """

    env = os.environ.copy()

    # CHANGED: quiet the MCP server subprocesses (no "Processing request of
    # type ListToolsRequest" log lines and no pydantic warnings in the console).
    env["FASTMCP_LOG_LEVEL"] = "WARNING"
    env["PYTHONWARNINGS"] = "ignore"

    for key, value in updates.items():
        if value:
            env[key] = value

    return env


# =========================================================
# MCP client setup
# =========================================================

client = MultiServerMCPClient(
    {
        "tavily": {
            "transport": "streamable_http",
            "url": "https://mcp.tavily.com/mcp/",
            # CHANGED: the key is sent as a header instead of in the URL,
            # because URLs end up in logs.
            "headers": {"Authorization": f"Bearer {TAVILY_API_KEY}"},
        },
        "aviationstack": {
            "transport": "stdio",
            "command": UVX_COMMAND,
            "args": [
                "aviationstack-mcp",
            ],
            "env": _subprocess_env(
                AVIATION_STACK_API_KEY=AVIATION_STACK_API_KEY,
            ),
        },
        "weather": {
            "transport": "stdio",
            # Uses the Python executable of the active environment.
            "command": sys.executable,
            # Uses the weather server inside the current project folder.
            "args": [
                str(WEATHER_SERVER_PATH),
            ],
            "env": _subprocess_env(
                OPENWEATHER_API_KEY=OPENWEATHER_API_KEY,
            ),
        },
    }
)


# CHANGED: this line was commented out (`#async def`) but its body was not,
# which caused the IndentationError. It is a normal `async def` again.
async def _get_server_tool(
    server_name: str,
    tool_name: str,
):
    """
    Load one tool from one MCP server.

    This prevents a broken weather or AviationStack server from
    crashing an unrelated Tavily request.
    """

    if server_name == "tavily":
        _require_env(
            "TAVILY_API_KEY",
            TAVILY_API_KEY,
        )

    elif server_name == "aviationstack":
        _require_env(
            "AVIATION_API_KEY",
            AVIATION_STACK_API_KEY,
        )

        if shutil.which("uvx") is None:
            raise RuntimeError(
                "uvx was not found. Install uv, reopen the terminal, "
                "activate the environment, and run `uvx --version`."
            )

    elif server_name == "weather":
        _require_env(
            "OPENWEATHER_API_KEY",
            OPENWEATHER_API_KEY,
        )

        if not WEATHER_SERVER_PATH.is_file():
            raise FileNotFoundError(f"Weather MCP server not found: {WEATHER_SERVER_PATH}")

    # Important: load only the requested MCP server.
    tools = await client.get_tools(
        server_name=server_name,
    )

    tool = next(
        (item for item in tools if item.name == tool_name),
        None,
    )

    if tool is None:
        available_tools = ", ".join(sorted(item.name for item in tools)) or "none"

        raise RuntimeError(
            f"MCP tool '{tool_name}' was not found "
            f"on server '{server_name}'. "
            f"Available tools: {available_tools}"
        )

    return tool


# =========================================================
# MCP connection test
# =========================================================


async def get_all_tools() -> None:
    """
    Test every MCP server independently.

    One failed server will not stop the remaining tests.
    """

    for server_name in (
        "tavily",
        "aviationstack",
        "weather",
    ):
        try:
            tools = await client.get_tools(
                server_name=server_name,
            )

            tool_names = ", ".join(tool.name for tool in tools) or "no tools"

            print(f"{server_name}: OK -> {tool_names}")

        except Exception as exc:
            print(f"{server_name}: FAILED -> {type(exc).__name__}: {exc}")


# =========================================================
# Tavily MCP
# =========================================================


def mcp_result_text(raw: Any) -> str:
    """
    CHANGED: added. Joins the `text` of MCP content blocks into one plain string
    (the weather tools return [{'type': 'text', 'text': '...'}]).
    """

    if isinstance(raw, str):
        return raw

    return "\n".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in raw
    )


def parse_tavily_result(raw: Any, max_chars: int = 300) -> str:
    """
    CHANGED: added. The MCP tool returns a list of content blocks, e.g.
    [{'type': 'text', 'text': '{"query": ..., "results": [...]}'}],
    where `text` is a JSON string. This turns it into clean numbered text
    (title, url, short snippet) that can be passed to Claude.
    """

    if isinstance(raw, str):
        blocks = [raw]
    else:
        blocks = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in raw
        ]

    lines: list[str] = []

    for text in blocks:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Not JSON: keep the text as it is.
            lines.append(text)
            continue

        # CHANGED: report API errors (e.g. 429 rate limit) instead of returning
        # an empty string.
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(
                f"Tavily error {data.get('status', '')}: "
                f"{data.get('detail') or data['error']}"
            )

        for i, item in enumerate(data.get("results", []), 1):
            title = item.get("title", "unknown")
            url = item.get("url", "")
            snippet = item.get("content", "").strip()

            if len(snippet) > max_chars:
                snippet = snippet[:max_chars].rsplit(" ", 1)[0] + "..."

            lines.append(f"{i}. {title}\n{url}\n{snippet}\n")

    return "\n\n".join(lines)


async def tavily_mcp_search(query: str) -> str:
    search_tool = await _get_server_tool(
        "tavily",
        "tavily_search",
    )

    raw = await search_tool.ainvoke(
        {
            "query": query,
        }
    )

    # CHANGED: returns clean text instead of the raw list of blocks.
    return parse_tavily_result(raw)


# =========================================================
# AviationStack MCP
# =========================================================


async def aviation_mcp_call(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
):
    aviation_tool = await _get_server_tool(
        "aviationstack",
        tool_name,
    )

    return await aviation_tool.ainvoke(tool_args or {})


# =========================================================
# Weather MCP
# =========================================================


async def weather_mcp_search(city: str):
    weather_tool = await _get_server_tool(
        "weather",
        "get_current_weather",
    )

    return mcp_result_text(await weather_tool.ainvoke({"city": city}))


async def forecast_mcp_search(city: str):
    forecast_tool = await _get_server_tool(
        "weather",
        "get_forecast",
    )

    return mcp_result_text(await forecast_tool.ainvoke({"city": city}))


# =========================================================
# Destination extractor
# =========================================================


def extract_destination(query: str) -> str:
    prompt = f"""
Extract only the destination city or country from the travel request.

Travel request:
{query}

Return only the destination name.
Do not add any explanation.
"""

    response = llm.invoke(prompt)

    # CHANGED: `.text` instead of `str(response.content)`, because Claude can
    # return a list of blocks, not a plain string.
    destination = response.text.strip()

    if not destination:
        raise ValueError("The destination could not be extracted.")

    return destination


# =========================================================
# Run the tests
# =========================================================

# CHANGED: added this block. Nothing ran before, and async functions need
# asyncio.run(). The result is now printed.
if __name__ == "__main__":
    # CHANGED: the Windows console defaults to cp1252 and crashed on symbols
    # like the star in hotel ratings; UTF-8 output fixes it.
    sys.stdout.reconfigure(encoding="utf-8")

    asyncio.run(get_all_tools())

    destination = extract_destination("Plan a 5 day trip to Tokyo from Delhi")
    print(f"\nDestination: {destination}")

    print("\nTavily search result:")
    print(asyncio.run(tavily_mcp_search(f"Best hotels in {destination}")))
