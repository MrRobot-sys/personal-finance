"""Получение текущих цен активов, курсов валют и графиков выплат.

Источники (все без ключей, только стандартная библиотека):
  * MOEX ISS   — акции и фонды Московской биржи;
  * Yahoo Finance chart — акции и ETF США, объявленные дивиденды;
  * CBR (cbr-xml-daily.ru) — курсы USD/EUR к рублю;
  * MOEX bondization — график будущих купонов облигаций;
  * smart-lab.ru — календарь дивидендов российских компаний;
  * MOEX ISS securities + Yahoo Finance search — подсказки бумаг при
    добавлении биржевого актива.

Модуль устроен для офлайн-работы: любая сетевая ошибка превращается в
``QuoteError``, а приложение продолжает использовать сохранённые оценки.
Разбор ответов вынесен в чистые функции, чтобы проверять их без сети.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser

from .models import (
    MARKET_MOEX,
    MARKET_US,
    SecurityMatch,
    category_for_moex,
    category_for_yahoo,
)

USER_AGENT = "Mozilla/5.0 (compatible; PersonalFinance/1.0)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
TIMEOUT = 6.0
CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
SMARTLAB_DIVIDENDS_URL = "https://smart-lab.ru/dividends/"

Opener = Callable[[str], bytes]

_MOEX_PRICE_COLUMNS = ("LAST", "MARKETPRICE", "LCURRENTPRICE", "CLOSEPRICE", "WAPRICE")


class QuoteError(RuntimeError):
    """Не удалось получить цену: нет сети, неизвестный тикер, биржа недоступна."""


@dataclass(frozen=True)
class Quote:
    price: float
    currency: str
    source: str
    fetched_at: str


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def moex_url(ticker: str) -> str:
    sec = urllib.parse.quote(ticker.strip().upper())
    return (
        f"https://iss.moex.com/iss/engines/stock/markets/shares/"
        f"securities/{sec}.json?iss.meta=off&iss.only=marketdata"
    )


def moex_bonds_url(ticker: str) -> str:
    """Рынок облигаций MOEX — цены облигаций не отдаются в рынке shares."""
    sec = urllib.parse.quote(ticker.strip().upper())
    return (
        f"https://iss.moex.com/iss/engines/stock/markets/bonds/"
        f"securities/{sec}.json?iss.meta=off&iss.only=marketdata"
    )


def yahoo_url(ticker: str) -> str:
    sec = urllib.parse.quote(ticker.strip().upper())
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{sec}?interval=1d&range=1d"


def http_get(url: str, timeout: float = TIMEOUT,
             user_agent: str = USER_AGENT) -> bytes:
    """Сетевой запрос через urllib. Ошибки — в виде QuoteError."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        raise QuoteError(f"Нет соединения: {exc}") from exc


# --- чистые парсеры (тестируются без сети) ---

