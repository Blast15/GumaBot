# GumaBot

Python 3.12+ Discord collectible-card game with local SQLite storage. Windows setup:

```bat
git clone https://github.com/Blast15/GumaBot
cd GumaBot
py -m pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set `DISCORD_TOKEN` to your own Discord bot token, then run:

```bat
py main.py
```

On systems without Python Launcher, replace `py` with `python` and use your OS file-copy command. Run from the repository root. While this implementation is on the `feat/gumabot-standalone` review branch, select that branch before installation with `git switch feat/gumabot-standalone`.

First startup creates data/cache/log directories, SQLite and versioned migrations. Discord, shared HTTP, workers and the optional webhook listener share one application lifecycle. Ctrl+C shuts them down together. No separate infrastructure or web process is required.

## Discord setup

Create your bot at https://discord.com/developers/applications and invite it with `bot` and `applications.commands` scopes. Grant View Channels, Send Messages, Embed Links and Attach Files. Only server managers may run `/setchannel`.

Message Content, Server Members and Presence privileged intents are not required. Guild message events count activity without storing message text; bots/webhooks are ignored. Counts are throttled to one event per user per minute and one drop per guild per hour. Guild rankings include registered players who have invoked commands in that guild, not every Discord member.

`SYNC_COMMANDS_ON_START=true` syncs in `setup_hook`, once per process login, not every reconnect. `DEV_GUILD_ID` enables development guild sync; otherwise sync is global. Discord may take time to propagate global changes. Disable sync for routine restarts after registration is complete.

## Commands and systems

Use `/start`, `/play`, `/guide` and `/help`. Full registered commands and parameters: [docs/COMMANDS.md](docs/COMMANDS.md). `/help` reads the actual command tree.

| System | Behavior |
| --- | --- |
| Starter | One registration, 150 coins, five cards with a guaranteed Holo-or-higher |
| Packs | Five cards, one energy, 1% God Packs, saved results, image reveal, selectable sets |
| Energy | One per two hours, natural cap three; purchased/vote energy can exceed the cap |
| Collection | Instance codes, inventory filters/sorting, fuzzy search, missing cards, completion milestones, chase meter |
| Grading | Four half-point subgrades, final grade 1–10, persisted queue, certificates and original GumaBot frame |
| Customization | Tint tokens, favorites, atomic code swaps, fusion of three raw duplicates |
| Economy | Integer coins/Aura, immutable ledger, rolling 24-hour daily, gifts, items, boxes, virtual blackjack |
| Trading | Invitation, escrow for cards/coins/items, confirmation reset after changes, atomic settlement, expiry refunds |
| Market | Atomic buy, removal, protected bulk-sell preview, immutable history and 7/30-day statistics |
| Auctions | Reserved funds, outbid refunds, buyout, restart-safe settlement |
| Social | Spare-duplicate Pack Peek and one-winner guild drops |
| Games | Five-instance decks, authoritative duel turns, eight original gym leaders, quiz, image guessing, pickcard |
| Journey | Battles/treasure/springs/supplies, stages, health, rest and potion bag |
| Progression | Three daily quests, achievements, 50 defined level rewards, rankings, monthly UTC seasons and Hall of Fame |
| Preferences | Opt-in reminders, trainer choices, feedback modal saved in SQLite |

Balance rules are in `gumabot/services/rules.py`; progression/shop seed data is versioned in migrations; encounters/questions are in `services/engines.py`. Odds are GumaBot game odds, not physical booster probabilities. Weights are normalized over available tiers in a set. A set needs a Holo-or-higher pool. Ten ordinary packs fill the chase meter for one free pack with doubled Holo-or-higher weights. Consumed/system-sold instances remain for audit but leave usable inventory and completion counts.

Examples:

```text
/openpack set:base1
/inventory rarity:Holo graded:false sort:condition
/grade code:GUMA-XXXXXXXX lane:express
/trade user:@friend
/trade trade_id:<id> action:accept
/trade trade_id:<id> action:add kind:card reference:GUMA-XXXXXXXX
/trade trade_id:<id> action:add kind:coins amount:50
/trade trade_id:<id> action:confirm
/market list code:GUMA-XXXXXXXX price:100
/auction create code:GUMA-XXXXXXXX price:100 hours:24
/deck codes:GUMA-AAAAAAAA GUMA-BBBBBBBB GUMA-CCCCCCCC GUMA-DDDDDDDD GUMA-EEEEEEEE
/journey action:explore
/journey action:potion
/useitem item:booster
/favorite code:GUMA-XXXXXXXX enabled:true
```

Trades expire after 30 minutes; Peek/drops and quiz/pickcard/blackjack sessions after ten minutes. Expired blackjack wagers are forfeited to prevent losing-hand reset abuse. Duels expire after 30 minutes and release cards. Persisted IDs let commands resume active workflows after restart; service authorization still checks the interacting player.

## Free API and local cache

TCGdex is the default, with no API key or paid plan. `CardDataProvider` and normalized `CardDefinition` isolate game code from provider JSON. One shared HTTP client uses a 5-second connect timeout, 10-second network timeout, bounded workflows, and at most three attempts on network/timeout/429/selected-5xx failures with backoff and jitter. Concurrency: API five, image downloads three, renders two.

Set-list/metadata TTL: 24 hours. Card TTL: seven days. `provider_cache`, `card_sets` and `card_catalog` are local SQLite tables. Identical resource requests share an in-flight task. Valid stale data is used on API failure; malformed cache data is refreshed. Inventory uses local metadata. Set-list refresh does not block Discord startup; first use lazily syncs a set. `/admin sync_cards set_id:<id>` is restricted to the bot owner and prewarms/refreshes sets. A usable cached set remains playable offline; refreshing metadata is explicit. Upcoming dates are shown only from verified cached metadata; missing future dates are not invented.

Images are accepted only from HTTPS `assets.tcgdex.net`, without redirects/arbitrary user URLs. Limits: 5 MB download, PNG/JPEG/WebP Content-Type, 4096 pixels per dimension, 12 million pixels. Pillow verifies files and enforces decompression limits. Hash-named files are reused. Renders operate on copies, with an original placeholder for missing images. Tint never alters the cached original.

## Optional Top.gg webhook

Default: `ENABLE_TOPGG_WEBHOOK=false`. `/vote` returns a link when `TOPGG_BOT_ID` is set; calling it alone never grants rewards.

For verified rewards, set the bot ID, generated `TOPGG_WEBHOOK_SECRET`, `ENABLE_TOPGG_WEBHOOK=true`, and `TOPGG_WEBHOOK_VERSION=v1`. The embedded listener exposes `/health` and `/webhooks/topgg` at `WEBHOOK_HOST:WEBHOOK_PORT`. Top.gg needs a publicly reachable HTTPS endpoint; localhost alone cannot receive its callbacks. This subsystem is optional and does not need a second Python process.

v1 verifies raw-body HMAC-SHA256 signatures with constant-time comparison and a five-minute timestamp window. Vote IDs are durably deduplicated. Events are queued in SQLite before acknowledgement; workers grant rewards afterward. Users must have run `/start`. Default reward is 90 coins, two energy and one card per rolling 12 hours. Weekend vote weight does not multiply the game reward.

Legacy Authorization-secret payloads are supported only with `TOPGG_WEBHOOK_VERSION=v0`. These payloads lack an immutable event ID; replay protection also depends on the reward cooldown. Prefer v1 for new installations.

## Database and recovery

SQLite uses WAL, foreign keys, 5000 ms busy timeout and short `BEGIN IMMEDIATE` transactions with conditional updates/unique constraints. Networking/rendering/Discord sends run outside write transactions. Auction/trade holds debit available balance, record ledger entries, and release or settle atomically.

`synchronous=NORMAL` is a local-game performance choice: SQLite consistency is preserved after crashes, but sudden machine power loss can lose the latest transactions. Keep regular backups and avoid unreliable network filesystems.

Migrations use `PRAGMA user_version`, sequential transactional DDL and SQLite safe backup before upgrading an existing database. Failures roll back; newer-than-application databases are rejected. Keep applied migrations immutable and append future changes.

```bat
py scripts/backup_db.py
py scripts/check_db.py
```

Backups use SQLite's backup API and are stored in `data/backups/`. Stop the bot before restoring:

```bat
py scripts/restore_db.py data/backups/gumabot-YYYYMMDD-HHMMSS-ffffff.db
```

Restore validates integrity/schema, requires typing `RESTORE`, makes a pre-restore backup and uses SQLite's backup API. Keep important copies outside the local machine.

## Verification

```bat
py main.py --check
py -m pip install -r requirements-dev.txt
py -m ruff check .
py -m ruff format --check .
py -m pytest -q
py -m pytest --cov=gumabot --cov-report=term-missing --cov-fail-under=85
py scripts/check_db.py
```

`--check` validates configuration, DB/migrations, rules and command registration without connecting Discord. It requires a nonempty token setting but does not authenticate that token.

Normal tests use real temporary SQLite, mocked HTTP boundaries, injectable clocks/RNG, races and a fixed-seed 100,000-pack simulation. Live API tests are excluded by default:

```bat
py -m pytest -m external -q
```

Actual executed results and limits: [docs/VALIDATION.md](docs/VALIDATION.md). Mypy is not configured. Cross-platform path design is not an executed Windows test or a 24/7 soak test.

## Source layout

| Path | Responsibility |
| --- | --- |
| `main.py` | Startup and graceful shutdown |
| `gumabot/config.py`, `logging_config.py`, `app.py` | Settings, rotating UTF-8 logs, shared lifecycle |
| `gumabot/database/` | SQLAlchemy async transactions and SQLite migrations |
| `gumabot/providers/` | Provider interface, normalized models, TCGdex/cache |
| `gumabot/services/` | Collection, economy, social systems, gameplay, progression |
| `gumabot/cogs/` | Slash commands and groups |
| `gumabot/views/`, `rendering/` | Buttons, selects, modals, pages, card composites |
| `gumabot/jobs/` | Workflow workers, reminders, signed vote inbox/listener |
| `gumabot/utils/` | Clock and completed-operation logging |
| `scripts/` | Backup, restore and DB check |
| `tests/` | Unit, integration, concurrency, Discord adapter and optional external tests |
| `docs/` | Generated command reference and execution report |

## Independence and references

Only public functionality inspired this implementation. No reference-bot code, private APIs, branding, slab/pack art or copied proprietary tutorial text is included. Gym names, tutorial text and GumaBot frames are independent. Card names/images remain third-party material; API availability does not transfer artwork ownership. No card artwork is committed.

- Repository: https://github.com/Blast15/GumaBot
- Public features: https://top.gg/bot/1362516883785515199?campaign=4-0
- Public commands: https://top.gg/bot/1362516883785515199/commands
- Reference site: https://thepokebot.com/
- Reference FAQ: https://thepokebot.com/faq
- TCGdex: https://tcgdex.dev/
- REST docs: https://tcgdex.dev/rest
- Card endpoint: https://tcgdex.dev/rest/card
- REST base: https://api.tcgdex.net/v2/en
- SDK reference: https://tcgdex.dev/sdks/python
- Discord intents: https://discordpy.readthedocs.io/en/stable/intents.html
- Top.gg signatures: https://docs.top.gg/webhooks/overview
- Top.gg events: https://docs.top.gg/webhooks/events
