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


from finance.selftest import selftest


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