def parse_moex(payload: bytes | str) -> float | None:
    """Возвращает последнюю цену из ответа MOEX ISS или None."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise QuoteError("MOEX: не удалось разобрать ответ") from exc
    block = data.get("marketdata") or {}
    columns = block.get("columns") or []
    rows = block.get("data") or []
    if not columns or not rows:
        return None
    index = {name: i for i, name in enumerate(columns)}

    def price_of(row) -> float | None:
        for name in _MOEX_PRICE_COLUMNS:
            pos = index.get(name)
            if pos is None or pos >= len(row):
                continue
            value = row[pos]
            if value is not None:
                return float(value)
        return None

    fallback: float | None = None
    for row in rows:
        price = price_of(row)
        if price is None:
            continue
        board = row[index["BOARDID"]] if "BOARDID" in index else ""
        if board == "TQBR":  # основной режим акций/фондов
            return price
        if fallback is None:
            fallback = price
    return fallback


def parse_yahoo(payload: bytes | str) -> tuple[float | None, str]:
    """Возвращает (цена, валюта) из ответа Yahoo Finance chart."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise QuoteError("Yahoo: не удалось разобрать ответ") from exc
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        return None, "USD"
    meta = results[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    currency = meta.get("currency") or "USD"
    return (float(price) if price is not None else None), currency


def parse_cbr(payload: bytes | str) -> dict[str, float]:
    """Курсы USD/EUR к рублю за 1 единицу валюты из ответа ЦБ."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise QuoteError("ЦБ: не удалось разобрать ответ") from exc
    valute = data.get("Valute") or {}
    rates: dict[str, float] = {}
    for code in ("USD", "EUR"):
        item = valute.get(code)
        if not item:
            continue
        nominal = item.get("Nominal") or 1
        value = item.get("Value")
        if value is not None and nominal:
            rates[code] = float(value) / float(nominal)
    return rates


# --- загрузка ---

def fetch_quote(asset, opener: Opener | None = None) -> Quote:
    """Текущая цена актива. Для имущества/ручных активов — QuoteError."""
    fetch = opener or http_get
    ticker = (asset.ticker or "").strip()
    if not ticker:
        raise QuoteError("У актива не указан тикер")
    if asset.market == MARKET_MOEX:
        price = parse_moex(fetch(moex_url(ticker)))
        if price is None:  # акции/фонды не нашлись — пробуем рынок облигаций
            price = parse_moex(fetch(moex_bonds_url(ticker)))
        if price is None:
            raise QuoteError(f"MOEX: нет цены для «{ticker}»")
        return Quote(price, "RUB", "moex", now_iso())
    if asset.market == MARKET_US:
        price, currency = parse_yahoo(fetch(yahoo_url(ticker)))
        if price is None:
            raise QuoteError(f"Yahoo: нет цены для «{ticker}»")
        return Quote(price, currency, "yahoo", now_iso())
    raise QuoteError("Для этого актива нет онлайн-цен")


def fetch_rates(opener: Opener | None = None) -> dict[str, float]:
    """Курсы USD/EUR к рублю с сайта ЦБ. Пустой словарь, если ничего не пришло."""
    fetch = opener or http_get
    rates = parse_cbr(fetch(CBR_URL))
    if not rates:
        raise QuoteError("ЦБ: курсы не найдены")
    return rates


# --- поиск бумаг для подсказок при добавлении актива ---

MOEX_SEARCH_URL = "https://iss.moex.com/iss/securities.json"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"


def moex_search_url(query: str) -> str:
    text = urllib.parse.quote(query.strip())
    return f"{MOEX_SEARCH_URL}?q={text}&iss.meta=off"


def yahoo_search_url(query: str) -> str:
    text = urllib.parse.quote(query.strip())
    return f"{YAHOO_SEARCH_URL}?q={text}&quotesCount=8&newsCount=0&listsCount=0"


def parse_moex_securities(payload: bytes | str, limit: int = 8) -> list[SecurityMatch]:
    """Биржевые бумаги MOEX из ответа ``/iss/securities.json``.

    Оставляем только торгуемые бумаги фондового рынка (акции, фонды,
    облигации); индексы и прочие инструменты отбрасываем.
    """
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise QuoteError("MOEX: не удалось разобрать поиск бумаг") from exc
    block = data.get("securities") or {}
    columns = [str(c).lower() for c in (block.get("columns") or [])]
    rows = block.get("data") or []
    if not columns or not rows:
        return []
    index = {name: i for i, name in enumerate(columns)}

    def cell(row, name: str):
        pos = index.get(name)
        return row[pos] if pos is not None and pos < len(row) else None

    out: list[SecurityMatch] = []
    seen: set[str] = set()
    for row in rows:
        if cell(row, "is_traded") not in (1, "1", True):
            continue
        group = str(cell(row, "group") or "")
        if not group.startswith("stock_") or group.startswith("stock_index"):
            continue
        ticker = str(cell(row, "secid") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        name = str(cell(row, "shortname") or cell(row, "name") or "").strip()
        type_ = str(cell(row, "type") or "")
        board = str(cell(row, "primary_boardid") or "")
        detail = ", ".join(part for part in (type_, board) if part)
        seen.add(ticker)
        out.append(SecurityMatch(
            ticker=ticker, name=name, currency="RUB",
            category=category_for_moex(type_, group),
            market=MARKET_MOEX, detail=detail,
        ))
        if len(out) >= limit:
            break
    return out


def parse_yahoo_search(payload: bytes | str, limit: int = 8) -> list[SecurityMatch]:
    """Бумаги США из ответа Yahoo Finance search (акции, ETF, фонды)."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise QuoteError("Yahoo: не удалось разобрать поиск бумаг") from exc
    out: list[SecurityMatch] = []
    seen: set[str] = set()
    for item in data.get("quotes") or []:
        quote_type = str(item.get("quoteType") or "").upper()
        if quote_type not in ("EQUITY", "ETF", "MUTUALFUND"):
            continue
        ticker = str(item.get("symbol") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        name = str(item.get("shortname") or item.get("longname") or "").strip()
        detail = str(item.get("exchange") or "")
        seen.add(ticker)
        out.append(SecurityMatch(
            ticker=ticker, name=name, currency="USD",
            category=category_for_yahoo(quote_type),
            market=MARKET_US, detail=detail,
        ))
        if len(out) >= limit:
            break
    return out


def search_moex(query: str, opener: Opener | None = None,
                limit: int = 8) -> list[SecurityMatch]:
    fetch = opener or http_get
    return parse_moex_securities(fetch(moex_search_url(query)), limit)


def search_yahoo(query: str, opener: Opener | None = None,
                 limit: int = 8) -> list[SecurityMatch]:
    if opener is not None:
        payload = opener(yahoo_search_url(query))
    else:
        payload = http_get(yahoo_search_url(query), user_agent=BROWSER_UA)
    return parse_yahoo_search(payload, limit)


def search_securities(market: str, query: str, opener: Opener | None = None,
                      limit: int = 8) -> list[SecurityMatch]:
    """Поиск бумаг для подсказок. Для имущества/ручных активов — пусто."""
    query = (query or "").strip()
    if not query:
        return []
    if market == MARKET_MOEX:
        return search_moex(query, opener, limit)
    if market == MARKET_US:
        return search_yahoo(query, opener, limit)
    return []


# --- графики будущих выплат ---

def bondization_url(secid: str) -> str:
    sec = urllib.parse.quote(secid.strip().upper())
    return (
        f"https://iss.moex.com/iss/securities/{sec}/bondization.json"
        "?iss.meta=off"
    )


def yahoo_dividends_url(ticker: str, years: int = 5) -> str:
    sec = urllib.parse.quote(ticker.strip().upper())
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sec}"
        f"?interval=1d&range={years}y&events=div"
    )


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").replace("\u00a0", "").strip())
    except (TypeError, ValueError):
        return None


