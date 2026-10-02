# What this desk is

The LangGraph and Grok plan that used to live in this file was not built. The running system is the TradeX desk described in the [root README](../README.md) and [REPO.md](../REPO.md).

The loop ranks one selected NSE index, sizes from the risk limits, and sends orders through Dhan or the paper ledger. Groq, when `GROQ_API_KEY` is set, may pick a symbol and a side from that list for a pending suggestion. It cannot place an order. Quantity and price come from the limits and a fresh Dhan quote.

Intraday positions flatten at 15:15 IST, on the stop, or on the target. A live entry parks a stop-market at Dhan. Delivery positions are not flattened by the clock.

## Before live capital

1. Confirm Dhan's current rules for API algos, including any static IP or algo id they require. This repository does not register one.
2. Run `TRADING_MODE=paper` until the desk, the token renewal, and the flatten behave the way you expect.
3. The model is not a risk check. The risk limits, the session clock, and the product rules are.
4. Use an amount you can lose. A market exit can slip past the daily-loss number. The broker stop is what bounds a position while this process is down.

Keep the API process running on weekdays. Token renewal and the 15:15 flatten do not happen when it is stopped.
