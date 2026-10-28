"""Домен котировок: курсы валют, сетевые цены и их запись в базу."""
from __future__ import annotations

from ..models import ONLINE_MARKETS, Asset
from ..quotes import now_iso
from .constants import RATES_UPDATED_KEY
from .core import ServiceBase
from .dto import PriceFetch, RefreshResult


class QuoteService(ServiceBase):
    """Курсы ЦБ и рыночные цены активов.

    Сетевые операции (:meth:`fetch_quotes`) не пишут в базу, поэтому их можно
    вызывать из фонового потока; применение результата делает главный поток
    через :meth:`apply_fetch`.
    """

    # --- курсы валют ---

    def rates(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for code in ("USD", "EUR"):
            raw = self.repo.get_setting(f"rate_{code}")
            if raw:
                try:
                    result[code] = float(raw)
                except ValueError:
                    pass
        return result

    def set_rates(self, rates: dict[str, float]) -> None:
        for code, value in (rates or {}).items():
            if value and value > 0:
                self.repo.set_setting(f"rate_{code}", f"{float(value):.6f}")
        self.repo.set_setting(RATES_UPDATED_KEY, now_iso())

    def rate_to_rub(self, currency: str) -> float:
        if currency == "RUB":
            return 1.0
        return self.rates().get(currency, 1.0)

    # --- обновление цен ---

    def fetch_quotes(self, assets: list[Asset] | None = None, opener=None) -> PriceFetch:
        """Только сеть, без записи в базу (можно вызывать из потока)."""
        from .. import quotes

        assets = self.repo.list_assets() if assets is None else assets
        result = PriceFetch()
        for asset in assets:
            if asset.market not in ONLINE_MARKETS:
                continue
            try:
                quote = quotes.fetch_quote(asset, opener=opener)
            except quotes.QuoteError as exc:
                result.failures.append(f"{asset.ticker or asset.name}: {exc}")
                continue
            result.quotes.append((asset.id, quote))
        try:
            result.rates = quotes.fetch_rates(opener=opener)
        except quotes.QuoteError as exc:
            result.failures.append(f"Курсы ЦБ: {exc}")
        return result

    def apply_fetch(self, fetched: PriceFetch) -> RefreshResult:
        """Запись полученных цен и курсов в базу (в основном потоке)."""
        for asset_id, quote in fetched.quotes:
            self.repo.add_price(
                asset_id, quote.price, quote.currency, quote.source, quote.fetched_at
            )
        if fetched.rates:
            self.set_rates(fetched.rates)
        return RefreshResult(updated=len(fetched.quotes), failed=list(fetched.failures))

    def refresh_prices(self, opener=None) -> RefreshResult:
        return self.apply_fetch(self.fetch_quotes(opener=opener))
