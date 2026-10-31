# Stock Selection (Module 1)

Owns manual candidate selection, symbol validation, instrument mapping, candidate persistence, and the public wrapper for the existing read-only index screener. It does not call AI providers, evaluate risk, or place orders.

## Public service

`StockSelectionService` exposes:

- `create_candidates(request, owner_id=...)` — normalize and validate manual NSE symbols, report per-symbol rejections, persist the batch and accepted candidates.
- `get_candidate(candidate_id, owner_id=...)` and `list_candidates(filters, owner_id=...)` — retrieve only the caller's records when an owner is supplied.
- `rank_candidates(request)` — thin typed adapter over the existing NIFTY index screener. The old ranking implementation remains in its existing location during this migration.

The API is exposed at `/api/v1/stock-selection/candidates`. Candidate creation requires an authenticated trader; admin and viewer roles cannot use it. The existing `/api/v1/screener/nifty50` response shape and role behavior remain available.

## Symbol mapping

`LocalNseInstrumentResolver` reads a local Dhan compact instrument CSV from `INSTRUMENT_MASTER_PATH` when configured and present. It uses only NSE equity rows, normalizes the Dhan security ID, rejects ambiguous mappings, and stores the resolver source and UTC resolution timestamp with each candidate. It never constructs a Dhan client or makes a network call.

When the local CSV is absent, the current built-in NIFTY 50 universe is a limited fallback. Those candidates receive a Yahoo-style `.NS` analysis ticker and `ANALYSIS_ONLY` status because no Dhan security ID is known. They may be analyzed, but must not be treated as executable. The fallback rejects symbols outside that known universe. A Dhan ID is never derived from a Yahoo ticker.

Duplicates are rejected within a submitted batch. Re-selecting a symbol in a later batch is allowed so a user can intentionally request fresh research; there is no global symbol uniqueness constraint.

The `004_stock_selection` Alembic revision owns the additive `candidate_batches` and `stock_candidates` tables. Rejections are retained with the batch for audit; candidate rows are created only for resolved instruments. Legacy SQLite schema creation remains removed from runtime initialization.

## Tests

Run independently from `backend/`:

```powershell
python -m pytest app/modules/stock_selection/tests -q
```

The tests use temporary SQLite databases migrated through Alembic, fake ranking/resolver providers, and local temporary CSV fixtures. They make no broker or AI-provider calls.
