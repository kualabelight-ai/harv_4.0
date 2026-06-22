# project_status_manager.py
"""
Единая система управления статусами проектов
"""
import streamlit as st
import json
from pathlib import Path
from typing import Dict, Optional


class ProjectStatusManager:
    """Централизованное управление статусами проектов"""

    @staticmethod
    def get_unified_status(project_id: str, user_id: int, site: str, domain: str) -> Dict:
        """Получает единый статус проекта"""
        from user_queue_manager import get_user_queue

        # ✅ ЗАГРУЖАЕМ ДОМЕН ИЗ ФАЙЛА
        try:
            from domain_manager import DomainManager
            if 'domain_manager' not in st.session_state:
                st.session_state.domain_manager = DomainManager()

            dm = st.session_state.domain_manager
            settings = dm.load_user_settings(user_id)
            saved_domain = settings.get('selected_domain', 'default')
            saved_site = settings.get('selected_site', 'steelborg')

            # Используем загруженный домен
            site = saved_site
            domain = saved_domain

            print(f"✅ ProjectStatusManager загружен домен из файла: {saved_domain}")
        except Exception as e:
            print(f"⚠️ ProjectStatusManager: ошибка загрузки домена: {e}")

        queue = get_user_queue()

        # Сначала проверяем в очереди
        if queue and project_id in queue.projects:
            task = queue.projects[project_id]
            return {
                'status': task.status.value,
                'current_phase': task.current_phase,
                'progress': task.progress,
                'message': task.message,
                'error': task.error,
                'from_queue': True
            }

        # ✅ ЕСЛИ НЕТ В ОЧЕРЕДИ - ПРОВЕРЯЕМ ФАЙЛ
        file_status = ProjectStatusManager._get_status_from_file(project_id, user_id, site, domain)
        if file_status:
            return file_status

        return {
            'status': 'unknown',
            'current_phase': 1,
            'progress': 0,
            'message': '',
            'error': '',
            'from_queue': False
        }

    @staticmethod
    def _get_status_from_file(project_id: str, user_id: int, site: str, domain: str) -> Optional[Dict]:
        """Читает статус из файла"""
        # ✅ ПРОВЕРЯЕМ ТОЛЬКО ПУТЬ С ПРАВИЛЬНЫМ ДОМЕНОМ
        file_path = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

        if not file_path.exists():
            # Пробуем старый путь для обратной совместимости
            old_path = Path(f"projects/{user_id}/{project_id}.json")
            if old_path.exists():
                file_path = old_path
            else:
                return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                app_data = data.get('app_data', {})

                # Проверяем наличие данных
                has_phase1 = bool(app_data.get('phase1', {}).get('characteristics'))
                has_phase3 = bool(app_data.get('phase3', {}).get('blocks'))
                has_phase4 = bool(app_data.get('phase4', {}).get('prompts'))

                # Проверяем реальные результаты PHASE5
                phase5_results = app_data.get('phase5', {}).get('results', {})
                has_phase5 = bool(phase5_results)

                # Проверяем phase5_completed
                phase5_completed = app_data.get('phase5_completed', False)

                if has_phase5 or phase5_completed:
                    return {
                        'status': 'completed',
                        'current_phase': 5,
                        'progress': 100,
                        'message': f'✅ Сгенерировано {len(phase5_results)} текстов' if has_phase5 else '✅ Завершено',
                        'error': '',
                        'from_queue': False,
                        'has_phase5': has_phase5,
                        'has_phase6': False,
                        'has_phase7': False
                    }

                if has_phase4:
                    return {
                        'status': 'idle',
                        'current_phase': 4,
                        'progress': 50,
                        'message': 'Готов к генерации текстов',
                        'error': '',
                        'from_queue': False,
                        'has_phase5': False,
                        'has_phase6': False,
                        'has_phase7': False
                    }

                if has_phase3 and has_phase1:
                    return {
                        'status': 'idle',
                        'current_phase': 3,
                        'progress': 25,
                        'message': 'Готов к генерации промптов',
                        'error': '',
                        'from_queue': False,
                        'has_phase5': False,
                        'has_phase6': False,
                        'has_phase7': False
                    }

                if has_phase1:
                    return {
                        'status': 'idle',
                        'current_phase': 1,
                        'progress': 0,
                        'message': 'Готов к запуску',
                        'error': '',
                        'from_queue': False,
                        'has_phase5': False,
                        'has_phase6': False,
                        'has_phase7': False
                    }

                return {
                    'status': 'idle',
                    'current_phase': 1,
                    'progress': 0,
                    'message': 'Новый проект',
                    'error': '',
                    'from_queue': False,
                    'has_phase5': False,
                    'has_phase6': False,
                    'has_phase7': False
                }

        except Exception as e:
            print(f"Ошибка чтения статуса из файла: {e}")
            return None

    @staticmethod
    def has_results(project_id: str, user_id: int, site: str, domain: str) -> bool:
        """Проверяет наличие результатов"""
        status = ProjectStatusManager.get_unified_status(project_id, user_id, site, domain)
        return (status.get('status') == 'completed' or
                status.get('has_phase5') or
                status.get('has_phase6') or
                status.get('has_phase7') or
                status.get('current_phase') >= 5)

    @staticmethod
    def clear_status(project_id: str, user_id: int = None, site: str = None, domain: str = None):
        """Принудительно сбрасывает статус проекта в файле"""
        from pathlib import Path
        import json
        import streamlit as st

        # Если параметры не переданы - берем из session_state (для UI)
        if user_id is None:
            user_id = st.session_state.get('user_id')
        if site is None:
            site = st.session_state.get('current_site', 'steelborg')
        if domain is None:
            domain = st.session_state.get('current_domain', 'default')

        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

        # Если файл не найден - пробуем старый путь
        if not project_file.exists():
            old_path = Path(f"projects/{user_id}/{project_id}.json")
            if old_path.exists():
                project_file = old_path
            else:
                print(f"❌ Файл проекта {project_id} не найден")
                return False

        if project_file.exists():
            try:
                with open(project_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Сбрасываем статус
                data['status'] = 'idle'
                data['current_phase'] = 3
                data['progress'] = 0
                data['message'] = 'Готов к запуску'
                data['error'] = None

                with open(project_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                print(f"✅ Статус проекта {project_id} сброшен на 'idle'")
                return True
            except Exception as e:
                print(f"❌ Ошибка сброса статуса: {e}")

        return False

    @staticmethod
    def can_run(project_id: str, user_id: int, site: str, domain: str) -> bool:
        """Проверяет возможность запуска"""
        status = ProjectStatusManager.get_unified_status(project_id, user_id, site, domain)

        if status.get('status') in ['running', 'queued']:
            return False

        file_path = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    phase1 = data.get('app_data', {}).get('phase1', {})
                    return bool(phase1.get('characteristics'))
            except Exception:
                return False
        return False