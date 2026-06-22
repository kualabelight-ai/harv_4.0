import json
import streamlit as st
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

class UserDataManager:
    """Менеджер данных с привязкой к пользователю"""

    @staticmethod
    def get_current_context():
        """Получает текущий контекст (пользователь, сайт, домен, проект) из session_state"""
        try:
            user_id = st.session_state.get('user_id')
            project_id = st.session_state.get('current_project_id')
            site = st.session_state.get('current_site', 'steelborg')
            domain = st.session_state.get('current_domain', 'default')

            if not user_id or not project_id:
                return None

            return {
                'user_id': user_id,
                'project_id': project_id,
                'site': site,
                'domain': domain,
                'key': f"{user_id}_{site}_{domain}_{project_id}"
            }
        except Exception as e:
            print(f"Ошибка получения контекста: {e}")
            return None

    # ========== НОВЫЙ МЕТОД: ЯВНЫЙ КОНТЕКСТ ==========
    @staticmethod
    def get_context_from_params(user_id: int, project_id: str, site: str, domain: str) -> Dict:
        """Создает контекст из явно переданных параметров (для воркера)"""
        return {
            'user_id': user_id,
            'project_id': project_id,
            'site': site,
            'domain': domain,
            'key': f"{user_id}_{site}_{domain}_{project_id}"
        }

    # ========== ИЗМЕНЕННЫЙ МЕТОД: ПРИНИМАЕТ КОНТЕКСТ ==========
    @staticmethod
    def get_file_path(context: Dict = None):
        """Возвращает путь к файлу проекта"""
        if context is None:
            ctx = UserDataManager.get_current_context()
        else:
            ctx = context

        if not ctx:
            return None
        return Path(f"sites/{ctx['site']}/domains/{ctx['domain']}/projects/{ctx['user_id']}/{ctx['project_id']}.json")

    # ========== ИЗМЕНЕННЫЙ МЕТОД: ПРИНИМАЕТ КОНТЕКСТ ==========
    @staticmethod
    def get_user_data(context: Dict = None):
        """Загружает данные для пользователя"""
        if context is None:
            ctx = UserDataManager.get_current_context()
        else:
            ctx = context

        if not ctx:
            return {}

        # Кэш с привязкой к пользователю
        cache_key = f"user_data_{ctx['key']}"
        if cache_key in st.session_state:
            return st.session_state[cache_key]

        file_path = UserDataManager.get_file_path(ctx)
        if not file_path or not file_path.exists():
            return {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                app_data = data.get('app_data', {})

                st.session_state[cache_key] = app_data
                return app_data
        except:
            return {}

    # ========== ИЗМЕНЕННЫЙ МЕТОД: ПРИНИМАЕТ КОНТЕКСТ ==========
    @staticmethod
    def set_user_data(data, context: Dict = None):
        """Сохраняет данные для пользователя"""
        if context is None:
            ctx = UserDataManager.get_current_context()
        else:
            ctx = context

        if not ctx:
            print("❌ set_user_data: нет контекста")
            return False

        print(f"💾 set_user_data: user={ctx['user_id']}, project={ctx['project_id']}")

        file_path = UserDataManager.get_file_path(ctx)
        if not file_path:
            return False

        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    full_data = json.load(f)
            else:
                full_data = {
                    "project_id": ctx['project_id'],
                    "user_id": ctx['user_id'],
                    "site_name": ctx['site'],
                    "domain_name": ctx['domain'],
                    "created_at": datetime.now().isoformat()
                }

            full_data['app_data'] = data
            full_data['updated_at'] = datetime.now().isoformat()

            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)

            # Обновляем кэш
            cache_key = f"user_data_{ctx['key']}"
            st.session_state[cache_key] = data

            return True
        except Exception as e:
            print(f"Ошибка сохранения: {e}")
            return False

    # ========== ИЗМЕНЕННЫЙ МЕТОД: ПРИНИМАЕТ КОНТЕКСТ ==========
    @staticmethod
    def get_phase5_completed(context: Dict = None):
        """Проверяет завершена ли фаза 5"""
        data = UserDataManager.get_user_data(context)
        phase5 = data.get('phase5', {})

        return (
                phase5.get('phase_completed', False) or
                data.get('phase5_completed', False) or
                bool(phase5.get('results'))
        )

    # ========== ИЗМЕНЕННЫЙ МЕТОД: ПРИНИМАЕТ КОНТЕКСТ ==========
    @staticmethod
    def get_phase5_results(context: Dict = None):
        """Получает результаты фазы 5"""
        data = UserDataManager.get_user_data(context)
        phase5 = data.get('phase5', {})
        return phase5.get('results', {})

    @staticmethod
    def clear_cache(context: Dict = None):
        """Очищает кэш для контекста"""
        if context is None:
            ctx = UserDataManager.get_current_context()
        else:
            ctx = context

        if ctx:
            cache_key = f"user_data_{ctx['key']}"
            if cache_key in st.session_state:
                del st.session_state[cache_key]




# user_queue_manager.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
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
import streamlit as st

def ensure_session_state():
    """Гарантирует, что все необходимые ключи session_state инициализированы"""
    if 'app_data' not in st.session_state:
        st.session_state.app_data = {}
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'current_site' not in st.session_state:
        st.session_state.current_site = 'steelborg'
    if 'current_domain' not in st.session_state:
        st.session_state.current_domain = 'default'
    if 'current_project_id' not in st.session_state:
        st.session_state.current_project_id = None
sys.stderr = SuppressStream()