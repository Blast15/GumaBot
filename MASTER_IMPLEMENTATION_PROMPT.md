# MASTER IMPLEMENTATION PROMPT — GumaBot

> Mục tiêu: dùng prompt này cho một coding agent/LLM có khả năng đọc–ghi toàn bộ repository để xây dựng GumaBot từ đầu tới production. Đây là yêu cầu **functional parity dựa trên các tính năng được mô tả công khai** của Pokebot tại Top.gg và website chính thức, không phải yêu cầu sao chép mã nguồn, thuật toán nội bộ, artwork, thương hiệu, dữ liệu bí mật hay tài sản độc quyền của Pokebot.
>
> Ngày đối chiếu nguồn: 2026-09-09.

## 0. Vai trò của bạn

Bạn là Principal Python Engineer + Discord Bot Engineer + Backend Engineer + QA/SRE. Hãy trực tiếp xây dựng một Discord collectible-card/economy game bot tên **GumaBot** trong repository hiện tại, bằng Python và SQLite, có chất lượng production-ready, test đầy đủ, tài liệu vận hành rõ ràng, không để lại TODO/placeholder ở đường chạy production.

Không chỉ viết ví dụ hoặc skeleton. Hãy hoàn thiện source code, migration, seed/dev data, test, CI, Docker, tài liệu cài đặt và runbook để một người khác clone repo, cấu hình `.env`, chạy migration rồi khởi động được.

## 1. Nguyên tắc pháp lý và clean-room implementation

1. Chỉ dùng hành vi/tính năng công khai làm specification.
2. Không scrape hoặc copy source code, private API, private assets, database, secrets, text dài, hình card/slab/pack độc quyền hay branding của Pokebot.
3. Tên sản phẩm phải là **GumaBot**; UI/copywriting phải nguyên bản, không giả mạo Pokebot.
4. Với dữ liệu Pokémon/TCG hoặc artwork bên thứ ba: xây `CardDataProvider` abstraction. Production chỉ được dùng nguồn/API/dataset mà người vận hành có quyền sử dụng theo điều khoản của nhà cung cấp. Repo phải có dataset fixture nhỏ, tự tạo hoặc permissively licensed, để test không phụ thuộc dịch vụ bên ngoài.
5. Mọi logic game phải được tự thiết kế để đạt parity chức năng, không cố reverse-engineer xác suất/giá trị bí mật ngoài những gì nguồn công khai nêu.

## 2. Tech stack bắt buộc

- Python 3.12+.
- `discord.py` bản stable tương thích Python 3.12, sử dụng application commands/slash commands, buttons/selects/modals khi phù hợp.
- SQLite qua SQLAlchemy 2.x async + `aiosqlite` (hoặc giải pháp async tương đương có migration rõ ràng).
- Alembic migrations.
- FastAPI + Uvicorn cho health endpoint, Top.gg vote webhook và dashboard/API web tối thiểu.
- Pydantic Settings cho configuration.
- Pillow cho pack reveal/showcase/slab rendering nếu cần render ảnh cục bộ.
- HTTP client async (`httpx`).
- `pytest`, `pytest-asyncio`, `hypothesis` cho test; `ruff`, `mypy` hoặc `pyright` cho quality gate; `pip-audit` cho dependency audit.
- Pin dependencies bằng `pyproject.toml` + lockfile phù hợp.

Nếu lựa chọn package khác, chỉ thay khi có lý do kỹ thuật tốt và cập nhật tài liệu.

## 3. Kiến trúc repository bắt buộc

Thiết kế modular, dependency direction rõ ràng. Cấu trúc mục tiêu có thể điều chỉnh nhẹ nhưng phải đạt tương đương:

```text
GumaBot/
├─ pyproject.toml
├─ README.md
├─ .env.example
├─ .gitignore
├─ Dockerfile
├─ docker-compose.yml
├─ alembic.ini
├─ migrations/
├─ src/gumabot/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ config.py
│  ├─ logging.py
│  ├─ constants.py
│  ├─ db/
│  │  ├─ engine.py
│  │  ├─ models.py
│  │  ├─ repositories/
│  │  └─ transaction.py
│  ├─ domain/
│  │  ├─ cards.py
│  │  ├─ economy.py
│  │  ├─ packs.py
│  │  ├─ grading.py
│  │  ├─ trading.py
│  │  ├─ market.py
│  │  ├─ auction.py
│  │  ├─ duel.py
│  │  ├─ progression.py
│  │  ├─ quests.py
│  │  └─ seasons.py
│  ├─ services/
│  ├─ providers/
│  │  ├─ card_data.py
│  │  └─ topgg.py
│  ├─ discord/
│  │  ├─ bot.py
│  │  ├─ checks.py
│  │  ├─ views/
│  │  └─ cogs/
│  ├─ web/
│  │  ├─ app.py
│  │  ├─ routes/
│  │  └─ auth.py
│  ├─ rendering/
│  └─ jobs/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ property/
│  └─ e2e/
├─ scripts/
└─ docs/
   ├─ ARCHITECTURE.md
   ├─ DATABASE.md
   ├─ GAME_BALANCE.md
   ├─ OPERATIONS.md
   ├─ SECURITY.md
   └─ TESTING.md
```

