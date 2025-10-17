#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SimpleTV Lua Sync v2.3 (Console Edition)
=========================================

	Консольная версия для автоматической синхронизации Lua-скриптов и аддонов
	для медиаплеера SimpleTV.

	Описание:
		Скрипт читает список файлов из INI-файла. Если файл отсутствует,
		создается шаблон с рекомендуемым списком. Затем скрипт загружает
		последние версии файлов из репозиториев GitHub и размещает их 
		в соответствующих папках плеера.

	Автор: A&R
	Дата создания: 17.10.2025
	Лицензия: MIT
	
"""

import os
import requests
import zipfile
from pathlib import Path

# ─── 1. Класс Конфигурации ───────────────────────────────────────────────────
class AppConfig:
	"""Хранит все конфигурационные данные приложения."""
	SCRIPT_PATH = Path(__file__).resolve()
	BASE_FOLDER = SCRIPT_PATH.parent
	INI_PATH = SCRIPT_PATH.with_suffix('.ini')
	
	# Пути к папкам плеера
	FOLDER_VIDEO = BASE_FOLDER / "luaScr/user/video"
	FOLDER_SCRAPERS = BASE_FOLDER / "luaScr/user/TVSources/AutoSetup"
	FOLDER_TIMESHIFT = BASE_FOLDER / "luaScr/user/httptimeshift/extensions"
	
	# URL для загрузки
	URL_VIDEO = "https://raw.githubusercontent.com/Nexterr-origin/simpleTV-Scripts/main/Video%20Scripts/"
	URL_SCRAPERS = "https://raw.githubusercontent.com/Nexterr-origin/simpleTV-Scripts/main/Scrapers%20TVSources/"
	URL_TIMESHIFT = "https://raw.githubusercontent.com/Nexterr-origin/simpleTV-Addons/main/timeshift-extensions/"
	URL_YOUTUBE = "https://raw.githubusercontent.com/Nexterr-origin/simpleTV-YouTube/main/"
	GITHUB_API = "https://api.github.com/repos/BMSimple/SimpleTV/releases/latest"

# ─── 2. Класс Логики Синхронизации ────────────────────────────────────────────
class ScriptSynchronizer:
	"""Выполняет всю логику по синхронизации файлов."""
	def __init__(self, config: AppConfig):
		self.config = config

	def run(self):
		"""Основной метод, запускающий процесс синхронизации."""
		print("🚀 Начало синхронизации...")
		
		file_list = self._get_file_list_from_ini()
		if not file_list:
			return

		print(f"📄 Всего файлов для обработки: {len(file_list)}")
		print()
		
		success_files, failed_files = [], []

		for name in file_list:
			# Пропускаем закомментированные строки
			if "'" in name:
				continue

			# Определяем, какой обработчик использовать
			if name.lower() == "tvsources.zip":
				was_success = self._handle_tvsources_zip()
			else:
				was_success = self._handle_single_file(name)
			
			# Добавляем в списки для отчета
			if was_success:
				success_files.append(name)
			else:
				failed_files.append(name)
		
		self._log_summary(success_files, failed_files)

	def _create_ini_template(self):
		"""Создает шаблон ini-файла с рекомендуемым списком скриптов."""
		print(f"⚠️ INI-файл не найден. Создание шаблона: {self.config.INI_PATH.name}")
		template_content = [
			'TVSources.zip',
			'YT.lua',
			'beeline-timeshift_ext.lua',
			'beeline-tv.lua',
			'beeline-tv_pls.lua',
			'dropbox.lua',
			'edem-timeshift_ext.lua',
			'filmix.lua',
			'hdrezka.lua',
			'inetcom.lua',
			'inetcom_pls.lua',
			'iviru.lua',
			'kinopoisk.lua',
			'kinopoisk_films-a_pls.lua',
			'kinopoisk_serials-a_pls.lua',
			'mediavitrina.lua',
			'ok.lua',
			'playerjs.lua',
			'psevdotv.bond_007.lua',
			'psevdotv.film_ussr.lua',
			'psevdotv.ivi_kinoteatr.lua',
			'psevdotv.jackie_chan.lua',
			'psevdotv_pls.lua',
			'regions_pls.lua',
			'rutube.lua',
			'rutv.lua',
			'rutv_pls.lua',
			'salomtv.lua',
			'salomtv_pls.lua',
			'smartKZ.lua',
			'smartKZ_pls.lua',
			'telegram.lua',
			'wink-timeshift_ext.lua',
			'wink-tv.lua',
			'wink-tv_pls.lua',
			'yandex+radio_pls.lua',
			'yandex-timeshift_ext.lua',
		]
		try:
			with self.config.INI_PATH.open('w', encoding='utf-8') as f:
				f.write('\n'.join(sorted(template_content)))
			print("✅ Шаблон INI-файла успешно создан.")
		except Exception as e:
			print(f"❌ Не удалось создать INI-файл: {repr(e)}")


	def _get_file_list_from_ini(self) -> list:
		"""Читает список файлов из .ini файла. Если файла нет - создает его."""
		if not self.config.INI_PATH.exists():
			self._create_ini_template()
			# Проверяем еще раз, на случай если создание не удалось
			if not self.config.INI_PATH.exists():
				return []
		try:
			with self.config.INI_PATH.open(encoding='utf-8') as f:
				files = [line.strip() for line in f if line.strip()]
			if not files:
				print("⚠️ INI-файл пустой. Нечего загружать.")
			return files
		except Exception as e:
			print(f"❌ Критическая ошибка чтения INI: {repr(e)}")
			return []

	def _handle_single_file(self, name: str) -> bool:
		"""Определяет URL и путь для одного файла и загружает его."""
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
		
		if target_path and source_url:
			return self._download_file(source_url, target_path)
			
		print(f"❓ Неизвестный тип файла: {name}. Пропущен.")
		return False

	def _handle_tvsources_zip(self) -> bool:
		"""Обрабатывает загрузку и распаковку TVSources.zip."""
		zip_url, zip_name = self._get_latest_tvsources_url()
		if not zip_url:
			return False
			
		zip_path = self.config.BASE_FOLDER / zip_name
		
		if self._download_file(zip_url, zip_path):
			try:
				print(f"📦 Распаковка архива: {zip_name}")
				with zipfile.ZipFile(zip_path, 'r') as zip_ref:
					zip_ref.extractall(self.config.BASE_FOLDER)
				zip_path.unlink() # Удаляем архив после распаковки
				print(f"   ✅ Архив успешно распакован.")
				return True
			except Exception as e:
				print(f"❌ Ошибка распаковки {zip_name}: {repr(e)}")
				return False
		return False

	def _get_latest_tvsources_url(self) -> (str, str):
		"""Получает URL на последний релиз TVSources.zip с GitHub."""
		print("🔗 Получение последней версии TVSources...")
		try:
			response = requests.get(self.config.GITHUB_API, timeout=10).json()
			for asset in response.get("assets", []):
				asset_name = asset.get("name", "").lower()
				if asset_name.endswith(".zip") and "tvsources" in asset_name:
					print(f"✔️ Найдена версия: {asset['name']}")
					return asset["browser_download_url"], asset["name"]
			print("⚠️ Не найден .zip актив TVSources в последнем релизе.")
		except Exception as e:
			print(f"❌ Ошибка при запросе к GitHub API: {repr(e)}")
		return None, None

	def _download_file(self, url: str, dest: Path) -> bool:
		"""Загружает один файл по URL и сохраняет его по пути dest."""
		print(f"📥 Загрузка: {dest.name}")
		try:
			r = requests.get(url, timeout=15)
			r.raise_for_status() # Проверка на ошибки HTTP (вроде 404)
			
			dest.parent.mkdir(parents=True, exist_ok=True)
			
			with open(dest, 'wb') as f:
				f.write(r.content)
			
			print(f"   ✅ Успешно: {dest.name}")
			return True
		except requests.exceptions.RequestException as e:
			print(f"   ❌ Ошибка загрузки {dest.name}: {repr(e)}")
			return False

	def _log_summary(self, success_files, failed_files):
		"""Выводит итоговый отчет о проделанной работе."""
		print("\n" + "─" * 20 + " ОТЧЕТ " + "─" * 20)
		print("📦 Синхронизация завершена!")
		
		if failed_files:
			print(f"\n❌ Не удалось загрузить: {len(failed_files)} файлов")
			for f in failed_files:
				print(f"   - {f}")
		
		if success_files:
			print(f"\n✅ Успешно загружено: {len(success_files)} файлов")
			for s in success_files:
				print(f"   - {s}")
		print("─" * 48)

# ─── 3. Точка входа в приложение ─────────────────────────────────────────────
if __name__ == "__main__":
	config = AppConfig()
	synchronizer = ScriptSynchronizer(config)
	synchronizer.run()
	
	# Пауза, чтобы пользователь мог увидеть результат перед закрытием окна
	input("\nНажмите Enter для выхода...")