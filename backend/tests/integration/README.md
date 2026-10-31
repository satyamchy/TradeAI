# Integration tests

`test_workflow_boundaries.py` covers the five Phase 3 boundaries in sequence:

1. Stock Selection → AI Analysis
2. AI Analysis → Decision Engine
3. Decision Engine → Execution
4. Execution → Position Monitoring
5. Position Monitoring → provider-neutral exit decision → Execution

Run from `backend/` after the isolated module suites:

```powershell
python -m pytest tests/integration/test_workflow_boundaries.py -q
```

The tests use temporary SQLite and fake analysis, market, account and broker adapters. They do not call Dhan or paid LLM providers. These boundary tests are not end-to-end validation against a real paper ledger or market feed.
