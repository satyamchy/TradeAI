# Harness

Owns scheduling and the automation runner. `get_automation_runner()` returns the existing singleton in `app.trading.automation_runner`; Phase 1 introduces no second scheduler or watchdog. Starting/stopping remains the responsibility of the one FastAPI lifespan.
