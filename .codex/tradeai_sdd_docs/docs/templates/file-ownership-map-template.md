# TradeAI — Existing File Ownership Map

Complete this file during Phase 0 before moving files.

| Existing path | Current responsibility | Current callers/importers | Proposed owner | Action | Compatibility wrapper needed? | Tests to run |
|---|---|---|---|---|---|---|
| `backend/app/...` | | | | KEEP / WRAP / MOVE / SPLIT / RETIRE | YES / NO | |

## Rules

- Inspect the implementation and callers before assigning an owner.
- Shared market data, instrument mapping, clock, logging and database concerns belong in `shared/`, not arbitrarily inside a business module.
- Do not create duplicate Dhan clients, schedulers, watchdogs or trading harnesses.
- Do not delete an old file until all imports/callers have moved and regression tests pass.
