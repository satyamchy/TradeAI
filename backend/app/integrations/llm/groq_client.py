from langchain_groq import ChatGroq
from app.config import settings


def get_llm():
    return ChatGroq(
        groq_api_key=settings.groq_api_key or "gsk_placeholder_dummy_key_for_offline_runs",
        model_name="openai/gpt-oss-20b",
        temperature=0,
    )
