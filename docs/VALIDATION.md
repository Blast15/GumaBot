# GumaBot — current validation status

Updated: 2026-09-10

This file describes the **current validation boundary**. Historical pass counts and obsolete
"NOT RUN" snapshots are intentionally not repeated here; Git history preserves them. For the
implementation review and the most recent recorded local/CI evidence, see
[`RELIABILITY.md`](RELIABILITY.md). GitHub Actions is the authority for current automated CI.

## Automated validation in the repository

The CI workflow currently validates Python 3.12 on Linux and Windows and includes:

- dependency installation from hashed lock files and `pip check`;
- Ruff lint and format checks;
- mypy over the application source;
- pytest with branch coverage and an enforced 85% minimum;
- `main.py --check` startup validation;
- SQLite integrity/foreign-key checks and migration regression coverage;
- Windows Python Launcher startup;
- wheel/sdist build;
- a short 30-second **offline** soak;
- a separate dependency security audit.

These checks validate the codebase and offline service behavior. They do not by themselves
validate a live Discord deployment.

## Production-validation status

| Area | Current status | What is still required |
| --- | --- | --- |
| Discord live E2E | **NOT YET VALIDATED** | Run the dedicated test application/guild protocol with real user interactions, components, restart/resume, reconnect, stale/expired controls, permission changes and global propagation. |
| 24–72h stability | **NOT YET VALIDATED** | Run the soak harness for at least 24h, then 72h if stable, and retain host/resource evidence. |
| Off-site backup | **IMPLEMENTED, ENVIRONMENT NOT VERIFIED** | Configure a real rclone remote and scheduler, upload a generation, download it, restore to a separate DB and run `scripts/check_db.py`. |
| Branch protection | **NOT ENABLED** | Protect `main` and require `quality (ubuntu-latest)`, `quality (windows-latest)` and `security` before merge. Prevent force-push/deletion; require PRs and up-to-date checks as appropriate. |
| Observability | **STRUCTURED LOGGING ONLY** | Route logs/metrics to a production collector, add dashboards/alerts, error aggregation, uptime checks and latency percentiles. |
| Database scale | **SINGLE INSTANCE** | SQLite is intentionally supported for one bot process. Re-evaluate PostgreSQL only when contention/load requires it. |
| Type checking | **INCREMENTAL** | mypy passes the configured checks, but the project is not claiming fully strict typing. |

The detailed live Discord, soak, backup/restore and operations procedures are in
[`OPERATIONS.md`](OPERATIONS.md).

## Gameplay/reliability clarifications

### Pickcard

Pickcard samples without replacement and can expose one, two or three choices depending on the
available pool. The slash-command wording and invalid-choice error must therefore remain dynamic;
the implementation must not assume that three cards always exist.

### Reminder delivery

Reminder rows use durable pending/claimed/sent/failed state with leases, retry/backoff and restart
recovery. The guarantee is **not exactly-once**. If Discord accepts a DM and the process crashes
before SQLite records `sent`, a retry can deliver a duplicate. Conversely, the retry ceiling means
eventual delivery is not guaranteed. See the dedicated section in `OPERATIONS.md`.

### Offline versus live soak

`scripts/soak.py` deliberately blocks provider network access. It validates service/database
stability but does not prove Discord Gateway behavior, DNS/TCP/TLS recovery, provider behavior,
Discord rate limiting or real traffic. A separate low-traffic live soak on the dedicated test bot
is required for those claims.

## Release claim

Until the four P0 deployment checks below are completed with retained evidence, describe GumaBot as
**production-capable for a single instance**, not **fully production-validated**:

1. full Discord live E2E;
2. 24h+ sustained soak;
3. real off-site backup plus restore test;
4. branch protection on `main`.

## Sources

- Repository: https://github.com/Blast15/GumaBot
- Actions: https://github.com/Blast15/GumaBot/actions
- Reliability review: https://github.com/Blast15/GumaBot/blob/main/docs/RELIABILITY.md
- Operations runbook: https://github.com/Blast15/GumaBot/blob/main/docs/OPERATIONS.md
- CI workflow: https://github.com/Blast15/GumaBot/blob/main/.github/workflows/ci.yml
- Discord smoke: https://github.com/Blast15/GumaBot/blob/main/scripts/discord_smoke.py
- Offline soak: https://github.com/Blast15/GumaBot/blob/main/scripts/soak.py
- Off-site backup: https://github.com/Blast15/GumaBot/blob/main/scripts/backup_offsite.py
