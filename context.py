# context.py
from pathlib import Path
import json
from datetime import datetime
import streamlit as st


class ProjectContext:
    """Локальный контекст проекта - НЕ ИСПОЛЬЗУЕТ st.session_state"""

    def __init__(self, user_id: int, project_id: str, site_name: str = None, domain_name: str = None):
        self.user_id = user_id
        self.project_id = project_id

        # ✅ ЕСЛИ ДОМЕН НЕ ПЕРЕДАН - ЗАГРУЖАЕМ ИЗ ФАЙЛА
        if site_name is None or domain_name is None:
            try:
                from domain_manager import DomainManager

                if 'domain_manager' not in st.session_state:
                    st.session_state.domain_manager = DomainManager()

                dm = st.session_state.domain_manager

                # Загружаем домен пользователя из файла
                if user_id:
                    settings = dm.load_user_settings(user_id)
                    site_name = site_name or settings.get('selected_site', 'steelborg')
                    domain_name = domain_name or settings.get('selected_domain', 'default')

                    # Обновляем session_state для синхронизации
                    st.session_state.current_domain = domain_name
                    st.session_state.selected_domain = domain_name
                    st.session_state.current_site = site_name
                    st.session_state.selected_site = site_name
                    st.session_state[f'domain_system_{site_name}'] = domain_name

                    print(f"✅ ProjectContext загружен домен из файла: {site_name}/{domain_name}")
            except Exception as e:
                print(f"⚠️ ProjectContext: ошибка загрузки домена: {e}")
                site_name = site_name or 'steelborg'
                domain_name = domain_name or 'default'

        self.site_name = site_name
        self.domain_name = domain_name
        self.data = {}  # Сюда загружаем app_data из файла
        self.project_file = None
        self._loaded = False

    def load(self) -> bool:
        """Загружает данные из файла"""
        self.project_file = Path(
            f"sites/{self.site_name}/domains/{self.domain_name}/projects/{self.user_id}/{self.project_id}.json"
        )

        if not self.project_file.exists():
            print(f"❌ Файл не найден: {self.project_file}")
            return False

        try:
            with open(self.project_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
                self.data = file_data.get('app_data', {})
                self._loaded = True
                print(f"✅ Загружен проект: {self.project_id} (site={self.site_name}, domain={self.domain_name})")
                return True
        except Exception as e:
            print(f"❌ Ошибка загрузки: {e}")
            return False

    def save(self) -> bool:
        """Сохраняет данные в файл"""
        if not self.project_file:
            print("❌ Нет файла для сохранения")
            return False

        try:
            # Загружаем существующий файл
            if self.project_file.exists():
                with open(self.project_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
            else:
                file_data = {}

            # Обновляем app_data
            file_data['app_data'] = self.data
            file_data['updated_at'] = datetime.now().isoformat()
            file_data['project_id'] = self.project_id
            file_data['user_id'] = self.user_id
            file_data['site_name'] = self.site_name
            file_data['domain_name'] = self.domain_name

            # Сохраняем
            with open(self.project_file, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, ensure_ascii=False, indent=2)

            print(f"✅ Сохранен проект: {self.project_id} (site={self.site_name}, domain={self.domain_name})")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    def get_phase_data(self, phase: int):
        """Получает данные фазы"""
        return self.data.get(f'phase{phase}', {})

    def set_phase_data(self, phase: int, data):
        """Устанавливает данные фазы"""
        self.data[f'phase{phase}'] = data

    def get(self, key: str, default=None):
        """Получает значение из data"""
        return self.data.get(key, default)

    def set(self, key: str, value):
        """Устанавливает значение в data"""
        self.data[key] = value

    def is_loaded(self) -> bool:
        return self._loaded

    def get_project_info(self) -> dict:
        """Возвращает информацию о проекте"""
        return {
            'user_id': self.user_id,
            'project_id': self.project_id,
            'site_name': self.site_name,
            'domain_name': self.domain_name,
            'project_file': str(self.project_file) if self.project_file else None,
            'is_loaded': self._loaded
        }

    def reload(self) -> bool:
        """Перезагружает данные из файла"""
        self._loaded = False
        return self.load()