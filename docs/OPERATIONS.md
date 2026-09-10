# Production validation and operations

This release adds automated gates and fixes; it does not certify a live deployment.
Use Python 3.12 and one bot process per SQLite database. Continue starting with
`py main.py` on Windows or `python main.py` elsewhere.

## Reproducible installation and CI

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements.txt
.venv\Scripts\python main.py --check
```

For development, install `requirements-dev.txt` instead. Both files pin transitive
dependencies and hashes. Inputs are `requirements.in` and `requirements-dev.in`.
The development lock is constrained by the production lock; colorama is included
for Windows pytest. These lockfiles are validated for Python 3.12; resolve and test
separate locks before changing the Python minor version.

To update deliberately, using the locked development environment:

```text
python -m piptools compile --upgrade --generate-hashes --strip-extras --no-emit-index-url --no-emit-trusted-host requirements.in -o requirements.txt
python -m piptools compile --upgrade --generate-hashes --strip-extras --no-emit-index-url --no-emit-trusted-host --allow-unsafe requirements-dev.in -o requirements-dev.txt
python -m pip install --require-hashes -r requirements-dev.txt
python -m pip check
python -m pip_audit --require-hashes -r requirements-dev.txt
```

Review both lock diffs and run CI on both operating systems. Dependabot checks pip
and Actions weekly. CI checks Ruff, formatting, mypy (including untyped function
bodies), branch coverage >=85%, fresh startup, SQLite integrity/foreign keys,
migration upgrade/rollback regression tests, package build and a 30-second offline
soak. Windows also exercises `py -3.12 main.py --check`. Security audit is a separate
required job and runs weekly to detect newly disclosed vulnerabilities.

Enable branch protection requiring `quality (ubuntu-latest)`,
`quality (windows-latest)` and `security` in repository settings. Workflow creation
alone does not enable branch protection or deploy/restart the bot. Package metadata
supports wheel/sdist builds; `main.py` remains the only application entry point.

## Reminder delivery guarantees

A migration appends `next_check_at` and a separate delivery table. Existing migration
SQL and wallet data are preserved. Delivery proceeds `pending -> claimed -> sent`;
failures retry with exponential delays of 60, 120, 240 and 480 seconds, up to five
attempts. A claim expires after 120 seconds; Discord lookup/send has a 30-second
budget. Forbidden/not-found responses stop immediately. `last_sent` advances only
after a successful send and stores the event timestamp, allowing newer events to
be discovered. Opt-out is checked before claiming. Rotating scans avoid starvation.

One row per user/reminder kind bounds outbox storage. Terminal failures remain
visible; a newer due event can replace them. Retries resume after restart. A crash
after Discord accepted the DM but before SQLite recorded success can cause a
duplicate. This is **at-least-once attempted delivery**, not exactly-once delivery;
Discord does not provide an idempotency key for these sends. Five attempts are a
hard ceiling, so eventual delivery is not guaranteed.

Inspect failures locally:

```sql
SELECT user_id,kind,due_at,status,attempts,next_attempt_at
FROM reminder_deliveries WHERE status='failed';
```

## Gameplay and provider behavior

Production services use `SystemRandom`; deterministic seeded RNGs remain injectable
in tests. Server drops first select a rarity using existing pack odds, then select
uniformly among cards of that rarity. Pickcard samples without replacement and shows
one or two choices if fewer than three cards exist. Quiz generates set, rarity,
illustrator and HP questions from up to 5,000 cached catalog cards, persists the ten
selected questions/options/answers, and preserves older indexed sessions. With a
small catalog it fills missing questions from the original bank. This increases
variety, but does not claim to prevent all farming or cheating.

TCGdex honors numeric and HTTP-date `Retry-After`, adds jitter and retains the
40-second overall budget. Delays beyond that budget fail quickly or serve stale
cache; the provider-wide cooldown prevents immediate new calls. Three exhausted
requests open a 30-second circuit. A longer server-supplied cooldown takes priority.

## Dedicated Discord test environment

**Not satisfied by mocks or `--check`.** Use a separate Discord application/bot,
a dedicated test guild, two consenting test accounts and a separate database.
Set `DISCORD_TOKEN`, `DEV_GUILD_ID`, `DATABASE_PATH` and `FEATURED_SET` locally;
never commit tokens or place them in issue/PR text. Invite the test bot with
`bot` and `applications.commands` scopes. Grant view/send/embed/attach/history
permissions to its test channel, without Administrator.

```text
python scripts/discord_smoke.py --channel-id YOUR_TEST_CHANNEL_ID
```

This intentionally syncs only the dedicated guild and checks login, guild access,
channel permissions and required command names. It does not send player messages,
simulate interactions or establish the Gateway. For full E2E, start the test bot
normally and record the commit SHA, UTC times, versions, guild/channel IDs,
message links, expected/actual outcomes and sanitized logs for every row:

| Scenario | Required live evidence |
|---|---|
| `/start` twice, `/openpack` and reveal | One starter reward, persisted cards, no double debit, timely defer/followup |
| `/trade` with two accounts | Accept, modify offer, reconfirm, cancel, stale controls and exact balances |
| `/market`, `/auction` | Buyer/seller permissions, competing purchase/bids, cooldown/settlement |
| Button/select/modal | Owner checks, cross-user rejection, valid result, timeout handling |
| Remove channel permissions / disable DMs | Useful errors, reminder retry or terminal failure, no false `last_sent` |
| Stop/restart with open trade/auction/quiz | Same persisted state, old controls behave correctly, no double settlement |
| Disconnect network then restore | Gateway disconnect/resume evidence, one worker, no sync/reconnect loop |
| Global command propagation | On the separate test application only: unset `DEV_GUILD_ID`, set `SYNC_COMMANDS_ON_START=true`, restart, record fetch and actual visibility times in two test guilds |
| Provider rate limits | Controlled mock 429 tests in CI; do not flood Discord to manufacture rate limits |

Use real people for user interactions; no self-bot or user-token automation.
A passing guild smoke is **not** a passing full live E2E run.

## 24–72 hour soak

```text
python scripts/soak.py --seconds 86400 --interval 1 > soak-24h.jsonl
python scripts/soak.py --seconds 259200 --interval 1 > soak-72h.jsonl
```

The harness creates a temporary database and prohibits provider network access.
It exercises packs, daily rewards, transfers through market/trades, auction
settlement and expiration jobs with an accelerated game clock while elapsed test
duration uses a real monotonic clock. It checks SQLite integrity, outstanding DB
connections/provider tasks, task growth and Python heap growth after warm-up.
Default heap growth budget is 64 MiB; exceptions/timeouts fail the run.
Database rows intentionally grow with completed gameplay. JSON output is bounded
rather than storing every measurement in memory. This does not measure native RSS,
live HTTP/Gateway reconnection, or real Discord traffic. Run the normal bot in the
dedicated guild alongside host RSS/file-descriptor monitoring for that evidence.
A 30-second CI smoke is not a 24-hour test. Do not use a GitHub-hosted job to claim
a single uninterrupted 72-hour run; use the intended deployment machine.

## Verified off-site backup and retention

Install rclone on the bot host, configure a named remote such as `archive`, and
choose a dedicated path on **another machine/account/storage system**. S3, B2,
Drive or a remote NAS are options. Configuring a local directory as a remote does
not provide off-site protection. rclone credentials remain in its user config.

```text
python scripts/backup_offsite.py --database data/gumabot.db --remote archive:gumabot --keep 14
```

The script uses SQLite's backup API, validates integrity/foreign keys, copies a new
generation and downloads it for content verification. Only after verification does
it upload a marker and prune the oldest marked generations beyond `--keep`.
Unrelated directories and unmarked failed uploads are not pruned. A failed copy or
check stops before pruning. Review/remove failed generations separately. Keep at
least two; the default is fourteen. Prevent overlapping scheduled runs.

For Windows Task Scheduler create a daily task at 03:00 under the same account
that owns the rclone config, with:

- Program: the absolute path to `.venv\Scripts\python.exe`.
- Arguments: `scripts\backup_offsite.py --database data\gumabot.db --remote archive:gumabot --keep 14`.
- Start in: the absolute GumaBot checkout directory.
- Configure “Do not start a new instance”; alert if task exit code is nonzero.

On Linux, a crontab example (replace the deployment paths):

```cron
0 3 * * * cd /srv/GumaBot && flock -n /srv/GumaBot/data/offsite.lock .venv/bin/python scripts/backup_offsite.py --database data/gumabot.db --remote archive:gumabot --keep 14 >> logs/offsite.log 2>&1
```

Rotate `offsite.log` and alert on failures/missing daily verified generations.
No remote or schedule is activated by installing this repository. Test restore on
a separate path first, then stop the bot before replacing the active database.
Do not point retention at a shared folder owned by another backup process.

## Observability and scale

Console and rotating file output are JSON. Events cover domain operation status
and latency, command completion/error, worker duration/failure, provider cache
hit/miss and API timing/errors, reminder failure, disconnect and resume.
`db_begin_error` includes a traceback; `db_writer_wait` duration is DEBUG-level.
These are structured events, not a Prometheus endpoint, latency SLO or installed
Grafana/Sentry dashboard. Route stdout/logs to your chosen collector; set alerts
for worker failures, repeated reminder failures, provider circuit openings, DB
contention and unexpected reconnect frequency. Do not export arbitrary interaction
payloads or environment variables as log labels.

SQLite is intentionally retained for a single instance. Track writer wait, DB size,
backup time and command latency before planning a PostgreSQL migration. Horizontal
scaling/HA requires a separate reviewed migration and changes to claims, transaction
semantics, backup/restore and integration tests. Merely changing a database URL is
not supported. The command domains and gameplay domains are now separate modules;
released migration SQL remains together to preserve upgrade history.

## References

- Repository: https://github.com/Blast15/GumaBot
- Actions: https://github.com/Blast15/GumaBot/actions
- pip-tools: https://pip-tools.readthedocs.io/en/stable/
- rclone content verification: https://rclone.org/commands/rclone_check/
- rclone listing: https://rclone.org/commands/rclone_lsjson/