Không đặt business logic trực tiếp trong Discord command handler. Handler chỉ parse input/permission, gọi service, render response.

## 4. SQLite production hardening

Vì yêu cầu bắt buộc SQLite, phải xử lý giới hạn concurrency cẩn thận:

- Enable `PRAGMA foreign_keys=ON`.
- Enable WAL (`journal_mode=WAL`).
- Thiết lập `busy_timeout` hợp lý.
- `synchronous=NORMAL` hoặc `FULL` phải được giải thích trong docs.
- Mọi thao tác economy/trade/market/auction phải atomic transaction.
- Dùng `BEGIN IMMEDIATE` hoặc transaction strategy tương đương cho luồng có tranh chấp ghi.
- Không dùng read-modify-write ngoài transaction cho coins/energy/card ownership.
- Có unique constraints/idempotency keys để chống double claim/double spend.
- Index đầy đủ cho user/guild/card/listing/status/expires_at/created_at.
- Không giữ transaction mở trong lúc gọi Discord API hoặc HTTP external.
- Có database backup command/script, retention, integrity check và restore procedure.
- Document giới hạn scale của SQLite và migration path sang PostgreSQL, nhưng implementation chính vẫn chạy hoàn chỉnh trên SQLite.

## 5. Data model tối thiểu

Thiết kế migration với ít nhất các nhóm bảng sau; tên có thể thay đổi nhưng semantics phải đầy đủ:

- `users`: Discord user, created_at, coins, aura, xp, level, vote streak, energy state, avatar/trainer choice, tutorial state.
- `guilds`: guild id, drop/announcement channel, locale/config, activity counters.
- `card_sets`: set metadata, release order/date, featured flags.
- `card_catalog`: card identity, set, number, rarity, image/provider metadata, battle stats or derivation metadata.
- `owned_cards`: unique instance code, owner, catalog card, condition, raw/graded state, tint/customization, acquired source/time.
- `pack_inventory` / `sealed_packs`.
- `pack_openings` + immutable pull audit rows.
- `energy_events` hoặc ledger tương đương.
- `currency_ledger`: mọi coin/aura/token delta với reason, correlation id, balance snapshot hoặc cơ chế audit tương đương.
- `cooldowns`.
- `grading_jobs`, `grade_certificates`, `grade_population` materialization/query support.
- `wishlists`.
- `pack_peek_offers/claims`.
- `server_drops` + claims.
- `trades`, `trade_items`, trạng thái negotiation/accepted/cancelled/expired.
- `market_listings`, `market_sales`, `price_history`.
- `auctions`, `auction_bids`.
- `duel_profiles`, `decks`, `deck_cards`, `duels`, `duel_turns`/battle log.
- `gym_progress`, `badges`.
- `quiz_stats`, `quiz_attempts`.
- `journey_progress`, `journey_inventory/bag`.
- `quests`, `user_quests`.
- `achievements`, `user_achievements`.
- `level_rewards` / claimed rewards.
- `seasons`, `season_stats`, `hall_of_fame`.
- `shop_items`, `user_items`.
- `reminder_preferences`.
- `reports`.
- `vote_events` với unique external event id/user+window để idempotent.
- `guild_activity` hoặc rolling counters phục vụ server drops.
- `outbox_events` nếu cần reliable background notification.

Tất cả timestamp lưu UTC. Discord snowflake lưu INTEGER/BIGINT-compatible. Money/score không dùng float nếu có thể gây sai số; grade half-point có thể lưu integer x2.

## 6. Nguồn dữ liệu card và cache

Tạo interface `CardDataProvider` hỗ trợ:

- list sets theo release order;
- load cards theo set;
- search card by name/code/catalog id;
- rarity metadata;
- image URL hoặc local asset reference;
- release dates/upcoming sets;
- cache TTL, retry exponential backoff + jitter, timeout;
- graceful degradation khi provider down.

Không để unit test gọi internet. Integration external phải có marker riêng và mặc định skip trong CI nếu thiếu key.

## 7. Feature parity bắt buộc — Core onboarding/UI

### `/start`

- Khởi tạo user idempotent.
- Người mới nhận starter reward: 150 coins và một starter/Legendary-style pack với ít nhất một Holo được đảm bảo theo public description.
- Không thể nhận lại bằng race condition hoặc spam command.
- Trả hướng dẫn tiếp theo.

### `/play`

Home screen tương tác, hiển thị tối thiểu:

- coins/aura/xp/level;
- energy hiện tại và ETA charge tiếp theo;
- daily/vote/gym/quiz/pack readiness;
- featured set;
- quest progress;
- nút/link tới inventory, packs, market, duel, guide.

### `/guide`

- Tutorial 7 chương ngắn theo public description, nội dung viết mới cho GumaBot.
- Buttons Previous/Next/Close.
- Không cần giữ DB transaction cho interaction view.

