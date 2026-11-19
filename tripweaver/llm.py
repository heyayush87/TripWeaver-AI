"""OpenAI model instances.

Model names can be overridden in .env (OPENAI_MODEL, OPENAI_FAST_MODEL).
ChatOpenAI reads OPENAI_API_KEY from the environment.
"""

import os

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

import tripweaver.config  # noqa: F401  (loads .env before the models are built)
from tripweaver.usage import USAGE_LOGGER
from tripweaver.utils import content_text


MAIN_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
FAST_MODEL = os.getenv("OPENAI_FAST_MODEL", "gpt-5-mini")

# Reasoning is kept to a minimum on the fast models: hidden reasoning tokens
# make calls slower and dearer and can use up max_tokens before any text is
# written. Set OPENAI_FAST_REASONING_EFFORT to an empty value for models that
# do not support reasoning (e.g. gpt-4.1-mini).
FAST_REASONING_EFFORT = os.getenv("OPENAI_FAST_REASONING_EFFORT", "minimal") or None


def _fast_kwargs() -> dict:
    return {"reasoning_effort": FAST_REASONING_EFFORT} if FAST_REASONING_EFFORT else {}


llm = ChatOpenAI(model=MAIN_MODEL, max_retries=4, callbacks=[USAGE_LOGGER])


# Smaller, faster model for routing, flight guidance and budget analysis.
fast_llm = ChatOpenAI(
    model=FAST_MODEL,
    max_tokens=2000,
    max_retries=4,
    callbacks=[USAGE_LOGGER],
    **_fast_kwargs(),
)


# The final answer reformats an existing draft, so the faster model is enough.
final_llm = ChatOpenAI(
    model=FAST_MODEL,
    max_tokens=8000,
    max_retries=4,
    callbacks=[USAGE_LOGGER],
    **_fast_kwargs(),
)


def llm_text(system_prompt: str, user_prompt: str) -> str:
    response = fast_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return content_text(response.content)
