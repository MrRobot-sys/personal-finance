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
        ValidationError,
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
    check(len(categories) == 9, "должны загрузиться стартовые категории")
    check(
        sum(1 for c in categories if c.kind == INCOME) == 3, "3 категории доходов"
    )
    check(
        sum(1 for c in categories if c.kind == EXPENSE) == 6, "6 категорий расходов"
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
