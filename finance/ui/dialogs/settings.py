"""Диалог настроек."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...services import (
    DEFAULT_PAYOUT_HOURS,
    DEFAULT_PRICE_MINUTES,
    MIN_PAYOUT_HOURS,
    MIN_PRICE_MINUTES,
    AutoRefreshSettings,
)
from ..widgets import FormDialog, theme

THEME_LABELS = {
    theme.LIGHT: "Светлая",
    theme.DARK: "Тёмная",
}


class SettingsDialog(FormDialog):
    """Настройки автообновления цен, автопоиска выплат и темы оформления."""

    def __init__(
        self, parent, settings: AutoRefreshSettings, theme_name: str = theme.DEFAULT
    ):
        self._settings = settings
        self._theme_name = theme_name
        #: Тема, выбранная в диалоге; читается вызывающей стороной после закрытия.
        self.theme_name = theme_name
        super().__init__(parent, "Настройки", confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        s = self._settings
        self.price_enabled_var = tk.BooleanVar(value=s.price_enabled)
        self.price_minutes_var = tk.StringVar(value=str(s.price_minutes))
        self.payout_enabled_var = tk.BooleanVar(value=s.payout_enabled)
        self.payout_hours_var = tk.StringVar(value=str(s.payout_hours))

        ttk.Checkbutton(
            parent, text="Автообновление цен", variable=self.price_enabled_var
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(parent, text="Интервал, минут:").grid(
            row=1, column=0, sticky="w", pady=4, padx=(18, 0)
        )
        price_entry = ttk.Entry(parent, textvariable=self.price_minutes_var, width=8)
        price_entry.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(
            parent, text=f"не менее {MIN_PRICE_MINUTES}", style="Muted.TLabel"
        ).grid(row=1, column=2, sticky="w", padx=(8, 0))

        ttk.Checkbutton(
            parent, text="Автопоиск выплат", variable=self.payout_enabled_var
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 4))

        ttk.Label(parent, text="Интервал, часов:").grid(
            row=3, column=0, sticky="w", pady=4, padx=(18, 0)
        )
        ttk.Entry(parent, textvariable=self.payout_hours_var, width=8).grid(
            row=3, column=1, sticky="w", pady=4
        )
        ttk.Label(
            parent, text=f"не менее {MIN_PAYOUT_HOURS}", style="Muted.TLabel"
        ).grid(row=3, column=2, sticky="w", padx=(8, 0))

        ttk.Label(
            parent,
            text="При отсутствии сети обновление просто пропускается.",
            style="Muted.TLabel",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))

        ttk.Label(
            parent, text="Тема оформления", style="CardTitle.TLabel"
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(16, 4))
        self.theme_var = tk.StringVar(value=self._theme_name)
        theme_box = ttk.Frame(parent)
        theme_box.grid(row=6, column=0, columnspan=3, sticky="w")
        for name, title in THEME_LABELS.items():
            ttk.Radiobutton(
                theme_box, text=title, value=name, variable=self.theme_var
            ).pack(side="left", padx=(0, 16))
        ttk.Label(
            parent,
            text="Применится после перезапуска приложения.",
            style="Muted.TLabel",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 0))
        parent.columnconfigure(1, weight=1)

    def on_ok(self) -> None:
        try:
            minutes = int(self.price_minutes_var.get().strip())
            hours = int(self.payout_hours_var.get().strip())
        except ValueError:
            self.show_error("Интервалы должны быть целыми числами")
            return
        if minutes < MIN_PRICE_MINUTES:
            self.show_error(f"Интервал цен — не менее {MIN_PRICE_MINUTES} мин")
            return
        if hours < MIN_PAYOUT_HOURS:
            self.show_error(f"Интервал выплат — не менее {MIN_PAYOUT_HOURS} ч")
            return
        self.result = AutoRefreshSettings(
            price_enabled=bool(self.price_enabled_var.get()),
            price_minutes=minutes,
            payout_enabled=bool(self.payout_enabled_var.get()),
            payout_hours=hours,
        )
        self.theme_name = self.theme_var.get()
        self.destroy()
