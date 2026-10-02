# TradeX API

FastAPI on port 8000. How to run it, the three roles, and paper versus live are in the [root README](../README.md). Production is in [REPO.md](../REPO.md).

Route behavior and status codes are the docstrings on the handlers. FastAPI publishes them at `/docs`.

Run one process. Do not add uvicorn workers. SQLite, the order lock, and the automation loop live in this process.

From this directory, with the virtualenv active:

```text
python main.py
python -m pytest tests -q
```
