"""Final response agent."""

from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from tripweaver.agents.state import TravelState
from tripweaver.context import FINAL_SPEC
from tripweaver.context import build_context
from tripweaver.context import prepare
from tripweaver.llm import final_llm
from tripweaver.streaming import get_emitter
from tripweaver.utils import content_text


def final_agent(state: TravelState):
    if state.get("approved", False):
        review_instruction = (
            "The user approved the draft. Preserve its decisions while polishing it."
        )
    else:
        review_instruction = f"""
The user requested a revision. Apply this feedback carefully:
{state.get('human_feedback', '') or 'Improve the draft before finalizing it.'}
"""

    final_prompt = f"""
Generate the final travel response for the user.

Human Review:
{review_instruction}

{build_context(prepare(state), FINAL_SPEC)}

Format the final answer beautifully using these sections:
1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations

Important:
- Be clear and practical.
- Mention that live flight APIs may not provide ticket prices when pricing is unavailable.
- Include weather-based travel advice.
- Keep the response useful for real travel planning.
- Incorporate the human feedback when revision was requested.
"""

    emit = get_emitter()
    pieces = []

    # Stream the answer so the page can show it while it is being written.
    for chunk in final_llm.stream(
        [
            SystemMessage(
                content="You are a professional AI travel booking assistant."
            ),
            HumanMessage(content=final_prompt),
        ]
    ):
        piece = content_text(chunk.content)
        if piece:
            pieces.append(piece)
            emit({"type": "final_delta", "text": piece})

    final_text = "".join(pieces)

    return {
        "final_response": final_text,
        "messages": [AIMessage(content=final_text)],
        "llm_calls": 1,
    }
