from __future__ import annotations

from collections import deque
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from buzzbot.accounts import mask_account_login
from buzzbot.routines import effective_task_group, task_setting_specs


CATEGORY_TITLES = {
    "startup": "Запуск",
    "daily": "Ежедневные действия",
    "development": "Развитие",
    "army": "Лечение",
    "training": "Производство войск",
    "marches": "Боевые задачи",
    "resources": "Сбор ресурсов",
    "custom": "Другие задачи",
}

CATEGORY_ORDER = ("startup", "daily", "development", "army", "training", "marches", "resources", "custom")


def _resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base.joinpath(*parts)


def _center(window, width, height):
    window.update_idletasks()
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def _bind_numeric_wheel(widget, variable, minimum, maximum, increment=1):
    def on_wheel(event):
        try:
            current = float(variable.get())
            direction = 1 if event.delta > 0 else -1
            value = min(float(maximum), max(float(minimum), current + direction * float(increment)))
            variable.set(int(value) if float(increment).is_integer() else value)
        except (tk.TclError, TypeError, ValueError):
            return "break"
        return "break"

    widget.bind("<MouseWheel>", on_wheel)


class TaskSettingsDialog:
    def __init__(self, parent, bot, task, refresh):
        self.parent = parent
        self.bot = bot
        self.task = task
        self.refresh = refresh
        self.vars = {}
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(task.get("name", "Настройки"))
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        _center(self.dialog, 470, 430)
        self._build()

    def _build(self):
        body = ttk.Frame(self.dialog, padding=16)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=self.task.get("name", ""), style="CompactTitle.TLabel").pack(anchor="w")

        form = ttk.Frame(body)
        form.pack(fill=tk.X, pady=(14, 8))
        settings = self.task.setdefault("settings", {})
        row = 0
        for spec in task_setting_specs(self.task["id"]):
            ttk.Label(form, text=spec["label"]).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            value = settings.get(spec["key"])
            kind = spec["kind"]
            if kind == "bool":
                variable = tk.BooleanVar(value=bool(value))
                widget = ttk.Checkbutton(form, variable=variable)
            elif kind == "choice":
                labels = {stored: label for stored, label in spec["choices"]}
                reverse = {label: stored for stored, label in spec["choices"]}
                variable = tk.StringVar(value=labels.get(value, next(iter(labels.values()))))
                widget = ttk.Combobox(form, textvariable=variable, values=list(reverse), state="readonly", width=23)
                spec = dict(spec, reverse=reverse)
            else:
                variable = tk.IntVar(value=int(value or spec.get("min", 0)))
                widget = ttk.Spinbox(
                    form,
                    from_=spec.get("min", 0),
                    to=spec.get("max", 1000000),
                    textvariable=variable,
                    width=12,
                )
                _bind_numeric_wheel(
                    widget,
                    variable,
                    spec.get("min", 0),
                    spec.get("max", 1000000),
                )
            widget.grid(row=row, column=1, sticky="w", pady=5)
            self.vars[spec["key"]] = (variable, spec)
            row += 1

        self.interval_var = None
        if self.task["id"] != "heal":
            ttk.Label(form, text="Повтор, минут").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            self.interval_var = tk.DoubleVar(value=float(self.task.get("interval_minutes", 1.0)))
            interval_spin = ttk.Spinbox(
                form,
                from_=0.1,
                to=1440,
                increment=0.5,
                textvariable=self.interval_var,
                width=12,
            )
            interval_spin.grid(row=row, column=1, sticky="w", pady=5)
            _bind_numeric_wheel(interval_spin, self.interval_var, 0.1, 1440, 0.5)

        group = effective_task_group(self.task)
        templates = [image for image in self.bot.search_images if image.get("group") == group]
        ttk.Label(body, text=f"Шаблонов: {len(templates)}", foreground="#6b7280").pack(anchor="w", pady=(8, 2))

        completion_map = {
            f"{image.get('description', '')} [{str(image.get('uid', ''))[:8]}]": image.get("uid", "")
            for image in templates
        }
        self.completion_map = completion_map
        selected_label = next(
            (label for label, uid in completion_map.items() if uid == self.task.get("completion_uid")),
            "Авто по таймауту",
        )
        self.completion_var = tk.StringVar(value=selected_label)
        ttk.Label(body, text="Финальный шаг").pack(anchor="w", pady=(8, 2))
        ttk.Combobox(
            body,
            textvariable=self.completion_var,
            values=["Авто по таймауту", *completion_map],
            state="readonly",
            width=48,
        ).pack(fill=tk.X)

        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X, side=tk.BOTTOM, pady=(16, 0))
        ttk.Button(buttons, text="Снять шаблон", command=self.capture_template).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Сохранить", style="Primary.TButton", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Отмена", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=8)
        self.dialog.bind("<Escape>", lambda _event: self.dialog.destroy())

    def _apply(self):
        settings = self.task.setdefault("settings", {})
        for key, (variable, spec) in self.vars.items():
            value = variable.get()
            if spec["kind"] == "choice":
                value = spec["reverse"].get(value, "off")
            settings[key] = value
        if self.interval_var is not None:
            self.task["interval_minutes"] = max(0.1, float(self.interval_var.get()))
        self.task["group"] = effective_task_group(self.task)
        self.task["completion_uid"] = self.completion_map.get(self.completion_var.get(), "")
        if self.task["id"] == "gathering_boost":
            self.task["interval_minutes"] = max(
                self.task["interval_minutes"],
                float(settings.get("boost_hours", 8)) * 60.0,
            )
        self.bot.groups[self.task["group"]] = bool(self.task.get("enabled", False))
        self.bot.save_config()
        self.refresh()

    def save(self):
        try:
            self._apply()
        except (tk.TclError, TypeError, ValueError) as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self.dialog)
            return
        self.dialog.destroy()

    def capture_template(self):
        try:
            self._apply()
        except (tk.TclError, TypeError, ValueError) as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self.dialog)
            return
        group = effective_task_group(self.task)
        count = len([image for image in self.bot.search_images if image.get("group") == group]) + 1
        self.dialog.destroy()
        self.bot.select_area(
            self.parent,
            default_group=group,
            default_description=f"{self.task.get('name')} {count}",
        )


