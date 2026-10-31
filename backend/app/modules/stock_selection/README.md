# Stock Selection (Module 1)

Owns screening inputs, index/list resolution, instrument validation, and candidate batches. It does not call AI providers, evaluate risk, or place orders.

`service.py` defines the typed `StockSelectionService` boundary. The existing screener/index/NSE code remains in its legacy locations and is wrapped when Module 1 is implemented. This package is currently structural; its interface tests do not claim screening functionality is complete.
