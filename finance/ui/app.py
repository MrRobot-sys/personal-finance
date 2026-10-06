"""Главное окно приложения."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from ..models import MONTH_NAMES, format_amount
from ..services import FinanceService
from . import theme
from .categories_tab import CategoriesTab
from .stats_tab import StatsTab
from .transactions_tab import TransactionsTab
from .widgets import add_divider


class App(tk.Tk):
    def __init__(self, service: FinanceService):
        super().__init__()
        self.service = service
        self.title("Учёт личных финансов")
        self.geometry("1100x720")
        self.minsize(940, 640)

        theme.apply_theme(self)
        self._build_header()
        self._build_menu()
        self._build_body()
        self.refresh_all()

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(18, 14, 18, 14))
        header.pack(fill="x")
        ttk.Label(header, text="Учёт личных финансов", style="Title.TLabel").pack(
            side="left"
        )

        chips = ttk.Frame(header)
        chips.pack(side="right")
        self.income_var = tk.StringVar(value=format_amount(0))
        self.expense_var = tk.StringVar(value=format_amount(0))
        self.balance_var = tk.StringVar(value=format_amount(0))
        self._chip(chips, "Баланс", self.balance_var, "balance").pack(
            side="right", padx=(10, 0)
        )
        self._chip(chips, "Расходы", self.expense_var, "expense").pack(
            side="right", padx=(10, 0)
        )
        self._chip(chips, "Доходы", self.income_var, "income").pack(side="right")
        add_divider(self)

    def _chip(self, parent, caption: str, variable: tk.StringVar, kind: str) -> tk.Frame:
        bg, fg = theme.CHIP[kind]
        box = tk.Frame(parent, bg=bg)
        tk.Label(
            box, text=caption, bg=bg, fg=theme.MUTED,
            font=theme.make_font(10),
        ).pack(anchor="e", padx=12, pady=(6, 0))
        tk.Label(
            box, textvariable=variable, bg=bg, fg=fg,
            font=theme.make_font(14, "bold"),
        ).pack(anchor="e", padx=12, pady=(0, 7))
        return box

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Обновить", command=self.refresh_all, accelerator="Ctrl+R")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self._about)
        menubar.add_cascade(label="Справка", menu=help_menu)
        self.config(menu=menubar)
        self.bind("<Control-r>", lambda _e: self.refresh_all())

    def _build_body(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(12, 14))

        self.transactions_tab = TransactionsTab(
            self.notebook, self.service, self.refresh_all
        )
        self.categories_tab = CategoriesTab(
            self.notebook, self.service, self.refresh_all
        )
        self.stats_tab = StatsTab(self.notebook, self.service, self.refresh_all)

        self.notebook.add(self.transactions_tab, text="Операции")
        self.notebook.add(self.categories_tab, text="Категории")
        self.notebook.add(self.stats_tab, text="Статистика")

    def refresh_all(self) -> None:
        self.transactions_tab.refresh()
        self.categories_tab.refresh()
        self.stats_tab.refresh()
        self._update_status()

    def _update_status(self) -> None:
        today = date.today()
        summary = self.service.month_summary(today.year, today.month)
        self.income_var.set(format_amount(summary.income))
        self.expense_var.set(format_amount(summary.expense))
        self.balance_var.set(format_amount(summary.balance))

    def _about(self) -> None:
        messagebox.showinfo(
            "О программе",
            "Учёт личных финансов\n\n"
            "Категории доходов и расходов, операции,\n"
            "планы по категориям и статистика. Хранение — SQLite.",
            parent=self,
        )