class AccountCredentialsDialog:
    def __init__(self, parent, bot, profile, refresh):
        self.parent = parent
        self.bot = bot
        self.profile = profile
        self.refresh = refresh
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Учётные данные: {profile.get('name', '')}")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        _center(self.dialog, 560, 350)
        self._build()

    def _build(self):
        body = ttk.Frame(self.dialog, padding=16)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="Безопасный вход IGG", style="CompactTitle.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "Пароль шифруется средствами Windows и не сохраняется в config.json. "
                "Он доступен только вашему пользователю Windows на этом компьютере."
            ),
            foreground="#72818A",
            wraplength=520,
        ).pack(anchor="w", pady=(5, 12))

        form = ttk.Frame(body)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Логин IGG (эл. почта)").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        self.login_var = tk.StringVar(value=self.profile.get("igg_login", ""))
        ttk.Entry(form, textvariable=self.login_var, width=42).grid(row=0, column=1, sticky="ew", pady=5)

        ttk.Label(form, text="Пароль").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(form, textvariable=self.password_var, show="●", width=42)
        password_entry.grid(row=1, column=1, sticky="ew", pady=5)

        self.auto_login_var = tk.BooleanVar(value=bool(self.profile.get("auto_login", False)))
        ttk.Checkbutton(
            form,
            text="Автоматически входить при смене аккаунта",
            variable=self.auto_login_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 2))

        self.saved_label = ttk.Label(form, foreground="#355844")
        self.saved_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(3, 0))
        self._refresh_saved_label()

        actions = ttk.Frame(body)
        actions.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(actions, text="Удалить пароль", command=self.delete_password).pack(side=tk.LEFT)

        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X, side=tk.BOTTOM, pady=(14, 0))
        ttk.Button(buttons, text="Сохранить", style="Primary.TButton", command=self.save_and_close).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Закрыть", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=8)
        self.dialog.bind("<Escape>", lambda _event: self.dialog.destroy())

    def _refresh_saved_label(self):
        saved = self.bot.account_has_saved_password(self.profile["id"])
        self.saved_label.config(text=f"Зашифрованный пароль: {'сохранён' if saved else 'не сохранён'}")

    def _save(self):
        login = self.login_var.get().strip()
        password = self.password_var.get()
        self.profile["login_method"] = "igg"
        self.bot.save_account_credentials(
            self.profile["id"],
            login,
            password=password if password else None,
            auto_login=self.auto_login_var.get(),
        )
        self.password_var.set("")
        self._refresh_saved_label()
        self.refresh()

    def save_and_close(self):
        try:
            self._save()
        except Exception as exc:
            messagebox.showerror("Учётные данные", str(exc), parent=self.dialog)
            return
        self.dialog.destroy()

    def delete_password(self):
        try:
            self.bot.delete_account_password(self.profile["id"])
        except Exception as exc:
            messagebox.showerror("Учётные данные", str(exc), parent=self.dialog)
            return
        self.auto_login_var.set(False)
        self.password_var.set("")
        self._refresh_saved_label()
        self.refresh()


class AccountsDialog:
    def __init__(self, parent, bot, refresh):
        self.parent = parent
        self.bot = bot
        self.refresh = refresh
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Аккаунты LDPlayer")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        _center(self.dialog, 720, 460)
        self._build()

    def _build(self):
        body = ttk.Frame(self.dialog, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            body,
            text="Один LDPlayer, несколько сохранённых аккаунтов",
            style="CompactTitle.TLabel",
        ).pack(anchor="w")
        details = self.bot.account_switch_last_result or "Переключение выполняется через IGG Account"
        ttk.Label(body, text=details, foreground="#72818A", wraplength=580).pack(
            anchor="w", pady=(5, 0)
        )
        self.listbox = tk.Listbox(body, height=10, font=("Segoe UI", 10), activestyle="none")
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=12)
        self._reload()

        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Добавить", command=self.add).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Удалить", command=self.delete).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Изменить", command=self.edit).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Учётные данные", command=self.credentials).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Сменить в игре", style="Primary.TButton", command=self.switch_in_game).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Профиль", command=self.select).pack(side=tk.RIGHT, padx=6)
        self.dialog.bind("<Escape>", lambda _event: self.dialog.destroy())

    def _reload(self):
        self.listbox.delete(0, tk.END)
        for profile in self.bot.account_profiles:
            mark = "●" if profile.get("id") == self.bot.current_account_id else " "
            login = str(profile.get("igg_login") or "").strip()
            login_label = mask_account_login(login) or "нет"
            password_label = "да" if self.bot.account_has_saved_password(profile.get("id")) else "нет"
            self.listbox.insert(
                tk.END,
                f"{mark} {profile.get('name')} | IGG | "
                f"логин: {login_label} | пароль: {password_label} | LD {profile.get('ldplayer_index')}",
            )
        if self.bot.account_profiles:
            current = next(
                (i for i, profile in enumerate(self.bot.account_profiles) if profile.get("id") == self.bot.current_account_id),
                0,
            )
            self.listbox.selection_set(current)

    def _selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return None
        return self.bot.account_profiles[selection[0]]

    def add(self):
        name = simpledialog.askstring("Новый аккаунт", "Название аккаунта:", parent=self.dialog)
        if not name or not name.strip():
            return
        current = self.bot.get_current_account() or {}
        ldplayer_index = self.bot.player_index
        if ldplayer_index is None:
            ldplayer_index = current.get("ldplayer_index", 5)
        profile = self.bot.add_account_profile(
            name.strip(), ldplayer_index, self.bot.adb_serial, 30.0
        )
        self.bot.select_account_profile(profile["id"])
        self._reload()
        self.refresh()

    def delete(self):
        profile = self._selected()
        if not profile:
            return
        if not messagebox.askyesno("Аккаунты", f"Удалить профиль «{profile.get('name')}»?", parent=self.dialog):
            return
        if not self.bot.remove_account_profile(profile["id"]):
            messagebox.showwarning("Аккаунты", "Нельзя удалить единственный профиль.", parent=self.dialog)
            return
        self._reload()
        self.refresh()

    def edit(self):
        profile = self._selected()
        if not profile:
            return
        name = simpledialog.askstring(
            "Изменить аккаунт",
            "Название аккаунта:",
            parent=self.dialog,
            initialvalue=profile.get("name", ""),
        )
        if not name or not name.strip():
            return
        profile["name"] = name.strip()
        profile["login_method"] = "igg"
        profile["switch_group"] = f"Аккаунт: {name.strip()}"
        self.bot.save_config()
        self._reload()
        self.refresh()

    def select(self):
        profile = self._selected()
        if not profile:
            return
        self.bot.select_account_profile(profile["id"])
        self.dialog.destroy()
        self.refresh()

    def credentials(self):
        profile = self._selected()
        if not profile:
            return
        AccountCredentialsDialog(self.dialog, self.bot, profile, self._reload)

    def switch_in_game(self):
        profile = self._selected()
        if not profile:
            return
        if not self.bot.start_account_switch(profile["id"]):
            messagebox.showwarning(
                "Аккаунты",
                "Сохраните логин и пароль IGG, включите автоматический вход и проверьте ADB.",
                parent=self.dialog,
            )
            return
        self.dialog.destroy()
        self.refresh()

    def probe(self):
        profile = self._selected()
        if not profile:
            return
        if not self.bot.start_account_probe(profile["id"]):
            messagebox.showwarning(
                "Аккаунты",
                "Не удалось запустить проверку. Убедитесь, что открыт главный экран игры.",
                parent=self.dialog,
            )
            return
        self.dialog.destroy()
        self.refresh()

    def capture_switch(self):
        profile = self._selected()
        if not profile:
            return
        group = "Переключение аккаунта"
        count = len([image for image in self.bot.search_images if image.get("group") == group]) + 1
        self.dialog.destroy()
        self.bot.select_area(
            self.parent,
            default_group=group,
            default_description=f"Вход {profile.get('name')} {count}",
        )


