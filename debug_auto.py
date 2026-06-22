# debug_auto.py
"""
АВТОМАТИЧЕСКАЯ ОТЛАДКА - ОДИН ИМПОРТ ДЛЯ ВСЕХ ФАЗ
"""

import json
import threading
import traceback
import functools
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import streamlit as st


class AutoDebug:
    """Автоматическая отладка - логирует ВСЕ вызовы функций в фазах"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.log_dir = Path("logs/debug")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # ИНИЦИАЛИЗАЦИЯ СРАЗУ
        if 'debug_entries' not in st.session_state:
            st.session_state.debug_entries = []
        if 'debug_enabled' not in st.session_state:
            st.session_state.debug_enabled = True
        if 'show_debug_panel' not in st.session_state:
            st.session_state.show_debug_panel = False

        print("🐛 AutoDebug активен - логирует ВСЕ фазы автоматически")

    def _get_context(self) -> Dict:
        try:
            # ✅ ПРОВЕРЯЕМ КОНТЕКСТ В ТЕКУЩЕМ ПОТОКЕ
            thread_context = {}
            if hasattr(threading.current_thread(), 'user_context'):
                thread_context = threading.current_thread().user_context

            return {
                'user_id': thread_context.get('user_id') or st.session_state.get('user_id'),
                'username': st.session_state.get('username'),
                'project_id': thread_context.get('project_id') or st.session_state.get('current_project_id'),
                'site': thread_context.get('site') or st.session_state.get('current_site', 'steelborg'),
                'domain': thread_context.get('domain') or st.session_state.get('current_domain', 'default'),
                'thread': threading.current_thread().name,
                'thread_id': threading.get_ident(),
                'phase': st.session_state.get('current_phase'),
                'session': st.session_state.get('session_token', '')[:8]
            }
        except:
            return {'error': 'Cannot get context'}

    def log(self, phase: str, event: str, data: Dict = None, level: str = "INFO"):
        # ===== БЕЗОПАСНАЯ ИНИЦИАЛИЗАЦИЯ =====
        if 'debug_entries' not in st.session_state:
            st.session_state.debug_entries = []
        if 'debug_enabled' not in st.session_state:
            st.session_state.debug_enabled = True

        if not st.session_state.get('debug_enabled', True):
            return

        context = self._get_context()
        timestamp = datetime.now().isoformat()

        entry = {
            'timestamp': timestamp,
            'phase': phase,
            'event': event,
            'level': level,
            'context': context,
            'data': data or {}
        }

        # В файл
        try:
            user = context.get('user_id', 'unknown')
            log_file = self.log_dir / f"debug_{user}_{datetime.now().strftime('%Y%m%d')}.jsonl"
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except:
            pass

        # В консоль
        colors = {'INFO': '\033[92m', 'WARN': '\033[93m', 'ERROR': '\033[91m',
                  'DEBUG': '\033[94m', 'SAVE': '\033[96m'}
        color = colors.get(level, '\033[0m')
        proj = context.get('project_id', '')[:8] if context.get('project_id') else 'no-proj'
        print(f"{color}[{timestamp[11:19]}] [{level}] [{phase}] {event} | user={context.get('user_id')} proj={proj}{'\033[0m'}")

        # В session_state
        st.session_state.debug_entries.append(entry)
        if len(st.session_state.debug_entries) > 500:
            st.session_state.debug_entries = st.session_state.debug_entries[-500:]

    # ===== АВТОМАТИЧЕСКИЙ ДЕКОРАТОР ДЛЯ ФАЗ =====

    def auto_log(self, func):
        """Декоратор - автоматически логирует ВСЕ вызовы функций в фазах"""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            module_name = func.__module__.split('.')[-1] if '.' in func.__module__ else func.__module__
            phase = module_name.replace('phase', 'Фаза ')
            is_main = func.__name__ == 'main'

            self.log(
                phase,
                f"▶ {func.__name__}()",
                {
                    'args': str(args)[:200] if args else [],
                    'kwargs': str(kwargs)[:200] if kwargs else {},
                    'settings_mode': kwargs.get('settings_mode', False) if kwargs else False
                },
                "DEBUG" if not is_main else "PHASE"
            )

            try:
                result = func(*args, **kwargs)
                self.log(
                    phase,
                    f"✓ {func.__name__}() завершена",
                    {
                        'result_type': type(result).__name__,
                        'result_len': len(result) if hasattr(result, '__len__') else None,
                        'result_preview': str(result)[:100] if result else None
                    },
                    "DEBUG" if not is_main else "PHASE"
                )
                return result
            except Exception as e:
                self.log(
                    phase,
                    f"✗ {func.__name__}() ОШИБКА",
                    {
                        'error': str(e),
                        'traceback': traceback.format_exc()[:500]
                    },
                    "ERROR"
                )
                raise
        return wrapper

    # ===== ПАНЕЛЬ В UI =====

    def render_panel(self):
        # ===== БЕЗОПАСНАЯ ИНИЦИАЛИЗАЦИЯ =====
        if 'debug_entries' not in st.session_state:
            st.session_state.debug_entries = []
        if 'show_debug_panel' not in st.session_state:
            st.session_state.show_debug_panel = False

        if not st.session_state.get('show_debug_panel', False):
            return

        st.markdown("---")
        st.markdown("## 🐛 ПАНЕЛЬ ОТЛАДКИ")

        if st.button("❌ Закрыть", key="debug_close"):
            st.session_state.show_debug_panel = False
            st.rerun()

        context = self._get_context()
        st.json(context)

        entries = st.session_state.get('debug_entries', [])
        col1, col2, col3 = st.columns(3)
        with col1:
            phases = ["Все"] + sorted(list(set(e.get('phase', 'unknown') for e in entries)))
            filter_phase = st.selectbox("Фаза", phases)
        with col2:
            levels = ["Все", "INFO", "WARN", "ERROR", "DEBUG", "PHASE", "SAVE"]
            filter_level = st.selectbox("Уровень", levels)
        with col3:
            if st.button("🗑️ Очистить"):
                st.session_state.debug_entries = []
                st.rerun()

        filtered = entries
        if filter_phase != "Все":
            filtered = [e for e in filtered if e.get('phase') == filter_phase]
        if filter_level != "Все":
            filtered = [e for e in filtered if e.get('level') == filter_level]

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего", len(entries))
        with col2:
            st.metric("Показано", len(filtered))
        with col3:
            errors = len([e for e in filtered if e.get('level') == 'ERROR'])
            st.metric("Ошибок", errors, delta="⚠️" if errors else "✅")
        with col4:
            saves = len([e for e in filtered if e.get('level') == 'SAVE'])
            st.metric("Сохранений", saves)

        st.markdown("---")

        for entry in filtered[-50:]:
            level = entry.get('level', 'INFO')
            color = {
                'INFO': 'green',
                'WARN': 'orange',
                'ERROR': 'red',
                'DEBUG': 'blue',
                'PHASE': 'purple',
                'SAVE': 'cyan'
            }.get(level, 'black')

            time = entry.get('timestamp', '')[:19] if entry.get('timestamp') else ''
            phase = entry.get('phase', '')
            event = entry.get('event', '')

            st.markdown(f"`{time}` | **{phase}** | <span style='color:{color}'>{level}</span> | {event[:80]}",
                        unsafe_allow_html=True)

            if entry.get('data'):
                with st.expander("📋 Детали", expanded=False):
                    st.json(entry.get('data', {}))

        st.stop()

    def render_button(self):
        # ===== БЕЗОПАСНАЯ ИНИЦИАЛИЗАЦИЯ =====
        if 'show_debug_panel' not in st.session_state:
            st.session_state.show_debug_panel = False

        if st.button("🐛 Отладка", key="debug_toggle", use_container_width=True):
            st.session_state.show_debug_panel = not st.session_state.get('show_debug_panel', False)
            st.rerun()

    # ===== ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ =====

    def log_phase_start(self, phase: str, details: Dict = None):
        self.log(phase, f"🚀 НАЧАЛО ФАЗЫ", details, "PHASE")

    def log_phase_end(self, phase: str, result: Dict = None):
        # Если в результате есть project_id, проверяем что он соответствует контексту
        if result and 'project_id' in result:
            # Получаем контекст потока
            thread_ctx = {}
            if hasattr(threading.current_thread(), 'user_context'):
                thread_ctx = threading.current_thread().user_context

            # Если project_id в результате не совпадает с контекстом потока - ОШИБКА!
            if thread_ctx and thread_ctx.get('project_id'):
                if result['project_id'] != thread_ctx['project_id']:
                    self.log(
                        "CRITICAL",
                        f"⚠️ ПЕРЕКРЕСТНЫЕ ДАННЫЕ! project_id={result['project_id']} должен быть {thread_ctx['project_id']}",
                        {
                            'result_project_id': result['project_id'],
                            'expected_project_id': thread_ctx['project_id'],
                            'thread': threading.current_thread().name
                        },
                        "ERROR"
                    )

        self.log(phase, f"✅ ЗАВЕРШЕНИЕ ФАЗЫ", result, "PHASE")

    def log_data(self, phase: str, data_name: str, data: Any):
        data_type = type(data).__name__
        data_len = len(data) if hasattr(data, '__len__') else 0
        self.log(phase, f"📊 ДАННЫЕ: {data_name}", {
            'data_name': data_name,
            'type': data_type,
            'length': data_len,
            'sample': str(data)[:200] if data else None
        }, "DEBUG")

    def log_load(self, phase: str, filename: str, exists: bool, count: int = 0):
        self.log(phase, f"📂 ЗАГРУЗКА: {filename}", {
            'filename': filename,
            'exists': exists,
            'count': count
        }, "INFO")

    def log_state(self, phase: str):
        keys = ['phase4_generated_prompts', 'phase5_results', 'phase5_completed',
                'current_project_id', 'user_id']
        state = {}
        for key in keys:
            if key in st.session_state:
                val = st.session_state[key]
                if isinstance(val, (list, dict)):
                    state[key] = f"{type(val).__name__}: {len(val)}"
                else:
                    state[key] = val
        self.log(phase, "🧠 СОСТОЯНИЕ SESSION_STATE", state, "DEBUG")

    def log_worker(self, action: str, project_name: str = None, details: Dict = None):
        self.log("worker", f"🔧 WORKER: {action}", {
            'project_name': project_name,
            'details': details or {}
        }, "DEBUG")


# ===== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР =====
debug = AutoDebug()


# ===== АВТОМАТИЧЕСКОЕ ПРИМЕНЕНИЕ КО ВСЕМ ФАЗАМ =====

def apply_debug_to_all_phases():
    try:
        from phases import phase1, phase2, phase3, phase4, phase5, phase6, phase7

        for phase_module in [phase1, phase2, phase3, phase4, phase5, phase6, phase7]:
            if hasattr(phase_module, 'main'):
                original_main = phase_module.main
                phase_module.main = debug.auto_log(original_main)
                print(f"✅ Отладка применена к {phase_module.__name__}.main")

        print("✅ Отладка применена ко ВСЕМ фазам автоматически!")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка применения отладки: {e}")
        return False


# ===== АНАЛИЗ ЛОГОВ =====

def analyze_logs():
    print("\n" + "="*80)
    print("📊 АНАЛИЗ ЛОГОВ")
    print("="*80)

    all_entries = []
    for log_file in debug.log_dir.glob("*.jsonl"):
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    all_entries.append(json.loads(line.strip()))
                except:
                    continue

    if not all_entries:
        print("❌ Нет логов")
        return

    print(f"\n📄 Всего записей: {len(all_entries)}")

    users = {}
    for entry in all_entries:
        user = entry.get('context', {}).get('user_id', 'unknown')
        if user not in users:
            users[user] = {'phase4': 0, 'phase5': 0, 'errors': 0}
        phase = entry.get('phase', '')
        if 'phase4' in phase:
            users[user]['phase4'] += 1
        elif 'phase5' in phase:
            users[user]['phase5'] += 1
        if entry.get('level') == 'ERROR':
            users[user]['errors'] += 1

    print("\n👤 ПОЛЬЗОВАТЕЛИ:")
    for user, stats in users.items():
        print(f"   {user}: phase4={stats['phase4']}, phase5={stats['phase5']}, errors={stats['errors']}")

    errors = [e for e in all_entries if e.get('level') == 'ERROR']
    if errors:
        print(f"\n❌ ОШИБКИ ({len(errors)}):")
        for e in errors[-5:]:
            print(f"   {e.get('timestamp', '')[:19]}: {e.get('event', '')[:100]}")

    print("\n" + "="*80)


if __name__ == "__main__":
    analyze_logs()