def _to_date(value) -> date | None:
    text = (str(value) if value is not None else "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def parse_bondization(payload: bytes | str) -> list[tuple[date, float]]:
    """Купоны облигации MOEX: список (дата, размер купона на одну бумагу)."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise QuoteError("MOEX: не удалось разобрать график купонов") from exc
    block = data.get("coupons") or {}
    columns = [str(c).lower() for c in (block.get("columns") or [])]
    rows = block.get("data") or []
    if not columns or not rows:
        return []
    date_pos = next(
        (i for i, c in enumerate(columns) if c in ("coupondate", "coupon_date")),
        None,
    )
    value_pos = next(
        (i for i, c in enumerate(columns) if c in ("value", "couponvalue", "couponvalue_rub")),
        None,
    )
    if date_pos is None or value_pos is None:
        return []
    out: list[tuple[date, float]] = []
    for row in rows:
        if date_pos >= len(row) or value_pos >= len(row):
            continue
        when = _to_date(row[date_pos])
        amount = _to_float(row[value_pos])
        if when and amount is not None and amount > 0:
            out.append((when, amount))
    out.sort()
    return out


def parse_yahoo_dividends(payload: bytes | str) -> list[tuple[date, float]]:
    """Объявленные/исторические дивиденды из ответа Yahoo Finance chart."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise QuoteError("Yahoo: не удалось разобрать дивиденды") from exc
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        return []
    events = (results[0].get("events") or {}).get("dividends") or {}
    out: list[tuple[date, float]] = []
    for item in events.values():
        amount = _to_float(item.get("amount"))
        if amount is None:
            continue
        moment = item.get("date")
        if moment is None:
            continue
        when = date.fromtimestamp(int(moment))
        if amount > 0:
            out.append((when, amount))
    out.sort()
    return out


class _TableParser(HTMLParser):
    """Собирает все строки всех таблиц HTML в список списков ячеек."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            self._row.append(text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def parse_smartlab_dividends(payload: bytes | str) -> list[dict]:
    """Календарь дивидендов РФ со smart-lab: тикер, сумма, даты, период."""
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", "replace")
    else:
        text = payload
    parser = _TableParser()
    parser.feed(text)
    rows = parser.rows
    if not rows:
        return []
    header = None
    header_index = -1
    for index, cells in enumerate(rows[:5]):
        lowered = [c.strip().lower() for c in cells]
        if any("тикер" in c for c in lowered):
            header = lowered
            header_index = index
            break
    if header is None:
        return []

    def find(*needles: str) -> int | None:
        for pos, name in enumerate(header):
            if any(needle in name for needle in needles):
                return pos
        return None

    ticker_pos = find("тикер")
    amount_pos = find("дивиденд")
    close_pos = find("закрыт", "реестр")
    pay_pos = find("выплат")
    period_pos = find("период")
    if ticker_pos is None or amount_pos is None:
        return []
    out: list[dict] = []
    for cells in rows[header_index + 1:]:
        if ticker_pos >= len(cells):
            continue
        ticker = cells[ticker_pos].strip().upper()
        if not ticker or not ticker.isalnum():
            continue
        amount = _to_float(cells[amount_pos]) if amount_pos < len(cells) else None
        if amount is None or amount <= 0:
            continue
        item = {
            "ticker": ticker,
            "amount": amount,
            "close_date": _to_date(cells[close_pos]) if close_pos is not None and close_pos < len(cells) else None,
            "pay_date": _to_date(cells[pay_pos]) if pay_pos is not None and pay_pos < len(cells) else None,
            "period": cells[period_pos] if period_pos is not None and period_pos < len(cells) else "",
        }
        out.append(item)
    return out


def fetch_bond_coupons(secid: str, opener: Opener | None = None) -> list[tuple[date, float]]:
    fetch = opener or http_get
    return parse_bondization(fetch(bondization_url(secid)))


def fetch_yahoo_dividends(ticker: str, opener: Opener | None = None) -> list[tuple[date, float]]:
    fetch = opener or http_get
    return parse_yahoo_dividends(fetch(yahoo_dividends_url(ticker)))


def fetch_smartlab_dividends(opener: Opener | None = None) -> list[dict]:
    if opener is not None:
        payload = opener(SMARTLAB_DIVIDENDS_URL)
    else:
        payload = http_get(SMARTLAB_DIVIDENDS_URL, user_agent=BROWSER_UA)
    return parse_smartlab_dividends(payload)
