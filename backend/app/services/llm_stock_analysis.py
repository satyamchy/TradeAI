"""Generates a plain-English analysis from already-fetched market data."""

import json
from urllib import response
import httpx
from langchain_core import messages
from app.integrations.llm.groq_client import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

_SYSTEM_PROMPT = """You are a stock market analyst covering Indian equities (NSE).
You will be given quote and fundamentals data for one stock.
Write a concise analysis (4-6 sentences): recent price action, notable
fundamentals if present, and balanced context. Do not give direct buy/sell
instructions — describe the data, don't issue financial advice.
"""


async def analyze_stock_data(ticker: str, market_data: dict) -> str:
    quote = market_data.get("quote", {})
    fundamentals = market_data.get("fundamentals", {})

    user_content = (
        f"Ticker: {ticker}\n"
        f"Quote: {quote}\n"
        f"Fundamentals: {fundamentals}\n"
    )

    # async with httpx.AsyncClient(timeout=30.0) as client:
    #     response = await client.post(
    #         "https://api.anthropic.com/v1/messages",
    #         headers={"Content-Type": "application/json"},
    #         json={
    #             "model": "claude-sonnet-4-6",
    #             "max_tokens": 400,
    #             "system": _SYSTEM_PROMPT,
    #             "messages": [{"role": "user", "content": user_content}],
    #         },
    #     )
    #     response.raise_for_status()
    #     data = response.json()

    llm = get_llm()
    # response = await llm.ainvoke({
    #         "system": _SYSTEM_PROMPT,
    #         "messages": [{"role": "user", "content": user_content}],
    #     })
    # data = response.json()
    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ])

    return response.content.strip()

    # return "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text").strip()