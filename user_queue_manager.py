import json
import queue
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
import streamlit as st
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
from file_data_manager import FileDataManager
from domain_manager import DomainManager
from context import ProjectContext
class ProjectStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class ProjectTask:
    project_id: str
    user_id: int
    project_name: str
    category: str
    status: ProjectStatus = ProjectStatus.QUEUED
    current_phase: int = 0
    message: str = ""
    error: str = None
    started_at: str = None
    completed_at: str = None
    progress: float = 0.0
    site_name: str = "steelborg"
    domain_name: str = "default"

# В начале файла user_queue_manager.py, после импортов:

from domain_manager import DomainManager  # ← ЭТО УЖЕ ДОБАВИЛИ


# ДОБАВЬТЕ ЭТУ ФУНКЦИЮ СЮДА:


class UserQueueManager:
    def __init__(self, user_id: int):
        self.user_id = user_id

        # ✅ ЗАГРУЖАЕМ ДОМЕН ИЗ ФАЙЛА
        try:
            import streamlit as st
            from domain_manager import DomainManager

            if 'domain_manager' not in st.session_state:
                st.session_state.domain_manager = DomainManager()

            dm = st.session_state.domain_manager
            settings = dm.load_user_settings(user_id)
            saved_domain = settings.get('selected_domain', 'default')
            saved_site = settings.get('selected_site', 'steelborg')

            self.site_name = saved_site
            self.domain_name = saved_domain

            # ✅ НЕ ПЕРЕЗАПИСЫВАЕМ session_state (это делает DomainManager)
            # Просто используем значения для очереди
            print(f"✅ Очередь загрузила домен из файла: {saved_site}/{saved_domain}")
        except Exception as e:
            # Fallback на дефолтные значения
            self.site_name = "steelborg"
            self.domain_name = "default"
            print(f"⚠️ Ошибка загрузки домена для очереди: {e}, используем default")

        self.projects: Dict[str, ProjectTask] = {}
        self._queue = queue.Queue()
        self._running = False
        self._thread = None
        self._max_parallel = 1

        print(f"✅ Очередь инициализирована: user={user_id}, site={self.site_name}, domain={self.domain_name}")

        self.queue_dir = Path(f"projects/user_{user_id}")
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.queue_file = self.queue_dir / "queue_state.json"

        self._load_queue()
        print(f"✅ Очередь инициализирована для пользователя {self.user_id} (воркер НЕ запущен)")
    def start_worker(self):
        """Запускает воркер в отдельном потоке - ПО КНОПКЕ"""
        if self._running:
            print("⚠️ Воркер уже запущен")
            return False

        if self._thread and self._thread.is_alive():
            print("⚠️ Поток воркера уже жив")
            return False

        print("🚀 ЗАПУСК ВОРКЕРА ПО КНОПКЕ")

        # ✅ ОЧИЩАЕМ СТАРЫЕ ЗАВЕРШЕННЫЕ ПРОЕКТЫ ИЗ ОЧЕРЕДИ!
        self._clean_completed_from_queue()

        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        print("✅ Воркер запущен")
        return True

    def _clean_completed_from_queue(self):
        """Очищает завершенные проекты из очереди перед запуском воркера"""
        cleaned = 0
        for pid, task in list(self.projects.items()):
            if task.status == ProjectStatus.COMPLETED:
                # Проверяем файл - есть ли реальные результаты
                project_file = Path(f"sites/{task.site_name}/domains/{task.domain_name}/projects/{task.user_id}/{pid}.json")
                if project_file.exists():
                    try:
                        with open(project_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            has_results = bool(data.get('app_data', {}).get('phase5', {}).get('results'))
                            if has_results:
                                # Есть реальные результаты - оставляем
                                continue
                    except:
                        pass

                # Нет результатов - удаляем из очереди
                print(f"🧹 Очищаем проект {pid} ({task.project_name}) из очереди - нет результатов")
                del self.projects[pid]
                cleaned += 1

        self._save_queue()
        if cleaned > 0:
            print(f"✅ Очищено {cleaned} проектов без результатов")

    def stop_worker(self):
        """Останавливает воркер"""
        if not self._running:
            print("⚠️ Воркер уже остановлен")
            return False

        print("🛑 ОСТАНОВКА ВОРКЕРА")
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        print("✅ Воркер остановлен")
        return True

    def is_worker_running(self):
        """Проверяет, запущен ли воркер"""
        return self._running and self._thread and self._thread.is_alive()
    def _load_queue(self):
        if not self.queue_file.exists():
            return

        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)

            for item in queue_data:
                try:
                    project_id = item.get('project_id')
                    if not project_id:
                        continue

                    task = ProjectTask(
                        project_id=project_id,
                        user_id=item['user_id'],
                        project_name=item['project_name'],
                        category=item['category'],
                        status=ProjectStatus(item.get('status', 'queued')),
                        current_phase=item.get('current_phase', 0),
                        message=item.get('message', ''),
                        progress=item.get('progress', 0.0),
                        started_at=item.get('started_at'),
                        completed_at=item.get('completed_at'),
                        error=item.get('error'),
                        site_name=item.get('site_name', 'steelborg'),
                        domain_name=item.get('domain_name', 'default')
                    )

                    self.projects[project_id] = task

                    if task.status == ProjectStatus.QUEUED:
                        self._queue.put({
                            'project_id': project_id,
                            'user_id': task.user_id,
                            'site_name': task.site_name,      # ← ДОБАВИТЬ
                            'domain_name': task.domain_name   # ← ДОБАВИТЬ
                        })
                    elif task.status == ProjectStatus.RUNNING:
                        task.status = ProjectStatus.QUEUED
                        task.message = "Восстановлен после перезагрузки"
                        self._queue.put({
                            'project_id': project_id,
                            'user_id': task.user_id,
                            'site_name': task.site_name,      # ← ДОБАВИТЬ
                            'domain_name': task.domain_name   # ← ДОБАВИТЬ
                        })

                except Exception as e:
                    print(f"Ошибка загрузки проекта: {e}")
        except Exception as e:
            print(f"Ошибка загрузки очереди: {e}")

    def _save_queue(self):
        try:
            queue_data = []
            for task in self.projects.values():
                queue_data.append({
                    'project_id': task.project_id,
                    'user_id': task.user_id,
                    'project_name': task.project_name,
                    'category': task.category,
                    'status': task.status.value,
                    'current_phase': task.current_phase,
                    'message': task.message,
                    'progress': task.progress,
                    'started_at': task.started_at,
                    'completed_at': task.completed_at,
                    'error': task.error,
                    'site_name': task.site_name,
                    'domain_name': task.domain_name
                })

            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения очереди: {e}")



    def _worker(self):
        # Подавляем предупреждения Streamlit в этом потоке
        import warnings
        warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")
        warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")

        import logging
        logging.getLogger("streamlit").setLevel(logging.ERROR)

        # Остальной код worker...

        while self._running:
            try:
                active_count = len([p for p in self.projects.values() if p.status == ProjectStatus.RUNNING])

                if active_count < self._max_parallel:
                    try:
                        task_item = self._queue.get(timeout=1)
                        project_id = task_item.get('project_id')
                        user_id = task_item.get('user_id')
                        site_name = task_item.get('site_name', 'steelborg')      # ← ДОБАВИТЬ
                        domain_name = task_item.get('domain_name', 'default')    # ← ДОБАВИТЬ

                        if project_id not in self.projects:
                            self._queue.task_done()
                            continue

                        if user_id != self.user_id:
                            print(f"⚠️ Несоответствие user_id: {user_id} vs {self.user_id}")
                            self._queue.task_done()
                            continue

                        self._run_project(project_id, site_name, domain_name)  # ← ПЕРЕДАЕМ КОНТЕКСТ
                        self._queue.task_done()
                        self._save_queue()

                    except queue.Empty:
                        time.sleep(0.5)
                else:
                    time.sleep(0.5)

            except Exception as e:
                print(f"Worker error for user {self.user_id}: {e}")
                time.sleep(1)

        print(f"🛑 Worker {self.user_id}: остановлен")
    def get_all_projects(self) -> Dict:
        """Возвращает все проекты (включая завершенные)"""
        return self.projects.copy()
    # user_queue_manager.py - ЗАМЕНИТЬ МЕТОД _run_project
    def _verify_file_has_phase4(self, ctx):
        from pathlib import Path
        import json

        project_file = Path(f"sites/{ctx.site_name}/domains/{ctx.domain_name}/projects/{ctx.user_id}/{ctx.project_id}.json")

        if not project_file.exists():
            print(f"❌ Файл не существует: {project_file}")
            return False

        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            prompts = data.get('app_data', {}).get('phase4', {}).get('prompts', [])
            print(f"📊 В файле phase4.prompts: {len(prompts)}")
            return len(prompts) > 0
        except Exception as e:
            print(f"❌ Ошибка проверки: {e}")
            return False
    # user_queue_manager.py - ИЗМЕНЕННЫЙ _run_project()
    def _force_save_phase4_to_file(self, ctx, prompts):
        """ПРИНУДИТЕЛЬНОЕ СОХРАНЕНИЕ PHASE4 В ФАЙЛ"""
        from pathlib import Path
        import json
        from datetime import datetime

        try:
            user_id = ctx.user_id
            project_id = ctx.project_id
            site_name = ctx.site_name
            domain_name = ctx.domain_name

            project_file = Path(f"sites/{site_name}/domains/{domain_name}/projects/{user_id}/{project_id}.json")

            if not project_file.exists():
                print(f"❌ Файл не существует: {project_file}")
                return False

            # Читаем файл
            with open(project_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Сохраняем phase4
            if 'app_data' not in data:
                data['app_data'] = {}

            data['app_data']['phase4'] = {
                'prompts': prompts,
                'generated_count': len(prompts),
                'generated_at': datetime.now().isoformat()
            }
            data['app_data']['phase4_generated_prompts'] = prompts
            data['updated_at'] = datetime.now().isoformat()

            # Записываем
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"✅ ПРИНУДИТЕЛЬНО сохранено phase4 в файл: {len(prompts)} промптов")

            # Обновляем контекст
            ctx.set_phase_data(4, {
                'prompts': prompts,
                'generated_count': len(prompts),
                'generated_at': datetime.now().isoformat()
            })
            ctx.save()

            return True
        except Exception as e:
            print(f"❌ Ошибка принудительного сохранения phase4: {e}")
            import traceback
            traceback.print_exc()
            return False
    def _run_project(self, project_id: str, site_name: str = None, domain_name: str = None):
        """Запускает проект - С ПРИНУДИТЕЛЬНЫМ СОХРАНЕНИЕМ"""

        print("\n" + "="*80)
        print(f"🔥🔥🔥 _run_project STARTED: {project_id} 🔥🔥🔥")
        print("="*80)

        task = self.projects.get(project_id)
        if not task:
            print("❌ task not found!")
            return

        if site_name is None:
            site_name = task.site_name
        if domain_name is None:
            domain_name = task.domain_name

        print(f"📌 task.user_id: {task.user_id}")
        print(f"📌 task.project_name: {task.project_name}")
        print(f"📌 site_name: {site_name}")
        print(f"📌 domain_name: {domain_name}")

        # ✅ СОЗДАЕМ КОНТЕКСТ
        from context import ProjectContext
        ctx = ProjectContext(
            user_id=task.user_id,
            project_id=project_id,
            site_name=site_name,
            domain_name=domain_name
        )

        print("📂 Загрузка данных...")
        if not ctx.load():
            print("❌ ctx.load() FAILED!")
            task.status = ProjectStatus.FAILED
            task.error = "Не удалось загрузить проект"
            self._save_queue()
            return
        print("✅ ctx.load() SUCCESS")

        try:
            task.status = ProjectStatus.RUNNING
            task.started_at = datetime.now().isoformat()
            task.message = "Выполнение..."
            self._save_queue()
            print("✅ Статус установлен: RUNNING")

            # ========== ФАЗА 3 ==========
            print("\n" + "-"*60)
            print("🔍 ПРОВЕРКА ФАЗЫ 3")
            print("-"*60)

            phase3_data = ctx.get_phase_data(3)
            has_blocks = phase3_data and phase3_data.get('blocks') and len(phase3_data.get('blocks', {})) > 0
            print(f"   phase3_data: {bool(phase3_data)}")
            print(f"   has_blocks: {has_blocks}")

            if not has_blocks:
                print("🚀 ЗАПУСК ФАЗЫ 3...")
                task.current_phase = 3
                task.message = "Фаза 3: создание AI-инструкций..."
                task.progress = 25
                self._save_queue()

                from phases.phase3 import run_mass_generation_auto
                result = run_mass_generation_auto(app_state=None, context=ctx)

                print(f"   RESULT: {result}")
                print(f"   success: {result.get('success') if result else 'None'}")

                if result and result.get('success'):
                    ctx.set_phase_data(3, result.get('phase3_data', {}))
                    ctx.save()
                    print("✅ Фаза 3 выполнена")
                else:
                    error_msg = result.get('error', 'неизвестная ошибка') if result else 'result is None'
                    print(f"❌ ОШИБКА ФАЗЫ 3: {error_msg}")
                    raise Exception(f"Ошибка фазы 3: {error_msg}")
            else:
                print("⏭️ Фаза 3 пропущена (уже есть блоки)")

            # ========== ФАЗА 4 ==========
            print("\n" + "-"*60)
            print("🔍 ПРОВЕРКА ФАЗЫ 4")
            print("-"*60)

            phase4_data = ctx.get_phase_data(4)
            has_prompts = phase4_data and phase4_data.get('prompts') and len(phase4_data.get('prompts', [])) > 0
            print(f"   phase4_data: {bool(phase4_data)}")
            print(f"   has_prompts: {has_prompts}")
            print(f"   prompts count: {len(phase4_data.get('prompts', [])) if phase4_data else 0}")

            generated_prompts = []

            if not has_prompts:
                print("🚀 ЗАПУСК ФАЗЫ 4...")
                task.current_phase = 4
                task.message = "Фаза 4: генерация промптов..."
                task.progress = 50
                self._save_queue()

                from phases.phase4 import auto_generate_all_prompts
                print(f"   Вызов auto_generate_all_prompts(app_state=None, context=ctx)")
                result = auto_generate_all_prompts(app_state=None, context=ctx)

                print(f"   RESULT: {result}")
                print(f"   success: {result.get('success') if result else 'None'}")
                print(f"   count: {result.get('count') if result else 0}")

                if result and result.get('success'):
                    # ✅ ПОЛУЧАЕМ ПРОМПТЫ ИЗ РЕЗУЛЬТАТА
                    generated_prompts = result.get('prompts', [])

                    # ✅ ПРИНУДИТЕЛЬНО СОХРАНЯЕМ В ФАЙЛ
                    self._force_save_phase4_to_file(ctx, generated_prompts)

                    # ✅ ОБНОВЛЯЕМ КОНТЕКСТ
                    ctx.set_phase_data(4, {
                        'prompts': generated_prompts,
                        'generated_count': len(generated_prompts),
                        'generated_at': datetime.now().isoformat()
                    })
                    ctx.save()

                    print(f"✅ Фаза 4 выполнена: {len(generated_prompts)} промптов")
                else:
                    error_msg = result.get('error', 'неизвестная ошибка') if result else 'result is None'
                    print(f"❌ ОШИБКА ФАЗЫ 4: {error_msg}")
                    raise Exception(f"Ошибка фазы 4: {error_msg}")
            else:
                print("⏭️ Фаза 4 пропущена (уже есть промпты)")
                generated_prompts = phase4_data.get('prompts', [])

            # ========== ПРОВЕРКА ЧТО ПРОМПТЫ СОХРАНИЛИСЬ ==========
            print("\n" + "-"*60)
            print("🔍 ПРОВЕРКА СОХРАНЕНИЯ PHASE4")
            print("-"*60)

            # Проверяем файл
            project_file = Path(f"sites/{site_name}/domains/{domain_name}/projects/{task.user_id}/{project_id}.json")
            if project_file.exists():
                with open(project_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    saved_prompts = file_data.get('app_data', {}).get('phase4', {}).get('prompts', [])
                    print(f"   В файле: {len(saved_prompts)} промптов")

                    if len(saved_prompts) == 0 and len(generated_prompts) > 0:
                        print("⚠️ ПРОМПТЫ НЕ СОХРАНИЛИСЬ! ПРИНУДИТЕЛЬНО ПЕРЕЗАПИСЫВАЕМ...")
                        self._force_save_phase4_to_file(ctx, generated_prompts)

            # ========== ФАЗА 5 ==========
            print("\n" + "-"*60)
            print("🔍 ПРОВЕРКА ФАЗЫ 5")
            print("-"*60)

            phase5_data = ctx.get_phase_data(5)
            has_results = phase5_data and phase5_data.get('results') and len(phase5_data.get('results', {})) > 0
            print(f"   phase5_data: {bool(phase5_data)}")
            print(f"   has_results: {has_results}")

            if not has_results:
                print("🚀 ЗАПУСК ФАЗЫ 5...")
                task.current_phase = 5
                task.message = "Фаза 5: генерация текстов..."
                task.progress = 75
                self._save_queue()

                from phases.phase5 import auto_generate_all_texts
                print(f"   Вызов auto_generate_all_texts(app_state=None, context=ctx)")
                result = auto_generate_all_texts(app_state=None, context=ctx)

                print(f"   RESULT: {result}")
                print(f"   success: {result.get('success') if result else 'None'}")
                print(f"   count: {result.get('count') if result else 0}")

                if result and result.get('success'):
                    ctx.set_phase_data(5, result.get('phase5_data', {}))
                    ctx.save()
                    print(f"✅ Фаза 5 выполнена: {result.get('count', 0)} текстов")
                else:
                    error_msg = result.get('error', 'неизвестная ошибка') if result else 'result is None'
                    print(f"❌ ОШИБКА ФАЗЫ 5: {error_msg}")
                    raise Exception(f"Ошибка фазы 5: {error_msg}")
            else:
                print("⏭️ Фаза 5 пропущена (уже есть результаты)")

            # ========== ЗАВЕРШЕНИЕ ==========
            print("\n" + "="*60)
            print("✅ ПРОЕКТ УСПЕШНО ЗАВЕРШЕН")
            print("="*60)

            task.status = ProjectStatus.COMPLETED
            task.current_phase = 7
            task.progress = 100
            task.message = "Завершён успешно"
            task.completed_at = datetime.now().isoformat()
            self._save_queue()

            # ✅ ФИНАЛЬНАЯ ПРОВЕРКА
            # В user_queue_manager.py - финальная проверка

            # ========== ФИНАЛЬНАЯ ПРОВЕРКА ==========
            print("\n🔍 ФИНАЛЬНАЯ ПРОВЕРКА ФАЙЛА:")
            if project_file.exists():
                with open(project_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)

                    # ПРОВЕРЯЕМ ВСЕ ВОЗМОЖНЫЕ МЕСТА
                    phase4_prompts = file_data.get('app_data', {}).get('phase4', {}).get('prompts', [])
                    phase5_results_1 = file_data.get('app_data', {}).get('phase5', {}).get('results', {})
                    phase5_results_2 = file_data.get('app_data', {}).get('phase5_results', {})
                    phase5_results_3 = file_data.get('phase5_results', {})

                    print(f"   phase4.prompts: {len(phase4_prompts)}")
                    print(f"   app_data.phase5.results: {len(phase5_results_1)}")
                    print(f"   app_data.phase5_results: {len(phase5_results_2)}")
                    print(f"   phase5_results: {len(phase5_results_3)}")

                    # Если есть результаты где-то, но не в основном месте - копируем
                    if phase5_results_2 and not phase5_results_1:
                        print(f"   🔄 Копируем phase5_results в app_data.phase5.results")
                        file_data['app_data']['phase5']['results'] = phase5_results_2
                        with open(project_file, 'w', encoding='utf-8') as f:
                            json.dump(file_data, f, ensure_ascii=False, indent=2)
                        print(f"   ✅ Исправлено!")

                    if phase5_results_3 and not phase5_results_1:
                        print(f"   🔄 Копируем phase5_results в app_data.phase5.results")
                        file_data['app_data']['phase5']['results'] = phase5_results_3
                        with open(project_file, 'w', encoding='utf-8') as f:
                            json.dump(file_data, f, ensure_ascii=False, indent=2)
                        print(f"   ✅ Исправлено!")

        except Exception as e:
            print("\n" + "="*60)
            print(f"❌❌❌ ОШИБКА В _run_project: {e}")
            print("="*60)
            import traceback
            traceback.print_exc()

            task.status = ProjectStatus.FAILED
            task.error = str(e)
            task.message = f"Ошибка: {str(e)[:80]}"
            self._save_queue()
        finally:
            self._save_queue()
            print("\n" + "="*80)
            print("🏁 _run_project FINISHED")
            print("="*80 + "\n")


    def _force_save_phase_data_to_file(self, project_id: str, user_id: int,
                                       site_name: str, domain_name: str,
                                       phase4_prompts=None, phase5_results=None):
        """ПРЯМОЕ СОХРАНЕНИЕ + обновление app_data"""
        project_file = Path(f"sites/{site_name}/domains/{domain_name}/projects/{user_id}/{project_id}.json")
        project_file.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        if project_file.exists():
            try:
                with open(project_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                data = {}

        if 'app_data' not in data:
            data['app_data'] = {}

        updated = False

        if phase4_prompts:
            if isinstance(phase4_prompts, dict):
                prompts_list = list(phase4_prompts.values())
            else:
                prompts_list = phase4_prompts or []

            if prompts_list:
                data['app_data'].setdefault('phase4', {})['prompts'] = prompts_list
                data['app_data']['phase4']['generated_count'] = len(prompts_list)
                updated = True
                print(f"💾 _force_save: phase4 = {len(prompts_list)} промптов")

        if phase5_results:
            if isinstance(phase5_results, list):
                results_dict = {f"b{i}": r for i, r in enumerate(phase5_results)}
            else:
                results_dict = phase5_results or {}

            if results_dict:
                data['app_data'].setdefault('phase5', {})['results'] = results_dict
                data['app_data']['phase5']['phase_completed'] = True
                data['app_data']['phase5_completed'] = True
                updated = True
                print(f"💾 _force_save: phase5 = {len(results_dict)} результатов")

        if updated:
            data['updated_at'] = datetime.now().isoformat()
            try:
                with open(project_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"✅ Прямое сохранение завершено: {project_file}")
                return True
            except Exception as e:
                print(f"❌ Ошибка записи файла: {e}")
        return False

    def add_project(self, project_id: str, project_name: str, category: str,
                    site_name: str = None, domain_name: str = None, user_id: int = None) -> bool:
        """Добавляет проект в очередь - С ПРАВИЛЬНЫМ ДОМЕНОМ"""

        if user_id is not None and user_id != self.user_id:
            print(f"⚠️ Несоответствие user_id: {user_id} vs {self.user_id}")
            return False

        # ✅ ИСПОЛЬЗУЕМ ДОМЕН ИЗ self (ЗАГРУЖЕН ИЗ ФАЙЛА)
        if site_name is None:
            site_name = self.site_name
        if domain_name is None:
            domain_name = self.domain_name

        print(f"📌 Добавление проекта с доменом: {site_name}/{domain_name}")

        # ✅ ПРОВЕРЯЕМ ФАЙЛ
        from pathlib import Path
        project_file = Path(f"sites/{site_name}/domains/{domain_name}/projects/{self.user_id}/{project_id}.json")
        print(f"   Проверяем: {project_file}")
        print(f"   Существует: {project_file.exists()}")

        if not project_file.exists():
            print(f"❌ Файл проекта не найден в {project_file}")
            return False

        # ... остальной код без изменений ...

        # ✅ СОХРАНЯЕМ С ПРАВИЛЬНЫМ ДОМЕНОМ
        task = ProjectTask(
            project_id=project_id,
            user_id=self.user_id,
            project_name=project_name,
            category=category,
            status=ProjectStatus.QUEUED,
            message="В очереди",
            site_name=site_name,      # ← ПРАВИЛЬНЫЙ САЙТ
            domain_name=domain_name    # ← ПРАВИЛЬНЫЙ ДОМЕН
        )

        self.projects[project_id] = task
        self._queue.put({
            'project_id': project_id,
            'user_id': task.user_id,
            'site_name': task.site_name,
            'domain_name': task.domain_name
        })
        self._save_queue()

        print(f"📥 Проект {project_name} добавлен в очередь с доменом {site_name}/{domain_name}")
        return True

    def get_status(self, project_id: str) -> Dict:
        if project_id in self.projects:
            p = self.projects[project_id]

            # ✅ Если статус COMPLETED - проверяем файл
            if p.status == ProjectStatus.COMPLETED:
                project_file = Path(f"sites/{p.site_name}/domains/{p.domain_name}/projects/{p.user_id}/{project_id}.json")
                if project_file.exists():
                    try:
                        with open(project_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            has_real_results = bool(data.get('app_data', {}).get('phase5', {}).get('results'))
                            if not has_real_results:
                                # В файле нет результатов - статус не COMPLETED
                                return {
                                    'status': 'idle',
                                    'current_phase': 3,
                                    'message': 'Готов к запуску',
                                    'progress': 0,
                                    'error': None,
                                    'project_name': p.project_name,
                                    'user_id': p.user_id
                                }
                    except:
                        pass

            return {
                'status': p.status.value,
                'current_phase': p.current_phase,
                'message': p.message,
                'progress': p.progress,
                'error': p.error,
                'project_name': p.project_name,
                'user_id': p.user_id
            }
        return {'status': 'unknown'}

    def get_all_projects_status(self) -> Dict:
        return {pid: self.get_status(pid) for pid in self.projects}

    def remove_project(self, project_id: str):
        if project_id in self.projects:
            del self.projects[project_id]
            self._save_queue()

    def clear_completed(self) -> int:
        completed_ids = []
        for pid, task in self.projects.items():
            if task.status in [ProjectStatus.COMPLETED, ProjectStatus.FAILED]:
                completed_ids.append(pid)

        for pid in completed_ids:
            del self.projects[pid]

        self._save_queue()
        return len(completed_ids)

    def stop(self):
        print(f"🛑 Остановка worker для пользователя {self.user_id}")
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    # ===== НОВЫЕ МЕТОДЫ =====
    def ensure_worker_running(self):
        """Гарантирует, что worker поток запущен (вызывается из UI)"""
        if not self.is_worker_running():
            print("🔄 Worker не активен, запускаем...")
            return self.start_worker()
        return True

    def get_reliable_status(self, project_id: str) -> Dict:
        """Получает статус проекта (НЕ ЗАПУСКАЕТ ВОРКЕР АВТОМАТИЧЕСКИ)"""
        # ❌ УБИРАЕМ self.ensure_worker_running()

        # Получаем статус
        status = self.get_status(project_id)

        # Если статус queued, но проект не в очереди worker'а - добавляем
        if status.get('status') == 'queued':
            in_queue = any(item.get('project_id') == project_id for item in list(self._queue.queue))
            if not in_queue and project_id in self.projects:
                task = self.projects[project_id]
                self._queue.put({
                    'project_id': project_id,
                    'user_id': task.user_id,
                    'site_name': task.site_name,
                    'domain_name': task.domain_name
                })
                print(f"📥 Проект {project_id} добавлен в очередь worker'а")

        return status


class GlobalQueueManager:
    _instance = None
    _lock = threading.Lock()
    _queues: Dict[int, UserQueueManager] = {}

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    @classmethod
    def get_queue(cls, user_id: int) -> UserQueueManager:
        with cls._lock:
            if user_id not in cls._queues:
                cls._queues[user_id] = UserQueueManager(user_id)
                print(f"📁 Создана очередь для пользователя {user_id}")
            else:
                # ✅ НИЧЕГО НЕ ДЕЛАЕМ - НЕ ПЕРЕСОЗДАЕМ!
                pass
            return cls._queues[user_id]

    @classmethod
    def remove_user_queue(cls, user_id: int):
        with cls._lock:
            if user_id in cls._queues:
                cls._queues[user_id].stop()
                del cls._queues[user_id]
                print(f"🗑️ Удалена очередь для пользователя {user_id}")

    @classmethod
    def get_all_queues_info(cls) -> Dict:
        with cls._lock:
            info = {}
            for user_id, queue in cls._queues.items():
                info[user_id] = {
                    'total_projects': len(queue.projects),
                    'queued': len([p for p in queue.projects.values() if p.status == ProjectStatus.QUEUED]),
                    'running': len([p for p in queue.projects.values() if p.status == ProjectStatus.RUNNING]),
                    'completed': len([p for p in queue.projects.values() if p.status == ProjectStatus.COMPLETED]),
                    'failed': len([p for p in queue.projects.values() if p.status == ProjectStatus.FAILED])
                }
            return info


def get_user_queue() -> UserQueueManager:
    """Возвращает очередь для текущего пользователя из Streamlit"""
    try:
        user_id = st.session_state.get('user_id')
        if not user_id:
            raise ValueError("Пользователь не авторизован")
        return GlobalQueueManager.get_queue(user_id)
    except Exception as e:
        print(f"⚠️ get_user_queue: {e}")
        return None