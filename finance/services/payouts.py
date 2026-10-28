"""Домен выплат: дивиденды, купоны, правила и календарь."""
from __future__ import annotations

from datetime import date

from ..models import (
    BUY,
    MARKET_MOEX,
    MARKET_US,
    PAYOUT_COUPON,
    PAYOUT_DIVIDEND,
    PAYOUT_EXPECTED,
    PAYOUT_RECEIVED,
    PERIOD_ONCE,
    PERIOD_MONTHS,
    Asset,
    Payout,
    PayoutRule,
    Trade,
    ValidationError,
    add_months,
    validate_payout_kind,
    validate_period,
)
from .constants import PAST_PAYOUT_MONTHS
from .core import ServiceBase
from .dto import PayoutEntry, PayoutFetch, RefreshResult


class PayoutService(ServiceBase):
    """Выплаты, правила их повторения и календарь ожидаемых поступлений."""

    # --- выплаты в базе ---

    def payouts(
        self, asset_id: int | None = None,
        date_from: date | None = None, date_to: date | None = None,
    ) -> list[Payout]:
        return self.repo.list_payouts(asset_id, date_from, date_to)

    def payout(self, payout_id: int) -> Payout | None:
        return self.repo.get_payout(payout_id)

    def create_payout(
        self, asset_id: int, kind: str, pay_date: date,
        rate: float | None = None, amount: float | None = None,
        status: str = PAYOUT_EXPECTED, received_date: date | None = None,
        note: str = "", source: str = "manual", rule_id: int | None = None,
    ) -> int:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise ValidationError("Актив не найден")
        kind = validate_payout_kind(kind)
        if status not in (PAYOUT_EXPECTED, PAYOUT_RECEIVED):
            raise ValidationError("Неизвестный статус выплаты")
        if status == PAYOUT_RECEIVED and (amount is None or amount < 0):
            raise ValidationError("Укажите полученную сумму")
        if status == PAYOUT_EXPECTED and rate is None and amount is None:
            raise ValidationError("Укажите ставку на единицу или ожидаемую сумму")
        if rate is not None and rate < 0:
            raise ValidationError("Ставка не может быть отрицательной")
        if amount is not None and amount < 0:
            raise ValidationError("Сумма не может быть отрицательной")
        if received_date is None and status == PAYOUT_RECEIVED:
            received_date = pay_date
        return self.repo.add_payout(
            asset_id, kind, pay_date,
            round(rate, 6) if rate is not None else None,
            round(amount, 2) if amount is not None else None,
            asset.currency, status, received_date, source, rule_id, note,
        )

    def update_payout(
        self, payout_id: int, kind: str, pay_date: date,
        rate: float | None = None, amount: float | None = None,
        status: str = PAYOUT_EXPECTED, received_date: date | None = None,
        note: str = "",
    ) -> None:
        existing = self.repo.get_payout(payout_id)
        if existing is None:
            raise ValidationError("Выплата не найдена")
        kind = validate_payout_kind(kind)
        if status not in (PAYOUT_EXPECTED, PAYOUT_RECEIVED):
            raise ValidationError("Неизвестный статус выплаты")
        if status == PAYOUT_RECEIVED and (amount is None or amount < 0):
            raise ValidationError("Укажите полученную сумму")
        if status == PAYOUT_EXPECTED and rate is None and amount is None:
            raise ValidationError("Укажите ставку на единицу или ожидаемую сумму")
        if rate is not None and rate < 0:
            raise ValidationError("Ставка не может быть отрицательной")
        if amount is not None and amount < 0:
            raise ValidationError("Сумма не может быть отрицательной")
        self.repo.update_payout(
            payout_id, kind, pay_date,
            round(rate, 6) if rate is not None else None,
            round(amount, 2) if amount is not None else None,
            existing.currency, status, received_date, note,
        )

    def remove_payout(self, payout_id: int) -> None:
        self.repo.delete_payout(payout_id)

    def mark_payout_received(
        self, payout_id: int, amount: float, received_date: date | None = None,
    ) -> None:
        payout = self.repo.get_payout(payout_id)
        if payout is None:
            raise ValidationError("Выплата не найдена")
        if amount is None or amount < 0:
            raise ValidationError("Сумма не может быть отрицательной")
        self.repo.update_payout(
            payout_id, payout.kind, payout.pay_date, payout.rate,
            round(amount, 2), payout.currency, PAYOUT_RECEIVED,
            received_date or date.today(), payout.note,
        )

    def receive_entry(
        self, entry: PayoutEntry, amount: float, received_date: date | None = None,
    ) -> None:
        """Отметить выплату календаря полученной.

        Для сохранённой выплаты меняет статус, для вхождения правила —
        материализует запись, которая перекроет вхождение в тот же день.
        """
        if amount is None or amount < 0:
            raise ValidationError("Сумма не может быть отрицательной")
        when = received_date or entry.date
        if entry.payout_id is not None:
            self.mark_payout_received(entry.payout_id, amount, when)
            return
        self.create_payout(
            entry.asset_id, entry.kind, entry.date, rate=entry.rate,
            amount=amount, status=PAYOUT_RECEIVED, received_date=when,
            note=entry.note, source=entry.source or "rule", rule_id=entry.rule_id,
        )

    def due_past_payouts(
        self, asset_id: int | None = None, months: int = PAST_PAYOUT_MONTHS,
    ) -> list[PayoutEntry]:
        """Прошедшие ожидаемые выплаты, которые ещё не отмечены полученными."""
        today = date.today()
        start = add_months(today, -months)
        entries = self.calendar_entries(start, today, asset_id)
        return [e for e in entries if e.is_due]

    def expected_payout_amount(self, payout: Payout) -> float:
        asset = self.repo.get_asset(payout.asset_id)
        quantity = asset.quantity if asset else 0.0
        return payout.expected(quantity)

    def holding_quantity_at(self, asset_id: int, day: date) -> float:
        """Количество актива на конец указанного дня по сделкам."""
        total = 0.0
        for trade in self.repo.list_trades(asset_id):
            if trade.trade_date <= day:
                total += trade.quantity if trade.kind == BUY else -trade.quantity
        return total

    # --- правила выплат ---

    def payout_rules(self, asset_id: int | None = None) -> list[PayoutRule]:
        return self.repo.list_payout_rules(asset_id)

    def create_payout_rule(
        self, asset_id: int, kind: str, rate: float, period: str, anchor: date,
        note: str = "",
    ) -> int:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise ValidationError("Актив не найден")
        kind = validate_payout_kind(kind)
        period = validate_period(period)
        if rate is None or rate <= 0:
            raise ValidationError("Ставка должна быть больше нуля")
        return self.repo.add_payout_rule(
            asset_id, kind, round(rate, 6), period, anchor, asset.currency, note
        )

    def remove_payout_rule(self, rule_id: int) -> None:
        self.repo.delete_payout_rule(rule_id)

    @staticmethod
    def rule_dates(rule: PayoutRule, date_from: date, date_to: date) -> list[date]:
        anchor = rule.anchor
        if rule.period == PERIOD_ONCE:
            return [anchor] if date_from <= anchor <= date_to else []
        step = PERIOD_MONTHS.get(rule.period)
        if not step:
            return []
        current = anchor
        guard = 0
        while current < date_from and guard < 4000:
            current = add_months(current, step)
            guard += 1
        dates: list[date] = []
        while current <= date_to and guard < 8000:
            if current >= date_from:
                dates.append(current)
            current = add_months(current, step)
            guard += 1
        return dates

    # --- календарь ---

    def calendar_entries(
        self, date_from: date, date_to: date, asset_id: int | None = None,
    ) -> list[PayoutEntry]:
        assets = {a.id: a for a in self.repo.list_assets()}
        entries: list[PayoutEntry] = []
        taken: set[tuple[int, date]] = set()
        today = date.today()
        trades_cache: dict[int, list[Trade]] = {}

        def quantity_at(asset_id: int, day: date) -> float | None:
            """Количество на дату; None для будущих дат (не требуется)."""
            if day > today:
                return None
            trades = trades_cache.get(asset_id)
            if trades is None:
                trades = self.repo.list_trades(asset_id)
                trades_cache[asset_id] = trades
            return sum(
                t.quantity if t.kind == BUY else -t.quantity
                for t in trades
                if t.trade_date <= day
            )

        for payout in self.repo.list_payouts(asset_id, date_from, date_to):
            asset = assets.get(payout.asset_id)
            quantity = asset.quantity if asset else 0.0
            entries.append(
                PayoutEntry(
                    date=payout.pay_date,
                    asset_id=payout.asset_id,
                    asset_name=payout.asset_name,
                    kind=payout.kind,
                    currency=payout.currency,
                    expected=payout.expected(quantity),
                    status=payout.status,
                    source=payout.source,
                    payout_id=payout.id,
                    rule_id=payout.rule_id,
                    received=payout.amount,
                    note=payout.note,
                    rate=payout.rate,
                    quantity_at=quantity_at(payout.asset_id, payout.pay_date),
                )
            )
            taken.add((payout.asset_id, payout.pay_date))
        for rule in self.repo.list_payout_rules():
            if not rule.active:
                continue
            if asset_id is not None and rule.asset_id != asset_id:
                continue
            asset = assets.get(rule.asset_id)
            quantity = asset.quantity if asset else 0.0
            for day in self.rule_dates(rule, date_from, date_to):
                if (rule.asset_id, day) in taken:
                    continue
                entries.append(
                    PayoutEntry(
                        date=day,
                        asset_id=rule.asset_id,
                        asset_name=rule.asset_name,
                        kind=rule.kind,
                        currency=rule.currency,
                        expected=rule.rate * quantity,
                        status=PAYOUT_EXPECTED,
                        source="rule",
                        rule_id=rule.id,
                        note=rule.note,
                        rate=rule.rate,
                        quantity_at=quantity_at(rule.asset_id, day),
                    )
                )
        entries.sort(key=lambda e: (e.date, e.asset_name.lower()))
        return entries

    def payout_calendar_totals(
        self, date_from: date, date_to: date, asset_id: int | None = None,
    ) -> tuple[float, float]:
        """(ожидаемые, полученные) выплаты за период (в валюте активов)."""
        entries = self.calendar_entries(date_from, date_to, asset_id)
        expected = sum(
            e.expected for e in entries if not e.is_received
        )
        received = sum(
            (e.received if e.received is not None else e.expected)
            for e in entries if e.is_received
        )
        return expected, received

    # --- онлайн-выплаты ---

    @staticmethod
    def _project_dividends(
        history: list[tuple[date, float]], horizon_months: int = 12, limit: int = 12,
    ) -> list[tuple[date, float]]:
        """Оценка будущих дивидендов по истории (для акций США)."""
        if not history:
            return []
        history = sorted(history)
        last_date, last_amount = history[-1]
        if last_amount <= 0:
            return []
        gaps = [
            (history[i][0] - history[i - 1][0]).days
            for i in range(1, len(history))
        ][-4:]
        if gaps:
            average = sum(gaps) / len(gaps)
            step = 1 if average <= 45 else 3 if average <= 135 else 12
        else:
            step = 3
        today = date.today()
        horizon = add_months(today, horizon_months)
        out: list[tuple[date, float]] = []
        moment = add_months(last_date, step)
        while moment <= horizon and len(out) < limit:
            if moment >= today:
                out.append((moment, last_amount))
            moment = add_months(moment, step)
        return out

    def fetch_payouts(
        self, assets: list[Asset] | None = None, opener=None,
        include_past: bool = False,
    ) -> PayoutFetch:
        """Только сеть, без записи в базу (можно вызывать из потока).

        Для бумаг MOEX — график купонов с ISS и дивиденды со smart-lab,
        для бумаг США — прогноз по истории дивидендов Yahoo (а при
        include_past — ещё и прошедшие дивиденды из истории).
        """
        from .. import quotes

        assets = self.repo.list_assets() if assets is None else assets
        result = PayoutFetch()
        ru_calendar: list[dict] | None = None
        for asset in assets:
            ticker = (asset.ticker or "").strip()
            if not ticker:
                continue
            if asset.market == MARKET_MOEX:
                try:
                    coupons = quotes.fetch_bond_coupons(ticker, opener=opener)
                except quotes.QuoteError as exc:
                    coupons = []
                    result.failures.append(f"{ticker} (купоны): {exc}")
                for when, value in coupons:
                    result.payouts.append({
                        "asset_id": asset.id, "kind": PAYOUT_COUPON,
                        "date": when, "rate": value, "source": "moex",
                        "note": "MOEX: купон",
                    })
                if ru_calendar is None:
                    try:
                        ru_calendar = quotes.fetch_smartlab_dividends(opener=opener)
                    except quotes.QuoteError as exc:
                        ru_calendar = []
                        result.failures.append(f"smart-lab: {exc}")
                for row in ru_calendar:
                    if row["ticker"] != ticker.upper():
                        continue
                    when = row.get("pay_date") or row.get("close_date")
                    if when is None:
                        continue
                    result.payouts.append({
                        "asset_id": asset.id, "kind": PAYOUT_DIVIDEND,
                        "date": when, "rate": row["amount"], "source": "smartlab",
                        "note": f"smart-lab: дивиденд, {row.get('period', '')}".strip(),
                    })
            elif asset.market == MARKET_US:
                try:
                    history = quotes.fetch_yahoo_dividends(ticker, opener=opener)
                except quotes.QuoteError as exc:
                    result.failures.append(f"{ticker}: {exc}")
                    continue
                for when, rate in self._project_dividends(history):
                    result.payouts.append({
                        "asset_id": asset.id, "kind": PAYOUT_DIVIDEND,
                        "date": when, "rate": rate, "source": "yahoo",
                        "note": "Yahoo: прогноз дивиденда",
                    })
                if include_past:
                    for when, rate in history:
                        result.payouts.append({
                            "asset_id": asset.id, "kind": PAYOUT_DIVIDEND,
                            "date": when, "rate": rate, "source": "yahoo",
                            "note": "Yahoo: дивиденд",
                        })
        return result

    def apply_payout_fetch(
        self, fetched: PayoutFetch, include_past: bool = False,
    ) -> RefreshResult:
        """Запись найденных выплат в базу (в основном потоке).

        При include_past дополнительно добавляются прошедшие выплаты, но
        только если бумага была в портфеле на дату выплаты и дата не старше
        окна PAST_PAYOUT_MONTHS (и не раньше даты первой покупки).
        """
        added = 0
        today = date.today()
        window_start = add_months(today, -PAST_PAYOUT_MONTHS)
        by_asset: dict[int, list[dict]] = {}
        for spec in fetched.payouts:
            by_asset.setdefault(spec["asset_id"], []).append(spec)
        for asset_id, specs in by_asset.items():
            asset = self.repo.get_asset(asset_id)
            if asset is None:
                continue
            existing = {
                (p.kind, p.pay_date) for p in self.repo.list_payouts(asset_id)
            }
            start = window_start
            if asset.first_buy is not None and asset.first_buy > start:
                start = asset.first_buy
            for spec in specs:
                when = spec.get("date")
                if when is None:
                    continue
                rate = spec.get("rate")
                if rate is None or rate <= 0:
                    continue
                if when < today:
                    if not include_past or when < start:
                        continue
                    if self.holding_quantity_at(asset_id, when) <= 0:
                        continue
                key = (spec["kind"], when)
                if key in existing:
                    continue
                self.repo.add_payout(
                    asset_id, spec["kind"], when, round(rate, 6), None,
                    asset.currency, PAYOUT_EXPECTED, None,
                    spec.get("source", ""), None, spec.get("note", ""),
                )
                existing.add(key)
                added += 1
        return RefreshResult(updated=added, failed=list(fetched.failures))

    def sync_payouts(self, opener=None, include_past: bool = False) -> RefreshResult:
        return self.apply_payout_fetch(
            self.fetch_payouts(opener=opener, include_past=include_past),
            include_past=include_past,
        )