### `/help`

- Help phân nhóm command, permission-aware.

### `/avatarchoice`

- Danh sách trainer avatar lựa chọn từ asset hợp pháp/original của GumaBot.

## 8. Pack, energy và set chase

### Energy

- Max mặc định 3 energy.
- Regen mặc định 1 energy / 2 giờ.
- Tính lazy regeneration từ timestamp để không cần scheduler tick mỗi user.
- Reward energy từ daily, gym wins, quiz streak, Pack Peek và vote theo rules cấu hình.
- Không được vượt cap trừ khi explicit bonus-energy design có docs.

### `/openpack [set]` và `/packs [set]`

- Cho phép random set hoặc target một set cụ thể.
- Một pack có 5 cards.
- Cost energy thay vì cooldown chờ pack.
- Công khai nêu 1/100 God Pack: implement configurable `GOD_PACK_RATE=0.01`; God Pack gồm 5 Holo-or-better theo game rarity policy.
- Card reveal phải có rarity visual, condition, và `NEW` badge nếu lần đầu user sở hữu catalog card đó.
- Tạo pack image/composite bằng Pillow; nếu render lỗi, fallback embed text không làm mất transaction/pulls.
- Pack result commit một lần; retry Discord response không được tạo pack lần hai.

### Rarity ladder

Hỗ trợ tối thiểu: Common, Uncommon, Rare, Promo, Holo, SIR, Mythical. Odds phải nằm trong config/data, tổng xác suất test đúng 1.0 và có simulation test chống sai distribution lớn.

### Condition

Thiết kế condition scale rõ ràng từ poor/played tới pristine; lưu internal normalized score. Condition tác động grade/value/fusion theo document `GAME_BALANCE.md`.

### Set chase

- Progress từng user/từng set dựa trên unique catalog cards.
- Milestones 25/50/75/100% trả rewards một lần duy nhất.
- Chase Meter tạo progress riêng; khi full nhận free pack với double Holo odds.
- Featured set hàng tuần có bonus configurable.
- `/setcompletion` và alias/feature `/collection` hiển thị tiến độ theo set.
- `/missing [set]` hiển thị cards còn thiếu, phân trang.
- `/upcoming` hiển thị lịch set sắp phát hành từ provider/cache.

### Pack mua thêm

Hỗ trợ `/buypack` và compatibility command `/resetpack` nếu muốn giữ tên public cũ: giá mặc định 40 coins theo FAQ/public command list, nhưng phải cấu hình được. Chống double-spend.

## 9. Inventory, search, customization, fusion

### `/inventory`

- Pagination bằng buttons/select.
- Filter set/rarity/condition/graded/duplicate/name.
- Stable sorting.
- Không leak card private data ngoài intended fields.

### `/find [name]`
- Fuzzy/normalized search trong inventory.

### `/search [code]`
- Tìm card instance code; hiển thị chủ sở hữu chỉ trong phạm vi privacy design phù hợp.

### `/swapcodes [code1] [code2]`
- Chỉ owner được swap.
- Atomic, unique code constraint, temporary value strategy an toàn.

### `/tint`
- Apply tint/customization từ user item hoặc rule economy.
- Không mutate original catalog image.

### `/fuse [3 cards]`
- 3 card instance phải cùng catalog identity, cùng owner, không đang listed/traded/auction/deck locked/grading.
- Atomic consume 3 -> create/upgrade 1 card condition tốt hơn theo documented rules.
- Có audit trail, không thể duplicate qua concurrent requests.

## 10. Economy và item shop

### `/balance`
Hiển thị coins, aura, tokens/items relevant.

### `/daily`
- 24h hoặc calendar-window rule phải được chọn rõ và document.
- Idempotent, streak nếu triển khai.
- Reward có coins/energy configurable.

### `/give`
- Gift coins/card/token khi hợp lệ.
- Không cho bot/self abuse; configurable min/max.
- Transaction atomic.

### `/items`, `/itemshop`, `/buyitem`
- Item catalog data-driven.
- Purchase atomic.
- Inventory cap/rules rõ ràng.

### `/mysterybox`
- Reward table data-driven: coins/cards/tokens/rare jackpot; public command nói có thể có mythical.
- RNG injectable để test deterministic.

### `/blackjack`
- Game coin wager, state machine rõ ràng, timeout/refund policy.
- Validate wager, no negative/overflow, atomic settlement.
- RNG testable.
- Có responsible gameplay caps/config; không liên quan tiền thật/cash-out.

## 11. Voting Top.gg

- `/vote` cung cấp link vote và trạng thái reward window.
- FastAPI webhook `/webhooks/topgg`.
- Secret qua env, validate authorization; reject invalid requests.
- Idempotent event handling.
- Theo public description mới: mỗi 12h mặc định +2 energy, +90 coins, +1 random card; streak reward tăng dần theo config. Không hard-code magic number ngoài settings/balance config.
- Có endpoint/test payload fixtures.
- Nếu Top.gg API unavailable, bot vẫn chạy core game.

