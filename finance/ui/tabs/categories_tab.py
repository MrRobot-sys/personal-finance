"""Вкладка категорий доходов и расходов."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from datetime import date

from ...models import (
    EXPENSE,
    INCOME,
    INVEST,
    KIND_LABELS,
    PLAN_KINDS,
    ValidationError,
    format_amount,
)
from ..dialogs import CategoryDialog, PlanDialog
from ..widgets import TreeTable, make_card, row, run_dialog

ALL_TYPES = "Все типы"
TYPE_TO_KIND = {
    ALL_TYPES: None,
    "Доходы": INCOME,
    "Расходы": EXPENSE,
    "Инвестиции": INVEST,
}
STATUS_RANK = {"bad": 0, "neutral": 1, "good": 2}


class CategoriesTab(ttk.Frame):
    def __init__(self, master, service, on_change):
        super().__init__(master, padding=12)
        self.service = service
        self.on_change = on_change
        self._build()

    def _build(self) -> None:
        outer, card = make_card(self, title="Категории")
        outer.pack(fill="both", expand=True)

        bar = ttk.Frame(card)
        bar.pack(fill="x")

        ttk.Label(bar, text="Показывать:").pack(side="left")
        self.kind_combo = ttk.Combobox(
            bar, values=list(TYPE_TO_KIND), state="readonly", width=11
        )
        self.kind_combo.set(ALL_TYPES)
        self.kind_combo.pack(side="left", padx=8)
        self.kind_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Button(
            bar, text="Добавить", style="Accent.TButton", command=self._add
        ).pack(side="right")
        ttk.Button(bar, text="Удалить", command=self._delete).pack(side="right", padx=8)
        ttk.Button(bar, text="Изменить", command=self._edit).pack(side="right")
        ttk.Button(bar, text="План в месяц...", command=self._plan).pack(
            side="right", padx=(0, 8)
        )

        self.table = TreeTable(
            card,
            columns=[
                ("kind", "Тип", 90, "center", False),
                ("name", "Название", 190, "w", True),
                ("plan", "План в месяц", 130, "e", True),
                ("fact", "За месяц", 130, "e", True),
                ("avg", "Среднее за 3 мес.", 145, "e", True),
                ("count", "Операций", 80, "e", True),
                ("total", "Всего", 150, "e", True),
            ],
            height=12,
            on_double_click=self._edit,
        )
        self.table.frame.pack(fill="both", expand=True, pady=(12, 0))
        self.table.tree.tag_configure("good", foreground="#047857")
        self.table.tree.tag_configure("bad", foreground="#B91C1C")

        self.hint_var = tk.StringVar(value="")
        ttk.Label(card, textvariable=self.hint_var, style="Muted.TLabel").pack(
            anchor="w", pady=(10, 0)
        )

    def refresh(self) -> None:
        kind = TYPE_TO_KIND.get(self.kind_combo.get())
        today = date.today()
        plans = self.service.category_plans(today.year, today.month)
        rows = []
        for plan in plans:
            category = plan.category
            if kind and category.kind != kind:
                continue
            count, total = self.service.category_usage(category.id)
            status = plan.status
            tags = [status] if status != "neutral" else []
            avg_text = format_amount(plan.avg_3) if plan.avg_3 is not None else "—"
            rows.append(
                row(
                    category.id,
                    [
                        KIND_LABELS[category.kind],
                        category.name,
                        format_amount(plan.limit) if plan.has_limit else "—",
                        format_amount(plan.spent),
                        avg_text,
                        str(count),
                        format_amount(total),
                    ],
                    tags=tags,
                    sort=[
                        category.kind, category.name.lower(),
                        plan.limit if plan.has_limit else 0.0,
                        plan.spent, plan.avg_3 if plan.avg_3 is not None else 0.0,
                        count, total,
                    ],
                )
            )
        rows.sort(key=lambda r: (
            STATUS_RANK[r["tags"][0]] if r["tags"] else STATUS_RANK["neutral"],
            r["values"][1].lower(),
        ))
        self.table.set_rows(rows)
        self.hint_var.set(
            "«Среднее за 3 мес.» — средний расход/доход категории за предыдущие 3 месяца. "
            "Красный — хуже плана, зелёный — лучше, серый — плана нет. "
            "Двойной клик — редактирование категории."
        )

    def _add(self) -> None:
        result = run_dialog(CategoryDialog, self)
        if result:
            name, kind, plan = result
            try:
                self.service.create_category(name, kind, plan)
            except ValidationError as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
                return
            self.on_change()

    def _edit(self) -> None:
        iid = self.table.selected_iid()
        if iid is None:
            messagebox.showinfo("Изменить", "Выберите категорию", parent=self)
            return
        category = self.service.repo.get_category(int(iid))
        if category is None:
            return
        result = run_dialog(CategoryDialog, self, category=category)
        if result:
            name, kind, plan = result
            try:
                self.service.rename_category(category.id, name, kind, plan)
            except ValidationError as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
                return
            self.on_change()

    def _plan(self) -> None:
        categories = [
            c for c in self.service.categories() if c.kind in PLAN_KINDS
        ]
        result = run_dialog(PlanDialog, self, categories=categories)
        if result:
            category, plan = result
            try:
                self.service.set_monthly_plan(category.id, str(plan).replace(".", ",")
                                              if plan is not None else "")
            except ValidationError as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
                return
            self.on_change()

    def _delete(self) -> None:
        iid = self.table.selected_iid()
        if iid is None:
            messagebox.showinfo("Удалить", "Выберите категорию", parent=self)
            return
        category_id = int(iid)
        count, _total = self.service.category_usage(category_id)
        with_transactions = False
        if count:
            answer = messagebox.askyesno(
                "Удалить категорию",
                f"В категории операций: {count}. Удалить категорию вместе с ними?",
                parent=self,
            )
            if not answer:
                return
            with_transactions = True
        else:
            if not messagebox.askyesno(
                "Удалить", "Удалить выбранную категорию?", parent=self
            ):
                return
        try:
            self.service.remove_category(category_id, with_transactions)
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()
