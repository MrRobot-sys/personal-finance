"""Единая тема оформления интерфейса (плоский стиль, светлая и тёмная палитры).

Тема хранится в таблице ``settings`` по ключу :data:`SETTING_KEY` и читается
при старте приложения (:func:`load_theme`). Активная палитра выбирается
функцией :func:`set_theme`; цвета доступны по семантическим ролям — как
``theme.CARD``, ``theme.MUTED`` и т. п. Роли вычисляются динамически
(см. :func:`__getattr__`), поэтому обращение к ним всегда возвращает цвет
текущей палитры, а не значение, зафиксированное при импорте модуля.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

LIGHT = "light"
DARK = "dark"
DEFAULT = LIGHT
SETTING_KEY = "ui_theme"

# --- палитры ---------------------------------------------------------------

LIGHT_PALETTE: dict[str, str] = {
    "CARD": "#FFFFFF",
    "BORDER": "#E5E7EB",
    "STRIP": "#F3F4F6",
    "BUTTON_BG": "#F3F4F6",
    "BUTTON_ACTIVE": "#E5E7EB",
    "BUTTON_PRESSED": "#D1D5DB",
    "TEXT": "#111827",
    "MUTED": "#6B7280",
    "FAINT": "#9CA3AF",
    "HINT": "#808080",
    "ACCENT": "#2563EB",
    "ACCENT_HOVER": "#1D4ED8",
    "ON_ACCENT": "#FFFFFF",
    "SUCCESS": "#16A34A",
    "DANGER": "#DC2626",
    "INCOME_FG": "#047857",
    "EXPENSE_FG": "#B91C1C",
    "INVEST": "#6D28D9",
    "ROW_ALT": "#F9FAFB",
    "SELECT_BG": "#DBEAFE",
    "SELECT_FG": "#1E3A8A",
    "TOOLTIP_BG": "#1F2937",
    "TOOLTIP_FG": "#F9FAFB",
    "GRID": "#EDEFF4",
    "TAB_BG": "#E8EAF2",
    "TAB_ACTIVE": "#DDE1EC",
    "DANGER_SOFT": "#FEF2F2",
    "DANGER_SOFT_HOVER": "#FEE2E2",
    "DANGER_SOFT_PRESSED": "#FECACA",
}

DARK_PALETTE: dict[str, str] = {
    "CARD": "#1B1E24",
    "BORDER": "#313742",
    "STRIP": "#22262E",
    "BUTTON_BG": "#262B34",
    "BUTTON_ACTIVE": "#323946",
    "BUTTON_PRESSED": "#3C4453",
    "TEXT": "#E5E7EB",
    "MUTED": "#98A2B3",
    "FAINT": "#6B7280",
    "HINT": "#8B93A1",
    "ACCENT": "#3D7FE8",
    "ACCENT_HOVER": "#5A94F0",
    "ON_ACCENT": "#FFFFFF",
    "SUCCESS": "#34D399",
    "DANGER": "#F87171",
    "INCOME_FG": "#34D399",
    "EXPENSE_FG": "#F87171",
    "INVEST": "#A78BFA",
    "ROW_ALT": "#20242C",
    "SELECT_BG": "#2B3B55",
    "SELECT_FG": "#DCE7FA",
    "TOOLTIP_BG": "#2C323D",
    "TOOLTIP_FG": "#F3F4F6",
    "GRID": "#2A2F38",
    "TAB_BG": "#20242B",
    "TAB_ACTIVE": "#2A3039",
    "DANGER_SOFT": "#3A2226",
    "DANGER_SOFT_HOVER": "#4A2A2F",
    "DANGER_SOFT_PRESSED": "#5A3238",
}

PALETTES: dict[str, dict[str, str]] = {
    LIGHT: LIGHT_PALETTE,
    DARK: DARK_PALETTE,
}

# Пары (фон, текст) для чипов сводки в шапке окна.
CHIPS: dict[str, dict[str, tuple[str, str]]] = {
    LIGHT: {
        "income": ("#ECFDF5", "#047857"),
        "expense": ("#FEF2F2", "#B91C1C"),
        "balance": ("#EFF6FF", "#1D4ED8"),
        "invest": ("#F5F3FF", "#6D28D9"),
    },
    DARK: {
        "income": ("#12291F", "#4ADE80"),
        "expense": ("#311D20", "#FCA5A5"),
        "balance": ("#16233A", "#93C5FD"),
        "invest": ("#221C36", "#C4B5FD"),
    },
}

_active_theme = DEFAULT

# --- состояние темы --------------------------------------------------------


def current_theme() -> str:
    """Имя активной темы (``light`` или ``dark``)."""
    return _active_theme


def set_theme(name: str) -> str:
    """Сделать тему активной; возвращает её имя.

    Неизвестное имя игнорируется (остаётся текущая тема): настройка в базе
    может устареть или быть испорчена вручную.
    """
    global _active_theme
    if name in PALETTES:
        _active_theme = name
    return _active_theme


def palette(name: str | None = None) -> dict[str, str]:
    """Палитра темы ``name`` (по умолчанию — активной)."""
    return PALETTES.get(name or _active_theme, LIGHT_PALETTE)


def chip(kind: str) -> tuple[str, str]:
    """Пара (фон, текст) чипа сводки для роли ``kind``."""
    return CHIPS[_active_theme].get(kind, CHIPS[_active_theme]["balance"])


def load_theme(repo) -> str:
    """Прочитать тему из настроек и сделать её активной.

    :param repo: репозиторий с методами ``get_setting``/``set_setting``;
        связь с хранилищем передаётся снаружи, чтобы модуль темы оставался
        независимым от слоя данных.
    """
    return set_theme(repo.get_setting(SETTING_KEY, DEFAULT) or DEFAULT)


def save_theme(repo, name: str) -> str:
    """Сохранить тему в настройках и сделать её активной."""
    applied = set_theme(name)
    repo.set_setting(SETTING_KEY, applied)
    return applied


def __getattr__(name: str):
    """Семантические роли палитры как атрибуты модуля (``theme.CARD``)."""
    current = palette()
    if name in current:
        return current[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# --- шрифты и стили --------------------------------------------------------


def font_family() -> str:
    families = set(tkfont.families())
    for candidate in ("SF Pro Text", "Helvetica Neue", "Helvetica", "Arial"):
        if candidate in families:
            return candidate
    return "TkDefaultFont"


def make_font(size: int, weight: str = "normal") -> tkfont.Font:
    return tkfont.Font(family=font_family(), size=size, weight=weight)


def apply_theme(root: tk.Misc) -> ttk.Style:
    """Настроить ttk-стили и фон окна под активную палитру."""
    p = palette()
    base = make_font(13)
    small = make_font(11)
    small_bold = make_font(11, "bold")
    bold = make_font(13, "bold")
    title = make_font(18, "bold")
    card_title = make_font(12, "bold")
    stat_value = make_font(20, "bold")

    root.configure(bg=p["CARD"])
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=p["CARD"], foreground=p["TEXT"], font=base)
    style.configure("TFrame", background=p["CARD"])
    style.configure("Border.TFrame", background=p["BORDER"])
    style.configure("Strip.TFrame", background=p["STRIP"])

    style.configure("TLabel", background=p["CARD"], foreground=p["TEXT"])
    style.configure("Muted.TLabel", background=p["CARD"], foreground=p["MUTED"], font=small)
    style.configure("CardTitle.TLabel", background=p["CARD"], foreground=p["MUTED"], font=card_title)
    style.configure("Title.TLabel", background=p["CARD"], foreground=p["TEXT"], font=title)
    style.configure("Value.TLabel", background=p["CARD"], foreground=p["TEXT"], font=bold)
    style.configure("StatLabel.TLabel", background=p["CARD"], foreground=p["MUTED"], font=small)
    style.configure("StatValue.TLabel", background=p["CARD"], foreground=p["TEXT"], font=stat_value)
    style.configure("StatIncome.TLabel", background=p["CARD"], foreground=p["SUCCESS"], font=stat_value)
    style.configure("StatExpense.TLabel", background=p["CARD"], foreground=p["DANGER"], font=stat_value)
    style.configure("StatBalance.TLabel", background=p["CARD"], foreground=p["ACCENT"], font=stat_value)
    style.configure("Success.TLabel", background=p["CARD"], foreground=p["SUCCESS"], font=bold)
    style.configure("Danger.TLabel", background=p["CARD"], foreground=p["DANGER"], font=bold)
    style.configure("Accent.TLabel", background=p["CARD"], foreground=p["ACCENT"], font=bold)

    style.configure(
        "TButton",
        background=p["BUTTON_BG"], foreground=p["TEXT"],
        borderwidth=0, relief="flat", padding=(14, 8), font=base,
    )
    style.map(
        "TButton",
        background=[("active", p["BUTTON_ACTIVE"]), ("pressed", p["BUTTON_PRESSED"])],
        foreground=[("active", p["TEXT"])],
    )
    style.configure(
        "Accent.TButton",
        background=p["ACCENT"], foreground=p["ON_ACCENT"],
        borderwidth=0, relief="flat", padding=(16, 9), font=bold,
    )
    style.map(
        "Accent.TButton",
        background=[("active", p["ACCENT_HOVER"]), ("pressed", p["ACCENT_HOVER"])],
        foreground=[("active", p["ON_ACCENT"])],
    )
    style.configure(
        "Danger.TButton",
        background=p["DANGER_SOFT"], foreground=p["DANGER"],
        borderwidth=0, relief="flat", padding=(14, 8), font=base,
    )
    style.map(
        "Danger.TButton",
        background=[
            ("active", p["DANGER_SOFT_HOVER"]),
            ("pressed", p["DANGER_SOFT_PRESSED"]),
        ],
        foreground=[("active", p["DANGER"])],
    )

    style.configure(
        "Compact.TButton",
        background=p["ACCENT"], foreground=p["ON_ACCENT"],
        borderwidth=0, relief="flat", padding=(6, 1), font=small_bold,
    )
    style.map(
        "Compact.TButton",
        background=[("active", p["ACCENT_HOVER"]), ("pressed", p["ACCENT_HOVER"])],
        foreground=[("active", p["ON_ACCENT"])],
    )

    style.configure(
        "TEntry",
        fieldbackground=p["CARD"], foreground=p["TEXT"], insertcolor=p["TEXT"],
        bordercolor=p["BORDER"], lightcolor=p["BORDER"], darkcolor=p["BORDER"],
        borderwidth=1, relief="solid", padding=(8, 7),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", p["ACCENT"])], lightcolor=[("focus", p["ACCENT"])],
        darkcolor=[("focus", p["ACCENT"])],
        fieldbackground=[("disabled", p["STRIP"])],
    )

    style.configure(
        "TCombobox",
        fieldbackground=p["CARD"], background=p["CARD"], foreground=p["TEXT"],
        arrowcolor=p["TEXT"], bordercolor=p["BORDER"], lightcolor=p["BORDER"],
        darkcolor=p["BORDER"], borderwidth=1, relief="solid", padding=(8, 7),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", p["CARD"])],
        foreground=[("readonly", p["TEXT"])],
        arrowcolor=[("active", p["ACCENT"])],
        bordercolor=[("focus", p["ACCENT"])], lightcolor=[("focus", p["ACCENT"])],
        darkcolor=[("focus", p["ACCENT"])],
        background=[("active", p["BUTTON_BG"])],
    )

    style.configure("TRadiobutton", background=p["CARD"], foreground=p["TEXT"], padding=(0, 3))
    style.map(
        "TRadiobutton",
        foreground=[("active", p["ACCENT"])],
        background=[("active", p["CARD"])],
    )
    style.configure("TCheckbutton", background=p["CARD"], foreground=p["TEXT"], padding=(0, 3))
    style.map(
        "TCheckbutton",
        foreground=[("active", p["TEXT"])],
        background=[("active", p["CARD"])],
    )

    style.configure(
        "TScrollbar",
        background=p["BUTTON_ACTIVE"], troughcolor=p["STRIP"],
        bordercolor=p["BORDER"], arrowcolor=p["MUTED"],
        borderwidth=0, relief="flat",
    )
    style.map("TScrollbar", background=[("active", p["ACCENT"])])

    style.configure(
        "TNotebook", background=p["STRIP"], borderwidth=0, tabmargins=(0, 0, 0, 0)
    )
    style.configure(
        "TNotebook.Tab",
        background=p["TAB_BG"], foreground=p["MUTED"], borderwidth=0,
        padding=(20, 11), font=base,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", p["CARD"]), ("active", p["TAB_ACTIVE"])],
        foreground=[("selected", p["ACCENT"]), ("active", p["TEXT"])],
    )
    try:
        style.map("TNotebook.Tab", font=[("selected", bold)])
    except tk.TclError:
        pass

    style.configure(
        "Treeview",
        background=p["CARD"], foreground=p["TEXT"], fieldbackground=p["CARD"],
        borderwidth=0, rowheight=28, font=base,
    )
    style.map(
        "Treeview",
        background=[("selected", p["SELECT_BG"])],
        foreground=[("selected", p["SELECT_FG"])],
    )
    style.configure(
        "Treeview.Heading",
        background=p["STRIP"], foreground=p["MUTED"], borderwidth=0, relief="flat",
        font=small_bold, padding=(8, 9),
    )
    style.map("Treeview.Heading", background=[("active", p["BUTTON_ACTIVE"])])

    style.configure(
        "Horizontal.TProgressbar",
        background=p["ACCENT"], troughcolor=p["BORDER"], borderwidth=0, thickness=8,
    )
    style.configure(
        "success.Horizontal.TProgressbar", background=p["SUCCESS"], troughcolor=p["BORDER"],
        borderwidth=0, thickness=8,
    )
    style.configure(
        "danger.Horizontal.TProgressbar", background=p["DANGER"], troughcolor=p["BORDER"],
        borderwidth=0, thickness=8,
    )

    style.configure("TLabelframe", background=p["CARD"], borderwidth=0, relief="flat")
    style.configure("TLabelframe.Label", background=p["CARD"], foreground=p["MUTED"], font=small_bold)

    root.option_add("*TCombobox*Listbox.background", p["CARD"])
    root.option_add("*TCombobox*Listbox.foreground", p["TEXT"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["SELECT_BG"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["SELECT_FG"])
    return style
