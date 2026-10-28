"""Главное окно приложения."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from ..models import MONTH_NAMES, format_amount
from ..services import FinanceService
from .widgets import theme
from .tabs.categories_tab import CategoriesTab
from .dialogs import SettingsDialog
from .tabs.investments_tab import InvestmentsTab
from .tabs.stats_tab import StatsTab
from .tabs.transactions_tab import TransactionsTab
from .widgets import add_divider


class App(tk.Tk):
    def __init__(self, service: FinanceService):
        super().__init__()
        self.service = service
        self.title("Учёт личных финансов")
        self.geometry("1100x720")
        self.minsize(940, 640)

        theme.load_theme(self.service.repo)
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
        self.invest_var = tk.StringVar(value=format_amount(0))
        self._chip(chips, "Инвестировано", self.invest_var, "invest").pack(
            side="right", padx=(10, 0)
        )
        self._chip(chips, "Баланс", self.balance_var, "balance").pack(
            side="right", padx=(10, 0)
        )
        self._chip(chips, "Расходы", self.expense_var, "expense").pack(
            side="right", padx=(10, 0)
        )
        self._chip(chips, "Доходы", self.income_var, "income").pack(side="right")
        add_divider(self)

    def _chip(self, parent, caption: str, variable: tk.StringVar, kind: str) -> tk.Frame:
        bg, fg = theme.chip(kind)
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
        file_menu.add_command(label="Настройки…", command=self._open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self._about)
        menubar.add_cascade(label="Справка", menu=help_menu)
        self.config(menu=menubar)
        self.bind("<Control-r>", lambda _e: self.refresh_all())
        self.bind("<Control-n>", self._new_transaction)
        self.bind("<Control-i>", self._import_operations)
        self.bind("<F5>", self._refresh_active_tab)

    def _build_body(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(
            fill="both", expand=True,
            padx=theme.SPACING["large"],
            pady=(theme.SPACING["large"], theme.SPACING["large"]),
        )

        self.transactions_tab = TransactionsTab(
            self.notebook, self.service, self.refresh_all
        )
        self.categories_tab = CategoriesTab(
            self.notebook, self.service, self.refresh_all
        )
        self.stats_tab = StatsTab(self.notebook, self.service, self.refresh_all)
        self.investments_tab = InvestmentsTab(
            self.notebook, self.service, self.refresh_all
        )

        self.notebook.add(self.transactions_tab, text="Операции")
        self.notebook.add(self.categories_tab, text="Категории")
        self.notebook.add(self.stats_tab, text="Статистика")
        self.notebook.add(self.investments_tab, text="Инвестиции")

        self._tab_list: tuple = (
            self.transactions_tab,
            self.categories_tab,
            self.stats_tab,
            self.investments_tab,
        )

    def refresh_all(self) -> None:
        self.transactions_tab.refresh()
        self.categories_tab.refresh()
        self.stats_tab.refresh()
        self.investments_tab.refresh()
        self._update_status()

    def _update_status(self) -> None:
        today = date.today()
        summary = self.service.month_summary(today.year, today.month)
        self.income_var.set(format_amount(summary.income))
        self.expense_var.set(format_amount(summary.expense))
        self.balance_var.set(format_amount(summary.balance))
        self.invest_var.set(format_amount(summary.invested))

    def _new_transaction(self, _event=None) -> None:
        """Ctrl+N — новая транзакция: тот же путь, что кнопка «Добавить»."""
        if self._modal_dialog_open():
            return
        self.transactions_tab.add_transaction()

    def _import_operations(self, _event=None) -> None:
        """Ctrl+I — импорт выписок: тот же путь, что кнопка «Импорт…»."""
        if self._modal_dialog_open():
            return
        self.transactions_tab.import_transactions()

    def _refresh_active_tab(self, _event=None) -> None:
        """F5 — обновить данные активного таба."""
        tab = self._active_tab()
        if tab is not None and hasattr(tab, "refresh"):
            tab.refresh()
        else:
            self.refresh_all()

    def _active_tab(self):
        """Вкладка, выбранная в текущий момент."""
        selected = self.notebook.select()
        if not selected:
            return None
        selected_path = str(selected)
        for tab in self._tab_list:
            if str(tab) == selected_path:
                return tab
        return None

    def _modal_dialog_open(self) -> bool:
        """Наличие открытого модального диалога поверх главного окна."""
        return self._has_modal(self)

    def _has_modal(self, widget) -> bool:
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_ismapped():
                return True
            if self._has_modal(child):
                return True
        return False

    def _open_settings(self) -> None:
        # Диалог возвращает и настройки автообновления, и выбранную тему,
        # поэтому экземпляр создаётся явно, а не через run_dialog.
        dialog = SettingsDialog(
            self,
            settings=self.service.auto_settings(),
            theme_name=theme.current_theme(),
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.service.save_auto_settings(dialog.result)
        if dialog.theme_name != theme.current_theme():
            theme.save_theme(self.service.repo, dialog.theme_name)
            messagebox.showinfo(
                "Тема",
                "Тема изменится после перезапуска приложения.",
                parent=self,
            )
        self.investments_tab.reschedule_auto()

    def _about(self) -> None:
        messagebox.showinfo(
            "О программе",
            "Учёт личных финансов\n\n"
            "Категории доходов и расходов, операции,\n"
            "планы по категориям и статистика. Хранение — SQLite.\n\n"
            "Вкладка «Инвестиции»: портфель биржевых активов\n"
            "(MOEX, США) и имущества. Цены можно обновлять онлайн,\n"
            "при отсутствии сети используются сохранённые оценки.",
            parent=self,
        )
