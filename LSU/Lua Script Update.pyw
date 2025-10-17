#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SimpleTV Lua Sync v2.3
======================

	Графическое приложение для автоматической синхронизации Lua-скриптов и аддонов
	для медиаплеера SimpleTV.

	Описание:
		Скрипт читает список файлов из INI-файла. Если файл не найден,
		создается шаблон. Затем скрипт загружает последние версии файлов
		из репозиториев GitHub и размещает в соответствующих папках плеера.

	Автор: A&R
	Дата создания: 17.10.2025
	Лицензия: MIT
	
"""

import os
import requests
import time
import zipfile
import subprocess
import ctypes
import threading
from pathlib import Path
from collections import defaultdict
import customtkinter as ctk
from customtkinter import CTkFont
import tkinter as tk
from tkinter import font as tkfont

# ─── 1. Класс Конфигурации ───────────────────────────────────────────────────
class AppConfig:
	"""Хранит все конфигурационные данные приложения."""
	SCRIPT_PATH = Path(__file__).resolve()
	BASE_FOLDER = SCRIPT_PATH.parent
	INI_PATH = SCRIPT_PATH.with_suffix('.ini')
	TV_EXE_PATH = BASE_FOLDER / "tv.exe"
	FOLDER_VIDEO = BASE_FOLDER / "luaScr/user/video"
	FOLDER_SCRAPERS = BASE_FOLDER / "luaScr/user/TVSources/AutoSetup"
	FOLDER_TIMESHIFT = BASE_FOLDER / "luaScr/user/httptimeshift/extensions"
	URL_VIDEO = "https://raw.githubusercontent.com/Nexterr-origin/simpleTV-Scripts/main/Video%20Scripts/"
	URL_SCRAPERS = "https://raw.githubusercontent.com/Nexterr-origin/simpleTV-Scripts/main/Scrapers%20TVSources/"
	URL_TIMESHIFT = "https://raw.githubusercontent.com/Nexterr-origin/simpleTV-Addons/main/timeshift-extensions/"
	URL_YOUTUBE = "https://raw.githubusercontent.com/Nexterr-origin/simpleTV-YouTube/main/"
	GITHUB_API = "https://api.github.com/repos/BMSimple/SimpleTV/releases/latest"
	WINDOW_TITLE = "SimpleTV Lua Sync v2.3"
	WINDOW_WIDTH = 900
	WINDOW_HEIGHT = 1000
	LOG_COLORS = {
		"success": "#0078d7", "error": "#d13438", "info": "#202020",
		"warning": "#ff8c00", "header": "#005a9e",
	}

# ─── 2. Класс Логики Синхронизации ────────────────────────────────────────────
class ScriptSynchronizer:
	"""Выполняет всю логику по синхронизации файлов."""
	def __init__(self, config: AppConfig, log_callback, progress_callback):
		self.config = config
		self.log = log_callback
		self.update_progress = progress_callback

	def run(self):
		self.log("🚀 Начало синхронизации...", "info")
		file_list = self._get_file_list_from_ini()
		if not file_list: 
			self.log("🏁 Синхронизация прервана: список файлов пуст.", "warning")
			return
		
		# Фильтруем закомментированные строки
		active_files = [name for name in file_list if not name.strip().startswith("'")]
		total_files = len(active_files)
		
		self.log(f"📄 Всего файлов для загрузки: {total_files}", "info")
		success_files, failed_files = [], []
		
		for index, name in enumerate(active_files):
			self.update_progress(index, total_files)
			was_success = self._handle_tvsources_zip() if name.lower() == "tvsources.zip" else self._handle_single_file(name)
			if was_success:
				success_files.append(name)
			else:
				failed_files.append(name)
		
		self.update_progress(total_files, total_files)
		self._log_summary(success_files, failed_files)

	def _get_file_list_from_ini(self) -> list:
		# На этом этапе GUI уже должен был создать файл, если его не было.
		# Эта проверка - дополнительная защита.
		if not self.config.INI_PATH.exists():
			self.log(f"❌ INI-файл {self.config.INI_PATH.name} не найден.", "error")
			return []
		try:
			with self.config.INI_PATH.open(encoding='utf-8') as f:
				files = [line.strip() for line in f if line.strip()]
			if not files: self.log("⚠️ INI-файл пустой. Нечего загружать.", "warning")
			return files
		except Exception as e:
			self.log(f"❌ Критическая ошибка чтения INI: {repr(e)}", "error")
			return []

	def _handle_single_file(self, name: str) -> bool:
		target_path, source_url = None, None
		if "_pls.lua" in name:
			target_path = self.config.FOLDER_SCRAPERS / name
			source_url = self.config.URL_SCRAPERS + name
		elif name.startswith("YT.lua"):
			target_path = self.config.FOLDER_VIDEO / name
			source_url = self.config.URL_YOUTUBE + name
		elif "timeshift_ext.lua" in name:
			target_path = self.config.FOLDER_TIMESHIFT / name
			source_url = self.config.URL_TIMESHIFT + name
		elif name.startswith("playerjs.lua"):
			target_path = self.config.FOLDER_VIDEO / "core" / name
			source_url = self.config.URL_VIDEO + "core/" + name
		elif name.endswith(".lua"):
			target_path = self.config.FOLDER_VIDEO / name
			source_url = self.config.URL_VIDEO + name
		if target_path and source_url: return self._download_file(source_url, target_path)
		self.log(f"❓ Неизвестный тип файла: {name}. Пропущен.", "warning")
		return False

	def _handle_tvsources_zip(self) -> bool:
		zip_url, zip_name = self._get_latest_tvsources_url()
		if not zip_url: return False
		zip_path = self.config.BASE_FOLDER / zip_name
		if self._download_file(zip_url, zip_path):
			try:
				self.log(f"📦 Распаковка архива: {zip_name}", "info")
				with zipfile.ZipFile(zip_path, 'r') as zip_ref:
					zip_ref.extractall(self.config.BASE_FOLDER)
				zip_path.unlink()
				self.log(f"✅ Архив успешно распакован.", "success")
				return True
			except Exception as e:
				self.log(f"❌ Ошибка распаковки {zip_name}: {repr(e)}", "error")
				return False
		return False

	def _get_latest_tvsources_url(self) -> (str, str):
		self.log("🔗 Получение последней версии TVSources...", "info")
		try:
			response = requests.get(self.config.GITHUB_API, timeout=10).json()
			for asset in response.get("assets", []):
				asset_name = asset.get("name", "").lower()
				if asset_name.endswith(".zip") and "tvsources" in asset_name:
					self.log(f"✔️ Найдена версия: {asset['name']}", "success")
					return asset["browser_download_url"], asset["name"]
			self.log("⚠️ Не найден .zip актив TVSources в последнем релизе.", "warning")
		except Exception as e:
			self.log(f"❌ Ошибка при запросе к GitHub API: {repr(e)}", "error")
		return None, None

	def _download_file(self, url: str, dest: Path) -> bool:
		self.log(f"📥 Загрузка: {dest.name}", "info")
		try:
			r = requests.get(url, timeout=15)
			r.raise_for_status()
			dest.parent.mkdir(parents=True, exist_ok=True)
			with open(dest, 'wb') as f: f.write(r.content)
			self.log(f"✅ Успешно: {dest.name}", "success")
			return True
		except requests.exceptions.RequestException as e:
			self.log(f"❌ Ошибка загрузки {dest.name}: {repr(e)}", "error")
			return False

	def _log_summary(self, success_files, failed_files):
		self.log("\n" + "─" * 20 + " ОТЧЕТ " + "─" * 20, "header")
		self.log("📦 Синхронизация завершена!", "info")
		if failed_files:
			self.log(f"❌ Не удалось загрузить: {len(failed_files)} файлов", "error")
			for f in failed_files: self.log(f"   - {f}", "error")
		if success_files:
			self.log(f"✅ Успешно загружено: {len(success_files)} файлов", "success")
			for s in success_files: self.log(f"   - {s}", "success")
		self.log("─" * 48, "header")

# ─── 3. Класс Приложения (GUI) ────────────────────────────────────────────────
class SyncApp(ctk.CTk):
	"""Основной класс приложения, управляющий GUI и взаимодействием с пользователем."""
	def __init__(self, config: AppConfig):
		super().__init__()
		self.config = config
		self.synchronizer = ScriptSynchronizer(config=self.config, log_callback=self._log, progress_callback=self._update_progress)
		self._setup_window()
		self._create_widgets()
		self._initialize_app_state()

	def _setup_window(self):
		self.title(self.config.WINDOW_TITLE)
		ctk.set_appearance_mode("light")
		ctk.set_default_color_theme("blue")
		try:
			ctypes.windll.user32.SetProcessDPIAware()
			screen_w = ctypes.windll.user32.GetSystemMetrics(0)
			screen_h = ctypes.windll.user32.GetSystemMetrics(1)
		except Exception:
			screen_w = self.winfo_screenwidth()
			screen_h = self.winfo_screenheight()
		x = (screen_w // 2) - (self.config.WINDOW_WIDTH)
		y = (screen_h // 2) - (self.config.WINDOW_HEIGHT)
		if x < 0: x = 0
		if y < 0: y = 0
		self.geometry(f"{self.config.WINDOW_WIDTH}x{self.config.WINDOW_HEIGHT}+{x}+{y}")

	def _create_widgets(self):
		ctk.CTkLabel(self, text="SimpleTV Lua Sync", font=("Segoe UI", 20, "bold")).pack(pady=(15, 5))
		self.status_label = ctk.CTkLabel(self, text="Готов", font=("Segoe UI", 14))
		self.status_label.pack(pady=5)
		main_container = ctk.CTkFrame(self)
		main_container.pack(fill="both", expand=True, padx=20, pady=10)
		main_container.grid_rowconfigure(0, weight=4)
		main_container.grid_rowconfigure(2, weight=5)
		main_container.grid_columnconfigure(0, weight=1)
		scripts_frame = self._create_labeled_frame(main_container, "Скрипты для обновления:", 0)
		self.scripts_text = self._create_textbox(scripts_frame)
		progress_frame = ctk.CTkFrame(main_container)
		progress_frame.grid(row=1, column=0, sticky="ew", pady=10)
		self.progress = ctk.CTkProgressBar(progress_frame, mode="determinate", height=20)
		self.progress.pack(fill="x", padx=10, pady=5, expand=True)
		self.progress.set(0)
		self.progress_label = ctk.CTkLabel(progress_frame, text="0%", font=("Segoe UI", 12))
		self.progress_label.pack()
		logs_frame = self._create_labeled_frame(main_container, "Лог выполнения:", 2)
		self.log_text = self._create_textbox(logs_frame)
		self.action_button = ctk.CTkButton(self, font=("Segoe UI", 14, "bold"), height=40)
		self.action_button.pack(fill="x", padx=20, pady=10)

	def _create_labeled_frame(self, parent, text, row):
		frame = ctk.CTkFrame(parent)
		frame.grid(row=row, column=0, sticky="nsew")
		header_frame = ctk.CTkFrame(frame, fg_color="transparent")
		header_frame.pack(fill="x", padx=10, pady=(10, 5))
		ctk.CTkLabel(header_frame, text=text, font=("Segoe UI", 14, "bold")).pack(side="left")
		return frame

	def _create_textbox(self, parent):
		textbox = ctk.CTkTextbox(parent, state="normal")
		textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
		textbox.bind("<Key>", self._block_editing, add=True)
		textbox.bind("<Control-Key>", lambda e, tb=textbox: self._handle_ctrl_key(e, tb), add=True)

		menu = tk.Menu(self, tearoff=0)
		menu.add_command(label="Копировать", command=lambda tb=textbox: self._copy_to_clipboard(tb))
		menu.add_command(label="Выделить всё", command=lambda tb=textbox: tb.tag_add("sel", "1.0", "end"))
		textbox.bind("<Button-3>", lambda e, m=menu: self._show_context_menu(e, m), add=True)

		if not getattr(self, "_global_copy_binds_installed", False):
			self.bind_all("<Control-c>", self._global_ctrlc_handler, add=True)
			self.bind_all("<Control-C>", self._global_ctrlc_handler, add=True)
			self.bind_all("<Control-a>", self._global_ctrla_handler, add=True)
			self.bind_all("<Control-A>", self._global_ctrla_handler, add=True)
			self._global_copy_binds_installed = True

		return textbox

	def _handle_ctrl_key(self, event, textbox):
		if not (event.state & 0x4):
			return
		keycode = event.keycode
		if keycode in (65, 97):  # A / a
			textbox.tag_add("sel", "1.0", "end")
			return "break"
		elif keycode in (67, 99):  # C / c
			self._copy_to_clipboard(textbox)
			return "break"

	def _show_context_menu(self, event, menu):
		try:
			menu.tk_popup(event.x_root, event.y_root)
		finally:
			menu.grab_release()

	def _copy_to_clipboard(self, textbox):
		try:
			try:
				selected = textbox.get("sel.first", "sel.last")
			except tk.TclError:
				selected = textbox.get("1.0", "end").rstrip("\n")
			if selected:
				self.clipboard_clear()
				self.clipboard_append(selected)
				self.update()
		except Exception:
			pass

	def _global_ctrlc_handler(self, event):
		widget = self.focus_get()
		if isinstance(widget, (ctk.CTkTextbox, tk.Text)):
			self._copy_to_clipboard(widget)
			return "break"

	def _global_ctrla_handler(self, event):
		widget = self.focus_get()
		if isinstance(widget, (ctk.CTkTextbox, tk.Text)):
			widget.tag_add("sel", "1.0", "end")
			return "break"

	def _block_editing(self, event):
		is_ctrl_pressed = (event.state & 4) != 0
		if is_ctrl_pressed and event.keysym.lower() in ('c', 'a'):
			return 
		if event.keysym in ("BackSpace", "Delete") or (event.char and event.char.isprintable()):
			return "break"

	def _initialize_app_state(self):
		self.status_label.configure(text="Загрузка списка скриптов...")
		self._display_scripts_from_ini()
		self.status_label.configure(text="Готов к обновлению")
		self._set_action_button("Обновить скрипты/скраперы", self._on_start_sync_button_click)
		self._log("✅ Приложение готово к работе.", "success")
		self._log("Нажмите кнопку 'Обновить скрипты/скраперы' для начала.", "info")

	def _create_ini_template(self):
		"""Создает шаблон ini-файла с рекомендуемым списком скриптов."""
		self._log(f"⚠️ INI-файл не найден. Создание шаблона: {self.config.INI_PATH.name}", "warning")
		template_content = [
			'TVSources.zip', 'YT.lua', 'beeline-timeshift_ext.lua', 'beeline-tv.lua',
			'beeline-tv_pls.lua', 'dropbox.lua', 'edem-timeshift_ext.lua', 'filmix.lua',
			'hdrezka.lua', 'inetcom.lua', 'inetcom_pls.lua', 'iviru.lua', 'kinopoisk.lua',
			'kinopoisk_films-a_pls.lua', 'kinopoisk_serials-a_pls.lua', 'mediavitrina.lua',
			'ok.lua', 'playerjs.lua', 'psevdotv.bond_007.lua', 'psevdotv.film_ussr.lua',
			'psevdotv.ivi_kinoteatr.lua', 'psevdotv.jackie_chan.lua', 'psevdotv_pls.lua',
			'regions_pls.lua', 'rutube.lua', 'rutv.lua', 'rutv_pls.lua', 'salomtv.lua',
			'salomtv_pls.lua', 'smartKZ.lua', 'smartKZ_pls.lua', 'telegram.lua',
			'wink-timeshift_ext.lua', 'wink-tv.lua', 'wink-tv_pls.lua',
			'yandex+radio_pls.lua', 'yandex-timeshift_ext.lua',
		]
		try:
			with self.config.INI_PATH.open('w', encoding='utf-8') as f:
				f.write('\n'.join(sorted(template_content)))
			self._log("✅ Шаблон INI-файла успешно создан.", "success")
		except Exception as e:
			self._log(f"❌ Не удалось создать INI-файл: {repr(e)}", "error")

	def _display_scripts_from_ini(self):
		"""Отображает скрипты из INI-файла, создавая его при отсутствии."""
		self.scripts_text.delete("1.0", "end")
		
		if not self.config.INI_PATH.exists():
			self._create_ini_template()
		
		# Теперь файл должен существовать
		if not self.config.INI_PATH.exists():
			self.scripts_text.insert("end", "❌ INI-файл не удалось создать.\n")
			return

		try:
			with self.config.INI_PATH.open(encoding='utf-8') as f:
				file_list = sorted([line.strip() for line in f if line.strip()], key=str.lower)
			if not file_list:
				self.scripts_text.insert("end", "⚠️ INI-файл пустой\n")
				return

			groups = self._group_scripts(file_list)

			for group_name, scripts in groups.items():
				if scripts:
					self.scripts_text.insert("end", f"\n{group_name}:\n", "group_header")
					for script in scripts:
						self.scripts_text.insert("end", f"  • {script}\n")

			self.scripts_text.tag_config("group_header", foreground=self.config.LOG_COLORS["header"], underline=False)

		except Exception as e:
			self.scripts_text.insert("end", f"❌ Ошибка при отображении списка: {repr(e)}\n")
			self._log(f"Ошибка чтения INI: {repr(e)}", "error")

	def _group_scripts(self, file_list: list) -> dict:
		groups = defaultdict(list)
		group_order = ["TVSources", "Скраперы", "YouTube", "TimeShift", "Core Video", "Видео скрипты", "Другие"]
		for name in file_list:
			if name.startswith("'"): continue
			if name.lower() == "tvsources.zip": groups["TVSources"].append(name)
			elif "_pls.lua" in name: groups["Скраперы"].append(name)
			elif name.startswith("YT.lua"): groups["YouTube"].append(name)
			elif "timeshift_ext.lua" in name: groups["TimeShift"].append(name)
			elif name.startswith("playerjs.lua"): groups["Core Video"].append(name)
			elif name.endswith(".lua"): groups["Видео скрипты"].append(name)
			else: groups["Другие"].append(name)
		return {key: groups[key] for key in group_order}

	def _log(self, msg, tag="info"):
		color = self.config.LOG_COLORS.get(tag, self.config.LOG_COLORS["info"])
		tag_name = f"log_{tag}"
		self.log_text.insert("end", f"{msg}\n")
		if tag_name not in self.log_text.tag_names():
			self.log_text.tag_config(tag_name, foreground=color)
		self.log_text.tag_add(tag_name, "end-2l", "end-1l")
		self.log_text.see("end")
		self.update_idletasks()

	def _update_progress(self, current, total):
		if total > 0:
			progress_value = current / total
			self.progress.set(progress_value)
			self.progress_label.configure(text=f"{int(progress_value * 100)}%")
		self.update_idletasks()

	def _set_action_button(self, text, command, state="normal"):
		self.action_button.configure(text=text, state=state, command=command)
		if command and state == "normal":
			self.unbind('<Return>')
			self.bind('<Return>', lambda event: command())
		else:
			self.unbind('<Return>')

	def _on_start_sync_button_click(self):
		self.status_label.configure(text="Выполняется синхронизация...")
		self._set_action_button("Выполняется обновление...", None, "disabled")
		self.log_text.delete("1.0", "end")
		sync_thread = threading.Thread(target=self._run_sync_in_thread, daemon=True)
		sync_thread.start()

	def _run_sync_in_thread(self):
		self.synchronizer.run()
		self.status_label.configure(text="Синхронизация завершена")
		self._set_action_button("Перезапустить SimpleTV", self._on_restart_button_click)

	def _on_restart_button_click(self):
		self._log(f"🔍 Проверка файла: {self.config.TV_EXE_PATH}", "info")
		if not self.config.TV_EXE_PATH.exists():
			self._log("❌ tv.exe не найден. Приложение будет закрыто.", "error")
		else:
			try:
				self._log("🔄 Закрытие SimpleTV...", "info")
				subprocess.run([str(self.config.TV_EXE_PATH), "-closeall"], shell=True, timeout=5)
				time.sleep(2)
				self._log("🚀 Запуск SimpleTV...", "info")
				subprocess.Popen([str(self.config.TV_EXE_PATH)], shell=True)
				self._log("✅ SimpleTV перезапущен.", "success")
			except subprocess.TimeoutExpired:
				self._log("⚠️ Timeout при закрытии SimpleTV. Пробуем запустить...", "warning")
				subprocess.Popen([str(self.config.TV_EXE_PATH)], shell=True)
			except Exception as e:
				self._log(f"❌ Ошибка перезапуска SimpleTV: {repr(e)}", "error")
		self.after(2000, self.destroy)

# ─── 4. Точка входа в приложение ─────────────────────────────────────────────
if __name__ == "__main__":
	config = AppConfig()
	app = SyncApp(config)
	app.mainloop()
