# Reliability review implementation — 2026-09-10

Base commit: `9c8aa7c8e0fe891dcb4cb0d0c3d2701ebfb86fe9`.
This records code changes and separates them from deployment evidence.

| # | Review item | Resolution / remaining evidence |
|---|---|---|
| 1 | CI/CD | Push/PR/manual CI: Python 3.12, Ruff, formatting, mypy, pytest, branch coverage >=85%, startup, SQLite, build and short soak. No automatic production deployment. |
| 2 | Live Discord E2E | Dedicated-guild login/permission/sync smoke script and full human-interaction protocol provided. **NOT RUN:** no test token/guild supplied. |
| 3 | Windows | Windows runner includes full suite and Python Launcher startup. Linux and Windows CI passed in run 34458904584, including Python Launcher, package build and short soak. |
| 4 | 24–72h soak | Runnable offline wall-clock harness with resource budgets. Only the 30-second smoke was run locally; long and live runs remain **NOT RUN**. |
| 5 | Dependency lock/audit | Production/development transitive hash locks, pip-tools inputs, Dependabot and weekly audit. Audit found vulnerable pytest 8.4.2; upgraded to 9.1.1. |
| 6 | Type checking | Mypy checks all 42 application source files including untyped bodies. Not a fully strict/fully annotated codebase. Fixed concrete None/channel/callback issues. |
| 7 | Ruff rules | Added B, ASYNC, UP, SIM, RUF, S. Narrow documented exceptions for tests, natural-language punctuation, validated SQL identifiers and one explicit fallback. |
| 8 | Branch coverage | Enabled and enforced >=85%; no coverage exclusion to bypass the gate. |
| 9 | Reminder reliability | Durable pending/claimed/sent/failed state, leases, timeout, five attempts, backoff, opt-out and fair paging; success timestamp only after DM. Regression tests cover failure/restart/race/starvation. |
| 10 | SQLite scaling | Retained single-instance SQLite; operational limits and PostgreSQL migration boundary documented. No unsupported multi-instance/HA claim. |
| 11 | Off-site backup | rclone upload, SQLite validation, download verification and bounded verified generations. Mock tests verify ordering and failure safety. Remote credentials/scheduler/real restore remain **NOT CONFIGURED/NOT RUN**. |
| 12 | Server drop | Shared create_drop service samples rarity using pack odds, then a random card in that tier. No longer selects first catalog ID. |
| 13 | Quiz bank | Questions generated from catalog facts; snapshot saved with each session; old sessions remain compatible. Diversity test exercises >300 distinct prompts. Small catalogs retain static fallback. |
| 14 | Pickcard duplicates | Sampling without replacement; one/two-card pools and invalid choice indices covered. |
| 15 | Production RNG | SystemRandom defaults in shared services/provider; seeded injection retained in tests. Not a claim of externally provable fairness. |
| 16 | TCGdex 429 | Numeric/date Retry-After, jitter, total budget, shared cooldown, circuit breaker and stale cache. Regression tests include long/invalid headers and repeated failures. |
| 17 | Observability | JSON logs for command/domain/worker/API/cache/reminder/Gateway/DB events; no external collector/dashboard installed. |
| 18 | Startup traceback | Unexpected startup exceptions use log.exception; formatter preserves traceback. |
| 19 | Large modules | Command facade reduced from ~580 to 71 lines with collection/economy/social/gameplay/progression modules. Gameplay facade reduced from ~380 to 28 lines with battle/sessions/journey/quiz modules. Published migration SQL preserved. |
| 20 | Package metadata | Project name/version/Python requirement, dependency metadata, repository URL, pinned setuptools backend, wheel/sdist build. main.py intentionally remains the application entry point. |

## Local validation

Executed with Python 3.12 on Linux using a clean virtual environment installed with
`--require-hashes -r requirements-dev.txt`:

- `python -m pip check`
- `python -m ruff check .`
- `python -m ruff format --check .`
- `python -m mypy`
- `python -m pytest --cov=gumabot --cov-report=term-missing -q`
- `python main.py --check` with an offline dummy token
- `python scripts/check_db.py`
- `python -m build --no-isolation`
- `python scripts/soak.py --seconds 30 --interval 0.1`
- `python -m pip_audit --require-hashes -r requirements-dev.txt`

The offline soak completed 73 cycles in 30.26 seconds with one asyncio task and
28,004 bytes of tracked Python heap growth after warm-up. This is one short local
measurement, not a sustained production performance result. Startup registered 77
command entries; SQLite integrity and foreign keys passed at schema version 5.
All four historical migrations remain unchanged; the fifth adds reminder state.

Final local result: **107 passed, 1 external test deselected; branch coverage 89.53%**.
Mypy passed all 42 application files and dependency audit found no known vulnerabilities.
See CI for final per-platform test/coverage/audit results. Full Discord interactions,
Gateway reconnect/global sync, 24–72h soak, real off-site backup/restore and HA have
not been validated in this session. Branch protection is not enabled automatically.

## Links

- Source: https://github.com/Blast15/GumaBot
- CI: https://github.com/Blast15/GumaBot/actions
- Operations: https://github.com/Blast15/GumaBot/blob/main/docs/OPERATIONS.md
- Workflow: https://github.com/Blast15/GumaBot/blob/main/.github/workflows/ci.yml


First remote CI run: https://github.com/Blast15/GumaBot/actions/runs/34458904584
— Linux, Windows and security jobs all passed for commit `42782a4`.
A subsequent reminder regression hardens stale scan/claim state using SQLite
`UPDATE ... RETURNING`; the local suite then passed 107 tests at 89.53% coverage.
