# Module Specification Template

## 1. Module name

## 2. Responsibility

One paragraph describing what the module owns and what it explicitly does not own.

## 3. In-scope capabilities

- 

## 4. Out-of-scope capabilities

- 

## 5. Public service functions

| Function | Input DTO | Output DTO | Side effects |
|---|---|---|---|
| | | | |

## 6. Data ownership

List tables/entities the module owns. Do not duplicate another module's repository ownership.

## 7. Dependencies

List allowed public service interfaces and shared services. Identify forbidden dependencies.

## 8. State transitions

Document lifecycle states and valid transitions.

## 9. Errors and retries

List expected error codes, retryability and recovery behavior.

## 10. Security and safety rules

List invariants the module must never violate.

## 11. Tests

List unit, integration, negative and end-to-end cases.

## 12. Acceptance criteria

Write observable, testable criteria. Avoid subjective criteria such as "works well".


## Independent test plan

- Unit tests: `backend/tests/unit/modules/<module_name>/`
- Repository tests: temporary SQLite database, if persistence is owned by this module.
- Adapter tests: fakes/mocks; no live provider or broker calls in default test suite.
- Module test command: `pytest tests/unit/modules/<module_name> -q` (run from `backend/`).
- External smoke tests: explicit `external` marker and separate command.
- Integration tests: `backend/tests/integration/`; do not place cross-module tests in the unit test folder.

## Structure-only status

State whether this module is only scaffolded, wrapped around legacy code, independently functional, or integrated with adjacent modules. Do not use a single generic `complete` status.
