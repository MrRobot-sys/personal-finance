"""Домен инвестиций: активы, сделки, ручные оценки и сводка портфеля."""
from __future__ import annotations

from datetime import date

from ..models import (
    BUY,
    SELL,
    MARKET_PHYSICAL,
    ONLINE_MARKETS,
    Asset,
    PortfolioSummary,
    PortfolioTotals,
    Trade,
    ValidationError,
    validate_asset_name,
    validate_currency,
    validate_market,
)
from ..repository import Repository
from .core import ServiceBase
from .quotes import QuoteService


class InvestmentService(ServiceBase):
    """Активы всех типов, сделки и агрегаты портфеля.

    Для пересчёта в рубли используется :class:`QuoteService`: курсы валют
    остаются единственным источником правды.
    """

    def __init__(self, repo: Repository, quotes: QuoteService):
        super().__init__(repo)
        self.quotes = quotes

    # --- активы ---

    def assets(self, scope: str | None = None) -> list[Asset]:
        return self.repo.list_assets(scope)

    def asset(self, asset_id: int) -> Asset | None:
        return self.repo.get_asset(asset_id)

    def create_asset(
        self, name: str, market: str, ticker: str = "", currency: str = "RUB",
        category: str = "", details: str = "", depreciation_rate: float | None = None,
        note: str = "", quantity: float | None = None, price: float | None = None,
        trade_date: date | None = None, fee: float = 0.0,
    ) -> int:
        name, market, ticker, currency, category, depreciation_rate = (
            self._validate_asset_fields(
                name, market, ticker, currency, category, depreciation_rate
            )
        )
        if ticker and self.repo.asset_by_ticker(ticker, market) is not None:
            raise ValidationError(f"Актив «{ticker}» уже есть в портфеле")
        asset_id = self.repo.add_asset(
            name, market, ticker, currency, category, details,
            depreciation_rate, note.strip(),
        )
        if quantity:
            self.add_trade(
                asset_id, BUY, quantity, price or 0.0,
                trade_date or date.today(), fee,
            )
        return asset_id

    def update_asset(
        self, asset_id: int, name: str, market: str, ticker: str = "",
        currency: str = "RUB", category: str = "", details: str = "",
        depreciation_rate: float | None = None, note: str = "",
    ) -> None:
        if self.repo.get_asset(asset_id) is None:
            raise ValidationError("Актив не найден")
        name, market, ticker, currency, category, depreciation_rate = (
            self._validate_asset_fields(
                name, market, ticker, currency, category, depreciation_rate
            )
        )
        existing = self.repo.asset_by_ticker(ticker, market) if ticker else None
        if existing is not None and existing.id != asset_id:
            raise ValidationError(f"Актив «{ticker}» уже есть в портфеле")
        self.repo.update_asset(
            asset_id, name, market, ticker, currency, category, details,
            depreciation_rate, note.strip(),
        )

    @staticmethod
    def _validate_asset_fields(
        name, market, ticker, currency, category, depreciation_rate
    ):
        name = validate_asset_name(name)
        market = validate_market(market)
        currency = validate_currency(currency or "RUB")
        ticker = (ticker or "").strip().upper()
        if market in ONLINE_MARKETS and not ticker:
            raise ValidationError("Для биржевого актива укажите тикер")
        if market not in ONLINE_MARKETS:
            ticker = ""
        category = (category or "").strip()
        if market != MARKET_PHYSICAL:
            depreciation_rate = None
        elif depreciation_rate is not None and depreciation_rate < 0:
            raise ValidationError("Износ не может быть отрицательным")
        return name, market, ticker, currency, category, depreciation_rate

    def remove_asset(self, asset_id: int) -> None:
        self.repo.delete_asset(asset_id)

    # --- сделки ---

    def trades(self, asset_id: int) -> list[Trade]:
        return self.repo.list_trades(asset_id)

    def add_trade(
        self, asset_id: int, kind: str, quantity: float, price: float,
        trade_date: date, fee: float = 0.0, note: str = "",
    ) -> int:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise ValidationError("Актив не найден")
        if kind not in (BUY, SELL):
            raise ValidationError("Неизвестный тип сделки")
        if quantity is None or quantity <= 0:
            raise ValidationError("Количество должно быть больше нуля")
        if price is None or price < 0:
            raise ValidationError("Цена не может быть отрицательной")
        if fee is None or fee < 0:
            raise ValidationError("Комиссия не может быть отрицательной")
        if kind == SELL and quantity > asset.quantity + 1e-9:
            raise ValidationError("Недостаточно актива для продажи")
        return self.repo.add_trade(
            asset_id, kind, round(quantity, 6), round(price, 6),
            trade_date, round(fee, 2), note,
        )

    def remove_trade(self, trade_id: int) -> None:
        self.repo.delete_trade(trade_id)

    def set_manual_price(
        self, asset_id: int, price: float, on_date: date | None = None,
        source: str = "manual",
    ) -> None:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise ValidationError("Актив не найден")
        if price is None or price < 0:
            raise ValidationError("Оценка не может быть отрицательной")
        stamp = f"{on_date.isoformat()} 12:00:00" if on_date else None
        self.repo.add_price(
            asset_id, round(price, 6), asset.currency, source, stamp
        )

    # --- сводка портфеля ---

    def portfolio_summary(self, assets: list[Asset] | None = None) -> PortfolioSummary:
        assets = self.repo.list_assets() if assets is None else assets
        rates = self.quotes.rates()
        securities = PortfolioTotals()
        physical = PortfolioTotals()
        deployed = 0.0
        for asset in assets:
            rate = 1.0 if asset.currency == "RUB" else rates.get(asset.currency, 1.0)
            target = physical if asset.is_physical else securities
            target.invested += asset.cost_basis * rate
            target.value += asset.market_value * rate
            target.realized += asset.realized * rate
            # В пул вложены нетто-покупки: покупки с комиссией минус продажи за вычетом комиссии.
            deployed += (asset.invested - asset.proceeds) * rate
        total = PortfolioTotals(
            invested=securities.invested + physical.invested,
            value=securities.value + physical.value,
            realized=securities.realized + physical.realized,
        )
        return PortfolioSummary(
            securities, physical, total, "RUB",
            rates.get("USD"), rates.get("EUR"),
            contributed=self.repo.invested_total(),
            deployed=deployed,
        )

    def portfolio_history(self, scope: str | None = None) -> list[tuple[date, float]]:
        """Стоимость портфеля по датам оценок (в рублях, по текущему курсу)."""
        assets = {a.id: a for a in self.repo.list_assets(scope)}
        if not assets:
            return []
        rates = self.quotes.rates()
        series: dict[int, list[tuple[str, float]]] = {}
        days: set[str] = set()
        for point in self.repo.list_prices():
            if point.asset_id not in assets:
                continue
            series.setdefault(point.asset_id, []).append(
                (point.fetched_at, point.price)
            )
            days.add(point.fetched_at[:10])
        if not days:
            return []
        trades: dict[int, list[tuple[date, float]]] = {}
        for asset_id in assets:
            trades[asset_id] = [
                (t.trade_date, t.quantity if t.kind == BUY else -t.quantity)
                for t in self.repo.list_trades(asset_id)
            ]
        points: list[tuple[date, float]] = []
        for day in sorted(days):
            total = 0.0
            for asset_id, asset in assets.items():
                quantity = sum(
                    qty for when, qty in trades.get(asset_id, [])
                    if when.isoformat() <= day
                )
                if not quantity:
                    continue
                price = asset.avg_price
                for stamp, value in series.get(asset_id, []):
                    if stamp[:10] <= day:
                        price = value
                    else:
                        break
                rate = 1.0 if asset.currency == "RUB" else rates.get(asset.currency, 1.0)
                total += quantity * price * rate
            points.append((date.fromisoformat(day), total))
        return points
