# Reliability update — 2026-09-10

This section supersedes historical totals below. The new CI runs on Python 3.12
Linux and Windows, with branch coverage enabled and a hard 85% gate. Results for
this change are recorded in `docs/RELIABILITY.md`; GitHub Actions results are the
authority for Windows execution. No full live Discord E2E, 24–72h soak or remote
backup restore is claimed. See `docs/OPERATIONS.md` for executable procedures.

---

# GumaBot — báo cáo triển khai và kiểm thử

Bản bàn giao có entry point `main.py`; lệnh Windows chính thức là `py main.py`. Source được tổ chức thành modules, không yêu cầu container hay dịch vụ dữ liệu bên ngoài.

## Kết quả đã thực thi

Môi trường: Python 3.12.14 trên Linux. Vì không có Windows Python Launcher trong môi trường này, các lệnh đã thực thi dùng `python`, không giả định đã chạy `py` trên Windows. Dependency cài trong thư mục riêng của workspace và được đưa vào PYTHONPATH khi kiểm thử; đây không phải yêu cầu cài đặt của người sử dụng.

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| Regression với pytest và coverage toàn package `gumabot` | **81 passed, 0 failed, 0 skipped; 1 external test deselected** |
| Coverage statement | **91.74%**, 2227 statements, 184 missed; ngưỡng 85% PASS |
| Live TCGdex smoke | **1 passed** ở bản trước; NOT RUN lại cho thay đổi gỡ tính năng này |
| Ruff check | PASS |
| Ruff format check | PASS |
| Config + startup `python main.py --check` | PASS, 77 command entries gồm 72 leaf slash commands và 5 command groups |
| Chạy `python main.py` khi thiếu token | PASS expected failure: thông báo cấu hình đúng, exit 1, không traceback |
| SQLite integrity_check + foreign_key_check | PASS, schema version 4, 52 tables |
| Empty-database startup | PASS trong integration tests |
| Migration rollback và pre-upgrade backup | PASS trong integration tests |
| Backup, restore có xác nhận và kiểm tra DB | PASS qua subprocess integration tests |
| 100,000 pack simulation, fixed seed | PASS |
| Production placeholder audit | Không tìm thấy TODO, FIXME, NotImplemented, NotImplementedError hoặc Coming Soon trong production source |
| Type checking / mypy | NOT RUN — không cấu hình mypy |
| Discord login/live guild end-to-end | NOT RUN — không có bot token thật |
| Windows execution `py main.py` | NOT RUN — môi trường kiểm thử là Linux |
| 24/7 soak test | NOT RUN |

Pytest có một DeprecationWarning của dependency Discord liên quan `audioop` trên Python 3.12. Warning này không làm test thất bại. Không có báo cáo giả rằng đã kiểm chứng đăng nhập Discord, Windows hoặc hoạt động liên tục 24/7.

## Các nhóm đã có implementation

- Bootstrap/config/logging UTF-8, SQLAlchemy async, SQLite WAL/FK/busy timeout, migrations và lifecycle cleanup.
- TCGdex REST provider, normalized card model, single-flight, TTL, stale fallback, bounded retries, local catalog và image cache có validation.
- Starter, packs/God Pack, energy, inventory/filter/sort, collection, completion milestones, chase meter, fuzzy find, card search.
- Coins/Aura ledger, daily, giving, items, Mystery Box, virtual blackjack.
- Grading queues/certificates, fusion, tint, favorites, code swapping, showcase, wishlist, Pack Peek và server drops.
- Escrow trades, atomic marketplace, bulk-sale confirmation, price history, auctions với fund reservation.
- Decks, authoritative duel state, gym simulations, quizzes, image guessing, pickcard và Journey có bag/health/stages.
- Daily quests, achievements, level rewards 1–50, SQL rankings, seasons/Hall of Fame, reminders và reports.
- Discord buttons, select menu, modal, inventory paging, workflow IDs có thể tiếp tục sau restart.

Danh sách command/arguments lấy từ registry: [COMMANDS.md](COMMANDS.md). Cấu trúc repository và cài đặt: [README.md](../README.md).

## Bằng chứng an toàn tiền và cạnh tranh

Tests sử dụng SQLite thật trong thư mục tạm, không mock database. Có `asyncio.gather` cho 20 lần /start, daily, market purchase, Pack Peek, server drop và pack retries; hai worker grading, auction settlement và season rollover; concurrent trade confirmation. Các test kiểm tra một reward/sale/certificate/settlement, ownership và ledger tương ứng. Có rollback khi thiếu tiền, không thể tiêu tiền đang escrow, hoàn tiền khi outbid/trade expiry, immutable ledger/history và conservation property tests với Hypothesis.

API tests không truy cập mạng: valid responses, 404/429/500/503/timeouts, invalid JSON/schema, thiếu rarity/image, empty set, language fallback, TTL, single-flight và stale/corrupted cache. Live smoke chỉ kiểm tra request và normalization một card `base1-1`; không phải test tải toàn bộ catalog hoặc kiểm thử end-to-end qua Discord.

## Giới hạn cần biết

- Bản này có implementation và kiểm thử tự động cho các nhóm chức năng chính, nhưng chưa thể xác nhận toàn bộ Definition of Done trong môi trường Discord thật. Cần token của chủ bot để kiểm chứng quyền guild, delivery, global sync và tương tác thực.
- Combat là luật GumaBot rút gọn: duel dùng sức mạnh tổng hợp của deck; gym tự mô phỏng trận với AI cố định/testable. Không mô phỏng luật Pokémon TCG vật lý. Ngân hàng quiz hiện có 10 câu GumaBot.
- Upcoming chỉ dùng ngày phát hành đã được cache đáng tin cậy. Không đảm bảo provider có dữ liệu tương lai. First-use sync có thể chậm; bot owner có thể prewarm set.
- Rarity odds được chuẩn hóa trên các tier thực sự có trong set. Không tự tạo artwork hoặc card catalog giả để bổ sung tier còn thiếu.
- Reminder dùng at-most-once delivery attempts; DM bị Discord chặn hoặc tiến trình dừng giữa claim/send có thể làm mất một thông báo, nhưng không mất tiền/card.
- SQLite phù hợp một bot local. Restore yêu cầu dừng bot; không có distributed deployment hoặc tự động supervision của hệ điều hành.

## Nguồn

- https://github.com/Blast15/GumaBot
- https://tcgdex.dev/rest
- https://api.tcgdex.net/v2/en
- https://discordpy.readthedocs.io/en/stable/intents.html
- https://top.gg/bot/1362516883785515199/commands
- https://thepokebot.com/faq

## Thay đổi mới nhất

Theo yêu cầu chủ bot, đã gỡ command vote, reward service, Top.gg listener/config/worker và reminder liên quan. Migration v4 dọn schema cũ, có backup trước nâng cấp; giữ số dư và immutable ledger. Tests mới kiểm tra upgrade v3 → v4, bảo toàn tiền/lịch sử, không còn command trong registry và từ chối reminder đã gỡ.
