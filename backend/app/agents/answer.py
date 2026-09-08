from langchain_core.prompts import ChatPromptTemplate

from app.llm.groq import get_llm
from app.prompts.answer_prompt import ANSWER_PROMPT
from app.utils.context_builder import build_context
from app.agents.state import ConversationState

llm = get_llm()

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", ANSWER_PROMPT),

        (
            "human",
            """
Question
{query}
Context
{context}
"""
        )
    ]
)

chain = prompt | llm


async def answer_node(
    state: ConversationState,
):
    context = build_context(
        state["sources"]
    )

    response = await chain.ainvoke(
        {
            "query": state["query"],
            "context": context
        }
    )

    return {
        "context": context,
        "answer": response.content
    }