# config_manager.py
"""Управление конфигурациями/проектами для фаз 3 и 4"""

import os
import shutil
import json
from pathlib import Path
import streamlit as st
from domain_manager import DomainManager


class ConfigManager:
    """Управление конфигурациями блоков и инструкций - ПРИВЯЗАН К ДОМЕНУ"""

    def __init__(self, base_dir=None):
        # ✅ ОПРЕДЕЛЯЕМ БАЗОВУЮ ДИРЕКТОРИЮ В ЗАВИСИМОСТИ ОТ ДОМЕНА
        if base_dir is None:
            try:
                # Загружаем домен из файла
                user_id = st.session_state.get('user_id')

                if 'domain_manager' not in st.session_state:
                    st.session_state.domain_manager = DomainManager()

                dm = st.session_state.domain_manager

                if user_id:
                    settings = dm.load_user_settings(user_id)
                    saved_domain = settings.get('selected_domain', 'default')
                    saved_site = settings.get('selected_site', 'steelborg')

                    # Обновляем session_state
                    st.session_state.current_domain = saved_domain
                    st.session_state.selected_domain = saved_domain
                    st.session_state.current_site = saved_site
                    st.session_state.selected_site = saved_site
                    st.session_state[f'domain_system_{saved_site}'] = saved_domain

                    # Конфигурации хранятся в папке домена
                    base_dir = f"sites/{saved_site}/domains/{saved_domain}/configs"
                    print(f"✅ ConfigManager: конфигурации в {base_dir}")
                else:
                    base_dir = "project_configs"
            except Exception as e:
                print(f"⚠️ ConfigManager: ошибка загрузки домена: {e}")
                base_dir = "project_configs"

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Создаем default конфигурацию, если её нет
        self._ensure_default_config()

    def _ensure_default_config(self):
        """Создает default конфигурацию, если её нет"""
        default_blocks = self.base_dir / "default" / "blocks"
        default_instructions = self.base_dir / "default" / "ai_instructions"

        default_blocks.mkdir(parents=True, exist_ok=True)
        default_instructions.mkdir(parents=True, exist_ok=True)

        # Создаем файл метаданных конфигурации
        self._save_config_metadata("default", {
            "name": "Default",
            "description": "Стандартная конфигурация по умолчанию",
            "created_at": "system",
            "is_default": True
        })

    def _save_config_metadata(self, config_name, metadata):
        """Сохраняет метаданные конфигурации"""
        metadata_file = self.base_dir / config_name / "config.json"
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _load_config_metadata(self, config_name):
        """Загружает метаданные конфигурации"""
        metadata_file = self.base_dir / config_name / "config.json"
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"name": config_name, "description": "", "created_at": "unknown"}

    def get_all_configs(self):
        """Возвращает список всех доступных конфигураций"""
        configs = []
        for item in self.base_dir.iterdir():
            if item.is_dir() and (item / "blocks").exists():
                metadata = self._load_config_metadata(item.name)
                configs.append({
                    "name": item.name,
                    "display_name": metadata.get("name", item.name),
                    "description": metadata.get("description", ""),
                    "is_default": metadata.get("is_default", False),
                    "created_at": metadata.get("created_at", "")
                })
        # Сортируем: default первый, остальные по имени
        configs.sort(key=lambda x: (0 if x["is_default"] else 1, x["display_name"]))
        return configs

    def get_current_config(self):
        """Возвращает текущую активную конфигурацию"""
        if 'current_project_config' not in st.session_state:
            st.session_state.current_project_config = "default"
        return st.session_state.current_project_config

    def set_current_config(self, config_name):
        """Устанавливает активную конфигурацию"""
        if self.config_exists(config_name):
            st.session_state.current_project_config = config_name
            return True
        return False

    def config_exists(self, config_name):
        """Проверяет существование конфигурации"""
        return (self.base_dir / config_name / "blocks").exists()

    def duplicate_config(self, source_config, new_config_name, display_name=None):
        """Дублирует конфигурацию"""
        source_dir = self.base_dir / source_config
        target_dir = self.base_dir / new_config_name

        if target_dir.exists():
            raise ValueError(f"Конфигурация '{new_config_name}' уже существует")

        # Копируем всё содержимое
        shutil.copytree(source_dir, target_dir)

        # Обновляем метаданные
        source_metadata = self._load_config_metadata(source_config)
        new_metadata = {
            "name": display_name or new_config_name,
            "description": f"Копия конфигурации '{source_metadata.get('name', source_config)}'",
            "created_at": "now",
            "is_default": False,
            "source": source_config
        }
        self._save_config_metadata(new_config_name, new_metadata)

        return True

    def delete_config(self, config_name):
        """Удаляет конфигурацию (нельзя удалить default)"""
        if config_name == "default":
            raise ValueError("Нельзя удалить конфигурацию по умолчанию")

        config_dir = self.base_dir / config_name
        if config_dir.exists():
            shutil.rmtree(config_dir)
            return True
        return False

    def create_config(self, config_name, display_name=None, description=""):
        """Создает новую пустую конфигурацию"""
        if self.config_exists(config_name):
            raise ValueError(f"Конфигурация '{config_name}' уже существует")

        config_dir = self.base_dir / config_name
        config_dir.mkdir(parents=True)

        # Создаем пустые директории
        (config_dir / "blocks").mkdir()
        (config_dir / "ai_instructions").mkdir()

        # Сохраняем метаданные
        metadata = {
            "name": display_name or config_name,
            "description": description,
            "created_at": "now",
            "is_default": False
        }
        self._save_config_metadata(config_name, metadata)

        return True

    def get_config_path(self, config_name, subpath=""):
        """Возвращает путь к файлам конфигурации"""
        return self.base_dir / config_name / subpath

    def rename_config(self, old_name, new_name, new_display_name=None):
        """Переименовывает конфигурацию"""
        if old_name == "default":
            raise ValueError("Нельзя переименовать конфигурацию по умолчанию")

        old_dir = self.base_dir / old_name
        new_dir = self.base_dir / new_name

        if new_dir.exists():
            raise ValueError(f"Конфигурация '{new_name}' уже существует")

        old_dir.rename(new_dir)

        # Обновляем метаданные
        metadata = self._load_config_metadata(new_name)
        metadata["name"] = new_display_name or new_name
        self._save_config_metadata(new_name, metadata)

        return True

    def get_configs_dir(self) -> Path:
        """Возвращает корневую директорию конфигураций"""
        return self.base_dir


# Глобальный экземпляр для доступа из других модулей
_config_manager = None


def get_config_manager():
    """Возвращает глобальный экземпляр ConfigManager с загрузкой домена"""
    global _config_manager

    # ✅ ПРОВЕРЯЕМ, НУЖНО ЛИ ПЕРЕСОЗДАТЬ ИЗ-ЗА СМЕНЫ ДОМЕНА
    try:
        user_id = st.session_state.get('user_id')
        if user_id and 'domain_manager' in st.session_state:
            dm = st.session_state.domain_manager
            current_domain = dm.get_current_domain()
            current_site = dm.site_name

            expected_base = f"sites/{current_site}/domains/{current_domain}/configs"

            if _config_manager is None or str(_config_manager.base_dir) != expected_base:
                _config_manager = ConfigManager(expected_base)
                print(f"✅ ConfigManager создан для домена {current_site}/{current_domain}")
    except Exception as e:
        print(f"⚠️ ConfigManager: ошибка инициализации: {e}")
        if _config_manager is None:
            _config_manager = ConfigManager("project_configs")

    return _config_manager