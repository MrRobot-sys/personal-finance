"""Точка входа приложения «Учёт личных финансов».

Запуск:            python main.py
Самопроверка:      python main.py --selftest
Проверка интерфейса: python main.py --smoke
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import date
from pathlib import Path


def build_service(db_path=None):
    from finance.db import connect
    from finance.repository import Repository
    from finance.services import FinanceService

    conn = connect(db_path)
    return FinanceService(Repository(conn))


def selftest() -> int:
    from finance.models import (
        EXPENSE,
        INCOME,
        INVEST,
        PAYOUT_COUPON,
        PAYOUT_DIVIDEND,
        PAYOUT_RECEIVED,
        PERIOD_QUARTERLY,
        ValidationError,
        add_months,
        format_amount,
        parse_amount,
        parse_date,
        format_date,
    )

    checks = 0

    def check(condition, message: str) -> None:
        nonlocal checks
        if not condition:
            raise AssertionError(message)
        checks += 1

    service = build_service(":memory:")

    categories = service.categories()
    check(len(categories) == 11, "должны загрузиться стартовые категории")
    check(
        sum(1 for c in categories if c.kind == INCOME) == 3, "3 категории доходов"
    )
    check(
        sum(1 for c in categories if c.kind == EXPENSE) == 6, "6 категорий расходов"
    )
    check(
        sum(1 for c in categories if c.kind == INVEST) == 2, "2 категории инвестиций"
    )

    income_id = service.create_category("Прочий доход", INCOME)
    expense_id = service.create_category("Кафе", EXPENSE)

    try:
        service.create_category("Кафе", EXPENSE)
        raise AssertionError("дубликат категории должен отклоняться")
    except ValidationError:
        checks += 1

    same_name_income = service.create_category("Одно имя", INCOME)
    same_name_expense = service.create_category("Одно имя", EXPENSE)
    check(
        same_name_income != same_name_expense,
        "одно имя допустимо для разных типов",
    )

    t1 = service.create_transaction(income_id, 10000, date(2026, 10, 1), "аванс")
    t2 = service.create_transaction(expense_id, 2500.5, date(2026, 10, 5), "обед, кофе")
    t3 = service.create_transaction(expense_id, 300, date(2026, 9, 20), "кофе")

    check(len(service.transactions()) == 3, "все операции")
    check(len(service.transactions(kind=EXPENSE)) == 2, "фильтр по типу")
    check(len(service.transactions(category_id=expense_id)) == 2, "фильтр по категории")
    check(
        len(service.transactions(date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))) == 2,
        "фильтр по периоду",
    )
    check(len(service.transactions(text="кофе")) == 2, "поиск по заметке")
    check(
        len(service.transactions(text="кофе", date_from=date(2026, 10, 1))) == 1,
        "поиск + период",
    )

    summary = service.month_summary(2026, 10)
    check(summary.income == 10000, "доходы октября")
    check(summary.expense == 2500.5, "расходы октября")
    check(summary.balance == 7499.5, "баланс октября")

    breakdown = service.month_breakdown(2026, 10)
    check(len(breakdown) == 2, "разбивка по категориям")
    check(breakdown[0][2] == 10000, "первая строка разбивки — самая большая")

    series = service.dynamics(2026, 10, 12)
    check(len(series) == 12, "12 месяцев динамики")
    check(series[-1].year == 2026 and series[-1].month == 10, "последний месяц — октябрь")
    check(series[-2].expense == 300, "сентябрь в динамике")

    service.set_monthly_plan(expense_id, "2000")
    service.set_monthly_plan(income_id, "15000")
    plans = service.category_plans(2026, 10)
    target = next(p for p in plans if p.category.id == expense_id)
    check(target.spent == 2500.5, "факт по плану за октябрь")
    check(target.is_over, "перерасход плана")
    check(target.percent == 125, "процент исполнения плана")
    income_plan = next(p for p in plans if p.category.id == income_id)
    check(income_plan.spent == 10000, "факт дохода за октябрь")
    check(income_plan.percent == 67, "процент плана дохода")
    check(not income_plan.is_over, "для дохода перерасхода нет")
    service.set_monthly_plan(expense_id, "")
    cleared = next(
        p for p in service.category_plans(2026, 10) if p.category.id == expense_id
    )
    check(cleared.limit is None and not cleared.is_over, "план можно снять")

    service.create_transaction(expense_id, 400, date(2026, 8, 3), "август")
    service.set_monthly_plan(expense_id, "200")
    avg_exp = next(p for p in service.category_plans(2026, 10) if p.category.id == expense_id)
    check(avg_exp.avg_3 == (400 + 300) / 3, "среднее за 3 месяца")
    check(avg_exp.spent == 2500.5, "в среднее октябрь не входит")
    check(avg_exp.status == "bad", "расход выше плана — плохо")
    service.set_monthly_plan(expense_id, "500")
    avg_exp = next(p for p in service.category_plans(2026, 10) if p.category.id == expense_id)
    check(avg_exp.status == "good", "расход ниже плана — хорошо")
    service.set_monthly_plan(expense_id, "1500")

    service.create_transaction(income_id, 2000, date(2026, 7, 2), "бонус")
    income_avg = next(p for p in service.category_plans(2026, 10) if p.category.id == income_id)
    check(income_avg.avg_3 == (2000 + 0) / 3, "среднее дохода с нулевым месяцем")
    check(income_avg.status == "bad", "доход ниже плана — плохо")

    no_hist = service.create_category("Без истории", EXPENSE)
    no_hist_plan = next(p for p in service.category_plans(2026, 10) if p.category.id == no_hist)
    check(no_hist_plan.avg_3 is None and no_hist_plan.status == "neutral",
          "нет истории — среднее пустое и без подсветки")

    service.update_transaction(t2, income_id, 1500, date(2026, 10, 6), "возврат")
    updated = service.transaction(t2)
    check(updated.category_id == income_id and updated.amount == 1500, "редактирование")
    service.remove_transaction(t2)
    check(service.transactions().__len__() == 4, "удаление операции")
    service.remove_transaction(t1)
    service.remove_transaction(t3)

    used_id = service.create_category("Временная", EXPENSE)
    service.create_transaction(used_id, 100, date(2026, 10, 2))
    try:
        service.remove_category(used_id)
        raise AssertionError("категория с операциями не должна удаляться молча")
    except ValidationError:
        checks += 1
    removed = service.remove_category(used_id, with_transactions=True)
    check(removed == 1, "удаление категории вместе с операцией")

    check(parse_amount("1 234,56") == 1234.56, "разбор суммы с запятой")
    check(parse_amount("2500.5") == 2500.5, "разбор суммы с точкой")
    check(format_amount(1234.5) == "1\u00a0234,50\u00a0₽", "формат суммы")
    check(parse_date("06.10.2026") == date(2026, 10, 6), "разбор даты")
    check(format_date(date(2026, 10, 6)) == "06.10.2026", "формат даты")

    for bad in ("", "-5", "abc", "0"):
        try:
            parse_amount(bad)
            raise AssertionError(f"сумма «{bad}» должна отклоняться")
        except ValidationError:
            checks += 1

    try:
        parse_date("32.01.2026")
        raise AssertionError("некорректная дата должна отклоняться")
    except ValidationError:
        checks += 1

    # --- импорт из файлов выписок ---

    from finance import importers

    csv_bytes = (
        "Имя счёта;Дата операции;Сумма операции;Сумма в валюте счёта;"
        "Категория по-умолчанию;Ваша категория;Описание;Учёт в аналитике\r\n"
        "Black;06.10.2026 20:30:41;-43,00;-43,00;Местный транспорт;;СберТройка;Да\r\n"
        "Black;06.10.2026 09:00:00;1000,00;1000,00;Переводы;;Юрий П.;Да\r\n"
        "Black;05.10.2026 12:00:00;0,00;0,00;Пропуск;;;-;\r\n"
        "Black;05.10.2026 13:00:00;-5,00;-5,00;Такси;;Ряд;Нет\r\n"
    ).encode("cp1251")
    csv_ops = importers.parse_bytes(csv_bytes)
    check(len(csv_ops) == 2, "csv: пропуск «Нет» и нулевой суммы")
    check(csv_ops[0].kind == EXPENSE and csv_ops[0].amount == 43, "csv: расход по минусу")
    check(csv_ops[1].kind == INCOME and csv_ops[1].amount == 1000, "csv: доход по плюсу")
    check(csv_ops[0].note == "СберТройка", "csv: заметка")
    check(csv_ops[0].fingerprint != csv_ops[1].fingerprint, "csv: разные отпечатки")

    ofx_bytes = """<?xml version="1.0" encoding="UTF-8"?>
