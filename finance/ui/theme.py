"""Единая тема оформления интерфейса (плоский стиль, акцентный синий)."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

CARD = "#FFFFFF"
BORDER = "#E5E7EB"
STRIP = "#F3F4F6"
BUTTON_BG = "#F3F4F6"
BUTTON_ACTIVE = "#E5E7EB"
TEXT = "#111827"
MUTED = "#6B7280"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
SUCCESS = "#16A34A"
DANGER = "#DC2626"
ROW_ALT = "#F9FAFB"
SELECT_BG = "#DBEAFE"
SELECT_FG = "#1E3A8A"
TOOLTIP_BG = "#1F2937"
TOOLTIP_FG = "#F9FAFB"

CHIP = {
    "income": ("#ECFDF5", "#047857"),
    "expense": ("#FEF2F2", "#B91C1C"),
    "balance": ("#EFF6FF", "#1D4ED8"),
}


def font_family() -> str:
    families = set(tkfont.families())
    for candidate in ("SF Pro Text", "Helvetica Neue", "Helvetica", "Arial"):
        if candidate in families:
            return candidate
    return "TkDefaultFont"


def make_font(size: int, weight: str = "normal") -> tkfont.Font:
    return tkfont.Font(family=font_family(), size=size, weight=weight)


def apply_theme(root: tk.Misc) -> ttk.Style:
    base = make_font(13)
    small = make_font(11)
    small_bold = make_font(11, "bold")
    bold = make_font(13, "bold")
    title = make_font(18, "bold")
    card_title = make_font(12, "bold")
    stat_value = make_font(20, "bold")

    root.configure(bg=CARD)
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=CARD, foreground=TEXT, font=base)
    style.configure("TFrame", background=CARD)
    style.configure("Border.TFrame", background=BORDER)
    style.configure("Strip.TFrame", background=STRIP)

    style.configure("TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=small)
    style.configure("CardTitle.TLabel", background=CARD, foreground=MUTED, font=card_title)
    style.configure("Title.TLabel", background=CARD, foreground=TEXT, font=title)
    style.configure("Value.TLabel", background=CARD, foreground=TEXT, font=bold)
    style.configure("StatLabel.TLabel", background=CARD, foreground=MUTED, font=small)
    style.configure("StatValue.TLabel", background=CARD, foreground=TEXT, font=stat_value)
    style.configure("StatIncome.TLabel", background=CARD, foreground=SUCCESS, font=stat_value)
    style.configure("StatExpense.TLabel", background=CARD, foreground=DANGER, font=stat_value)
    style.configure("StatBalance.TLabel", background=CARD, foreground=ACCENT, font=stat_value)
    style.configure("Success.TLabel", background=CARD, foreground=SUCCESS, font=bold)
    style.configure("Danger.TLabel", background=CARD, foreground=DANGER, font=bold)
    style.configure("Accent.TLabel", background=CARD, foreground=ACCENT, font=bold)

    style.configure(
        "TButton",
        background=BUTTON_BG, foreground=TEXT,
        borderwidth=0, relief="flat", padding=(14, 8), font=base,
    )
    style.map(
        "TButton",
        background=[("active", BUTTON_ACTIVE), ("pressed", "#D1D5DB")],
        foreground=[("active", TEXT)],
    )
    style.configure(
        "Accent.TButton",
        background=ACCENT, foreground="white",
        borderwidth=0, relief="flat", padding=(16, 9), font=bold,
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)],
        foreground=[("active", "white")],
    )
    style.configure(
        "Danger.TButton",
        background="#FEF2F2", foreground=DANGER,
        borderwidth=0, relief="flat", padding=(14, 8), font=base,
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#FEE2E2"), ("pressed", "#FECACA")],
        foreground=[("active", DANGER)],
    )

    style.configure(
        "TEntry",
        fieldbackground=CARD, foreground=TEXT, insertcolor=TEXT,
        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
        borderwidth=1, relief="solid", padding=(8, 7),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
        fieldbackground=[("disabled", STRIP)],
    )

    style.configure(
        "TCombobox",
        fieldbackground=CARD, background=CARD, foreground=TEXT,
        arrowcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER,
        darkcolor=BORDER, borderwidth=1, relief="solid", padding=(8, 7),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", CARD)],
        foreground=[("readonly", TEXT)],
        arrowcolor=[("active", ACCENT)],
        bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
        background=[("active", BUTTON_BG)],
    )

    style.configure("TRadiobutton", background=CARD, foreground=TEXT, padding=(0, 3))
    style.map(
        "TRadiobutton",
        foreground=[("active", ACCENT)],
        background=[("active", CARD)],
    )
    style.configure("TCheckbutton", background=CARD, foreground=TEXT, padding=(0, 3))

    style.configure(
        "TNotebook", background=STRIP, borderwidth=0, tabmargins=(0, 0, 0, 0)
    )
    style.configure(
        "TNotebook.Tab",
        background="#E8EAF2", foreground=MUTED, borderwidth=0,
        padding=(20, 11), font=base,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", CARD), ("active", "#DDE1EC")],
        foreground=[("selected", ACCENT), ("active", TEXT)],
    )
    try:
        style.map("TNotebook.Tab", font=[("selected", bold)])
    except tk.TclError:
        pass

    style.configure(
        "Treeview",
        background=CARD, foreground=TEXT, fieldbackground=CARD,
        borderwidth=0, rowheight=28, font=base,
    )
    style.map(
        "Treeview",
        background=[("selected", SELECT_BG)],
        foreground=[("selected", SELECT_FG)],
    )
    style.configure(
        "Treeview.Heading",
        background=STRIP, foreground=MUTED, borderwidth=0, relief="flat",
        font=small_bold, padding=(8, 9),
    )
    style.map("Treeview.Heading", background=[("active", BUTTON_ACTIVE)])

    style.configure(
        "Horizontal.TProgressbar",
        background=ACCENT, troughcolor=BORDER, borderwidth=0, thickness=8,
    )
    style.configure(
        "success.Horizontal.TProgressbar", background=SUCCESS, troughcolor=BORDER,
        borderwidth=0, thickness=8,
    )
    style.configure(
        "danger.Horizontal.TProgressbar", background=DANGER, troughcolor=BORDER,
        borderwidth=0, thickness=8,
    )

    style.configure("TLabelframe", background=CARD, borderwidth=0, relief="flat")
    style.configure("TLabelframe.Label", background=CARD, foreground=MUTED, font=small_bold)

    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", SELECT_FG)
    return style
