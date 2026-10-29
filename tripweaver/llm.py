"""Claude model instances."""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from tripweaver.usage import USAGE_LOGGER
from tripweaver.utils import content_text


llm = ChatAnthropic(model="claude-sonnet-5-5", callbacks=[USAGE_LOGGER])


# Smaller, faster model for routing, flight guidance and budget analysis.
# Thinking is switched off for Haiku: on by default it adds hundreds of hidden
# output tokens per call (slower, dearer) and can use up max_tokens before any
# text is written (the budget answer came back empty).
fast_llm = ChatAnthropic(
    model="claude-haiku-5-5",
    max_tokens=2000,
    thinking={"type": "disabled"},
    callbacks=[USAGE_LOGGER],
)


# The final answer reformats an existing draft, so the faster model is enough.
final_llm = ChatAnthropic(
    model="claude-haiku-5-5",
    max_tokens=8000,
    thinking={"type": "disabled"},
    callbacks=[USAGE_LOGGER],
)


def llm_text(system_prompt: str, user_prompt: str) -> str:
    response = fast_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return content_text(response.content)
