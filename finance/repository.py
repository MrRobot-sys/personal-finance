"""SQL-запросы: CRUD, фильтры, агрегаты."""
from __future__ import annotations

import sqlite3
from datetime import date

from .models import (
    INCOME,
    EXPENSE,
    INVEST,
    BUY,
    MARKET_PHYSICAL,
    Asset,
    Category,
    CategoryPlan,
    MonthSummary,
    Payout,
    PayoutRule,
    PricePoint,
    Trade,
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

    def invested_total(self) -> float:
        """Сумма всех инвестиционных операций (внесено в пул)."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(t.amount), 0) FROM transactions t "
            "JOIN categories c ON c.id = t.category_id WHERE c.kind = ?",
            (INVEST,),
        ).fetchone()
        return float(row[0])

    def category_totals(
        self, date_from: date, date_to: date
    ) -> list[tuple[str, str, float]]:
        rows = self._rows(
            "SELECT c.name, c.kind, COALESCE(SUM(t.amount), 0) AS total "
            "FROM transactions t JOIN categories c ON c.id = t.category_id "
            "WHERE t.txn_date BETWEEN ? AND ? AND c.kind IN ('income', 'expense') "
            "GROUP BY c.id ORDER BY total DESC",
            (date_from.isoformat(), date_to.isoformat()),
        )
        return [(r["name"], r["kind"], float(r["total"])) for r in rows]

    def monthly_totals(self, year: int, month: int) -> MonthSummary:
        start, end = month_range(year, month)
        income, expense = self.period_totals(start, end)
        invested = self._kind_sum(INVEST, start, end)
        return MonthSummary(year, month, income, expense, invested)

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

    # --- активы, сделки и оценки ---

    _ASSET_COLUMNS = (
        "id, market, ticker, name, currency, category, details, "
        "depreciation_rate, note"
    )

    def list_assets(self, scope: str | None = None) -> list[Asset]:
        sql = f"SELECT {self._ASSET_COLUMNS} FROM assets"
        if scope == "property":
            sql += " WHERE market = ?"
            params: tuple = (MARKET_PHYSICAL,)
        elif scope == "securities":
            sql += " WHERE market != ?"
            params = (MARKET_PHYSICAL,)
        else:
            params = ()
        sql += " ORDER BY market, name COLLATE NOCASE"
        positions = self._positions()
        prices = self._last_prices()
        return [
            self._read_asset(r, positions.get(r["id"]), prices.get(r["id"]))
            for r in self._rows(sql, params)
        ]

    def get_asset(self, asset_id: int) -> Asset | None:
        row = self.conn.execute(
            f"SELECT {self._ASSET_COLUMNS} FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        if row is None:
            return None
        positions = self._positions(asset_id)
        prices = self._last_prices(asset_id)
        return self._read_asset(row, positions.get(asset_id), prices.get(asset_id))

    @staticmethod
    def _read_asset(
        row: sqlite3.Row,
        position: dict | None = None,
        price: sqlite3.Row | None = None,
    ) -> Asset:
        position = position or {}
        return Asset(
            id=row["id"],
            name=row["name"],
            market=row["market"],
            ticker=row["ticker"] or "",
            currency=row["currency"],
            category=row["category"],
            details=row["details"],
            depreciation_rate=row["depreciation_rate"],
            note=row["note"],
            quantity=position.get("quantity", 0.0),
            avg_price=position.get("avg_price", 0.0),
            invested=position.get("invested", 0.0),
            proceeds=position.get("proceeds", 0.0),
            realized=position.get("realized", 0.0),
            first_buy=position.get("first_buy"),
            last_price=float(price["price"]) if price is not None else None,
            last_price_at=price["fetched_at"] if price is not None else "",
            price_source=price["source"] if price is not None else "",
        )

    def _positions(self, asset_id: int | None = None) -> dict[int, dict]:
        """Считает количество, среднюю цену, вложения и реализованный итог
        по сделкам (средняя стоимость покупки, продажи её не меняют)."""
        sql = (
            "SELECT asset_id, kind, quantity, price, fee, trade_date "
            "FROM trades"
        )
        params: tuple = ()
        if asset_id is not None:
            sql += " WHERE asset_id = ?"
            params = (asset_id,)
        sql += " ORDER BY trade_date, id"
        raw: dict[int, dict] = {}
        for r in self._rows(sql, params):
            acc = raw.setdefault(r["asset_id"], {
                "buy_qty": 0.0, "buy_cost": 0.0,
                "sell_qty": 0.0, "sell_proceeds": 0.0,
                "first_buy": None,
            })
            qty = float(r["quantity"])
            price = float(r["price"])
            fee = float(r["fee"])
            if r["kind"] == BUY:
                acc["buy_qty"] += qty
                acc["buy_cost"] += qty * price + fee
                day = date.fromisoformat(r["trade_date"])
                if acc["first_buy"] is None or day < acc["first_buy"]:
                    acc["first_buy"] = day
            else:
                acc["sell_qty"] += qty
                acc["sell_proceeds"] += qty * price - fee
        result: dict[int, dict] = {}
        for aid, acc in raw.items():
            avg = acc["buy_cost"] / acc["buy_qty"] if acc["buy_qty"] else 0.0
            result[aid] = {
                "quantity": acc["buy_qty"] - acc["sell_qty"],
                "avg_price": avg,
                "invested": acc["buy_cost"],
                "proceeds": acc["sell_proceeds"],
                "realized": acc["sell_proceeds"] - acc["sell_qty"] * avg,
                "first_buy": acc["first_buy"],
            }
        return result

    def _last_prices(self, asset_id: int | None = None) -> dict[int, sqlite3.Row]:
        sql = (
            "SELECT asset_id, price, currency, source, fetched_at FROM prices"
        )
        params: tuple = ()
        if asset_id is not None:
            sql += " WHERE asset_id = ?"
            params = (asset_id,)
        sql += " ORDER BY fetched_at, id"
        latest: dict[int, sqlite3.Row] = {}
        for r in self._rows(sql, params):
            latest[r["asset_id"]] = r
        return latest

    def asset_by_ticker(self, ticker: str, market: str) -> Asset | None:
        row = self.conn.execute(
            f"SELECT {self._ASSET_COLUMNS} FROM assets "
            "WHERE ticker = ? COLLATE NOCASE AND market = ?",
            (ticker, market),
        ).fetchone()
        return self._read_asset(row) if row else None

    def add_asset(
        self, name: str, market: str, ticker: str = "", currency: str = "RUB",
        category: str = "", details: str = "", depreciation_rate: float | None = None,
        note: str = "",
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO assets (market, ticker, name, currency, category, "
                "details, depreciation_rate, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    market, ticker or None, name, currency, category,
                    details, depreciation_rate, note,
                ),
            )
        return int(cur.lastrowid)

    def update_asset(
        self, asset_id: int, name: str, market: str, ticker: str = "",
        currency: str = "RUB", category: str = "", details: str = "",
        depreciation_rate: float | None = None, note: str = "",
    ) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE assets SET market = ?, ticker = ?, name = ?, currency = ?, "
                "category = ?, details = ?, depreciation_rate = ?, note = ? "
                "WHERE id = ?",
                (
                    market, ticker or None, name, currency, category,
                    details, depreciation_rate, note, asset_id,
                ),
            )

    def delete_asset(self, asset_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))

    def add_trade(
        self, asset_id: int, kind: str, quantity: float, price: float,
        trade_date: date, fee: float = 0.0, note: str = "",
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO trades (asset_id, kind, quantity, price, fee, "
                "trade_date, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    asset_id, kind, quantity, price, fee,
                    trade_date.isoformat(), note.strip(),
                ),
            )
        return int(cur.lastrowid)

    def list_trades(self, asset_id: int) -> list[Trade]:
        rows = self._rows(
            "SELECT id, asset_id, kind, quantity, price, fee, trade_date, note "
            "FROM trades WHERE asset_id = ? ORDER BY trade_date DESC, id DESC",
            (asset_id,),
        )
        return [
            Trade(
                id=r["id"], asset_id=r["asset_id"], kind=r["kind"],
                quantity=float(r["quantity"]), price=float(r["price"]),
                fee=float(r["fee"]), trade_date=date.fromisoformat(r["trade_date"]),
                note=r["note"],
            )
            for r in rows
        ]

    def delete_trade(self, trade_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))

    def add_price(
        self, asset_id: int, price: float, currency: str, source: str,
        fetched_at: str | None = None,
    ) -> int:
        with self.conn:
            if fetched_at:
                cur = self.conn.execute(
                    "INSERT INTO prices (asset_id, price, currency, source, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (asset_id, price, currency, source.strip(), fetched_at),
                )
            else:
                cur = self.conn.execute(
                    "INSERT INTO prices (asset_id, price, currency, source) "
                    "VALUES (?, ?, ?, ?)",
                    (asset_id, price, currency, source.strip()),
                )
        return int(cur.lastrowid)

    def list_prices(self) -> list[PricePoint]:
        rows = self._rows(
            "SELECT asset_id, price, currency, source, fetched_at "
            "FROM prices ORDER BY fetched_at, id"
        )
        return [
            PricePoint(
                asset_id=r["asset_id"], price=float(r["price"]),
                currency=r["currency"], source=r["source"],
                fetched_at=r["fetched_at"],
            )
            for r in rows
        ]

    # --- выплаты ---

    _PAYOUT_SELECT = """
    SELECT p.id, p.asset_id, p.kind, p.pay_date, p.rate, p.amount, p.currency,
           p.status, p.received_date, p.source, p.rule_id, p.note,
           a.name AS asset_name
    FROM payouts p JOIN assets a ON a.id = p.asset_id
    """

    @staticmethod
    def _read_payout(row: sqlite3.Row) -> Payout:
        return Payout(
            id=row["id"],
            asset_id=row["asset_id"],
            kind=row["kind"],
            pay_date=date.fromisoformat(row["pay_date"]),
            rate=float(row["rate"]) if row["rate"] is not None else None,
            amount=float(row["amount"]) if row["amount"] is not None else None,
            currency=row["currency"],
            status=row["status"],
            received_date=(
                date.fromisoformat(row["received_date"])
                if row["received_date"] else None
            ),
            source=row["source"],
            rule_id=row["rule_id"],
            note=row["note"],
            asset_name=row["asset_name"],
        )

    def list_payouts(
        self,
        asset_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Payout]:
        sql = self._PAYOUT_SELECT
        clauses: list[str] = []
        params: list = []
        if asset_id is not None:
            clauses.append("p.asset_id = ?")
            params.append(asset_id)
        if date_from:
            clauses.append("p.pay_date >= ?")
            params.append(date_from.isoformat())
        if date_to:
            clauses.append("p.pay_date <= ?")
            params.append(date_to.isoformat())
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY p.pay_date, p.id"
        return [self._read_payout(r) for r in self._rows(sql, tuple(params))]

    def get_payout(self, payout_id: int) -> Payout | None:
        row = self.conn.execute(
            self._PAYOUT_SELECT + " WHERE p.id = ?", (payout_id,)
        ).fetchone()
        return self._read_payout(row) if row else None

    def add_payout(
        self, asset_id: int, kind: str, pay_date: date, rate: float | None = None,
        amount: float | None = None, currency: str = "RUB",
        status: str = "expected", received_date: date | None = None,
        source: str = "", rule_id: int | None = None, note: str = "",
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO payouts (asset_id, kind, pay_date, rate, amount, "
                "currency, status, received_date, source, rule_id, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    asset_id, kind, pay_date.isoformat(), rate, amount, currency,
                    status, received_date.isoformat() if received_date else None,
                    source.strip(), rule_id, note.strip(),
                ),
            )
        return int(cur.lastrowid)

    def update_payout(
        self, payout_id: int, kind: str, pay_date: date, rate: float | None = None,
        amount: float | None = None, currency: str = "RUB",
        status: str = "expected", received_date: date | None = None,
        note: str = "",
    ) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE payouts SET kind = ?, pay_date = ?, rate = ?, amount = ?, "
                "currency = ?, status = ?, received_date = ?, note = ? WHERE id = ?",
                (
                    kind, pay_date.isoformat(), rate, amount, currency, status,
                    received_date.isoformat() if received_date else None,
                    note.strip(), payout_id,
                ),
            )

    def delete_payout(self, payout_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM payouts WHERE id = ?", (payout_id,))

    def delete_payouts_by_rule(self, rule_id: int) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM payouts WHERE rule_id = ? AND status = 'expected'",
                (rule_id,),
            )

    # --- правила выплат ---

    _RULE_SELECT = """
    SELECT r.id, r.asset_id, r.kind, r.rate, r.period, r.anchor, r.currency,
           r.note, r.active, a.name AS asset_name
    FROM payout_rules r JOIN assets a ON a.id = r.asset_id
    """

    @staticmethod
    def _read_rule(row: sqlite3.Row) -> PayoutRule:
        return PayoutRule(
            id=row["id"],
            asset_id=row["asset_id"],
            kind=row["kind"],
            rate=float(row["rate"]),
            period=row["period"],
            anchor=date.fromisoformat(row["anchor"]),
            currency=row["currency"],
            note=row["note"],
            active=bool(row["active"]),
            asset_name=row["asset_name"],
        )

    def list_payout_rules(self, asset_id: int | None = None) -> list[PayoutRule]:
        sql = self._RULE_SELECT
        params: tuple = ()
        if asset_id is not None:
            sql += " WHERE r.asset_id = ?"
            params = (asset_id,)
        sql += " ORDER BY r.anchor, r.id"
        return [self._read_rule(r) for r in self._rows(sql, params)]

    def get_payout_rule(self, rule_id: int) -> PayoutRule | None:
        row = self.conn.execute(
            self._RULE_SELECT + " WHERE r.id = ?", (rule_id,)
        ).fetchone()
        return self._read_rule(row) if row else None

    def add_payout_rule(
        self, asset_id: int, kind: str, rate: float, period: str, anchor: date,
        currency: str = "RUB", note: str = "", active: bool = True,
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO payout_rules (asset_id, kind, rate, period, anchor, "
                "currency, note, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    asset_id, kind, rate, period, anchor.isoformat(), currency,
                    note.strip(), 1 if active else 0,
                ),
            )
        return int(cur.lastrowid)

    def delete_payout_rule(self, rule_id: int) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM payouts WHERE rule_id = ?", (rule_id,)
            )
            self.conn.execute("DELETE FROM payout_rules WHERE id = ?", (rule_id,))

    # --- настройки ---

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default
    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
