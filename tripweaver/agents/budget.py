"""Budget agent."""

from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from tripweaver.agents.state import TravelState
from tripweaver.context import BUDGET_SPEC
from tripweaver.context import build_context
from tripweaver.context import prepare
from tripweaver.llm import fast_llm
from tripweaver.utils import content_text


def budget_agent(state: TravelState):
    prompt = f"""
Analyze whether this trip is realistic for the user's budget.

{build_context(prepare(state), BUDGET_SPEC)}

Return:
1. Estimated cost categories
2. Budget risk areas
3. Money-saving suggestions
4. Overall feasibility

If exact live prices are unavailable, clearly label estimates as approximate.
"""

    response = fast_llm.invoke(
        [
            SystemMessage(content="You are a practical travel budget analyst."),
            HumanMessage(content=prompt),
        ]
    )

    return {
        "budget_results": content_text(response.content),
        "messages": [AIMessage(content="Budget assessment generated.")],
        "llm_calls": 1,
    }
