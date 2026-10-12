"""Подключение к SQLite, схема базы и начальные данные."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def _default_db_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "finance.db"
    return Path(__file__).resolve().parent.parent / "finance.db"


DEFAULT_DB_PATH = _default_db_path()

DEFAULT_CATEGORIES = (
    ("Зарплата", "income"),
    ("Фриланс", "income"),
    ("Подарки", "income"),
    ("Продукты", "expense"),
    ("Транспорт", "expense"),
    ("Жильё", "expense"),
    ("Развлечения", "expense"),
    ("Здоровье", "expense"),
    ("Прочее", "expense"),
    ("Инвестиции", "invest"),
    ("Брокерский счёт", "invest"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('income', 'expense', 'invest')),
    monthly_limit REAL CHECK (monthly_limit IS NULL OR monthly_limit > 0),
    UNIQUE (name COLLATE NOCASE, kind)
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    amount      REAL    NOT NULL CHECK (amount > 0),
    txn_date    TEXT    NOT NULL,
    note        TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(txn_date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category_id);

CREATE TABLE IF NOT EXISTS assets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    market            TEXT    NOT NULL
                      CHECK (market IN ('moex', 'us', 'manual', 'physical')),
    ticker            TEXT,
    name              TEXT    NOT NULL,
    currency          TEXT    NOT NULL DEFAULT 'RUB',
    category          TEXT    NOT NULL DEFAULT '',
    details           TEXT    NOT NULL DEFAULT '',
    depreciation_rate REAL    CHECK (depreciation_rate IS NULL
                                     OR depreciation_rate >= 0),
    note              TEXT    NOT NULL DEFAULT '',
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Уникальность тикера только для биржевых активов: у имущества тикера нет,
-- и пустой тикер не должен конфликтовать сам с собой.
CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_market_ticker
    ON assets(market, ticker)
    WHERE market IN ('moex', 'us') AND ticker IS NOT NULL;

CREATE TABLE IF NOT EXISTS trades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id   INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL CHECK (kind IN ('buy', 'sell')),
    quantity   REAL    NOT NULL CHECK (quantity > 0),
    price      REAL    NOT NULL CHECK (price >= 0),
    fee        REAL    NOT NULL DEFAULT 0 CHECK (fee >= 0),
    trade_date TEXT    NOT NULL,
    note       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_asset ON trades(asset_id);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);

CREATE TABLE IF NOT EXISTS prices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id   INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    price      REAL    NOT NULL CHECK (price >= 0),
    currency   TEXT    NOT NULL DEFAULT 'RUB',
    source     TEXT    NOT NULL DEFAULT '',
    fetched_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_prices_asset ON prices(asset_id, fetched_at);

CREATE TABLE IF NOT EXISTS payouts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id      INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    kind          TEXT    NOT NULL
                  CHECK (kind IN ('dividend', 'coupon', 'other')),
    pay_date      TEXT    NOT NULL,
    rate          REAL    CHECK (rate IS NULL OR rate >= 0),
    amount        REAL    CHECK (amount IS NULL OR amount >= 0),
    currency      TEXT    NOT NULL DEFAULT 'RUB',
    status        TEXT    NOT NULL DEFAULT 'expected'
                  CHECK (status IN ('expected', 'received')),
    received_date TEXT,
    source        TEXT    NOT NULL DEFAULT '',
    rule_id       INTEGER,
    note          TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_payouts_asset ON payouts(asset_id, pay_date);
CREATE INDEX IF NOT EXISTS idx_payouts_date ON payouts(pay_date);

CREATE TABLE IF NOT EXISTS payout_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id   INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL
               CHECK (kind IN ('dividend', 'coupon', 'other')),
    rate       REAL    NOT NULL CHECK (rate >= 0),
    period     TEXT    NOT NULL
               CHECK (period IN ('once', 'monthly', 'quarterly', 'yearly')),
    anchor     TEXT    NOT NULL,
    currency   TEXT    NOT NULL DEFAULT 'RUB',
    note       TEXT    NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_payout_rules_asset ON payout_rules(asset_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def resolve_db_path(path: str | os.PathLike | None = None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get("PERSONAL_FINANCE_DB")
    if env:
        return Path(env)
    return DEFAULT_DB_PATH


def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    db_path = resolve_db_path(path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    with conn:
        count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO categories (name, kind) VALUES (?, ?)",
                DEFAULT_CATEGORIES,
            )


def _migrate(conn: sqlite3.Connection) -> None:
    """Миграции старых схем БД. Вызывается вне транзакции (autocommit)."""
    cat_cols = {row["name"] for row in conn.execute("PRAGMA table_info(categories)")}
    if "monthly_limit" not in cat_cols:
        conn.execute("ALTER TABLE categories ADD COLUMN monthly_limit REAL")

    txn_cols = {row["name"] for row in conn.execute("PRAGMA table_info(transactions)")}
    if "source" not in txn_cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN source TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_source ON transactions(source)"
    )

    has_budgets = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'budgets'"
    ).fetchone() is not None
    if has_budgets:
        conn.execute(
            "UPDATE categories SET monthly_limit = "
            "(SELECT monthly_limit FROM budgets WHERE budgets.category_id = categories.id)"
        )
        conn.execute("DROP TABLE budgets")

    _upgrade_unique_name_kind(conn)
    _ensure_invest_kind(conn)


def _ensure_invest_kind(conn: sqlite3.Connection) -> None:
    """Старые БД: CHECK(kind) без 'invest'. Пересобираем таблицу категорий."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'categories'"
    ).fetchone()
    if row is None:
        return
    sql = (row["sql"] if isinstance(row, sqlite3.Row) else row[0]) or ""
    if "'invest'" not in sql:
        _rebuild_categories_table(conn)


def _upgrade_unique_name_kind(conn: sqlite3.Connection) -> None:
    """Старые БД: уникальность name глобально. Новая схема: UNIQUE (name, kind)."""
    for idx in conn.execute("PRAGMA index_list(categories)"):
        if not idx["unique"]:
            continue
        cols = {
            row["name"]
            for row in conn.execute(f'PRAGMA index_info("{idx["name"]}")')
        }
        if cols == {"name"}:
            _rebuild_categories_table(conn)
            return


def _rebuild_categories_table(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript(
            """
            BEGIN;
            CREATE TABLE categories_new (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                kind          TEXT NOT NULL CHECK (kind IN ('income', 'expense', 'invest')),
                monthly_limit REAL CHECK (monthly_limit IS NULL OR monthly_limit > 0),
                UNIQUE (name COLLATE NOCASE, kind)
            );
            INSERT INTO categories_new (id, name, kind, monthly_limit)
                SELECT id, name, kind, monthly_limit FROM categories;
            DROP TABLE categories;
            ALTER TABLE categories_new RENAME TO categories;
            COMMIT;
            """
        )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