## 12. Professional grading

### `/grade [code]`

- Chỉ card raw, owner hợp lệ, không locked/listed.
- 4 sub-grades, half-point scores.
- Final score deterministic/stochastic có seeded RNG service; rules document.
- Unique certificate number không đoán tuần tự dễ va chạm; có uniqueness DB.
- Lanes với thời gian target từ 6 giờ tới 5 ngày.
- Queue congestion làm tăng fee và estimated turnaround theo công thức documented, bounded và testable.
- Charge fee + create grading job trong một transaction.

### Background completion

- Không cần giữ process timer per job. Scheduler định kỳ query `due_at <= now`.
- Completion idempotent.
- Restart app không mất grading job.

### `/checkgrade [code/cert]`

- Pending: hiển thị ETA/status.
- Complete: reveal slab, 4 sub-grades, final grade, cert, population count.
- Slab artwork phải original GumaBot, không sao chép trade dress độc quyền.
- Population count query theo card + grade.

## 13. Showcase và wishlist

### `/showcase [user]`
- Render 9 card nổi bật nhất theo documented ranking (grade/rarity/value), cho phép user pin/override nếu thiết kế hỗ trợ.
- Composite image có timeout/fallback.

### `/wishlist`
- Add/remove/list wanted cards.
- Server MOST WANTED board tổng hợp:
  - card;
  - estimated pull odds từ chính GumaBot rules;
  - số user có duplicate spare;
  - lowest/current market ask;
  - số người wishlist.
- Không expose inventory nhạy cảm ngoài aggregate hoặc consented spare indicator.

## 14. Pack Peek

Sau khi mở pack và có duplicate/spare hợp lệ:

- Có thể tạo Peek window ngắn bằng button.
- Một friend/user khác được claim một spare duplicate theo rules.
- Owner được reward/payment.
- Chỉ một claimant thắng; transaction lock/idempotency bắt buộc.
- Không được lấy unique copy cuối nếu rule yêu cầu chỉ spare.
- Timeout cleanup.
- Test race với >=10 concurrent claims, chỉ 1 thành công.

## 15. Server drops

- Guild activity tạo progress; busy server có cơ hội nhận sealed pack drop vào configured channel.
- `/setchannel [channel]` admin-only để chọn drop/announcement channel.
- First-to-claim button atomic.
- Drop expiry.
- Anti-spam rate limit per guild.
- Không đếm bot/webhook messages để farm activity.
- Khả năng disable feature per guild.

## 16. Trading

### `/trade [user]`

Interactive trade state machine:

1. Invite.
2. Both sides add/remove cards/coins/items.
3. Both lock offer.
4. Any offer mutation unlocks both confirmations.
5. Both confirm.
6. Final atomic settlement with re-validation ownership/balance/locks.
7. Cancel/timeout.

Không bao giờ transfer từng item rời rạc ngoài final transaction. Card đang grading/listed/auction/deck-locked không trade được.

## 17. Marketplace / shop

Hỗ trợ cả UX `/market` và compatibility `/shop`:

- `/shop list [code] [price]` / `/market list`.
- `/shop browse` / `/market browse`.
- `/shop remove [code]`.
- buy flow với confirmation.
- Seller không thể mua listing của mình.
- Listing lock card ownership.
- Atomic buyer debit + seller credit + ownership transfer + listing sold.
- Optional fee/tax configurable.
- `price_history` immutable.
- `/cardtrend [card]`: median/percentile/volume theo time window; xử lý ít dữ liệu.
- `/sell` bulk-to-system nếu giữ command cũ: filter + preview + confirm, documented pricing.

## 18. Auctions

### `/auction`

- Create auction cho card, start bid, optional buyout nếu chọn.
- Bids tăng tối thiểu theo increment rule.
- Không cho seller bid.
- Dùng escrow/hold accounting hoặc revalidation model được document để chống fake bids/double spend.
- `ends_at` UTC; anti-sniping extension configurable nếu bật.
- Background settlement idempotent sau restart.
- Winner transfer + seller payment atomic.
- Cancel chỉ khi chưa có bid hoặc theo rule rõ.
- Concurrency test simultaneous highest bids.

## 19. Duels và decks

### `/deck`
- Manage 5-card deck.
- Không trùng instance; validate ownership/availability.

### `/duel [opponent]`
- Challenge/accept/decline/timeout.
- Turn-based state machine.
- Public description nêu attack, defend, heal và rarity moves: implement bốn nhóm action này với balance data-driven.
- Không giữ toàn bộ logic trong Discord view.
- Server-authoritative RNG.
- Turn timeout, forfeit policy.
- Persist duel/log đủ để recover hoặc conclude an toàn sau restart.
- Rewards capped, anti-win-trading basic controls.

### `/duelprofile`
- wins/losses/rating/streak/most-used card image hoặc metadata.

## 20. Gym, progression, quiz, journey

