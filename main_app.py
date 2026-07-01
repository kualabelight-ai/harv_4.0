

# === ПОЛНОЕ ПОДАВЛЕНИЕ ПРЕДУПРЕЖДЕНИЙ STREAMLIT ===
import os
os.environ["STREAMLIT_WATCHDOG_TIMEOUT"] = "0"
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_SERVER_ENABLE_CORS"] = "false"
os.environ["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "false"

import warnings
warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")
warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")
warnings.filterwarnings("ignore", category=UserWarning, module="streamlit")

import logging
# Полное отключение логов Streamlit
logging.getLogger("streamlit").setLevel(logging.ERROR)
logging.getLogger("streamlit.scriptrunner").setLevel(logging.ERROR)
logging.getLogger("streamlit.scriptrunner.script_runner").setLevel(logging.ERROR)
logging.getLogger("streamlit.runtime.scriptrunner").setLevel(logging.ERROR)
logging.getLogger("streamlit.runtime.scriptrunner.script_runner").setLevel(logging.ERROR)

# Отключаем все сообщения от Thread
logging.getLogger("threading").setLevel(logging.ERROR)

# Перенаправляем stderr в null для потоков
import sys
class SuppressStream:
    def write(self, msg):
        if "missing ScriptRunContext" not in msg:
            sys.__stderr__.write(msg)
    def flush(self):
        pass

sys.stderr = SuppressStream()



import streamlit as st
import json
import uuid
from pathlib import Path
import os
import time
import threading
import queue
from datetime import datetime
from typing import Dict, Any
from dataclasses import dataclass
from enum import Enum

from styles import load_css
from database_settings import auth
from project_manager import ProjectManager
from phases import phase1, phase2, phase3, phase4, phase5, phase6, phase7
# Добавить после всех импортов
from domain_manager import DomainManager, render_domain_selector
from phases.phase3 import has_phase3_data
from phases.phase3 import force_save_phase3_blocks
from user_queue_manager import GlobalQueueManager, get_user_queue
from file_data_manager import FileDataManager
import warnings
import logging
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
# Подавляем конкретное предупреждение о ScriptRunContext
warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")
import logging
# ДОБАВЬТЕ ЭТИ ИМПОРТЫ В НАЧАЛО ФАЙЛА (после остальных импортов):

from phase_navigation import render_phase_navigation, render_phase_content
from project_status_manager import ProjectStatusManager
# Подавляем конкретное сообщение от Streamlit
logging.getLogger("streamlit.scriptrunner").setLevel(logging.ERROR)
# Или более агрессивно - подавляем все предупреждения Streamlit в потоках
logging.getLogger("streamlit").setLevel(logging.ERROR)
# === В НАЧАЛЕ ФАЙЛА (ПОСЛЕ ИМПОРТОВ) ===
import os
import sys
import builtins
import logging
import warnings

# ============================================
# 1. ПОДАВЛЕНИЕ КОНСОЛЬНОГО ВЫВОДА (print, stdout)
# ============================================

class SuppressConsole:
    """Подавляет ВЕСЬ консольный вывод без трогания Streamlit"""

    def __init__(self):
        self.original_stdout = None
        self.original_stderr = None
        self.original_print = None
        self.null_file = None
        self._active = False

    def enable(self):
        """Включает подавление"""
        if self._active:
            return

        # Сохраняем оригиналы
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        # Открываем /dev/null (Windows: nul)
        import platform
        if platform.system() == 'Windows':
            self.null_file = open('nul', 'w')
        else:
            self.null_file = open('/dev/null', 'w')

        # Перенаправляем stdout/stderr в null
        sys.stdout = self.null_file
        sys.stderr = self.null_file

        # Перехватываем print
        self.original_print = builtins.print
        builtins.print = lambda *args, **kwargs: None

        self._active = True

    def disable(self):
        """Выключает подавление"""
        if not self._active:
            return

        # Восстанавливаем
        if self.original_stdout:
            sys.stdout = self.original_stdout
        if self.original_stderr:
            sys.stderr = self.original_stderr
        if self.original_print:
            builtins.print = self.original_print

        if self.null_file:
            self.null_file.close()

        self._active = False

# Создаем экземпляр
console_suppressor = SuppressConsole()

# ============================================
# 2. КАСТОМНЫЙ ЛОГГЕР (ВМЕСТО st.write ДЛЯ ОТЛАДКИ)
# ============================================

class DebugLogger:
    """Логгер для отладочной информации - НЕ использует st.write()"""

    def __init__(self):
        self.logs = []
        self.max_logs = 500
        self.enabled = False

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def log(self, msg, level="INFO"):
        """Сохраняет лог в память (НЕ ВЫВОДИТ НА ЭКРАН)"""
        if not self.enabled:
            return

        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {level} | {msg}"
        self.logs.append(log_entry)

        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def show_logs(self):
        """Показывает логи в Streamlit (только если включено)"""
        if not self.enabled or not self.logs:
            return

        import streamlit as st
        with st.expander("🐛 Логи отладки", expanded=False):
            st.code("\n".join(self.logs[-100:]), language="text")

    def clear(self):
        self.logs = []

# Создаем глобальный логгер
debug_logger = DebugLogger()

# ============================================
# 3. КОНТРОЛЬ РЕЖИМА ОТЛАДКИ
# ============================================

def setup_debug_mode():
    """
    Настраивает режим отладки.
    НЕ ТРОГАЕТ Streamlit функции (st.write, st.info и т.д.)
    """
    # Проверяем переменную окружения
    debug_env = os.environ.get('DEBUG_MODE', 'false').lower()
    is_debug = debug_env in ['true', '1', 'yes']

    if is_debug:
        print("🐛 РЕЖИМ ОТЛАДКИ ВКЛЮЧЕН")
        # Включаем вывод в консоль
        console_suppressor.disable()
        # Включаем логирование
        debug_logger.enable()
    else:
        print("🚀 РЕЖИМ ОТЛАДКИ ОТКЛЮЧЕН")
        # Подавляем консольный вывод
        console_suppressor.enable()
        # Отключаем логирование (но сохраняем логи в памяти на всякий случай)
        debug_logger.disable()

    return is_debug

def suppress_all_warnings():
    """Подавляет все предупреждения"""
    warnings.filterwarnings("ignore")

    # Подавляем логи Streamlit
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    logging.getLogger("streamlit.scriptrunner").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)

    for logger_name in ['watchdog', 'tornado', 'asyncio', 'socketio']:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

# ============================================
# 4. ЗАМЕНА log() ФУНКЦИИ
# ============================================

def log(msg, level="INFO"):
    """
    Заменяет старую функцию log().
    В production просто игнорирует вывод.
    """
    debug_logger.log(msg, level)

# ============================================
# 5. ФУНКЦИЯ ДЛЯ ПОКАЗА ЛОГОВ (ОПЦИОНАЛЬНО)
# ============================================

def render_debug_logs():
    """Показывает логи отладки (только для админа)"""
    try:
        from database_settings.auth import is_admin
        if not is_admin():
            return
    except:
        return

    if st.button("🐛 Показать логи отладки", key="show_debug_logs"):
        debug_logger.show_logs()
