"""SQL-запросы: CRUD, фильтры, агрегаты."""
from __future__ import annotations

import sqlite3
from datetime import date

from .models import (
    INCOME,
    EXPENSE,
    Category,
    CategoryPlan,
    MonthSummary,
    Transaction,
    month_range,
    previous_months,
    validate_kind,
)

TRANSACTION_SELECT = """
SELECT t.id, t.category_id, t.amount, t.txn_date, t.note,
       c.name AS category_name, c.kind AS kind
FROM transactions t
JOIN categories c ON c.id = t.category_id
"""


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _rows(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    # --- категории ---

    def list_categories(self, kind: str | None = None) -> list[Category]:
        sql = "SELECT id, name, kind, monthly_limit FROM categories"
        params: tuple = ()
        if kind:
            sql += " WHERE kind = ?"
            params = (validate_kind(kind),)
        sql += " ORDER BY kind DESC, name COLLATE NOCASE"
        return [self._read_category(r) for r in self._rows(sql, params)]

    def get_category(self, category_id: int) -> Category | None:
        row = self.conn.execute(
            "SELECT id, name, kind, monthly_limit FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        return self._read_category(row) if row else None

    @staticmethod
    def _read_category(row: sqlite3.Row) -> Category:
        return Category(
            id=row["id"], name=row["name"], kind=row["kind"],
            monthly_limit=row["monthly_limit"],
        )

    def category_exists_name(
        self, name: str, kind: str | None = None, exclude_id: int | None = None,
    ) -> bool:
        sql = "SELECT 1 FROM categories WHERE name = ? COLLATE NOCASE"
        params: list = [name]
        if kind:
            sql += " AND kind = ?"
            params.append(validate_kind(kind))
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return self.conn.execute(sql, tuple(params)).fetchone() is not None

    def category_by_name(
        self, name: str, kind: str | None = None,
    ) -> Category | None:
        sql = "SELECT id, name, kind, monthly_limit FROM categories WHERE name = ? COLLATE NOCASE"
        params: list = [name]
        if kind:
            sql += " AND kind = ?"
            params.append(validate_kind(kind))
        row = self.conn.execute(sql, tuple(params)).fetchone()
        return self._read_category(row) if row else None

    def add_category(self, name: str, kind: str, monthly_limit: float | None = None) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO categories (name, kind, monthly_limit) "
                "VALUES (?, ?, ?)",
                (name, validate_kind(kind), monthly_limit),
            )
        return int(cur.lastrowid)

    def update_category(
        self, category_id: int, name: str, kind: str,
        monthly_limit: float | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE categories SET name = ?, kind = ?, monthly_limit = ? "
                "WHERE id = ?",
                (name, validate_kind(kind), monthly_limit, category_id),
            )

    def set_monthly_limit(self, category_id: int, monthly_limit: float | None) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE categories SET monthly_limit = ? WHERE id = ?",
                (monthly_limit, category_id),
            )

    def delete_category(self, category_id: int, with_transactions: bool = False) -> int:
        count = self.transaction_count(category_id)
        if count and not with_transactions:
            raise ValueError("У категории есть операции")
        with self.conn:
            if count:
                self.conn.execute(
                    "DELETE FROM transactions WHERE category_id = ?", (category_id,)
                )
            self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        return count

    def transaction_count(self, category_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id = ?", (category_id,)
        ).fetchone()
        return int(row[0])

    def category_stats(self, category_id: int) -> tuple[int, float]:
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions WHERE category_id = ?",
            (category_id,),
        ).fetchone()
        return int(row[0]), float(row[1])

    # --- операции ---

    def add_transaction(
        self, category_id: int, amount: float, txn_date: date, note: str = "",
        source: str = "",
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO transactions (category_id, amount, txn_date, note, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (category_id, amount, txn_date.isoformat(), note.strip(), source.strip()),
            )
        return int(cur.lastrowid)

    def list_sources(self) -> list[str]:
        rows = self._rows(
            "SELECT source FROM transactions WHERE source != ''"
        )
        return [row["source"] for row in rows]

    def update_transaction(
        self, transaction_id: int, category_id: int, amount: float,
        txn_date: date, note: str = "",
    ) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE transactions SET category_id = ?, amount = ?, txn_date = ?, note = ? "
                "WHERE id = ?",
                (category_id, amount, txn_date.isoformat(), note.strip(), transaction_id),
            )

    def delete_transaction(self, transaction_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))

    def get_transaction(self, transaction_id: int) -> Transaction | None:
        row = self.conn.execute(
            TRANSACTION_SELECT + " WHERE t.id = ?", (transaction_id,)
        ).fetchone()
        return self._to_transaction(row) if row else None

    @staticmethod
    def _to_transaction(row: sqlite3.Row) -> Transaction:
        return Transaction(
            id=row["id"],
            category_id=row["category_id"],
            amount=float(row["amount"]),
            txn_date=date.fromisoformat(row["txn_date"]),
            note=row["note"],
            category_name=row["category_name"],
            kind=row["kind"],
        )

    def list_transactions(
        self,
        kind: str | None = None,
        category_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        text: str | None = None,
    ) -> list[Transaction]:
        sql = TRANSACTION_SELECT
        clauses: list[str] = []
        params: list = []
        if kind:
            clauses.append("c.kind = ?")
            params.append(validate_kind(kind))
        if category_id is not None:
            clauses.append("t.category_id = ?")
            params.append(category_id)
        if date_from:
            clauses.append("t.txn_date >= ?")
            params.append(date_from.isoformat())
        if date_to:
            clauses.append("t.txn_date <= ?")
            params.append(date_to.isoformat())
        if text and text.strip():
            clauses.append("(t.note LIKE ? OR c.name LIKE ?)")
            pattern = f"%{text.strip()}%"
            params.extend([pattern, pattern])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY t.txn_date DESC, t.id DESC"
        return [self._to_transaction(r) for r in self._rows(sql, tuple(params))]

    # --- планы ---

    def category_plans(self, year: int, month: int) -> list[CategoryPlan]:
        start, end = month_range(year, month)
        rows = self._rows(
            "SELECT c.id, c.name, c.kind, c.monthly_limit, "
            "COALESCE((SELECT SUM(t.amount) FROM transactions t "
            "          WHERE t.category_id = c.id "
            "          AND t.txn_date BETWEEN ? AND ?), 0) AS spent "
            "FROM categories c "
            "ORDER BY c.kind DESC, c.name COLLATE NOCASE",
            (start.isoformat(), end.isoformat()),
        )
        avgs = self._avg3_by_category(year, month)
        return [
            CategoryPlan(
                self._read_category(r), float(r["spent"]),
                avgs.get(r["id"]),
            )
            for r in rows
        ]

    def _avg3_by_category(
        self, year: int, month: int,
    ) -> dict[int, float | None]:
        """Среднее за 3 месяца до текущего; месяцы без операций = 0."""
        window = previous_months(year, month, 4)[:-1]
        first = date(window[0][0], window[0][1], 1)
        _, last = month_range(window[-1][0], window[-1][1])
        rows = self._rows(
            "SELECT t.category_id, SUBSTR(t.txn_date, 1, 7) AS ym, "
            "SUM(t.amount) AS msum "
            "FROM transactions t "
            "WHERE t.txn_date BETWEEN ? AND ? "
            "GROUP BY t.category_id, ym",
            (first.isoformat(), last.isoformat()),
        )
        per_category: dict[int, dict[str, float]] = {}
        for row in rows:
            per_category.setdefault(row["category_id"], {})[row["ym"]] = float(row["msum"])
        size = len(window)
        return {
            category_id: sum(totals.values()) / size
            for category_id, totals in per_category.items()
        }

    # --- агрегаты ---

    def _kind_sum(self, kind: str, date_from: date, date_to: date) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(t.amount), 0) FROM transactions t "
            "JOIN categories c ON c.id = t.category_id "
            "WHERE c.kind = ? AND t.txn_date BETWEEN ? AND ?",
            (kind, date_from.isoformat(), date_to.isoformat()),
        ).fetchone()
        return float(row[0])

    def period_totals(self, date_from: date, date_to: date) -> tuple[float, float]:
        return (
            self._kind_sum(INCOME, date_from, date_to),
            self._kind_sum(EXPENSE, date_from, date_to),
        )

    def category_totals(
        self, date_from: date, date_to: date
    ) -> list[tuple[str, str, float]]:
        rows = self._rows(
            "SELECT c.name, c.kind, COALESCE(SUM(t.amount), 0) AS total "
            "FROM transactions t JOIN categories c ON c.id = t.category_id "
            "WHERE t.txn_date BETWEEN ? AND ? "
            "GROUP BY c.id ORDER BY total DESC",
            (date_from.isoformat(), date_to.isoformat()),
        )
        return [(r["name"], r["kind"], float(r["total"])) for r in rows]

    def monthly_totals(self, year: int, month: int) -> MonthSummary:
        start, end = month_range(year, month)
        income, expense = self.period_totals(start, end)
        return MonthSummary(year, month, income, expense)

    def monthly_series(self, year: int, month: int, count: int = 12) -> list[MonthSummary]:
        months = previous_months(year, month, count)
        wanted = {f"{y:04d}-{m:02d}" for y, m in months}
        income_map: dict[str, float] = {}
        expense_map: dict[str, float] = {}
        for kind, target in ((INCOME, income_map), (EXPENSE, expense_map)):
            rows = self._rows(
                "SELECT substr(t.txn_date, 1, 7) AS period, COALESCE(SUM(t.amount), 0) "
                "FROM transactions t JOIN categories c ON c.id = t.category_id "
                "WHERE c.kind = ? GROUP BY period",
                (kind,),
            )
            for row in rows:
                if row["period"] in wanted:
                    target[row["period"]] = float(row[1])
        return [
            MonthSummary(y, m, income_map.get(f"{y:04d}-{m:02d}", 0.0),
                         expense_map.get(f"{y:04d}-{m:02d}", 0.0))
            for y, m in months
        ]

    def counts_by_category(self) -> dict[int, int]:
        rows = self._rows(
            "SELECT category_id, COUNT(*) AS cnt FROM transactions GROUP BY category_id"
        )
        return {r["category_id"]: int(r["cnt"]) for r in rows}
