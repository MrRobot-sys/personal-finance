"""Вкладка операций: список, фильтры, добавление/редактирование/удаление."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...models import (
    EXPENSE,
    INCOME,
    INVEST,
    KIND_LABELS,
    ValidationError,
    format_amount,
    format_date,
)
from ...services import ImportFormatError
from ..dialogs import TransactionDialog
from ..dialogs import CategoryMapDialog, ImportDialog
from ..widgets import PlaceholderEntry, TreeTable, make_card, row, run_dialog, theme

ALL_TYPES = "Все типы"
ALL_CATEGORIES = "Все категории"
TYPE_TO_KIND = {
    ALL_TYPES: None,
    "Доходы": INCOME,
    "Расходы": EXPENSE,
    "Инвестиции": INVEST,
}
KIND_TO_TYPE = {INCOME: "Доходы", EXPENSE: "Расходы", INVEST: "Инвестиции"}


class TransactionsTab(ttk.Frame):
    def __init__(self, master, service, on_change):
        super().__init__(master, padding=theme.SPACING["large"])
        self.service = service
        self.on_change = on_change
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self._build_filters()
        self._build_table()
        self._build_actions()

    def _build_filters(self) -> None:
        outer, bar = make_card(self, title="Фильтры")
        outer.grid(row=0, column=0, sticky="ew", pady=(0, theme.SPACING["large"]))

        ttk.Label(bar, text="Период с:").grid(row=0, column=0, sticky="w")
        self.date_from = PlaceholderEntry(bar, placeholder="ДД.ММ.ГГГГ", width=12)
        self.date_from.grid(
            row=0, column=1, padx=(theme.SPACING["small"], theme.SPACING["large"])
        )

        ttk.Label(bar, text="по:").grid(row=0, column=2, sticky="w")
        self.date_to = PlaceholderEntry(bar, placeholder="ДД.ММ.ГГГГ", width=12)
        self.date_to.grid(
            row=0, column=3, padx=(theme.SPACING["small"], theme.SPACING["large"])
        )

        ttk.Label(bar, text="Тип:").grid(row=0, column=4, sticky="w")
        self.kind_combo = ttk.Combobox(
            bar, values=list(TYPE_TO_KIND), state="readonly", width=11
        )
        self.kind_combo.set(ALL_TYPES)
        self.kind_combo.grid(
            row=0, column=5, padx=(theme.SPACING["small"], theme.SPACING["large"])
        )
        self.kind_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply())

        ttk.Label(bar, text="Категория:").grid(row=0, column=6, sticky="w")
        self.category_combo = ttk.Combobox(bar, state="readonly", width=17)
        self.category_combo.grid(
            row=0, column=7, padx=(theme.SPACING["small"], theme.SPACING["large"])
        )
        self.category_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply())

        ttk.Label(bar, text="Поиск:").grid(row=0, column=8, sticky="w")
        self.search_entry = ttk.Entry(bar, width=16)
        self.search_entry.grid(
            row=0, column=9, padx=(theme.SPACING["small"], theme.SPACING["large"])
        )
        self.search_entry.bind("<Return>", lambda _e: self._apply())

        ttk.Button(
            bar, text="Применить", command=self._apply
        ).grid(row=0, column=10, padx=theme.SPACING["small"])
        ttk.Button(
            bar, text="Сбросить", command=self._reset
        ).grid(row=0, column=11, padx=(theme.SPACING["small"], 0))

    def _build_table(self) -> None:
        outer, content = make_card(self, padding=theme.CARD_PADDING_COMPACT)
        outer.grid(row=1, column=0, sticky="nsew")
        self.empty_var = tk.StringVar(value="")
        self.empty_label = ttk.Label(
            content, textvariable=self.empty_var, style="Muted.TLabel"
        )
        self.empty_label.pack(anchor="w", pady=theme.SPACING["large"])
        self.table = TreeTable(
            content,
            columns=[
                ("date", "Дата", 95, "center", False),
                ("kind", "Тип", 85, "center", False),
                ("category", "Категория", 190, "w", True),
                ("amount", "Сумма", 120, "e", True),
                ("note", "Заметка", 260, "w", True),
            ],
            height=11,
            on_double_click=self._edit,
        )
        self.table.frame.pack(fill="both", expand=True)

    def _build_actions(self) -> None:
        bottom = ttk.Frame(self)
        bottom.grid(row=2, column=0, sticky="ew", pady=(theme.SPACING["large"], 0))

        ttk.Button(
            bottom, text="Добавить", style="Accent.TButton", command=self._add
        ).pack(side="left")
        ttk.Button(bottom, text="Изменить", command=self._edit).pack(
            side="left", padx=theme.SPACING["medium"]
        )
        ttk.Button(bottom, text="Удалить", command=self._delete).pack(side="left")
        ttk.Button(bottom, text="Импорт…", command=self._import).pack(
            side="left", padx=(theme.SPACING["large"], 0)
        )

        self.totals_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.totals_var, style="Value.TLabel").pack(
            side="right"
        )

    def _selected_category_id(self) -> int | None:
        name = self.category_combo.get()
        if not name or name == ALL_CATEGORIES:
            return None
        for category in self.service.categories():
            if category.name == name:
                return category.id
        return None

    def _filters(self) -> dict:
        from ...models import parse_date

        date_from = date_to = None
        raw_from, raw_to = self.date_from.get(), self.date_to.get()
        if raw_from.strip():
            date_from = parse_date(raw_from)
        if raw_to.strip():
            date_to = parse_date(raw_to)
        return {
            "kind": TYPE_TO_KIND.get(self.kind_combo.get()),
            "category_id": self._selected_category_id(),
            "date_from": date_from,
            "date_to": date_to,
            "text": self.search_entry.get(),
        }

    def refresh(self) -> None:
        current = self.category_combo.get()
        names = [ALL_CATEGORIES] + [c.name for c in self.service.categories()]
        self.category_combo.configure(values=names)
        self.category_combo.set(current if current in names else ALL_CATEGORIES)
        self._apply()

    def _apply(self) -> None:
        try:
            filters = self._filters()
        except ValidationError as exc:
            messagebox.showwarning("Фильтры", str(exc), parent=self)
            return
        transactions = self.service.transactions(**filters)
        rows = []
        for t in transactions:
            rows.append(
                row(
                    t.id,
                    [
                        format_date(t.txn_date),
                        KIND_LABELS[t.kind],
                        t.category_name,
                        format_amount(t.amount),
                        t.note,
                    ],
                    tags=(t.kind,),
                    sort=[t.txn_date.toordinal(), t.kind, t.category_name, t.amount, t.note],
                )
            )
        self.table.set_rows(rows)
        if rows:
            self.table.frame.pack(fill="both", expand=True)
            self.empty_label.pack_forget()
        else:
            self.table.frame.pack_forget()
            self.empty_label.pack(anchor="w", pady=theme.SPACING["large"])
        income, expense = self.service.filtered_totals(transactions)
        invested = sum(t.amount for t in transactions if t.kind == INVEST)
        text = (
            f"Доходы: {format_amount(income)}   ·   Расходы: {format_amount(expense)}"
            f"   ·   Баланс: {format_amount(income - expense)}"
        )
        if invested:
            text += f"   ·   Инвестировано: {format_amount(invested)}"
        self.totals_var.set(text)

    def _reset(self) -> None:
        self.date_from.show_placeholder()
        self.date_to.show_placeholder()
        self.kind_combo.set(ALL_TYPES)
        self.category_combo.set(ALL_CATEGORIES)
        self.search_entry.delete(0, tk.END)
        self._apply()

    def _add(self) -> None:
        kind = TYPE_TO_KIND.get(self.kind_combo.get()) or EXPENSE
        categories = self.service.categories()
        if not categories:
            messagebox.showinfo(
                "Категории", "Сначала создайте категории", parent=self
            )
            return
        result = run_dialog(
            TransactionDialog, self, categories=categories, default_kind=kind
        )
        if result:
            try:
                self.service.create_transaction(
                    result["category_id"], result["amount"], result["date"], result["note"]
                )
            except ValidationError as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
                return
            self.on_change()

    def _edit(self) -> None:
        iid = self.table.selected_iid()
        if iid is None:
            messagebox.showinfo("Изменить", "Выберите операцию", parent=self)
            return
        transaction = self.service.transaction(int(iid))
        if transaction is None:
            return
        result = run_dialog(
            TransactionDialog, self,
            categories=self.service.categories(),
            transaction=transaction,
        )
        if result:
            try:
                self.service.update_transaction(
                    transaction.id, result["category_id"],
                    result["amount"], result["date"], result["note"],
                )
            except ValidationError as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
                return
            self.on_change()

    def _delete(self) -> None:
        iid = self.table.selected_iid()
        if iid is None:
            messagebox.showinfo("Удалить", "Выберите операцию", parent=self)
            return
        if messagebox.askyesno("Удалить", "Удалить выбранную операцию?", parent=self):
            self.service.remove_transaction(int(iid))
            self.on_change()

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            title="Файл выписки банка (CSV, OFX, XLSX)",
            filetypes=[
                ("Банковские выписки", "*.csv *.ofx *.xlsx"),
                ("CSV", "*.csv"),
                ("OFX", "*.ofx"),
                ("Excel", "*.xlsx"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return
        try:
            operations = self.service.parse_operations(path)
        except (ImportFormatError, OSError) as exc:
            messagebox.showerror("Импорт", str(exc), parent=self)
            return
        if not operations:
            messagebox.showinfo("Импорт", "В файле нет операций для импорта", parent=self)
            return
        chosen = run_dialog(
            ImportDialog, self,
            file_name=os.path.basename(path),
            operations=operations,
            known_sources=self.service.operation_sources(),
        )
        if not chosen:
            return
        selected = chosen["operations"]
        if not selected:
            return
        resolutions = self._resolve_import_categories(selected)
        if resolutions is None:
            return
        resolver = self._make_import_resolver(resolutions)
        try:
            summary = self.service.import_operations(
                selected, resolver, skip_existing=chosen["skip_existing"]
            )
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        lines = [f"Импортировано операций: {summary.imported}"]
        if summary.skipped_duplicates:
            lines.append(f"Пропущено (уже есть в базе): {summary.skipped_duplicates}")
        if summary.skipped_category:
            lines.append(f"Пропущено (нет категории): {summary.skipped_category}")
        messagebox.showinfo("Импорт", "\n".join(lines), parent=self)
        self.on_change()

    def _resolve_import_categories(self, selected) -> dict | None:
        keys = sorted(
            {(op.category_name, op.kind) for op in selected},
            key=lambda item: (item[1], item[0]),
        )
        categories = self.service.categories()
        resolutions: dict[tuple[str, str], tuple[str, int | None]] = {}
        new_categories = []
        for name, kind in keys:
            existing = next(
                (c for c in categories
                 if c.name.lower() == name.lower() and c.kind == kind),
                None,
            )
            if existing is not None:
                resolutions[(name, kind)] = ("existing", existing.id)
            else:
                new_categories.append((name, kind))
        if not new_categories:
            return resolutions
        mapped = run_dialog(
            CategoryMapDialog, self,
            new_categories=new_categories, categories=categories,
        )
        if mapped is None:
            return None
        resolutions.update(mapped)
        return resolutions

    def _make_import_resolver(self, resolutions) -> callable:
        cache: dict[tuple[str, str], int] = {}

        def resolver(name: str, kind: str) -> int | None:
            key = (name, kind)
            if key in cache:
                return cache[key]
            action, existing_id = resolutions[key]
            category_id = self.service.import_category(
                name, kind, action, existing_id
            )
            cache[key] = category_id
            return category_id

        return resolver
