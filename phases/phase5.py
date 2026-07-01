



import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import time
import pandas as pd
from ai_settings.ai_module import AIGenerator, AIConfigManager
from styles import load_css
from domain_manager import DomainManager
from pathlib import Path
# --- CSS стили для фазы 5 ---
LOG_FILE = "phase5_crash.log"
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
from file_data_manager import FileDataManager
import traceback
from datetime import datetime
import streamlit as st
from typing import Dict, List, Optional, Any
# В самом начале phase5.py, после импортов
import traceback
from datetime import datetime
import streamlit as st
def _get_context_data(context, st_session):
    """
    Возвращает данные контекста.
    Приоритет: context > st.session_state
    """
    if context is not None:
        return {
            'user_id': context.user_id,
            'project_id': context.project_id,
            'site_name': context.site_name,
            'domain_name': context.domain_name,
            'project_name': context.data.get('project_name', 'Новый проект'),
            'category': context.data.get('category', ''),
            'app_data': context.data,
            'has_context': True
        }
    else:
        return {
            'user_id': st_session.get('user_id'),
            'project_id': st_session.get('current_project_id'),
            'site_name': st_session.get('current_site', 'steelborg'),
            'domain_name': st_session.get('current_domain', 'default'),
            'project_name': st_session.get('project_name', 'Новый проект'),
            'category': st_session.get('category', ''),
            'app_data': st_session.get('app_data', {}),
            'has_context': False
        }
