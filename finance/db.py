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
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
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
                kind          TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
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
