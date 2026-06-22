# project_manager.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import uuid
import shutil
import streamlit as st
import warnings
warnings.filterwarnings("ignore", message="missing ScriptRunContext")
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
import shutil
# project_manager.py - ЗАМЕНИТЬ ВЕСЬ КЛАСС

class ProjectManager:
    """Управление проектами пользователя в структуре сайт→домен→пользователь"""

    def __init__(self, user_id: int, site_name: str = None, domain_name: str = None):
        self.user_id = user_id

        # ✅ ЕСЛИ ДОМЕН НЕ ПЕРЕДАН - ЗАГРУЖАЕМ ИЗ ФАЙЛА
        if site_name is None or domain_name is None:
            try:
                import streamlit as st
                from domain_manager import DomainManager

                if 'domain_manager' not in st.session_state:
                    st.session_state.domain_manager = DomainManager()

                dm = st.session_state.domain_manager
                settings = dm.load_user_settings(user_id)
                saved_domain = settings.get('selected_domain', 'default')
                saved_site = settings.get('selected_site', 'steelborg')

                site_name = site_name or saved_site
                domain_name = domain_name or saved_domain

                print(f"✅ ProjectManager загружен домен из файла: {saved_domain}")
            except Exception as e:
                print(f"⚠️ ProjectManager: ошибка загрузки домена: {e}")
                site_name = site_name or 'steelborg'
                domain_name = domain_name or 'default'

        self.site_name = site_name
        self.domain_name = domain_name

        # Создаём директорию ТОЛЬКО в указанном домене
        self.projects_dir = Path(f"sites/{self.site_name}/domains/{self.domain_name}/projects/{user_id}")
        self.projects_dir.mkdir(parents=True, exist_ok=True)

        print(f"📁 ProjectManager: user={user_id}, site={self.site_name}, domain={self.domain_name}")
        print(f"   Путь: {self.projects_dir}")

    # ... остальной код без изменений ...

    # ❌ УДАЛИТЬ МЕТОД _find_project_file - ОН НЕ НУЖЕН!
    # Проект всегда ищется ТОЛЬКО в self.projects_dir

    def get_project_path(self, project_id: str) -> Path:
        """Путь к проекту - ТОЛЬКО В ТЕКУЩЕМ ДОМЕНЕ"""
        return self.projects_dir / f"{project_id}.json"

    def delete_project(self, project_id: str) -> bool:
        """Удаляет проект и все связанные с ним файлы"""
        import shutil

        project_file = self.get_project_path(project_id)

        if not project_file.exists():
            print(f"❌ Проект {project_id} не найден в домене {self.domain_name}")
            return False

        try:
            # 1. Удаляем JSON файл
            project_file.unlink()
            print(f"🗑️ Удален JSON: {project_file}")

            # 2. Удаляем backup
            backup_file = project_file.with_suffix('.json.backup')
            if backup_file.exists():
                backup_file.unlink()
                print(f"   Удален backup: {backup_file}")

            # 3. Удаляем папку AI инструкций
            ai_dir = self.projects_dir / f"{project_id}_ai_instructions"
            if ai_dir.exists():
                shutil.rmtree(ai_dir)
                print(f"   Удалена папка AI инструкций: {ai_dir}")

            # 4. Удаляем папку с бэкапами
            backup_dir = self.projects_dir / f"{project_id}_backup"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
                print(f"   Удалена папка бэкапов: {backup_dir}")

            # 5. Удаляем из очереди (если есть)
            try:
                from user_queue_manager import get_user_queue
                queue = get_user_queue()
                if queue and project_id in queue.projects:
                    queue.remove_project(project_id)
                    print(f"   Удален из очереди: {project_id}")
            except:
                pass

            return True

        except Exception as e:
            print(f"❌ Ошибка удаления проекта {project_id}: {e}")
            return False

    def get_all_projects(self) -> List[Dict]:
        """Возвращает список всех проектов - ТОЛЬКО ИЗ ТЕКУЩЕГО ДОМЕНА"""
        print(f"📂 get_all_projects: user={self.user_id}, site={self.site_name}, domain={self.domain_name}")
        projects = []
        seen_ids = set()

        if not self.projects_dir.exists():
            print(f"⚠️ Директория не существует: {self.projects_dir}")
            return projects

        all_files = list(self.projects_dir.glob("*.json"))
        print(f"🔍 Найдено {len(all_files)} файлов в {self.projects_dir}")

        for file_path in all_files:
            # ===== ИСКЛЮЧАЕМ СЛУЖЕБНЫЕ ФАЙЛЫ =====
            if file_path.name in ["queue_state.json", "user_settings.json", "selections.json"]:
                print(f"   ⏭️ Пропускаем служебный файл: {file_path.name}")
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    project_id = data.get('project_id', file_path.stem)

                    # ✅ ПРОВЕРЯЕМ ДОМЕН В ФАЙЛЕ
                    file_domain = data.get('domain_name')
                    if file_domain and file_domain != self.domain_name:
                        print(f"⚠️ Пропускаем проект {project_id}: домен в файле {file_domain} != {self.domain_name}")
                        continue

                    if project_id == 'None' or not project_id:
                        print(f"⚠️ Пропускаем файл с None: {file_path}")
                        continue

                    if project_id in seen_ids:
                        print(f"⚠️ Дубликат проекта: {project_id}, пропускаем")
                        continue
                    seen_ids.add(project_id)

                    projects.append({
                        'project_id': project_id,
                        'project_name': data.get('project_name', file_path.stem),
                        'category': data.get('category', ''),
                        'current_phase': data.get('current_phase', 1),
                        'created_at': data.get('created_at', ''),
                        'updated_at': data.get('updated_at', ''),
                        'status': data.get('status', 'unknown'),
                        'domain_name': data.get('domain_name', self.domain_name),
                        'site_name': data.get('site_name', self.site_name)
                    })
                    print(f"   ✅ Добавлен проект: {project_id} - {data.get('project_name', '')}")
            except Exception as e:
                print(f"❌ Ошибка чтения {file_path}: {e}")

        print(f"📊 Всего проектов в домене {self.domain_name}: {len(projects)}")
        return projects

    def load_project(self, project_id: str) -> Optional[Dict]:
        """Загрузка проекта - ТОЛЬКО ИЗ ТЕКУЩЕГО ДОМЕНА"""
        main_file = self.get_project_path(project_id)

        if not main_file.exists():
            print(f"❌ Проект {project_id} не найден в домене {self.domain_name}")
            # ❌ НЕ ИЩЕМ В ДРУГИХ ДОМЕНАХ!
            return None

        try:
            with open(main_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # ✅ ПРОВЕРЯЕМ, ЧТО ДОМЕН В ФАЙЛЕ СОВПАДАЕТ
            file_domain = data.get('domain_name')
            if file_domain and file_domain != self.domain_name:
                print(f"❌ Проект {project_id} принадлежит домену {file_domain}, а не {self.domain_name}")
                return None

            print(f"📂 Загружен проект: {data.get('project_name')} из домена {self.domain_name}")
            return data

        except json.JSONDecodeError:
            # Пробуем восстановить из бэкапа
            backup_file = main_file.with_suffix('.json.backup')
            if backup_file.exists():
                import shutil
                shutil.copy(backup_file, main_file)
                return self.load_project(project_id)
            return None

    def save_project(self, project_data: Dict) -> bool:
        """Сохраняет проект - СТРОГО В ТЕКУЩИЙ ДОМЕН"""
        project_id = project_data.get('project_id')
        if not project_id:
            import uuid
            project_id = str(uuid.uuid4())
            project_data['project_id'] = project_id

        # ✅ ЖЕСТКО ЗАКРЕПЛЯЕМ ДОМЕН
        project_data['site_name'] = self.site_name
        project_data['domain_name'] = self.domain_name
        project_data['user_id'] = self.user_id
        project_data['updated_at'] = datetime.now().isoformat()

        if 'created_at' not in project_data:
            project_data['created_at'] = datetime.now().isoformat()

        # ✅ Синхронизируем категорию
        if 'app_data' in project_data:
            app_data = project_data['app_data']
            if app_data.get('category'):
                project_data['category'] = app_data['category']
            elif app_data.get('phase1', {}).get('category'):
                project_data['category'] = app_data['phase1']['category']

        file_path = self.get_project_path(project_id)

        # Создаём бэкап
        if file_path.exists():
            backup_path = file_path.with_suffix('.json.backup')
            import shutil
            shutil.copy(file_path, backup_path)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)
            print(f"💾 СОХРАНЕН ПРОЕКТ: {project_id} в домене {self.domain_name}")
            print(f"   site_name: {self.site_name}, domain_name: {self.domain_name}")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    # ❌ УДАЛИТЬ МЕТОДЫ:
    # - _find_project_file (не нужен)
    # - get_projects_from_other_domains (не нужен)
    # - migrate_project_from_other_domain (не нужен)