# Глобальная функция логирования
def log(msg="", level="INFO"):
    """Логирование для отладки"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level} | {msg}\n"

    # Пишем в файл
    try:
        with open("phase5_debug.log", "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

    # Сохраняем в session_state
    if "logs" not in st.session_state:
        st.session_state.logs = []
    st.session_state.logs.append(line)

    print(line.strip())

# в консоль хостинга
# Добавить после всех импортов, перед def log():



def local_css():
    st.markdown("""
    <style>
    .phase5-container {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    .prompt-card {
        background-color: white;
        border-left: 4px solid #4CAF50;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .result-card {
        background-color: #e8f5e9;
        border-left: 4px solid #2196F3;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .error-card {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .pending-card {
        background-color: #fff3e0;
        border-left: 4px solid #ff9800;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.8em;
        font-weight: bold;
        margin: 0 5px;
    }
    .status-success { background-color: #c8e6c9; color: #2e7d32; }
    .status-error { background-color: #ffcdd2; color: #c62828; }
    .status-pending { background-color: #ffe0b2; color: #ef6c00; }
    .status-running { background-color: #bbdefb; color: #1565c0; }
    .generation-progress {
        background: linear-gradient(90deg, #4CAF50, #8BC34A);
        height: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .text-preview {
        max-height: 200px;
        overflow-y: auto;
        border: 1px solid #ddd;
        padding: 10px;
        border-radius: 5px;
        background-color: #fafafa;
        font-size: 0.9em;
    }
    .stats-box {
        background-color: white;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
        border: 1px solid #e0e0e0;
    }
    </style>
    """, unsafe_allow_html=True)

def init_phase5_structure():
    """Надёжная инициализация - НЕ ПЕРЕЗАПИСЫВАЕТ существующие данные"""
    if 'phase5' not in st.session_state:
        st.session_state.phase5 = {}

    phase5 = st.session_state.phase5

    defaults = {
        'generation_status': 'idle',
        'selected_prompt_ids': [],
        'results': {},  # ← НЕ ПЕРЕЗАПИСЫВАТЬ, если есть!
        'statistics': {
            'total': 0, 'selected': 0, 'completed': 0, 'success': 0, 'error': 0, 'pending': 0
        },
        'generation_settings': {
            'provider': 'agentplatform', 'temperature': 0.7, 'max_tokens': 2000,
            'retry_count': 3, 'delay_between_requests': 2.0
        },
        'generation_queue': [], 'current_index': 0, 'generation_running': False,
        'initialized': True, 'phase_completed': False
    }

    for key, default in defaults.items():
        if key not in phase5:
            phase5[key] = default
        elif isinstance(phase5[key], dict) and not phase5[key]:
            phase5[key] = default
        # ✅ НЕ ПЕРЕЗАПИСЫВАЕМ, если уже есть данные!
        elif key == 'results' and phase5['results']:
            # Уже есть результаты - не трогаем
            pass
        elif key == 'statistics' and phase5['statistics'].get('success', 0) > 0:
            # Уже есть успешные генерации - не трогаем
            pass

    # ✅ Дополнительная страховка - не перезаписываем существующие результаты
    if 'results' not in phase5:
        phase5['results'] = {}
    if 'statistics' not in phase5:
        phase5['statistics'] = defaults['statistics'].copy()
# --- Менеджер данных фазы 5 ---
class Phase5DataManager:
    """Управление данными для фазы 5"""

    def __init__(self):
        self._ensure_session_state()
        self._load_from_current_project()
        # После force_load_phase5_from_file()
        if 'phase5' in st.session_state:
            # Обновляем статистику без data_manager
            results = st.session_state.phase5.get('results', {})
            total = len(st.session_state.phase5_prompts) if 'phase5_prompts' in st.session_state else 0
            success = sum(1 for r in results.values() if r.get('status') == 'success')
            error = sum(1 for r in results.values() if r.get('status') == 'error')

            st.session_state.phase5['statistics'] = {
                'total': total,
                'success': success,
                'error': error,
                'completed': success + error,
                'pending': total - success - error,
                'selected': st.session_state.phase5.get('statistics', {}).get('selected', total)
            }
    def _log_prompts_stats(self, context=""):
        """Логирует статистику по промптам"""
        prompts = st.session_state.phase5_prompts if 'phase5_prompts' in st.session_state else []
        results = st.session_state.phase5.get('results', {})

        print(f"\n{'=' * 60}")
        print(f"📊 СТАТИСТИКА ПРОМПТОВ: {context}")
        print(f"{'=' * 60}")
        print(f"   Всего промптов в session_state.phase5_prompts: {len(prompts)}")
        print(f"   Всего результатов в session_state.phase5.results: {len(results)}")

        # Статистика по статусам
        status_counts = {}
        for r in results.values():
            status = r.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1

        print(f"   Статусы результатов:")
        for status, count in status_counts.items():
            print(f"      {status}: {count}")

        # Проверяем наличие phase5_id у промптов
        missing_id = 0
        for p in prompts:
            if not p.get('phase5_id'):
                missing_id += 1
        print(f"   Промптов без phase5_id: {missing_id}")

        # Проверяем соответствие промптов и результатов
        prompts_with_results = 0
        for p in prompts:
            if p.get('phase5_id') in results:
                prompts_with_results += 1
        print(f"   Промптов с результатами: {prompts_with_results}")

        print(f"{'=' * 60}\n")
    def _ensure_session_state(self):
        """Гарантирует, что session_state инициализирован"""
        if 'phase5' not in st.session_state:
            st.session_state.phase5 = {
                'generation_status': 'idle',
                'selected_prompt_ids': [],
                'results': {},
                'statistics': {
                    'total': 0, 'selected': 0, 'completed': 0, 'success': 0, 'error': 0, 'pending': 0
                },
                'generation_settings': {
                    'provider': 'agentplatform',
                    'temperature': 0.7,
                    'max_tokens': 2000,
                    'retry_count': 3,
                    'delay_between_requests': 2.0
                },
                'generation_queue': [],
                'current_index': 0,
                'generation_running': False,
                'initialized': True,
                'phase_completed': False
            }
        if 'phase5_prompts' not in st.session_state:
            st.session_state.phase5_prompts = []

    def _get_project_file(self, context=None):
        """Возвращает путь к файлу текущего проекта"""
        # ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
        if context is not None:
            user_id = context.user_id
            site = context.site_name
            domain = context.domain_name
            project_id = context.project_id
        else:
            user_id = st.session_state.get('user_id')
            site = st.session_state.get('current_site', 'steelborg')
            domain = st.session_state.get('current_domain', 'default')
            project_id = st.session_state.get('current_project_id')

        if not user_id or not project_id:
            return None

        return Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")
    def _load_from_project_file(self, context=None):
        """Загружает данные из файла проекта"""
        project_file = self._get_project_file(context)
        if not project_file or not project_file.exists():
            return {}

        with open(project_file, 'r', encoding='utf-8') as f:
            file_data = json.load(f)

        return file_data.get('app_data', {})

    def _save_to_project_file(self, app_data: dict, context=None):
        """Сохраняет данные в файл проекта - ПЕРЕЗАПИСЫВАЕТ файл"""
        project_file = self._get_project_file(context)
        if not project_file:
            return False

        # ✅ ЧИТАЕМ СУЩЕСТВУЮЩИЙ ФАЙЛ, ЕСЛИ ОН ЕСТЬ
        file_data = {}
        if project_file.exists():
            try:
                with open(project_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
            except:
                file_data = {}

        # ✅ ОБНОВЛЯЕМ app_data
        file_data['app_data'] = app_data
        file_data['updated_at'] = datetime.now().isoformat()

        # ✅ СОХРАНЯЕМ (ПЕРЕЗАПИСЫВАЕМ)
        with open(project_file, 'w', encoding='utf-8') as f:
            json.dump(file_data, f, ensure_ascii=False, indent=2)

        return True

    def _load_from_current_project(self):
        """Загружает данные из файла текущего проекта"""
        app_data = self._load_from_project_file()
        phase5_from_app = app_data.get('phase5', {})

        if phase5_from_app:
            if 'results' in phase5_from_app and phase5_from_app['results']:
                st.session_state.phase5['results'] = phase5_from_app['results'].copy()
                print(f"✅ Загружены results: {len(st.session_state.phase5['results'])}")

            if 'statistics' in phase5_from_app:
                st.session_state.phase5['statistics'] = phase5_from_app['statistics'].copy()

            if 'generation_settings' in phase5_from_app:
                st.session_state.phase5['generation_settings'] = phase5_from_app['generation_settings'].copy()

            if 'prompts' in phase5_from_app and phase5_from_app['prompts']:
                st.session_state.phase5_prompts = phase5_from_app['prompts'].copy()
                print(f"✅ Загружены промпты: {len(st.session_state.phase5_prompts)}")

            if 'selected_prompt_ids' in phase5_from_app:
                st.session_state.phase5['selected_prompt_ids'] = phase5_from_app['selected_prompt_ids'].copy()

            if 'generation_status' in phase5_from_app:
                st.session_state.phase5['generation_status'] = phase5_from_app['generation_status']

            if phase5_from_app.get('phase_completed', False):
                st.session_state.phase5['phase_completed'] = True
                st.session_state.phase5_completed = True

            current_project_id = st.session_state.get('current_project_id', '')
            st.session_state.phase5['last_loaded_project'] = current_project_id
            log(f"✅ Загружены данные phase5 из проекта {current_project_id}")
        else:
            print(f"⚠️ Нет данных phase5 в проекте")

    def load_prompts_from_phase4(self, context=None):
        """Загружает ГОТОВЫЕ промпты из фазы 4"""
        import json
        from pathlib import Path

        print("\n" + "=" * 80)
        print("🔍 load_prompts_from_phase4 STARTED")
        print("=" * 80)

        # ===== 1. ЗАГРУЖАЕМ ГОТОВЫЕ ПРОМПТЫ ИЗ ФАЙЛА =====
        app_data = self._load_from_project_file(context)
        phase4_data = app_data.get('phase4', {})

        # ✅ БЕРЕМ ГОТОВЫЕ ПРОМПТЫ
        prompts = phase4_data.get('prompts', [])

        if not prompts:
            print("   ❌ Нет готовых промптов в phase4.prompts")
            return []

        print(f"   ✅ Загружено {len(prompts)} готовых промптов из phase4.prompts")

        # ===== 2. СОХРАНЯЕМ ИХ В SESSION_STATE =====
        st.session_state.phase5_prompts = prompts

        # ===== 3. СОЗДАЕМ ЗАПИСИ ДЛЯ ВСЕХ ПРОМПТОВ =====
        new_results = {}
        for i, prompt in enumerate(prompts):
            # ✅ БЕРЕМ ГОТОВЫЙ phase5_id ИЗ ПРОМПТА
            prompt_id = prompt.get('phase5_id')

            # Если нет phase5_id - создаем
            if not prompt_id:
                if 'characteristic_id' in prompt:
                    prompt_id = f"char_{prompt['characteristic_id']}_{prompt.get('value', '')}_{prompt.get('prompt_num', i)}"
                elif 'block_id' in prompt:
                    prompt_id = f"block_{prompt['block_id']}_{prompt.get('prompt_num', i)}"
                else:
                    prompt_id = f"prompt_{i}"
                prompt['phase5_id'] = prompt_id

            # ✅ ИСПОЛЬЗУЕМ ГОТОВЫЙ ПРОМПТ
            new_results[prompt_id] = {
                'prompt_id': prompt_id,
                'prompt': prompt.get('prompt', ''),  # ← БЕРЕМ ГОТОВЫЙ ТЕКСТ!
                'ai_response': '',
                'status': 'pending',
                'model': '',
                'provider': '',
                'tokens_used': 0,
                'generated_at': None,
                'error_message': None,
                'edited_text': '',
                'characteristic_name': prompt.get('characteristic_name', ''),
                'characteristic_value': prompt.get('value', ''),
                'block_name': prompt.get('block_name', ''),
                'prompt_num': prompt.get('prompt_num', 1),
                'type': prompt.get('type', prompt.get('block_type', 'unknown'))
            }

        st.session_state.phase5['results'] = new_results

        # ===== 4. ВЫБИРАЕМ ВСЕ ПРОМПТЫ =====
        all_ids = list(new_results.keys())
        st.session_state.phase5['selected_prompt_ids'] = all_ids

        # ===== 5. СТАТИСТИКА =====
        st.session_state.phase5['statistics'] = {
            'total': len(prompts),
            'selected': len(all_ids),
            'completed': 0,
            'success': 0,
            'error': 0,
            'pending': len(prompts)
        }

        print(f"\n✅ Загружено {len(prompts)} готовых промптов")
        print(f"   Создано {len(new_results)} записей")
        print("=" * 80 + "\n")
        # В load_prompts_from_phase4
        print(f"\n📊 ПРОВЕРКА:")
        print(f"   phase4.prompts: {len(phase4_data.get('prompts', []))} промптов")
        print(f"   Первый промпт: {phase4_data['prompts'][0].get('characteristic_name')} = {phase4_data['prompts'][0].get('value')}")
        print(f"   Всего создано результатов: {len(new_results)}")
        return prompts

    def save_to_app_data(self, app_state=None):
        """Сохраняет данные фазы 5 в файл ПРОЕКТА"""
        # ✅ СОХРАНЯЕМ ВСЕ РЕЗУЛЬТАТЫ, БЕЗ ФИЛЬТРАЦИИ!
        phase5_data = {
            'results': st.session_state.phase5.get('results', {}).copy(),
            'statistics': st.session_state.phase5.get('statistics', {}).copy(),
            'generation_settings': st.session_state.phase5.get('generation_settings', {}).copy(),
            'prompts': st.session_state.phase5_prompts.copy() if st.session_state.phase5_prompts else [],
            'selected_prompt_ids': st.session_state.phase5.get('selected_prompt_ids', []).copy(),
            'generation_status': st.session_state.phase5.get('generation_status', 'idle'),
            'generation_running': st.session_state.phase5.get('generation_running', False),
            'generation_queue': st.session_state.phase5.get('generation_queue', []).copy(),
            'current_index': st.session_state.phase5.get('current_index', 0),
            'phase_completed': st.session_state.phase5.get('generation_status') == 'completed',
            'completed_at': datetime.now().isoformat() if st.session_state.phase5.get(
                'generation_status') == 'completed' else None,
            'prompts_count': len(st.session_state.phase5_prompts) if st.session_state.phase5_prompts else 0
        }

        # ✅ СОХРАНЯЕМ В ФАЙЛ
        app_data = self._load_from_project_file()
        app_data['phase5'] = phase5_data
        app_data['phase5_completed'] = st.session_state.phase5.get('generation_status') == 'completed'
        self._save_to_project_file(app_data)

        # ✅ ОБНОВЛЯЕМ ТОЛЬКО ФЛАГ В session_state ДЛЯ UI (НЕ ДАННЫЕ!)
        if 'app_data' not in st.session_state:
            st.session_state.app_data = {}
        st.session_state.app_data['phase5'] = phase5_data  # ← для отображения в UI

        log(f"✅ Данные phase5 сохранены в файл проекта {st.session_state.get('current_project_id', '')}")
        print(f"   Сохранено результатов: {len(phase5_data['results'])}")
        print(f"   Промптов: {len(phase5_data['prompts'])}")

        return True

    def complete_phase5_and_prepare_phase6(self):
        """Завершить фазу 5 и подготовить данные для фазы 6 — исправленная версия"""
        results = st.session_state.phase5.get('results', {})
        success_count = sum(1 for r in results.values() if r.get('status') == 'success')

        print(f"📊 complete_phase5: всего results={len(results)}, success={success_count}")

        if success_count == 0:
            st.warning("Нет сгенерированных результатов!")
            return False

        # === ФОРМИРУЕМ АКТУАЛЬНЫЕ ДАННЫЕ ===
        phase6_data = {
            'generation_results': results.copy(),           # ← все актуальные результаты
            'generation_stats': st.session_state.phase5.get('statistics', {}).copy(),
            'generation_settings': st.session_state.phase5.get('generation_settings', {}).copy(),
            'prompts_data': st.session_state.phase5_prompts.copy() if st.session_state.phase5_prompts else [],
            'completed_at': datetime.now().isoformat(),
            'total_texts': success_count,
            'completed_manually': True   # флаг, что было ручное завершение
        }

        # === СОХРАНЯЕМ В ФАЙЛ ===
        app_data = self._load_from_project_file()
        app_data['phase5'] = phase6_data
        app_data['phase5_completed'] = True
        app_data['phase5_status'] = 'completed'
        app_data['phase6'] = phase6_data  # дублируем для фазы 6

        self._save_to_project_file(app_data)

        # === ОБНОВЛЯЕМ session_state ===
        st.session_state.phase5['phase_completed'] = True
        st.session_state.phase5['generation_status'] = 'completed'
        st.session_state.phase5['phase_completed_at'] = datetime.now().isoformat()

        if 'app_data' not in st.session_state:
            st.session_state.app_data = {}
        st.session_state.app_data['phase5'] = phase6_data
        st.session_state.app_data['phase5_completed'] = True

        # Дополнительное сохранение
        self.save_to_app_data()

        print(f"✅ Фаза 5 завершена успешно! Передано в фазу 6: {success_count} текстов")
        return True

    def _update_statistics(self, context=None):
        """Обновляет статистику из результатов в session_state"""
        results = st.session_state.phase5.get('results', {})
        prompts = st.session_state.phase5_prompts if 'phase5_prompts' in st.session_state else []

        total = len(prompts) if prompts else len(results)
        success = sum(1 for r in results.values() if r.get('status') == 'success')
        error = sum(1 for r in results.values() if r.get('status') == 'error')
        completed = success + error
        pending = total - completed
        selected = st.session_state.phase5.get('statistics', {}).get('selected', 0)

        st.session_state.phase5['statistics'] = {
            'total': total,
            'success': success,
            'error': error,
            'completed': completed,
            'pending': pending,
            'selected': selected
        }

        print(f"📊 Статистика обновлена: total={total}, success={success}, error={error}, pending={pending}")
        print(f"   results={len(results)}, prompts={len(prompts)}")

        # ❌ НЕ ВЫЗЫВАТЬ СОХРАНЕНИЕ ЗДЕСЬ!
        # self.save_to_app_data()  ← УБРАТЬ!

        return st.session_state.phase5['statistics']

    def get_prompt_by_id(self, prompt_id: str):
        """Возвращает промпт по ID"""
        if 'phase5_prompts' in st.session_state:
            for prompt in st.session_state.phase5_prompts:
                if prompt.get('phase5_id') == prompt_id:
                    return prompt
        return None

    def get_prompts_for_generation(self) -> List[Dict]:
        """Возвращает список выбранных промптов для генерации"""
        selected_ids = st.session_state.phase5.get('selected_prompt_ids', [])
        prompts = st.session_state.phase5_prompts

        if not prompts or not selected_ids:
            return []

        return [p for p in prompts if p.get('phase5_id') in selected_ids]

    def update_result(self, prompt_id: str, result_data: dict, save_to_app: bool = False):
        """Обновляет результат для промпта"""
        if 'phase5' not in st.session_state:
            st.session_state.phase5 = {}
        if 'results' not in st.session_state.phase5:
            st.session_state.phase5['results'] = {}

        # Обновляем результат
        if prompt_id in st.session_state.phase5['results']:
            st.session_state.phase5['results'][prompt_id].update(result_data)
        else:
            st.session_state.phase5['results'][prompt_id] = result_data

        # Обновляем статистику
        self._update_statistics()

        # ✅ ВСЕГДА СОХРАНЯЕМ В ФАЙЛ, ЧТОБЫ ДАННЫЕ НЕ ТЕРЯЛИСЬ
        # Убираем условие save_to_app - всегда сохраняем
        self.save_to_app_data()

        return True

    def toggle_prompt_selection(self, prompt_id: str):
        """Переключает выбор промпта"""
        if 'selected_prompt_ids' not in st.session_state.phase5:
            st.session_state.phase5['selected_prompt_ids'] = []

        selected = st.session_state.phase5['selected_prompt_ids']
        if prompt_id in selected:
            selected.remove(prompt_id)
        else:
            selected.append(prompt_id)

        # Обновляем статистику
        self._update_statistics()

        return True

    def reset_generation(self):
        """Сбрасывает все результаты и выборы"""
        st.session_state.phase5['results'] = {}
        st.session_state.phase5['selected_prompt_ids'] = []
        st.session_state.phase5['generation_status'] = 'idle'
        st.session_state.phase5['generation_running'] = False
        st.session_state.phase5['generation_queue'] = []
        st.session_state.phase5['current_index'] = 0

        self._update_statistics()
        self.save_to_app_data()

    def reset_session_data(self):
        """Полностью сбрасывает данные фазы 5"""
        st.session_state.phase5 = {
            'generation_status': 'idle',
            'selected_prompt_ids': [],
            'results': {},
            'statistics': {
                'total': 0, 'selected': 0, 'completed': 0, 'success': 0, 'error': 0, 'pending': 0
            },
            'generation_settings': {
                'provider': 'agentplatform',
                'temperature': 0.7,
                'max_tokens': 2000,
                'retry_count': 3,
                'delay_between_requests': 2.0
            },
            'generation_queue': [],
            'current_index': 0,
            'generation_running': False,
            'initialized': True,
            'phase_completed': False
        }
        st.session_state.phase5_prompts = []

        self.save_to_app_data()
    def get_pending_prompts(self) -> List[Dict]:
        """Возвращает промпты, которые еще не сгенерированы (pending)"""
        prompts = st.session_state.phase5_prompts
        results = st.session_state.phase5.get('results', {})

        pending = []
        for p in prompts:
            pid = p.get('phase5_id')
            if pid:
                result = results.get(pid, {})
                if result.get('status') != 'success':
                    pending.append(p)
        return pending
    def save_results_to_file(self, export_format: str = 'json') -> Optional[str]:
        """Экспортирует результаты в файл"""
        import pandas as pd
        from datetime import datetime

        results = st.session_state.phase5.get('results', {})
        if not results:
            return None

        # Подготавливаем данные для экспорта
        export_data = []
        for prompt_id, result in results.items():
            if result.get('status') == 'success' and result.get('ai_response'):
                export_data.append({
                    'prompt_id': prompt_id,
                    'characteristic_name': result.get('characteristic_name', ''),
                    'characteristic_value': result.get('characteristic_value', ''),
                    'block_name': result.get('block_name', ''),
                    'prompt_num': result.get('prompt_num', 1),
                    'ai_response': result.get('ai_response', ''),
                    'edited_text': result.get('edited_text', result.get('ai_response', '')),
                    'model': result.get('model', ''),
                    'provider': result.get('provider', ''),
                    'tokens_used': result.get('tokens_used', 0),
                    'generated_at': result.get('generated_at', '')
                })

        if not export_data:
            return None

        # Создаем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"phase5_results_{timestamp}"

        # Экспортируем в нужном формате
        if export_format == 'json':
            filename += '.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            return filename

        elif export_format == 'txt':
            filename += '.txt'
            with open(filename, 'w', encoding='utf-8') as f:
                for item in export_data:
                    f.write(f"=== {item.get('characteristic_name', 'Без названия')} ===\n")
                    f.write(f"Значение: {item.get('characteristic_value', '')}\n")
                    f.write(f"Текст:\n{item.get('ai_response', '')}\n")
                    f.write(f"Редактированный текст:\n{item.get('edited_text', '')}\n")
                    f.write("-" * 50 + "\n\n")
            return filename

        elif export_format == 'excel':
            filename += '.xlsx'
            df = pd.DataFrame(export_data)
            df.to_excel(filename, index=False, sheet_name='Phase5 Results')
            return filename

        return None
class GenerationManager:
    def __init__(self, data_manager: Phase5DataManager):
        self.data_manager = data_manager
        self._should_stop = False  # Флаг для остановки
        self._should_pause = False  # Флаг для паузы
        if 'ai_config_manager' not in st.session_state:
            from ai_settings.ai_module import AIConfigManager
            st.session_state.ai_config_manager = AIConfigManager()

    def start_generation(self, batch_size=10):
        """Начать генерацию текстов — исправленная версия"""
        if 'phase5' not in st.session_state:
            st.error("Фаза 5 не инициализирована")
            return

        print("=== START_GENERATION START ===")
        print(f"Текущий статус: {st.session_state.phase5.get('generation_status')}")
        print(f"phase_completed: {st.session_state.phase5.get('phase_completed')}")

        # === ПРИНУДИТЕЛЬНЫЙ СБРОС ВСЕХ СТАТУСОВ ===
        st.session_state.phase5['generation_status'] = 'idle'
        st.session_state.phase5['generation_running'] = False
        st.session_state.phase5['phase_completed'] = False
        st.session_state.phase5['generation_queue'] = []
        st.session_state.phase5['current_index'] = 0

        selected_ids = st.session_state.phase5.get('selected_prompt_ids', [])
        print(f"Выбрано пользователем: {len(selected_ids)}")

        if not selected_ids:
            st.warning("Не выбрано ни одного промпта")
            return

        # Получаем только те, которые действительно нужно генерировать
        prompts = st.session_state.phase5_prompts
        results = st.session_state.phase5.get('results', {})

        to_generate = []
        for p in prompts:
            pid = p.get('phase5_id')
            if pid not in selected_ids:
                continue

            result = results.get(pid, {})
            status = result.get('status')
            response = str(result.get('ai_response', '')).strip()

            if status != 'success' or len(response) < 30:   # надёжная проверка
                to_generate.append(p)

        print(f"Реально будут генерироваться: {len(to_generate)} промптов")

        if not to_generate:
            st.success("✅ Все выбранные промпты уже успешно сгенерированы!")
            self.data_manager._update_statistics()
            return

        pending_ids = [p.get('phase5_id') for p in to_generate]

        # Запускаем генерацию
        st.session_state.phase5.update({
            'generation_status': 'running',
            'generation_start_time': datetime.now().isoformat(),
            'generation_queue': pending_ids,
            'current_index': 0,
            'generation_running': True,
            'current_batch': 0,
            'total_batches': len(pending_ids),
            'error_message': None
        })

        self._should_stop = False
        self._should_pause = False

        # ✅ НЕМЕДЛЕННО ОБРАБАТЫВАЕМ ПЕРВЫЙ БАТЧ
        processed = self.process_batch(batch_size=batch_size)

        if processed > 0:
            st.success(f"🚀 Запущена генерация для {len(pending_ids)} выбранных промптов! Обработано {processed} за батч.")
        else:
            st.error("❌ Не удалось запустить генерацию. Проверьте логи.")

        st.rerun()

    def run_one_generation_step(self):
        """Выполнить один шаг генерации"""
        phase5 = st.session_state.phase5

        if not phase5['generation_running']:
            return

        if phase5['current_index'] >= len(phase5['generation_queue']):
            phase5['generation_status'] = 'completed'
            phase5['generation_running'] = False
            phase5['generation_end_time'] = datetime.now().isoformat()
            return

        if self._should_stop:
            phase5['generation_status'] = 'stopped'
            phase5['generation_running'] = False
            phase5['generation_end_time'] = datetime.now().isoformat()
            return

        while self._should_pause and not self._should_stop:
            return

        # Получаем текущий промпт
        prompt_id = phase5['generation_queue'][phase5['current_index']]
        prompt = self.data_manager.get_prompt_by_id(prompt_id)

        if not prompt:
            phase5['current_index'] += 1
            return

        # Подготавливаем AI генератор
        config_manager = st.session_state.ai_config_manager
        ai_generator = AIGenerator(config_manager)
        settings = phase5['generation_settings']
        provider = settings['provider']
        retry_count = settings['retry_count']

        # Генерация с повторными попытками
        success = False
        error_message = None
        ai_response = None
        model_used = None
        tokens_used = 0

        for attempt in range(retry_count):
            try:
                results = ai_generator.generate_instruction(
                    prompt_template=prompt.get('prompt', ''),
                    context={},
                    provider=provider,
                    num_variants=1,
                    return_full_response=False
                )

                if results and results[0]['success']:
                    ai_response = results[0]['text']
                    model_used = results[0].get('model', '')
                    tokens_used = results[0].get('usage', {}).get('total_tokens', 0)
                    success = True
                    break
                else:
                    error_message = results[0].get('error',
                                                   'Неизвестная ошибка ИИ') if results else 'Пустой ответ от ИИ'

            except Exception as e:
                error_message = str(e)

        # Сохраняем результат
        result_data = {
            'ai_response': self._clean_response(ai_response) if success else '',
            'status': 'success' if success else 'error',
            'model': model_used if success else '',
            'provider': provider,
            'tokens_used': tokens_used if success else 0,
            'generated_at': datetime.now().isoformat(),
            'error_message': error_message if not success else None,
            'edited_text': self._clean_response(ai_response) if success else ''
        }

        self.data_manager.update_result(prompt_id, result_data)
        phase5['current_index'] += 1
        phase5['current_batch'] = phase5['current_index']

        # Если это был последний промпт
        if phase5['current_index'] >= len(phase5['generation_queue']):
            phase5['generation_status'] = 'completed'
            phase5['generation_running'] = False
            phase5['generation_end_time'] = datetime.now().isoformat()

    def process_batch(self, batch_size=10):
        phase5 = st.session_state.phase5
        print(f"\n📦 process_batch START: current_index={phase5.get('current_index')}, queue_len={len(phase5.get('generation_queue', []))}")

        if not phase5.get('generation_running', False):
            print("   ⚠️ generation_running = False")
            return 0




        print(f"   current_index={phase5.get('current_index', 0)}")
        print(f"   generation_queue len={len(phase5.get('generation_queue', []))}")

        if not phase5.get('generation_running', False):
            print("   ⚠️ generation_running = False, выход")
            return 0

        if not phase5.get('generation_queue'):
            phase5['generation_running'] = False
            phase5['generation_status'] = 'completed'
            phase5['generation_end_time'] = datetime.now().isoformat()
            print("   ⚠️ generation_queue пуст, завершение")
            return 0

        start_idx = phase5['current_index']
        end_idx = min(start_idx + batch_size, len(phase5['generation_queue']))

        print(f"   Обрабатываем индексы {start_idx} - {end_idx} (всего {end_idx - start_idx} промптов)")

        processed_count = 0

        # Создаём AI генератор один раз на батч
        config_manager = st.session_state.get('ai_config_manager')
        if not config_manager:
            log("❌ AIConfigManager не найден в process_batch!", "ERROR")
            return 0

        ai_generator = AIGenerator(config_manager)

        for i in range(start_idx, end_idx):
            if self._should_stop:
                break

            prompt_id = phase5['generation_queue'][i]
            print(f"   🎯 [{i + 1}/{len(phase5['generation_queue'])}] {prompt_id[:50]}...")

            prompt = self.data_manager.get_prompt_by_id(prompt_id)

            if not prompt:
                print(f"      ⚠️ Промпт не найден, пропускаем")
                phase5['current_index'] += 1
                continue

            success = False
            error_message = None
            ai_response = None
            model_used = None
            tokens_used = 0

            retry_count = phase5['generation_settings'].get('retry_count', 3)
            for attempt in range(retry_count):
                try:
                    results = ai_generator.generate_instruction(
                        prompt_template=prompt.get('prompt', ''),
                        context={},
                        provider=phase5['generation_settings']['provider'],
                        num_variants=1,
                        return_full_response=False
                    )

                    if results and results[0].get('success'):
                        ai_response = results[0]['text']
                        model_used = results[0].get('model', '')
                        tokens_used = results[0].get('usage', {}).get('total_tokens', 0)
                        success = True
                        print(f"      ✅ Успешно! токенов: {tokens_used}")
                        break
                    else:
                        error_message = results[0].get('error', 'Неизвестная ошибка') if results else 'Пустой ответ'
                        print(f"      ⚠️ Попытка {attempt + 1} ошибка: {error_message[:50]}")

                except Exception as e:
                    error_message = str(e)
                    print(f"      ❌ Попытка {attempt + 1} exception: {e}")

            # Формируем результат
            result_data = {
                'ai_response': self._clean_response(ai_response) if success else '',
                'status': 'success' if success else 'error',
                'model': model_used if success else '',
                'provider': phase5['generation_settings']['provider'],
                'tokens_used': tokens_used if success else 0,
                'generated_at': datetime.now().isoformat(),
                'error_message': error_message if not success else None,
                'edited_text': self._clean_response(ai_response) if success else ''
            }

            # Сохраняем в файл не каждый раз
            save_now = (processed_count % 5 == 0) or (i == end_idx - 1)
            self.data_manager.update_result(prompt_id, result_data, save_to_app=save_now)

            phase5['current_index'] += 1
            processed_count += 1

            # Обновляем статистику
            self.data_manager._update_statistics()

        # Логируем после батча
        print(f"\n   📊 После батча:")
        print(f"      processed_count: {processed_count}")
        print(f"      current_index: {phase5['current_index']}")
        print(f"      generation_queue len: {len(phase5['generation_queue'])}")

        # Завершение генерации
        if phase5['current_index'] >= len(phase5['generation_queue']):
            phase5['generation_status'] = 'completed'
            phase5['generation_running'] = False
            phase5['generation_end_time'] = datetime.now().isoformat()
            print(f"   ✅ Генерация успешно завершена! Обработано {processed_count} промптов")
        else:
            phase5['generation_status'] = 'running'
            print(
                f"   ⏳ Генерация продолжается, осталось {len(phase5['generation_queue']) - phase5['current_index']} промптов")

        print(f"📦 process_batch END: processed={processed_count}\n")
        return processed_count

    def _clean_response(self, text):
        """Очистка ответа ИИ от лишних кавычек и форматирования"""
        if not text:
            return ""

        # Убираем обрамляющие кавычки если текст в них целиком
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            text = text[1:-1]

        # Заменяем множественные переносы строк
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Убираем лишние пробелы
        text = text.strip()

        return text

    def pause_generation(self):
        """Приостановить генерацию"""
        if st.session_state.phase5['generation_status'] == 'running':
            self._should_pause = True
            st.session_state.phase5['generation_status'] = 'paused'
            st.info("Генерация приостановлена")
            return True
        return False

    def resume_generation(self):
        """Возобновить генерацию"""
        if st.session_state.phase5['generation_status'] == 'paused':
            self._should_pause = False
            st.session_state.phase5['generation_status'] = 'running'
            st.success("Генерация возобновлена")
            st.rerun()
            return True
        return False

    def stop_generation(self):
        """Остановить генерацию"""
        self._should_stop = True
        self._should_pause = False

        if st.session_state.phase5['generation_status'] in ['running', 'paused']:
            st.session_state.phase5['generation_status'] = 'stopped'
            st.session_state.phase5['generation_running'] = False
            st.session_state.phase5['generation_end_time'] = datetime.now().isoformat()
            st.warning("Генерация остановлена")
            return True
        return False

    def get_generation_progress(self):
        """Получить прогресс генерации в процентах"""
        phase5 = st.session_state.phase5
        if not phase5['generation_queue']:
            return 0

        return int((phase5['current_index'] / len(phase5['generation_queue'])) * 100)


# --- Компоненты интерфейса ---
class Phase5UIComponents:
    """Компоненты пользовательского интерфейса фазы 5"""

    @staticmethod
    def show_prompts_selection(data_manager: Phase5DataManager):
        st.header("📋 Выбор промптов для генерации")

        # Логируем состояние перед отображением
        data_manager._log_prompts_stats("Перед отображением выбора промптов")

        init_phase5_structure()

        # ✅ ЕСЛИ БЫЛА ЗАГРУЗКА ИЗ ФАЗЫ 4 - НЕ ЗАГРУЖАЕМ ИЗ ФАЙЛА
        if st.session_state.get('_phase5_loaded_from_phase4', False):
            print("⏭️ Пропускаем force_load_phase5_from_file - данные загружены из фазы 4")
        else:
            force_load_phase5_from_file()

        if 'phase5_prompts' not in st.session_state or not st.session_state.phase5_prompts:
            st.info("Нет загруженных промптов. Загрузите данные из фазы 4.")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Загрузить промпты из фазы 4", key="load_prompts_btn"):
                    print("\n" + "=" * 80)
                    print("🔥 КНОПКА НАЖАТА - ПОЛНАЯ ОЧИСТКА ВСЕХ ДАННЫХ PHASE 5")
                    print("=" * 80)

                    # ===== 1. ОЧИЩАЕМ session_state ПОЛНОСТЬЮ =====
                    keys_to_remove = []
                    for key in list(st.session_state.keys()):
                        if key.startswith('phase5') or key == 'temp_selections' or key == '_phase5_loaded_from_phase4':
                            keys_to_remove.append(key)

                    for key in keys_to_remove:
                        del st.session_state[key]
                        print(f"   🗑️ Удален ключ: {key}")

                    # ===== 2. ОЧИЩАЕМ app_data =====
                    if 'app_data' in st.session_state:
                        if 'phase5' in st.session_state.app_data:
                            del st.session_state.app_data['phase5']
                            print("   🗑️ Удален app_data.phase5")
                        if 'phase5_results' in st.session_state.app_data:
                            del st.session_state.app_data['phase5_results']
                            print("   🗑️ Удален app_data.phase5_results")
                        if 'phase5_completed' in st.session_state.app_data:
                            del st.session_state.app_data['phase5_completed']
                            print("   🗑️ Удален app_data.phase5_completed")
                        if 'phase5_settings' in st.session_state.app_data:
                            del st.session_state.app_data['phase5_settings']
                            print("   🗑️ Удален app_data.phase5_settings")
                        st.session_state.app_data['phase5_completed'] = False

                    # ===== 3. ОЧИЩАЕМ ФАЙЛ =====
                    project_file = data_manager._get_project_file()
                    if project_file and project_file.exists():
                        try:
                            import json
                            with open(project_file, 'r', encoding='utf-8') as f:
                                file_data = json.load(f)

                            # Удаляем ВСЕ ключи phase5
                            if 'app_data' in file_data:
                                keys_to_remove_from_file = ['phase5', 'phase5_results', 'phase5_completed',
                                                            'phase5_settings']
                                for key in keys_to_remove_from_file:
                                    if key in file_data['app_data']:
                                        del file_data['app_data'][key]
                                        print(f"   🗑️ Удален из файла: app_data.{key}")

                            if 'phase5_results' in file_data:
                                del file_data['phase5_results']
                                print("   🗑️ Удален из файла: phase5_results")

                            file_data['updated_at'] = datetime.now().isoformat()

                            with open(project_file, 'w', encoding='utf-8') as f:
                                json.dump(file_data, f, ensure_ascii=False, indent=2)
                            print(f"   ✅ Файл очищен: {project_file}")
                        except Exception as e:
                            print(f"   ❌ Ошибка очистки файла: {e}")

                    # ===== 4. ПЕРЕСОЗДАЕМ СТРУКТУРУ =====
                    st.session_state.phase5 = {
                        'generation_status': 'idle',
                        'selected_prompt_ids': [],
                        'results': {},
                        'statistics': {
                            'total': 0,
                            'selected': 0,
                            'completed': 0,
                            'success': 0,
                            'error': 0,
                            'pending': 0
                        },
                        'generation_settings': {
                            'provider': 'agentplatform',
                            'temperature': 0.7,
                            'max_tokens': 2000,
                            'retry_count': 3,
                            'delay_between_requests': 2.0
                        },
                        'generation_queue': [],
                        'current_index': 0,
                        'generation_running': False,
                        'initialized': True,
                        'phase_completed': False
                    }
                    st.session_state.phase5_prompts = []
                    st.session_state.temp_selections = {}
                    st.session_state._phase5_loaded_from_phase4 = True
                    print("   ✅ Создана новая пустая структура phase5")

                    # ===== 5. ЗАГРУЖАЕМ ПРОМПТЫ ИЗ ФАЗЫ 4 =====
                    print("   📥 Загрузка промптов из фазы 4...")
                    data_manager.load_prompts_from_phase4()

                    # ===== 6. СОХРАНЯЕМ В ФАЙЛ =====
                    data_manager.save_to_app_data()
                    print("   💾 Данные сохранены в файл")

                    print("=" * 80)
                    print("✅ ВСЕ ДАННЫЕ PHASE 5 ПОЛНОСТЬЮ ОЧИЩЕНЫ И ПЕРЕЗАГРУЖЕНЫ!")
                    print("=" * 80 + "\n")

                    st.success("✅ Данные фазы 5 полностью очищены и загружены из фазы 4!")
                    st.rerun()

            with col2:
                if st.button("🗑️ Сбросить все данные фазы 5", key="reset_all_data_btn"):
                    print("\n🔍 КНОПКА 'СБРОСИТЬ ВСЕ ДАННЫЕ' НАЖАТА")
                    data_manager.reset_session_data()
                    st.session_state.temp_selections = {}
                    st.session_state._phase5_loaded_from_phase4 = False
                    print("   ✅ Все данные фазы 5 сброшены")
                    st.success("✅ Все данные фазы 5 сброшены!")
                    st.rerun()
            return

        # ===== ДАЛЬШЕ КОД ТОЛЬКО ЕСЛИ ЕСТЬ ПРОМПТЫ =====

        # === ИНИЦИАЛИЗАЦИЯ СТРУКТУРЫ phase5 ===
        if 'phase5' not in st.session_state:
            st.session_state.phase5 = {}

        phase5 = st.session_state.phase5

        # Критические ключи, которые должны быть всегда
        if 'selected_prompt_ids' not in phase5:
            phase5['selected_prompt_ids'] = []
        if 'results' not in phase5:
            phase5['results'] = {}
        if 'statistics' not in phase5:
            phase5['statistics'] = {
                'total': 0,
                'success': 0,
                'error': 0,
                'selected': 0
            }

        prompts = st.session_state.phase5_prompts
        print(f"\n📋 show_prompts_selection: загружено {len(prompts)} промптов")

        # ===== ФИКС: ИНИЦИАЛИЗИРУЕМ selected_prompt_ids =====
        if not st.session_state.phase5.get('selected_prompt_ids') and 'temp_selections' in st.session_state:
            selected_ids = [pid for pid, val in st.session_state.temp_selections.items() if val]
            if selected_ids:
                st.session_state.phase5['selected_prompt_ids'] = selected_ids
                st.session_state.phase5['statistics']['selected'] = len(selected_ids)
                data_manager._update_statistics()
                print(f"✅ Восстановлены selected_prompt_ids из temp_selections: {len(selected_ids)}")

        if not st.session_state.phase5.get('selected_prompt_ids'):
            all_ids = [p.get('phase5_id') for p in prompts if p.get('phase5_id')]
            if all_ids:
                st.session_state.phase5['selected_prompt_ids'] = all_ids
                st.session_state.phase5['statistics']['selected'] = len(all_ids)
                if 'temp_selections' not in st.session_state:
                    st.session_state.temp_selections = {}
                for pid in all_ids:
                    st.session_state.temp_selections[pid] = True
                data_manager._update_statistics()
                print(f"✅ ВЫБРАНЫ ВСЕ ПРОМПТЫ: {len(all_ids)}")

        for i, p in enumerate(prompts[:5]):
            print(f"   {i}: phase5_id={p.get('phase5_id')}, char={p.get('characteristic_name', '')}")
        if len(prompts) > 5:
            print(f"   ... и ещё {len(prompts) - 5}")

        # Фильтры
        st.subheader("Фильтры")

        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_type = st.selectbox(
                "Тип:",
                ["Все", "regular", "unique", "other"],
                key="filter_prompt_type_phase5"
            )

        with col_f2:
            char_names = sorted(list(set(
                p.get('characteristic_name', '') for p in prompts
                if p.get('characteristic_name')
            )))
            filter_options = ["Все характеристики"] + char_names
            filter_characteristic = st.selectbox(
                "Характеристика:",
                filter_options,
                key="filter_characteristic_phase5"
            )

        with col_f3:
            filter_status = st.selectbox(
                "Статус генерации:",
                ["Все", "ожидает", "успешно", "ошибка"],
                key="filter_status_phase5"
            )

        # Применяем фильтры
        filtered_prompts = prompts

        if filter_type != "Все":
            filtered_prompts = [
                p for p in filtered_prompts
                if p.get('type') == filter_type or p.get('block_type') == filter_type
            ]

        if filter_characteristic != "Все характеристики":
            filtered_prompts = [
                p for p in filtered_prompts
                if p.get('characteristic_name') == filter_characteristic
            ]

        if filter_status != "Все":
            status_map = {
                "ожидает": "pending",
                "успешно": "success",
                "ошибка": "error"
            }
            target_status = status_map.get(filter_status)
            filtered_prompts = [
                p for p in filtered_prompts
                if st.session_state.phase5['results'].get(p.get('phase5_id'), {}).get('status') == target_status
            ]

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            if st.button("✅ Выбрать все", key="select_all_prompts_btn"):
                filtered_ids = [p.get('phase5_id') for p in filtered_prompts if p.get('phase5_id')]
                for pid in filtered_ids:
                    if pid not in st.session_state.phase5['selected_prompt_ids']:
                        st.session_state.phase5['selected_prompt_ids'].append(pid)
                for pid in filtered_ids:
                    st.session_state.temp_selections[pid] = True
                st.session_state.phase5['statistics']['selected'] = len(st.session_state.phase5['selected_prompt_ids'])
                print(f"✅ Выбрано все {len(filtered_ids)} промптов")
                st.rerun()

        with col2:
            if st.button("❌ Снять все", key="deselect_all_prompts_btn"):
                filtered_ids = [p.get('phase5_id') for p in filtered_prompts if p.get('phase5_id')]
                st.session_state.phase5['selected_prompt_ids'] = [
                    pid for pid in st.session_state.phase5['selected_prompt_ids']
                    if pid not in filtered_ids
                ]
                for pid in filtered_ids:
                    st.session_state.temp_selections[pid] = False
                st.session_state.phase5['statistics']['selected'] = len(st.session_state.phase5['selected_prompt_ids'])
                print(f"❌ Снято все {len(filtered_ids)} промптов")
                st.rerun()

        with col3:
            if st.button("🗑️ Очистить всё", key="clear_selection_results_btn"):
                print("🔍 КНОПКА 'ОЧИСТИТЬ ВСЁ' НАЖАТА")
                data_manager.reset_generation()
                st.session_state.temp_selections = {}
                print("   ✅ Все результаты очищены")
                st.rerun()

        with col4:
            selected_count = st.session_state.phase5['statistics']['selected']
            total_count = st.session_state.phase5['statistics']['total']
            filtered_count = len(filtered_prompts)
            selected_in_filter = sum(1 for p in filtered_prompts
                                     if p.get('phase5_id') in st.session_state.phase5['selected_prompt_ids'])
            st.metric("Выбрано", f"{selected_count}/{total_count}")
            st.caption(f"в фильтре: {selected_in_filter}/{filtered_count}")

        # Таблица промптов с редактируемыми чекбоксами
        if filtered_prompts:
            if 'temp_selections' not in st.session_state:
                st.session_state.temp_selections = {}

            if st.session_state.get('last_filter_hash') != hash(
                    str(filter_type) + filter_characteristic + filter_status):
                st.session_state.temp_selections = {}
                st.session_state.last_filter_hash = hash(str(filter_type) + filter_characteristic + filter_status)

            for prompt in filtered_prompts:
                prompt_id = prompt.get('phase5_id')
                if prompt_id not in st.session_state.temp_selections:
                    st.session_state.temp_selections[prompt_id] = prompt_id in st.session_state.phase5[
                        'selected_prompt_ids']

            table_data = []
            for prompt in filtered_prompts:
                prompt_id = prompt.get('phase5_id')

                if prompt_id is None:
                    char_name = prompt.get('characteristic_name', 'unknown')
                    value = prompt.get('value', '')
                    block_name = prompt.get('block_name', '')
                    prompt_num = prompt.get('prompt_num', 1)
                    prompt_id = f"temp_{char_name}_{value}_{block_name}_{prompt_num}"
                    prompt['phase5_id'] = prompt_id

                result = st.session_state.phase5['results'].get(prompt_id, {})

                display_id = prompt_id[:20] + "..." if len(prompt_id) > 20 else prompt_id

                table_data.append({
                    "Выбрать": st.session_state.temp_selections.get(prompt_id, False),
                    "ID": display_id,
                    "Тип": prompt.get('type', prompt.get('block_type', 'unknown')),
                    "Характеристика": prompt.get('characteristic_name', prompt.get('block_name', 'N/A')),
                    "Значение": prompt.get('value', 'N/A'),
                    "Промпт №": prompt.get('prompt_num', 1),
                    "Статус": result.get('status', 'pending'),
                    "Токенов": result.get('tokens_used', 0),
                    "prompt_id": prompt_id
                })

            df = pd.DataFrame(table_data)

            column_config = {
                "Выбрать": st.column_config.CheckboxColumn(
                    "Выбрать",
                    help="Включить в генерацию",
                    default=False,
                ),
                "ID": st.column_config.TextColumn("ID", width="small"),
                "Тип": st.column_config.TextColumn("Тип", width="small"),
                "Характеристика": st.column_config.TextColumn("Характеристика", width="medium"),
                "Значение": st.column_config.TextColumn("Значение", width="medium"),
                "Промпт №": st.column_config.NumberColumn("Промпт №", width="small"),
                "Статус": st.column_config.TextColumn("Статус", width="small"),
                "Токенов": st.column_config.NumberColumn("Токенов", width="small"),
                "prompt_id": st.column_config.Column(disabled=True, width=None)
            }

            edited_df = st.data_editor(
                df,
                column_config=column_config,
                hide_index=True,
                disabled=["ID", "Тип", "Характеристика", "Значение", "Промпт №", "Статус", "Токенов", "prompt_id"],
                key="prompts_selection_editor_phase5"
            )

            current_selected = set(st.session_state.phase5.get('selected_prompt_ids', []))
            new_selected = set()

            for idx, row in edited_df.iterrows():
                prompt_id = row['prompt_id']
                is_selected = row['Выбрать']

                if prompt_id and is_selected:
                    new_selected.add(prompt_id)
                    st.session_state.temp_selections[prompt_id] = True
                elif prompt_id and not is_selected:
                    st.session_state.temp_selections[prompt_id] = False

            if new_selected != current_selected:
                st.session_state.phase5['selected_prompt_ids'] = list(new_selected)
                st.session_state.phase5['statistics']['selected'] = len(new_selected)
                data_manager._update_statistics()
                data_manager.save_to_app_data()
                print(f"✅ Обновлен выбор: {len(new_selected)} промптов")

            st.caption("💡 Кликните на чекбоксы в колонке 'Выбрать', чтобы включить/исключить промпты из генерации")

    @staticmethod
    def show_generation_settings():
        """Показать настройки генерации"""
        st.header("⚙️ Настройки генерации")

        with st.expander("Параметры AI", expanded=True):
            col1, col2 = st.columns(2)

            with col1:
                # Расширяем список провайдеров
                # Новый список провайдеров - только agentplatform и deepseek
                available_providers = ["agentplatform", "deepseek"]
                provider_labels = {
                    "agentplatform": "AgentPlatform (OpenAI/Anthropic/Google/Mistral и др.)",
                    "deepseek": "DeepSeek (прямой доступ)"
                }

                current_provider = st.session_state.phase5['generation_settings'].get('provider', 'deepseek')

                # Определяем индекс для выбора
                if current_provider in ["agentplatform", "deepseek"]:
                    default_index = available_providers.index(current_provider)
                else:
                    # Если сохранен старый провайдер, по умолчанию выбираем agentplatform
                    default_index = 0

                provider = st.selectbox(
                    "Провайдер AI:",
                    available_providers,
                    format_func=lambda x: provider_labels.get(x, x),
                    index=default_index,
                    key="ai_provider_select_phase5"
                )

                temperature = st.slider(
                    "Temperature:",
                    min_value=0.0,
                    max_value=2.0,
                    value=st.session_state.phase5['generation_settings'].get('temperature', 0.7),
                    step=0.1,
                    key="ai_temperature_phase5"
                )

            with col2:
                # Динамический max_tokens в зависимости от провайдера (Gemini поддерживают больше)
                max_tokens_default = 2000
                max_tokens_max = 16384 if "gemini" in provider else 8000
                max_tokens = st.number_input(
                    "Max Tokens:",
                    min_value=100,
                    max_value=max_tokens_max,
                    value=st.session_state.phase5['generation_settings'].get('max_tokens', max_tokens_default),
                    key="ai_max_tokens_phase5"
                )

                retry_count = st.number_input(
                    "Повторных попыток при ошибке:",
                    min_value=1,
                    max_value=10,
                    value=st.session_state.phase5['generation_settings'].get('retry_count', 3),
                    key="ai_retry_count_phase5"
                )

            # Общая задержка
            delay = st.slider(
                "Задержка между запросами (сек):",
                min_value=0.5,
                max_value=10.0,
                value=st.session_state.phase5['generation_settings'].get('delay_between_requests', 2.0),
                step=0.5,
                key="ai_delay_phase5"
            )

            # Дополнительные предупреждения / поля в зависимости от провайдера
            if provider == "deepseek":
                st.info("ℹ️ Прямой доступ к DeepSeek API. Убедитесь, что ключ настроен в конфигурации AI.")
            else:  # agentplatform
                st.info("ℹ️ Единый ключ AgentPlatform для всех моделей. Поддерживает OpenAI, Anthropic, Google Gemini, Mistral и другие.")

            # Кнопка сохранения
            if st.button("💾 Сохранить настройки", key="save_settings_phase5_btn"):
                st.session_state.phase5['generation_settings'].update({
                    'provider': provider,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'retry_count': retry_count,
                    'delay_between_requests': delay
                })
                st.success("Настройки сохранены!")

    @staticmethod

    def show_generation_control(generation_manager: GenerationManager, data_manager: Phase5DataManager):
        init_phase5_structure()

        # ✅ ПРИНУДИТЕЛЬНО ЗАГРУЖАЕМ ДАННЫЕ ИЗ ФАЙЛА
        force_load_phase5_from_file()

        st.header("🚀 Управление генерацией")

        status = st.session_state.phase5.get('generation_status', 'idle')
        stats = st.session_state.phase5.get('statistics', {})
        phase5 = st.session_state.phase5

        # Статистика
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        with col_s1: st.metric("Выбрано", stats['selected'])
        with col_s2: st.metric("Успешно", stats['success'])
        with col_s3: st.metric("Ошибки", stats['error'])
        with col_s4: st.metric("Ожидают", stats['pending'])

        # Прогресс и статус
        if status in ['running', 'paused']:
            current = phase5['current_index']
            total = len(phase5['generation_queue'])

            if total > 0:
                progress = current / total
                st.progress(progress)

                # Показываем примерный текущий промпт (немного вперёд)
                look_ahead = min(current + 3, total - 1)
                if look_ahead < total:
                    pid = phase5['generation_queue'][look_ahead]
                    p = data_manager.get_prompt_by_id(pid)
                    if p:
                        char_name = p.get('characteristic_name') or p.get('block_name', '—')
                        value = p.get('value', '—')[:35]
                        num = p.get('prompt_num', '—')
                        st.caption(f"≈ сейчас обрабатывается: **{char_name} → {value}** (промпт {num})")

                # ETA (грубо)
                if current >= 5 and 'generation_start_time' in phase5:
                    try:
                        start = datetime.fromisoformat(phase5['generation_start_time'])
                        elapsed = (datetime.now() - start).total_seconds()
                        if elapsed > 0 and current > 0:
                            per_prompt = elapsed / current
                            remaining_sec = (total - current) * per_prompt
                            min_left = int(remaining_sec // 60)
                            sec_left = int(remaining_sec % 60)
                            st.caption(f"Осталось ≈ {min_left} мин {sec_left} сек")
                    except:
                        pass

                st.caption(f"{current} / {total} • {int(progress*100)}%")

        if status == 'running':
            st.info("Генерация идёт батчами по 10 промптов…")
        elif status == 'paused':
            st.warning("⏸️ Генерация приостановлена")
        elif status == 'completed':
            st.success("Генерация завершена!")
        elif status == 'stopped':
            st.warning("Генерация остановлена пользователем")

        # Кнопки управления
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if status in ['idle', 'paused', 'stopped', 'completed']:
                if st.button("🚀 Запустить", type="primary"):
                    # ✅ ПРИНУДИТЕЛЬНО СБРАСЫВАЕМ СТАТУС ПЕРЕД ЗАПУСКОМ
                    st.session_state.phase5['generation_status'] = 'idle'
                    st.session_state.phase5['generation_running'] = False
                    st.session_state.phase5['phase_completed'] = False
                    generation_manager.start_generation()
                    st.rerun()

        with col2:
            if status == 'running':
                if st.button("⏸️ Пауза"):
                    generation_manager.pause_generation()
                    st.rerun()

        with col3:
            if status == 'paused':
                if st.button("▶️ Продолжить"):
                    generation_manager.resume_generation()
                    st.rerun()

        with col4:
            if status in ['running', 'paused']:
                if st.button("⏹️ Остановить"):
                    generation_manager.stop_generation()
                    st.rerun()

    @staticmethod
    def show_phase_completion(generation_manager, data_manager):
        """Показать панель завершения фазы 5"""
        st.header("✅ Завершение фазы 5")

        stats = st.session_state.phase5['statistics']

        # Проверяем условия для завершения
        completion_conditions = [
            (stats['selected'] > 0, f"Выбрано промптов: {stats['selected']}/{stats['total']}"),
            (stats['completed'] == stats['selected'], f"Сгенерировано: {stats['completed']}/{stats['selected']}"),
            (stats['error'] == 0 or st.checkbox("Завершить даже с ошибками"),
             f"Ошибки: {stats['error']} (можно игнорировать)")
        ]

        st.write("**Условия завершения:**")
        for condition, description in completion_conditions:
            status = "✅" if condition else "❌"
            st.write(f"{status} {description}")

        # Кнопка завершения
        can_complete = all([cond for cond, _ in completion_conditions[:-1]])  # игнорируем последнее если чекбокс

        if st.button("🏁 Завершить фазу 5 и перейти к фазе 6",
                     type="primary",
                     disabled=not can_complete,
                     key="complete_phase5_btn"):

            if data_manager.complete_phase5_and_prepare_phase6():
                # Меняем текущую фазу в основном приложении
                st.session_state.current_phase = 6
                st.rerun()

    @staticmethod
    def show_results(data_manager: Phase5DataManager):
        st.header("📊 Результаты генерации")

        # ✅ ПРИНУДИТЕЛЬНО ЗАГРУЖАЕМ ДАННЫЕ ИЗ ФАЙЛА
        force_load_phase5_from_file()

        results = st.session_state.phase5.get('results', {})
        stats = st.session_state.phase5.get('statistics', {})

        # ✅ ОБНОВЛЯЕМ СТАТИСТИКУ
        data_manager._update_statistics()

        if stats.get('completed', 0) == 0:
            st.info("Результаты генерации появятся здесь после запуска генерации.")
            return

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            result_filter = st.selectbox("Фильтр по статусу:", ["Все", "Успешно", "Ошибки"], key="result_filter_phase5")
        with col_f2:
            group_by = st.selectbox("Группировать по:", ["Нет", "Характеристике", "Типу", "Статусу"],
                                    key="result_group_by_phase5")

        filtered_results = []
        for prompt_id, result in results.items():
            if not result.get('ai_response') and result.get('status') == 'pending':
                continue
            if result_filter == "Успешно" and result.get('status') != 'success':
                continue
            elif result_filter == "Ошибки" and result.get('status') != 'error':
                continue
            prompt = data_manager.get_prompt_by_id(prompt_id)
            filtered_results.append({'prompt_id': prompt_id, 'result': result, 'prompt': prompt})

        if group_by != "Нет":
            groups = {}
            for item in filtered_results:
                if group_by == "Характеристике":
                    key = item['prompt'].get('characteristic_name', item['prompt'].get('block_name', 'Другие'))
                elif group_by == "Типу":
                    key = item['prompt'].get('type', item['prompt'].get('block_type', 'unknown'))
                elif group_by == "Статусу":
                    key = item['result'].get('status', 'unknown')
                groups.setdefault(key, []).append(item)

            for group_name, group_items in groups.items():
                with st.expander(f"{group_name} ({len(group_items)} результатов)", expanded=False):
                    Phase5UIComponents._show_results_table(group_items, data_manager)
        else:
            Phase5UIComponents._show_results_table(filtered_results, data_manager)

        # ВЫЗОВ УДАЛЁН: Phase5UIComponents._show_export_options(data_manager)

    @staticmethod
    def _show_results_table(results_items, data_manager):
        """Показать таблицу результатов"""
        for idx, item in enumerate(results_items):  # Исправлено: добавлен idx
            result = item['result']
            prompt = item['prompt']

            # Карточка результата
            if result['status'] == 'success':
                card_class = "result-card"
                status_badge = "✅ Успешно"
            elif result['status'] == 'error':
                card_class = "error-card"
                status_badge = "❌ Ошибка"
            else:
                card_class = "pending-card"
                status_badge = "⏳ Ожидает"

            st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)

            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                # Информация о промпте
                if prompt:
                    if 'characteristic_name' in prompt:
                        st.write(f"**{prompt['characteristic_name']}** = {prompt.get('value', '')}")
                    else:
                        st.write(f"**Блок:** {prompt.get('block_name', '')}")

                # Модель и токены
                st.caption(f"Модель: {result.get('model', 'N/A')} | "
                           f"Токенов: {result.get('tokens_used', 0)}")

            with col2:
                st.write(status_badge)

            with col3:
                # Кнопки действий
                if result['status'] == 'success':
                    if st.button("👁️ Просмотр", key=f"view_{item['prompt_id']}_{idx}",
                                 use_container_width=False):
                        st.session_state[f"show_preview_{item['prompt_id']}"] = True

                if result['status'] == 'error':
                    if st.button("🔄 Повторить", key=f"retry_{item['prompt_id']}_{idx}",
                                 use_container_width=False):
                        # Сбросить статус для повторной генерации
                        result.update({
                            'status': 'pending',
                            'error_message': None
                        })
                        data_manager._update_statistics()
                        st.rerun()

            # Превью текста (если открыто)
            if st.session_state.get(f"show_preview_{item['prompt_id']}", False):
                st.markdown("---")
                st.write("**Сгенерированный текст:**")

                # Редактируемое поле для текста
                edited_text = st.text_area(
                    "Текст (можно редактировать):",
                    value=result.get('edited_text') or result.get('ai_response', ''),
                    height=150,
                    key=f"edit_{item['prompt_id']}_{idx}"
                )

                # Сохранить изменения
                if edited_text != result.get('edited_text'):
                    result['edited_text'] = edited_text
                    st.success("Изменения сохранены!")

                col_save, col_close = st.columns(2)
                with col_close:
                    if st.button("Закрыть", key=f"close_{item['prompt_id']}_{idx}",
                                 use_container_width=False):
                        st.session_state[f"show_preview_{item['prompt_id']}"] = False
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    @staticmethod
    def _show_export_options(data_manager):
        """Показать опции экспорта"""
        st.subheader("💾 Экспорт результатов")

        col1, col2, col3 = st.columns(3)

        with col1:
            export_format = st.selectbox(
                "Формат экспорта:",
                ["json", "txt", "excel"],  # ← добавлено "excel"
                key="export_format_select_phase5"
            )

        with col2:
            include_edited = st.checkbox(
                "Включить отредактированные тексты",
                value=True,
                key="include_edited_phase5"
            )

        with col3:
            if st.button("📥 Экспортировать результаты", type="primary",
                         key="export_results_phase5_btn"):
                with st.spinner("Экспорт..."):
                    filename = data_manager.save_results_to_file(export_format)
                    if filename:
                        st.success(f"✅ Результаты экспортированы в файл: {filename}")

                        # Предложить скачать
                        if export_format == 'json':
                            with open(filename, 'r', encoding='utf-8') as f:
                                data = f.read()
                            st.download_button(
                                label="Скачать JSON",
                                data=data,
                                file_name=filename,
                                mime="application/json",
                                key="download_json_phase5"
                            )
                        elif export_format == 'txt':
                            with open(filename, 'r', encoding='utf-8') as f:
                                data = f.read()
                            st.download_button(
                                label="Скачать TXT",
                                data=data,
                                file_name=filename,
                                mime="text/plain",
                                key="download_txt_phase5"
                            )
                        elif export_format == 'excel':  # ← новый блок
                            with open(filename, 'rb') as f:
                                data = f.read()
                            st.download_button(
                                label="Скачать Excel",
                                data=data,
                                file_name=filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="download_excel_phase5"
                            )

                    else:
                        st.error("Ошибка при экспорте")

# phase5.py - добавить в конец файла
# phase5.py - добавить в конец файла
def debug_phase5_file(project_file: Path):
    """Отладочная функция для проверки файла"""
    import json

    if not project_file.exists():
        print(f"❌ Файл не существует: {project_file}")
        return

    with open(project_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"\n{'='*60}")
    print(f"🔍 ОТЛАДКА PHASE5: {project_file.name}")
    print(f"{'='*60}")

    app_data = data.get('app_data', {})

    # Проверяем все возможные места
    locations = [
        ('app_data.phase5.results', app_data.get('phase5', {}).get('results', {})),
        ('app_data.phase5_results', app_data.get('phase5_results', {})),
        ('phase5_results', data.get('phase5_results', {})),
        ('app_data.phase5', app_data.get('phase5', {})),
    ]

    for name, value in locations:
        if isinstance(value, dict):
            print(f"   {name}: {len(value)}")
        elif isinstance(value, list):
            print(f"   {name}: {len(value)} (list)")
        else:
            print(f"   {name}: {type(value).__name__}")

    # Проверяем статистику
    stats = app_data.get('phase5', {}).get('statistics', {})
    print(f"\n   Статистика: {stats}")

    print(f"{'='*60}\n")


# phase5.py - добавить функцию принудительной загрузки

def force_load_phase5_from_file(context=None):
    """Принудительно загружает данные фазы 5 из файла"""
    from pathlib import Path
    import json

    # Получаем путь к проекту
    ctx_data = _get_context_data(context, st.session_state)

    if ctx_data['has_context'] and context is not None:
        user_id = context.user_id
        project_id = context.project_id
        site = context.site_name
        domain = context.domain_name
    else:
        user_id = st.session_state.get('user_id')
        project_id = st.session_state.get('current_project_id')
        site = st.session_state.get('current_site', 'steelborg')
        domain = st.session_state.get('current_domain', 'default')

    if not user_id or not project_id:
        print("❌ Нет данных для загрузки phase5")
        return False

    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

    if not project_file.exists():
        print(f"❌ Файл не существует: {project_file}")
        return False

    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        app_data = data.get('app_data', {})
        phase5_data = app_data.get('phase5', {})
        results = phase5_data.get('results', {})

        # ✅ ЗАГРУЖАЕМ ПРОМПТЫ ИЗ PHASE4
        phase4_data = app_data.get('phase4', {})
        prompts_from_phase4 = phase4_data.get('prompts', [])

        if prompts_from_phase4 and (not st.session_state.phase5_prompts or len(st.session_state.phase5_prompts) != len(prompts_from_phase4)):
            loaded_prompts = []
            for i, prompt in enumerate(prompts_from_phase4):
                if 'characteristic_id' in prompt:
                    prompt_id = f"char_{prompt['characteristic_id']}_{prompt.get('value', '')}_{prompt.get('prompt_num', i)}"
                elif 'block_id' in prompt:
                    prompt_id = f"block_{prompt['block_id']}_{prompt.get('prompt_num', i)}"
                elif 'characteristic_name' in prompt:
                    prompt_id = f"char_{prompt['characteristic_name']}_{prompt.get('value', '')}_{prompt.get('prompt_num', i)}"
                else:
                    prompt_id = f"prompt_{i}"
                prompt['phase5_id'] = prompt_id
                loaded_prompts.append(prompt)

            st.session_state.phase5_prompts = loaded_prompts
            print(f"✅ Загружены промпты из phase4: {len(loaded_prompts)}")

        # Обновляем session_state
        if 'phase5' not in st.session_state:
            st.session_state.phase5 = {}

        # ✅ НЕ ПЕРЕЗАПИСЫВАЕМ СУЩЕСТВУЮЩИЕ РЕЗУЛЬТАТЫ
        existing_results = st.session_state.phase5.get('results', {})

        # Добавляем результаты из файла
        for pid, result in results.items():
            if pid not in existing_results:
                existing_results[pid] = result

        st.session_state.phase5['results'] = existing_results

        # ✅ СОЗДАЕМ НЕДОСТАЮЩИЕ ЗАПИСИ ДЛЯ ВСЕХ ПРОМПТОВ
        prompts = st.session_state.phase5_prompts if 'phase5_prompts' in st.session_state else []
        if prompts:
            missing_count = 0
            for p in prompts:
                pid = p.get('phase5_id')
                if pid and pid not in st.session_state.phase5['results']:
                    st.session_state.phase5['results'][pid] = {
                        'prompt_id': pid,
                        'prompt': p.get('prompt', ''),
                        'ai_response': '',
                        'status': 'pending',
                        'model': '',
                        'provider': '',
                        'tokens_used': 0,
                        'generated_at': None,
                        'error_message': None,
                        'edited_text': '',
                        'characteristic_name': p.get('characteristic_name', ''),
                        'characteristic_value': p.get('value', ''),
                        'block_name': p.get('block_name', ''),
                        'prompt_num': p.get('prompt_num', 1),
                        'type': p.get('type', p.get('block_type', 'unknown'))
                    }
                    missing_count += 1
                    print(f"   ✅ СОЗДАН НЕДОСТАЮЩИЙ РЕЗУЛЬТАТ для: {pid}")

            if missing_count > 0:
                print(f"   ✅ СОЗДАНО {missing_count} НЕДОСТАЮЩИХ РЕЗУЛЬТАТОВ")

        # ✅ ОБНОВЛЯЕМ СТАТИСТИКУ - ИСПРАВЛЕНО: НЕ ИСПОЛЬЗУЕМ data_manager
        total_prompts = len(st.session_state.phase5_prompts) if 'phase5_prompts' in st.session_state else 0
        current_results = st.session_state.phase5['results']

        success = sum(1 for r in current_results.values() if r.get('status') == 'success')
        error = sum(1 for r in current_results.values() if r.get('status') == 'error')
        completed = success + error
        pending = total_prompts - completed

        st.session_state.phase5['statistics'] = {
            'total': total_prompts,
            'success': success,
            'error': error,
            'completed': completed,
            'pending': pending,
            'selected': st.session_state.phase5.get('statistics', {}).get('selected', total_prompts)  # ← ИСПРАВЛЕНО
        }

        # ✅ ВЫБИРАЕМ ВСЕ ПРОМПТЫ
        prompts = st.session_state.phase5_prompts if 'phase5_prompts' in st.session_state else []
        if prompts:
            all_ids = [p.get('phase5_id') for p in prompts if p.get('phase5_id')]
            if not st.session_state.phase5.get('selected_prompt_ids'):
                st.session_state.phase5['selected_prompt_ids'] = all_ids
                st.session_state.phase5['statistics']['selected'] = len(all_ids)
                if 'temp_selections' not in st.session_state:
                    st.session_state.temp_selections = {}
                for pid in all_ids:
                    st.session_state.temp_selections[pid] = True
                print(f"✅ ВЫБРАНЫ ВСЕ ПРОМПТЫ (force_load): {len(all_ids)}")

        # Если есть статус завершения
        if phase5_data.get('phase_completed', False):
            st.session_state.phase5['generation_status'] = 'completed'
            st.session_state.phase5_completed = True

        return True

    except Exception as e:
        print(f"❌ Ошибка загрузки phase5: {e}")
        import traceback
        traceback.print_exc()
        return False
def auto_generate_all_texts(app_state=None, context=None):
    """
    АВТОМАТИЧЕСКАЯ ГЕНЕРАЦИЯ ТЕКСТОВ - БАТЧЕВАЯ ВЕРСИЯ
    Обрабатывает по BATCH_SIZE промптов за раз
    """
    from pathlib import Path
    import json
    from datetime import datetime
    import time

    BATCH_SIZE = 10

    print("=" * 60)
    print("🔄 auto_generate_all_texts STARTED (BATCH MODE)")
    print("=" * 60)

    # ========== 1. ОПРЕДЕЛЯЕМ ТЕКУЩИЙ ПРОЕКТ ==========
    ctx_data = _get_context_data(context, st.session_state)

    if ctx_data['has_context'] and context is not None:
        user_id = context.user_id
        project_id = context.project_id
        site = context.site_name
        domain = context.domain_name
        print(f"📌 Используем контекст: user={user_id}, project={project_id}, site={site}, domain={domain}")
    else:
        user_id = st.session_state.get('user_id')
        project_id = st.session_state.get('current_project_id')
        site = st.session_state.get('current_site', 'steelborg')
        domain = st.session_state.get('current_domain', 'default')
        print(f"📌 Используем session_state: user={user_id}, project={project_id}")

    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

    print(f"📁 Проект: {project_file}")

    if not project_file.exists():
        return {
            'success': False,
            'message': f'❌ Файл проекта не найден',
            'count': 0,
            'errors': 0
        }

    # ========== 2. ЗАГРУЖАЕМ ПРОМПТЫ ИЗ ФАЙЛА ==========
    prompts = []

    # ✅ ПРЯМО БЕРЕМ ИЗ phase4.prompts
    with open(project_file, 'r', encoding='utf-8') as f:
        file_data = json.load(f)
        app_data = file_data.get('app_data', {})
        phase4 = app_data.get('phase4', {})
        prompts = phase4.get('prompts', [])

        if prompts:
            print(f"   ✅ Загружено {len(prompts)} готовых промптов из phase4.prompts")

    # ❌ НЕ ПЫТАЙТЕСЬ ПЕРЕСЧИТЫВАТЬ ИХ КОЛИЧЕСТВО!
    # Просто используйте то, что есть

    if not prompts:
        return {'success': False, 'message': '❌ Нет готовых промптов в phase4.prompts', 'count': 0, 'errors': 0}

        print(f"📝 Итого загружено {len(prompts)} промптов")
        print(f"{'='*60}\n")



    # ========== 3. ЗАГРУЖАЕМ СУЩЕСТВУЮЩИЕ РЕЗУЛЬТАТЫ ==========
    existing_results = {}
    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            file_data = json.load(f)
            existing_results = file_data.get('app_data', {}).get('phase5', {}).get('results', {})
            print(f"📂 Существующие результаты: {len(existing_results)}")
    except:
        pass

    # ========== 4. НАСТРОЙКИ AI ==========
    # ✅ Получаем user_id для APIKeyManager, НО НЕ ДЛЯ AIConfigManager
    user_id = None
    if context is not None:
        user_id = getattr(context, 'user_id', None)
    if user_id is None:
        user_id = st.session_state.get('user_id')

    print(f"👤 user_id для API: {user_id}")

    # ✅ ОБЪЯВЛЯЕМ ПЕРЕМЕННЫЕ ДО ИХ ИСПОЛЬЗОВАНИЯ
    retry_count = 3
    provider = 'agentplatform'
    delay = 2.0
    phase5_settings = {}

    # ========== 5. ИНИЦИАЛИЗАЦИЯ AI С ПЕРЕДАЧЕЙ USER_ID ==========
    try:
        from ai_settings.ai_module import AIConfigManager, AIGenerator

        # ✅ НЕ ПЕРЕДАЕМ user_id В AIConfigManager
        config_manager = AIConfigManager()  # ← БЕЗ ПАРАМЕТРОВ!

        # ✅ user_id передаем только в APIKeyManager через отдельный метод
        # Если у AIConfigManager есть метод set_user_id, используем его
        if hasattr(config_manager, 'set_user_id'):
            config_manager.set_user_id(user_id)
        elif hasattr(config_manager, 'user_id'):
            config_manager.user_id = user_id

        st.session_state.ai_config_manager = config_manager

        # Создаем генератор
        ai_generator = AIGenerator(config_manager)
        print(f"✅ AI Generator инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации AI: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': f'Ошибка AI: {e}', 'count': 0, 'errors': 0}

    # ========== 6. ПОДГОТАВЛИВАЕМ ОЧЕРЕДЬ ==========
    all_results = existing_results.copy()
    success_count = sum(1 for r in all_results.values() if r.get('status') == 'success')
    error_count = sum(1 for r in all_results.values() if r.get('status') == 'error')

    # Создаём очередь промптов
    pending_prompts = []
    for idx, prompt_data in enumerate(prompts):
        if 'characteristic_id' in prompt_data:
            prompt_id = f"char_{prompt_data['characteristic_id']}_{prompt_data.get('value', '')}_{prompt_data.get('prompt_num', idx)}"
        elif 'block_id' in prompt_data:
            prompt_id = f"block_{prompt_data['block_id']}_{prompt_data.get('prompt_num', idx)}"
        else:
            prompt_id = f"prompt_{idx}"

        if prompt_id not in all_results or all_results[prompt_id].get('status') != 'success':
            pending_prompts.append((prompt_id, prompt_data, idx))

    total_pending = len(pending_prompts)
    print(f"📊 Ожидают генерации: {total_pending} из {len(prompts)}")

    if total_pending == 0:
        print("✅ Все промпты уже сгенерированы")
        return {
            'success': True,
            'message': f'Все {success_count} текстов уже сгенерированы',
            'count': success_count,
            'errors': 0
        }

    # ========== 7. БАТЧЕВАЯ ГЕНЕРАЦИЯ ==========
    processed_in_this_run = 0

    for batch_start in range(0, total_pending, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_pending)
        batch = pending_prompts[batch_start:batch_end]

        print(f"\n📦 Батч {batch_start//BATCH_SIZE + 1}: {len(batch)} промптов")

        for prompt_id, prompt_data, original_idx in batch:
            print(f"   🎯 {prompt_id[:50]}...")

            ai_response = None
            error_message = None
            success = False

            for attempt in range(retry_count):
                try:
                    result = ai_generator.generate_instruction(
                        prompt_template=prompt_data.get('prompt', ''),
                        context={},
                        provider=provider,
                        num_variants=1,
                        return_full_response=False
                    )

                    if result and result[0].get('success'):
                        ai_response = result[0]['text']
                        if ai_response:
                            ai_response = ai_response.strip()
                            if (ai_response.startswith('"') and ai_response.endswith('"')) or \
                                    (ai_response.startswith("'") and ai_response.endswith("'")):
                                ai_response = ai_response[1:-1]
                        success = True
                        break
                    else:
                        error_message = result[0].get('error', 'Неизвестная ошибка') if result else 'Пустой ответ'
                except Exception as e:
                    error_message = str(e)

                if attempt < retry_count - 1:
                    time.sleep(delay)

            # Сохраняем результат
            if success:
                all_results[prompt_id] = {
                    'prompt_id': prompt_id,
                    'prompt': prompt_data.get('prompt', ''),
                    'ai_response': ai_response,
                    'edited_text': ai_response,
                    'status': 'success',
                    'model': result[0].get('model', '') if result else '',
                    'provider': provider,
                    'tokens_used': result[0].get('usage', {}).get('total_tokens', 0) if result else 0,
                    'generated_at': datetime.now().isoformat(),
                    'error_message': None,
                    'characteristic_name': prompt_data.get('characteristic_name', ''),
                    'characteristic_value': prompt_data.get('value', ''),
                    'block_name': prompt_data.get('block_name', ''),
                    'prompt_num': prompt_data.get('prompt_num', 1),
                    'type': prompt_data.get('type', prompt_data.get('block_type', 'unknown'))
                }
                success_count += 1
                processed_in_this_run += 1
                print(f"      ✅ Успешно")
            else:
                all_results[prompt_id] = {
                    'prompt_id': prompt_id,
                    'prompt': prompt_data.get('prompt', ''),
                    'ai_response': '',
                    'edited_text': '',
                    'status': 'error',
                    'model': '',
                    'provider': provider,
                    'tokens_used': 0,
                    'generated_at': datetime.now().isoformat(),
                    'error_message': error_message,
                    'characteristic_name': prompt_data.get('characteristic_name', ''),
                    'characteristic_value': prompt_data.get('value', ''),
                    'block_name': prompt_data.get('block_name', ''),
                    'prompt_num': prompt_data.get('prompt_num', 1),
                    'type': prompt_data.get('type', prompt_data.get('block_type', 'unknown'))
                }
                error_count += 1
                processed_in_this_run += 1
                print(f"      ❌ Ошибка: {error_message[:80] if error_message else 'Unknown'}")

            time.sleep(delay)

        # ========== СОХРАНЯЕМ ПОСЛЕ КАЖДОГО БАТЧА ==========
        _save_phase5_results_to_file(project_file, all_results, success_count, error_count, len(prompts))
        print(f"   💾 Сохранено после батча: {success_count} успешных")

    # ========== ФИНАЛЬНОЕ СОХРАНЕНИЕ (ВНЕ ЦИКЛА!) ==========
    print(f"\n{'='*60}")
    print(f"💾 ФИНАЛЬНОЕ СОХРАНЕНИЕ PHASE5")
    print(f"{'='*60}")

    # ✅ ПРЯМОЕ СОХРАНЕНИЕ В ФАЙЛ
    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

    # Читаем файл
    file_data = {}
    if project_file.exists():
        with open(project_file, 'r', encoding='utf-8') as f:
            file_data = json.load(f)

    if 'app_data' not in file_data:
        file_data['app_data'] = {}

    # ✅ СОХРАНЯЕМ В НЕСКОЛЬКО МЕСТ ДЛЯ НАДЕЖНОСТИ
    phase5_data = {
        'results': all_results,
        'statistics': {
            'total': len(prompts),
            'success': success_count,
            'error': error_count,
            'completed': success_count + error_count
        },
        'phase_completed': True,
        'completed_at': datetime.now().isoformat()
    }

    file_data['app_data']['phase5'] = phase5_data
    file_data['app_data']['phase5_completed'] = True
    file_data['app_data']['phase5_results'] = all_results
    file_data['phase5_results'] = all_results  # ← на всякий случай
    file_data['updated_at'] = datetime.now().isoformat()
    file_data['current_phase'] = 5

    with open(project_file, 'w', encoding='utf-8') as f:
        json.dump(file_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Файл сохранен: {project_file}")
    print(f"   phase5.results: {len(all_results)}")

    # ✅ ПРОВЕРЯЕМ
    with open(project_file, 'r', encoding='utf-8') as f:
        check_data = json.load(f)
        check_results = check_data.get('app_data', {}).get('phase5', {}).get('results', {})
        print(f"   ✅ Проверка: {len(check_results)} результатов в файле")

    # ✅ ОБНОВЛЯЕМ КОНТЕКСТ
    if context is not None:
        context.set_phase_data(5, {
            'results': all_results,
            'statistics': {
                'total': len(prompts),
                'success': success_count,
                'error': error_count,
                'completed': success_count + error_count
            },
            'phase_completed': True,
            'completed_at': datetime.now().isoformat(),
            'settings': phase5_settings
        })
        context.save()
        print("✅ Phase5 сохранена в контекст")

    print(f"\n✅ Генерация завершена!")
    print(f"   Успешно: {success_count}")
    print(f"   Ошибок: {error_count}")
    print(f"   Обработано в этом запуске: {processed_in_this_run}")

    return {
        'success': success_count > 0,
        'message': f'Сгенерировано {success_count} текстов, ошибок: {error_count}',
        'count': success_count,
        'errors': error_count,
        'processed_in_this_run': processed_in_this_run,
        'statistics': {
            'total': len(prompts),
            'success': success_count,
            'error': error_count
        }
    }


def _save_phase5_results_to_file(project_file: Path, results: dict,
                                 success_count: int, error_count: int,
                                 total: int, final: bool = False) -> bool:
    """Сохраняет результаты Phase5 в файл"""
    import json
    from datetime import datetime

    try:
        file_data = {}
        if project_file.exists():
            with open(project_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)

        if 'app_data' not in file_data:
            file_data['app_data'] = {}

        # ✅ СОХРАНЯЕМ ВО ВСЕ МЕСТА
        phase5_data = {
            'results': results,
            'statistics': {
                'total': total,
                'success': success_count,
                'error': error_count,
                'completed': success_count + error_count
            },
            'phase_completed': final,
            'completed_at': datetime.now().isoformat() if final else None
        }

        # 1. Основное место
        file_data['app_data']['phase5'] = phase5_data

        # 2. Дублирующее место в app_data
        file_data['app_data']['phase5_results'] = results
        file_data['app_data']['phase5_completed'] = final

        # 3. Корневой уровень (для совместимости)
        file_data['phase5_results'] = results

        file_data['updated_at'] = datetime.now().isoformat()
        if final:
            file_data['current_phase'] = 5

        with open(project_file, 'w', encoding='utf-8') as f:
            json.dump(file_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Сохранено: app_data.phase5.results={len(results)}, phase5_results={len(results)}")
        return True

    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return False


def save_to_app_state(app_state=None):
    """Сохраняет данные фазы 5 в общее состояние приложения"""
    if 'app_data' in st.session_state:
        if st.session_state.phase5_prompts:
            phase5_data = {
                'statistics': st.session_state.phase5['statistics'].copy(),
                'generation_settings': st.session_state.phase5['generation_settings'].copy(),
                'phase_completed': st.session_state.phase5.get('generation_status') == 'completed',
                'completed_at': datetime.now().isoformat(),
                'prompts_count': len(st.session_state.phase5_prompts)
            }

            # Добавляем результаты (только успешные, чтобы не раздувать)
            phase5_data['results'] = {
                pid: result for pid, result in st.session_state.phase5['results'].items()
                if result.get('status') == 'success' and result.get('ai_response')
            }

            st.session_state.app_data['phase5'] = phase5_data
            if app_state:
                app_state.save_project()

            # === ДОБАВИТЬ СОХРАНЕНИЕ В ДОМЕН ===
            if 'domain_manager' not in st.session_state:
                st.session_state.domain_manager = DomainManager()

            # === КОНЕЦ ДОБАВЛЕНИЯ ===

            return True
    return False


def main(app_state=None, settings_mode=False, context=None):
    try:
        init_phase5_structure()

        # ✅ ДОБАВИТЬ СИНХРОНИЗАЦИЮ ДОМЕНА ИЗ ФАЙЛА
        if 'domain_manager' not in st.session_state:
            from domain_manager import DomainManager
            st.session_state.domain_manager = DomainManager()

        dm = st.session_state.domain_manager
        user_id = st.session_state.get('user_id')

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

            print(f"✅ Phase5 загружен домен из файла: {saved_domain}")

        # ========== ПРИНУДИТЕЛЬНАЯ ЗАГРУЗКА ИЗ ФАЙЛА ==========
        # ✅ Загружаем данные из файла ПЕРЕД отображением
        force_load_phase5_from_file(context)

        # === ОТОБРАЖЕНИЕ ТЕКУЩЕГО ДОМЕНА ===
        if 'domain_manager' not in st.session_state:
            st.session_state.domain_manager = DomainManager()

        dm = st.session_state.domain_manager
        st.info(f"🌐 Текущий домен: **{dm.get_domain_display_name()}**")

        ctx_data = _get_context_data(context, st.session_state)

        # ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
        if ctx_data['has_context'] and context is not None:
            phase5_saved = context.get_phase_data(5)
            if phase5_saved:
                if 'results' in phase5_saved:
                    st.session_state.phase5['results'] = phase5_saved.get('results', {})
                if 'statistics' in phase5_saved:
                    st.session_state.phase5['statistics'].update(phase5_saved.get('statistics', {}))
                if 'generation_settings' in phase5_saved:
                    st.session_state.phase5['generation_settings'].update(phase5_saved.get('generation_settings', {}))
                print(f"✅ Phase5 загружена из контекста")

        # ПРИОРИТЕТ 2: ИЗ APP_STATE
        elif app_state:
            phase5_saved = app_state.get_phase_data(5)
            if phase5_saved:
                if 'results' in phase5_saved:
                    st.session_state.phase5['results'] = phase5_saved.get('results', {})
                if 'statistics' in phase5_saved:
                    st.session_state.phase5['statistics'].update(phase5_saved.get('statistics', {}))
                if 'generation_settings' in phase5_saved:
                    st.session_state.phase5['generation_settings'].update(phase5_saved.get('generation_settings', {}))
                print(f"✅ Phase5 загружена из app_state")
        # === КОНЕЦ ДОБАВЛЕНИЯ ===
        if 'phase5' not in st.session_state:
            st.session_state.phase5 = {
                'generation_status': 'idle',
                'selected_prompt_ids': [],
                'results': {},
                'statistics': {
                    'total': 0, 'selected': 0, 'completed': 0, 'success': 0, 'error': 0, 'pending': 0
                },
                'generation_settings': {
                    'provider': 'agentplatform',
                    'temperature': 0.7,
                    'max_tokens': 2000,
                    'retry_count': 3,
                    'delay_between_requests': 2.0
                },
                'current_batch': 0,
                'total_batches': 0,
                'generation_start_time': None,
                'generation_end_time': None,
                'generation_queue': [],
                'current_index': 0,
                'generation_running': False,
                'initialized': False
            }

        if 'ai_config_manager' not in st.session_state:
            try:
                from ai_settings.ai_module import AIConfigManager
                st.session_state.ai_config_manager = AIConfigManager()
                print("✅ AIConfigManager initialized in phase5 main")
            except Exception as e:
                print(f"⚠️ Failed to initialize AIConfigManager: {e}")
                st.session_state.ai_config_manager = None

        load_css()

        # ========== ПРИНУДИТЕЛЬНАЯ ИНИЦИАЛИЗАЦИЯ phase5 ==========
        # Инициализируем phase5 если его нет (для любого режима)
        if 'phase5' not in st.session_state:
            st.session_state.phase5 = {
                'generation_status': 'idle',
                'selected_prompt_ids': [],
                'results': {},
                'statistics': {
                    'total': 0, 'selected': 0, 'completed': 0, 'success': 0, 'error': 0, 'pending': 0
                },
                'generation_settings': {
                    'provider': 'agentplatform',
                    'temperature': 0.7,
                    'max_tokens': 2000,
                    'retry_count': 3,
                    'delay_between_requests': 2.0
                },
                'current_batch': 0,
                'total_batches': 0,
                'generation_start_time': None,
                'generation_end_time': None,
                'generation_queue': [],
                'current_index': 0,
                'generation_running': False,
                'initialized': False
            }

        # ========== РЕЖИМ НАСТРОЕК ==========
        if settings_mode:
            st.markdown("### 🚀 Настройка генерации текстов (Фаза 5)")
            st.caption("Настройте параметры генерации текстов для автоматического запуска")
            #st.info("💡 Промпты будут автоматически загружены из фазы 4 во время автоматического запуска")
            st.markdown("---")

            # Загружаем сохранённые настройки из app_data если есть
            saved_settings = {}
            if app_state and hasattr(app_state, 'app_data'):
                saved_settings = app_state.app_data.get('phase5_settings', {})
            elif 'app_data' in st.session_state:
                saved_settings = st.session_state.app_data.get('phase5_settings', {})

            # Настройки AI
            col1, col2 = st.columns(2)
            with col1:
                available_providers = ["agentplatform", "deepseek"]
                provider_labels = {
                    "agentplatform": "AgentPlatform (OpenAI/Anthropic/Google/Mistral и др.)",
                    "deepseek": "DeepSeek (прямой доступ)"
                }

                current_provider = saved_settings.get('provider', 'agentplatform')
                if current_provider not in available_providers:
                    current_provider = 'agentplatform'
                default_index = available_providers.index(current_provider)

                provider = st.selectbox(
                    "Провайдер AI для генерации текстов:",
                    available_providers,
                    format_func=lambda x: provider_labels.get(x, x),
                    index=default_index,
                    key="phase5_settings_provider"
                )

            with col2:
                if provider == "agentplatform":
                    available_models = [
                        "gpt-4o-mini",
                        "gpt-4o",
                        "gpt-4-turbo",
                        "claude-3-5-sonnet-20241022",
                        "claude-3-haiku-20240307",
                        "gemini-2.0-flash-exp",
                        "gemini-1.5-pro",
                        "llama-3.1-70b-instruct"
                    ]
                else:
                    available_models = ["deepseek-chat", "deepseek-coder"]

                current_model = saved_settings.get('model', available_models[0])
                if current_model not in available_models:
                    current_model = available_models[0]
                model_index = available_models.index(current_model)

                ai_model = st.selectbox(
                    "Модель AI:",
                    available_models,
                    index=model_index,
                    key="phase5_settings_model"
                )

            # Дополнительные настройки
            with st.expander("⚙️ Дополнительные настройки (опционально)", expanded=False):
                temperature = st.slider(
                    "Temperature:",
                    min_value=0.0, max_value=2.0,
                    value=saved_settings.get('temperature', 0.7),
                    step=0.1,
                    key="phase5_settings_temperature"
                )
                max_tokens = st.number_input(
                    "Max Tokens:",
                    min_value=100, max_value=8000,
                    value=saved_settings.get('max_tokens', 2000),
                    key="phase5_settings_max_tokens"
                )
                retry_count = st.number_input(
                    "Повторных попыток при ошибке:",
                    min_value=1, max_value=10,
                    value=saved_settings.get('retry_count', 3),
                    key="phase5_settings_retry_count"
                )
                delay = st.slider(
                    "Задержка между запросами (сек):",
                    min_value=0.5, max_value=10.0,
                    value=saved_settings.get('delay_between_requests', 2.0),
                    step=0.5,
                    key="phase5_settings_delay"
                )

            # Кнопка сохранения настроек
            if st.button("💾 Сохранить настройки фазы 5", type="primary"):
                # Обновляем generation_settings
                st.session_state.phase5['generation_settings'].update({
                    'provider': provider,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'retry_count': retry_count,
                    'delay_between_requests': delay
                })

                # Сохраняем в app_data
                if 'app_data' not in st.session_state:
                    st.session_state.app_data = {}

                st.session_state.app_data['phase5_settings'] = {
                    'provider': provider,
                    'model': ai_model,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'retry_count': retry_count,
                    'delay_between_requests': delay,
                    'auto_generate': True
                }
                st.session_state.app_data['phase5_ai_provider'] = provider
                st.session_state.app_data['phase5_ai_model'] = ai_model

                if app_state:
                    app_state.save_project()
                st.success("✅ Настройки фазы 5 сохранены!")

            st.markdown("---")
            st.info("💡 Эти настройки будут использоваться при автоматической генерации текстов (кнопка 🚀 в списке проектов)")

            # Кнопка назад
            if st.button("← Назад к настройкам проекта", key='back_phase5'):
                st.session_state.show_settings = True
                st.rerun()

            return  # ВАЖНО: выходим из функции после настроек

        # ========== ОБЫЧНЫЙ РЕЖИМ (полная функциональность) ==========

        st.title("🚀 Фаза 5: Генерация текстовых блоков")
        st.markdown("---")

        # Инициализация менеджеров
        data_manager = Phase5DataManager()
        generation_manager = GenerationManager(data_manager)
        ui = Phase5UIComponents()

        # Восстанавливаем данные из app_data если есть
        # Восстанавливаем данные из app_data если есть
        if app_state:
            if 'phase5' in st.session_state.app_data:
                phase5_saved = st.session_state.app_data['phase5']
                if phase5_saved:
                    # ✅ Проверяем, что phase5 существует в session_state
                    if 'phase5' not in st.session_state:
                        st.session_state.phase5 = {
                            'generation_status': 'idle',
                            'selected_prompt_ids': [],
                            'results': {},
                            'statistics': {
                                'total': 0, 'selected': 0, 'completed': 0, 'success': 0, 'error': 0, 'pending': 0
                            },
                            'generation_settings': {
                                'provider': 'agentplatform',
                                'temperature': 0.7,
                                'max_tokens': 2000,
                                'retry_count': 3,
                                'delay_between_requests': 2.0
                            },
                            'current_batch': 0,
                            'total_batches': 0,
                            'generation_start_time': None,
                            'generation_end_time': None,
                            'generation_queue': [],
                            'current_index': 0,
                            'generation_running': False,
                            'initialized': False
                        }

                    if 'statistics' in phase5_saved:
                        st.session_state.phase5['statistics'].update(phase5_saved['statistics'])

                    if 'results' in phase5_saved:
                        if isinstance(phase5_saved['results'], list):
                            for result in phase5_saved['results']:
                                if 'prompt_id' in result:
                                    st.session_state.phase5['results'][result['prompt_id']] = result
                        elif isinstance(phase5_saved['results'], dict):
                            st.session_state.phase5['results'].update(phase5_saved['results'])

                    if 'generation_settings' in phase5_saved:
                        st.session_state.phase5['generation_settings'].update(phase5_saved['generation_settings'])

                    st.info("🔄 Данные фазы 5 восстановлены из сохранённого проекта")

            st.session_state.current_phase = 5
            app_state.save_project()

        # Загрузка промптов из фазы 4
        if not st.session_state.phase5_prompts:
            with st.spinner("Загрузка промптов из фазы 4..."):
                data_manager.load_prompts_from_phase4()

        # Обработка фоновой генерации
        # Обработка фоновой генерации
        phase5 = st.session_state.phase5
        if (phase5.get('generation_running', False) and
                phase5.get('generation_status') == 'running'):

            print(f"🔄 Запускаем process_batch | current_index = {phase5.get('current_index', 0)}")

            BATCH_SIZE = 10
            with st.spinner(f"Генерируем батч {phase5.get('current_index', 0) // BATCH_SIZE + 1}..."):
                processed = generation_manager.process_batch(batch_size=BATCH_SIZE)

            if processed > 0:
                print(f"✅ Обработано {processed} промптов в этом батче")
                st.rerun()
            else:
                print("⚠️ process_batch вернул 0")

        # Создаём словарь для быстрого поиска
        if st.session_state.phase5_prompts:
            st.session_state.phase5_prompts_by_id = {
                p.get('phase5_id'): p for p in st.session_state.phase5_prompts
            }

        # Вкладки
        nav_options = ["Выбор промптов", "Настройки генерации", "Управление генерацией", "Результаты", "Экспорт"]
        tab1, tab2, tab3, tab4, tab5 = st.tabs(nav_options)

        with tab1:
            ui.show_prompts_selection(data_manager)
        with tab2:
            ui.show_generation_settings()
        with tab3:
            ui.show_generation_control(generation_manager, data_manager)
        with tab4:
            ui.show_results(data_manager)
        with tab5:
            st.header("💾 Экспорт результатов")
            if st.session_state.phase5['statistics']['completed'] == 0:
                st.info("Нет данных для экспорта. Сначала сгенерируйте тексты.")
            else:
                Phase5UIComponents._show_export_options(data_manager)

        # Боковая панель
        with st.sidebar:
            st.header("📊 Статус фазы 5")
            if st.session_state.phase5_prompts:
                status = st.session_state.phase5.get('generation_status', 'idle')
                status_colors = {'idle': '⚪', 'running': '🟢', 'paused': '🟡', 'stopped': '🔴', 'completed': '✅', 'error': '❌'}
                status_icon = status_colors.get(status, '⚪')
                st.write(f"{status_icon} **Статус:** {status.upper()}")

                types_count = {}
                for p in st.session_state.phase5_prompts:
                    t = p.get('type', p.get('block_type', 'unknown'))
                    types_count[t] = types_count.get(t, 0) + 1
                with st.expander("Статистика по типам"):
                    for t, count in types_count.items():
                        st.write(f"• {t}: {count}")
            else:
                st.warning("⚠️ Промпты не загружены")

            st.divider()
            st.header("🗂️ Управление данными")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Загрузить из фазы 4", key="sidebar_load_prompts_btn"):
                    data_manager.load_prompts_from_phase4()
                    st.rerun()
            with col2:
                if st.button("🗑️ Сбросить все", key="sidebar_reset_all_btn"):
                    data_manager.reset_session_data()
                    st.rerun()

            st.divider()
            if 'app_data' in st.session_state:
                app_data = st.session_state.app_data
                st.header("📁 Инфо")
                st.write(f"**Категория:** {app_data.get('category', 'Не указана')}")
                if 'phase4' in app_data:
                    st.write(f"**Промптов из фазы 4:** {len(app_data['phase4'].get('prompts', []))}")

        # Основной контент - статистика
        st.markdown("---")
        data_manager._update_statistics()
        stats = st.session_state.phase5['statistics']

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Всего промптов", stats['total'])
        with col2:
            st.metric("Выбрано", stats['selected'])
        with col3:
            st.metric("Успешно", stats['success'])
        with col4:
            st.metric("Ошибки", stats['error'])
        with col5:
            st.metric("Ожидают", stats['pending'])

        # Переход к фазе 6
        st.markdown("---")
        st.header("🚀 Переход к фазе 6")

        col1, col2, col3 = st.columns(3)
        with col1:
            can_proceed = stats['selected'] > 0 and stats['completed'] == stats['selected']
            status_text = "✅ Готово к переходу" if can_proceed else "⏳ Завершите генерацию"
            st.write(f"**Статус:** {status_text}")

        with col2:
            if st.button("💾 Сохранить данные для фазы 6", key="save_for_phase6_btn"):
                # ✅ ВЫЗЫВАЕМ ПРАВИЛЬНУЮ ФУНКЦИЮ ДЛЯ ЗАВЕРШЕНИЯ
                if data_manager.complete_phase5_and_prepare_phase6():
                    st.success("✅ Данные сохранены! Фаза 5 завершена. Теперь можно переходить к фазе 6.")
                    st.rerun()
                else:
                    st.error("❌ Ошибка при сохранении данных. Проверьте, что есть сгенерированные тексты.")

        with col3:
            if st.button("➡️ Перейти к фазе 6", type="primary", key="goto_phase6_btn"):
                # ✅ ТОЖЕ ВЫЗЫВАЕМ ПРАВИЛЬНУЮ ФУНКЦИЮ
                if data_manager.complete_phase5_and_prepare_phase6():
                    st.session_state.current_phase = 6
                    st.rerun()
                else:
                    st.error(
                        "❌ Нет сгенерированных текстов. Сначала сгенерируйте тексты или нажмите 'Сохранить данные'.")

        # Автоматическое сохранение
        if stats['completed'] > 0:
            if 'app_data' not in st.session_state:
                st.session_state.app_data = {}
            st.session_state.app_data['phase5'] = {
                'results': list(st.session_state.phase5['results'].values()),
                'statistics': st.session_state.phase5['statistics'],
                'generation_settings': st.session_state.phase5['generation_settings'],
                'phase_completed': True,
                'completed_at': datetime.now().isoformat(),
                'prompts_count': len(st.session_state.phase5_prompts)
            }

    except Exception as e:
        err = traceback.format_exc()
        log(f"CRASH: {err}", "ERROR")
        st.error("Произошла ошибка — смотри логи ниже")
        if st.session_state.get("logs"):
            st.code("".join(st.session_state.logs[-20:]), language="text")


# --- Главная функция фазы 5 ---




if __name__ == "__main__":
    main()