### `/gym`
- 8 AI Gym Leaders.
- Mỗi leader có deck/archetype/rules data-driven.
- Badge progression và Champion title khi hoàn thành.
- Gym win có thể thưởng energy theo config.
- AI phải deterministic/testable enough; không cần external LLM.

### `/quiz`
- Tối đa 10 câu multiple-choice/session theo public command description.
- Rewards coins + Aura.
- Streak tracking và energy bonus configurable.
- Question bank data-driven; không vi phạm copyright nội dung.

### `/quizstats`
- Accuracy, attempts, correct, best streak, rewards.

### `/namepokemon`
- Guess-name minigame dùng legal/original/provider asset rules; anti-answer leak.

### `/pickcard`
- Chọn 1 trong 3 dropped cards; cooldown mặc định 30 phút theo public command list.
- Atomic claim.

### `/journey`
Không để "In development". Production version cần:
- map/stages data-driven;
- encounters;
- bag items;
- stamina/cooldown rule;
- rewards;
- checkpoints;
- `/bag` view.

## 21. Quests, achievements, levels

### Daily quests
- Generate 3 hoặc configurable count/ngày/user từ templates.
- Progress qua domain events: open pack, holo pull, trade, quiz, gym, market, etc.
- Reward claim idempotent.

### Achievements
- Data-driven definitions, hidden/visible achievements.
- Award idempotent từ events.

### 50 levels
- XP curve documented.
- Exactly 50 reward levels theo public feature description.
- `/level` hiển thị XP progress + next reward.
- Level rewards claim once.

## 22. Leaderboards và seasons

### `/leaderboard`
Interactive tabs:
- coins;
- aura;
- XP/level;
- collection size;
- graded score/top grades;
- duel rating;
- achievements.

### `/serverleaderboard`
- Race giữa guilds dựa trên normalized activity/collection/game metrics để guild lớn không auto-win nếu thiết kế có thể cân bằng.

### `/season`
- Monthly season, timezone UTC.
- Snapshot/rollover idempotent.
- Seasonal leaderboard.
- Rewards.
- Hall of Fame immutable lưu winners lịch sử.
- Job restart-safe; unique `(season_id, category, rank)`.

## 23. Cooldowns và reminders

### `/cooldowns`
- Tổng hợp next available time cho actions có cooldown.

### `/reminder`
- User opt-in/out reminders cho daily/vote/pickcard/energy/grading/auction.
- Persist preference.
- Notification scheduler restart-safe.
- DM failure không crash, backoff và disable after repeated forbidden errors nếu cần.

## 24. Reports/feedback

### `/report`
- Modal bug/feedback.
- Store sanitized report vào DB, có timestamp/guild/user/context.
- Không thu thập secrets.
- Optional webhook to maintainer via env URL, retry safe.

## 25. Web interface

Vì Top.gg public feature flags nêu Web Interface supported, xây dashboard tối thiểu bằng FastAPI:

- `/health/live` — process alive.
- `/health/ready` — DB reachable + migration schema expected.
- `/webhooks/topgg` — vote webhook.
- `/api/public/stats` — non-sensitive aggregate stats.
- Discord OAuth2 login cho collection dashboard nếu `DISCORD_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI` được cấu hình.
- Authenticated pages/API: profile, collection, grades, wishlist, listings, duel/season stats.
- CSRF/state validation cho OAuth flow; secure cookie flags; session secret env-only.
- Không expose bot token hoặc DB path.
- Nếu OAuth vars thiếu, bot vẫn start được và dashboard private routes trả configured-unavailable rõ ràng.

Không cần clone giao diện website nguồn; thiết kế original, functional.

## 26. Installable user app / Discord interaction compatibility

- Slash commands phải có contexts/integration types phù hợp với guild install và user app install ở nơi discord.py/API hỗ trợ.
- Các command cần guild state phải gracefully từ chối khi chạy trong DM/user context.
- Không yêu cầu privileged intents nếu không thực sự cần. Nếu cần message-content để tính guild activity thì ưu tiên `on_message` metadata/activity với intent được document; tốt hơn là dùng interaction/activity signals để giảm quyền.

## 27. Concurrency, idempotency, anti-abuse

Mọi feature có giá trị phải test race condition:

- `/start` double call;
- `/daily` double claim;
- vote duplicate webhook;
- open pack retry;
- milestone duplicate reward;
- Pack Peek concurrent claim;
- server drop concurrent claim;
- marketplace simultaneous buy;
- auction simultaneous bid/settle;
- trade confirm races;
- grading completion duplicate worker;
- season rollover duplicate worker.

Yêu cầu:

- idempotency/correlation keys;
- atomic conditional UPDATE (`... WHERE state='open'`) hoặc equivalent;
- ledger/audit event;
- domain services trả typed result/error, không dựa vào parsing message string.

## 28. Security requirements

