"""Главное окно приложения."""
from __future__ import annotations

import sys
import tkinter as tk
from datetime import date
from pathlib import Path
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


class _Tooltip:
    """Всплывающая подсказка для кнопки в шапке окна.

    У ttk нет штатной подсказки, поэтому это отдельное безрамочное окно
    ``Toplevel``. Атрибут ``_is_tooltip`` помечает его для
    :meth:`App._has_modal`: подсказка не должна считаться модальным диалогом.
    """

    #: Задержка перед показом, мс: подсказка не мелькает при движении курсора.
    DELAY_MS = 400

    def __init__(self, widget: tk.Misc, text):
        self._widget = widget
        self._text = text
        self._win: tk.Toplevel | None = None
        self._label: tk.Label | None = None
        self._job: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        try:
            self._job = self._widget.after(self.DELAY_MS, self._show)
        except tk.TclError:
            self._job = None

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self._widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _show(self) -> None:
        self._job = None
        try:
            x = self._widget.winfo_rootx()
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        except tk.TclError:
            return
        text = self._text() if callable(self._text) else self._text
        if self._win is None:
            self._win = tk.Toplevel(self._widget)
            self._win._is_tooltip = True  # type: ignore[attr-defined]
            self._win.overrideredirect(True)
            self._win.attributes("-topmost", True)
            self._label = tk.Label(
                self._win,
                text="",
                background=theme.TOOLTIP_BG,
                foreground=theme.TOOLTIP_FG,
                font=theme.make_font(11),
                padx=10,
                pady=5,
            )
            self._label.pack()
        self._label.configure(text=text)
        self._win.geometry(f"+{x}+{y}")
        self._win.deiconify()
        self._win.lift()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._win is not None:
            try:
                self._win.withdraw()
            except tk.TclError:
                pass


class App(tk.Tk):
    def __init__(self, service: FinanceService):
        super().__init__()
        self.service = service
        self.title("Учёт личных финансов")
        self.geometry("1100x720")
        self.minsize(940, 640)

        theme.load_theme(self.service.repo)
        theme.apply_theme(self)
        self._icon_image = self._load_icon()
        self._build_header()
        self._build_menu()
        self._build_body()
        self.refresh_all()

    def _load_icon(self) -> tk.PhotoImage | None:
        """Загружает иконку приложения и устанавливает её окну.

        Путь зависит от способа запуска: из исходников — каталог
        проекта, из сборки PyInstaller onefile — каталог
        ``sys._MEIPASS``. Если файла нет, запуск продолжается без
        иконки. Ссылка на изображение сохраняется в атрибуте окна,
        иначе объект будет собран сборщиком мусора.
        """
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        else:
            base = Path(__file__).resolve().parents[2]
        path = base / "finance" / "ui" / "assets" / "icon.png"
        try:
            image = tk.PhotoImage(file=str(path))
            self.iconphoto(True, image)
        except (OSError, tk.TclError):
            return None
        return image

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(18, 14, 18, 14))
        header.pack(fill="x")
        ttk.Label(header, text="Учёт личных финансов", style="Title.TLabel").pack(
            side="left"
        )

        # Крайний правый край шапки: переключатель темы всегда на одном месте.
        self._theme_btn = ttk.Button(
            header, style="Theme.TButton", command=self._toggle_theme
        )
        self._theme_btn.pack(side="right", padx=(theme.SPACING["large"], 0))
        self._theme_tip = _Tooltip(self._theme_btn, self._theme_hint)
        self._update_theme_btn()

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

    def _next_theme(self) -> str:
        """Тема, которая включится по нажатию кнопки в шапке."""
        return theme.DARK if theme.current_theme() == theme.LIGHT else theme.LIGHT

    def _update_theme_btn(self) -> None:
        """Подпись кнопки: иконка и название темы, в которую переключимся."""
        target = self._next_theme()
        if target == theme.DARK:
            text = "🌙 Тёмная тема"
        else:
            text = "☀️ Светлая тема"
        self._theme_btn.configure(text=text)

    def _theme_hint(self) -> str:
        """Текст подсказки кнопки темы (с учётом текущей темы)."""
        if theme.current_theme() == theme.LIGHT:
            return "Сейчас светлая тема. Нажмите, чтобы включить тёмную."
        return "Сейчас тёмная тема. Нажмите, чтобы включить светлую."

    def _toggle_theme(self) -> None:
        """Переключить тему на противоположную и применить её сразу."""
        self._apply_theme_now(self._next_theme())

    def _apply_theme_now(self, theme_name: str) -> None:
        """Сделать тему активной, сохранить выбор и сразу пересобрать окно.

        tkinter запоминает цвета виджета при создании, поэтому смены активной
        палитры недостаточно: tk-виджеты с явным ``bg`` (чипы шапки) остались
        бы в прежних цветах. Выбрана пересборка содержимого окна, а не
        перезапуск процесса через ``os.exec``: пересборка дешевле, сохраняет
        положение окна и активную вкладку и не обрывает работу сервиса.
        """
        theme.save_theme(self.service.repo, theme_name)
        theme.apply_theme(self)
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        """Уничтожить и заново построить шапку, меню и вкладки под новую тему."""
        active_tab = self._selected_tab_index()
        geometry = self.geometry()
        # Меню — тоже дочерний виджет корня: снимаем его до уничтожения детей,
        # чтобы Tk не остался со ссылкой на удалённый объект.
        self.config(menu="")
        for child in self.winfo_children():
            # Вместе с дочерними виджетами уничтожаются и их Toplevel-потомки
            # (диалоги, подсказки), поэтому отдельный проход не нужен.
            child.destroy()
        self._build_header()
        self._build_menu()
        self._build_body()
        if active_tab is not None:
            self.notebook.select(active_tab)
        self.geometry(geometry)
        self.refresh_all()

    def _selected_tab_index(self) -> int | None:
        """Номер выбранной вкладки; ``None``, если вкладок ещё нет."""
        notebook = getattr(self, "notebook", None)
        if notebook is None or not notebook.tabs():
            return None
        try:
            return notebook.index(notebook.select())
        except tk.TclError:
            return None

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
            if getattr(child, "_is_tooltip", False):
                continue
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
            # Пересборка окна создаёт вкладку «Инвестиции» заново, и она сама
            # ставит таймеры автообновления по сохранённым настройкам.
            self._apply_theme_now(dialog.theme_name)
        else:
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