<?OFX OFXHEADER="200" SECURITY="NONE" VERSION="102"?>
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>
<STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20261006</DTPOSTED><TRNAMT>-43.00</TRNAMT><FITID>ofx001</FITID><NAME>СберТройка</NAME><MEMO>Местный транспорт</MEMO></STMTTRN>
<STMTTRN><TRNTYPE>CREDIT</TRNTYPE><DTPOSTED>20261001</DTPOSTED><TRNAMT>1000.00</TRNAMT><FITID>ofx002</FITID><NAME>Юрий П.</NAME><MEMO>Переводы</MEMO></STMTTRN>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>""".encode("utf-8")
    ofx_ops = importers.parse_bytes(ofx_bytes)
    check(len(ofx_ops) == 2, "ofx: разобраны обе операции")
    check(ofx_ops[0].txn_date == date(2026, 10, 6), "ofx: дата")
    check(ofx_ops[0].kind == EXPENSE and ofx_ops[0].category_name == "Местный транспорт", "ofx: расход и MEMO")
    check(ofx_ops[1].fingerprint == "ofx:ofx002", "ofx: отпечаток по FITID")

    import io
    import zipfile

    def make_xlsx() -> bytes:
        serial = lambda d: (d - date(1899, 12, 30)).days
        sheet = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            '<row r="1">'
            '<c r="A1" t="inlineStr"><is><t>Дата операции</t></is></c>'
            '<c r="B1" t="inlineStr"><is><t>Сумма в валюте счёта</t></is></c>'
            '<c r="C1" t="inlineStr"><is><t>Категория по-умолчанию</t></is></c>'
            '<c r="D1" t="inlineStr"><is><t>Ваша категория</t></is></c>'
            '<c r="E1" t="inlineStr"><is><t>Описание</t></is></c>'
            "</row>"
            f'<row r="2"><c r="A2"><v>{serial(date(2026,10,6))}</v></c>'
            '<c r="B2"><v>-43</v></c>'
            '<c r="C2" t="inlineStr"><is><t>Такси</t></is></c>'
            '<c r="E2" t="inlineStr"><is><t>Яндекс Такси</t></is></c></row>'
            f'<row r="3"><c r="A3"><v>{serial(date(2026,10,6))}</v></c>'
            '<c r="B3"><v>1000</v></c>'
            '<c r="C3" t="inlineStr"><is><t>Зарплата</t></is></c>'
            '<c r="E3" t="inlineStr"><is><t>Аванс</t></is></c></row>'
            "</sheetData></worksheet>"
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                "</Types>",
            )
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Sheet1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr("xl/worksheets/sheet1.xml", sheet)
        return buffer.getvalue()

    xlsx_ops = importers.parse_bytes(make_xlsx())
    check(len(xlsx_ops) == 2, "xlsx: разобраны обе строки")
    check(xlsx_ops[0].kind == EXPENSE and xlsx_ops[0].note == "Яндекс Такси", "xlsx: расход из числа")
    check(xlsx_ops[1].kind == INCOME and xlsx_ops[1].category_name == "Зарплата", "xlsx: доход")
    check(xlsx_ops[0].txn_date == date(2026, 10, 6), "xlsx: дата из серийного числа")

    import_service = build_service(":memory:")
    resolver = lambda name, kind: import_service.get_or_create_category(name, kind)
    first = import_service.import_operations(csv_ops, resolver)
    check(first.imported == 2, "импорт операций")
    second = import_service.import_operations(csv_ops, resolver)
    check(second.imported == 0 and second.skipped_duplicates == 2, "повторный импорт пропускает дубликаты")
    third = import_service.import_operations(csv_ops, resolver, skip_existing=False)
    check(third.imported == 2, "импорт с добавлением всех")

    same_name_expense = import_service.import_category("Одно имя", EXPENSE, "create")
    check(
        same_name_expense == import_service.import_category("Одно имя", EXPENSE, "create"),
        "создание повторного имени с тем же типом не дублирует",
    )
    check(
        len(import_service.categories(EXPENSE)) > 0,
        "после импорта есть категории расходов",
    )
    fallback_id = import_service.import_category("Несуществующая", INCOME, "fallback")
    fallback = import_service.categories()[0]
    check(
        any(c.id == fallback_id and c.name == "Прочее" and c.kind == INCOME
            for c in import_service.categories()),
        "не найденная категория уходит в «Прочее» нужного типа",
    )

    # --- третий тип операции: «Инвестировано» ---

    kind_service = build_service(":memory:")
    invest_id = kind_service.create_category("Пополнения", INVEST)
    kind_service.create_transaction(invest_id, 50000, date(2026, 10, 3), "пополнение")
    kind_service.create_transaction(
        kind_service.create_category("Зарплата2", INCOME), 10000, date(2026, 10, 1)
    )
    kind_summary = kind_service.month_summary(2026, 10)
    check(kind_summary.invested == 50000, "инвестиции показаны отдельно за месяц")
    check(
        kind_summary.income == 10000 and kind_summary.expense == 0,
        "инвестиции не попадают в доходы/расходы",
    )
    check(kind_summary.balance == 10000, "инвестиции не влияют на баланс")
    check(kind_service.invested_total() == 50000, "внесено в пул за всё время")
    kind_breakdown = kind_service.month_breakdown(2026, 10)
    check(
        all(k != INVEST for _n, k, _v in kind_breakdown),
        "инвестиции не попадают в разбивку статистики",
    )
    check(
        len(kind_service.transactions(kind=INVEST)) == 1,
        "фильтр операций по типу «инвестиции»",
    )
    invest_cats = kind_service.categories(INVEST)
    check(
        bool(invest_cats) and all(c.kind == INVEST for c in invest_cats)
        and any(c.name == "Пополнения" for c in invest_cats),
        "категории фильтруются по типу «инвестиции»",
    )
    try:
        kind_service.create_category("Плохой", "unknown")
        raise AssertionError("неизвестный тип категории должен отклоняться")
    except ValidationError:
        checks += 1

    # --- инвестиции и имущество ---

    import sqlite3

    from finance import db as db_mod
    from finance import quotes as quotes_mod
    from finance.models import (
        BUY,
        MARKET_MOEX,
        MARKET_PHYSICAL,
        MARKET_US,
        SELL,
        category_for_moex,
        category_for_yahoo,
    )
    from finance.services import AutoRefreshSettings, PayoutFetch

    # обратная совместимость: старая БД получает новые таблицы и тип «invest»
    legacy = sqlite3.connect(":memory:")
    legacy.row_factory = sqlite3.Row
    legacy.executescript(
        "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT, "
        "kind TEXT CHECK (kind IN ('income', 'expense')));"
        "CREATE TABLE transactions (id INTEGER PRIMARY KEY, category_id INTEGER, "
        "amount REAL, txn_date TEXT);"
        "INSERT INTO categories (name, kind) VALUES ('Зарплата', 'income');"
        "INSERT INTO transactions (category_id, amount, txn_date) "
        "VALUES (1, 500, '2026-01-01');"
    )
    db_mod.init_schema(legacy)
    tables = {
        r[0] for r in legacy.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    check(
        {"assets", "trades", "prices", "settings"} <= tables,
        "миграция добавляет таблицы инвестиций к старой базе",
    )
    check(
        legacy.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id = 1"
        ).fetchone()[0] == 1,
        "миграция сохраняет старые операции",
    )
    legacy.execute(
        "INSERT INTO categories (name, kind) VALUES ('Инвестиции', 'invest')"
    )
    check(
        legacy.execute(
            "SELECT COUNT(*) FROM categories WHERE kind = 'invest'"
        ).fetchone()[0] == 1,
        "миграция разрешает тип «invest» в старой базе",
    )
    legacy.close()

    inv = build_service(":memory:")
    sber = inv.create_asset(
        "Сбербанк", MARKET_MOEX, ticker="sber", currency="RUB",
        quantity=10, price=250, trade_date=date(2026, 1, 10),
    )
    asset = inv.asset(sber)
    check(asset.ticker == "SBER" and asset.quantity == 10, "создан биржевой актив")
    check(asset.invested == 2500 and asset.avg_price == 250, "вложения и средняя цена")
    check(asset.current_price == 250 and asset.market_value == 2500, "оценка без цены")

    inv.add_trade(sber, BUY, 5, 300, date(2026, 2, 1))
    asset = inv.asset(sber)
    check(asset.quantity == 15, "покупка увеличивает количество")
    check(abs(asset.avg_price - (2500 + 1500) / 15) < 1e-9, "средневзвешенная цена")

    inv.add_trade(sber, SELL, 5, 400, date(2026, 3, 1))
    asset = inv.asset(sber)
    check(asset.quantity == 10, "продажа уменьшает количество")
    check(
        abs(asset.realized - (5 * 400 - 5 * asset.avg_price)) < 1e-6,
        "реализованный результат",
    )
    try:
        inv.add_trade(sber, SELL, 100, 400, date(2026, 3, 2))
        raise AssertionError("продажа сверх позиции должна отклоняться")
    except ValidationError:
        checks += 1

    inv.set_manual_price(sber, 350, date(2026, 4, 1))
    asset = inv.asset(sber)
    check(asset.last_price == 350 and asset.market_value == 3500, "ручная оценка")
    check(
        abs(asset.profit - (3500 - 10 * asset.avg_price)) < 1e-6,
        "нереализованная прибыль",
    )

    flat = inv.create_asset(
        "Квартира", MARKET_PHYSICAL, currency="RUB", category="Недвижимость",
        depreciation_rate=2.0, quantity=1, price=5_000_000,
        trade_date=date(2010, 1, 1),
    )
    flat_asset = inv.asset(flat)
    check(flat_asset.is_physical, "создано имущество")
    check(flat_asset.category == "Недвижимость", "категория имущества")
    check(flat_asset.years_held > 4, "срок владения посчитан")
    check(
        flat_asset.residual_value is not None
        and flat_asset.residual_value < flat_asset.cost_basis,
        "износ уменьшает остаточную стоимость",
    )

    try:
        inv.create_asset("Дубль", MARKET_MOEX, ticker="SBER")
        raise AssertionError("дубликат тикера должен отклоняться")
    except ValidationError:
        checks += 1

    summary = inv.portfolio_summary()
    check(abs(summary.securities.value - 3500) < 1e-6, "сводка: биржевые")
    check(abs(summary.property.value - 5_000_000) < 1e-6, "сводка: имущество")
    check(
        abs(summary.total.value - summary.securities.value - summary.property.value) < 1e-6,
        "сводка: общий итог",
    )

    deposit = inv.create_asset(
        "Вклад", "manual", currency="RUB", category="Вклады",
        quantity=1, price=100_000,
    )
    check(inv.asset(deposit).category == "Вклады", "категория у ручного актива")

    # --- пул: внесено / вложено / свободно ---
    pool = inv.portfolio_summary()
    check(pool.contributed == 0, "без инвест-операций пул пуст")
    check(
        abs(pool.deployed - (2000 + 5_000_000 + 100_000)) < 1e-6,
        "вложено = покупки минус продажи",
    )
    invest_cat = inv.create_category("Пополнения", INVEST)
    inv.create_transaction(invest_cat, 6_000_000, date(2026, 1, 1), "взнос")
    pool = inv.portfolio_summary()
    check(pool.contributed == 6_000_000, "внесено из инвест-операций")
    check(
        abs(pool.free - (6_000_000 - pool.deployed)) < 1e-6,
        "свободно = внесено минус вложено",
    )
    check(
        bool(inv.transactions(kind=INVEST)),
        "инвест-операции доступны через фильтр",
    )

    # --- календарь выплат ---
    check(date(2026, 2, 28) == add_months(date(2026, 1, 31), 1), "add_months: конец месяца")

    dividend_id = inv.create_payout(
        sber, PAYOUT_DIVIDEND, date(2026, 7, 1), rate=25.0
    )
    payout = inv.payout(dividend_id)
    check(payout.asset_name and payout.rate == 25.0, "выплата создана")
    check(
        abs(inv.expected_payout_amount(payout) - 250.0) < 1e-6,
        "ожидаемая сумма = ставка × количество",
    )
    inv.add_trade(sber, BUY, 10, 100, date(2026, 4, 1))  # количество станет 20
    check(
        abs(inv.expected_payout_amount(inv.payout(dividend_id)) - 500.0) < 1e-6,
        "ожидаемая сумма пересчитывается при изменении позиции",
    )
    inv.mark_payout_received(dividend_id, 480.0, date(2026, 7, 2))
    received = inv.payout(dividend_id)
    check(
        received.status == PAYOUT_RECEIVED and received.amount == 480.0,
        "выплата отмечена полученной",
    )
    july = inv.month_summary(2026, 7)
    check(
        july.income == 0 and july.expense == 0 and july.invested == 0,
        "полученная выплата не попадает в доходы/расходы",
    )

    rule_id = inv.create_payout_rule(
        sber, PAYOUT_COUPON, 12.0, PERIOD_QUARTERLY, date(2026, 1, 15)
    )
    entries = inv.calendar_entries(
        date(2026, 1, 1), date(2026, 12, 31), asset_id=sber
    )
    coupon_dates = [e.date for e in entries if e.source == "rule"]
    check(
        coupon_dates == [
            date(2026, 1, 15), date(2026, 4, 15),
            date(2026, 7, 15), date(2026, 10, 15),
        ],
        "правило разворачивается в даты периода",
    )
    expected_coupon = next(e for e in entries if e.source == "rule")
    check(
        abs(expected_coupon.expected - 12.0 * 20) < 1e-6,
        "ожидаемый купон = ставка × количество",
    )
    check(
        any(e.is_received and abs(e.received - 480.0) < 1e-6 for e in entries),
        "полученная выплата попадает в календарь отдельно",
    )
    inv.create_payout(sber, PAYOUT_DIVIDEND, date(2026, 4, 15), rate=5.0)
    entries = inv.calendar_entries(
        date(2026, 4, 1), date(2026, 4, 30), asset_id=sber
    )
    check(
        sum(1 for e in entries if e.date == date(2026, 4, 15)) == 1,
        "явная выплата перекрывает вхождение правила",
    )
    inv.remove_payout_rule(rule_id)
    check(
        not any(
            e.rule_id == rule_id
            for e in inv.calendar_entries(date(2026, 1, 1), date(2026, 12, 31), asset_id=sber)
        ),
        "удаление правила убирает его выплаты",
    )
    try:
        inv.create_payout(9999, PAYOUT_DIVIDEND, date(2026, 8, 1), rate=1.0)
        raise AssertionError("выплата по несуществующему активу должна отклоняться")
    except ValidationError:
        checks += 1

    # --- офлайн-разбор источников цен (без сети) ---

    moex_json = (
        '{"marketdata":{"columns":["SECID","BOARDID","LAST"],'
        '"data":[["SBER","TQBR",284.71],["SBER","SPEQ",281.8]]}}'
    )
    check(quotes_mod.parse_moex(moex_json) == 284.71, "MOEX: цена с основной доски")

    yahoo_json = (
        '{"chart":{"result":[{"meta":{"currency":"USD",'
        '"regularMarketPrice":336.64}}]}}'
    )
    yahoo_price, yahoo_currency = quotes_mod.parse_yahoo(yahoo_json)
    check(
        yahoo_price == 336.64 and yahoo_currency == "USD",
        "Yahoo: цена и валюта",
    )

    cbr_json = (
        '{"Valute":{"USD":{"Nominal":1,"Value":84.9048},'
        '"EUR":{"Nominal":1,"Value":94.9745}}}'
    )
    rates = quotes_mod.parse_cbr(cbr_json)
    check(rates["USD"] == 84.9048 and rates["EUR"] == 94.9745, "ЦБ: курсы USD/EUR")

    def offline(_url):
        raise quotes_mod.QuoteError("нет сети")

    try:
        quotes_mod.fetch_quote(inv.asset(sber), opener=offline)
        raise AssertionError("офлайн должен давать QuoteError")
    except quotes_mod.QuoteError:
        checks += 1

    def fake_opener(url):
        if "moex" in url:
            return moex_json.encode()
        if "yahoo" in url:
            return yahoo_json.encode()
        return cbr_json.encode()

    apple = inv.create_asset(
        "Apple", MARKET_US, ticker="AAPL", currency="USD",
        quantity=2, price=300, trade_date=date(2026, 1, 1),
    )
    result = inv.refresh_prices(opener=fake_opener)
    check(result.updated == 2, "онлайн-обновление биржевых активов")
    check(inv.asset(sber).last_price == 284.71, "цена MOEX сохранена")
    check(inv.asset(apple).last_price == 336.64, "цена США сохранена")
    check(inv.rates().get("USD") == 84.9048, "курс ЦБ сохранён")

    history = inv.portfolio_history()
    check(bool(history), "история стоимости портфеля строится")

    offline_result = inv.refresh_prices(opener=offline)
    check(
        offline_result.updated == 0 and offline_result.failed,
        "офлайн-режим: обновление не ломается",
    )

    # --- офлайн-поиск бумаг для подсказок при добавлении актива ---

    moex_search_json = (
        '{"securities":{"columns":["secid","shortname","name","is_traded",'
        '"type","group","primary_boardid"],"data":['
        '["FIXSBER","Фиксинг","Фиксинг",1,"stock_index_pf","stock_index",null],'
        '["SBER","Сбербанк","Сбербанк России ПАО ао",1,"common_share","stock_shares","TQBR"],'
        '["SBERP","Сбербанк-п","Сбербанк ап",1,"preferred_share","stock_shares","TQBR"],'
        '["RU000A10DS74","Сбер Sb51R","Сбербанк ПАО 001Р",1,"exchange_bond","stock_bonds","TQCB"],'
        '["VTBR","ВТБ","ВТБ",0,"common_share","stock_shares","TQBR"]'
        ']}}'
    )
    found = quotes_mod.parse_moex_securities(moex_search_json)
    check(
        [m.ticker for m in found] == ["SBER", "SBERP", "RU000A10DS74"],
        "поиск MOEX: индексы и неторгуемые отфильтрованы",
    )
    check(
        found[0].category == "Акции" and found[0].currency == "RUB",
        "поиск MOEX: категория и валюта акции",
    )
    check(found[2].category == "Облигации", "поиск MOEX: облигация распознана")
    check("Сбербанк" in found[0].label, "подсказка содержит название")

    yahoo_search_json = (
        '{"quotes":['
        '{"symbol":"AAPL","shortname":"Apple Inc.","exchange":"NMS","quoteType":"EQUITY"},'
        '{"symbol":"VOO","shortname":"Vanguard S&P 500 ETF","exchange":"PCX","quoteType":"ETF"},'
        '{"symbol":"SAAPL=F","shortname":"Apple Futures","exchange":"CME","quoteType":"FUTURE"}'
        ']}'
    )
    found_us = quotes_mod.parse_yahoo_search(yahoo_search_json)
    check(
        [m.ticker for m in found_us] == ["AAPL", "VOO"],
        "поиск США: фьючерсы отфильтрованы",
    )
    check(
        found_us[0].category == "Акции" and found_us[1].category == "Фонды/ETF",
        "поиск США: категории распознаны",
    )
    check(found_us[0].currency == "USD", "поиск США: валюта USD")

    check(
        category_for_moex("exchange_bond", "stock_bonds") == "Облигации",
        "категория MOEX: облигация",
    )
    check(
        category_for_yahoo("MUTUALFUND") == "Фонды/ETF",
        "категория Yahoo: фонд",
    )

    def search_opener(url):
        if "iss.moex.com" in url:
            return moex_search_json.encode()
        if "yahoo" in url:
            return yahoo_search_json.encode()
        return b"{}"

    check(
        [m.ticker for m in quotes_mod.search_securities(
            MARKET_MOEX, "Sber", opener=search_opener
        )] == ["SBER", "SBERP", "RU000A10DS74"],
        "фасад поиска: MOEX",
    )
    check(
        [m.ticker for m in quotes_mod.search_securities(
            MARKET_US, "Apple", opener=search_opener
        )] == ["AAPL", "VOO"],
        "фасад поиска: США",
    )
    check(
        quotes_mod.search_securities(MARKET_PHYSICAL, "дом") == [],
        "поиск бумаг: имущество без подсказок",
    )

    # цена MOEX-облигации берётся с рынка bonds, если на shares её нет
    def bond_price_opener(url):
        if "/markets/bonds/" in url:
            return (
                '{"marketdata":{"columns":["SECID","BOARDID","LAST"],'
                '"data":[["RU000A10DS74","TQCB",100.86]]}}'
            ).encode()
        return b'{"marketdata":{"columns":["SECID","BOARDID","LAST"],"data":[]}}'

    bond_asset = inv.create_asset(
        "Облигация", MARKET_MOEX, ticker="RU000A10DS74", currency="RUB",
    )
    bond_quote = quotes_mod.fetch_quote(
        inv.asset(bond_asset), opener=bond_price_opener
    )
    check(bond_quote.price == 100.86, "MOEX: цена облигации с рынка bonds")

    # --- офлайн-разбор графиков выплат (без сети) ---

    bond_json = (
        '{"coupons":{"columns":["SECID","coupondate","value"],"data":['
        '["SBER","2030-01-01",12.5],["SBER","2030-04-01",12.5],'
        '["SBER","2020-01-01",10.0]]}}'
    )
    coupons = quotes_mod.parse_bondization(bond_json)
    check(len(coupons) == 3, "MOEX: график купонов разобран")
    check(coupons[0][0] == date(2020, 1, 1), "MOEX: купоны отсортированы")

    yahoo_div_json = (
        '{"chart":{"result":[{"events":{"dividends":{'
        '"1704067200":{"amount":0.24,"date":1704067200},'
        '"1711929600":{"amount":0.25,"date":1711929600},'
        '"1719792000":{"amount":0.25,"date":1719792000},'
        '"1727740800":{"amount":0.25,"date":1727740800}}}}]}}'
    )
    divs = quotes_mod.parse_yahoo_dividends(yahoo_div_json)
    check(len(divs) == 4 and divs[-1][1] == 0.25, "Yahoo: дивиденды разобраны")

    smartlab_html = (
        "<table>"
        "<tr><th>Название</th><th>Тикер</th><th>Период</th>"
        "<th>Дивиденд руб</th><th>Дата закрытия реестра</th>"
        "<th>Выплата До</th></tr>"
        "<tr><td>Сбербанк</td><td>SBER</td><td>2030</td><td>25,50</td>"
        "<td>20.05.2030</td><td>10.06.2030</td></tr>"
        "</table>"
    )
    rows = quotes_mod.parse_smartlab_dividends(smartlab_html)
    check(
        len(rows) == 1 and rows[0]["ticker"] == "SBER"
        and abs(rows[0]["amount"] - 25.5) < 1e-9
        and rows[0]["pay_date"] == date(2030, 6, 10),
        "smart-lab: календарь дивидендов разобран",
    )

    projected = inv._project_dividends(divs)
    check(bool(projected), "прогноз дивидендов США строится из истории")

    def payout_opener(url):
        if "iss.moex.com" in url:
            return bond_json.encode()
        if "yahoo" in url:
            return yahoo_div_json.encode()
        if "smart-lab" in url:
            return smartlab_html.encode()
        return b"{}"

    fetched = inv.fetch_payouts(opener=payout_opener)
    check(
        any(p["kind"] == PAYOUT_COUPON and p["date"] == date(2030, 1, 1)
            for p in fetched.payouts),
        "онлайн: найден будущий купон",
    )
    check(
        any(p["source"] == "smartlab" for p in fetched.payouts),
        "онлайн: найден дивиденд smart-lab",
    )
    applied = inv.apply_payout_fetch(fetched)
    check(applied.updated >= 4, "онлайн-выплаты записаны в базу")
    coupon_rows = [
        p for p in inv.payouts(asset_id=sber)
        if p.kind == PAYOUT_COUPON and p.pay_date == date(2030, 1, 1)
    ]
    check(len(coupon_rows) == 1, "купон сохранён как ожидаемая выплата")
    check(
        abs(inv.expected_payout_amount(coupon_rows[0]) - 12.5 * 20) < 1e-6,
        "ожидаемая сумма купона = ставка × количество",
    )
    again = inv.sync_payouts(opener=payout_opener)
    check(again.updated == 0, "повторный синк не создаёт дубликатов")

    offline_fetch = inv.fetch_payouts(opener=offline)
    check(
        offline_fetch.failures and not offline_fetch.payouts,
        "онлайн-выплаты: офлайн не ломает приложение",
    )

    # --- прошедшие выплаты, кнопка «получить» и автонастройки ---

    check(
        abs(inv.holding_quantity_at(sber, date(2026, 1, 10)) - 10) < 1e-9,
        "holding_quantity_at: на дату первой покупки",
    )
    check(
        abs(inv.holding_quantity_at(sber, date(2026, 3, 15)) - 10) < 1e-9,
        "holding_quantity_at: после продажи",
    )
    check(
        abs(inv.holding_quantity_at(sber, date(2026, 4, 15)) - 20) < 1e-9,
        "holding_quantity_at: после докупки",
    )

    late = inv.create_asset(
        "Газпром", MARKET_MOEX, ticker="gazp", currency="RUB",
        quantity=10, price=100, trade_date=date(2026, 6, 1),
    )
    past_fetch = PayoutFetch(payouts=[
        {"asset_id": sber, "kind": PAYOUT_COUPON, "date": date(2026, 4, 15),
         "rate": 12.5, "source": "moex", "note": "тест: пропущенный купон"},
        {"asset_id": sber, "kind": PAYOUT_COUPON, "date": date(2023, 1, 1),
         "rate": 9.0, "source": "moex", "note": "слишком старая"},
        {"asset_id": late, "kind": PAYOUT_DIVIDEND, "date": date(2026, 5, 1),
         "rate": 7.0, "source": "smartlab", "note": "бумагу ещё не купили"},
    ])
    check(
        inv.apply_payout_fetch(past_fetch).updated == 0,
        "прошедшие выплаты не пишутся без include_past",
    )
    past_applied = inv.apply_payout_fetch(past_fetch, include_past=True)
    check(past_applied.updated == 1, "записана только удержанная прошедшая выплата")
    check(
        any(
            p.kind == PAYOUT_COUPON and p.pay_date == date(2026, 4, 15)
            for p in inv.payouts(asset_id=sber)
        ),
        "прошедшая выплата попала в календарь",
    )
    check(
        not any(p.asset_id == late for p in inv.payouts()),
        "выплата по бумаге, которой ещё не было, не пишется",
    )
    check(
        inv.apply_payout_fetch(past_fetch, include_past=True).updated == 0,
        "повторный синк прошедших не создаёт дубликатов",
    )

    due = inv.due_past_payouts(asset_id=sber)
    target_entry = next(
        e for e in due
        if e.date == date(2026, 4, 15) and e.kind == PAYOUT_COUPON
    )
    check(
        abs(target_entry.expected_at_date - 12.5 * 20) < 1e-6,
        "сумма прошедшей выплаты — по количеству на дату",
    )
    inv.receive_entry(
        target_entry, target_entry.expected_at_date, date(2026, 4, 16)
    )
    stored = inv.payout(target_entry.payout_id)
    check(
        stored.status == PAYOUT_RECEIVED
        and abs(stored.amount - 250.0) < 1e-6,
        "receive_entry отмечает выплату полученной",
    )
    check(
        not any(
            e.date == date(2026, 4, 15) and e.kind == PAYOUT_COUPON and e.is_due
            for e in inv.due_past_payouts(asset_id=sber)
        ),
        "отмеченная выплата больше не в списке пропущенных",
    )

    rule_rid = inv.create_payout_rule(
        sber, PAYOUT_COUPON, 3.0, PERIOD_QUARTERLY, date(2026, 1, 20)
    )
    rule_entries = inv.calendar_entries(
        date(2026, 1, 1), date(2026, 12, 31), asset_id=sber
    )
    rule_due = [e for e in rule_entries if e.rule_id == rule_rid and e.is_due]
    check(bool(rule_due), "прошедшее вхождение правила видно как пропущенное")
    inv.receive_entry(rule_due[0], 60.0, rule_due[0].date)
    after = inv.calendar_entries(
        date(2026, 1, 1), date(2026, 12, 31), asset_id=sber
    )
    check(
        any(
            e.payout_id is not None and e.is_received
            and e.date == rule_due[0].date
            for e in after
        ),
        "получение вхождения правила материализует выплату",
    )
    inv.remove_payout_rule(rule_rid)

    defaults = inv.auto_settings()
    check(
        defaults.price_enabled and defaults.price_minutes == 30,
        "автонастройки цен по умолчанию",
    )
    check(
        defaults.payout_enabled and defaults.payout_hours == 24,
        "автонастройки выплат по умолчанию",
    )
    inv.save_auto_settings(AutoRefreshSettings(
        price_enabled=False, price_minutes=10,
        payout_enabled=True, payout_hours=6,
    ))
    saved = inv.auto_settings()
    check(
        not saved.price_enabled and saved.price_minutes == 10,
        "автонастройки цен сохраняются",
    )
    check(
        saved.payout_enabled and saved.payout_hours == 6,
        "автонастройки выплат сохраняются",
    )
    inv.save_auto_settings(AutoRefreshSettings(price_minutes=1, payout_hours=0))
    clamped = inv.auto_settings()
    check(
        clamped.price_minutes == 5 and clamped.payout_hours == 1,
        "интервалы ограничены снизу",
    )
    inv.mark_synced("prices_updated_at")
    check(
        inv.last_sync("prices_updated_at") is not None,
        "метка синхронизации сохраняется",
    )

    print(f"selftest: OK ({checks} проверок)")
    return 0

def smoke() -> int:
    from finance.db import connect
    from finance.repository import Repository
    from finance.services import FinanceService
    from finance.ui.app import App

    tmp_dir = Path(tempfile.mkdtemp(prefix="finance_smoke_"))
    conn = connect(tmp_dir / "smoke.db")
    service = FinanceService(Repository(conn))
    app = App(service)
    app.after(1500, app.destroy)
    app.mainloop()
    print("smoke: OK (окно построено и закрыто)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Учёт личных финансов (tkinter + SQLite)")
    parser.add_argument("--db", help="путь к файлу базы данных (по умолчанию finance.db)")
    parser.add_argument("--selftest", action="store_true", help="проверка логики без интерфейса")
    parser.add_argument("--smoke", action="store_true", help="быстрая проверка интерфейса")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.smoke:
        return smoke()

    from finance.ui.app import App

    app = App(build_service(args.db))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
