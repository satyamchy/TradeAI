# # app/tools/compare_stocks.py
# import asyncio
# from app.tools.yfinance_tool import stock_analyzer

# MANIFEST = {
#     "name": "compare_stocks",
#     "description": "Compare technical indicators and returns across 2-5 stock tickers side by side.",
#     "input_schema": {"tickers": "list of ticker symbols, e.g. ['AAPL', 'MSFT']", "period": "optional, defaults to 6mo"},
# }

# async def compare_stocks(tickers: list[str], period: str = "6mo") -> dict:
#     if len(tickers) > 5:
#         raise ValueError("compare_stocks supports a maximum of 5 tickers per request.")

#     results = await asyncio.gather(
#         *[stock_analyzer(t, period) for t in tickers],
#         return_exceptions=True,
#     )

#     output = {}
#     for ticker, result in zip(tickers, results):
#         output[ticker.upper()] = {"error": str(result)} if isinstance(result, Exception) else result

#     return {"tickers_compared": [t.upper() for t in tickers], "results": output}