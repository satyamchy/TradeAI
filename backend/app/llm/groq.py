from langchain_groq import ChatGroq
from app.config import GROQ_API_KEY 


def get_llm():
    return ChatGroq(
        groq_api_key=GROQ_API_KEY or "gsk_placeholder_dummy_key_for_offline_runs",
        model_name="openai/gpt-oss-20b",
        temperature=0,
    )