- `.env` không commit; `.env.example` chỉ placeholder.
- Validate config startup.
- Secrets không log.
- Structured logs redact auth headers/tokens.
- SQL qua ORM/bound params, không string interpolation.
- Validate Discord IDs, prices, quantities, card codes.
- Bounds để chống integer abuse, huge pagination, huge render.
- Per-user/per-guild command rate limit cho command đắt.
- HTTP timeout, retry bounded, no infinite retry.
- Webhook auth constant-time compare nếu applicable.
- OAuth state nonce + expiry.
- Dependency audit CI.
- `SECURITY.md` threat model: double spend, replay, forged webhook, privilege abuse, data exposure, DoS/render bomb, race condition.

## 29. Logging, metrics, operations

Structured JSON logging production; human-readable dev option.

Log tối thiểu:
- startup/shutdown;
- guild joins/leaves;
- command latency/result category không log private payload;
- DB busy/lock metrics;
- grading/auction/season jobs summary;
- webhook accepted/rejected counts;
- external provider latency/errors.

Có correlation/request id.

Nếu thêm Prometheus endpoint, phải optional và document. Không bắt buộc external observability stack để chạy bot.

## 30. Background jobs

Dùng scheduler đơn-process có DB-backed idempotency. Các job:

- grading completion;
- expired trade cleanup;
- expired market/auction settlement;
- reminders;
- server drop generation/expiry nếu cần;
- daily/weekly featured set rotation;
- season rollover;
- backup trigger nếu configured.

Không dùng `asyncio.create_task` rải rác cho long-lived critical workflows mà không tracking/recovery.

## 31. Configuration

`.env.example` phải có ít nhất:

```env
DISCORD_TOKEN=
DISCORD_APPLICATION_ID=
DATABASE_URL=sqlite+aiosqlite:///./data/gumabot.db
LOG_LEVEL=INFO
ENVIRONMENT=development
TOPGG_BOT_ID=
TOPGG_TOKEN=
TOPGG_WEBHOOK_SECRET=
WEB_HOST=0.0.0.0
WEB_PORT=8080
DISCORD_OAUTH_CLIENT_ID=
DISCORD_OAUTH_CLIENT_SECRET=
DISCORD_OAUTH_REDIRECT_URI=
SESSION_SECRET=
CARD_PROVIDER=fixture
CARD_PROVIDER_API_KEY=
BACKUP_DIR=./backups
```

Game balance numbers nằm trong typed settings/data file, không scatter magic numbers.

## 32. Error UX

- User-facing errors ngắn, actionable, không stack trace.
- Unexpected error có reference id.
- Permission errors rõ.
- Interaction timeout phải defer đúng lúc.
- Long render/provider call defer + followup.
- Discord `NotFound/Forbidden/HTTPException` xử lý có chiến lược.
- Job error không giết scheduler loop.

## 33. Test strategy bắt buộc

Mục tiêu coverage: >=90% statement cho domain/services và >=85% overall; quan trọng hơn là cover invariants/races.

### Unit tests

Bao phủ:
- energy lazy regen boundary: 0s, 2h-1s, 2h, nhiều charge, cap 3;
- rarity weight normalization;
- God Pack rate config path;
- condition/fusion calculation;
- grading half-point and final grade bounds;
- grading queue pricing/ETA bounds;
- XP->level 1..50 boundaries;
- quest progress;
- duel damage/defend/heal/rarity move;
- market stats/cardtrend;
- season date boundaries;
- vote streak calculations.

### Property-based tests (Hypothesis)

Invariants:
- balances không âm;
- energy không âm/không vượt allowed cap;
- card instance có tối đa một owner;
- trade settlement bảo toàn tổng item/coin trừ documented fees;
- market settlement bảo toàn tiền/card;
- auction winner duy nhất;
- grading score luôn trong range và bước 0.5;
- pack luôn 5 cards;
- God Pack tất cả card đạt Holo-or-better;
- fuse consume đúng 3 create/upgrade đúng 1;
- set completion 0..100%.

### Integration tests với SQLite thật

Không dùng mock DB cho transaction-critical tests. Tạo temp SQLite, bật WAL/foreign keys giống production.

Test:
- migrations up từ empty DB;
- foreign key/unique constraints;
- `/start` service idempotency;
- open pack + inventory + ledger;
- daily/vote double claim;
- set milestone once;
- grade submit -> worker -> reveal;
- trade full lifecycle;
- market list/buy/remove;
- auction create/bid/settle;
- duel persist/recover;
- season rollover;
- backup + restore smoke test.

### Concurrency tests

Dùng `asyncio.gather` với nhiều independent sessions/connections:

1. 20 `/daily` claims cùng user => đúng 1 success.
2. 20 buyers mua cùng listing => đúng 1 owner cuối và 1 sale.
3. 20 Pack Peek claims => đúng 1 claimant.
4. 20 server-drop claims => đúng 1 claimant.
5. concurrent trade confirmations => settle đúng 1 lần.
6. concurrent auction bids => highest valid bid deterministic theo transaction order, không mất tiền.
7. 2 workers complete grading job => một certificate.
8. 2 season workers => một Hall of Fame snapshot.

### Discord command tests

