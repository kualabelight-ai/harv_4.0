# background_worker.py
import threading
import queue
import time
from datetime import datetime
from typing import Dict
import warnings
import streamlit as st
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
import logging

# Подавляем конкретное сообщение от Streamlit
logging.getLogger("streamlit.scriptrunner").setLevel(logging.ERROR)
class BackgroundWorker:
    """Фоновый воркер для выполнения проектов"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.queue = queue.Queue()
        self.status = {}
        self.results = {}
        self.active = None
        self._running = False
        self._thread = None
        self._start_worker()

    def _start_worker(self):
        """Запускает фоновый поток"""
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        while self._running:
            try:
                task = self.queue.get(timeout=1)
                project_id = task['project_id']
                user_id = task['user_id']

                self.active = project_id
                self.status[project_id] = 'running'

                # Выполняем
                result = self._execute_project(project_id, user_id)
                self.results[project_id] = result
                self.status[project_id] = 'completed' if result['success'] else 'failed'

                self.active = None
                self.queue.task_done()

            except queue.Empty:
                continue

    # background_worker.py - исправленная версия с передачей по аргументам

    def _execute_project(self, project_id: str, user_id: int) -> Dict:
        """Выполняет проект (фазы 3-5)"""
        try:
            from main_app import AppState
            from phases.phase3 import run_mass_generation_auto
            from phases.phase4 import auto_generate_all_prompts
            from phases.phase5 import auto_generate_all_texts

            # Загружаем проект
            app_state = AppState()
            app_state.load_project(project_id)

            # Устанавливаем user_id
            if hasattr(app_state, 'user_id'):
                app_state.user_id = user_id

            print(f"✅ Background worker: проект {project_id} загружен")
            print(f"   Категория из фазы 2: {app_state.get_phase_data(2).get('category') if app_state.get_phase_data(2) else 'None'}")

            # Фаза 3 - ПЕРЕДАЁМ app_state
            result3 = run_mass_generation_auto(app_state=app_state)
            print(f"   Фаза 3 результат: success={result3.get('success')}, count={result3.get('count')}")

            if not result3.get('success'):
                return {
                    'success': False,
                    'phase': 3,
                    'error': result3.get('message'),
                    'details': result3
                }

            # Фаза 4
            result4 = auto_generate_all_prompts(app_state=app_state)
            print(f"   Фаза 4 результат: success={result4.get('success')}")

            if not result4.get('success'):
                return {
                    'success': False,
                    'phase': 4,
                    'error': result4.get('message'),
                    'details': result4
                }

            # Фаза 5
            result5 = auto_generate_all_texts(app_state=app_state)
            print(f"   Фаза 5 результат: success={result5.get('success')}")

            return {
                'success': True,
                'phase3': result3,
                'phase4': result4,
                'phase5': result5,
                'completed_at': datetime.now().isoformat()
            }

        except Exception as e:
            import traceback
            print(f"❌ Ошибка в background worker: {e}")
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def add_project(self, project_id: str, user_id: int):
        self.queue.put({
            'project_id': project_id,
            'user_id': user_id,
            'added_at': datetime.now().isoformat()
        })
        self.status[project_id] = 'queued'

    def get_status(self, project_id: str) -> Dict:
        return {
            'status': self.status.get(project_id, 'unknown'),
            'result': self.results.get(project_id),
            'active': self.active == project_id
        }

    def get_queue_info(self) -> Dict:
        return {
            'active': self.active,
            'queue_size': self.queue.qsize(),
            'projects': self.status.copy()
        }

# Синглтон
background_worker = BackgroundWorker()