def debug_json_structure(project_id: str = None):
    """Показывает полную структуру JSON проекта"""
    import json
    from pathlib import Path

    st.markdown("### 🔬 ДЕТАЛЬНАЯ ДИАГНОСТИКА JSON")

    user_id = st.session_state.get('user_id')
    site = st.session_state.get('current_site', 'steelborg')
    domain = st.session_state.get('current_domain', 'default')

    if not project_id:
        project_id = st.session_state.get('current_project_id')

    if not project_id:
        st.error("❌ Нет project_id")
        return

    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

    if not project_file.exists():
        st.error(f"❌ Файл не найден: {project_file}")
        return

    with open(project_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    st.markdown("#### 📊 Корневые поля:")
    st.json({
        'project_id': data.get('project_id'),
        'project_name': data.get('project_name'),
        'category': data.get('category'),
        'current_phase': data.get('current_phase'),
        'status': data.get('status'),
        'progress': data.get('progress'),
        'message': data.get('message'),
        'error': data.get('error'),
        'domain_name': data.get('domain_name'),
        'site_name': data.get('site_name'),
    })

    st.markdown("#### 📊 app_data ключи:")
    app_data = data.get('app_data', {})
    st.write(f"**Ключи:** {list(app_data.keys())}")

    st.markdown("#### 📊 Флаги в app_data:")
    flags = {
        'phase5_completed': app_data.get('phase5_completed'),
        'phase6_completed': app_data.get('phase6_completed'),
        'phase7_completed': app_data.get('phase7_completed'),
        'phase5_results': bool(app_data.get('phase5', {}).get('results')),
        'phase5_has_data': bool(app_data.get('phase5', {})),
        'phase4_has_data': bool(app_data.get('phase4', {})),
        'phase3_has_data': bool(app_data.get('phase3', {})),
    }
    st.json(flags)

    st.markdown("#### 📊 phase5 содержимое:")
    phase5 = app_data.get('phase5', {})
    st.json({
        'has_results': bool(phase5.get('results')),
        'results_count': len(phase5.get('results', {})),
        'phase_completed': phase5.get('phase_completed'),
        'keys': list(phase5.keys())
    })

    st.markdown("#### 📊 phase4 содержимое:")
    phase4 = app_data.get('phase4', {})
    st.json({
        'has_prompts': bool(phase4.get('prompts')),
        'prompts_count': len(phase4.get('prompts', [])),
        'keys': list(phase4.keys())
    })
def debug_project_paths(project_id: str = None):
    """Диагностика путей к проектам"""
    st.markdown("### 🔍 Диагностика путей к проектам")

    user_id = st.session_state.get('user_id')
    current_site = st.session_state.get('current_site', 'steelborg')
    current_domain = st.session_state.get('current_domain', 'default')

    st.write(f"**User ID:** {user_id}")
    st.write(f"**Current site:** {current_site}")
    st.write(f"**Current domain:** {current_domain}")
    st.write(f"**Project ID:** {project_id}")

    st.markdown("---")

    # Проверяем существование директорий
    import os
    from pathlib import Path

    st.markdown("#### 📁 Существующие директории:")

    # 1. Базовая директория sites
    sites_dir = Path("sites")
    st.write(f"sites/ существует: {sites_dir.exists()}")
    if sites_dir.exists():
        sites = [d.name for d in sites_dir.iterdir() if d.is_dir()]
        st.write(f"  Сайты: {sites}")

    # 2. Директория текущего сайта
    site_dir = sites_dir / current_site
    st.write(f"sites/{current_site}/ существует: {site_dir.exists()}")
    if site_dir.exists():
        domains_dir = site_dir / "domains"
        st.write(f"  domains/ существует: {domains_dir.exists()}")
        if domains_dir.exists():
            domains = [d.name for d in domains_dir.iterdir() if d.is_dir()]
            st.write(f"  Домены: {domains}")

    # 3. Директория текущего домена
    domain_dir = site_dir / "domains" / current_domain
    st.write(f"sites/{current_site}/domains/{current_domain}/ существует: {domain_dir.exists()}")

    # 4. Директория проектов
    projects_dir = domain_dir / "projects" / str(user_id) if user_id else None
    if projects_dir:
        st.write(f"projects/{user_id}/ существует: {projects_dir.exists()}")
        if projects_dir.exists():
            project_files = list(projects_dir.glob("*.json"))
            st.write(f"  Найдено JSON файлов: {len(project_files)}")
            for pf in project_files[:10]:  # показываем первые 10
                st.write(f"    - {pf.name}")

    # 5. Старая структура (для обратной совместимости)
    old_projects_dir = Path(f"projects/{user_id}") if user_id else None
    if old_projects_dir:
        st.write(f"projects/{user_id}/ (старая структура) существует: {old_projects_dir.exists()}")
        if old_projects_dir.exists():
            old_files = list(old_projects_dir.glob("*.json"))
            st.write(f"  Найдено JSON файлов: {len(old_files)}")

    # 6. Если указан конкретный project_id, ищем его
    if project_id:
        st.markdown("---")
        st.markdown(f"#### 🔎 Поиск проекта '{project_id}':")

        # Поиск в новой структуре
        if projects_dir:
            new_path = projects_dir / f"{project_id}.json"
            st.write(f"Новый путь: {new_path}")
            st.write(f"Существует: {new_path.exists()}")
            if new_path.exists():
                try:
                    import json
                    with open(new_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        st.success(f"✅ Проект найден! Название: {data.get('project_name', 'N/A')}")
                except Exception as e:
                    st.error(f"Ошибка чтения: {e}")

        # Поиск в старой структуре
        if old_projects_dir:
            old_path = old_projects_dir / f"{project_id}.json"
            st.write(f"Старый путь: {old_path}")
            st.write(f"Существует: {old_path.exists()}")
            if old_path.exists():
                try:
                    import json
                    with open(old_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        st.success(f"✅ Проект найден в старой структуре! Название: {data.get('project_name', 'N/A')}")
                except Exception as e:
                    st.error(f"Ошибка чтения: {e}")

        # Глобальный поиск
        st.write("---")
        st.write("**Глобальный поиск по всем sites/:**")
        all_files = list(Path("sites").rglob(f"**/projects/*/{project_id}.json"))
        st.write(f"Найдено файлов: {len(all_files)}")
        for f in all_files:
            st.write(f"  - {f}")
def render_diagnostic_button():
    """Рендерит кнопку диагностики и показывает результаты при нажатии"""

    # Кнопка диагностики
    if st.button("🔍 ДИАГНОСТИКА", key="diagnostic_btn_main", use_container_width=True):
        st.session_state.show_diagnostic = not st.session_state.get('show_diagnostic', False)
        st.rerun()

    # Если диагностика включена - показываем детали
    if st.session_state.get('show_diagnostic', False):
        st.markdown("---")
        st.markdown("## 🔬 ДЕТАЛЬНАЯ ДИАГНОСТИКА")

        # Получаем текущие параметры
        user_id = st.session_state.get('user_id')
        current_project_id = st.session_state.get('current_project_id')

        if 'domain_manager' in st.session_state:
            dm = st.session_state.domain_manager
            current_site = dm.site_name
            current_domain = dm.get_current_domain()
        else:
            current_site = st.session_state.get('current_site', 'steelborg')
            current_domain = st.session_state.get('current_domain', 'default')

        st.markdown(f"### 📌 Текущие параметры")
        st.write(f"**User ID:** `{user_id}`")
        st.write(f"**Current site:** `{current_site}`")
        st.write(f"**Current domain:** `{current_domain}`")
        st.write(f"**Current project ID:** `{current_project_id}`")

        st.markdown("---")

        # Проверка путей
        st.markdown("### 📁 Проверка путей к проектам")

        from pathlib import Path

        # Путь в новой структуре
        new_path = Path(f"sites/{current_site}/domains/{current_domain}/projects/{user_id}")
        st.write(f"**Новая структура:** `{new_path}`")
        st.write(f"  Существует: {'✅' if new_path.exists() else '❌'}")

        if new_path.exists():
            files = list(new_path.glob("*.json"))
            st.write(f"  Найдено JSON файлов: {len(files)}")
            for f in files[:10]:
                st.write(f"    - {f.name}")

        # Путь в старой структуре
        old_path = Path(f"projects/{user_id}")
        st.write(f"**Старая структура:** `{old_path}`")
        st.write(f"  Существует: {'✅' if old_path.exists() else '❌'}")

        if old_path.exists():
            files = list(old_path.glob("*.json"))
            st.write(f"  Найдено JSON файлов: {len(files)}")
            for f in files[:10]:
                st.write(f"    - {f.name}")

        st.markdown("---")

        # Поиск конкретного проекта
        if current_project_id:
            st.markdown(f"### 🔎 Поиск проекта `{current_project_id}`")

            # Поиск в новой структуре
            specific_new = new_path / f"{current_project_id}.json"
            st.write(f"**Новая структура:** `{specific_new}`")
            st.write(f"  Существует: {'✅' if specific_new.exists() else '❌'}")

            if specific_new.exists():
                try:
                    import json
                    with open(specific_new, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        st.success(f"✅ Проект найден! Название: {data.get('project_name', 'N/A')}")
                        st.write(f"  Текущая фаза: {data.get('current_phase', 'N/A')}")
                except Exception as e:
                    st.error(f"Ошибка чтения: {e}")

            # Поиск в старой структуре
            specific_old = old_path / f"{current_project_id}.json"
            st.write(f"**Старая структура:** `{specific_old}`")
            st.write(f"  Существует: {'✅' if specific_old.exists() else '❌'}")

            if specific_old.exists():
                try:
                    import json
                    with open(specific_old, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        st.success(f"✅ Проект найден в старой структуре! Название: {data.get('project_name', 'N/A')}")
                except Exception as e:
                    st.error(f"Ошибка чтения: {e}")

        st.markdown("---")

        # Рекомендации
        st.markdown("### 💡 Рекомендации")

        # Проверяем, есть ли проекты в старой структуре, но нет в новой
        if old_path.exists() and new_path.exists():
            old_files = set(f.name for f in old_path.glob("*.json"))
            new_files = set(f.name for f in new_path.glob("*.json"))
            missing = old_files - new_files

            if missing:
                st.warning(f"⚠️ Найдено {len(missing)} проектов в старой структуре, которые отсутствуют в новой!")
                st.write("**Что делать:** Нажмите кнопку 'Синхронизировать проекты' ниже, чтобы скопировать их.")

                if st.button("📦 Синхронизировать проекты (скопировать из старой структуры)", key="sync_projects_btn"):
                    import shutil
                    copied = 0
                    for filename in missing:
                        src = old_path / filename
                        dst = new_path / filename
                        try:
                            shutil.copy(src, dst)
                            copied += 1
                            st.write(f"  ✅ Скопирован: {filename}")
                        except Exception as e:
                            st.write(f"  ❌ Ошибка копирования {filename}: {e}")
                    st.success(f"✅ Скопировано {copied} проектов!")
                    st.rerun()

        # Если нет проектов вообще
        if not new_path.exists() or len(list(new_path.glob("*.json"))) == 0:
            if not old_path.exists() or len(list(old_path.glob("*.json"))) == 0:
                st.info("📭 У вас нет сохраненных проектов. Создайте новый проект через кнопку '➕ Новый проект'.")
            else:
                st.info("📭 Проекты есть в старой структуре, но не скопированы. Нажмите кнопку синхронизации выше.")

        # Кнопка закрытия диагностики
        st.markdown("---")
        if st.button("❌ Закрыть диагностику", key="close_diagnostic", use_container_width=True):
            st.session_state.show_diagnostic = False
            st.rerun()

        st.stop()  # Останавливаем дальнейший рендеринг, пока открыта диагностика
# === КОНСТАНТЫ ===
PROJECTS_DIR = Path("projects")
PROJECTS_DIR.mkdir(exist_ok=True)

# === ГЛОБАЛЬНЫЙ СЛОВАРЬ ДЛЯ СТАТУСА ===
_background_status = {}
_status_lock = threading.Lock()
# === ЛОГИРОВАНИЕ ===

def reset_session_for_new_project():
    """Полный сброс session_state для нового проекта"""
    # Ключи, которые нужно сохранить
    preserve = [
        'authenticated', 'user_id', 'username', 'session_token',
        'current_site', 'current_domain', 'domain_manager',
        'selected_site', 'selected_domain', 'selected_module',
        'module_selected', 'app_mode', 'theme'
    ]

    # Сохраняем нужные ключи
    saved = {}
    for key in preserve:
        if key in st.session_state:
            saved[key] = st.session_state[key]

    # Очищаем всё
    for key in list(st.session_state.keys()):
        if key not in preserve:
            del st.session_state[key]

    # Восстанавливаем
    for key, value in saved.items():
        st.session_state[key] = value
def log(msg, level="INFO"):
    """Логирование для отладки"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {level} | {msg}"
    print(log_line)

    if 'debug_logs' not in st.session_state:
        st.session_state.debug_logs = []
    st.session_state.debug_logs.append(log_line)
    if len(st.session_state.debug_logs) > 150:
        st.session_state.debug_logs = st.session_state.debug_logs[-150:]


def init_queue_manager():
    if 'user_id' not in st.session_state or not st.session_state.user_id:
        return None

    current_site = st.session_state.get('current_site', 'steelborg')
    current_domain = st.session_state.get('current_domain', 'default')

    queue = get_user_queue()
    if queue:
        if hasattr(queue, 'site_name') and hasattr(queue, 'domain_name'):
            if queue.site_name != current_site or queue.domain_name != current_domain:
                print(f"🔄 Обновляем домен в очереди: {queue.domain_name} -> {current_domain}")
                # ✅ НЕ ПЕРЕСОЗДАЕМ! ПРОСТО ОБНОВЛЯЕМ
                queue.site_name = current_site
                queue.domain_name = current_domain
                queue._save_queue()

    return queue
def is_admin() -> bool:
    """Проверяет, является ли текущий пользователь администратором"""
    try:
        from database_settings.database import get_db
        with get_db() as conn:
            user = conn.execute(
                "SELECT is_admin FROM users WHERE id = ?",
                (st.session_state.get("user_id"),)
            ).fetchone()
            return user and user["is_admin"] == 1
    except Exception as e:
        log(f"Ошибка проверки прав администратора: {e}")
        return False
def get_real_project_status(project_id: str, user_id: int):
    """Получает реальный статус проекта из worker'а или файла"""
    manager = st.session_state.get('project_queue_manager')

    # Сначала проверяем в памяти worker'а
    if manager and project_id in manager.projects:
        task = manager.projects[project_id]
        return {
            'status': task.status.value,
            'current_phase': task.current_phase,
            'progress': task.progress,
            'message': task.message,
            'from_worker': True
        }

    # Если нет в памяти, читаем из файла
    project_file = Path(f"projects/{user_id}/{project_id}.json")
    if project_file.exists():
        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    'status': data.get('status', 'unknown'),
                    'current_phase': data.get('current_phase', 1),
                    'progress': data.get('progress', 0),
                    'message': data.get('message', ''),
                    'from_worker': False
                }
        except:
            pass

    return {
        'status': 'unknown',
        'current_phase': 1,
        'progress': 0,
        'message': '',
        'from_worker': False
    }

def update_background_status(project_id: str, status_data: dict):
    with _status_lock:
        _background_status[project_id] = status_data

def get_background_status(project_id: str = None):
    with _status_lock:
        if project_id:
            return _background_status.get(project_id, {})
        return _background_status.copy()

def clear_background_status(project_id: str = None):
    with _status_lock:
        if project_id:
            _background_status.pop(project_id, None)
        else:
            _background_status.clear()

# === СТАТУСЫ ПРОЕКТА ===
class ProjectStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

@dataclass
class ProjectTask:
    project_id: str
    user_id: int
    project_name: str
    category: str
    status: ProjectStatus = ProjectStatus.QUEUED
    current_phase: int = 0
    message: str = ""
    result: Dict = None
    error: str = None
    started_at: str = None
    completed_at: str = None
    progress: float = 0.0
    site_name: str = "steelborg"      # <-- ДОБАВИТЬ
    domain_name: str = "default"
def render_phase6_in_results(app_state):
    """Встраивает интерфейс фазы 6 прямо в результаты"""
    st.markdown("---")
    st.markdown("## 🔄 Фаза 6: Синонимизация текстов")
    st.info("💡 Здесь можно выполнить синонимизацию прямо в результатах, не переключаясь в ручной режим")

    # Импортируем функции из phase6
    from phases.phase6 import (
        init_phase6_structure, load_texts_from_phase5, analyze_texts,
        apply_replacements, render_ngrams_table, render_results,
        ReplacementType, FastSynonymManager, StopWordManager,
        save_to_phase7, SelectionManager, log
    )

    # Инициализация структуры
    init_phase6_structure()

    # Создаём менеджеры
    try:
        syn_manager = FastSynonymManager("synonyms.json")
        stop_manager = StopWordManager(syn_manager)
        selection_manager = SelectionManager()
    except Exception as e:
        st.error(f"Ошибка загрузки синонимов: {e}")
        return

    # Загрузка текстов из фазы 5
    if not st.session_state.phase6.get('texts'):
        texts, metadata = load_texts_from_phase5()
        if texts:
            st.session_state.phase6['texts'] = texts
            st.session_state.phase6['original_texts'] = texts.copy()
            st.session_state.phase6['texts_metadata'] = metadata
            st.success(f"✅ Загружено {len(texts)} текстов из фазы 5")
        else:
            st.warning("⚠️ Нет текстов для синонимизации")
            return

    # Компактный интерфейс вкладок
    tabs = st.tabs([
        "📝 Настройки",
        "📊 Слова",
        "🔤 Биграммы",
        "📚 Триграммы",
        "🔠 N-граммы",
        "📋 Фразы с предлогами",
        "✨ Результаты"
    ])

    # Вкладка настроек
    with tabs[0]:
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔍 Выполнить анализ", key="results_analyze", use_container_width=True):
                if analyze_texts(syn_manager, stop_manager):
                    st.rerun()
        with col2:
            if st.button("🔄 Применить замены", key="results_apply", use_container_width=True):
                if st.session_state.phase6.get('analysis_completed'):
                    if apply_replacements(syn_manager, stop_manager, selection_manager):
                        st.rerun()
                else:
                    st.warning("Сначала выполните анализ")
        with col3:
            if st.button("💾 Сохранить для фазы 7", key="results_save", use_container_width=True):
                if save_to_phase7():
                    st.success("✅ Сохранено!")

    # Вкладки с n-граммами (упрощённо)
    with tabs[1]:
        if st.session_state.phase6.get('unigrams'):
            render_ngrams_table(
                st.session_state.phase6.get('unigrams', {}),
                ReplacementType.UNIGRAM,
                "слова",
                syn_manager,
                selection_manager
            )

    with tabs[2]:
        if st.session_state.phase6.get('bigrams'):
            render_ngrams_table(
                st.session_state.phase6.get('bigrams', {}),
                ReplacementType.BIGRAM,
                "биграммы",
                syn_manager,
                selection_manager
            )

    with tabs[3]:
        if st.session_state.phase6.get('trigrams'):
            render_ngrams_table(
                st.session_state.phase6.get('trigrams', {}),
                ReplacementType.TRIGRAM,
                "триграммы",
                syn_manager,
                selection_manager
            )

    with tabs[4]:
        if st.session_state.phase6.get('ngrams'):
            render_ngrams_table(
                st.session_state.phase6.get('ngrams', {}),
                ReplacementType.NGRAM,
                "n-граммы",
                syn_manager,
                selection_manager
            )

    with tabs[5]:
        if st.session_state.phase6.get('prepositional'):
            render_ngrams_table(
                st.session_state.phase6.get('prepositional', {}),
                ReplacementType.PREPOSITIONAL,
                "фразы с предлогами",
                syn_manager,
                selection_manager
            )

    with tabs[6]:
        if st.session_state.phase6.get('replacements_applied'):
            render_results()
        else:
            st.info("👆 Выполните анализ и примените замены")

    # Логи
    with st.expander("🐛 Логи", expanded=False):
        logs = st.session_state.get('phase6_logs', [])
        if logs:
            st.code("\n".join(logs[-20:]))


def render_phase7_in_results(app_state):
    """Встраивает интерфейс фазы 7 прямо в результаты"""
    st.markdown("---")
    st.markdown("## 📊 Фаза 7: Подготовка к загрузке")

    try:
        from phases.phase7 import main as phase7_main
        # Запускаем phase7.main в режиме просмотра
        phase7_main(app_state=app_state, settings_mode=False)
    except Exception as e:
        st.error(f"Ошибка загрузки фазы 7: {e}")
# === ГЛОБАЛЬНЫЙ МЕНЕДЖЕР ПРОЕКТОВ ===
# === ГЛОБАЛЬНЫЙ МЕНЕДЖЕР ПРОЕКТОВ (улучшенная версия) ===
# === ГЛОБАЛЬНЫЙ МЕНЕДЖЕР ПРОЕКТОВ (С СОХРАНЕНИЕМ ОЧЕРЕДИ) ===

# Инициализация менеджера
# Инициализация менеджера очередей


# === CSS СТИЛИ ===
def local_css():
    st.markdown("""
    <style>
        .stApp { background-color: #faf7f2; color: #3e3a36; }
        h1, h2, h3, h4, h5, h6 { color: #5e4b3c !important; font-family: 'Courier New', monospace; }
        .stButton>button { background-color: #e6dacd; color: #4a3f38; border: 1px solid #b7a99a; border-radius: 6px; font-size: 14px; padding: 4px 12px; transition: 0.2s; font-family: 'Courier New', monospace; }
        .stButton>button:hover { background-color: #d4c3b2; border-color: #8c7a6a; }
        div.stAlert { background-color: #f0ebe4; border-left: 4px solid #b08968; color: #3e3a36; border-radius: 0; }
        div.stSuccess { background-color: #e6f0da; border-left: 4px solid #7f9f6f; }
        div.stWarning { background-color: #fff1d6; border-left: 4px solid #e6b89c; }
        div.stInfo { background-color: #e1e7e0; border-left: 4px solid #8d9f87; }
        hr { border-top: 1px solid #d4c3a2; }
        .block-container { padding-top: 1rem; padding-bottom: 1rem; }
        .mode-card { background-color: #f5f0e6; border-radius: 12px; padding: 30px; text-align: center; transition: all 0.3s ease; border: 2px solid #e6dacd; }
        .mode-card:hover { border-color: #b08968; transform: translateY(-5px); box-shadow: 0 10px 20px rgba(0,0,0,0.1); }
        .status-running { color: #3b82f6; font-weight: bold; }
        .status-completed { color: #10b981; font-weight: bold; }
        .status-failed { color: #ef4444; font-weight: bold; }
        .status-queued { color: #f59e0b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# === КЛАСС УПРАВЛЕНИЯ СОСТОЯНИЕМ ===
class AppState:
    def __init__(self):
        # ✅ НЕ СОЗДАЁМ ПРОЕКТ АВТОМАТИЧЕСКИ!
        if 'current_project_id' not in st.session_state:
            st.session_state.current_project_id = None

        if 'current_phase' not in st.session_state:
            st.session_state.current_phase = 1

        # ✅ НЕ ПЕРЕЗАПИСЫВАЕМ app_data, если он уже существует
        # ДОЛЖНО БЫТЬ (ХОРОШО):
        if 'app_data' not in st.session_state or st.session_state.app_data is None:
            # ТОЛЬКО если нет данных - создаем новые
            st.session_state.app_data = {
                'phase1': {}, 'phase2': {}, 'phase3': {}, 'phase4': {},
                'phase5': {}, 'phase6': {}, 'phase7': {},
                'category': '',
                'project_name': '',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'phase5_completed': False
            }
        else:
            # Убеждаемся, что все необходимые ключи есть
            for phase in range(1, 8):
                if f'phase{phase}' not in st.session_state.app_data:
                    st.session_state.app_data[f'phase{phase}'] = {}

        # Инициализируем отдельные ключи для каждой фазы в session_state
        for i in range(1, 8):
            phase_key = f'phase{i}'
            if phase_key not in st.session_state:
                st.session_state[phase_key] = {}

        # Инициализируем другие важные ключи
        if 'phase5_settings' not in st.session_state:
            st.session_state.phase5_settings = {}
        if 'phase4_generated_prompts' not in st.session_state:
            st.session_state.phase4_generated_prompts = {}
        if 'phase4_char_settings' not in st.session_state:
            st.session_state.phase4_char_settings = {}
        if 'phase4_other_blocks_settings' not in st.session_state:
            st.session_state.phase4_other_blocks_settings = {}
        if 'phase4_global_prompts' not in st.session_state:
            st.session_state.phase4_global_prompts = {}
        if 'phase5_prompts' not in st.session_state:
            st.session_state.phase5_prompts = []
        if 'phase6_logs' not in st.session_state:
            st.session_state.phase6_logs = []

        if 'show_project_selector' not in st.session_state:
            st.session_state.show_project_selector = False
        if 'current_project_id' not in st.session_state:
            st.session_state.current_project_id = None
        if 'show_queue_panel' not in st.session_state:
            st.session_state.show_queue_panel = False
        if 'auto_refresh' not in st.session_state:
            st.session_state.auto_refresh = False
        if 'app_mode' not in st.session_state:
            st.session_state.app_mode = None
        if 'view_mode' not in st.session_state:
            st.session_state.view_mode = 'settings'
        if 'show_project_settings' not in st.session_state:
            st.session_state.show_project_settings = False
    def save_current_domain_phase(self, phase: int):
        """Сохраняет данные текущей фазы в домен - ОТКЛЮЧЕНО (данные только в проекте)"""
        # ❌ УДАЛИТЬ ВЕСЬ КОД
        pass

    def _convert_ngram_info_to_serializable(self, obj):
        if obj is None:
            return None

        # Проверяем, является ли объект NGramInfo
        if hasattr(obj, '__class__') and obj.__class__.__name__ == 'NGramInfo':
            return obj.to_dict() if hasattr(obj, 'to_dict') else {
                'text': getattr(obj, 'text', ''),
                'count': getattr(obj, 'count', 0),
                'length': getattr(obj, 'length', 0),
                'positions': getattr(obj, 'positions', []),
                'replace': getattr(obj, 'replace', True),
                'synonyms': getattr(obj, 'synonyms', []),
                'forms': getattr(obj, 'forms', {}),
                'original_forms': getattr(obj, 'original_forms', []),
                'has_prepositions': getattr(obj, 'has_prepositions', False),
                'is_stopword': getattr(obj, 'is_stopword', False),
                '__class__': 'NGramInfo'
            }
        elif isinstance(obj, dict):
            return {k: self._convert_ngram_info_to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_ngram_info_to_serializable(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_ngram_info_to_serializable(item) for item in obj)
        else:
            return obj
    def force_save_phase6_to_phase7(self):
        """Принудительно сохраняет данные из фазы 6 в фазу 7"""

        if 'phase6' not in st.session_state:
            return False

        phase6_data = st.session_state.phase6

        # Создаём данные для фазы 7
        phase7_data = {
            'fragments_count': len(phase6_data.get('processed_texts', [])),
            'fragment_names': list(set(m.get('fragment_name', '') for m in phase6_data.get('texts_metadata', []))),
            'category_code': st.session_state.app_data.get('category', ''),
            'last_modified': datetime.now().isoformat(),
            'blocks': []
        }

        # Конвертируем блоки
        for idx, text in enumerate(phase6_data.get('processed_texts', [])):
            meta = phase6_data.get('texts_metadata', [{}])[idx] if idx < len(phase6_data.get('texts_metadata', [])) else {}

            block = {
                'id': meta.get('prompt_id', f'block_{idx}'),
                'fragment_name': meta.get('fragment_name', f'Фрагмент_{idx}'),
                'original_text': phase6_data.get('original_texts', [''])[idx] if idx < len(phase6_data.get('original_texts', [])) else '',
                'processed_text': text,
                'html_text': '',
                'block_type': meta.get('type', 'other'),
                'characteristic_name': meta.get('characteristic_name', ''),
                'characteristic_value': meta.get('characteristic_value', ''),
                'errors': [],
                'warnings': [],
                'status': 'processed',
                'manually_fixed': False,
                'special_symbols': [],
                'auto_corrected': False,
                'added_value': None
            }
            phase7_data['blocks'].append(block)

        # Сохраняем
        st.session_state.app_data['phase7'] = phase7_data
        self.save_project()

        return True
    # В классе AppState, ЗАМЕНИТЕ методы sync_app_data_with_session_state
    # и sync_session_state_with_app_data на:


    # from phase_sync import PhaseSyncManager  # ← УДАЛИ или ЗАКОММЕНТИРУЙ

    # и в методах AppState:
    def sync_app_data_with_session_state(self):
        """Синхронизирует данные из session_state в app_data"""
        # from phase_sync import PhaseSyncManager  # ← ЗАКОММЕНТИРУЙ
        # return PhaseSyncManager.sync_all_to_app_data(self)
        return True  # ← ПРОСТО ВОЗВРАЩАЕМ True

    def sync_session_state_with_app_data(self):
        """Синхронизирует данные из app_data в session_state"""
        # from phase_sync import PhaseSyncManager  # ← ЗАКОММЕНТИРУЙ
        # return PhaseSyncManager.sync_all_from_app_data(self)
        return True  # ← ПРОСТО ВОЗВРАЩАЕМ True

    def force_sync_all_data(self):
        """Принудительная полная синхронизация всех данных"""
        log("=== force_sync_all_data started ===")
        # Просто сохраняем проект
        self.save_project()
        log("=== force_sync_all_data completed ===")
        return True

    def get_phase_data(self, phase: int) -> Dict:
        return st.session_state.app_data.get(f'phase{phase}', {})

    def set_phase_data(self, phase: int, data: Dict):
        st.session_state.app_data[f'phase{phase}'] = data
        setattr(st.session_state, f'phase{phase}', data)
        st.session_state.app_data['updated_at'] = datetime.now().isoformat()
        self.save_project()

    # В классе AppState, заменить метод save_project:

    def save_project(self, max_retries: int = 3):
        """Сохраняет проект - С ПРИНУДИТЕЛЬНЫМ СОХРАНЕНИЕМ ВСЕХ ФАЗ"""

        # ✅ ПРОВЕРЯЕМ И СОХРАНЯЕМ PHASE1
        if 'phase1' in st.session_state and st.session_state.phase1:
            if 'phase1' not in st.session_state.app_data:
                st.session_state.app_data['phase1'] = {}
            st.session_state.app_data['phase1'] = st.session_state.phase1
            print(f"✅ Сохранена phase1: {len(st.session_state.phase1.get('characteristics', {}))} характеристик")

        # ✅ ПРОВЕРЯЕМ И СОХРАНЯЕМ PHASE2
        if 'phase2' in st.session_state and st.session_state.phase2:
            if 'phase2' not in st.session_state.app_data:
                st.session_state.app_data['phase2'] = {}
            st.session_state.app_data['phase2'] = st.session_state.phase2
            print(f"✅ Сохранена phase2: {len(st.session_state.phase2.get('markers', {}))} маркеров")

        # ✅ ПРОВЕРЯЕМ И СОХРАНЯЕМ PHASE3
        if 'phase3' in st.session_state and st.session_state.phase3:
            if 'phase3' not in st.session_state.app_data:
                st.session_state.app_data['phase3'] = {}
            st.session_state.app_data['phase3'] = st.session_state.phase3
            print(f"✅ Сохранена phase3: {len(st.session_state.phase3.get('blocks', {}))} блоков")

        # ... остальной код save_project без изменений ...
        if 'current_project_id' not in st.session_state or not st.session_state.current_project_id:
            print("❌ save_project: current_project_id = None, пропускаем сохранение!")
            return False

        if 'user_id' not in st.session_state or not st.session_state.user_id:
            print("❌ save_project: user_id отсутствует, пропускаем сохранение!")
            return False




        # ========== 2. ЯВНО СОХРАНЯЕМ phase4_generated_prompts ==========
        if st.session_state.get('phase4_generated_prompts'):
            prompts = st.session_state.phase4_generated_prompts
            if 'phase4' not in st.session_state.app_data:
                st.session_state.app_data['phase4'] = {}

            if isinstance(prompts, dict):
                st.session_state.app_data['phase4']['prompts'] = list(prompts.values())
                st.session_state.app_data['phase4']['generated_count'] = len(prompts)
            elif isinstance(prompts, list):
                st.session_state.app_data['phase4']['prompts'] = prompts
                st.session_state.app_data['phase4']['generated_count'] = len(prompts)
            else:
                st.session_state.app_data['phase4']['prompts'] = []
                st.session_state.app_data['phase4']['generated_count'] = 0

            print(f"🔥 ЯВНО СОХРАНЕНЫ phase4_generated_prompts: {st.session_state.app_data['phase4']['generated_count']} промптов")

        # ========== 3. ЯВНО СОХРАНЯЕМ phase5_results ==========
        if st.session_state.get('phase5_results'):
            results = st.session_state.phase5_results
            if 'phase5' not in st.session_state.app_data:
                st.session_state.app_data['phase5'] = {}

            st.session_state.app_data['phase5']['results'] = results
            st.session_state.app_data['phase5']['phase_completed'] = st.session_state.get('phase5_completed', False)
            st.session_state.app_data['phase5_completed'] = st.session_state.get('phase5_completed', False)

            print(f"🔥 ЯВНО СОХРАНЕНЫ phase5_results: {len(results)} результатов")

            # ... остальной код save_project без изменений ...

        # ========== 3. ЯВНО СОХРАНЯЕМ phase5_results В app_data.phase5 ==========
        if st.session_state.get('phase5_results'):
            results = st.session_state.phase5_results
            if 'phase5' not in st.session_state.app_data:
                st.session_state.app_data['phase5'] = {}

            # Сохраняем результаты
            st.session_state.app_data['phase5']['results'] = results
            st.session_state.app_data['phase5']['phase_completed'] = st.session_state.get('phase5_completed', False)
            st.session_state.app_data['phase5_completed'] = st.session_state.get('phase5_completed', False)

            print(f"🔥 ЯВНО СОХРАНЕНЫ phase5_results: {len(results)} результатов")

            # Сохраняем статистику
            if st.session_state.get('phase5_statistics'):
                st.session_state.app_data['phase5']['statistics'] = st.session_state.phase5_statistics
                print(f"🔥 ЯВНО СОХРАНЕНА phase5_statistics")

        # ========== 4. ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: если phase4_generated_prompts пуст, но phase4 в app_data не пуст ==========
        if not st.session_state.get('phase4_generated_prompts') and st.session_state.app_data.get('phase4', {}).get('prompts'):
            print("⚠️ Восстанавливаем phase4_generated_prompts из app_data.phase4.prompts перед сохранением")
            prompts_list = st.session_state.app_data['phase4']['prompts']
            if isinstance(prompts_list, list):
                st.session_state.phase4_generated_prompts = prompts_list

        # ========== 5. ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА для phase5 ==========
        if not st.session_state.get('phase5_results') and st.session_state.app_data.get('phase5', {}).get('results'):
            print("⚠️ Восстанавливаем phase5_results из app_data.phase5.results перед сохранением")
            st.session_state.phase5_results = st.session_state.app_data['phase5']['results']

        # ========== 6. ПРОВЕРЯЕМ ЧТО СОХРАНЯЕМ ==========
        has_phase4 = bool(st.session_state.app_data.get('phase4', {}).get('prompts')) or bool(st.session_state.get('phase4_generated_prompts'))
        has_phase5 = bool(st.session_state.app_data.get('phase5', {}).get('results')) or bool(st.session_state.get('phase5_results'))

        print(f"   phase4 в сохраняемых данных: {has_phase4}")
        print(f"   phase5 в сохраняемых данных: {has_phase5}")

        # ========== 7. ПОЛУЧАЕМ ТЕКУЩИЙ САЙТ И ДОМЕН ==========
        if 'domain_manager' not in st.session_state:
            from domain_manager import DomainManager
            st.session_state.domain_manager = DomainManager()

        dm = st.session_state.domain_manager
        current_site = dm.site_name
        current_domain = dm.get_current_domain()

        # ========== 8. ВРЕМЕННО УДАЛЯЕМ НЕСЕРИАЛИЗУЕМЫЕ ОБЪЕКТЫ ==========
        problematic_keys = [
            'ai_config_manager', 'project_queue_manager', 'block_manager',
            'variable_manager', 'dynamic_var_manager', 'ai_instruction_manager',
            'fragment_manager', 'transformation_registry'
        ]

        saved_objects = {}
        for key in problematic_keys:
            if key in st.session_state:
                saved_objects[key] = st.session_state[key]
                del st.session_state[key]

        try:
            # ========== 9. ФИНАЛЬНАЯ СИНХРОНИЗАЦИЯ ПЕРЕД СОХРАНЕНИЕМ ==========


            from project_manager import ProjectManager
            pm = ProjectManager(
                user_id=st.session_state.user_id,
                site_name=current_site,
                domain_name=current_domain
            )

            # ========== 10. ПОДГОТАВЛИВАЕМ ДАННЫЕ ДЛЯ СОХРАНЕНИЯ ==========
            data_to_save = {
                "project_id": st.session_state['current_project_id'],
                "project_name": st.session_state.app_data.get('project_name', 'Новый проект'),
                "category": st.session_state.app_data.get('category', ''),
                "current_phase": st.session_state.current_phase,
                "app_data": st.session_state.app_data.copy(),
                "created_at": st.session_state.app_data.get('created_at', datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat(),
                "site_name": current_site,
                "domain_name": current_domain,
                "user_id": st.session_state.user_id
            }

            # ========== 11. ЕЩЕ РАЗ ПРОВЕРЯЕМ ЧТО ДАННЫЕ В data_to_save ==========
            if has_phase4:
                print(f"   В data_to_save: phase4.prompts = {len(data_to_save['app_data'].get('phase4', {}).get('prompts', []))}")
            if has_phase5:
                print(f"   В data_to_save: phase5.results = {len(data_to_save['app_data'].get('phase5', {}).get('results', {}))}")

            # ========== 12. СОХРАНЯЕМ ==========
            result = pm.save_project(data_to_save)

            if result:
                print(f"✅ Проект успешно сохранен: sites/{current_site}/domains/{current_domain}/projects/{st.session_state.user_id}/{st.session_state.current_project_id}.json")
            else:
                print(f"❌ Ошибка при сохранении проекта")

            return result

        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            # ========== 13. ВОССТАНАВЛИВАЕМ УДАЛЕННЫЕ ОБЪЕКТЫ ==========
            for key, value in saved_objects.items():
                st.session_state[key] = value
    def debug_dump_state(self, context: str = ""):
        """Выводит в лог текущее состояние session_state (только ключи проекта)"""
        log(f"=== DEBUG: {context} ===")
        log(f"current_project_id: {st.session_state.get('current_project_id')}")
        log(f"app_data keys: {list(st.session_state.get('app_data', {}).keys()) if st.session_state.get('app_data') else 'None'}")
        log(f"app_data['project_name']: {st.session_state.get('app_data', {}).get('project_name')}")
        log(f"app_data['category']: {st.session_state.get('app_data', {}).get('category')}")
        log(f"phase1 keys: {list(st.session_state.get('phase1', {}).keys())}")
        log(f"phase2 keys: {list(st.session_state.get('phase2', {}).keys())}")
        log(f"phase3 keys: {list(st.session_state.get('phase3', {}).keys())}")
        log(f"block_manager exists: {'block_manager' in st.session_state}")
        if 'block_manager' in st.session_state:
            try:
                blocks = st.session_state.block_manager.get_all_blocks()
                log(f"block_manager blocks count: {len(blocks)}")
            except:
                log("block_manager error")
        log("==========================")
    def _rebuild_managers_from_app_data(self):
        """Пересоздаёт менеджеры и загружает в них данные из app_data"""
        try:
            from phases.phase3 import BlockManager, VariableManager, DynamicVariableManager
            from ai_settings.ai_module import AIInstructionManager

            # Создаём новые менеджеры
            st.session_state.block_manager = BlockManager()
            st.session_state.variable_manager = VariableManager(st.session_state.block_manager)
            st.session_state.dynamic_var_manager = DynamicVariableManager()
            st.session_state.ai_instruction_manager = AIInstructionManager()

            # Загружаем блоки из phase3
            phase3_data = st.session_state.app_data.get('phase3', {})
            blocks = phase3_data.get('blocks', {})
            if blocks:
                # Прямое присвоение внутреннего словаря (работает, если менеджер имеет атрибут blocks)
                if hasattr(st.session_state.block_manager, 'blocks'):
                    st.session_state.block_manager.blocks = blocks
                else:
                    # Если нет, пытаемся добавить через API
                    for block_id, block_info in blocks.items():
                        name = block_info.get('name', block_id)
                        block_type = block_info.get('block_type', 'other')
                        variables = block_info.get('variables', [])
                        st.session_state.block_manager.add_block(name, block_type, variables)

            # Загружаем AI инструкции
            ai_instructions = phase3_data.get('ai_instructions', {})
            if ai_instructions and hasattr(st.session_state.ai_instruction_manager, 'instructions'):
                st.session_state.ai_instruction_manager.instructions = ai_instructions

            log("✅ Менеджеры пересозданы и загружены из app_data")
        except Exception as e:
            log(f"⚠️ Ошибка при пересоздании менеджеров: {e}")

    # ============================================
    # 5. ИСПРАВЛЕННЫЙ AppState.load_project
    # ============================================

    # main_app.py - ЗАМЕНИТЬ МЕТОД AppState.load_project

    def load_project(self, project_id: str) -> bool:
        """Загружает проект - С ВОССТАНОВЛЕНИЕМ ВСЕХ ФАЗ В session_state"""
        print(f"📂 load_project: {project_id}")

        user_id = st.session_state.get('user_id')
        if not user_id:
            print("❌ Нет user_id")
            return False

        # Берем текущий домен
        if 'domain_manager' not in st.session_state:
            from domain_manager import DomainManager
            st.session_state.domain_manager = DomainManager()

        dm = st.session_state.domain_manager
        current_site = dm.site_name
        current_domain = dm.get_current_domain()

        project_file = Path(f"sites/{current_site}/domains/{current_domain}/projects/{user_id}/{project_id}.json")

        if not project_file.exists():
            print(f"❌ Проект не найден в домене {current_domain}")
            st.error(f"❌ Проект не найден в домене {current_domain}")
            return False

        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Ошибка чтения: {e}")
            return False

        # ✅ ВОССТАНАВЛИВАЕМ ВСЕ ФАЗЫ В session_state
        app_data = data.get('app_data', {})

        # Phase 1
        if 'phase1' in app_data:
            st.session_state.phase1 = app_data['phase1']
            print(f"✅ Восстановлена phase1: {len(st.session_state.phase1.get('characteristics', {}))} характеристик")

        # Phase 2
        if 'phase2' in app_data:
            st.session_state.phase2 = app_data['phase2']
            print(f"✅ Восстановлена phase2: {len(st.session_state.phase2.get('markers', {}))} маркеров")

        # Phase 3
        if 'phase3' in app_data:
            st.session_state.phase3 = app_data['phase3']
            print(f"✅ Восстановлена phase3: {len(st.session_state.phase3.get('blocks', {}))} блоков")

        # Сохраняем остальные данные
        st.session_state.current_project_id = project_id
        st.session_state.current_phase = data.get('current_phase', 1)
        st.session_state.app_data = app_data

        # Сохраняем категорию
        category = data.get('category')
        if not category:
            category = app_data.get('category')
        if not category:
            category = app_data.get('phase1', {}).get('category')
        if category:
            st.session_state.app_data['category'] = category
            if 'phase1' not in st.session_state.app_data:
                st.session_state.app_data['phase1'] = {}
            st.session_state.app_data['phase1']['category'] = category

        # Загружаем настройки фаз
        self._load_phase_settings(data)

        print(f"✅ Проект загружен: {project_id} в домене {current_domain}")
        return True

    def _load_phase_settings(self, data: Dict):
        """Загружает настройки фаз из данных"""
        # Phase 4 настройки
        phase4_settings = data.get('app_data', {}).get('phase4_settings', {})
        if phase4_settings:
            st.session_state.phase4_settings = phase4_settings
            st.session_state.phase4_char_settings = phase4_settings.get('char_settings', {})
            st.session_state.phase4_other_blocks_settings = phase4_settings.get('other_blocks_settings', {})
            st.session_state.phase4_global_prompts = phase4_settings.get('global_prompts', 3)
            st.session_state.phase4_global_other_prompts = phase4_settings.get('global_other_prompts', 20)
            st.session_state.selected_regular_block_id = phase4_settings.get('selected_regular_block_id')
            st.session_state.selected_unique_block_id = phase4_settings.get('selected_unique_block_id')
        else:
            # Дефолтные значения
            st.session_state.phase4_global_prompts = 3
            st.session_state.phase4_global_other_prompts = 20
            st.session_state.phase4_char_settings = {}
            st.session_state.phase4_other_blocks_settings = {}

        # Phase 5 настройки
        phase5_settings = data.get('app_data', {}).get('phase5_settings', {})
        if phase5_settings:
            st.session_state.phase5_settings = phase5_settings

        # Phase 4 промпты
        prompts = data.get('app_data', {}).get('phase4', {}).get('prompts', [])
        if prompts:
            st.session_state.phase4_generated_prompts = prompts
        else:
            st.session_state.phase4_generated_prompts = []

        # Phase 5 результаты
        results = data.get('app_data', {}).get('phase5', {}).get('results', {})
        if results:
            st.session_state.phase5_results = results
            st.session_state.phase5_completed = True
        else:
            st.session_state.phase5_results = {}
            st.session_state.phase5_completed = False

    def create_new_project(self, category: str = "Новая категория"):
        """Создает новый проект — АБСОЛЮТНО ЧИСТЫЙ"""
        import uuid
        import json
        from pathlib import Path
        from datetime import datetime
        import streamlit as st
        import time
        import shutil

        category = (category or "Новая категория").strip()

        if st.session_state.get('project_creating'):
            return
        st.session_state.project_creating = True

        try:
            print(f"\n🚀 СОЗДАНИЕ НОВОГО ПРОЕКТА: {category}")

            user_id = st.session_state.get('user_id')
            if not user_id:
                st.error("❌ Пользователь не авторизован")
                return

            if 'domain_manager' in st.session_state:
                dm = st.session_state.domain_manager
                current_site = dm.site_name
                current_domain = dm.get_current_domain()
            else:
                current_site = st.session_state.get('current_site', 'steelborg')
                current_domain = st.session_state.get('current_domain', 'default')

            new_project_id = str(uuid.uuid4())
            project_dir = Path(f"sites/{current_site}/domains/{current_domain}/projects/{user_id}")
            project_dir.mkdir(parents=True, exist_ok=True)

            # ========== СОЗДАЁМ АБСОЛЮТНО ПУСТОЙ ФАЙЛ ==========
            project_file = project_dir / f"{new_project_id}.json"

            # ✅ ВАЖНО: НЕ копируем старые данные!
            project_data = {
                "project_id": new_project_id,
                "project_name": category,
                "category": category,
                "user_id": user_id,
                "site_name": current_site,
                "domain_name": current_domain,
                "current_phase": 1,
                "status": "idle",
                "progress": 0,
                "message": "Новый проект",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "app_data": {
                    "phase1": {},
                    "phase2": {},
                    "phase3": {},      # ← ПУСТО!
                    "phase4": {},      # ← ПУСТО!
                    "phase5": {},      # ← ПУСТО! (здесь хранятся результаты)
                    "phase6": {},
                    "phase7": {},
                    "category": category,
                    "project_name": category,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "phase5_completed": False,
                    "phase5_results": {},        # ← ЯВНО ПУСТО!
                    "phase4_generated_prompts": [],  # ← ЯВНО ПУСТО!
                    "site_name": current_site,
                    "domain_name": current_domain
                }
            }

            # Сохраняем файл
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)

            print(f"   ✅ Файл создан: {project_file}")

            # ========== ОЧИЩАЕМ session_state (НО НЕ ВСЁ!) ==========
            # Очищаем только данные фаз
            # Очищаем только данные фаз
            for phase in ['phase1', 'phase2', 'phase3', 'phase4', 'phase5', 'phase6', 'phase7']:
                if phase in st.session_state:
                    st.session_state[phase] = {}

            # Очищаем результаты
            st.session_state.phase4_generated_prompts = []
            st.session_state.phase5_results = {}
            st.session_state.phase5_completed = False
            st.session_state.phase5_statistics = {}
            st.session_state.phase5_prompts = []
            st.session_state.phase6 = {}
            st.session_state.phase6_logs = []

            # ✅ ОЧИЩАЕМ НАСТРОЙКИ ФАЗ 4 И 5
            st.session_state.phase4_char_settings = {}
            st.session_state.phase4_other_blocks_settings = {}
            st.session_state.phase4_global_prompts = 3
            st.session_state.phase4_global_other_prompts = 20
            st.session_state.phase4_settings = {}
            st.session_state.selected_regular_block_id = None
            st.session_state.selected_unique_block_id = None
            st.session_state.phase5_settings = {}
            # Устанавливаем новый проект
            st.session_state.current_project_id = new_project_id
            st.session_state.current_phase = 1
            st.session_state.app_data = project_data['app_data'].copy()

            # ========== ОЧИЩАЕМ AI ИНСТРУКЦИИ ДЛЯ НОВОГО ПРОЕКТА ==========
            if 'ai_instruction_manager' in st.session_state:
                # Пересоздаём AI менеджер для нового проекта
                from ai_settings.ai_module import AIInstructionManager
                st.session_state.ai_instruction_manager = AIInstructionManager(
                    project_id=new_project_id,
                    user_id=user_id,
                    site_name=current_site,
                    domain_name=current_domain
                )
                # Очищаем инструкции
                st.session_state.ai_instruction_manager.instructions = {}

            # ========== ОЧИЩАЕМ ОЧЕРЕДЬ ==========
            from user_queue_manager import get_user_queue
            queue = get_user_queue()
            if queue:
                # Удаляем все проекты из очереди
                for pid in list(queue.projects.keys()):
                    queue.remove_project(pid)
                queue._save_queue()

            st.success(f"✅ Создан **чистый** проект: **{category}**")
            print(f"✅ Проект {category} успешно создан")
            st.session_state._new_project_created = True
            time.sleep(0.5)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if 'project_creating' in st.session_state:
                del st.session_state.project_creating

    def validate_project_data(self) -> Dict:
        issues = []

        phase1_data = self.get_phase_data(1)
        if not phase1_data or not phase1_data.get('characteristics'):
            issues.append("Фаза 1: Нет данных о характеристиках")

        phase2_data = self.get_phase_data(2)
        if not phase2_data or not phase2_data.get('markers'):
            issues.append("Фаза 2: Нет данных о маркерах (опционально)")

        phase3_data = self.get_phase_data(3)
        if not phase3_data:
            issues.append("Фаза 3: Нет AI-инструкций (будут сгенерированы автоматически)")

        return {
            'valid': len([i for i in issues if 'опционально' not in i and 'будут сгенерированы' not in i]) == 0,
            'issues': issues,
            'can_proceed_to_phase3': bool(phase1_data and phase1_data.get('characteristics'))
        }

# === ВЫБОР ПРОЕКТА ===
def render_project_selector():
    if not st.session_state.get('show_project_selector', False):
        # ✅ ДОБАВИТЬ ДИАГНОСТИКУ
        print("⚠️ render_project_selector: show_project_selector = False")
        return
    app_state = AppState()

    print("✅ render_project_selector: show_project_selector = True")
    print(f"   user_id: {st.session_state.get('user_id')}")
    print(f"   current_site: {st.session_state.get('current_site')}")
    print(f"   current_domain: {st.session_state.get('current_domain')}")
    if not st.session_state.get('current_project_id'):
        st.session_state.show_project_selector = True
    st.session_state.show_project_settings = False
    st.markdown("## 📁 Мои проекты")
    st.markdown("---")
    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager()
    dm = st.session_state.domain_manager

    pm = ProjectManager(
        user_id=st.session_state.user_id,
        site_name=dm.site_name,
        domain_name=dm.get_current_domain()
    )
    projects = pm.get_all_projects()
    if projects is None:
        projects = []
    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown("### Доступные проекты")
    with col2:
        if st.button("➕ Новый проект", use_container_width=True, type="primary"):

            st.session_state.show_new_project_form = True
    if st.session_state.get('show_new_project_form', False):
        with st.form(key="new_project_form_selector"):
            new_category = st.text_input("Название категории", key="new_category_selector")
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("Создать", key=...):
                    if new_category and new_category.strip():
                        app_state = AppState()
                        app_state.create_new_project(new_category.strip())
                        st.session_state.show_new_project_form = False
                        # Важно: сразу переключаемся на новый проект
                        st.rerun()
            with col2:
                if st.form_submit_button("Отмена", key="cancel_new_project_selector"):
                    st.session_state.show_new_project_form = False
                    st.rerun()
    st.markdown("---")
    if not projects:
        st.info("📭 У вас пока нет сохраненных проектов. Создайте новый проект, чтобы начать работу.")

        # ✅ КНОПКА СОЗДАНИЯ В БЛОКЕ "НЕТ ПРОЕКТОВ"
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("➕ Создать первый проект", use_container_width=True, type="primary"):
                st.session_state.show_new_project_form = True
                st.rerun()

        st.markdown("---")
        if st.button("← Назад", key="back_from_empty", use_container_width=True):
            st.session_state.show_project_selector = False
            st.rerun()
        return
    col1, col2, col3 = st.columns(3)
    with col1:
        search_query = st.text_input("🔍 Поиск", placeholder="Название или категория...")
    with col2:
        filter_phase = st.selectbox("Фильтр по фазе", ["Все", "Фаза 1", "Фаза 2", "Фаза 3", "Фаза 4", "Фаза 5", "Фаза 6", "Фаза 7", "Завершены"])
    with col3:
        sort_by = st.selectbox("Сортировка", ["По дате изменения", "По названию", "По категории"])
    filtered_projects = projects.copy()
    if search_query:
        filtered_projects = [p for p in filtered_projects if search_query.lower() in p['project_name'].lower() or search_query.lower() in p['category'].lower()]
    if filter_phase != "Все":
        if filter_phase == "Завершены":
            filtered_projects = [p for p in filtered_projects if p['current_phase'] == 7]
        else:
            phase_num = int(filter_phase.split()[1])
            filtered_projects = [p for p in filtered_projects if p['current_phase'] == phase_num]
    if sort_by == "По названию":
        filtered_projects.sort(key=lambda x: x['project_name'])
    elif sort_by == "По категории":
        filtered_projects.sort(key=lambda x: x['category'])
    else:
        filtered_projects.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    for project in filtered_projects:
        with st.container():
            col1, col2, col3, col4 = st.columns([4, 2, 1.5, 1.5])
            with col1:
                phase_icons = {1: "📦", 2: "🏷️", 3: "📝", 4: "🚀", 5: "📄", 6: "🔄", 7: "📊"}
                icon = phase_icons.get(project['current_phase'], "📁")
                st.markdown(f"**{icon} {project['project_name']}**")
                st.caption(f"📂 {project['category']}")
            with col2:
                progress = project['current_phase'] / 7
                st.progress(progress, text=f"Фаза {project['current_phase']}/7")
            with col3:
                if project.get('updated_at'):
                    updated = datetime.fromisoformat(project['updated_at']).strftime("%d.%m.%Y")
                    st.caption(f"📅 {updated}")
            with col4:
                if st.button("Открыть", key=f"open_{project['project_id']}", type="primary"):
                    # ✅ ПОЛУЧАЕМ current_site ИЗ DomainManager
                    if 'domain_manager' in st.session_state:
                        dm = st.session_state.domain_manager
                        current_site = dm.site_name
                        current_domain = dm.get_current_domain()
                    else:
                        current_site = st.session_state.get('current_site', 'steelborg')
                        current_domain = st.session_state.get('current_domain', 'default')

                    if 'domain_manager' in st.session_state:
                        dm = st.session_state.domain_manager
                        if dm.site_name != current_site:
                            st.session_state.domain_manager = DomainManager(current_site)
                            dm = st.session_state.domain_manager
                        dm.set_current_domain(current_domain)

                    if app_state.load_project(project['project_id']):
                        st.session_state.current_project_id = project['project_id']
                        st.session_state.current_domain = current_domain
                        st.session_state.selected_domain = current_domain
                        st.session_state.show_project_selector = False  # ← ДОБАВИТЬ ЭТУ СТРОКУ!
                        st.session_state.show_project_settings = False  # ← И ЭТУ
                        print(f"✅ Проект загружен: {project['project_name']}")
                        st.success(f"✅ Проект '{project['project_name']}' загружен")
                        st.rerun()
                    else:
                        print(f"❌ Ошибка загрузки проекта {project['project_id']}")
                        st.error("❌ Не удалось загрузить проект")
            with st.expander("⚙️ Действия", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("📋 Дублировать", key=f"dup_{project['project_id']}"):
                        new_name = st.text_input("Новое имя", f"Копия {project['project_name']}", key=f"dup_name_{project['project_id']}")
                        if new_name:
                            new_id = pm.duplicate_project(project['project_id'], new_name)
                            if new_id:
                                st.success("✅ Проект скопирован")
                                st.rerun()
                with col2:
                    if st.button("📤 Экспорт", key=f"exp_{project['project_id']}"):
                        export_file = pm.export_project(project['project_id'], 'json')
                        if export_file:
                            st.success(f"✅ Экспортирован в {export_file}")
                with col3:
                    if st.button("🗑️ Удалить", key=f"del_{project['project_id']}"):
                        if pm.delete_project(project['project_id']):
                            st.warning(f"⚠️ Проект '{project['project_name']}' удален")
                            st.rerun()
            st.divider()
    with st.expander("📊 Статистика", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего проектов", len(projects))
        with col2:
            completed = len([p for p in projects if p['current_phase'] == 7])
            st.metric("Завершенных", completed)
        with col3:
            active = len([p for p in projects if 1 <= p['current_phase'] < 7])
            st.metric("В работе", active)
        with col4:
            total_phases = sum(p['current_phase'] for p in projects)
            avg_phase = total_phases / len(projects) if projects else 0
            st.metric("Средняя фаза", f"{avg_phase:.1f}")
    if st.button("← Назад", key="back_from_selector", use_container_width=True):
        st.session_state.show_project_selector = False
        st.rerun()

# === ПАНЕЛЬ ОЧЕРЕДЕЙ ===
def render_queue_panel():
    if not st.session_state.get('show_queue_panel', False):
        return
    st.markdown("## 📋 Очереди задач")
    st.info("Информация о выполнении проектов в фоне")
    st.markdown("---")
def render_manual_mode_with_domain():
    """Ручной режим с поддержкой доменов"""
    from domain_manager import DomainManager, render_domain_selector
    from pathlib import Path
    import json

    render_auth_buttons()

    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager

    # ========== ПРИНУДИТЕЛЬНО ЗАГРУЖАЕМ ДОМЕН ИЗ ФАЙЛА ==========
    user_id = st.session_state.get('user_id')
    if user_id:
        settings_file = Path(f"sites/users/{user_id}/settings.json")
        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    saved_domain = settings.get('selected_domain', 'default')
                    saved_site = settings.get('selected_site', 'steelborg')

                    if st.session_state.get('current_domain') != saved_domain:
                        st.session_state.current_domain = saved_domain
                        st.session_state.selected_domain = saved_domain
                        st.session_state.current_site = saved_site
                        st.session_state.selected_site = saved_site
                        dm.set_current_domain(saved_domain)
                        print(f"✅ Домен загружен из файла: {saved_site}/{saved_domain}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки домена: {e}")

    current_domain = dm.get_current_domain()
    domain_display = dm.get_domain_display_name(current_domain)

    site_name = st.session_state.get('selected_site', 'steelborg')
    try:
        from site_manager import SiteManager
        sm = SiteManager()
        site_config = sm.get_site_config(site_name)
        site_display = site_config.get('display_name', site_name)
    except:
        site_display = site_name

    st.info(f"🌐 Сайт: **{site_display}** | Домен: **{domain_display}** | Модуль: **{st.session_state.get('selected_module', 'Тексты')}**")

    # ✅ СОЗДАЕМ КОНТЕКСТ
    context = None
    project_id = st.session_state.get('current_project_id')
    user_id = st.session_state.get('user_id')

    if project_id and user_id:
        from context import ProjectContext
        context = ProjectContext(
            user_id=user_id,
            project_id=project_id,
            site_name=site_name,
            domain_name=current_domain
        )
        context.load()

    app_state = AppState()


    if st.session_state.get('selected_module') == 'texts':
        render_manual_mode_with_domain_context(dm, context=context)
    elif st.session_state.get('selected_module') == 'faq':
        st.info("🚧 Модуль FAQ в разработке")
        if st.button("← Назад к выбору модуля"):
            st.session_state.module_selected = False
            st.session_state.selected_module = None
            st.session_state.app_mode = None
            st.rerun()
    elif st.session_state.get('selected_module') == 'reviews':
        st.info("🚧 Модуль Отзывы в разработке")
        if st.button("← Назад к выбору модуля"):
            st.session_state.module_selected = False
            st.session_state.selected_module = None
            st.session_state.app_mode = None
            st.rerun()
    else:
        render_manual_mode()


# main_app.py - ЗАМЕНИТЬ НАЧАЛО ФУНКЦИИ render_manual_mode_with_domain_context

def render_manual_mode_with_domain_context(dm: DomainManager, context=None):
    """Ручной режим с поддержкой доменов - С ФИКСАЦИЕЙ ДОМЕНА ИЗ ФАЙЛА ПОЛЬЗОВАТЕЛЯ"""
    from phase_navigation import render_phase_navigation, render_phase_content
    from pathlib import Path

    app_state = AppState()

    # ========== 1. ПРИНУДИТЕЛЬНО ЗАГРУЖАЕМ ДОМЕН ИЗ ФАЙЛА ПОЛЬЗОВАТЕЛЯ ==========
    user_id = st.session_state.get('user_id')
    if user_id:
        # Загружаем настройки пользователя
        settings_file = Path(f"sites/users/{user_id}/settings.json")
        saved_domain = 'default'
        saved_site = 'steelborg'

        if settings_file.exists():
            try:
                import json
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    saved_domain = settings.get('selected_domain', 'default')
                    saved_site = settings.get('selected_site', 'steelborg')
                    print(f"📂 Загружен домен из файла: {saved_site}/{saved_domain}")
            except Exception as e:
                print(f"⚠️ Ошибка чтения settings.json: {e}")

        # Принудительно устанавливаем домен из файла
        if st.session_state.get('current_domain') != saved_domain or st.session_state.get('current_site') != saved_site:
            print(f"🔄 Синхронизация: {st.session_state.get('current_site')}/{st.session_state.get('current_domain')} -> {saved_site}/{saved_domain}")

            # Обновляем session_state
            st.session_state.current_site = saved_site
            st.session_state.current_domain = saved_domain
            st.session_state.selected_site = saved_site
            st.session_state.selected_domain = saved_domain
            st.session_state[f'domain_system_{saved_site}'] = saved_domain

            # Обновляем DomainManager
            if dm.site_name != saved_site:
                from domain_manager import DomainManager
                st.session_state.domain_manager = DomainManager(saved_site)
                dm = st.session_state.domain_manager
            dm.set_current_domain(saved_domain)

            # Показываем сообщение пользователю
            st.info(f"🔄 Переключено на домен: **{dm.get_domain_display_name(saved_domain)}**")

    # ========== 2. ПРОВЕРКА ПРОЕКТА ==========
    if not st.session_state.get('current_project_id'):
        st.session_state.show_project_selector = True
        render_project_selector()
        return

    # ========== 3. ПРОВЕРЯЕМ, ЧТО ПРОЕКТ СУЩЕСТВУЕТ В ТЕКУЩЕМ ДОМЕНЕ ==========
    user_id = st.session_state.get('user_id')
    project_id = st.session_state.get('current_project_id')
    current_site = st.session_state.get('current_site', 'steelborg')
    current_domain = st.session_state.get('current_domain', 'default')

    project_file = Path(f"sites/{current_site}/domains/{current_domain}/projects/{user_id}/{project_id}.json")

    if not project_file.exists():
        st.error(f"❌ Проект не найден в домене {current_domain}")
        st.session_state.current_project_id = None
        st.session_state.show_project_selector = True
        st.rerun()
        return

    # ========== 4. ОСТАЛЬНОЙ КОД БЕЗ ИЗМЕНЕНИЙ ==========
    # Проверка проекта
    if st.session_state.get('show_project_selector', False):
        render_project_selector()
        return

    # Загружаем проект если нужно
    if 'current_project_id' in st.session_state and not st.session_state.app_data.get('phase1'):
        if not app_state.load_project(st.session_state.current_project_id):
            st.session_state.show_project_selector = True
            st.rerun()
            return

    # Хедер


    # Навигация и содержимое
    render_phase_navigation(app_state, context)
    render_phase_content(app_state, context)

    # Сохраняем
    if st.session_state.current_phase in [3, 4, 5, 6]:
        app_state.save_project()

    if 'current_project_id' in st.session_state:
        app_state.save_project()

def _load_domain_data_safe(dm: DomainManager, domain_key: str, app_state):
    """Безопасная загрузка данных домена без сброса"""
    # ✅ НЕ УДАЛЯЕМ ВСЕ ДАННЫЕ!
    # ✅ ТОЛЬКО ЗАГРУЖАЕМ СПЕЦИФИЧНЫЕ ДАННЫЕ ДОМЕНА

    # Проверяем, есть ли сохранённые данные для этого домена
    domain_data_file = Path(f"sites/{dm.site_name}/domains/{dm.get_current_domain()}/domain_state.json")

    if domain_data_file.exists():
        try:
            with open(domain_data_file, 'r', encoding='utf-8') as f:
                domain_data = json.load(f)

                # Загружаем только если нет активного проекта
                if not st.session_state.get('current_project_id'):
                    # Восстанавливаем последний проект для этого домена
                    last_project = domain_data.get('last_project_id')
                    if last_project and app_state.load_project(last_project):
                        st.session_state.current_project_id = last_project
                        st.success(f"✅ Загружен последний проект для {dm.get_domain_display_name()}")
        except Exception as e:
            print(f"Ошибка загрузки данных домена: {e}")

    st.session_state.domain_data_loaded = domain_key
    st.success(f"✅ Готов к работе с доменом {dm.get_domain_display_name()}")
    st.rerun()
def render_manual_mode():
    """Ручной режим - УПРОЩЁННАЯ ВЕРСИЯ с использованием общих компонентов"""
    from phase_navigation import render_phase_navigation, render_phase_content


    app_state = AppState()

    # Проверка наличия проекта
    if st.session_state.get('current_project_id') is None:
        st.session_state.show_project_selector = True
        render_project_selector()
        return

    if st.session_state.get('show_project_selector', False):
        render_project_selector()
        return

    # Загрузка проекта если нужно
    if 'current_project_id' in st.session_state and not st.session_state.app_data.get('phase1'):
        if not app_state.load_project(st.session_state.current_project_id):
            st.session_state.show_project_selector = True
            st.rerun()
            return

    # Верхняя панель


    # Навигация и содержимое фаз
    render_phase_navigation(app_state)
    render_phase_content(app_state)

    # Сохраняем изменения
    if st.session_state.current_phase in [3, 4, 5, 6]:
        app_state.save_project()

    if 'current_project_id' in st.session_state:
        app_state.save_project()

def render_manual_header(app_state):
    """Единый хедер для ручного режима"""
    col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([2, 1, 1, 1, 1, 1, 1, 1])

    with col1:
        project_name = st.session_state.app_data.get('project_name', 'Новый проект')
        category = st.session_state.app_data.get('category', 'Без категории')
        st.markdown(f"### {project_name}")
        st.caption(f"Категория: {category} | Фаза {st.session_state.current_phase}/7")

    with col2:
        if st.button("📁 Сменить проект", use_container_width=True):
            st.session_state.show_project_selector = True
            st.rerun()

    with col3:
        if st.button("💾 Сохранить", use_container_width=True):
            app_state.save_project()
            st.success("✅ Проект сохранен")

    with col4:
        if st.button("📊 Очереди", use_container_width=True):
            st.session_state.show_queue_panel = not st.session_state.show_queue_panel
            st.rerun()

    with col5:
        if st.button("🤖 AI", use_container_width=True):
            st.session_state.show_ai_config = True
            st.rerun()

    with col6:
        if st.button("👤 Профиль", use_container_width=True):
            st.session_state.show_profile = True
            st.rerun()

    with col7:
        if st.button("🚪 Выйти", use_container_width=True):
            st.session_state.app_mode = None
            auth.logout()
            st.rerun()

    with col8:
        if st.button("🏠 Главная", use_container_width=True, help="Вернуться к выбору режима"):
            if st.session_state.get('current_project_id'):
                app_state.save_project()
            st.session_state.app_mode = None
            st.session_state.show_project_selector = False
            st.rerun()

    st.markdown("---")

    # Модальные окна
    if st.session_state.get("show_profile", False):
        auth.profile_page()
        if st.button("← Назад"):
            st.session_state.show_profile = False
            st.rerun()
        st.stop()

    if st.session_state.get("show_ai_config", False):
        st.title("🤖 Настройки AI")
        try:
            from ai_settings.ai_config import show_ai_config_interface
            show_ai_config_interface()
        except Exception as e:
            st.error(f"Ошибка загрузки настроек AI: {e}")
        if st.button("← Назад", key="back_from_ai"):
            st.session_state.show_ai_config = False
            st.rerun()
        st.stop()

    render_queue_panel()
def render_phase6_full_interface(app_state, context = None):
    """Полноценный интерфейс фазы 6 — с принудительным сохранением"""

    from phases.phase6 import (
        init_phase6_structure, load_texts_from_phase5, analyze_texts,
        apply_replacements, render_ngrams_table, render_results,
        ReplacementType, FastSynonymManager, StopWordManager,
        save_to_phase7, SelectionManager, log, handle_edit_dialogs,
        save_without_replacements
    )

    init_phase6_structure()

    try:
        syn_manager = FastSynonymManager("synonyms.json")
        stop_manager = StopWordManager(syn_manager)
        selection_manager = SelectionManager()
    except Exception as e:
        st.error(f"Ошибка загрузки синонимов: {e}")
        return

    # Загрузка текстов
    if not st.session_state.phase6.get('texts'):
        texts, metadata = load_texts_from_phase5()
        if texts:
            st.session_state.phase6['texts'] = texts
            st.session_state.phase6['original_texts'] = texts.copy()
            st.session_state.phase6['texts_metadata'] = metadata
            st.success(f"✅ Загружено {len(texts)} текстов из фазы 5")
        else:
            st.warning("⚠️ Нет текстов из фазы 5")
            return

    # ✅ ДОБАВИТЬ: Кнопка принудительной синхронизации
    col_sync, col_empty = st.columns([1, 5])
    with col_sync:
        if st.button("🔄 Синхронизировать с проектом", key="sync_phase6_to_project", use_container_width=True):
            # Принудительно сохраняем все данные
            if save_to_phase7():
                st.success("✅ Данные синхронизированы с проектом!")
                st.rerun()

    st.markdown("### 🔄 Фаза 6: Синонимизация текстов")

    # === ВКЛАДКИ ===
    phase6_tabs = st.tabs([
        "📝 Настройки",
        "📊 Слова (униграммы)",
        "🔤 Биграммы",
        "📚 Триграммы",
        "🔠 N-граммы (4-6 слов)",
        "📋 Фразы с предлогами",
        "✨ Результаты"
    ])

    # ====================== ВКЛАДКА НАСТРОЕК ======================
    with phase6_tabs[0]:
        col1, col2 = st.columns(2)
        with col1:
            min_count = st.slider(
                "Минимальная частота для отображения:",
                min_value=1, max_value=20,
                value=st.session_state.phase6.get('min_count', 3)
            )
            st.session_state.phase6['min_count'] = min_count

        with col2:
            total_selected = 0
            for ntype in ['unigram', 'bigram', 'trigram', 'ngram', 'prepositional']:
                selections = [selection_manager.get_selection(ntype, key, False)
                              for key in st.session_state.phase6.get(f'{ntype}s', {}).keys()]
                total_selected += sum(selections)
            st.metric("Выбрано для замены", total_selected)

        st.divider()

        col_a, col_b, col_c, col_d = st.columns(4)

        with col_a:
            if st.button("🔍 Выполнить анализ", use_container_width=True):
                if analyze_texts(syn_manager, stop_manager):

                    st.rerun()

        with col_b:
            if st.button("🔄 Применить замены", type="primary", use_container_width=True):
                if st.session_state.phase6.get('analysis_completed'):
                    if apply_replacements(syn_manager, stop_manager, selection_manager):
                        save_to_phase7()
                        st.rerun()
                else:
                    st.warning("Сначала выполните анализ")

        with col_c:
            if st.button("💾 Сохранить БЕЗ замен",
                         help="Передать тексты из фазы 5 в фазу 7 без синонимизации",
                         use_container_width=True):
                if save_without_replacements(context=context):
                    st.success("✅ Тексты сохранены **без синонимизации**")
                    if hasattr(app_state, 'force_save_phase6_to_phase7'):
                        app_state.force_save_phase6_to_phase7()
                    st.balloons()

        with col_d:
            if st.button("💾 Сохранить с заменами", type="primary", use_container_width=True):
                if save_to_phase7():
                    if hasattr(app_state, 'force_save_phase6_to_phase7'):
                        app_state.force_save_phase6_to_phase7()
                    st.success("✅ Результаты синонимизации сохранены!")
                    st.balloons()

        st.divider()
        # Кнопки сброса
        col_reset1, col_reset2 = st.columns(2)
        with col_reset1:
            if st.button("🔄 Сбросить все замены", use_container_width=True):
                original = st.session_state.phase6.get('original_texts', [])
                if original:
                    st.session_state.phase6['texts'] = original.copy()
                    st.session_state.phase6['processed_texts'] = []
                    st.session_state.phase6['edited_texts'] = original.copy()
                    st.session_state.phase6['replacements_applied'] = False
                    st.session_state.phase6['analysis_completed'] = False
                    selection_manager.clear_selections()
                    st.success("Сброшено до оригинальных текстов")
                    st.rerun()

    # ====================== ОСТАЛЬНЫЕ ВКЛАДКИ ======================
    with phase6_tabs[1]:
        render_ngrams_table(st.session_state.phase6.get('unigrams', {}), ReplacementType.UNIGRAM, "слова", syn_manager, selection_manager)
    with phase6_tabs[2]:
        render_ngrams_table(st.session_state.phase6.get('bigrams', {}), ReplacementType.BIGRAM, "биграммы", syn_manager, selection_manager)
    with phase6_tabs[3]:
        render_ngrams_table(st.session_state.phase6.get('trigrams', {}), ReplacementType.TRIGRAM, "триграммы", syn_manager, selection_manager)
    with phase6_tabs[4]:
        render_ngrams_table(st.session_state.phase6.get('ngrams', {}), ReplacementType.NGRAM, "n-граммы", syn_manager, selection_manager)
    with phase6_tabs[5]:
        render_ngrams_table(st.session_state.phase6.get('prepositional', {}), ReplacementType.PREPOSITIONAL, "фразы с предлогами", syn_manager, selection_manager)

    with phase6_tabs[6]:
        if st.session_state.phase6.get('replacements_applied'):
            render_results()
        else:
            st.info("Выполните анализ и примените замены на вкладке «Настройки»")

    handle_edit_dialogs(syn_manager, stop_manager)

    with st.expander("🐛 Логи"):
        logs = st.session_state.get('phase6_logs', [])
        if logs:
            st.code("\n".join(logs[-30:]))


def render_phase7_full_interface(app_state):
    """Полноценный интерфейс фазы 7 - с ПРИНУДИТЕЛЬНОЙ ЗАГРУЗКОЙ"""

    current_project_id = st.session_state.get('current_project_id', '')
    user_id = st.session_state.get('user_id')
    site = st.session_state.get('current_site', 'steelborg')
    domain = st.session_state.get('current_domain', 'default')

    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{current_project_id}.json")

    if not project_file.exists():
        st.error(f"❌ Файл проекта не найден")
        return

    try:
        from phases.phase7 import Phase7Interface

        # ✅ СБРАСЫВАЕМ ФЛАГ ЗАГРУЗКИ, ЕСЛИ ПРОЕКТ СМЕНИЛСЯ
        if st.session_state.get('_last_phase7_project') != current_project_id:
            st.session_state.phase7_data_loaded = False
            st.session_state._last_phase7_project = current_project_id

        interface = Phase7Interface()

        if not st.session_state.get('phase7_data_loaded', False):
            with st.spinner("Загрузка данных из фазы 6..."):
                success = interface._load_data()
                if success:
                    st.session_state.phase7_data_loaded = True
                    st.success("✅ Данные фазы 6 загружены в фазу 7")
                else:
                    st.error("❌ Не удалось загрузить данные")
                    return

        interface.display_main_interface()

    except Exception as e:
        st.error(f"Ошибка загрузки фазы 7: {e}")
        import traceback
        st.code(traceback.format_exc())
# === НАСТРОЙКИ ПРОЕКТА ===
def render_auto_project_settings(app_state, context=None):
    app_state.debug_dump_state("RENDER_AUTO_PROJECT_SETTINGS START")
    render_auth_buttons()
    view_mode = st.session_state.get('view_mode', 'settings')

    # 🎯 НОВЫЙ РЕЖИМ: результаты с активными фазами 6-7
    if view_mode == 'unified_results':

        st.markdown("### 📊 Результаты проекта")

        # Проверяем статус фаз
        # Проверяем статус фаз
        phase5_completed = st.session_state.app_data.get('phase5_completed', False)

        # Добавь диагностику для проверки
        if not phase5_completed:
            # Проверяем альтернативные источники
            phase5_data = st.session_state.app_data.get('phase5', {})
            if phase5_data.get('phase_completed') or phase5_data.get('results'):
                phase5_completed = True
                st.session_state.app_data['phase5_completed'] = True
                log("✅ Восстановлен phase5_completed из phase5 данных")

        phase5_data = st.session_state.app_data.get('phase5', {})

        if not phase5_completed or not phase5_data.get('results'):
            st.warning("⚠️ Фаза 5 не завершена. Сначала запустите автоматическую генерацию.")
            # ... остальной код ...
            col1, col2, col3 = st.columns(3)
            with col2:
                if st.button("← Назад", use_container_width=True):
                    st.session_state.show_project_settings = False
                    st.rerun()
            return

        # Кнопка возврата в верхней части
        col_back, col_spacer = st.columns([1, 5])
        with col_back:
            if st.button("← К списку проектов", key="back_to_projects_top", use_container_width=True):
                st.session_state.show_project_settings = False
                st.session_state.view_mode = 'settings'
                st.rerun()

        st.markdown("---")

        # ========== ТАБЫ ==========
        tabs = st.tabs([
            "📦 Фаза 1", "🏷️ Фаза 2", "📝 Фаза 3", "🚀 Фаза 4", "📄 Фаза 5",
            "🔄 Фаза 6 (Синонимизация)", "📊 Фаза 7 (Подготовка)"
        ])

        # ========== ФАЗА 1 - ТОЛЬКО ПРОСМОТР ==========
        with tabs[0]:
            st.subheader("📦 Фаза 1: Исходные данные")
            phase1_data = st.session_state.app_data.get('phase1', {})
            if phase1_data:
                characteristics = phase1_data.get('characteristics', {})
                st.write(f"**Всего характеристик:** {len(characteristics)}")
                with st.expander("Показать все характеристики", expanded=False):
                    st.json(characteristics)
            else:
                st.info("Нет данных фазы 1")

        # ========== ФАЗА 2 - ТОЛЬКО ПРОСМОТР ==========
        with tabs[1]:
            st.subheader("🏷️ Фаза 2: Маркеры")
            phase2_data = st.session_state.app_data.get('phase2', {})
            if phase2_data:
                markers = phase2_data.get('markers', {})
                st.write(f"**Всего маркеров:** {len(markers)}")
                with st.expander("Показать все маркеры", expanded=False):
                    st.json(markers)
            else:
                st.info("Нет данных фазы 2 (опционально)")

        # ========== ФАЗА 3 - ТОЛЬКО ПРОСМОТР ==========
        with tabs[2]:
            st.subheader("📝 Фаза 3: Блоки и AI-инструкции")
            phase3_data = st.session_state.app_data.get('phase3', {})
            blocks = phase3_data.get('blocks', {})

            if blocks:
                st.write(f"**Всего блоков:** {len(blocks)}")
                with st.expander("Показать все блоки", expanded=False):
                    for block_id, block_info in blocks.items():
                        st.markdown(f"**{block_info.get('name', block_id)}**")
                        st.write(f"Тип: {block_info.get('block_type', 'unknown')}")
                        st.write(f"Переменные: {', '.join(block_info.get('variables', []))}")
                        st.divider()
            else:
                st.info("Нет данных фазы 3")

        # ========== ФАЗА 4 - ТОЛЬКО ПРОСМОТР ==========
        with tabs[3]:
            st.subheader("🚀 Фаза 4: Сгенерированные промпты")
            phase4_data = st.session_state.app_data.get('phase4', {})
            prompts = phase4_data.get('prompts', [])

            if prompts:
                st.write(f"**Всего промптов:** {len(prompts)}")
                with st.expander("Показать первые 50 промптов", expanded=False):
                    for i, p in enumerate(prompts[:50]):
                        st.write(f"**{i+1}. {p.get('characteristic_name', p.get('block_name', 'Блок'))}**")
                        st.code(p.get('prompt', ''), language="text")
                        st.divider()
            else:
                st.info("Нет данных фазы 4")

        # ========== ФАЗА 5 - ТОЛЬКО ПРОСМОТР ==========
        with tabs[4]:
            st.subheader("📄 Фаза 5: Сгенерированные тексты")
            phase5_data = st.session_state.app_data.get('phase5', {})
            results = phase5_data.get('results', {})
            stats = phase5_data.get('statistics', {})

            if results:
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Всего промптов", stats.get('total', 0))
                col2.metric("Успешно", stats.get('success', 0))
                col3.metric("Ошибки", stats.get('error', 0))
                col4.metric("Выбрано", stats.get('selected', 0))

                with st.expander("Показать сгенерированные тексты", expanded=True):
                    for prompt_id, result in list(results.items())[:50]:
                        if result.get('status') == 'success':
                            st.markdown(f"**{result.get('characteristic_name', prompt_id)}**")
                            st.text_area(
                                f"text_{prompt_id}",
                                result.get('edited_text', result.get('ai_response', '')),
                                height=150,
                                disabled=True,
                                key=f"view_phase5_{prompt_id}"
                            )
                            st.divider()
            else:
                st.info("Нет данных фазы 5")

        # ========== ФАЗА 6 - ПОЛНОЦЕННЫЙ ИНТЕРФЕЙС ==========
        # ========== ФАЗА 6 - ПОЛНОЦЕННЫЙ ИНТЕРФЕЙС ==========
        # ========== ФАЗА 6 - ПОЛНОЦЕННЫЙ ИНТЕРФЕЙС ==========
        # ========== ФАЗА 6 - ПОЛНОЦЕННЫЙ ИНТЕРФЕЙС ==========
        # ========== ФАЗА 6 - ПОЛНОЦЕННЫЙ ИНТЕРФЕЙС ==========
        with tabs[5]:
            phase6.auto_process_synonyms(app_state, context=context)

        # ========== ФАЗА 7 - ПОЛНОЦЕННЫЙ ИНТЕРФЕЙС ==========
        with tabs[6]:
            st.markdown("## 📊 Фаза 7: Подготовка к загрузке")
            st.info("💡 Просмотр и экспорт финальных текстов")
            render_phase7_full_interface(app_state)

        # Кнопка возврата внизу
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col2:
            if st.button("← Вернуться к списку проектов", use_container_width=True, key="back_to_projects_bottom"):
                st.session_state.show_project_settings = False
                st.session_state.view_mode = 'settings'
                st.rerun()
        return

    # ========== РЕЖИМ НАСТРОЕК (settings) ==========
    if view_mode == 'settings':
        st.markdown("### ⚙️ Настройки проекта (фазы 1-6)")
        st.info("✏️ Здесь вы можете настроить маркеры, блоки, промпты, тексты и синонимы")

        # Кнопка возврата к списку проектов
        col_back, col_spacer = st.columns([1, 10])
        with col_back:
            if st.button("←", help="Назад к списку проектов", key="back_to_projects_settings"):
                st.session_state.show_project_settings = False
                st.rerun()

        st.markdown("---")

        project_name = st.session_state.app_data.get('project_name', 'Новый проект')
        category = st.session_state.app_data.get('category', 'Без категории')
        current_phase = st.session_state.current_phase

        phase6_results = st.session_state.app_data.get('phase6', {}).get('processed_texts')
        has_phase6_results = bool(phase6_results)

        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"**Проект:** {project_name}")
            st.markdown(f"**Категория:** {category}")
        with col2:
            if has_phase6_results:
                st.success("✅ **Синонимизация выполнена**")
                st.caption(f"📄 Обработано текстов: {len(phase6_results)}")
            else:
                st.warning("⏳ **Синонимизация не выполнена**")
                st.caption("Выполните фазу 6 в ручном режиме")

        st.markdown("---")
        st.markdown("## ✏️ Редактирование фаз 1-6")

        st.markdown("#### Прогресс выполнения")
        phases_status = []
        for i in range(1, 7):
            phase_data = st.session_state.app_data.get(f'phase{i}', {})
            phases_status.append(bool(phase_data))

        cols = st.columns(6)
        for i, col in enumerate(cols, 1):
            with col:
                if phases_status[i-1]:
                    st.markdown(f"✅ Фаза {i}")
                else:
                    st.markdown(f"⭕ Фаза {i}")
                if st.button(f"Открыть", key=f"goto_phase_{i}_settings"):
                    st.session_state.current_phase = i
                    st.rerun()

        st.markdown("---")

        tabs = st.tabs(["📦 Фаза 1 (Сбор данных)", "🏷️ Фаза 2 (Маркеры)", "📝 Фаза 3 (AI-инструкции)",
                        "🚀 Фаза 4 (Промпты)", "📄 Фаза 5 (Генерация)", "🔄 Фаза 6 (Синонимизация)"])

        with tabs[0]:
            try:
                phase1.main(app_state=app_state, settings_mode=True, context=context)
                app_state.save_project()
            except Exception as e:
                st.error(f"Ошибка загрузки фазы 1: {e}")

        with tabs[1]:
            try:
                phase2.main(app_state=app_state, settings_mode=True, context=context)
                app_state.save_project()
            except Exception as e:
                st.error(f"Ошибка загрузки фазы 2: {e}")

        with tabs[2]:
            try:
                phase3.main(app_state=app_state, settings_mode=True, context=context)

                app_state.save_project()
            except Exception as e:
                st.error(f"Ошибка загрузки фазы 3: {e}")

        with tabs[3]:
            try:
                phase4.main(app_state=app_state, settings_mode=True, context=context)

                app_state.save_project()
            except Exception as e:
                st.error(f"Ошибка загрузки фазы 4: {e}")

        with tabs[4]:
            try:
                phase5.main(app_state=app_state, settings_mode=True, context=context)

                app_state.save_project()
            except Exception as e:
                st.error(f"Ошибка загрузки фазы 5: {e}")

        with tabs[5]:
            try:
                phase6.main(app_state=app_state, settings_mode=True, context=context)

                app_state.save_project()
            except Exception as e:
                st.error(f"Ошибка загрузки фазы 6: {e}")

        st.markdown("---")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("💾 Сохранить настройки", type="primary", use_container_width=True):

                app_state.sync_app_data_with_session_state()
                app_state.save_project()
                st.success("✅ Настройки проекта сохранены!")

        with col2:
            if has_phase6_results:
                if st.button("📊 Перейти к результатам", use_container_width=True):
                    app_state.save_project()
                    st.session_state.view_mode = 'results'
                    st.session_state.current_phase = 7
                    st.rerun()

        with col3:
            if st.button("🔄 Переключиться в ручной режим", use_container_width=True):
                app_state.save_project()
                st.session_state.app_mode = 'manual'
                st.session_state.show_project_settings = False
                st.rerun()

        return

    # ========== РЕЖИМ РЕЗУЛЬТАТОВ (results) ==========
    if view_mode == 'results':
        st.markdown("### 📊 Результаты проекта")

        # Кнопка возврата
        col_back, col_spacer = st.columns([1, 10])
        with col_back:
            if st.button("←", help="Назад к настройкам", key="back_to_settings"):
                st.session_state.view_mode = 'settings'
                st.rerun()

        st.markdown("---")

        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
            ["📦 Фаза 1", "🏷️ Фаза 2", "📝 Фаза 3", "🚀 Фаза 4", "📄 Фаза 5", "🔄 Фаза 6", "📊 Фаза 7"]
        )

        with tab1:
            phase1_data = st.session_state.app_data.get('phase1', {})
            if phase1_data:
                st.json(phase1_data)
            else:
                st.info("Нет данных фазы 1")

        with tab2:
            phase2_data = st.session_state.app_data.get('phase2', {})
            if phase2_data:
                st.json(phase2_data)
            else:
                st.info("Нет данных фазы 2")

        with tab3:
            st.subheader("📝 Блоки и AI-инструкции (Фаза 3)")
            phase3_data = st.session_state.app_data.get('phase3', {})
            blocks = phase3_data.get('blocks', {})

            if blocks:
                blocks_count = phase3_data.get('blocks_count', len(blocks))
                characteristic_blocks = phase3_data.get('characteristic_blocks', len([b for b in blocks.values() if b.get('block_type') == 'characteristic']))
                other_blocks = phase3_data.get('other_blocks', len([b for b in blocks.values() if b.get('block_type') == 'other']))

                col1, col2, col3 = st.columns(3)
                col1.metric("Всего блоков", blocks_count)
                col2.metric("Блоки характеристик", characteristic_blocks)
                col3.metric("Другие блоки", other_blocks)

                with st.expander("📋 Список блоков", expanded=False):
                    for block_id, block_info in blocks.items():
                        st.markdown(f"**{block_info.get('name', block_id)}**")
                        st.write(f"Тип: {block_info.get('block_type', 'unknown')}")
                        st.write(f"Переменные: {', '.join(block_info.get('variables', []))}")
                        st.divider()
            else:
                st.warning("⚠️ Нет данных о блоках.")

                if 'block_manager' in st.session_state:
                    blocks_direct = st.session_state.block_manager.get_all_blocks()
                    if blocks_direct:
                        st.info(f"✅ Найдено {len(blocks_direct)} блоков в BlockManager. Сохраняем...")
                        from phases.phase3 import force_save_phase3_blocks
                        force_save_phase3_blocks()
                        st.rerun()

        with tab4:
            phase4_data = st.session_state.app_data.get('phase4', {})
            if phase4_data:
                prompts = phase4_data.get('prompts', [])
                st.write(f"**Сгенерировано промптов:** {len(prompts)}")
                with st.expander("Показать первые 100 промптов"):
                    for i, p in enumerate(prompts[:100]):
                        st.write(f"**{i+1}. {p.get('characteristic_name', p.get('block_name', 'Блок'))}**")
                        st.code(p.get('prompt', ''), language="text")
            else:
                st.info("Нет данных фазы 4")

        with tab5:
            phase5_data = st.session_state.app_data.get('phase5', {})
            if phase5_data:
                stats = phase5_data.get('statistics', {})
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Всего промптов", stats.get('total', 0))
                col2.metric("Успешно", stats.get('success', 0))
                col3.metric("Ошибки", stats.get('error', 0))
                col4.metric("Выбрано", stats.get('selected', 0))

                results = phase5_data.get('results', {})
                if results:
                    with st.expander("Показать сгенерированные тексты"):
                        for prompt_id, result in list(results.items())[:20]:
                            if result.get('status') == 'success':
                                st.write(f"**{result.get('characteristic_name', prompt_id)}**")
                                st.write(result.get('edited_text', result.get('ai_response', ''))[:500])
                                st.divider()
            else:
                st.info("Нет данных фазы 5")

        with tab6:
            phase6_data = st.session_state.app_data.get('phase6', {})
            if phase6_data:
                stats = phase6_data.get('statistics', {})
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Текстов обработано", stats.get('total_texts', 0))
                col2.metric("Всего замен", stats.get('total_replacements', 0))
                col3.metric("Замен слов", stats.get('unigram_replacements', 0))
                col4.metric("Замен фраз", stats.get('phrase_replacements', 0))

                with st.expander("Примеры замен", expanded=False):
                    replacements = phase6_data.get('replacements', [])
                    for r in replacements[:20]:
                        st.write(f"• '{r.get('original')}' → '{r.get('new')}' (тип: {r.get('type', 'unknown')})")

                with st.expander("Результаты синонимизации", expanded=False):
                    processed_texts = phase6_data.get('processed_texts', [])
                    original_texts = phase6_data.get('original_texts', [])
                    for i, (orig, proc) in enumerate(zip(original_texts[:5], processed_texts[:5])):
                        st.write(f"**Текст {i+1}:**")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("Оригинал:")
                            st.text_area("", orig, height=150, key=f"orig_{i}", disabled=True)
                        with col2:
                            st.write("Результат:")
                            st.text_area("", proc, height=150, key=f"proc_{i}", disabled=True)
                        st.divider()
            else:
                st.info("Нет данных фазы 6 (синонимизация еще не выполнена)")

        with tab7:
            try:
                phase7.main(app_state=app_state, settings_mode=False)
                app_state.save_project()
            except Exception as e:
                st.error(f"Ошибка загрузки фазы 7: {e}")
                import traceback
                st.code(traceback.format_exc())

            st.markdown("---")

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("💾 Сохранить изменения", type="primary", use_container_width=True):
                    app_state.save_project()
                    st.success("✅ Изменения в фазе 7 сохранены!")

            with col2:
                if st.button("⚙️ Вернуться к настройкам", use_container_width=True):
                    app_state.save_project()
                    st.session_state.view_mode = 'settings'
                    st.rerun()

            with col3:
                if st.button("🔄 Перезапустить генерацию", use_container_width=True):
                    st.warning("Это удалит все текущие результаты и запустит генерацию заново. Продолжить?")
                    project_name = st.session_state.app_data.get('project_name', 'Проект')
                    category = st.session_state.app_data.get('category', 'Категория')
                    for phase in ['phase3', 'phase4', 'phase5', 'phase6', 'phase7']:
                        st.session_state.app_data[phase] = {}
                    st.session_state.app_data['phase5_completed'] = False
                    st.session_state.current_phase = 3
                    app_state.save_project()

                    manager = st.session_state.project_queue_manager
                    manager.add_project(st.session_state.current_project_id, st.session_state.user_id, project_name, category)
                    st.success("✅ Проект добавлен в очередь на перегенерацию")
                    st.session_state.show_project_settings = False
                    st.rerun()

        return
def sync_project_status():
    """Синхронизирует статус проекта между worker'ом и интерфейсом"""
    if 'current_project_id' not in st.session_state:
        return

    queue = get_user_queue()
    if queue is None:  # <-- ДОБАВИТЬ ЭТУ ПРОВЕРКУ
        return

    project_id = st.session_state.current_project_id
    status = queue.get_status(project_id)

    if status.get('status') == 'running':
        st.session_state.project_running = True
        st.session_state.project_phase = status.get('current_phase', 0)
        st.session_state.project_progress = status.get('progress', 0)
        st.session_state.project_message = status.get('message', '')

        if 'app_data' in st.session_state:
            st.session_state.app_data['current_phase'] = status.get('current_phase', 1)
            st.session_state.current_phase = status.get('current_phase', 1)

    return status
def diagnose_worker_status():
    """Диагностика состояния worker'а и очереди"""
    st.markdown("### 🔬 ДИАГНОСТИКА WORKER'А")

    queue = get_user_queue()
    if queue is None:
        st.error("❌ Очередь не инициализирована!")
        return

    # 1. Статус worker'а
    st.markdown("#### 1. Статус worker потока")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"Worker running: `{queue._running}`")
        st.write(f"Worker thread alive: `{hasattr(queue, '_thread') and queue._thread.is_alive()}`")
    with col2:
        if hasattr(queue, '_thread') and queue._thread.is_alive():
            st.success("✅ Worker поток жив")
        else:
            st.error("❌ Worker поток МЕРТВ!")

    # 2. Состояние очереди
    st.markdown("#### 2. Состояние очереди")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Проектов в словаре", len(queue.projects))
    with col2:
        st.metric("Размер очереди (qsize)", queue._queue.qsize())

    # 3. Детальный статус каждого проекта
    st.markdown("#### 3. Детальный статус проектов")
    if not queue.projects:
        st.info("Нет проектов в очереди")
    else:
        for pid, task in queue.projects.items():
            with st.expander(f"📁 {task.project_name} ({pid[:8]}...)"):
                st.write(f"**Статус:** `{task.status.value}`")
                st.write(f"**Текущая фаза:** {task.current_phase}")
                st.write(f"**Прогресс:** {task.progress}%")
                st.write(f"**Сообщение:** {task.message}")
                if task.error:
                    st.error(f"**Ошибка:** {task.error[:200]}")
# === АВТОМАТИЧЕСКИЙ РЕЖИМ ===
# В main_app.py, ЗАМЕНИТЕ render_auto_mode на:
def check_data_integrity():
    """Проверяет целостность данных фаз 4 и 5"""
    print("\n" + "="*60)
    print("🔍 ПРОВЕРКА ЦЕЛОСТНОСТИ ДАННЫХ:")

    # ✅ Проверяем существование app_data
    if 'app_data' not in st.session_state:
        print("⚠️ app_data НЕ СУЩЕСТВУЕТ в session_state!")
        print("   Возможно проект еще не загружен или не создан")
        print("="*60 + "\n")
        return False

    # ✅ Безопасное получение данных
    app_data = st.session_state.app_data

    # Phase 4
    phase4_prompts = st.session_state.get('phase4_generated_prompts', {})
    phase4_in_app = app_data.get('phase4', {}).get('prompts', []) if app_data.get('phase4') else []

    print(f"Phase4 в session_state: {len(phase4_prompts) if phase4_prompts else 0} промптов")
    print(f"Phase4 в app_data: {len(phase4_in_app)} промптов")

    # Phase 5
    phase5_results = st.session_state.get('phase5_results', {})
    phase5_in_app = app_data.get('phase5', {}).get('results', {}) if app_data.get('phase5') else {}

    print(f"Phase5 в session_state: {len(phase5_results)} результатов")
    print(f"Phase5 в app_data: {len(phase5_in_app)} результатов")
    print(f"Phase5 completed: {st.session_state.get('phase5_completed', False)}")

    # Проверка синхронизации
    if len(phase4_prompts) != len(phase4_in_app):
        print(f"⚠️ РАССИНХРОНИЗАЦИЯ PHASE4! session_state={len(phase4_prompts)}, app_data={len(phase4_in_app)}")
    if len(phase5_results) != len(phase5_in_app):
        print(f"⚠️ РАССИНХРОНИЗАЦИЯ PHASE5! session_state={len(phase5_results)}, app_data={len(phase5_in_app)}")

    print("="*60 + "\n")
    return len(phase4_prompts) > 0 and len(phase5_results) > 0
# main_app.py - ЗАМЕНИТЬ НАЧАЛО ФУНКЦИИ render_auto_mode

def render_auto_mode():
    """Автоматический режим - С ФИКСАЦИЕЙ ДОМЕНА"""
    from domain_utils import ensure_domain_consistency
    from project_status_manager import ProjectStatusManager

    # ✅ СОЗДАЕМ КОНТЕКСТ (если есть проект)
    context = None
    project_id = st.session_state.get('current_project_id')
    user_id = st.session_state.get('user_id')
    if project_id and user_id:
        from context import ProjectContext
        context = ProjectContext(
            user_id=user_id,
            project_id=project_id,
            site_name=st.session_state.get('current_site', 'steelborg'),
            domain_name=st.session_state.get('current_domain', 'default')
        )
        context.load()
        log(f"📌 Контекст создан в render_auto_mode: project_id={project_id}")

    # ✅ СНАЧАЛА СИНХРОНИЗИРУЕМ ДОМЕН




    # ✅ ОЧИЩАЕМ СТАРЫЕ ДАННЫЕ PHASE5 И PHASE6 ПЕРЕД ГЕНЕРАЦИЕЙ
    if st.session_state.get('_new_project_created', False):
        st.session_state.phase5_results = {}
        st.session_state.phase5_completed = False
        st.session_state.phase5_statistics = {}
        st.session_state.phase6 = {}
        st.session_state.phase6_logs = []
        if 'app_data' in st.session_state:
            st.session_state.app_data['phase5'] = {}
            st.session_state.app_data['phase5_completed'] = False
            st.session_state.app_data['phase6'] = {}
            st.session_state.app_data['phase6_completed'] = False
        st.session_state._new_project_created = False
        print("🧹 Очищены старые данные phase5 и phase6 для нового проекта")

    check_data_integrity()
    app_state = AppState()
    render_auth_buttons()
    render_diagnostic_button()

    # ✅ DomainManager уже есть, берем существующий
    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    # ✅ БЕРЕМ ДОМЕН ИЗ session_state (ОДИН РАЗ!)
    current_site = st.session_state.get('current_site', 'steelborg')
    current_domain = st.session_state.get('current_domain', 'default')
    # ❌ УБИРАЕМ ПОВТОРНЫЙ ЗАБОР current_domain
    # current_site = st.session_state.get('current_site', 'steelborg')
    # current_domain = st.session_state.get('current_domain', 'default')
    # print(f"🌐 render_auto_mode: site={current_site}, domain={current_domain}")

    # ❌ УБИРАЕМ ПЕРЕЗАПИСЬ session_state
    # st.session_state.current_site = current_site
    # st.session_state.current_domain = current_domain

    # Кнопки модуля


    # Загрузка проекта если выбран
    if st.session_state.get('current_project_id'):
        _auto_load_project_if_needed(app_state, current_site, current_domain)

    # ✅ ПОКАЗЫВАЕМ ПРАВИЛЬНЫЙ ДОМЕН
    domain_display = dm.get_domain_display_name(current_domain)
    st.info(f"🌐 Текущий домен: **{domain_display}** (сайт: {current_site})")

    # Показываем статус текущего проекта
    _show_current_project_status(current_site, current_domain)

    st.markdown("---")

    # ✅ КНОПКА СОЗДАНИЯ ПРОЕКТА ВСЕГДА ВИДНА
    col1, col2 = st.columns([5, 1])
    with col1:
        st.markdown("<h1>🤖 Data Harvester Pro - Автоматический режим</h1>", unsafe_allow_html=True)
    with col2:
        if st.button("➕ Новый проект", use_container_width=True, type="primary", key="new_project_auto_list"):
            st.session_state.show_new_project_form = True
            st.rerun()

    # Форма создания проекта
    if st.session_state.get('show_new_project_form', False):
        with st.form(key="new_project_form_auto_main"):
            new_category = st.text_input("Название категории / проекта")
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("✅ Создать", use_container_width=True):
                    if new_category and new_category.strip():
                        app_state.create_new_project(new_category.strip())
                        st.session_state.show_new_project_form = False
                        st.rerun()
                    else:
                        st.error("❌ Введите название проекта")
            with col2:
                if st.form_submit_button("❌ Отмена", use_container_width=True):
                    st.session_state.show_new_project_form = False
                    st.rerun()

    st.markdown("---")

    # Настройки или проекты
    if st.session_state.get('show_project_settings', False):
        render_auto_project_settings(app_state, context=context)
        return

    # Табы
    tab1, tab2 = st.tabs(["📁 Проекты", "📊 Действия и статус"])

    with tab1:
        render_auto_projects_list_improved(app_state, current_site, current_domain)

    with tab2:
        render_auto_actions_and_status_improved(app_state)

    # Логи
    _render_debug_logs()

# main_app.py - ЗАМЕНИТЬ ФУНКЦИЮ

def _auto_load_project_if_needed(app_state, current_site: str, current_domain: str):
    """Загружает проект - ТОЛЬКО ИЗ ТЕКУЩЕГО ДОМЕНА"""
    project_id = st.session_state.get('current_project_id')

    if not project_id or project_id == 'None':
        print(f"❌ _auto_load_project_if_needed: project_id = {project_id}, пропускаем")
        if project_id == 'None':
            st.session_state.current_project_id = None
        return

    if not project_id:
        print("❌ Нет project_id для загрузки")
        return

    # ✅ ПРОВЕРЯЕМ, ЧТО ПРОЕКТ СУЩЕСТВУЕТ В ТЕКУЩЕМ ДОМЕНЕ
    project_file = Path(f"sites/{current_site}/domains/{current_domain}/projects/{st.session_state.user_id}/{project_id}.json")

    if not project_file.exists():
        print(f"❌ Проект {project_id} не найден в домене {current_domain}")
        # ✅ ОЧИЩАЕМ session_state, чтобы не было "призрачного" проекта
        st.session_state.current_project_id = None
        if 'app_data' in st.session_state:
            st.session_state.app_data = {}
        st.warning(f"⚠️ Проект не найден в домене {current_domain}. Выберите другой проект.")
        return

    # ✅ ЗАГРУЖАЕМ ПРОЕКТ
    if app_state.load_project(project_id):
        # ✅ УБЕЖДАЕМСЯ, ЧТО ДОМЕН В session_state СОВПАДАЕТ С ДОМЕНОМ В ФАЙЛЕ
        project_data = st.session_state.app_data
        file_domain = project_data.get('domain_name')
        if file_domain and file_domain != current_domain:
            print(f"⚠️ Домен в файле ({file_domain}) не совпадает с текущим ({current_domain})")
            # ✅ ПЕРЕКЛЮЧАЕМ НА ДОМЕН ИЗ ФАЙЛА
            if 'domain_manager' in st.session_state:
                dm = st.session_state.domain_manager
                if dm.site_name != current_site:
                    st.session_state.domain_manager = DomainManager(current_site)
                    dm = st.session_state.domain_manager
                dm.set_current_domain(file_domain)
                st.session_state.current_domain = file_domain
                st.session_state.selected_domain = file_domain
                print(f"🔄 Переключено на домен из файла: {file_domain}")

        if 'current_phase' in st.session_state.app_data:
            st.session_state.current_phase = st.session_state.app_data['current_phase']
        print(f"✅ Проект {project_id} загружен из домена {current_domain}")
    else:
        st.session_state.current_project_id = None
        st.warning("⚠️ Не удалось загрузить проект")

def _show_current_project_status(current_site: str, current_domain: str):
    """Показывает статус текущего проекта"""
    from project_status_manager import ProjectStatusManager

    if not st.session_state.get('current_project_id'):
        return

    status = ProjectStatusManager.get_unified_status(
        st.session_state.current_project_id,
        st.session_state.user_id,
        current_site,
        current_domain
    )

    status_texts = {
        'running': ('🟢', 'Выполняется в фоне'),
        'queued': ('🟡', 'В очереди'),
        'completed': ('✅', 'Завершён'),
        'failed': ('❌', 'Ошибка'),
        'unknown': ('⚪', 'Не запущен')
    }

    icon, text = status_texts.get(status.get('status'), ('⚪', 'Неизвестно'))

    if status.get('status') == 'running':
        st.info(f"{icon} **Проект {text}** - Фаза {status.get('current_phase')}/7 - {status.get('message', '')} (прогресс: {status.get('progress', 0):.0f}%)")
        st.progress(status.get('progress', 0) / 100)
    elif status.get('status') == 'queued':
        st.warning(f"{icon} **Проект {text}** - ожидает выполнения")
    elif status.get('status') == 'completed':
        st.success(f"{icon} **Проект {text}**")
    elif status.get('status') == 'failed':
        st.error(f"{icon} **Проект {text}**")
        if status.get('error'):
            with st.expander("Детали ошибки"):
                st.code(status.get('error')[:500])

def _render_debug_logs():
    """Рендерит отладочные логи"""
    with st.expander("🐛 Логи отладки + Управление Worker", expanded=False):
        if 'debug_logs' in st.session_state and st.session_state.debug_logs:
            st.code("\n".join(st.session_state.debug_logs[-30:]), language="text")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🗑️ Очистить логи", use_container_width=True):
                st.session_state.debug_logs = []
                st.rerun()
        with col2:
            if st.button("🔄 Обновить статус", use_container_width=True):
                st.success("✅ Статус обновлен")
        with col3:
            if st.button("♻️ Перезапустить Worker", use_container_width=True):
                queue = get_user_queue()
                if queue:
                    queue.ensure_worker_running()
                    st.success("✅ Worker перезапущен")
                    time.sleep(0.5)
                    st.rerun()


def render_auto_projects_list_improved(app_state, current_site: str, current_domain: str):
    print(f"\n🔍 render_auto_projects_list_improved: site={current_site}, domain={current_domain}")
    print(f"   st.session_state.current_site={st.session_state.get('current_site')}")
    print(f"   st.session_state.current_domain={st.session_state.get('current_domain')}")
    print(f"   st.session_state.selected_site={st.session_state.get('selected_site')}")
    print(f"   st.session_state.selected_domain={st.session_state.get('selected_domain')}")
    print(f"   'project_cache' in session_state: {'project_cache' in st.session_state}")
    if 'project_cache' in st.session_state:
        print(f"   project_cache keys: {list(st.session_state.project_cache.keys()) if isinstance(st.session_state.project_cache, dict) else 'NOT A DICT'}")

    # ... остальной код ...

    # Проверка смены домена
    domain_key = f"{current_site}_{current_domain}"
    last_domain_key = st.session_state.get('_last_domain_key')
    print(f"   domain_key={domain_key}, last_domain_key={last_domain_key}")

    if last_domain_key != domain_key:
        print(f"🔄 Домен изменился: {last_domain_key} -> {domain_key}, очищаем кэш")
        st.session_state._rendering_projects = set()
        st.session_state._refresh_projects = True
        if 'project_cache' in st.session_state:
            del st.session_state.project_cache
        st.session_state._last_domain_key = domain_key

    if st.session_state.get('_refresh_projects', False):
        st.session_state._rendering_projects = set()
        st.session_state._refresh_projects = False


    # ... остальной код без изменений ...
    print("\n" + "=" * 80)
    print("🔍 render_auto_projects_list_improved")
    # ... остальной код ...
    print("🔍 render_auto_projects_list_improved")
    print(f"   current_site: {current_site}")
    print(f"   current_domain: {current_domain}")
    print(f"   phase5 в session_state: {bool(st.session_state.get('phase5', {}).get('results'))}")
    print(f"   phase5 в app_data: {bool(st.session_state.app_data.get('phase5', {}).get('results'))}")
    print(f"   phase5_completed: {st.session_state.app_data.get('phase5_completed', False)}")
    print("=" * 80 + "\n")
    if st.session_state.get('_new_project_created', False):
        st.session_state._new_project_created = False
    # ... остальной код ...
    from project_status_manager import ProjectStatusManager

    st.markdown("### 📁 Мои проекты")

    # ProjectManager
    from project_manager import ProjectManager
    pm = ProjectManager(
        user_id=st.session_state.user_id,
        site_name=current_site,
        domain_name=current_domain
    )

    # ✅ ПОЛУЧАЕМ ПРОЕКТЫ ТОЛЬКО ИЗ ТЕКУЩЕГО ДОМЕНА
    print(f"   ProjectManager создан: site={pm.site_name}, domain={pm.domain_name}")
    projects = pm.get_all_projects()
    print(f"   Получено проектов: {len(projects)}")

    if not projects:
        st.info(f"📭 Нет проектов в домене **{current_domain}**")

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("➕ Создать первый проект", use_container_width=True, type="primary"):
                st.session_state.show_new_project_form = True
                st.rerun()
        return


    # ✅ ДЛЯ КАЖДОГО ПРОЕКТА ПОЛУЧАЕМ СТАТУС ИЗ ОЧЕРЕДИ (ЕСЛИ ЕСТЬ)
    projects_with_status = []
    for project in projects:
        status_info = ProjectStatusManager.get_unified_status(
            project['project_id'],
            st.session_state.user_id,
            current_site,
            current_domain
        )
        projects_with_status.append((project, status_info))

    # ✅ ВСЕГДА ПОКАЗЫВАЕМ ПРОЕКТЫ, ДАЖЕ ЕСЛИ ИХ НЕТ В ОЧЕРЕДИ
    if not projects_with_status:
        st.info("📭 Нет проектов")
        return

    # Кнопка нового проекта
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown("#### Доступные проекты")
    with col2:
        if st.button("🔄 Обновить список", use_container_width=True):
            st.session_state._refresh_projects = True
            if 'project_cache' in st.session_state:
                del st.session_state.project_cache
            st.success("✅ Список обновлен")
            st.rerun()  # ← ВЕРНИ ОБРАТНО!
    with col3:
        if st.button("➕ Новый проект", use_container_width=True, type="primary"):
            st.session_state.show_new_project_form = True

    # Форма создания проекта
    if st.session_state.get('show_new_project_form', False):
        _render_new_project_form(app_state)

    st.markdown("---")

    if not projects:
        st.info(f"📭 У вас пока нет сохраненных проектов для сайта '{current_site}' и домена '{current_domain}'. Создайте новый проект.")

        # ✅ КНОПКА СОЗДАНИЯ В БЛОКЕ "НЕТ ПРОЕКТОВ"
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("➕ Создать первый проект", use_container_width=True, type="primary"):
                st.session_state.show_new_project_form = True
                st.rerun()
        return

    # Фильтры
    search_query, filter_status, sort_by = _render_project_filters()
    # После фильтров, перед списком проектов
    col_diag1, col_diag2 = st.columns([4, 1])
    with col_diag2:
        if st.button("🔬 Диагностика JSON", use_container_width=True):
            if st.session_state.get('current_project_id'):
                debug_json_structure(st.session_state.get('current_project_id'))
            else:
                st.warning("Нет активного проекта")
    # Получаем статусы для всех проектов
    projects_with_status = []
    for project in projects:
        status_info = ProjectStatusManager.get_unified_status(
            project['project_id'],
            st.session_state.user_id,
            current_site,
            current_domain
        )
        projects_with_status.append((project, status_info))
    # В render_auto_projects_list_improved() после получения projects:

    filtered = _filter_projects(projects_with_status, search_query, filter_status)

    # Сортировка
    filtered = _sort_projects(filtered, sort_by)
    with st.expander("🔍 Диагностика (показать все проекты)", expanded=False):
        st.write(f"Всего проектов в файлах: {len(projects)}")
        for p in projects:
            st.write(f"  - {p.get('project_name')} (ID: {p.get('project_id')[:8]})")

        st.write(f"Всего projects_with_status: {len(projects_with_status)}")
        for p, s in projects_with_status:
            st.write(f"  - {p.get('project_name')}: статус={s.get('status')}")

        st.write(f"Всего filtered: {len(filtered)}")
        for p, s in filtered:
            st.write(f"  - {p.get('project_name')}: статус={s.get('status')}")
    # Отображение
    # ============================================================
    # ✅ ВОТ ЗДЕСЬ ВСТАВЛЯЕМ ЦИКЛ ОТОБРАЖЕНИЯ ПРОЕКТОВ
    # ============================================================
    for project, status_info in filtered:
        _render_project_card(
            project,
            status_info,  # ← передаем реальный статус, а не пустой {}
            app_state,
            pm,
            current_site,
            current_domain
        )

    # Статистика
    _render_project_statistics(projects, projects_with_status)

def _render_new_project_form(app_state):
    """Рендерит форму создания нового проекта"""
    with st.form(key="new_project_form_auto"):
        new_category = st.text_input("Название категории / проекта", key="new_category_auto")
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Создать", key="create_project_btn_auto"):
                if new_category.strip():
                    app_state.create_new_project(new_category.strip())
                    st.session_state.show_new_project_form = False
                    st.rerun()
        with col2:
            if st.form_submit_button("Отмена", key="cancel_new_project_auto"):
                st.session_state.show_new_project_form = False
                st.rerun()

def _render_project_filters():
    """Рендерит фильтры проектов"""
    col1, col2, col3 = st.columns(3)
    with col1:
        search_query = st.text_input("🔍 Поиск", placeholder="Название или категория...")
    with col2:
        filter_status = st.selectbox(
            "Фильтр по статусу",
            ["Все", "running", "queued", "completed", "failed", "unknown", "idle"]  # ← ДОБАВЛЕНЫ ВСЕ СТАТУСЫ!
        )
    with col3:
        sort_by = st.selectbox("Сортировка",
                               ["По дате изменения", "По названию", "По категории", "По статусу"])
    return search_query, filter_status, sort_by

def _filter_projects(projects_with_status, search_query: str, filter_status: str):
    """Фильтрует проекты"""
    filtered = projects_with_status.copy()

    if search_query:
        filtered = [(p, s) for p, s in filtered
                    if search_query.lower() in p['project_name'].lower()
                    or search_query.lower() in p['category'].lower()]

    # ✅ ЕСЛИ filter_status == "Все" - НЕ ФИЛЬТРУЕМ
    if filter_status != "Все":
        filtered = [(p, s) for p, s in filtered
                    if s.get('status') == filter_status]

    return filtered

def _sort_projects(projects_with_status, sort_by: str):
    """Сортирует проекты"""
    if sort_by == "По названию":
        return sorted(projects_with_status, key=lambda x: x[0]['project_name'])
    elif sort_by == "По категории":
        return sorted(projects_with_status, key=lambda x: x[0]['category'])
    elif sort_by == "По статусу":
        return sorted(projects_with_status, key=lambda x: x[1].get('status', 'unknown'))
    else:  # По дате изменения
        return sorted(projects_with_status, key=lambda x: x[0].get('updated_at', ''), reverse=True)

def _render_project_card(project, status_info, app_state, pm, current_site, current_domain):
    # ========== ДИАГНОСТИКА ==========
    #st.write(f"📁 Рендерим: {project['project_name']}")
    from project_status_manager import ProjectStatusManager

    pid = project.get('project_id')

    if not pid or pid == 'None':
        return

    # ✅ ПРОВЕРЯЕМ, ЧТО ПРОЕКТ ПРИНАДЛЕЖИТ ТЕКУЩЕМУ ДОМЕНУ
    project_domain = project.get('domain_name')
    if project_domain and project_domain != current_domain:
        print(f"⚠️ Проект {pid} принадлежит домену {project_domain}, не показываем в {current_domain}")
        return

    # st.write(f"   PID: {pid}")  # ← ДОБАВЬ

    # ✅ ЗАЩИТА: если проект уже рендерится, пропускаем
    #if pid in st.session_state.get('_rendering_projects', set()):
    #st.write(f"⚠️ Проект уже рендерится, пропускаем")  # ← ДОБАВЬ
    #return
    if '_rendering_projects' not in st.session_state:
        st.session_state._rendering_projects = set()
    st.session_state._rendering_projects.add(pid)

    st.write(f"   Статус: {status_info.get('status')}")  # ← ДОБАВЬ

    # ... остальной код ...

    status = status_info.get('status', 'unknown')
    current_phase = status_info.get('current_phase', project.get('current_phase', 1))
    progress = status_info.get('progress', 0)
    message = status_info.get('message', '')

    # Определяем визуальное оформление
    status_config = {
        'running': ('🟢', 'ВЫПОЛНЯЕТСЯ', '#10b981', False),
        'queued': ('🟡', 'В ОЧЕРЕДИ', '#f59e0b', False),
        'completed': ('✅', 'ЗАВЕРШЁН', '#10b981', False),
        'failed': ('❌', 'ОШИБКА', '#ef4444', True),
        'unknown': ('⚪', 'НЕ ЗАПУЩЕН', '#6b7280', True)
    }

    icon, status_text, status_color, show_run = status_config.get(status, ('⚪', 'НЕИЗВЕСТНО', '#6b7280', True))

    # Проверяем наличие результатов
    has_results = ProjectStatusManager.has_results(pid, st.session_state.user_id, current_site, current_domain)
    can_run = ProjectStatusManager.can_run(pid, st.session_state.user_id, current_site, current_domain)

    with st.container():
        col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([2, 1.5, 1, 1, 1, 1, 1, 1])

        with col1:
            phase_icons = {1: "📦", 2: "🏷️", 3: "📝", 4: "🚀", 5: "📄", 6: "🔄", 7: "📊"}
            icon_phase = phase_icons.get(project['current_phase'], "📁")
            st.markdown(f"**{icon_phase} {project['project_name']}**")
            st.caption(f"📂 {project['category']}")

        with col2:
            st.markdown(f"{icon} **<span style='color:{status_color}'>{status_text}</span>**", unsafe_allow_html=True)
            if status == 'running':
                st.caption(f"⚙️ Фаза {current_phase}/7")
                st.progress(progress / 100, text=f"{progress:.0f}%")
            if message and status != 'completed':
                st.caption(f"📝 {message[:60]}")

        with col3:
            if project.get('updated_at'):
                updated = datetime.fromisoformat(project['updated_at']).strftime("%d.%m.%Y %H:%M")
                st.caption(f"📅 {updated}")

        with col4:
            if show_run and can_run:
                if st.button("🚀", key=f"run_{pid}", help="Запустить автоматическую генерацию"):
                    from user_queue_manager import get_user_queue
                    queue = get_user_queue()
                    if queue:
                        if pid not in queue.projects or queue.projects[pid].status not in [ProjectStatus.QUEUED, ProjectStatus.RUNNING]:
                            # ✅ ПЕРЕДАЕМ ПРАВИЛЬНЫЙ САЙТ И ДОМЕН
                            queue.add_project(
                                project_id=pid,
                                project_name=project['project_name'],
                                category=project['category'],
                                site_name=current_site,      # ← steelborg
                                domain_name=current_domain    # ← kz (НЕ DEFAULT!)
                            )
                            st.success(f"✅ Проект добавлен в очередь ({current_site}/{current_domain})")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning(f"⚠️ Проект уже в очереди")

        with col5:
            # Кнопка настроек
            if st.button("⚙️", key=f"settings_{pid}", help="Настройки проекта"):
                if app_state.load_project(pid):
                    st.session_state.current_project_id = pid
                    st.session_state.show_project_settings = True
                    st.session_state.view_mode = 'settings'
                    st.rerun()

        with col6:
            # Кнопка результатов
            if has_results:
                if st.button("📊", key=f"results_{pid}", help="Результаты генерации"):
                    if app_state.load_project(pid):
                        st.session_state.current_project_id = pid
                        st.session_state.show_project_settings = True
                        st.session_state.view_mode = 'unified_results'
                        st.rerun()
            else:
                st.button("📊", disabled=True, key=f"results_disabled_{pid}")

        # В _render_project_card внутри кнопки перезапуска:
        with col7:
            if st.button("🔄", key=f"restart_{pid}", help="Очистить и перезапустить"):
                if _restart_project(pid, project, app_state):
                    st.rerun()

        with col8:
            if st.button("🗑️", key=f"del_{pid}", help="Удалить проект"):
                from pathlib import Path
                import shutil

                base_path = Path(f"sites/{current_site}/domains/{current_domain}/projects/{st.session_state.user_id}")

                # 1. Удаляем JSON файл проекта
                project_file = base_path / f"{pid}.json"
                if project_file.exists():
                    project_file.unlink()
                    print(f"✅ Удален JSON: {project_file}")

                # 2. Удаляем папку с AI инструкциями
                ai_instructions_dir = base_path / f"{pid}_ai_instructions"
                if ai_instructions_dir.exists():
                    shutil.rmtree(ai_instructions_dir)
                    print(f"✅ Удалена папка AI инструкций: {ai_instructions_dir}")

                # 3. Удаляем другие возможные папки (бэкапы, временные файлы)
                backup_dir = base_path / f"{pid}_backup"
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                    print(f"✅ Удалена папка бэкапов: {backup_dir}")

                # 4. Удаляем из очереди
                from user_queue_manager import get_user_queue
                queue = get_user_queue()
                if queue and pid in queue.projects:
                    queue.remove_project(pid)
                    print(f"✅ Удален из очереди: {pid}")

                st.success(f"✅ Проект '{project['project_name']}' полностью удален")
                time.sleep(0.5)
                st.rerun()

        # Показываем ошибку если есть
        if status == 'failed' and status_info.get('error'):
            with st.expander("❌ Детали ошибки", expanded=False):
                st.error(status_info['error'][:500])

        # ✅ УДАЛЯЕМ ПРОЕКТ ИЗ МНОЖЕСТВА ПОСЛЕ РЕНДЕРИНГА
        if pid in st.session_state.get('_rendering_projects', set()):
            st.session_state._rendering_projects.discard(pid)

        st.divider()


# 6. ФУНКЦИЯ ДЛЯ КНОПКИ ПЕРЕЗАПУСКА
# ============================================
def debug_check_phase5_cleared(project_id: str):
    """Диагностика: проверяет, очистились ли данные phase5"""
    from pathlib import Path
    import json

    user_id = st.session_state.get('user_id')
    site = st.session_state.get('current_site', 'steelborg')
    domain = st.session_state.get('current_domain', 'default')

    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

    if not project_file.exists():
        st.error("❌ Файл не найден")
        return

    with open(project_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    st.markdown("### 🔍 Проверка phase5 после очистки")

    # Проверяем app_data.phase5
    phase5 = data.get('app_data', {}).get('phase5', {})
    st.write(f"**app_data.phase5:**")
    st.write(f"  - results: {bool(phase5.get('results'))}")
    st.write(f"  - phase_completed: {phase5.get('phase_completed')}")
    st.write(f"  - keys: {list(phase5.keys())}")

    # Проверяем отдельные ключи
    st.write(f"**app_data.phase5_results:** {bool(data.get('app_data', {}).get('phase5_results'))}")
    st.write(f"**app_data.phase5_completed:** {data.get('app_data', {}).get('phase5_completed')}")
    st.write(
        f"**app_data.phase4_generated_prompts:** {len(data.get('app_data', {}).get('phase4_generated_prompts', []))}")

    # Проверяем session_state
    st.write(f"**session_state.phase5_results:** {bool(st.session_state.get('phase5_results'))}")
    st.write(f"**session_state.phase5_completed:** {st.session_state.get('phase5_completed')}")

    if not phase5.get('results') and not st.session_state.get('phase5_results'):
        st.success("✅ Phase5 полностью очищена!")
    else:
        st.error("❌ Phase5 НЕ ОЧИЩЕНА! Остались данные.")
def _restart_project(project_id: str, project: dict, app_state):
    """ПЕРЕЗАПУСК - УДАЛЯЕТ ВСЕ РЕЗУЛЬТАТЫ ВКЛЮЧАЯ КОРНЕВОЙ phase5_results"""
    from pathlib import Path
    import json
    import shutil
    from datetime import datetime

    project_name = project.get('project_name', 'Проект')
    user_id = st.session_state.get('user_id')
    site = st.session_state.get('current_site', 'steelborg')
    domain = st.session_state.get('current_domain', 'default')

    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

    if not project_file.exists():
        st.error(f"❌ Файл проекта не найден в домене {domain}")
        return False

    with open(project_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # ========== СОХРАНЯЕМ НАСТРОЙКИ ==========
    phase1_settings = data.get('app_data', {}).get('phase1', {})
    phase2_settings = data.get('app_data', {}).get('phase2', {})
    phase4_settings = data.get('app_data', {}).get('phase4_settings', {})
    phase5_settings = data.get('app_data', {}).get('phase5_settings', {})
    category = data.get('category', '')
    project_name_saved = data.get('project_name', project_name)

    # ========== ОЧИЩАЕМ ВСЕ РЕЗУЛЬТАТЫ ==========
    if 'app_data' not in data:
        data['app_data'] = {}

    # Очищаем app_data фазы
    data['app_data']['phase3'] = {}
    data['app_data']['phase4'] = {}
    data['app_data']['phase5'] = {}
    data['app_data']['phase6'] = {}
    data['app_data']['phase7'] = {}

    # Очищаем флаги
    data['app_data']['phase3_generated'] = False
    data['app_data']['phase4_generated_prompts'] = []
    data['app_data']['phase5_completed'] = False
    data['app_data']['phase6_completed'] = False
    data['app_data']['phase7_completed'] = False
    data['app_data']['phase5_results'] = {}  # внутри app_data
    data['app_data']['phase4_generated_prompts'] = []

    # ✅ КРИТИЧЕСКИ ВАЖНО: УДАЛЯЕМ КОРНЕВОЙ phase5_results!
    if 'phase5_results' in data:
        del data['phase5_results']
        print("🗑️ Удален корневой phase5_results")

    # ✅ Также удаляем phase4_generated_prompts на корневом уровне если есть
    if 'phase4_generated_prompts' in data:
        del data['phase4_generated_prompts']

    # ✅ Удаляем statistics если есть
    if 'phase5_statistics' in data:
        del data['phase5_statistics']

    # Очищаем корневые поля
    data['current_phase'] = 3
    data['status'] = 'idle'
    data['progress'] = 0
    data['message'] = 'Готов к запуску'
    data['error'] = None

    # ========== ВОССТАНАВЛИВАЕМ НАСТРОЙКИ ==========
    data['app_data']['phase1'] = phase1_settings
    data['app_data']['phase2'] = phase2_settings
    if phase4_settings:
        data['app_data']['phase4_settings'] = phase4_settings
    if phase5_settings:
        data['app_data']['phase5_settings'] = phase5_settings

    data['category'] = category
    data['project_name'] = project_name_saved
    data['user_id'] = user_id
    data['site_name'] = site
    data['domain_name'] = domain

    # ========== СОХРАНЯЕМ ==========
    with open(project_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # ========== ОЧИЩАЕМ session_state ==========
    for phase in ['phase3', 'phase4', 'phase5', 'phase6', 'phase7']:
        if phase in st.session_state:
            st.session_state[phase] = {}

    st.session_state.phase5_results = {}
    st.session_state.phase5_completed = False
    st.session_state.phase5_statistics = {}
    st.session_state.phase5_prompts = []
    st.session_state.phase4_generated_prompts = []
    st.session_state.phase6 = {}
    st.session_state.phase6_logs = []

    if 'app_data' in st.session_state:
        st.session_state.app_data['phase3'] = {}
        st.session_state.app_data['phase4'] = {}
        st.session_state.app_data['phase5'] = {}
        st.session_state.app_data['phase6'] = {}
        st.session_state.app_data['phase7'] = {}
        st.session_state.app_data['phase5_completed'] = False
        st.session_state.app_data['phase5_results'] = {}
        st.session_state.app_data['phase4_generated_prompts'] = []
        st.session_state.app_data['current_phase'] = 3

    # ========== ОЧИЩАЕМ ОЧЕРЕДЬ ==========
    from user_queue_manager import get_user_queue
    queue = get_user_queue()
    if queue and project_id in queue.projects:
        del queue.projects[project_id]
        queue._save_queue()

    # ========== ПЕРЕЗАГРУЖАЕМ ==========
    st.session_state.current_project_id = project_id
    st.session_state.current_phase = 3

    if app_state.load_project(project_id):
        st.session_state._refresh_projects = True
        if 'project_cache' in st.session_state:
            del st.session_state.project_cache
        st.success(f"✅ Проект «{project_name_saved}» перезапущен - все результаты очищены")
        time.sleep(0.5)
        st.rerun()
        return True

    return False
def _render_project_statistics(projects, projects_with_status):
    """Рендерит статистику по проектам"""
    with st.expander("📊 Статистика", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего проектов", len(projects))
        with col2:
            completed = len([p for p, s in projects_with_status if s.get('status') == 'completed'])
            st.metric("Завершенных", completed)
        with col3:
            active = len([p for p, s in projects_with_status if s.get('status') in ['running', 'queued']])
            st.metric("В работе", active)
        with col4:
            total_phases = sum(p['current_phase'] for p, _ in projects_with_status)
            avg_phase = total_phases / len(projects) if projects else 0
            st.metric("Средняя фаза", f"{avg_phase:.1f}")
def render_worker_controls():
    """Рендерит кнопки управления воркером"""
    queue = get_user_queue()
    if queue is None:
        st.warning("⚠️ Очередь не инициализирована")
        return

    is_running = queue.is_worker_running()

    st.markdown("### ⚙️ Управление воркером")

    col1, col2, col3 = st.columns(3)

    with col1:
        if is_running:
            st.success("🟢 Воркер ЗАПУЩЕН")
        else:
            st.error("🔴 Воркер ОСТАНОВЛЕН")

    with col2:
        if not is_running:
            if st.button("▶ Запустить воркер", type="primary", use_container_width=True):
                if queue.start_worker():
                    st.success("✅ Воркер запущен!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Не удалось запустить воркер")
        else:
            if st.button("⏹ Остановить воркер", type="secondary", use_container_width=True):
                if queue.stop_worker():
                    st.warning("⚠️ Воркер остановлен")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Не удалось остановить воркер")

    with col3:
        if is_running:
            queue_size = queue._queue.qsize()
            active = len([p for p in queue.projects.values() if p.status == ProjectStatus.RUNNING])
            st.caption(f"📋 В очереди: {queue_size}")
            st.caption(f"🔄 Активных: {active}")
        else:
            st.caption("⏸ Воркер неактивен")
def render_auto_actions_and_status_improved(app_state):
    from user_queue_manager import ProjectStatus
    st.markdown("### 🚀 Управление очередью")
    st.markdown("---")
    render_worker_controls()
    st.markdown("---")
    # ✅ Добавить синхронизацию домена в начале
    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    current_site = dm.site_name
    current_domain = dm.get_current_domain()

    # Сохраняем в session_state
    st.session_state.current_site = current_site
    st.session_state.current_domain = current_domain
    st.session_state[f'domain_system_{current_site}'] = current_domain

    # Синхронизируем auto_domain_loaded
    domain_key = f"{current_site}_{current_domain}"
    if st.session_state.get('auto_domain_loaded') != domain_key:
        st.session_state.auto_domain_loaded = domain_key

    st.markdown("---")
    if is_admin():
        if st.button("🔬 ДИАГНОСТИКА WORKER'А", type="secondary", use_container_width=True):
            diagnose_worker_status()
            st.stop()

    queue = get_user_queue()
    if queue is None:
        st.error("Ошибка: очередь не инициализирована")
        return

    # ✅ ТОЛЬКО РЕАЛЬНЫЕ ПРОЕКТЫ В ОЧЕРЕДИ
    all_projects = queue.get_all_projects()

    # ✅ ОПРЕДЕЛЯЕМ has_active
    has_active = any(p.status in [ProjectStatus.RUNNING, ProjectStatus.QUEUED]
                     for p in all_projects.values())

    if has_active:
        st.info("🟢 **Есть активные задачи** - статус обновляется автоматически")
        if 'last_refresh' not in st.session_state:
            st.session_state.last_refresh = time.time()

        if time.time() - st.session_state.last_refresh > 3:
            st.session_state.last_refresh = time.time()
            # ❌ НЕ ДЕЛАЕМ st.rerun() чтобы не было бесконечного цикла!

    # ✅ КНОПКА ПРИНУДИТЕЛЬНОЙ СИНХРОНИЗАЦИИ
    col_sync1, col_sync2 = st.columns(2)
    with col_sync1:
        if st.button("🔄 Синхронизировать статус со всеми проектами", use_container_width=True):
            # Перезагружаем статус каждого проекта из файла
            for pid, task in queue.projects.items():
                project_file = Path(f"projects/{task.user_id}/{pid}.json")
                if project_file.exists():
                    try:
                        with open(project_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if 'status' in data:
                                task.status = ProjectStatus(data['status'])
                                task.current_phase = data.get('current_phase', 0)
                                task.progress = data.get('progress', 0)
                                task.message = data.get('message', '')
                                log(f"Синхронизирован {task.project_name}: {task.status.value}")
                    except Exception as e:
                        log(f"Ошибка синхронизации {pid}: {e}")
            st.success("✅ Статусы синхронизированы!")
            st.rerun()

    with col_sync2:
        if st.button("📊 Показать активные фоновые задачи", use_container_width=True):
            active = [p for p in queue.projects.values() if p.status == ProjectStatus.RUNNING]
            if active:
                for p in active:
                    st.info(f"🟢 {p.project_name}: фаза {p.current_phase}/7 - {p.message}")
            else:
                st.info("Нет активных фоновых задач")

    # Диагностика
    queue_status = {
        'total_projects': len(queue.projects),
        'queue_size': queue._queue.qsize(),
        'worker_running': queue._running and hasattr(queue, '_thread') and queue._thread.is_alive(),
        'active_workers': len([p for p in queue.projects.values() if p.status == ProjectStatus.RUNNING]),
        'queued_count': len([p for p in queue.projects.values() if p.status == ProjectStatus.QUEUED]),
    }

    # Отображаем статус
    col_status1, col_status2, col_status3, col_status4 = st.columns(4)
    with col_status1:
        if queue_status['worker_running']:
            st.success("✅ Worker активен")
        else:
            st.error("❌ Worker НЕ активен!")

    with col_status2:
        st.metric("В очереди (queue)", queue_status['queue_size'])
    with col_status3:
        st.metric("Проектов QUEUED", queue_status['queued_count'])
    with col_status4:
        st.metric("Активных задач", queue_status['active_workers'])

    st.markdown("---")

    # ✅ КНОПКИ С ЗАЩИТОЙ ОТ ДУБЛИРОВАНИЯ
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        if st.button("🔄 Обновить", use_container_width=True):
            # ✅ ПРИНУДИТЕЛЬНО СОХРАНЯЕМ ДАННЫЕ ПЕРЕД ОБНОВЛЕНИЕМ
            if 'app_state' in locals() and app_state:
                app_state.save_project()
            st.success("✅ Статус обновлен")

    with col2:
        if st.button("▶ Запустить всю очередь", type="primary", use_container_width=True):
            queued = [pid for pid, task in queue.projects.items() if task.status == ProjectStatus.QUEUED]
            added = 0

            for pid in queued:
                queue._queue.put({'project_id': pid, 'user_id': queue.user_id})
                added += 1

            queue._save_queue()
            st.success(f"✅ Добавлено {added} проектов")
            time.sleep(0.5)
            st.rerun()

    with col3:
        if st.button("🗑️ Очистить завершённые", use_container_width=True):
            cleared = queue.clear_completed()
            if cleared > 0:
                st.success(f"✅ Очищено {cleared} проектов")
            else:
                st.info("Нет завершённых проектов для очистки")
            time.sleep(0.5)
            st.rerun()

    with col4:
        if st.button("🧹 Очистить очередь worker'а", use_container_width=True, help="Удаляет все ожидающие задачи из очереди worker'а (не трогает проекты)"):
            while not queue._queue.empty():
                try:
                    queue._queue.get_nowait()
                    queue._queue.task_done()
                except queue.Empty:
                    break
            st.success("✅ Очередь worker'а очищена!")
            st.rerun()

    with col5:
        if st.button("🚨 Force запуск", use_container_width=True, type="secondary"):
            queued = [pid for pid, task in queue.projects.items() if task.status == ProjectStatus.QUEUED]
            for pid in queued:
                queue._queue.put({'project_id': pid, 'user_id': queue.user_id})
            st.success(f"✅ Принудительно добавлено {len(queued)} проектов")
            st.rerun()

    st.markdown("---")

    if not all_projects:
        st.info("📭 Нет активных проектов")
        return

    # Отображение списка проектов В ОЧЕРЕДИ
    st.markdown("### 📋 Проекты в очереди")

    for pid, task in all_projects.items():
        status = task.status.value
        project_name = task.project_name[:40]
        current_phase = task.current_phase
        message = task.message
        progress = task.progress
        error = task.error

        # Выбор иконки
        icon = {"running": "🟢", "completed": "✅", "failed": "❌", "queued": "🟡"}.get(status, "⚪")

        with st.container():
            col1, col2, col3 = st.columns([3, 3, 1])

            with col1:
                st.markdown(f"{icon} **{project_name}**")
                st.caption(f"{pid[:8]}...")

            with col2:
                if status == 'running':
                    st.markdown("🟢 **ВЫПОЛНЯЕТСЯ**")
                    if message:
                        st.caption(f"📝 {message[:60]}")
                    if current_phase:
                        st.progress(progress / 100, text=f"Фаза {current_phase}/7 — {progress:.0f}%")
                elif status == 'queued':
                    st.markdown("🟡 **В ОЧЕРЕДИ**")
                    # Проверяем, действительно ли проект в очереди worker'а
                    in_worker_queue = any(item.get('project_id') == pid for item in list(queue._queue.queue))
                    if not in_worker_queue and status == 'queued':
                        st.warning("⚠️ В статусе QUEUED, но НЕ в очереди worker'а!")
                        if st.button("📥 Добавить в очередь", key=f"add_to_queue_{pid}"):
                            queue._queue.put({'project_id': pid, 'user_id': task.user_id})
                            st.rerun()
                elif status == 'completed':
                    st.markdown("✅ **ЗАВЕРШЁН**")
                elif status == 'failed':
                    st.markdown("❌ **ОШИБКА**")
                    if error:
                        with st.expander("Детали"):
                            st.error(error[:200])

            with col3:
                if status == 'queued':
                    if st.button("▶", key=f"force_{pid}", help="Запустить сейчас"):
                        # Проверяем, есть ли уже в очереди
                        already_in_queue = any(item.get('project_id') == pid for item in list(queue._queue.queue))
                        if not already_in_queue:
                            queue._queue.put({'project_id': pid, 'user_id': task.user_id})
                            st.success("✅ Добавлен в очередь!")
                        else:
                            st.warning("⚠️ Уже в очереди!")
                        st.rerun()

            st.divider()

# ДОБАВИТЬ ЭТУ ФУНКЦИЮ В КОД (после импортов или перед main())
def reset_to_main_menu():
    """Сбрасывает все флаги и возвращает на главный экран выбора модуля"""
    st.session_state.app_mode = None
    st.session_state.module_selected = False
    st.session_state.selected_module = None
    st.session_state.selected_site = None
    st.session_state.selected_domain = None
    st.session_state.current_project_id = None
    st.session_state.show_project_selector = False
    st.session_state.show_project_settings = False
    st.session_state.view_mode = 'settings'
    st.session_state.show_queue_panel = False
    st.session_state.show_profile = False
    st.session_state.show_ai_config = False
    st.session_state.show_domain_in_manual = False
    st.session_state.show_new_project_form = False

    # Очищаем кэшированные данные
    for key in ['auto_domain_loaded', 'domain_data_loaded', 'phase7_data_loaded']:
        if key in st.session_state:
            del st.session_state[key]

    # ===== ДОБАВИТЬ ЭТУ СТРОКУ =====
    st.rerun()
def render_auth_buttons():
    """Рендерит кнопки профиля и выхода с надёжной защитой от дубликатов"""

    # Защита: отмечаем, что кнопки уже отрендерены в этом цикле
    if st.session_state.get('_auth_buttons_rendered', False):
        return False

    st.session_state._auth_buttons_rendered = True

    # Создаём максимально уникальные ключи
    timestamp = int(time.time() * 1000) % 100000  # добавляем случайность
    context = st.session_state.get('app_mode', 'main')
    if st.session_state.get('show_project_settings', False):
        context = 'settings'
    if st.session_state.get('view_mode') == 'unified_results':
        context = 'results'

    profile_key = f"global_profile_btn_{context}_{timestamp}"
    logout_key = f"global_logout_btn_{context}_{timestamp}"
    home_key = f"global_home_btn_{context}_{timestamp}"

    col1, col2, col3, col4 = st.columns([1, 1, 1, 5])

    with col1:
        if st.button("👤 Профиль", use_container_width=True, key=profile_key):
            st.session_state.show_profile = True
            st.rerun()

    with col2:
        if st.button("🚪 Выйти", use_container_width=True, key=logout_key):
            # Полная очистка
            st.session_state.app_mode = None
            st.session_state.module_selected = False
            st.session_state.selected_module = None
            st.session_state.selected_site = None
            st.session_state.selected_domain = None
            st.session_state.current_project_id = None
            st.session_state.show_project_settings = False
            auth.logout()
            st.rerun()

    with col3:
        if st.session_state.get('module_selected', False) or st.session_state.get('app_mode') is not None:
            if st.button("🏠 Главная", use_container_width=True, key=home_key):
                reset_to_main_menu()

    # Отображаем профиль если открыт
    if st.session_state.get("show_profile", False):
        try:
            from database_settings import auth
            auth.profile_page()
        except Exception as e:
            st.error(f"Ошибка открытия профиля: {e}")

        if st.button("← Закрыть профиль", key=f"close_profile_{context}"):
            st.session_state.show_profile = False
            st.rerun()
        return True

    return False


def render_module_specific_buttons(app_state=None):
    """Рендерит кнопки специфичные для модуля Тексты (сменить проект, сохранить, очереди, AI)"""
    # Создаем app_state если не передан
    if app_state is None:
        app_state = AppState()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("📁 Сменить проект", use_container_width=True, key="module_change_project"):
            st.session_state.show_project_selector = True
            st.rerun()

    with col2:
        if st.button("💾 Сохранить", use_container_width=True, key="module_save_project"):
            if st.session_state.get('current_project_id'):
                app_state.save_project()
                st.success("✅ Проект сохранен")

    with col3:
        if st.button("📊 Очереди", use_container_width=True, key="module_show_queue"):
            st.session_state.show_queue_panel = not st.session_state.show_queue_panel
            st.rerun()

    with col4:
        if st.button("🤖 AI", use_container_width=True, key="module_show_ai"):
            st.session_state.show_ai_config = True
            st.rerun()

    # Отображаем панель очереди если нужно
    render_queue_panel()

    # Отображаем AI настройки если нужно (профиль уже обработан в render_auth_buttons)
    if st.session_state.get("show_ai_config", False):
        st.title("🤖 Настройки AI")
        try:
            from ai_settings.ai_config import show_ai_config_interface
            show_ai_config_interface()
        except Exception as e:
            st.error(f"Ошибка загрузки настроек AI: {e}")
        if st.button("← Назад", key="back_from_ai"):
            st.session_state.show_ai_config = False
            st.rerun()
        return True

    return False
# В самом начале main(), после st.set_page_config, добавьте:

def init_session_state_keys():
    """Инициализирует все необходимые ключи session_state"""
    defaults = {
        'phase4_generated_prompts': [],
        'phase5_results': {},
        'phase5_completed': False,
        'phase6_completed': False,
        'phase7_completed': False,
        'phase5_statistics': {},
        'phase6_logs': [],
        'phase4_char_settings': {},
        'phase4_other_blocks_settings': {},
        'phase4_global_prompts': 3,
        'phase5_settings': {},
        'phase6': {},
        'phase7': {},
    }

    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def main():
    st.set_page_config(page_title="Data Harvester Pro", layout="wide", initial_sidebar_state="expanded")
    init_session_state_keys()
    load_css()


    # ✅ Восстанавливаем сохранённый домен при запуске
    app_state = AppState()

    render_manual_header(app_state)

    # === ИНИЦИАЛИЗАЦИЯ СТРУКТУРЫ САЙТОВ И ДОМЕНОВ ===
    if 'sites_initialized' not in st.session_state:
        from pathlib import Path
        import json
        from datetime import datetime
        from domain_manager import DomainManager

        sites_dir = Path("sites")
        sites_dir.mkdir(exist_ok=True)

        # Создаем steelborg сайт если его нет
        steelborg_dir = sites_dir / "steelborg"
        if not steelborg_dir.exists():
            steelborg_dir.mkdir(parents=True, exist_ok=True)

            # Создаем конфиг steelborg
            steelborg_config = {
                "site_name": "steelborg",
                "display_name": "Steelborg",
                "description": "Основной сайт Steelborg",
                "created_at": datetime.now().isoformat(),
                "modules": ["texts", "faq", "reviews"],
                "default_module": "texts",
                "ai_config": {
                    "default_provider": "deepseek",
                    "default_model": "deepseek-chat",
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
            }

            with open(steelborg_dir / "config.json", 'w', encoding='utf-8') as f:
                json.dump(steelborg_config, f, ensure_ascii=False, indent=2)

            # Создаем структуру доменов для steelborg
            domains_dir = steelborg_dir / "domains"
            domains_dir.mkdir(exist_ok=True)

            # Создаем дефолтный домен
            dm = DomainManager("steelborg")
            dm._create_default_domain()

        st.session_state.sites_initialized = True
        st.session_state.current_site = "steelborg"

    # ... остальной код main() без изменений ...

    # Аутентификация
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "session_token" not in st.session_state:
        st.session_state.session_token = None

    if not st.session_state.authenticated:
        query_params = st.query_params
        if "token" in query_params:
            token = query_params["token"]
            from database_settings.database import validate_session
            user_data = validate_session(token)
            if user_data:
                st.session_state.authenticated = True
                st.session_state.user_id = user_data["user_id"]
                st.session_state.username = user_data["username"]
                st.session_state.session_token = token
                st.query_params.clear()
                st.rerun()

    if not st.session_state.authenticated:
        auth.login_form()
        return

    # ===== ЗАГРУЗКА ДОМЕНА ПОЛЬЗОВАТЕЛЯ =====
    if st.session_state.authenticated:
        if 'domain_manager' not in st.session_state:
            from domain_manager import DomainManager
            st.session_state.domain_manager = DomainManager()

        dm = st.session_state.domain_manager
        user_id = st.session_state.get('user_id')

        # ✅ ЗАГРУЖАЕМ НАСТРОЙКИ
        settings = dm.load_user_settings(user_id)

        st.session_state.selected_domain = settings.get('selected_domain', 'default')
        st.session_state.current_domain = settings.get('selected_domain', 'default')
        st.session_state.selected_site = settings.get('selected_site', 'steelborg')
        st.session_state.current_site = settings.get('selected_site', 'steelborg')
        st.session_state[f'domain_system_{st.session_state.current_site}'] = st.session_state.current_domain
        print(f"✅ Загружены настройки пользователя {user_id}: домен={st.session_state.selected_domain}")
    init_queue_manager()

    col1, col2, col3 = st.columns([1, 8, 1])
    with col3:
        from styles import init_theme, toggle_theme
        init_theme()
        theme_icon = "🌙" if st.session_state.theme == 'light' else "☀️"
        if st.button(theme_icon, key="global_theme_toggle", help="Переключить тему"):
            toggle_theme()
            st.rerun()

    # AI Config
    if 'ai_config_manager' not in st.session_state:
        try:
            from ai_settings.ai_module import AIConfigManager
            st.session_state.ai_config_manager = AIConfigManager()
            print("✅ AIConfigManager initialized")
        except Exception as e:
            print(f"⚠️ Failed to initialize AIConfigManager: {e}")
            st.session_state.ai_config_manager = None

    # Проверка пользователя
    try:
        from database_settings.database import get_db
        with get_db() as conn:
            user = conn.execute("SELECT id, username, status FROM users WHERE id = ?", (st.session_state.get("user_id"),)).fetchone()
            if not user or user["status"] != "approved":
                st.error("Доступ отозван или аккаунт не найден.")
                auth.logout()
                return
            st.session_state.username = user["username"]
    except Exception as e:
        st.error(f"Ошибка проверки сессии: {e}")
        auth.logout()
        return


    # ===== НОВЫЙ КОД: ВЫБОР МОДУЛЯ =====
    # Показываем выбор модуля только если не выбран режим работы
    if st.session_state.get('app_mode') is None and not st.session_state.get('module_selected', False):
        render_module_selection()
        return

    # Если выбран модуль, но не выбран режим работы
    if st.session_state.get('module_selected', False) and st.session_state.get('app_mode') is None:
        render_mode_selection()
        return

    # Если выбран модуль и режим - запускаем соответствующий режим
    if st.session_state.get('app_mode') == 'manual':
        render_manual_mode_with_domain()
    elif st.session_state.get('app_mode') == 'auto':
        render_auto_mode()
    else:
        # По умолчанию показываем выбор модуля
        render_module_selection()


def render_module_selection():
    """Рендерит выбор модуля (тексты/FAQ/отзывы) с выбором сайта"""

    st.markdown("<h1 style='text-align: center;'>📀 Data Harvester Pro</h1>", unsafe_allow_html=True)
    render_auth_buttons()
    st.markdown("<p style='text-align: center;'>Выберите сайт и модуль для работы</p>", unsafe_allow_html=True)
    st.markdown("---")

    from site_manager import SiteManager, render_site_selector, render_site_admin_panel

    if 'site_manager' not in st.session_state:
        st.session_state.site_manager = SiteManager()

    sm = st.session_state.site_manager

    if st.session_state.get('show_site_manager', False):
        render_site_admin_panel()
        return

    st.markdown("### 🏢 Шаг 1: Выберите сайт")
    selected_site = render_site_selector()

    site_config = sm.get_site_config(selected_site)
    site_display = site_config.get('display_name', selected_site.capitalize())

    st.markdown("---")

    st.markdown("### 🌍 Шаг 2: Выберите домен/регион")

    if 'domain_manager' not in st.session_state or st.session_state.domain_manager.site_name != selected_site:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager(selected_site)

    dm = st.session_state.domain_manager

    # Отображаем селектор доменов
    from domain_manager import render_domain_selector
    selected_domain = render_domain_selector(phase=0, key_suffix="module_selection")
    # ↑ render_domain_selector САМ ОБНОВЛЯЕТ session_state при нажатии кнопки

    # ✅ НЕ ОБНОВЛЯЕМ session_state ЗДЕСЬ!
    # st.session_state.current_domain = selected_domain  ← УДАЛИ ЭТУ СТРОКУ!
    # st.session_state[f'domain_system_{selected_site}'] = selected_domain  ← УДАЛИ ЭТУ СТРОКУ!

    domain_display = dm.get_domain_display_name(st.session_state.get('current_domain', 'default'))

    st.markdown("---")

    st.markdown("### 📦 Шаг 3: Выберите модуль")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="mode-card">
            <h2>📝 Тексты</h2>
            <p>Полный цикл генерации SEO-текстов</p>
            <p style="color: #7f9f6f;">7 фаз: от сбора данных до подготовки к загрузке</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("📝 Модуль Тексты", use_container_width=True, key="select_texts_module"):
            # ✅ СОХРАНЯЕМ ВСЕ НЕОБХОДИМЫЕ ДАННЫЕ ПЕРЕД ПЕРЕХОДОМ
            st.session_state.selected_module = 'texts'
            st.session_state.module_selected = True
            st.session_state.selected_site = selected_site
            st.session_state.selected_domain = selected_domain
            st.session_state.app_mode = None

            # ✅ Сохраняем выбранный домен в DomainManager
            if 'domain_manager' in st.session_state:
                st.session_state.domain_manager.set_current_domain(selected_domain)

            # ✅ НЕ устанавливаем auto_domain_loaded здесь, чтобы при входе в режим данные загрузились
            # Просто сохраняем выбранный домен
            st.session_state.last_selected_domain = selected_domain
            st.session_state.last_selected_site = selected_site

            st.rerun()

    with col2:
        st.markdown("""
        <div class="mode-card">
            <h2>❓ FAQ</h2>
            <p>Генерация вопросов и ответов</p>
            <p style="color: #f59e0b;">🚧 В разработке</p>
        </div>
        """, unsafe_allow_html=True)

        st.button("❓ Модуль FAQ", disabled=True, use_container_width=True, key="select_faq_module")

    with col3:
        st.markdown("""
        <div class="mode-card">
            <h2>⭐ Отзывы</h2>
            <p>Генерация пользовательских отзывов</p>
            <p style="color: #f59e0b;">🚧 В разработке</p>
        </div>
        """, unsafe_allow_html=True)

        st.button("⭐ Модуль Отзывы", disabled=True, use_container_width=True, key="select_reviews_module")

    st.markdown("---")

    try:
        from database_settings.auth import is_admin
        if is_admin(st.session_state.get('user_id')):
            if st.button("⚙️ Управление сайтами и доменами (Админка)", use_container_width=True):
                st.session_state.show_site_manager = True
                st.rerun()
    except Exception as e:
        if st.button("⚙️ Управление сайтами и доменами", use_container_width=True):
            st.session_state.show_site_manager = True
            st.rerun()

    with st.expander("ℹ️ Текущая конфигурация", expanded=False):
        st.write(f"**Сайт:** {site_display} ({selected_site})")
        st.write(f"**Домен:** {domain_display} ({selected_domain})")
        st.write(f"**Путь к данным:** `sites/{selected_site}/domains/{selected_domain}/`")


def render_mode_selection():
    """Рендерит выбор режима работы (ручной/автоматический)"""

    st.markdown("<h1 style='text-align: center;'>📀 Data Harvester Pro</h1>", unsafe_allow_html=True)
    render_auth_buttons()
    # ✅ Восстанавливаем выбранную конфигурацию из session_state
    site_display = st.session_state.get('selected_site', 'steelborg')
    domain_display = st.session_state.get('selected_domain', 'default')
    module = st.session_state.get('selected_module', 'Тексты')

    # ✅ Убеждаемся, что DomainManager использует правильный сайт и домен
    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager(site_display)

    dm = st.session_state.domain_manager

    # ✅ Если сайт не совпадает, обновляем DomainManager
    if dm.site_name != site_display:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager(site_display)
        dm = st.session_state.domain_manager

    # ✅ Устанавливаем правильный домен в DomainManager
    dm.set_current_domain(domain_display)

    # ✅ Сохраняем в session_state для синхронизации
    st.session_state.current_site = site_display
    st.session_state.current_domain = domain_display
    st.session_state[f'domain_system_{site_display}'] = domain_display

    # Получаем отображаемые имена
    try:
        from site_manager import SiteManager
        sm = SiteManager()
        site_config = sm.get_site_config(site_display)
        site_display_name = site_config.get('display_name', site_display)
    except:
        site_display_name = site_display

    try:
        domain_display_name = dm.get_domain_display_name(domain_display)
    except:
        domain_display_name = domain_display

    st.markdown(f"<p style='text-align: center;'>Сайт: <strong>{site_display_name}</strong> | Домен: <strong>{domain_display_name}</strong> | Модуль: <strong>{module}</strong></p>", unsafe_allow_html=True)
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div class="mode-card">
            <h2>🔧 Ручной режим</h2>
            <p>Пошаговое выполнение каждой фазы</p>
            <p style="color: #7f9f6f;">Подходит для тонкой настройки</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🔧 Ручной режим", use_container_width=True, key="manual_mode_btn"):
            st.session_state.app_mode = 'manual'
            st.session_state.current_site = site_display
            st.session_state.current_domain = domain_display
            st.session_state[f'domain_system_{site_display}'] = domain_display
            st.rerun()

    with col2:
        st.markdown("""
        <div class="mode-card">
            <h2>🤖 Автоматический режим</h2>
            <p>Фоновое выполнение проектов</p>
            <p style="color: #b08968;">Запустите проект и занимайтесь другими делами</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🤖 Автоматический режим", use_container_width=True, key="auto_mode_btn"):
            st.session_state.app_mode = 'auto'
            st.session_state.current_site = site_display
            st.session_state.current_domain = domain_display
            st.session_state[f'domain_system_{site_display}'] = domain_display
            st.rerun()

    # Кнопка назад к выбору модуля
    col_back1, col_back2, col_back3 = st.columns([1, 2, 1])
    with col_back2:
        if st.button("← Назад к выбору сайта и модуля", use_container_width=True):
            st.session_state.module_selected = False
            st.session_state.selected_module = None
            st.session_state.selected_site = None
            st.session_state.selected_domain = None
            st.session_state.app_mode = None
            # Очищаем все флаги домена
            for key in ['auto_domain_loaded', 'domain_data_loaded', 'phase7_data_loaded']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

if __name__ == "__main__":
    main()