- Test command callbacks/services với fake interaction adapter.
- Permission admin `/setchannel`.
- DM/guild context restrictions.
- Pagination/custom IDs không vượt Discord limits.
- defer/followup path cho slow commands.

### Web tests

FastAPI TestClient/AsyncClient:
- health endpoints;
- Top.gg webhook valid/invalid secret;
- duplicate vote event;
- malformed payload;
- OAuth state mismatch/replay;
- unauthorized authenticated routes;
- aggregate stats không leak private data.

### Rendering tests

- deterministic fixed-seed snapshots hoặc image property assertions (dimensions/mode/non-empty), tránh brittle pixel-perfect nếu fonts khác platform.
- missing image fallback.
- render timeout/error không rollback valid game result.

### Simulation tests

- 100k+ simulated pack rolls trong pure domain test, assert observed distribution trong statistical tolerance.
- Simulate economy 30 days để phát hiện inflation/extreme reward bugs; xuất summary trong test/debug tool, không cần gate quá chặt nếu nondeterministic — dùng fixed seed.

## 34. CI/CD GitHub Actions

Tạo `.github/workflows/ci.yml` chạy trên push + PR:

1. setup Python 3.12;
2. install locked dependencies;
3. `ruff check`;
4. formatting check;
5. static type check;
6. `pytest` + coverage threshold;
7. `alembic upgrade head` trên temp DB;
8. `pip-audit`;
9. Docker build smoke test.

Không cần secret để chạy CI unit/integration core. External tests chỉ chạy khi secret tồn tại và phải tách marker.

Có optional workflow backup/release only nếu thực sự hữu ích, không commit deploy secrets.

## 35. Docker/Deployment

- Multi-stage hoặc slim Docker image, non-root user.
- Persistent volumes `/app/data` và `/app/backups`.
- Healthcheck gọi readiness endpoint.
- Graceful SIGTERM: stop accepting new work, close bot/http/db cleanly.
- `docker-compose.yml` cho single-instance deployment.
- Cảnh báo rõ: với SQLite chỉ chạy **một writer app instance**; không horizontal-scale nhiều bot replicas cùng file DB qua network filesystem.

`docs/OPERATIONS.md` phải có:
- first deploy;
- migration;
- backup;
- restore;
- upgrade;
- rollback;
- rotate Discord/Top.gg secrets;
- DB corruption recovery;
- Discord API outage behavior;
- provider outage behavior.

## 36. README bắt buộc

README phải có:
- GumaBot là gì;
- feature list;
- screenshots/placeholder policy chỉ nếu asset repo hợp pháp;
- prerequisites;
- Discord Developer Portal intents/permissions;
- local setup;
- `.env`;
- migration;
- run bot+web;
- Docker;
- tests;
- slash command sync strategy;
- Top.gg webhook setup;
- backup/restore;
- troubleshooting;
- license/IP disclaimer.

Không ghi token thật.

## 37. Command matrix tối thiểu cần có

Coding agent phải implement hoặc cung cấp documented alias tương đương cho toàn bộ matrix sau:

```text
/start
/play
/guide
/help
/avatarchoice
/bag
/balance
/blackjack
/cardtrend
/checkgrade
/cooldowns
/daily
/deck
/duel
/duelprofile
/find
/fuse
/give
/grade
/gym
/inventory
/items
/itemshop
/buyitem
/journey
/leaderboard
/level
/missing
/mysterybox
/namepokemon
/openpack
/packs
/buypack
/resetpack (compatibility alias nếu giữ)
/pickcard
/quiz
/quizstats
/reminder
/report
/search
/sell
/serverleaderboard
/setchannel
/setcompletion
/collection
/showcase
/wishlist
/trade
/market ...
/shop list|browse|remove
/auction ...
/season
/swapcodes
/tint
/upcoming
/vote
```

Ngoài slash commands, phải có interactive Pack Peek và Server Drop claim flows.

## 38. Acceptance criteria theo feature

Một feature chỉ được đánh dấu DONE khi:

- DB migration tồn tại nếu cần persistence;
- domain/service implementation hoàn chỉnh;
- Discord command/view hoàn chỉnh;
- permission/validation/error handling;
- unit tests;
- integration test cho happy path và ít nhất 2 failure paths;
- concurrency test nếu có transfer/reward/claim;
- docs user/operator cập nhật;
- không có TODO/NotImplemented trong production path.

## 39. Definition of Done toàn dự án

Trước khi kết thúc, coding agent phải tự chạy và báo kết quả thực tế của:

```bash
ruff check .
ruff format --check .
# hoặc formatter tương đương đã chọn
mypy src tests
pytest -q --cov=src/gumabot --cov-report=term-missing --cov-fail-under=85
alembic upgrade head
python -m gumabot --check-config
# Docker build
docker build -t gumabot:test .
```

Nếu tool/environment không có Docker, ghi rõ Docker build chưa chạy nhưng CI phải có job build. Không được tuyên bố test pass nếu chưa thực thi.

