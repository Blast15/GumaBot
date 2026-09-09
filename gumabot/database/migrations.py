"""Sequential, transactional SQLite migrations; never execute DDL in game services."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS = [
    [
        "CREATE TABLE users (discord_user_id INTEGER PRIMARY KEY CHECK(discord_user_id>0), created_at INTEGER NOT NULL, coins INTEGER NOT NULL DEFAULT 0 CHECK(coins>=0), aura INTEGER NOT NULL DEFAULT 0 CHECK(aura>=0), xp INTEGER NOT NULL DEFAULT 0 CHECK(xp>=0), level INTEGER NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 50), energy INTEGER NOT NULL DEFAULT 3 CHECK(energy>=0), energy_updated_at INTEGER NOT NULL, vote_streak INTEGER NOT NULL DEFAULT 0, last_vote_at INTEGER, trainer_avatar TEXT NOT NULL DEFAULT 'Scout', tutorial_progress INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE guilds (id INTEGER PRIMARY KEY, drop_channel INTEGER, drop_enabled INTEGER NOT NULL DEFAULT 0, last_drop_at INTEGER NOT NULL DEFAULT 0, activity INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE guild_members (guild_id INTEGER REFERENCES guilds(id), user_id INTEGER REFERENCES users(discord_user_id), PRIMARY KEY(guild_id,user_id))",
        "CREATE TABLE card_sets (id TEXT PRIMARY KEY, name TEXT NOT NULL, total INTEGER NOT NULL DEFAULT 0, release_date TEXT, synced_at INTEGER NOT NULL)",
        "CREATE TABLE card_catalog (id TEXT PRIMARY KEY, name TEXT NOT NULL, search_name TEXT NOT NULL, set_id TEXT NOT NULL REFERENCES card_sets(id), rarity INTEGER NOT NULL, metadata TEXT NOT NULL)",
        "CREATE TABLE provider_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at INTEGER NOT NULL)",
        "CREATE TABLE owned_cards (id INTEGER PRIMARY KEY, public_code TEXT UNIQUE NOT NULL, owner_id INTEGER NOT NULL REFERENCES users(discord_user_id), catalog_card_id TEXT NOT NULL REFERENCES card_catalog(id), condition_score INTEGER NOT NULL CHECK(condition_score BETWEEN 0 AND 100), condition_name TEXT NOT NULL, tint TEXT, grade_status TEXT NOT NULL DEFAULT 'raw', grade REAL CHECK(grade BETWEEN 1 AND 10), created_at INTEGER NOT NULL, acquisition_source TEXT NOT NULL, locked_reason TEXT, favorite INTEGER NOT NULL DEFAULT 0)",
        "CREATE INDEX owned_owner ON owned_cards(owner_id,catalog_card_id)",
        "CREATE TABLE pack_openings (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(discord_user_id), set_id TEXT NOT NULL REFERENCES card_sets(id), god INTEGER NOT NULL, created_at INTEGER NOT NULL)",
        "CREATE TABLE pack_pulls (opening_id TEXT REFERENCES pack_openings(id), slot INTEGER CHECK(slot BETWEEN 0 AND 4), public_code TEXT NOT NULL, catalog_card_id TEXT NOT NULL REFERENCES card_catalog(id), PRIMARY KEY(opening_id,slot))",
        "CREATE TABLE currency_ledger (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(discord_user_id), currency TEXT NOT NULL CHECK(currency IN ('coins','aura')), amount_delta INTEGER NOT NULL, reason TEXT NOT NULL, correlation_id TEXT NOT NULL, reference_type TEXT, reference_id TEXT, created_at INTEGER NOT NULL)",
        "CREATE TRIGGER ledger_no_update BEFORE UPDATE ON currency_ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END",
        "CREATE TRIGGER ledger_no_delete BEFORE DELETE ON currency_ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END",
        "CREATE TABLE energy_events (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(discord_user_id), delta INTEGER NOT NULL, reason TEXT NOT NULL, created_at INTEGER NOT NULL)",
        "CREATE TABLE cooldowns (user_id INTEGER REFERENCES users(discord_user_id), kind TEXT, due_at INTEGER NOT NULL, PRIMARY KEY(user_id,kind))",
        "CREATE TABLE grading_jobs (id TEXT PRIMARY KEY, card_id INTEGER UNIQUE NOT NULL REFERENCES owned_cards(id), user_id INTEGER REFERENCES users(discord_user_id), lane TEXT NOT NULL, due_at INTEGER NOT NULL, completed_at INTEGER)",
        "CREATE TABLE grade_certificates (id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL REFERENCES grading_jobs(id), card_id INTEGER UNIQUE NOT NULL REFERENCES owned_cards(id), centering REAL NOT NULL, corners REAL NOT NULL, edges REAL NOT NULL, surface REAL NOT NULL, final_grade REAL NOT NULL, created_at INTEGER NOT NULL)",
        "CREATE TABLE wishlists (user_id INTEGER REFERENCES users(discord_user_id), card_id TEXT REFERENCES card_catalog(id), PRIMARY KEY(user_id,card_id))",
        "CREATE TABLE pack_peek_offers (id TEXT PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES owned_cards(id), owner_id INTEGER NOT NULL REFERENCES users(discord_user_id), due_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active')",
        "CREATE TABLE pack_peek_claims (offer_id TEXT PRIMARY KEY REFERENCES pack_peek_offers(id), user_id INTEGER REFERENCES users(discord_user_id), created_at INTEGER NOT NULL)",
        "CREATE TABLE server_drops (id TEXT PRIMARY KEY, guild_id INTEGER NOT NULL REFERENCES guilds(id), card_id TEXT NOT NULL REFERENCES card_catalog(id), due_at INTEGER NOT NULL, claimant INTEGER REFERENCES users(discord_user_id), created_at INTEGER NOT NULL)",
        "CREATE TABLE trades (id TEXT PRIMARY KEY, proposer INTEGER REFERENCES users(discord_user_id), recipient INTEGER REFERENCES users(discord_user_id), status TEXT NOT NULL, proposer_confirmed INTEGER NOT NULL DEFAULT 0, recipient_confirmed INTEGER NOT NULL DEFAULT 0, due_at INTEGER NOT NULL)",
        "CREATE TABLE trade_items (trade_id TEXT REFERENCES trades(id), user_id INTEGER REFERENCES users(discord_user_id), kind TEXT NOT NULL, reference TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), PRIMARY KEY(trade_id,user_id,kind,reference))",
        "CREATE TABLE market_listings (id TEXT PRIMARY KEY, seller INTEGER REFERENCES users(discord_user_id), card_id INTEGER NOT NULL REFERENCES owned_cards(id), price INTEGER NOT NULL CHECK(price>0), status TEXT NOT NULL DEFAULT 'active', created_at INTEGER NOT NULL)",
        "CREATE TABLE market_sales (listing_id TEXT PRIMARY KEY REFERENCES market_listings(id), buyer INTEGER REFERENCES users(discord_user_id), seller INTEGER REFERENCES users(discord_user_id), price INTEGER NOT NULL, created_at INTEGER NOT NULL)",
        "CREATE TABLE price_history (id INTEGER PRIMARY KEY, catalog_card_id TEXT REFERENCES card_catalog(id), price INTEGER NOT NULL, source TEXT NOT NULL, reference TEXT UNIQUE NOT NULL, created_at INTEGER NOT NULL)",
        "CREATE TRIGGER history_no_update BEFORE UPDATE ON price_history BEGIN SELECT RAISE(ABORT,'immutable history'); END",
        "CREATE TRIGGER history_no_delete BEFORE DELETE ON price_history BEGIN SELECT RAISE(ABORT,'immutable history'); END",
        "CREATE TABLE auctions (id TEXT PRIMARY KEY, seller INTEGER REFERENCES users(discord_user_id), card_id INTEGER NOT NULL REFERENCES owned_cards(id), start_price INTEGER NOT NULL CHECK(start_price>0), increment INTEGER NOT NULL CHECK(increment>0), current_bid INTEGER NOT NULL DEFAULT 0, bidder INTEGER REFERENCES users(discord_user_id), buyout INTEGER, due_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active')",
        "CREATE TABLE auction_bids (id INTEGER PRIMARY KEY, auction_id TEXT REFERENCES auctions(id), user_id INTEGER REFERENCES users(discord_user_id), amount INTEGER NOT NULL, created_at INTEGER NOT NULL)",
        "CREATE TABLE auction_holds (auction_id TEXT PRIMARY KEY REFERENCES auctions(id), user_id INTEGER REFERENCES users(discord_user_id), amount INTEGER NOT NULL CHECK(amount>0))",
        "CREATE TABLE decks (user_id INTEGER PRIMARY KEY REFERENCES users(discord_user_id), name TEXT NOT NULL DEFAULT 'Main')",
        "CREATE TABLE deck_cards (user_id INTEGER REFERENCES decks(user_id), slot INTEGER CHECK(slot BETWEEN 0 AND 4), card_id INTEGER NOT NULL REFERENCES owned_cards(id) ON DELETE CASCADE, PRIMARY KEY(user_id,slot), UNIQUE(user_id,card_id))",
        "CREATE TABLE duels (id TEXT PRIMARY KEY, challenger INTEGER REFERENCES users(discord_user_id), opponent INTEGER REFERENCES users(discord_user_id), status TEXT NOT NULL, state TEXT NOT NULL, due_at INTEGER NOT NULL, winner INTEGER REFERENCES users(discord_user_id))",
        "CREATE TABLE duel_turns (duel_id TEXT REFERENCES duels(id), turn INTEGER, user_id INTEGER REFERENCES users(discord_user_id), action TEXT NOT NULL, PRIMARY KEY(duel_id,turn))",
        "CREATE TABLE duel_profiles (user_id INTEGER PRIMARY KEY REFERENCES users(discord_user_id), wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, rating INTEGER NOT NULL DEFAULT 1000, streak INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE gym_progress (user_id INTEGER REFERENCES users(discord_user_id), gym INTEGER, wins INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,gym))",
        "CREATE TABLE badges (user_id INTEGER REFERENCES users(discord_user_id), gym INTEGER, name TEXT NOT NULL, PRIMARY KEY(user_id,gym))",
        "CREATE TABLE quiz_attempts (id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(discord_user_id), kind TEXT NOT NULL, state TEXT NOT NULL, due_at INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE quiz_stats (user_id INTEGER PRIMARY KEY REFERENCES users(discord_user_id), attempts INTEGER NOT NULL DEFAULT 0, correct INTEGER NOT NULL DEFAULT 0, streak INTEGER NOT NULL DEFAULT 0, best_streak INTEGER NOT NULL DEFAULT 0, rewards INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE journey_progress (user_id INTEGER PRIMARY KEY REFERENCES users(discord_user_id), stage INTEGER NOT NULL DEFAULT 1, hp INTEGER NOT NULL DEFAULT 100, encounters INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE journey_inventory (user_id INTEGER REFERENCES users(discord_user_id), item TEXT, quantity INTEGER NOT NULL CHECK(quantity>=0), PRIMARY KEY(user_id,item))",
        "CREATE TABLE quests (id TEXT PRIMARY KEY, event TEXT NOT NULL, target INTEGER NOT NULL, reward INTEGER NOT NULL)",
        "CREATE TABLE user_quests (user_id INTEGER REFERENCES users(discord_user_id), day TEXT, quest_id TEXT REFERENCES quests(id), progress INTEGER NOT NULL DEFAULT 0, claimed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,day,quest_id))",
        "CREATE TABLE achievements (id TEXT PRIMARY KEY, event TEXT NOT NULL, target INTEGER NOT NULL, reward INTEGER NOT NULL)",
        "CREATE TABLE user_achievements (user_id INTEGER REFERENCES users(discord_user_id), achievement_id TEXT REFERENCES achievements(id), progress INTEGER NOT NULL DEFAULT 0, awarded INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,achievement_id))",
        "CREATE TABLE level_rewards (level INTEGER PRIMARY KEY CHECK(level BETWEEN 1 AND 50), xp_required INTEGER UNIQUE NOT NULL, coins INTEGER NOT NULL, aura INTEGER NOT NULL)",
        "CREATE TABLE seasons (id TEXT PRIMARY KEY, ends_at INTEGER NOT NULL, settled INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE season_stats (season_id TEXT REFERENCES seasons(id), user_id INTEGER REFERENCES users(discord_user_id), points INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(season_id,user_id))",
        "CREATE TABLE hall_of_fame (season_id TEXT REFERENCES seasons(id), rank INTEGER, user_id INTEGER REFERENCES users(discord_user_id), points INTEGER NOT NULL, PRIMARY KEY(season_id,rank))",
        "CREATE TABLE shop_items (id TEXT PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>0))",
        "CREATE TABLE user_items (user_id INTEGER REFERENCES users(discord_user_id), item_id TEXT REFERENCES shop_items(id), quantity INTEGER NOT NULL CHECK(quantity>=0), PRIMARY KEY(user_id,item_id))",
        "CREATE TABLE vote_events (id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(discord_user_id), created_at INTEGER NOT NULL)",
        "CREATE TABLE reminder_preferences (user_id INTEGER REFERENCES users(discord_user_id), kind TEXT, enabled INTEGER NOT NULL, last_sent INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,kind))",
        "CREATE TABLE reports (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, body TEXT NOT NULL, created_at INTEGER NOT NULL)",
        "CREATE TABLE set_milestones (user_id INTEGER REFERENCES users(discord_user_id), set_id TEXT REFERENCES card_sets(id), milestone INTEGER, PRIMARY KEY(user_id,set_id,milestone))",
        "CREATE TABLE chase_meters (user_id INTEGER REFERENCES users(discord_user_id), set_id TEXT REFERENCES card_sets(id), progress INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,set_id))",
        "CREATE TABLE action_receipts (id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(discord_user_id), kind TEXT NOT NULL, payload TEXT NOT NULL)",
        "CREATE INDEX grading_due ON grading_jobs(completed_at,due_at)",
        "CREATE INDEX auction_due ON auctions(status,due_at)",
        "CREATE INDEX history_card_time ON price_history(catalog_card_id,created_at)",
    ],
    [
        *[
            f"INSERT INTO level_rewards VALUES ({i},{100 * (i - 1) ** 2},{20 * i if i > 1 else 0},{i // 5 if i > 1 else 0})"
            for i in range(1, 51)
        ],
        *[
            f"INSERT INTO shop_items VALUES ('{key}','{name}',{price})"
            for key, name, price in [
                ("tint", "Tint token", 30),
                ("coupon", "Grading coupon", 80),
                ("booster", "Energy booster", 40),
                ("box", "Mystery box", 60),
                ("cosmetic", "Avatar badge", 100),
            ]
        ],
        *[
            f"INSERT INTO quests VALUES ('{event}','{event}',{target},30)"
            for event, target in [
                ("pack", 3),
                ("holo", 1),
                ("quiz", 1),
                ("duel", 1),
                ("gym", 1),
                ("trade", 1),
                ("market", 1),
                ("grade", 1),
            ]
        ],
        *[
            f"INSERT INTO achievements VALUES ('{event}_10','{event}',10,100)"
            for event in [
                "pack",
                "holo",
                "quiz",
                "duel",
                "gym",
                "trade",
                "market",
                "grade",
                "collection",
                "level",
            ]
        ],
    ],
]


MIGRATIONS.append(
    [
        "CREATE TABLE vote_inbox (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, received_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending')",
        "CREATE INDEX vote_inbox_pending ON vote_inbox(status,received_at)",
    ]
)


# Keep published migrations intact; remove the retired feature on both upgrades and fresh installs.
MIGRATIONS.append(
    [
        "DELETE FROM cooldowns WHERE kind='vote'",
        "DELETE FROM reminder_preferences WHERE kind='vote'",
        "DROP TABLE vote_inbox",
        "DROP TABLE vote_events",
        "ALTER TABLE users DROP COLUMN vote_streak",
        "ALTER TABLE users DROP COLUMN last_vote_at",
    ]
)


def backup(path: Path, destination: Path | None = None) -> Path:
    if not path.exists():
        raise ValueError("Database does not exist")
    folder = path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    destination = (
        destination or folder / f"gumabot-{datetime.now(timezone.utc):%Y%m%d-%H%M%S-%f}.db"
    )
    with sqlite3.connect(path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return destination


def check(path: Path):
    with sqlite3.connect(path) as conn:
        if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Database integrity check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Database foreign key check failed")
        return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    conn = sqlite3.connect(path, timeout=5, isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise ValueError("Database is newer than this application")
        if existed and version < len(MIGRATIONS):
            backup(path)
        conn.execute("BEGIN IMMEDIATE")
        # Re-read after obtaining the lock: another startup may have migrated it.
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for index in range(version, len(MIGRATIONS)):
            for statement in MIGRATIONS[index]:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version={index + 1}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    check(path)