class RemoteControlDialog:
    def __init__(self, parent, bot, refresh=None):
        self.parent = parent
        self.bot = bot
        self.refresh = refresh or (lambda: None)
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Удалённое управление")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        _center(self.dialog, 620, 485)
        self._build()

    def _build(self):
        settings = self.bot.remote_settings
        body = ttk.Frame(self.dialog, padding=18)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="Удалённое управление", style="CompactTitle.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "Устройство отправляет только состояние BuZzbot и принимает команды управления. "
                "Секрет хранится в защищённом хранилище Windows и не попадает в config.json."
            ),
            foreground="#72818A",
            wraplength=570,
        ).pack(anchor="w", pady=(5, 14))

        form = ttk.Frame(body)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)
        self.enabled_var = tk.BooleanVar(value=bool(settings.enabled))
        ttk.Checkbutton(
            form,
            text="Подключать BuZzbot к Remote Hub",
            variable=self.enabled_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(form, text="Имя устройства").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.name_var = tk.StringVar(value=settings.device_name)
        ttk.Entry(form, textvariable=self.name_var, width=42).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Адрес Hub").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        self.url_var = tk.StringVar(value=settings.hub_url)
        ttk.Entry(form, textvariable=self.url_var, width=42).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Секрет Hub").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        self.token_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.token_var, show="●", width=42).grid(row=3, column=1, sticky="ew", pady=6)
        token_state = (
            "Секрет уже сохранён; оставьте поле пустым, чтобы не менять."
            if self.bot.remote_has_token()
            else "Скопируйте секрет из BuZzbot Remote Hub."
        )
        ttk.Label(form, text=token_state, foreground="#72818A").grid(row=4, column=1, sticky="w")

        ttk.Label(form, text="ID устройства").grid(row=5, column=0, sticky="w", padx=(0, 12), pady=6)
        id_var = tk.StringVar(value=settings.device_id)
        ttk.Entry(form, textvariable=id_var, state="readonly", width=42).grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Separator(body).pack(fill=tk.X, pady=14)
        ttk.Label(
            body,
            text=(
                "Для машин в разных городах установите Tailscale на оба ПК и укажите адрес Hub "
                "вида http://100.x.y.z:18765. Открывать порт роутера не требуется."
            ),
            foreground="#72818A",
            wraplength=570,
        ).pack(anchor="w")
        self.status_var = tk.StringVar(value=self.bot.get_remote_control_summary())
        ttk.Label(body, textvariable=self.status_var, foreground="#355844").pack(anchor="w", pady=(10, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X, side=tk.BOTTOM, pady=(16, 0))
        self.test_button = ttk.Button(buttons, text="Проверить", command=self.test)
        self.test_button.pack(side=tk.LEFT)
        ttk.Button(buttons, text="Сохранить", style="Primary.TButton", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Отмена", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=8)
        self.dialog.bind("<Escape>", lambda _event: self.dialog.destroy())

    def _apply(self):
        snapshot = self.bot.configure_remote_control(
            enabled=self.enabled_var.get(),
            hub_url=self.url_var.get(),
            device_name=self.name_var.get(),
            token=self.token_var.get(),
        )
        self.token_var.set("")
        self.refresh()
        return snapshot

    def save(self):
        try:
            self._apply()
        except Exception as exc:
            messagebox.showerror("Удалённое управление", str(exc), parent=self.dialog)
            return
        self.dialog.destroy()

    def test(self):
        try:
            self._apply()
        except Exception as exc:
            messagebox.showerror("Удалённое управление", str(exc), parent=self.dialog)
            return
        self.test_button.configure(state=tk.DISABLED)
        self.status_var.set("Подключение к Hub...")

        def worker():
            try:
                snapshot = self.bot.check_remote_connection()
                message = (
                    f"Связь установлена: {snapshot.get('device_name')}"
                    if snapshot.get("connected")
                    else "Hub не подтвердил подключение."
                )
                is_error = False
            except Exception as exc:
                message = str(exc)
                is_error = True

            def finish():
                self.test_button.configure(state=tk.NORMAL)
                self.status_var.set(message)
                if is_error:
                    messagebox.showerror("Удалённое управление", message, parent=self.dialog)

            self.dialog.after(0, finish)

        threading.Thread(target=worker, name="RemoteControlTest", daemon=True).start()


class ReportCloudDialog:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Диагностические отчёты")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        _center(self.dialog, 620, 430)
        self._build()

    def _build(self):
        settings = self.bot.report_cloud_settings
        body = ttk.Frame(self.dialog, padding=18)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="Диагностические отчёты", style="CompactTitle.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "BuZzbot создаёт обезличенный ZIP со снимком, логами и настройками. "
                "Можно сразу поместить его в синхронизируемую папку Yandex Disk, "
                "Google Drive или OneDrive."
            ),
            foreground="#72818A",
            wraplength=570,
        ).pack(anchor="w", pady=(5, 14))

        form = ttk.Frame(body)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)
        self.enabled_var = tk.BooleanVar(value=bool(settings.enabled))
        ttk.Checkbutton(
            form,
            text="Отправлять новые отчёты в облачную папку",
            variable=self.enabled_var,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(form, text="Имя этого ПК").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.device_var = tk.StringVar(value=settings.device_name)
        ttk.Entry(form, textvariable=self.device_var, width=39).grid(row=1, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(form, text="Облачная папка").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        self.folder_var = tk.StringVar(value=settings.sync_folder)
        ttk.Entry(form, textvariable=self.folder_var, width=34).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Button(form, text="Выбрать", command=self.select_folder).grid(row=2, column=2, padx=(8, 0), pady=6)

        ttk.Separator(body).pack(fill=tk.X, pady=16)
        ttk.Label(
            body,
            text=(
                "Очередь: BuZzbot Reports / Входящие / <имя ПК>. "
                "Локальный дубль удаляется после передачи в папку синхронизации. "
                "Фактическую загрузку выполняет установленный облачный клиент. "
                "После проверки ZIP можно удалить из Входящих, и облачный клиент удалит его на остальных ПК."
            ),
            foreground="#72818A",
            wraplength=570,
        ).pack(anchor="w")

        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X, side=tk.BOTTOM, pady=(18, 0))
        ttk.Button(buttons, text="Закрыть", command=self.dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Сохранить", command=self.save).pack(side=tk.RIGHT, padx=8)
        ttk.Button(
            buttons,
            text="Создать отчёт",
            style="Primary.TButton",
            command=self.create_report,
        ).pack(side=tk.LEFT)
        self.dialog.bind("<Escape>", lambda _event: self.dialog.destroy())

    def select_folder(self):
        selected = filedialog.askdirectory(
            parent=self.dialog,
            title="Выберите папку Yandex Disk, Google Drive или OneDrive",
            initialdir=self.folder_var.get() or None,
        )
        if selected:
            self.folder_var.set(selected)
            self.enabled_var.set(True)

    def _apply(self):
        return self.bot.configure_report_cloud(
            enabled=self.enabled_var.get(),
            sync_folder=self.folder_var.get(),
            device_name=self.device_var.get(),
        )

    def save(self):
        try:
            self._apply()
        except Exception as exc:
            messagebox.showerror("Отчёты", str(exc), parent=self.dialog)
            return
        self.dialog.destroy()

    def create_report(self):
        try:
            self._apply()
            report_path, uploaded = self.bot.create_and_upload_diagnostic_report()
        except Exception as exc:
            messagebox.showerror(
                "Отчёт",
                f"Не удалось создать или отправить отчёт.\n\n{exc}",
                parent=self.dialog,
            )
            return
        title = "Отчёт передан" if uploaded else "Отчёт создан"
        location = "Папка синхронизации" if uploaded else "Локальный файл"
        messagebox.showinfo(title, f"{location}:\n{report_path}", parent=self.dialog)


def build_compact_ui(root, bot):
    colors = {
        "shell": "#14232B",
        "title": "#1B2A33",
        "sidebar": "#21343E",
        "sidebar_active": "#30434C",
        "paper": "#E7EFF3",
        "surface": "#F7FAFB",
        "surface_alt": "#DFE9EE",
        "line": "#C8D5DB",
        "text": "#26343C",
        "muted": "#72818A",
        "accent": "#E46922",
        "green": "#72A47E",
        "green_dark": "#355844",
        "red": "#A64C40",
        "activity": "#304A56",
        "activity_text": "#EAF0F2",
    }

    for after_name in ("status_after_id", "active_after_id", "monitor_after_id", "compact_after_id"):
        after_id = getattr(root, after_name, None)
        if after_id:
            try:
                root.after_cancel(after_id)
            except tk.TclError:
                pass
            setattr(root, after_name, None)
    try:
        root.unbind_all("<MouseWheel>")
    except tk.TclError:
        pass
    for widget in root.winfo_children():
        widget.destroy()

    root.title(f"BuZzbot v{getattr(bot, 'app_version', '3.0.0')}")
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = min(1320, max(1080, screen_width - 70))
    window_height = min(840, max(680, screen_height - 110))
    root.minsize(min(1080, window_width), min(680, window_height))
    root.configure(bg=colors["shell"])
    _center(root, window_width, window_height)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=colors["paper"])
    style.configure("TLabel", background=colors["paper"], foreground=colors["text"], font=("Segoe UI", 9))
    style.configure("TLabelframe", background=colors["paper"], bordercolor=colors["line"])
    style.configure(
        "TLabelframe.Label",
        background=colors["paper"],
        foreground=colors["text"],
        font=("Bahnschrift SemiBold", 10),
    )
    style.configure("TCheckbutton", background=colors["paper"], font=("Segoe UI", 9))
    style.configure("TButton", font=("Bahnschrift SemiBold", 9), padding=(10, 7))
    style.configure("Primary.TButton", foreground="#102019", background=colors["green"])
    style.map("Primary.TButton", background=[("active", "#83B28D"), ("disabled", "#B8C5C9")])
    style.configure("Danger.TButton", foreground="white", background=colors["red"])
    style.map("Danger.TButton", background=[("active", "#8E3F36")])
    style.configure("CompactTitle.TLabel", font=("Bahnschrift SemiBold", 15), foreground=colors["text"])
    style.configure("Deck.TCombobox", padding=5)
    style.configure("Deck.Vertical.TScrollbar", troughcolor=colors["paper"], background="#AFC0C8")

    app = tk.Frame(root, bg=colors["paper"], highlightthickness=1, highlightbackground="#314650")
    app.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

    titlebar = tk.Frame(app, bg=colors["title"], height=52)
    titlebar.pack(fill=tk.X, side=tk.TOP)
    titlebar.pack_propagate(False)
    brand_mark = tk.Label(
        titlebar,
        text="B",
        bg=colors["accent"],
        fg="#14232B",
        font=("Bahnschrift", 14, "bold"),
        width=2,
        pady=5,
    )
    brand_mark.pack(side=tk.LEFT, padx=(18, 10), pady=9)
    tk.Label(
        titlebar,
        text="BuZzbot",
        bg=colors["title"],
        fg="#F4F7F8",
        font=("Bahnschrift", 16, "bold"),
    ).pack(side=tk.LEFT)
    tk.Label(
        titlebar,
        text=f"{getattr(bot, 'app_version', '3.0.0')}  ·  COMMAND DECK",
        bg=colors["title"],
        fg="#83949D",
        font=("Bahnschrift", 8),
    ).pack(side=tk.LEFT, padx=10)
    body = tk.Frame(app, bg=colors["paper"])
    body.pack(fill=tk.BOTH, expand=True)

    sidebar = tk.Frame(body, bg=colors["sidebar"], width=205)
    sidebar.pack(side=tk.LEFT, fill=tk.Y)
    sidebar.pack_propagate(False)
    workspace = tk.Frame(body, bg=colors["paper"])
    workspace.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    tk.Label(
        sidebar,
        text="КОМАНДНЫЙ ЦЕНТР",
        bg=colors["sidebar"],
        fg="#70828B",
        font=("Bahnschrift", 7),
    ).pack(anchor="w", padx=18, pady=(24, 10))

    account_var = tk.StringVar()
    rotation_var = tk.BooleanVar(value=bot.account_rotation_enabled)
    task_vars = {}
    task_rows = {}
    task_redraws = {}
    category_count_labels = {}
    status_events = deque(maxlen=5)

    def run_root_callback(name, fallback=None):
        callback = getattr(root, name, None)
        if callable(callback):
            callback()
        elif fallback:
            fallback()

    nav_rows = []

    def add_nav(code, text, command, active=False):
        row = tk.Frame(sidebar, bg=colors["sidebar_active"] if active else colors["sidebar"], height=44)
        row.pack(fill=tk.X, padx=12, pady=2)
        row.pack_propagate(False)
        if active:
            tk.Frame(row, bg=colors["accent"], width=3).pack(side=tk.LEFT, fill=tk.Y)
        code_label = tk.Label(
            row,
            text=code,
            bg=row["bg"],
            fg=colors["accent"] if active else "#A8B5BB",
            font=("Bahnschrift", 7, "bold"),
            width=4,
        )
        code_label.pack(side=tk.LEFT, padx=(7, 2))
        button = tk.Button(
            row,
            text=text,
            command=command,
            bg=row["bg"],
            fg="#F5F7F8" if active else "#AFBBC0",
            activebackground=colors["sidebar_active"],
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            anchor="w",
            font=("Bahnschrift", 9),
            cursor="hand2",
        )
        button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        nav_rows.append(row)
        return row

    add_nav("ОБ", "Обзор", lambda: None, active=True)
    add_nav("ЗД", "Задачи", lambda: root.after_idle(lambda: cards_canvas.yview_moveto(0.0)))
    add_nav("ШБ", "Шаблоны", lambda: run_root_callback("open_area_manager", lambda: bot.select_area(root)))
    add_nav("АК", "Аккаунты", lambda: AccountsDialog(root, bot, refresh_all))
    add_nav("ЖР", "Отчёт", lambda: create_report())
    add_nav("НТ", "Настройки", lambda: run_root_callback("open_group_schedule"))
    add_nav("UP", "Обновить", lambda: update_app())

    account_panel = tk.Frame(sidebar, bg="#1C2E37", padx=12, pady=12)
    account_panel.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=12)
    tk.Label(
        account_panel,
        text="АКТИВНЫЙ ПРОФИЛЬ",
        bg="#1C2E37",
        fg="#70828B",
        font=("Bahnschrift", 7),
    ).pack(anchor="w")
    account_combo = ttk.Combobox(
        account_panel,
        textvariable=account_var,
        state="readonly",
        width=20,
        style="Deck.TCombobox",
    )
    account_combo.pack(fill=tk.X, pady=(6, 7))
    rotation_check = tk.Checkbutton(
        account_panel,
        text="Автосмена аккаунтов",
        variable=rotation_var,
        bg="#1C2E37",
        fg="#B5C0C5",
        activebackground="#1C2E37",
        activeforeground="#FFFFFF",
        selectcolor="#314852",
        font=("Segoe UI", 8),
        bd=0,
        highlightthickness=0,
    )
    rotation_check.pack(anchor="w")
    tk.Button(
        account_panel,
        text="Управление аккаунтами",
        command=lambda: AccountsDialog(root, bot, refresh_all),
        bg="#2B414B",
        fg="#DDE5E8",
        activebackground="#38515C",
        activeforeground="#FFFFFF",
        relief=tk.FLAT,
        bd=0,
        font=("Bahnschrift", 8),
        cursor="hand2",
        pady=6,
    ).pack(fill=tk.X, pady=(8, 0))

    topbar = tk.Frame(workspace, bg=colors["surface"], height=84, highlightthickness=1, highlightbackground=colors["line"])
    topbar.pack(fill=tk.X, side=tk.TOP)
    topbar.pack_propagate(False)

    connection_title = tk.StringVar(value="Проверка связи")
    connection_detail = tk.StringVar(value="LDPlayer · поиск устройства")
    connection = tk.Frame(topbar, bg=colors["surface"])
    connection.pack(side=tk.LEFT, padx=(22, 18), pady=16)
    connection_dot = tk.Label(connection, text="●", bg=colors["surface"], fg="#A9B8BE", font=("Segoe UI", 21))
    connection_dot.pack(side=tk.LEFT, padx=(0, 9))
    connection_text = tk.Frame(connection, bg=colors["surface"])
    connection_text.pack(side=tk.LEFT)
    tk.Label(
        connection_text,
        textvariable=connection_title,
        bg=colors["surface"],
        fg=colors["text"],
        font=("Bahnschrift", 10, "bold"),
    ).pack(anchor="w")
    tk.Label(
        connection_text,
        textvariable=connection_detail,
        bg=colors["surface"],
        fg=colors["muted"],
        font=("Segoe UI", 7),
    ).pack(anchor="w", pady=(2, 0))

    selected_var = tk.StringVar(value="0 задач")
    march_usage_var = tk.StringVar(value="0 / 5")
    next_cycle_var = tk.StringVar(value="готово")

    def add_stat(label, variable, accent=False):
        frame = tk.Frame(topbar, bg=colors["surface"], width=135, height=82)
        frame.pack(side=tk.LEFT, fill=tk.Y)
        frame.pack_propagate(False)
        tk.Label(
            frame,
            text=label.upper(),
            bg=colors["surface"],
            fg=colors["muted"],
            font=("Bahnschrift", 7),
        ).pack(anchor="w", pady=(18, 3))
        tk.Label(
            frame,
            textvariable=variable,
            bg=colors["surface"],
            fg=colors["accent"] if accent else colors["text"],
            font=("Bahnschrift", 12, "bold"),
        ).pack(anchor="w")
        return frame

    add_stat("Выбрано", selected_var)
    marches_stat = add_stat("Походы", march_usage_var, accent=True)
    add_stat("Следующий цикл", next_cycle_var)

    marches_var = tk.IntVar(value=bot.routine_max_marches)
    marches_spin = ttk.Spinbox(
        marches_stat,
        from_=1,
        to=5,
        width=3,
        textvariable=marches_var,
        font=("Bahnschrift", 8),
    )
    tk.Label(
        marches_stat,
        text="лимит",
        bg=colors["surface"],
        fg=colors["muted"],
        font=("Segoe UI", 7),
    ).place(x=62, y=49)
    marches_spin.place(x=91, y=44, width=36, height=22)

    check_button = tk.Button(
        topbar,
        text="Проверить связь",
        command=lambda: check_environment(),
        bg=colors["surface"],
        fg=colors["text"],
        activebackground=colors["surface_alt"],
        activeforeground=colors["text"],
        relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground="#B5C4CB",
        font=("Bahnschrift", 8),
        cursor="hand2",
        padx=18,
        pady=9,
    )
    check_button.pack(side=tk.RIGHT, padx=20, pady=20)

    controlbar = tk.Frame(workspace, bg=colors["surface_alt"], height=112, highlightthickness=1, highlightbackground=colors["line"])
    controlbar.pack(fill=tk.X, side=tk.BOTTOM)
    controlbar.pack_propagate(False)

    run_summary = tk.Frame(controlbar, bg=colors["surface_alt"])
    run_summary.pack(side=tk.LEFT, fill=tk.Y, padx=24)
    run_summary_title = tk.StringVar(value="Автоматический цикл готов")
    run_summary_detail = tk.StringVar(value="Выберите задачи и нажмите Старт")
    tk.Label(
        run_summary,
        textvariable=run_summary_title,
        bg=colors["surface_alt"],
        fg=colors["text"],
        font=("Bahnschrift", 10, "bold"),
    ).pack(anchor="w", pady=(28, 4))
    tk.Label(
        run_summary,
        textvariable=run_summary_detail,
        bg=colors["surface_alt"],
        fg=colors["muted"],
        font=("Segoe UI", 8),
    ).pack(anchor="w")

    action_panel = tk.Frame(controlbar, bg=colors["surface_alt"])
    action_panel.pack(side=tk.RIGHT, padx=(8, 20), pady=27)

    def action_button(parent, text, command, background, foreground, border=None):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=background,
            activeforeground=foreground,
            disabledforeground="#829099",
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1 if border else 0,
            highlightbackground=border or background,
            font=("Bahnschrift", 9, "bold"),
            width=13,
            height=2,
            cursor="hand2",
        )

    start_button = action_button(action_panel, "СТАРТ НА ВСЕХ", bot.start_all_emulators, colors["green"], "#102019")
    start_button.pack(side=tk.LEFT, padx=5)
    pause_button = action_button(action_panel, "ПАУЗА", bot.toggle_pause_all_emulators, "#B9CED8", "#674411")
    pause_button.pack(side=tk.LEFT, padx=5)
    stop_button = action_button(action_panel, "СТОП ВСЕ", bot.stop_all_emulators, colors["surface_alt"], colors["red"], "#C98E87")
    stop_button.pack(side=tk.LEFT, padx=5)
    root.bind("<F5>", lambda _event: bot.start_all_emulators())
    root.bind("<F6>", lambda _event: bot.stop_all_emulators())

    fox_path = _resource_path("buzzbot", "assets", "fox.png")
    if fox_path.is_file():
        fox_image = Image.open(fox_path).convert("RGBA")
        fox_height = 66
        fox_width = max(1, round(fox_image.width * fox_height / fox_image.height))
        fox_image = fox_image.resize((fox_width, fox_height), Image.Resampling.LANCZOS)
        root.buzzbot_fox_image = ImageTk.PhotoImage(fox_image)
        tk.Label(
            action_panel,
            image=root.buzzbot_fox_image,
            bg=colors["surface_alt"],
            bd=0,
        ).pack(side=tk.LEFT, padx=(10, 0))

    content_shell = tk.Frame(workspace, bg=colors["paper"])
    content_shell.pack(fill=tk.BOTH, expand=True)

    activity = tk.Frame(content_shell, bg=colors["activity"], width=315)
    activity.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 20), pady=20)
    activity.pack_propagate(False)
    main_column = tk.Frame(content_shell, bg=colors["paper"])
    main_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(22, 16), pady=18)

    heading = tk.Frame(main_column, bg=colors["paper"])
    heading.pack(fill=tk.X, pady=(0, 10))
    tk.Label(
        heading,
        text="Панель управления",
        bg=colors["paper"],
        fg=colors["text"],
        font=("Bahnschrift", 18),
    ).pack(side=tk.LEFT)
    tk.Label(
        heading,
        text="только выбранные задачи",
        bg=colors["paper"],
        fg=colors["muted"],
        font=("Segoe UI", 8),
    ).pack(side=tk.LEFT, padx=16, pady=(8, 0))
    tk.Button(
        heading,
        text="Снять все",
        command=lambda: [bot.clear_routine_selection(), refresh_task_state()],
        bg=colors["paper"],
        fg=colors["muted"],
        activebackground=colors["paper"],
        activeforeground=colors["red"],
        relief=tk.FLAT,
        bd=0,
        font=("Bahnschrift", 8),
        cursor="hand2",
    ).pack(side=tk.RIGHT, padx=(12, 0), pady=(8, 0))
    tk.Button(
        heading,
        text="Настроить шаблоны",
        command=lambda: run_root_callback("open_area_manager", lambda: bot.select_area(root)),
        bg=colors["paper"],
        fg=colors["accent"],
        activebackground=colors["paper"],
        activeforeground="#C65317",
        relief=tk.FLAT,
        bd=0,
        font=("Bahnschrift", 8),
        cursor="hand2",
    ).pack(side=tk.RIGHT, pady=(8, 0))

    cards_frame = tk.Frame(main_column, bg=colors["paper"])
    cards_frame.pack(fill=tk.BOTH, expand=True)
    cards_canvas = tk.Canvas(cards_frame, bg=colors["paper"], highlightthickness=0)
    cards_scrollbar = ttk.Scrollbar(
        cards_frame,
        orient=tk.VERTICAL,
        command=cards_canvas.yview,
        style="Deck.Vertical.TScrollbar",
    )
    cards_holder = tk.Frame(cards_canvas, bg=colors["paper"])
    cards_window = cards_canvas.create_window((0, 0), window=cards_holder, anchor="nw")
    cards_canvas.configure(yscrollcommand=cards_scrollbar.set)
    cards_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    cards_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    cards_holder.columnconfigure(0, weight=1, uniform="task_cards")
    cards_holder.columnconfigure(1, weight=1, uniform="task_cards")
    cards_holder.bind("<Configure>", lambda _event: cards_canvas.configure(scrollregion=cards_canvas.bbox("all")))
    cards_canvas.bind("<Configure>", lambda event: cards_canvas.itemconfigure(cards_window, width=event.width))

    def scroll_tasks(event):
        cards_canvas.yview_scroll((-1 if event.delta > 0 else 1) * 3, "units")
        return "break"

    cards_canvas.bind("<Enter>", lambda _event: cards_canvas.bind_all("<MouseWheel>", scroll_tasks))
    cards_canvas.bind("<Leave>", lambda _event: cards_canvas.unbind_all("<MouseWheel>"))

    activity_header = tk.Frame(activity, bg=colors["activity"], height=54)
    activity_header.pack(fill=tk.X)
    activity_header.pack_propagate(False)
    tk.Label(
        activity_header,
        text="ВЫПОЛНЕНИЕ",
        bg=colors["activity"],
        fg=colors["activity_text"],
        font=("Bahnschrift", 10, "bold"),
    ).pack(side=tk.LEFT, padx=18, pady=18)
    live_badge = tk.Label(
        activity_header,
        text="ГОТОВ",
        bg=colors["green_dark"],
        fg="#CDE2D3",
        font=("Bahnschrift", 7),
        padx=15,
        pady=5,
    )
    live_badge.pack(side=tk.RIGHT, padx=16, pady=14)

    current_task_var = tk.StringVar(value="Ожидание запуска")
    status_var = tk.StringVar(value=bot.status_message or "Готов к запуску")
    current = tk.Frame(activity, bg="#3A4E57", highlightthickness=1, highlightbackground="#8D6538", padx=14, pady=13)
    current.pack(fill=tk.X, padx=16, pady=(2, 14))
    tk.Label(
        current,
        text="СЕЙЧАС",
        bg="#3A4E57",
        fg="#F0A45B",
        font=("Bahnschrift", 7),
    ).pack(anchor="w")
    tk.Label(
        current,
        textvariable=current_task_var,
        bg="#3A4E57",
        fg="#F4F7F8",
        font=("Bahnschrift", 10, "bold"),
        wraplength=255,
        justify=tk.LEFT,
    ).pack(anchor="w", pady=(7, 4))
    tk.Label(
        current,
        textvariable=status_var,
        bg="#3A4E57",
        fg="#BCC8CD",
        font=("Segoe UI", 8),
        wraplength=255,
        justify=tk.LEFT,
    ).pack(anchor="w")

    timeline = tk.Frame(activity, bg=colors["activity"])
    timeline.pack(fill=tk.BOTH, expand=True, padx=16)
    environment_var = tk.StringVar(value="ADB и экран: проверка...")
    environment_label = tk.Label(
        activity,
        textvariable=environment_var,
        bg=colors["activity"],
        fg="#91A4AD",
        font=("Segoe UI", 7),
        wraplength=275,
        justify=tk.LEFT,
    )
    environment_label.pack(fill=tk.X, padx=16, pady=(4, 7))
    activity_tools = tk.Frame(activity, bg=colors["activity"])
    activity_tools.pack(fill=tk.X, padx=14, pady=(0, 13))

    check_busy = {"value": False}

    report_busy = {"value": False}

    def create_report():
        if report_busy["value"]:
            return
        if not bot.report_cloud_settings.configured:
            ReportCloudDialog(root, bot)
            return

        report_busy["value"] = True
        report_button.configure(state=tk.DISABLED, text="Создание...")
        bot.set_status_message("Создаю диагностический отчёт и отправляю в облако", force=True)

        def worker():
            try:
                report_path, uploaded = bot.create_and_upload_diagnostic_report()
                error = None
            except Exception as exc:
                report_path = None
                uploaded = False
                error = exc

            def finish():
                report_busy["value"] = False
                report_button.configure(state=tk.NORMAL, text="Создать отчёт")
                if error is not None:
                    messagebox.showerror(
                        "Отчёт",
                        f"Не удалось создать или отправить отчёт.\n\n{error}",
                        parent=root,
                    )
                    return
                title = "Отчёт отправлен" if uploaded else "Отчёт создан"
                location = "Облачная очередь" if uploaded else "Локальный файл"
                messagebox.showinfo(title, f"{location}:\n{report_path}", parent=root)

            root.after(0, finish)

        threading.Thread(target=worker, name="DiagnosticReport", daemon=True).start()

    def update_app():
        if bot.remote_update_in_progress:
            messagebox.showinfo("Обновление", "Проверка обновления уже выполняется.", parent=root)
            return
        if not messagebox.askyesno(
            "Обновление BuZzbot",
            f"Проверить и установить новую версию?\n\nТекущая версия: {bot.app_version}",
            parent=root,
        ):
            return
        bot.start_update()

    report_button = tk.Button(
        activity_tools,
        text="Создать отчёт",
        command=create_report,
        bg="#405A65",
        fg="#DCE5E8",
        activebackground="#4A6773",
        activeforeground="#FFFFFF",
        relief=tk.FLAT,
        bd=0,
        font=("Bahnschrift", 7),
        cursor="hand2",
        pady=6,
    )
    report_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

    repair_button = tk.Button(
        activity_tools,
        text="Восстановить ADB",
        bg="#405A65",
        fg="#DCE5E8",
        activebackground="#4A6773",
        activeforeground="#FFFFFF",
        relief=tk.FLAT,
        bd=0,
        font=("Bahnschrift", 7),
        cursor="hand2",
        pady=6,
    )
    repair_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

    def refresh_timeline():
        for widget in timeline.winfo_children():
            widget.destroy()
        for index, (stamp, message) in enumerate(status_events):
            row = tk.Frame(timeline, bg=colors["activity"])
            row.pack(fill=tk.X, pady=4)
            tk.Label(
                row,
                text=stamp,
                bg=colors["activity"],
                fg="#8398A1",
                font=("Bahnschrift", 7),
                width=5,
                anchor="e",
            ).pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(
                row,
                text="●",
                bg=colors["activity"],
                fg=colors["accent"] if index == 0 else colors["green"],
                font=("Segoe UI", 8),
            ).pack(side=tk.LEFT, anchor="n", padx=(0, 8))
            tk.Label(
                row,
                text=message,
                bg=colors["activity"],
                fg="#D4DEE2" if index == 0 else "#AAB9BF",
                font=("Segoe UI", 7),
                wraplength=188,
                justify=tk.LEFT,
                anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def record_status(*_args):
        message = " ".join(status_var.get().split())
        if not message:
            return
        message = message[:105] + ("..." if len(message) > 105 else "")
        if status_events and status_events[0][1] == message:
            return
        status_events.appendleft((time.strftime("%H:%M"), message))
        refresh_timeline()

    bot.attach_status_var(status_var)
    status_var.trace_add("write", record_status)
    record_status()

    def save_rotation():
        bot.account_rotation_enabled = bool(rotation_var.get())
        bot.save_config()

    rotation_var.trace_add("write", lambda *_args: save_rotation())

    def save_marches():
        try:
            bot.routine_max_marches = min(5, max(1, int(marches_var.get())))
        except (tk.TclError, ValueError):
            return
        marches_var.set(bot.routine_max_marches)
        bot.routine_march_deadlines = bot.routine_march_deadlines[:bot.routine_max_marches]
        bot.save_config()

    _bind_numeric_wheel(marches_spin, marches_var, 1, 5)
    marches_spin.configure(command=save_marches)
    marches_spin.bind("<FocusOut>", lambda _event: save_marches())

    def toggle_task(task):
        value = bool(task_vars[task["id"]].get())
        if task["id"] == "research":
            task.setdefault("settings", {})["branch"] = (
                task.get("settings", {}).get("branch", "any") if value else "off"
            )
            if value and task["settings"]["branch"] == "off":
                task["settings"]["branch"] = "any"
        bot.set_routine_enabled(task["id"], value)
        refresh_task_state()

    def create_task_toggle(parent, task, variable):
        control = tk.Frame(parent, bg=colors["surface"])
        box = tk.Canvas(
            control,
            width=15,
            height=15,
            bg=colors["surface"],
            highlightthickness=0,
            cursor="hand2",
        )
        box.pack(side=tk.LEFT, padx=(0, 7))
        label = tk.Label(
            control,
            text=task.get("name", task["id"]),
            bg=colors["surface"],
            fg="#46535A",
            activebackground=colors["surface"],
            activeforeground=colors["text"],
            font=("Segoe UI", 8),
            anchor="w",
            cursor="hand2",
        )
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        rectangle = box.create_rectangle(1, 1, 14, 14, width=1)
        checkmark = box.create_line(4, 8, 7, 11, 12, 4, fill="#FFFFFF", width=2)

        def redraw(*_args):
            selected = bool(variable.get())
            box.itemconfigure(
                rectangle,
                fill=colors["accent"] if selected else colors["surface"],
                outline=colors["accent"] if selected else "#A7B5BC",
            )
            box.itemconfigure(checkmark, state="normal" if selected else "hidden")

        def click(_event=None):
            variable.set(not bool(variable.get()))
            redraw()
            toggle_task(task)
            return "break"

        box.bind("<Button-1>", click)
        label.bind("<Button-1>", click)
        redraw()
        task_redraws[task["id"]] = redraw
        return control

    def build_task_rows():
        position = cards_canvas.yview()[0] if cards_canvas.winfo_exists() else 0.0
        for widget in cards_holder.winfo_children():
            widget.destroy()
        task_vars.clear()
        task_rows.clear()
        task_redraws.clear()
        category_count_labels.clear()
        grouped = {}
        for task in bot.routine_tasks:
            grouped.setdefault(task.get("category", "custom"), []).append(task)

        card_index = 0
        for category in CATEGORY_ORDER:
            tasks = grouped.get(category, [])
            if not tasks:
                continue
            card = tk.Frame(
                cards_holder,
                bg=colors["surface"],
                highlightthickness=1,
                highlightbackground=colors["line"],
            )
            card.grid(
                row=card_index // 2,
                column=card_index % 2,
                sticky="nsew",
                padx=(0, 6) if card_index % 2 == 0 else (6, 0),
                pady=6,
            )
            tk.Frame(card, bg=colors["accent"], width=4).pack(side=tk.LEFT, fill=tk.Y)
            card_body = tk.Frame(card, bg=colors["surface"], padx=12, pady=10)
            card_body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            card_header = tk.Frame(card_body, bg=colors["surface"])
            card_header.pack(fill=tk.X, pady=(0, 5))
            tk.Label(
                card_header,
                text=CATEGORY_TITLES.get(category, category),
                bg=colors["surface"],
                fg=colors["text"],
                font=("Bahnschrift", 10, "bold"),
            ).pack(side=tk.LEFT)
            active_count = sum(bool(task.get("enabled", False)) for task in tasks)
            active_count_label = tk.Label(
                card_header,
                text=f"{active_count} активно",
                bg=colors["surface_alt"],
                fg=colors["muted"],
                font=("Segoe UI", 7),
                padx=8,
                pady=3,
            )
            active_count_label.pack(side=tk.RIGHT)
            category_count_labels[category] = active_count_label

            for index, task in enumerate(tasks):
                if index:
                    tk.Frame(card_body, bg="#DFE7EA", height=1).pack(fill=tk.X, pady=2)
                row = tk.Frame(card_body, bg=colors["surface"], height=31)
                row.pack(fill=tk.X)
                row.pack_propagate(False)
                variable = tk.BooleanVar(value=bool(task.get("enabled", False)))
                task_vars[task["id"]] = variable
                check = create_task_toggle(row, task, variable)
                check.pack(side=tk.LEFT, fill=tk.X, expand=True)

                if task["id"] == "research":
                    branch_labels = {"off": "Выкл", "economy": "Экономика", "war": "Война", "any": "Любое"}
                    reverse_branches = {label: key for key, label in branch_labels.items()}
                    branch_var = tk.StringVar(
                        value=branch_labels.get(task.get("settings", {}).get("branch", "off"), "Выкл")
                    )

                    def select_research_branch(_event=None, current_task=task, variable=branch_var):
                        branch = reverse_branches.get(variable.get(), "off")
                        current_task.setdefault("settings", {})["branch"] = branch
                        current_task["enabled"] = branch != "off"
                        bot.groups[effective_task_group(current_task)] = current_task["enabled"]
                        bot.save_config()
                        refresh_task_state()

                    branch_combo = ttk.Combobox(
                        row,
                        textvariable=branch_var,
                        values=list(reverse_branches),
                        state="readonly",
                        width=9,
                        style="Deck.TCombobox",
                    )
                    branch_combo.pack(side=tk.RIGHT, padx=(4, 0))
                    branch_combo.bind("<<ComboboxSelected>>", select_research_branch)
                elif task["id"] == "collective_mind":
                    level_var = tk.StringVar(value=str(task.get("settings", {}).get("level", 6)))

                    def select_collective_level(_event=None, current_task=task, variable=level_var):
                        current_task.setdefault("settings", {})["level"] = 7 if variable.get() == "7" else 6
                        bot.save_config()

                    level_combo = ttk.Combobox(
                        row,
                        textvariable=level_var,
                        values=("6", "7"),
                        state="readonly",
                        width=3,
                        style="Deck.TCombobox",
                    )
                    level_combo.pack(side=tk.RIGHT, padx=(4, 0))
                    level_combo.bind("<<ComboboxSelected>>", select_collective_level)
                elif task["id"] == "zombie_hunt":
                    fallback_var = tk.StringVar(
                        value=f"-{int(task.get('settings', {}).get('fallback_levels', 3) or 0)}"
                    )

                    def select_zombie_fallback(_event=None, current_task=task, variable=fallback_var):
                        try:
                            fallback = int(variable.get().lstrip("-"))
                        except ValueError:
                            fallback = 3
                        current_task.setdefault("settings", {})["fallback_levels"] = min(3, max(0, fallback))
                        bot.save_config()

                    fallback_combo = ttk.Combobox(
                        row,
                        textvariable=fallback_var,
                        values=("-0", "-1", "-2", "-3"),
                        state="readonly",
                        width=3,
                        style="Deck.TCombobox",
                    )
                    fallback_combo.pack(side=tk.RIGHT, padx=(4, 0))
                    fallback_combo.bind("<<ComboboxSelected>>", select_zombie_fallback)

                if task_setting_specs(task["id"]):
                    tk.Button(
                        row,
                        text="···",
                        command=lambda current_task=task: TaskSettingsDialog(
                            root,
                            bot,
                            current_task,
                            refresh_task_state,
                        ),
                        bg=colors["surface"],
                        fg=colors["muted"],
                        activebackground=colors["surface_alt"],
                        activeforeground=colors["text"],
                        relief=tk.FLAT,
                        bd=0,
                        font=("Bahnschrift", 9, "bold"),
                        cursor="hand2",
                        width=3,
                    ).pack(side=tk.RIGHT)

                group = effective_task_group(task)
                template_count = len([image for image in bot.search_images if image.get("group") == group])
                indicator = tk.Label(
                    row,
                    text="●",
                    bg=colors["surface"],
                    fg=colors["green"] if template_count else "#C99162",
                    font=("Segoe UI", 7),
                )
                indicator.pack(side=tk.RIGHT, padx=4)
                task_rows[task["id"]] = indicator
            card_index += 1

        cards_holder.update_idletasks()
        cards_canvas.configure(scrollregion=cards_canvas.bbox("all"))
        cards_canvas.yview_moveto(position)

    def check_environment():
        if check_busy["value"]:
            return
        check_busy["value"] = True
        connection_title.set("Проверка связи")
        connection_detail.set("ADB и экран · ожидание")
        connection_dot.configure(fg="#A9B8BE")
        environment_var.set("ADB и экран: проверка...")
        check_button.configure(state=tk.DISABLED)

        def worker():
            ok = bot.check_runtime_environment(notify=False, wait_seconds=45.0)
            summary = bot.get_environment_summary()

            def finish():
                check_busy["value"] = False
                check_button.configure(state=tk.NORMAL)
                environment_var.set(summary)
                connection_title.set("Подключено" if ok else "Нет связи")
                connection_detail.set(
                    f"LDPlayer · {bot.adb_serial}" if ok else "Нажмите «Восстановить ADB»"
                )
                connection_dot.configure(fg=colors["green"] if ok else colors["red"])
                if not ok:
                    bot.sync_status_message()

            root.after(0, finish)

        threading.Thread(target=worker, name="EnvironmentCheck", daemon=True).start()

    def repair_adb():
        target = bot.get_adb_repair_target()
        if not target:
            bot.check_adb_connection(notify=True)
            return
        if not messagebox.askyesno(
            "Восстановление ADB",
            f"Будет включён ADB и перезапущен только LDPlayer {target.index} «{target.name}». Продолжить?",
            parent=root,
        ):
            return
        repair_button.configure(state=tk.DISABLED)
        bot.set_status_message(
            f"Перезапуск LDPlayer {target.index}. Ожидание подключения до 90 секунд...",
            force=True,
        )

        def worker():
            ok = bot.repair_adb_connection(target.index)

            def finish():
                repair_button.configure(state=tk.NORMAL)
                check_environment()
                title = "Связь восстановлена" if ok else "ADB не подключён"
                message = (
                    f"Подключено устройство {bot.adb_serial}."
                    if ok else "Не удалось подключиться. Нажмите «Создать отчёт»."
                )
                (messagebox.showinfo if ok else messagebox.showerror)(title, message, parent=root)

            root.after(0, finish)

        threading.Thread(target=worker, name="AdbRepair", daemon=True).start()

    repair_button.configure(command=repair_adb)

    def select_account(_event=None):
        name = account_var.get()
        profile = next((item for item in bot.account_profiles if item.get("name") == name), None)
        if profile:
            bot.select_account_profile(profile["id"])
            refresh_all()

    account_combo.bind("<<ComboboxSelected>>", select_account)

    def refresh_task_state():
        task_ids = {task["id"] for task in bot.routine_tasks}
        if task_ids != set(task_vars):
            build_task_rows()
            task_ids = set(task_vars)

        category_counts = {}
        for task in bot.routine_tasks:
            task_id = task["id"]
            enabled = bool(task.get("enabled", False))
            variable = task_vars.get(task_id)
            if variable is not None and bool(variable.get()) != enabled:
                variable.set(enabled)
            redraw = task_redraws.get(task_id)
            if redraw:
                redraw()

            category = task.get("category", "custom")
            category_counts[category] = category_counts.get(category, 0) + int(enabled)

            indicator = task_rows.get(task_id)
            if indicator is not None:
                group = effective_task_group(task)
                has_templates = any(
                    image.get("group") == group for image in bot.search_images
                )
                indicator.configure(fg=colors["green"] if has_templates else "#C99162")

        for category, label in category_count_labels.items():
            label.configure(text=f"{category_counts.get(category, 0)} активно")
        selected_var.set(
            f"{sum(bool(task.get('enabled')) for task in bot.routine_tasks)} задач"
        )

    def refresh_all():
        names = [profile.get("name") for profile in bot.account_profiles]
        account_combo["values"] = names
        current_account = bot.get_current_account()
        account_var.set(current_account.get("name") if current_account else (names[0] if names else ""))
        build_task_rows()
        selected_var.set(f"{sum(bool(task.get('enabled')) for task in bot.routine_tasks)} задач")

    def format_countdown(seconds):
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"0:{seconds:02d}"
        if seconds < 3600:
            return f"{seconds // 60}:{seconds % 60:02d}"
        return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}"

    march_refresh = {
        "next_at": 0.0,
        "value": int(getattr(bot, "routine_display_active_marches", 0) or 0),
    }

    def update_state():
        now = time.time()
        enabled_tasks = [task for task in bot.routine_tasks if task.get("enabled")]
        selected_var.set(f"{len(enabled_tasks)} задач")
        if bot.is_running:
            march_refresh["value"] = int(getattr(
                bot,
                "routine_display_active_marches",
                sum(deadline > now for deadline in bot.routine_march_deadlines),
            ))
        elif now >= march_refresh["next_at"]:
            march_refresh["next_at"] = now + 2.0
            try:
                march_refresh["value"] = bot.get_active_marches(now)
            except Exception:
                logger.exception("Не удалось обновить счётчик походов в интерфейсе")
        busy_marches = march_refresh["value"]
        march_usage_var.set(f"{busy_marches} / {bot.routine_max_marches}")

        current_task = bot.get_routine_task(bot.current_routine_task_id) if bot.current_routine_task_id else None
        current_task_var.set(current_task.get("name", "Ожидание") if current_task else "Ожидание следующей задачи")

        deadlines = [
            bot.routine_next_run.get(task["id"], 0.0)
            for task in enabled_tasks
            if bot.routine_next_run.get(task["id"], 0.0) > now
        ]
        next_cycle_var.set(format_countdown(min(deadlines) - now) if deadlines else "готово")

        if bot.is_running:
            start_button.configure(state=tk.DISABLED)
            pause_button.configure(state=tk.NORMAL, text="ПРОДОЛЖИТЬ" if bot.is_paused else "ПАУЗА")
            stop_button.configure(state=tk.NORMAL)
            if bot.is_paused:
                live_badge.configure(text="ПАУЗА", bg="#74613C", fg="#F1D8A8")
                run_summary_title.set("Автоматический цикл на паузе")
            else:
                live_badge.configure(text="В РАБОТЕ", bg=colors["green_dark"], fg="#CDE2D3")
                emulator_count = max(1, int(getattr(bot, "multi_emulator_total", 1)))
                run_summary_title.set(f"Автоматический цикл работает · {emulator_count} эмулятора")
        else:
            ready_state = tk.DISABLED if check_busy["value"] else tk.NORMAL
            start_button.configure(state=ready_state)
            pause_button.configure(state=tk.DISABLED, text="ПАУЗА")
            stop_button.configure(state=tk.DISABLED)
            live_badge.configure(text="ГОТОВ", bg="#425A50", fg="#CDE2D3")
            run_summary_title.set("Автоматический цикл готов")

        detail = " ".join(status_var.get().split())
        run_summary_detail.set(detail[:95] + ("..." if len(detail) > 95 else ""))
        root.compact_after_id = root.after(500, update_state)

    root.bind("<<AccountChanged>>", lambda _event: refresh_all())
    root.refresh_routine_summary = refresh_task_state
    refresh_all()
    root.after(250, check_environment)
    update_state()