Ngoài ra:
- grep production source cho `TODO`, `FIXME`, `pass`, `NotImplementedError` và giải quyết các placeholder thực sự;
- đảm bảo `.env`, DB, backup, coverage artifacts không bị commit;
- kiểm tra git diff cuối;
- cập nhật README với exact commands.

## 40. Cách làm việc bắt buộc cho coding agent

Thực hiện theo từng phase nhưng **tiếp tục làm đến khi repository hoàn chỉnh**, không dừng ở kế hoạch:

### Phase A — Foundation
Project config, app lifecycle, config, logging, DB engine, Alembic, core models, Discord bot startup, FastAPI startup, health endpoints, CI.

### Phase B — Core game
Users, start, energy, packs, inventory, search, set progress, economy, daily, vote webhook.

### Phase C — Collection systems
Grading, fusion, tint, showcase, wishlist, Pack Peek, server drops.

### Phase D — Social economy
Trade, market/shop, auctions, cardtrend.

### Phase E — Gameplay/progression
Deck/duel, gym, quiz, namepokemon, pickcard, journey/bag, quests, achievements, 50 levels.

### Phase F — Competitive/ops
Leaderboards, server leaderboard, seasons/Hall of Fame, reminders, reports, dashboard.

### Phase G — Hardening
Concurrency suite, property tests, simulation tests, backup/restore test, security review, docs, CI final.

Sau mỗi phase:
1. chạy test liên quan;
2. sửa lỗi;
3. commit logic coherent nếu môi trường cho phép;
4. không tạo fake passing tests.

## 41. Quy tắc chất lượng code

- Type hints đầy đủ ở public API.
- Small cohesive functions/classes.
- Domain exceptions typed.
- Không global mutable singleton khó test.
- Clock injectable (`Clock` interface) cho time-based tests.
- RNG injectable cho pack/grade/game tests.
- Provider external injectable.
- Repository interfaces chỉ ở nơi thực sự giúp test/architecture; tránh overengineering.
- Comments giải thích “why”, không lặp lại code.
- SQL/index explain cho queries leaderboard/market nặng.
- Pagination mọi query có thể trả nhiều rows.
- Không N+1 rendering inventory/showcase.

## 42. Balance/config defaults phải document

Các giá trị công khai nên có default tương ứng:

- starter coins: 150;
- starter guaranteed Holo: yes;
- pack size: 5;
- energy cap: 3;
- energy regeneration: 1 / 2h;
- God Pack: 1%;
- set milestones: 25/50/75/100%;
- chase reward pack: doubled Holo odds;
- grading lane range: 6h..5d;
- vote interval: 12h;
- vote default reward: +2 energy, +90 coins, +1 card;
- pickcard cooldown: 30m;
- 50 progression levels;
- 8 Gym Leaders.

Các giá trị mâu thuẫn giữa tài liệu cũ/mới (ví dụ vote reward cũ từng ghi 50 coins, Top.gg mới ghi 90 coins) phải ưu tiên mô tả công khai mới nhất và đưa vào config để dễ thay đổi.

## 43. Deliverables cuối cùng

Repository hoàn chỉnh phải chứa tối thiểu:

1. source production;
2. migrations;
3. fixture/seed data hợp pháp;
4. tests đầy đủ;
5. CI workflow;
6. Dockerfile + compose;
7. `.env.example`;
8. README;
9. ARCHITECTURE/DATABASE/GAME_BALANCE/TESTING/OPERATIONS/SECURITY docs;
10. scripts backup/restore/check DB;
11. command sync/bootstrap instructions;
12. test report tóm tắt bằng kết quả chạy thật.

Cuối phiên coding, hãy trả về:
- cây thư mục cuối;
- danh sách feature đã hoàn thành;
- migration head;
- test commands + số test pass/fail/skipped + coverage thật;
- lint/type/audit/docker status;
- các biến môi trường bắt buộc;
- cách chạy local và Docker;
- mọi giới hạn còn lại (nếu có), tuyệt đối không che giấu.

## 44. Nguồn public dùng làm feature specification

- Top.gg overview: https://top.gg/bot/1362516883785515199?campaign=4-0
- Top.gg commands: https://top.gg/bot/1362516883785515199/commands
- Official public website: https://thepokebot.com/
- Official public commands/FAQ: https://thepokebot.com/faq
- Target repository: https://github.com/Blast15/GumaBot

Nếu các nguồn thay đổi sau ngày đối chiếu, không tự động scrape thêm behavior bí mật. Chỉ bổ sung chức năng nếu nó được mô tả công khai và vẫn phù hợp clean-room/IP rules ở trên.

---

# EXECUTION DIRECTIVE

Bắt đầu bằng cách đọc toàn bộ repository hiện tại và `git status`. Sau đó triển khai **thực tế** theo Phase A → G. Không chỉ trả lời bằng kế hoạch hoặc snippets. Tạo/sửa file trực tiếp, chạy migration/test/lint/type-check, sửa cho đến khi pass, và để repository ở trạng thái có thể deploy. Mọi economy mutation phải an toàn trước concurrency và mọi claim/reward phải idempotent.
