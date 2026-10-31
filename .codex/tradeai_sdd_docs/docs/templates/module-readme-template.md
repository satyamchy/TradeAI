# Module: <Name>

## Status

`NOT_STARTED` / `STRUCTURED` / `LEGACY_WRAPPED` / `INDEPENDENTLY_TESTED` / `INTEGRATED` / `E2E_VALIDATED`

## Responsibility

Describe what this module owns in 2–4 sentences.

## Out of scope

List what this module must not own or call.

## Public service interface

List public functions, their request DTOs and response DTOs.

## Dependencies

List injected shared services, repositories and provider interfaces. Do not list another module's private implementation.

## Persistence

Describe tables/repositories owned by this module. State whether persistence is required.

## Run this module's tests

Run from `backend/`:

```powershell
pytest tests/unit/modules/<module_name> -q
```

## Test coverage

- [ ] Contract/schema tests
- [ ] Business-logic unit tests
- [ ] SQLite repository tests, if applicable
- [ ] External adapter tests using fakes/mocks
- [ ] Failure-path tests
- [ ] Module boundary/import rule tests

## Known limitations

Record deferred behavior and external dependencies.

## Change history

| Date | Change | Tests | Result |
|---|---|---|---|
