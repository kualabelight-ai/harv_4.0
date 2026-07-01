
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import html
import json
from pathlib import Path
import re
import shutil
import streamlit as st
import time
from ai_settings.ai_module import AIConfigManager, AIGenerator, AIInstructionManager
import random
from database_settings.auth import is_admin
from datetime import datetime
from styles import load_css
from domain_manager import DomainManager
from pathlib import Path
import warnings
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
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
__all__ = ['main', 'has_phase3_data', 'force_save_phase3_blocks', 'save_phase3_settings']
# Добавьте после всех import, до local_css()
def log(msg):
    """Простое логирование для отладки"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] phase4: {msg}")
def toggle_selection(key):
    """Переключает состояние выбора переменной"""
    if 'selected_ai_vars' not in st.session_state:
        st.session_state.selected_ai_vars = set()

    if key in st.session_state.selected_ai_vars:
        st.session_state.selected_ai_vars.discard(key)
    else:
        st.session_state.selected_ai_vars.add(key)
def get_phase2_data(context=None):
    """Унифицированное получение данных фазы 2"""
    result = {}

    # ========== ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА ==========
    if context is not None:
        phase2_data = context.get_phase_data(2)
        if phase2_data:
            result = phase2_data.copy()
            # Если есть original_category - подменяем category
            if result and result.get('original_category'):
                result['category'] = result['original_category']
            return result

    # ========== ПРИОРИТЕТ 2: ИЗ SESSION_STATE ==========
    if 'phase2_data' in st.session_state and st.session_state.phase2_data:
        result = st.session_state.phase2_data.copy()
    elif 'app_data' in st.session_state and 'phase2' in st.session_state.app_data:
        result = st.session_state.app_data['phase2'].copy()

    # ХАК: если есть original_category - подменяем category
    if result and result.get('original_category'):
        result['category'] = result['original_category']

    return result

def get_characteristics_data(context=None):
    """Унифицированное получение характеристик"""

    # ========== ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА ==========
    if context is not None:
        phase1_data = context.get_phase_data(1)
        if phase1_data and isinstance(phase1_data, dict):
            characteristics = phase1_data.get('characteristics', [])
            if characteristics:
                return characteristics

    # ========== ПРИОРИТЕТ 2: ИЗ SESSION_STATE ==========
    # Сначала проверяем loaded_data
    if 'loaded_data' in st.session_state and st.session_state.loaded_data:
        return st.session_state.loaded_data.get('characteristics', [])

    # Затем проверяем app_data
    if 'app_data' in st.session_state and 'phase1' in st.session_state.app_data:
        return st.session_state.app_data['phase1'].get('characteristics', [])

    return []

def save_data_to_app_state():
    """Сохраняет данные фазы 3 в общее состояние приложения"""
    if 'app_data' in st.session_state and 'block_manager' in st.session_state:
        blocks = st.session_state.block_manager.get_all_blocks()
        if blocks:
            # Сохраняем ПОЛНЫЕ данные блоков
            blocks_data = {}
            for block_id, block in blocks.items():
                blocks_data[block_id] = {
                    'block_id': block_id,
                    'name': block.get('name', ''),
                    'block_type': block.get('block_type', 'other'),
                    'description': block.get('description', ''),
                    'template': block.get('template', ''),
                    'variables': block.get('variables', []),
                    'settings': block.get('settings', {}),
                    'variables_data': block.get('variables_data', {})
                }

            st.session_state.app_data['phase3'] = {
                'blocks': blocks_data,
                'blocks_count': len(blocks),
                'characteristic_blocks': len([b for b in blocks.values() if b.get('block_type') == 'characteristic']),
                'other_blocks': len([b for b in blocks.values() if b.get('block_type') == 'other']),
                'settings_saved': True,
                'saved_at': datetime.now().isoformat()
            }
            return True
    return False
class SessionVariableManager:
    """Управление временными сессионными переменными (не сохраняются в файл)"""

    def __init__(self):
        # Хранилище для временных переменных
        self.session_vars = {}

    def set_session_var(self, var_name, var_data):
        """Устанавливает временную переменную на текущую сессию"""
        self.session_vars[var_name] = {
            **var_data,
            "_session_temp": True,
            "_timestamp": time.time()
        }

    def get_session_var(self, var_name):
        """Получает временную переменную"""
        return self.session_vars.get(var_name)

    def get_all_session_vars(self):
        """Получает все временные переменные"""
        return {k: v for k, v in self.session_vars.items()}

    def clear_session_vars(self):
        """Очищает все временные переменные"""
        self.session_vars.clear()

    def delete_session_var(self, var_name):
        """Удаляет конкретную временную переменную"""
        if var_name in self.session_vars:
            del self.session_vars[var_name]
            return True
        return False
# Функция для нормализации строк (убираем лишние пробелы, приводим к нижнему регистру)
def normalize_string(s):
    """Нормализует строку для сравнения"""
    if not s:
        return ""
    return " ".join(str(s).strip().lower().split())


def init_ai_managers(app_state=None, context=None):
    """Инициализация менеджеров AI - ПРАВИЛЬНАЯ ПРИВЯЗКА К ПРОЕКТУ"""
    from ai_settings.ai_module import AIConfigManager, AIGenerator, AIInstructionManager

    if 'ai_config_manager' not in st.session_state:
        st.session_state.ai_config_manager = AIConfigManager()

    if 'ai_generator' not in st.session_state:
        st.session_state.ai_generator = AIGenerator(st.session_state.ai_config_manager)

    # ========== ПОЛУЧАЕМ PROJECT_ID ==========
    project_id = None
    user_id = None
    site_name = None
    domain_name = None

    # ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
    if context is not None:
        # Проверяем, является ли context объектом с атрибутами
        if hasattr(context, 'project_id'):
            project_id = context.project_id
            user_id = context.user_id
            site_name = context.site_name
            domain_name = context.domain_name
        elif isinstance(context, dict):
            project_id = context.get('project_id')
            user_id = context.get('user_id')
            site_name = context.get('site_name')
            domain_name = context.get('domain_name')
        print(f"🔍 init_ai_managers: project_id={project_id}, user_id={user_id} (из контекста)")

    # ПРИОРИТЕТ 2: ИЗ APP_STATE
    if project_id is None and app_state is not None:
        if hasattr(app_state, 'current_project_id'):
            project_id = app_state.current_project_id
        elif hasattr(app_state, 'get_current_project_id'):
            project_id = app_state.get_current_project_id()
        if hasattr(app_state, 'user_id'):
            user_id = app_state.user_id

    # ПРИОРИТЕТ 3: ИЗ SESSION_STATE
    if project_id is None:
        project_id = st.session_state.get('current_project_id')
    if user_id is None:
        user_id = st.session_state.get('user_id')
    if site_name is None:
        site_name = st.session_state.get('current_site', 'steelborg')
    if domain_name is None:
        domain_name = st.session_state.get('current_domain', 'default')

    print(
        f"🔍 init_ai_managers: ИТОГО project_id={project_id}, user_id={user_id}, site={site_name}, domain={domain_name}")

    # ========== СОЗДАЕМ ИЛИ ОБНОВЛЯЕМ AIInstructionManager ==========
    if project_id and user_id:
        # Создаём менеджер с явной передачей параметров
        st.session_state.ai_instruction_manager = AIInstructionManager(
            project_id=project_id,
            user_id=user_id,
            site_name=site_name,
            domain_name=domain_name,
            context=context
        )

        # ✅ Проверяем, что storage_dir создался
        if hasattr(st.session_state.ai_instruction_manager, 'storage_dir'):
            print(f"✅ AIInstructionManager создан для проекта {project_id}")
            print(f"   Путь: {st.session_state.ai_instruction_manager.storage_dir}")
        else:
            print(f"⚠️ AIInstructionManager создан, но storage_dir не найден!")
            # Принудительно создаём storage_dir
            ai_mgr = st.session_state.ai_instruction_manager
            ai_mgr.storage_dir = Path(
                f"sites/{site_name}/domains/{domain_name}/projects/{user_id}/{project_id}/ai_instructions")
            ai_mgr.storage_dir.mkdir(parents=True, exist_ok=True)
            ai_mgr.storage_file = ai_mgr.storage_dir / "instructions.json"
            ai_mgr.instructions = ai_mgr.load_instructions()
            print(f"   Принудительно создан путь: {ai_mgr.storage_dir}")
    else:
        print(f"⚠️ Не хватает данных для создания AIInstructionManager: project_id={project_id}, user_id={user_id}")

        # Fallback: пробуем создать с данными из session_state
        try:
            fallback_project_id = st.session_state.get('current_project_id')
            fallback_user_id = st.session_state.get('user_id')
            fallback_site = st.session_state.get('current_site', 'steelborg')
            fallback_domain = st.session_state.get('current_domain', 'default')

            if fallback_project_id and fallback_user_id:
                st.session_state.ai_instruction_manager = AIInstructionManager(
                    project_id=fallback_project_id,
                    user_id=fallback_user_id,
                    site_name=fallback_site,
                    domain_name=fallback_domain,
                    context=context
                )
                print(f"✅ AIInstructionManager создан через fallback")
        except Exception as e:
            print(f"⚠️ Не удалось создать AIInstructionManager через fallback: {e}")

def show_ai_variable_generator(block_id, var_name, var_data):
    """Интерфейс для генерации AI-инструкций"""

    init_ai_managers()

    st.markdown("### 🤖 Генерация AI-инструкций")

    # Выбор провайдера
    available_providers = ["agentplatform", "deepseek"]

    provider_labels = {
        "agentplatform": "AgentPlatform (OpenAI/Anthropic/Google/Mistral и др.)",
        "deepseek": "DeepSeek (прямой доступ)"
    }

    default_provider = st.session_state.ai_config_manager.config.get("default_provider", "agentplatform")

    provider = st.selectbox(
        "AI провайдер:",
        available_providers,
        format_func=lambda x: provider_labels.get(x, x),
        index=available_providers.index(default_provider)
        if default_provider in available_providers else 1,
        key=f"ai_provider_{block_id}_{var_name}"
    )

    if provider == "true_gemini":
        st.caption("⚠️ Для true_gemini нужен VPN / зарубежный IP")
    elif provider == "genapi_gemini":
        st.info("GenAPI Gemini — работает без VPN, оплата рублями")

    # Промпт для генерации (без изменений)
    prompt_template = st.text_area(
        "Промпт для AI:",
        value=var_data.get("ai_prompt", ""),
        height=200,
        key=f"ai_prompt_{block_id}_{var_name}",
        help="Используйте {категория}, {характеристика}, {значение} для подстановки контекста"
    )

    # Количество вариантов (без изменений)
    num_variants = st.number_input(
        "Количество вариантов:",
        min_value=1,
        max_value=10,
        value=var_data.get("ai_num_variants", 1),
        key=f"ai_num_variants_{block_id}_{var_name}"
    )

    # Контекст для генерации
    with st.expander("⚙️ Контекст для генерации"):
        st.info("Контекст будет автоматически подставляться из данных фазы 2")

        # Показываем пример контекста
        example_context = {
            "категория": "Адаптер котла",
            "характеристика": "Диаметр",
            "значение": "115 мм",
            "тип": "regular"
        }
        st.json(example_context)

    # Кнопки генерации
    col_gen1, col_gen2, col_gen3 = st.columns(3)

    with col_gen1:
        if st.button("🧪 Тестовая генерация", key=f"test_gen_{block_id}_{var_name}"):
            with st.spinner("Генерация тестового варианта..."):
                test_context = {
                    "категория": "Тестовая категория",
                    "характеристика": "Тестовая характеристика",
                    "значение": "Тестовое значение",
                    "тип": "regular"
                }

                results = st.session_state.ai_generator.generate_instruction(
                    prompt_template,
                    test_context,
                    provider=provider,
                    num_variants=1
                )

                if results and results[0]["success"]:
                    st.success("✅ Тестовая генерация успешна!")
                    st.text_area("Результат:", value=results[0]["text"], height=150)
                else:
                    st.error(f"❌ Ошибка: {results[0].get('error', 'Неизвестная ошибка')}")

    with col_gen2:
        if st.button("🚀 Сгенерировать для всех характеристик",
                     key=f"gen_all_{block_id}_{var_name}"):

            # Получаем данные из фазы 2
            phase2_data = get_phase2_data()
            category = phase2_data.get('category', '')
            characteristics = st.session_state.get('loaded_data', {}).get('characteristics', [])

            if not category or not characteristics:
                st.error("❌ Нет данных из фазы 2. Загрузите данные сначала.")
                return

            with st.spinner(f"Генерация инструкций для {len(characteristics)} характеристик..."):
                results = st.session_state.ai_generator.batch_generate_for_characteristics(
                    prompt_template,
                    characteristics,
                    category,
                    provider=provider
                )

                # Сохраняем результаты
                saved_count = 0
                for char_id, char_results in results.items():
                    if char_results:
                        # Для regular характеристик
                        if isinstance(char_results, list) and len(char_results) > 0 and isinstance(char_results[0],
                                                                                                   dict):
                            # Это unique - результаты для каждого значения
                            for value_result in char_results:
                                context = {
                                    "категория": category,
                                    "характеристика": next((c.get('char_name', '') for c in characteristics
                                                            if c.get('char_id') == char_id), ''),
                                    "значение": value_result.get("value", ""),
                                    "тип": "unique"
                                }

                                values = [r["text"] for r in value_result.get("results", []) if r.get("success")]

                                if values:
                                    st.session_state.ai_instruction_manager.save_instruction(
                                        block_id,
                                        var_name,
                                        values,
                                        context
                                    )
                                    saved_count += len(values)
                        else:
                            # Это regular - общие результаты
                            context = {
                                "категория": category,
                                "характеристика": next((c.get('char_name', '') for c in characteristics
                                                        if c.get('char_id') == char_id), ''),
                                "тип": "regular"
                            }

                            values = [r["text"] for r in char_results if r.get("success")]

                            if values:
                                st.session_state.ai_instruction_manager.save_instruction(
                                    block_id,
                                    var_name,
                                    values,
                                    context
                                )
                                saved_count += len(values)

                st.success(f"✅ Сгенерировано и сохранено {saved_count} инструкций!")
                st.session_state.ai_instruction_manager.reload()  # ← ДОБАВЬ ЭТУ СТРОКУ
                st.rerun()

    with col_gen3:
        if st.button("🔄 Загрузить сохраненные инструкции",
                     key=f"load_saved_{block_id}_{var_name}"):
            # Загружаем сохраненные инструкции для этой переменной
            instructions = st.session_state.ai_instruction_manager.get_instruction(block_id, var_name)

            if instructions:
                # Обновляем значения переменной
                var_data["values"] = instructions
                st.success(f"✅ Загружено {len(instructions)} сохраненных инструкций")
                st.rerun()
            else:
                st.info("Нет сохраненных инструкций для этой переменной")

    # Редактор сохраненных инструкций
    st.markdown("### 📝 Редактирование сохраненных инструкций")

    # Получаем все сохраненные инструкции для этой переменной
    if block_id in st.session_state.ai_instruction_manager.instructions:
        if var_name in st.session_state.ai_instruction_manager.instructions[block_id]:
            for context_hash, instruction_data in st.session_state.ai_instruction_manager.instructions[block_id][
                var_name].items():
                context = instruction_data.get("context", {})
                values = instruction_data.get("values", [])

                with st.expander(f"Контекст: {context.get('характеристика', 'Общий')} ({context.get('тип', 'N/A')})"):
                    st.json(context)

                    for idx, value in enumerate(values):
                        col_edit1, col_edit2 = st.columns([4, 1])
                        with col_edit1:
                            new_value = st.text_area(
                                f"Инструкция {idx + 1}:",
                                value=value,
                                height=100,
                                key=f"edit_{block_id}_{var_name}_{context_hash}_{idx}"
                            )

                        with col_edit2:
                            if st.button("💾", key=f"save_{block_id}_{var_name}_{context_hash}_{idx}"):
                                if st.session_state.ai_instruction_manager.update_instruction_value(
                                        block_id, var_name, context_hash, idx, new_value
                                ):
                                    st.success("Сохранено!")
                                    st.rerun()

                    # Удаление всего контекста
                    if st.button("🗑️ Удалить все инструкции для этого контекста",
                                 key=f"delete_{block_id}_{var_name}_{context_hash}"):
                        if st.session_state.ai_instruction_manager.delete_instruction(
                                block_id, var_name, context_hash
                        ):
                            st.success("Удалено!")
                            st.rerun()

    # Сохраняем AI-настройки в var_data
    var_data["ai_prompt"] = prompt_template
    var_data["ai_num_variants"] = num_variants
    var_data["ai_provider"] = provider

    return var_data
# --- CSS стили ---
def local_css():
    st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .prompt-block {
        background-color: white;
        border-radius: 10px;
        padding: 20px;
        margin: 15px 0;
        border: 1px solid #e0e0e0;
        font-family: monospace;
        font-size: 0.9em;
        white-space: pre-wrap;
    }
    .variable-chip {
        display: inline-block;
        background-color: #e9ecef;
        padding: 3px 8px;
        border-radius: 15px;
        margin: 2px;
        font-size: 0.8em;
        border: 1px solid #dee2e6;
    }
    .variable-chip.static {
        background-color: #d4edda;
        border-color: #c3e6cb;
    }
    .variable-chip.dynamic {
        background-color: #cce5ff;
        border-color: #b8daff;
    }
    .block-type-chip {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75em;
        margin-left: 8px;
    }
    .block-type-characteristic {
        background-color: #e3f2fd;
        color: #1565c0;
    }
    .block-type-other {
        background-color: #f3e5f5;
        color: #7b1fa2;
    }
    .edit-mode {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
    }
    </style>
    """, unsafe_allow_html=True)


# --- Новый класс для обработки глобальных переменных ---
class DynamicVariableProcessor:
    """Универсальный обработчик глобальных переменных"""

    def __init__(self, dynamic_var_manager):
        self.dynamic_var_manager = dynamic_var_manager

    def render_template_with_context(self, template, context_data=None, include_dynamic=True):
        """Рендерит шаблон с подстановкой контекста"""
        if not template:
            return template

        # Копируем шаблон для работы
        result = template

        # Подготавливаем контекст
        context = context_data or {}

        # Заменяем глобальные переменные
        if include_dynamic:
            result = self._replace_dynamic_variables(result, context)

        # Заменяем локальные переменные (оставляем как есть для фазы 3)
        # В фазе 3 мы не заменяем их реальными значениями
        # В фазе 4 они будут заменены отдельно

        return result

    def _replace_dynamic_variables(self, template, context):
        """Заменяет глобальные переменные в шаблоне (включая временные)"""
        # Находим все переменные в шаблоне
        variables = re.findall(r'\{([^}]+)\}', template)

        for var_name in variables:
            # Сначала ищем во временных, потом в постоянных
            var_data = self.dynamic_var_manager.get_dynamic_variable(var_name)
            if not var_data:
                continue

            # Получаем значение с подстановкой контекста
            value = self._get_dynamic_value_with_context(var_name, var_data, context)

            # Экранируем HTML в значении
            if value:
                escaped_value = html.escape(str(value))
                template = template.replace(f"{{{var_name}}}", escaped_value)

        return template

    def _get_dynamic_value_with_context(self, var_name, var_data, context):
        """Получает значение глобальной переменной с подстановкой контекста"""
        values = var_data.get("values", [])
        if not values:
            return ""

        # Выбираем случайное значение
        import random
        value = random.choice(values)

        # Подставляем контекстные данные
        if context:
            for key, val in context.items():
                placeholder = f"{{{key}}}"
                if placeholder in value:
                    # Экранируем HTML в подставляемом значении
                    escaped_val = html.escape(str(val))
                    value = value.replace(placeholder, escaped_val)

        return value

    def get_context_for_preview(self):
        """Возвращает контекст для предпросмотра в фазе 3"""
        return {
            "категория": "Смартфоны",
            "стоп-слова": "купить, заказать, цена, дешево",
            "характеристика": "диагональ экрана",
            "значение": "6.5 дюймов",
            "маркер": "[МАРКЕР]",
            "название_характеристики": "Диагональ экрана"
        }


# --- Классы для работы с данными ---
class BlockManager:
    def __init__(self, domain_name: str = None, site_name: str = None):
        print(f"🛠 BlockManager.__init__ вызван с domain_name={domain_name}, site_name={site_name}")

        # Приоритет: переданные параметры > session_state
        if domain_name is None:
            domain_name = st.session_state.get('current_domain', 'default')
        if site_name is None:
            site_name = st.session_state.get('current_site', 'steelborg')

        self.blocks_dir = Path(f"sites/{site_name}/domains/{domain_name}/blocks")
        print(f"   → blocks_dir = {self.blocks_dir}")

        self.blocks_dir.mkdir(parents=True, exist_ok=True)
        self.blocks = {}
        self.load_blocks()

        print(f"📁 BlockManager инициализирован: domain={domain_name}, блоков={len(self.blocks)}")

        print(f"📁 BlockManager: сайт={site_name}, домен={domain_name}, путь={self.blocks_dir}")
        print(f"   Загружено блоков: {len(self.blocks)}")

        print(f"📁 BlockManager: сайт={site_name}, домен={domain_name}, путь={self.blocks_dir}")

    def load_blocks(self):
        """Загружает все блоки из папки ДОМЕНА"""
        self.blocks = {}

        if not self.blocks_dir.exists():
            return

        for block_dir in self.blocks_dir.iterdir():
            if not block_dir.is_dir():
                continue

            block_file = block_dir / "block.json"
            variables_file = block_dir / "variables.json"

            if block_file.exists():
                try:
                    with open(block_file, 'r', encoding='utf-8') as f:
                        block_data = json.load(f)

                    if "block_type" not in block_data:
                        if "характеристика" in block_data.get("name", "").lower():
                            block_data["block_type"] = "characteristic"
                        else:
                            block_data["block_type"] = "other"

                    if variables_file.exists():
                        with open(variables_file, 'r', encoding='utf-8') as f:
                            block_data["variables_data"] = json.load(f)
                    else:
                        block_data["variables_data"] = {}

                    self.blocks[block_data["block_id"]] = block_data

                except Exception as e:
                    st.error(f"Ошибка загрузки блока {block_dir.name}: {e}")

    def save_block(self, block_data, variables_data=None):
        """Сохраняет блок в папку ДОМЕНА"""
        import traceback

        block_id = block_data["block_id"]
        block_dir = self.blocks_dir / block_id

        print(f"🔵 SAVE_BLOCK START: {block_id}")
        print(f"   blocks_dir: {self.blocks_dir}")
        print(f"   block_dir: {block_dir}")
        print(f"   block_dir exists: {block_dir.exists()}")

        try:
            # Создаём папку блока
            block_dir.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ Папка создана: {block_dir}")

            block_file = block_dir / "block.json"
            variables_file = block_dir / "variables.json"

            print(f"   block_file: {block_file}")
            print(f"   variables_file: {variables_file}")

            # Сохраняем block.json
            with open(block_file, 'w', encoding='utf-8') as f:
                json.dump(block_data, f, ensure_ascii=False, indent=2)
            print(f"   ✅ block.json сохранён, размер: {block_file.stat().st_size if block_file.exists() else 0}")

            # Сохраняем variables.json
            if variables_data:
                with open(variables_file, 'w', encoding='utf-8') as f:
                    json.dump(variables_data, f, ensure_ascii=False, indent=2)
                print(f"   ✅ variables.json сохранён")
            else:
                print(f"   ⚠️ Нет variables_data")

            # Проверяем, что файлы реально создались
            if block_file.exists():
                print(f"   ✅ Файл существует! Читаем обратно для проверки...")
                with open(block_file, 'r', encoding='utf-8') as f:
                    test_data = json.load(f)
                    print(f"   ✅ Прочитано имя: {test_data.get('name', 'N/A')}")
            else:
                print(f"   ❌ Файл НЕ существует после записи!")
                return False

            if "variables_data" not in block_data and variables_data:
                block_data["variables_data"] = variables_data
            self.blocks[block_id] = block_data

            print(f"🔵 SAVE_BLOCK SUCCESS: {block_id}")
            return True

        except Exception as e:
            print(f"🔴 SAVE_BLOCK ERROR: {e}")
            traceback.print_exc()
            st.error(f"Ошибка сохранения блока {block_id}: {e}")
            return False

    def delete_block(self, block_id):
        """Удаляет блок из папки ДОМЕНА"""
        if block_id in self.blocks:
            block_dir = self.blocks_dir / block_id
            if block_dir.exists():
                shutil.rmtree(block_dir)
            del self.blocks[block_id]
            return True
        return False

    # === ЗАМЕНИТЬ полностью функцию create_new_block ===
    def create_new_block(self, base_block_id=None):
        """Создает новый блок — ТОЛЬКО по явному запросу"""
        print(f"🔧 create_new_block вызван | base_block_id={base_block_id} | существующих блоков: {len(self.blocks)}")

        if base_block_id and base_block_id in self.blocks:
            print(f"   → Копируем существующий блок {base_block_id}")
            base_block = self.blocks[base_block_id]
            new_block_id = f"{base_block_id}_copy_{int(time.time())}"

            new_block = base_block.copy()
            new_block["block_id"] = new_block_id
            new_block["name"] = f"{base_block.get('name', 'Блок')} (копия)"

            variables_data = base_block.get("variables_data", {}).copy()
            return new_block_id, new_block, variables_data

        # Пустой минимальный блок
        print(f"   → Создаём ПУСТОЙ новый блок")
        new_block_id = f"block_{int(time.time())}"
        new_block = {
            "block_id": new_block_id,
            "name": "Новый блок",
            "description": "Новый шаблон промпта",
            "template": "Вставьте шаблон здесь...\n{переменная1}",
            "variables": ["переменная1"],
            "settings": {},
            "block_type": "other"
        }

        variables_data = {
            "переменная1": {
                "name": "переменная1",
                "description": "Описание",
                "values": ["Значение 1"],
                "type": "static"
            }
        }

        return new_block_id, new_block, variables_data

    def get_block(self, block_id):
        """Получает блок по ID"""
        return self.blocks.get(block_id)

    def get_all_blocks(self):
        """Возвращает все блоки"""
        return self.blocks

    def get_blocks_by_type(self, block_type):
        """Возвращает блоки определенного типа"""
        return {block_id: block for block_id, block in self.blocks.items() if block.get("block_type") == block_type}


class DynamicVariableManager:
    """Управление глобальными переменными"""

    def __init__(self, config_dir="config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        self.dynamic_vars_file = self.config_dir / "dynamic_variables.json"
        self.dynamic_vars = {}
        self.processor = None
        self.session_var_manager = SessionVariableManager()  # Добавляем менеджер сессионных переменных
        self.load_dynamic_variables()

    def get_all_dynamic_vars(self, include_session=True):
        """Возвращает все переменные, включая сессионные, если нужно"""
        all_vars = self.dynamic_vars.copy()
        if include_session:
            all_vars.update(self.session_var_manager.get_all_session_vars())
        return all_vars

    def get_dynamic_variable(self, var_name, include_session=True):
        """Получает переменную (сначала ищет в сессии, потом в файле)"""
        # Сначала ищем в сессионных
        if include_session:
            session_var = self.session_var_manager.get_session_var(var_name)
            if session_var:
                return session_var
        # Потом в постоянных
        return self.dynamic_vars.get(var_name)

    def create_session_variable(self, var_name, var_data):
        """Создает временную сессионную переменную"""
        self.session_var_manager.set_session_var(var_name, var_data)
        return True

    def delete_session_variable(self, var_name):
        """Удаляет временную сессионную переменную"""
        return self.session_var_manager.delete_session_var(var_name)

    def clear_all_session_variables(self):
        """Очищает все временные переменные"""
        self.session_var_manager.clear_session_vars()

    def promote_session_to_permanent(self, var_name):
        """Преобразует временную переменную в постоянную"""
        session_var = self.session_var_manager.get_session_var(var_name)
        if session_var:
            # Убираем временные метки
            permanent_var = {k: v for k, v in session_var.items() if not k.startswith('_')}
            self.dynamic_vars[var_name] = permanent_var
            self.session_var_manager.delete_session_var(var_name)
            return self.save_dynamic_variables()
        return False

    def get_processor(self):
        """Возвращает процессор для работы с глобальними переменными"""
        if not self.processor:
            self.processor = DynamicVariableProcessor(self)
        return self.processor

    def load_dynamic_variables(self):
        """Загружает глобальные переменные из файла"""
        if self.dynamic_vars_file.exists():
            try:
                with open(self.dynamic_vars_file, 'r', encoding='utf-8') as f:
                    self.dynamic_vars = json.load(f)
            except Exception as e:
                st.error(f"Ошибка загрузки глобальных переменных: {e}")
                self.dynamic_vars = self.get_default_dynamic_vars()
        else:
            self.dynamic_vars = self.get_default_dynamic_vars()
            self.save_dynamic_variables()

    def save_dynamic_variables(self):
        """Сохраняет глобальные переменные в файл"""
        try:
            with open(self.dynamic_vars_file, 'w', encoding='utf-8') as f:
                json.dump(self.dynamic_vars, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            st.error(f"Ошибка сохранения глобальных переменных: {e}")
            return False

    def get_default_dynamic_vars(self):
        """Возвращает глобальные переменные по умолчанию"""
        return {
            "стоп": {
                "name": "стоп",
                "description": "Стоп-слова и ограничения",
                "values": [
                    "Не используй слова: очень, самый, лучший",
                    "Избегай: купить, заказать, цена",
                    "Не упоминай бренды и названия компаний",
                    "Не используй восклицательные знаки",
                    "Избегай клишированных фраз"
                ],
                "type": "dynamic",
                "source": "config"
            },
            "контекст_категория": {
                "name": "контекст_категория",
                "description": "Контекст и категория товара",
                "values": ["{подставляется_из_данных}"],
                "type": "dynamic",
                "source": "data"
            },
            "значение_форматированное": {
                "name": "значение_форматированное",
                "description": "Отформатированное значение характеристики",
                "values": ["{подставляется_на_основе_типа_характеристики}"],
                "type": "dynamic",
                "source": "processing"
            },
            "название_характеристики": {
                "name": "название_характеристики",
                "description": "Название текущей характеристики",
                "values": ["{подставляется_из_данных}"],
                "type": "dynamic",
                "source": "data"
            },
            "характеристика_маркер": {
                "name": "характеристика_маркер",
                "description": "Маркер для вставки в текст характеристики",
                "values": ["{маркер_позиция}"],
                "type": "dynamic",
                "source": "config"
            },
            "маркер": {
                "name": "маркер",
                "description": "Маркер для других типов блоков",
                "values": ["[МАРКЕР]"],
                "type": "dynamic",
                "source": "config"
            }
        }

    def get_dynamic_variable(self, var_name):
        """Получает глобальную переменную по имени"""
        return self.dynamic_vars.get(var_name)

    def update_dynamic_variable(self, var_name, var_data):
        """Обновляет глобальную переменную"""
        self.dynamic_vars[var_name] = var_data
        return self.save_dynamic_variables()

    def get_all_dynamic_vars(self):
        """Возвращает все глобальные переменные"""
        return self.dynamic_vars


class VariableManager:
    """Управление переменными (упрощенная версия)"""

    def __init__(self, block_manager):
        self.block_manager = block_manager

    def get_all_variables_with_data(self, block_id):
        """Возвращает все переменные блока с их данными"""
        block = self.get_block(block_id)
        if not block:
            return {}

        result = {}

        # Добавляем локальные переменные
        static_vars = block.get("variables", [])
        variables_data = block.get("variables_data", {})

        for var_name in static_vars:
            if var_name in variables_data:
                result[var_name] = variables_data[var_name]
            else:
                result[var_name] = {
                    "name": var_name,
                    "description": f"Описание для {var_name}",
                    "values": [f"Значение для {var_name}"],
                    "type": "static"
                }

        return result

    def get_variable_data(self, block_id, var_name):
        """Получает данные переменной из блока"""
        block = self.block_manager.get_block(block_id)
        if not block:
            return None

        variables_data = block.get("variables_data", {})
        return variables_data.get(var_name)

    def save_variable(self, block_id, var_name, var_data):
        """Сохраняет переменную"""
        block = self.block_manager.get_block(block_id)
        if not block:
            return False

        if "variables_data" not in block:
            block["variables_data"] = {}

        block["variables_data"][var_name] = var_data
        return self.block_manager.save_block(block, block["variables_data"])

    def get_block(self, block_id):
        """Получает блок по ID"""
        return self.block_manager.get_block(block_id)

def force_save_phase3_blocks(app_state=None):
    if 'block_manager' not in st.session_state:
        print("❌ force_save_phase3_blocks: block_manager не в session_state")
        return False

    selected_blocks = st.session_state.get('selected_blocks', {})

    phase3_data = {
        'selected_blocks': selected_blocks,
        'blocks_count': len(st.session_state.block_manager.get_all_blocks()),
        'settings_saved': True,
        'saved_at': datetime.now().isoformat(),
        'phase3_generated': True,  # ← ДОБАВИТЬ ЭТУ СТРОКУ!
        'ai_instructions': st.session_state.ai_instruction_manager.instructions if 'ai_instruction_manager' in st.session_state else {}
    }

    if 'app_data' in st.session_state:
        st.session_state.app_data['phase3'] = phase3_data
        st.session_state.app_data['phase3_generated'] = True  # ← И ЭТУ!

    if app_state:
        app_state.set_phase_data(3, phase3_data)
        app_state.save_project()

    print(f"✅ Phase3 settings saved to project (blocks are already in domain)")
    return True

def has_instructions_for_category(block_id, var_name, category, context=None):
    """Проверяет, есть ли уже сгенерированные инструкции для данной категории"""

    if 'ai_instruction_manager' not in st.session_state:
        print(f"⚠️ has_instructions: AIInstructionManager не инициализирован")
        return False

    ai_mgr = st.session_state.ai_instruction_manager

    # Если есть контекст, можно добавить проверку
    if context is not None:
        # Проверяем, что AIInstructionManager привязан к правильному проекту
        if hasattr(ai_mgr, 'storage_dir'):
            project_id = context.project_id
            if project_id and str(project_id) not in str(ai_mgr.storage_dir):
                print(f"⚠️ has_instructions: AIInstructionManager НЕ привязан к проекту {project_id}")
                print(f"   Текущий путь: {ai_mgr.storage_dir}")

    if not category:
        print(f"⚠️ has_instructions: пустая категория")
        return False

    current_category_norm = normalize_string(category)

    if not current_category_norm:
        print(f"⚠️ has_instructions: категория '{category}' после нормализации пуста")
        return False

    # Проверяем наличие блока
    if block_id not in ai_mgr.instructions:
        print(f"⚠️ has_instructions: блок {block_id} не найден в инструкциях")
        print(f"   Доступные блоки: {list(ai_mgr.instructions.keys())}")
        return False

    # Проверяем наличие переменной
    if var_name not in ai_mgr.instructions[block_id]:
        print(f"⚠️ has_instructions: переменная {var_name} не найдена в блоке {block_id}")
        print(f"   Доступные переменные: {list(ai_mgr.instructions[block_id].keys())}")
        return False

    # Ищем совпадение по категории
    for ctx_hash, data in ai_mgr.instructions[block_id][var_name].items():
        context_data = data.get("context", {})
        cat_in_context = context_data.get("категория") or context_data.get("category", "")
        cat_in_context_norm = normalize_string(cat_in_context)

        if cat_in_context_norm == current_category_norm:
            values = data.get("values", [])
            if values:
                print(f"✅ has_instructions: найдены инструкции для категории '{category}'")
                print(f"   Количество значений: {len(values)}")
                return True
            else:
                print(f"⚠️ has_instructions: найдены инструкции для категории '{category}', но values пуст")
                return False

    print(f"⚠️ has_instructions: инструкции для категории '{category}' не найдены")
    return False


def run_mass_generation_auto(app_state=None, context=None):
    print("🔍 run_mass_generation_auto STARTED")
    print(f"   app_state: {app_state}")
    print(f"   context: {context is not None}")

    # ========== ПОЛУЧАЕМ ПАРАМЕТРЫ ИЗ КОНТЕКСТА ==========
    project_id = None
    user_id = None
    site_name = None
    domain_name = None

    # ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
    if context is not None:
        if hasattr(context, 'project_id'):
            project_id = context.project_id
            user_id = context.user_id
            site_name = context.site_name
            domain_name = context.domain_name
            print(f"📌 Из контекста: project={project_id}, user={user_id}, site={site_name}, domain={domain_name}")
        elif isinstance(context, dict):
            project_id = context.get('project_id')
            user_id = context.get('user_id')
            site_name = context.get('site_name')
            domain_name = context.get('domain_name')

    # ПРИОРИТЕТ 2: ИЗ SESSION_STATE (если нет в контексте)
    if project_id is None:
        project_id = st.session_state.get('current_project_id')
    if user_id is None:
        user_id = st.session_state.get('user_id')
    if site_name is None:
        site_name = st.session_state.get('current_site', 'steelborg')
    if domain_name is None:
        domain_name = st.session_state.get('current_domain', 'default')

    print(f"📌 ИТОГО: project={project_id}, user={user_id}, site={site_name}, domain={domain_name}")

    if not project_id or not user_id:
        print("❌ Нет project_id или user_id")
        return {'success': False, 'message': 'Нет данных проекта', 'count': 0}

    # ========== ПРИНУДИТЕЛЬНО ЗАГРУЖАЕМ ДАННЫЕ ИЗ ФАЙЛА ПРОЕКТА ==========
    project_file = Path(f"sites/{site_name}/domains/{domain_name}/projects/{user_id}/{project_id}.json")
    print(f"📂 Загружаем файл проекта: {project_file}")

    if not project_file.exists():
        print(f"❌ Файл проекта не найден: {project_file}")
        return {'success': False, 'message': f'Файл проекта не найден', 'count': 0}

    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            file_data = json.load(f)
        print(f"✅ Файл загружен, размер: {len(str(file_data))} байт")
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return {'success': False, 'message': f'Ошибка чтения файла: {e}', 'count': 0}

    # ========== ИЗВЛЕКАЕМ ДАННЫЕ ИЗ ФАЙЛА ==========
    app_data = file_data.get('app_data', {})

    # Фаза 1 - характеристики
    phase1_data = app_data.get('phase1', {})
    if not phase1_data:
        # Пробуем другие места
        phase1_data = file_data.get('phase1_data', {})
    if not phase1_data:
        phase1_data = file_data.get('characteristics_data', {})

    characteristics = phase1_data.get('characteristics', [])
    category = phase1_data.get('category', '')

    # Если нет в phase1, пробуем другие места
    if not characteristics:
        characteristics = app_data.get('characteristics', [])
        if not characteristics:
            characteristics = file_data.get('characteristics', [])

    if not category:
        category = app_data.get('category', '')
        if not category:
            category = file_data.get('category', '')

    print(f"📊 Из ФАЙЛА: категория='{category}', характеристик={len(characteristics)}")

    if not characteristics:
        print("❌ Нет характеристик в файле")
        return {'success': False, 'message': 'Нет характеристик в файле проекта', 'count': 0}

    # ========== СОХРАНЯЕМ В SESSION_STATE ДЛЯ UI ==========
    st.session_state.phase2_data = {'category': category}
    st.session_state.loaded_data = {'characteristics': characteristics, 'category': category}
    st.session_state.category = category

    # ========== ОБНОВЛЯЕМ КОНТЕКСТ ==========
    if context is not None:
        if hasattr(context, 'set_phase_data'):
            context.set_phase_data(1, {'characteristics': characteristics, 'category': category})
            context.set('category', category)
            context.set('phase2_data', {'category': category})
            context.set('loaded_data', {'characteristics': characteristics, 'category': category})
            context.save()
            print("✅ Данные сохранены в контекст")

    # ========== ПРОВЕРКА НА СУЩЕСТВУЮЩИЕ ИНСТРУКЦИИ ==========
    skip_existing = False
    if context is not None:
        if hasattr(context, 'get'):
            skip_existing = context.get('phase3_skip_existing', False)

    # ========== ИНИЦИАЛИЗИРУЕМ AI МЕНЕДЖЕРЫ ==========
    init_ai_managers(app_state, context)

    # ========== ПОЛУЧАЕМ БЛОКИ ИЗ ДОМЕНА ==========
    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()
    dm = st.session_state.domain_manager

    # 🔥 КРИТИЧНО: явно передаём domain_name из контекста/параметров
    effective_domain = domain_name or dm.get_current_domain() or st.session_state.get('current_domain', 'default')
    effective_site = site_name or dm.site_name or st.session_state.get('current_site', 'steelborg')

    print(f"🔄 run_mass_generation_auto: используем domain='{effective_domain}', site='{effective_site}'")

    from phases.phase3 import BlockManager
    block_manager = BlockManager(
        domain_name=effective_domain,   # ← Явная передача!
        site_name=effective_site
    )

    blocks = block_manager.get_all_blocks()
    print(f"📦 Блоков из ДОМЕНА (в автогенерации): {len(blocks)} | domain={effective_domain}")

    if len(blocks) == 0:
        print(f"❌ Нет блоков в домене '{effective_domain}'!")
        return {"success": False, "message": f"Нет созданных блоков в домене {effective_domain}.", "count": 0}

    print(f"   ID блоков: {list(blocks.keys())}")

    # ========== СОБИРАЕМ AI ПЕРЕМЕННЫЕ ==========
    ai_vars = []
    for block_id, block in blocks.items():
        variables_data = block.get("variables_data", {})
        for var_name, var_data in variables_data.items():
            if var_data.get("type") == "ai":
                ai_vars.append({
                    "block_id": block_id,
                    "var_name": var_name,
                    "block": block,
                    "var_data": var_data
                })

    print(f"🤖 AI переменных: {len(ai_vars)}")

    if not ai_vars:
        return {"success": True, "message": "Нет AI переменных", "count": 0}

    # ========== ПРОВЕРКА СУЩЕСТВУЮЩИХ ИНСТРУКЦИЙ ==========
    if skip_existing and category:
        all_exist = True
        for item in ai_vars:
            has_instr = has_instructions_for_category(item["block_id"], item["var_name"], category, context)
            if not has_instr:
                all_exist = False
                break

        if all_exist:
            print(f"⏭️ Пропуск генерации - инструкции уже существуют для категории '{category}'")
            return {
                "success": True,
                "message": f"✅ Инструкции уже существуют для категории '{category}'. Генерация пропущена.",
                "count": 0,
                "skipped": True
            }

    # ========== ЗАПУСК ГЕНЕРАЦИИ ==========
    success_count = 0
    error_count = 0
    errors_list = []
    total_ai_vars = len(ai_vars)

    for idx, item in enumerate(ai_vars):
        block_id = item["block_id"]
        var_name = item["var_name"]
        block = item["block"]
        var_data = item["var_data"]
        provider = var_data.get("ai_provider", "deepseek")

        print(f"\n🚀 [{idx + 1}/{total_ai_vars}] Генерация для {block_id}/{var_name}")

        if skip_existing and category:
            if has_instructions_for_category(block_id, var_name, category, context):
                print(f"⏭️ Пропуск - уже есть инструкции")
                continue

        try:
            if block.get("block_type") == "characteristic":
                result = batch_generate_for_characteristic_with_data(
                    block_id=block_id,
                    var_name=var_name,
                    var_data=var_data,
                    block=block,
                    provider=provider,
                    category=category,
                    characteristics=characteristics,
                    context=context,
                    app_state=app_state
                )
            else:
                result = batch_generate_for_other_with_data(
                    block_id=block_id,
                    var_name=var_name,
                    var_data=var_data,
                    block=block,
                    provider=provider,
                    category=category,
                    context=context,
                    app_state=app_state
                )

            success_count += result.get("success", 0)
            error_count += result.get("errors", 0)

            if result.get("error"):
                errors_list.append({
                    "block": block.get("name", block_id),
                    "var": var_name,
                    "error": result.get("error")
                })

            print(f"   Результат: success={result.get('success', 0)}, errors={result.get('errors', 0)}")

        except Exception as e:
            error_count += 1
            errors_list.append({
                "block": block.get("name", block_id),
                "var": var_name,
                "error": str(e)
            })
            print(f"   ❌ Exception: {e}")

    force_save_phase3_blocks(app_state)

    # ========== УСТАНОВКА ФЛАГА ==========
    if context is not None and hasattr(context, 'set_phase_data'):
        # ✅ БЕЗОПАСНО ПОЛУЧАЕМ INSTRUCTIONS
        ai_mgr = st.session_state.get('ai_instruction_manager')
        ai_instructions = ai_mgr.instructions if ai_mgr and hasattr(ai_mgr, 'instructions') else {}

        context.set_phase_data(3, {
            'phase3_generated': True,
            'blocks_count': len(blocks),
            'ai_instructions': ai_instructions
        })
        context.save()
        print(f"   ✅ Установлен phase3_generated = True в контексте")
    # Перезагружаем инструкции
    if 'ai_instruction_manager' in st.session_state:
        st.session_state.ai_instruction_manager.reload()

    print(f"\n✅ run_mass_generation_auto END: success={success_count}, errors={error_count}")

    return {
        "success": True,
        "message": f"Сгенерировано: {success_count}, Ошибок: {error_count}",
        "count": success_count,
        "errors": error_count,
        "errors_list": errors_list,
        "skipped": success_count == 0 and error_count == 0 and len(ai_vars) > 0,
        "phase3_data": {
            "phase3_generated": True,
            "blocks_count": len(blocks)
        }
    }

def check_all_instructions_exist():
    """Проверяет, есть ли AI-инструкции для всех AI-переменных для текущей категории"""
    phase2_data = get_phase2_data()
    current_category = phase2_data.get('category', '')

    if not current_category:
        return False

    ai_vars = get_all_ai_variables()
    if not ai_vars:
        return False

    missing_count = 0
    for block_id, var_name, block, var_data in ai_vars:
        if not has_instructions_for_category(block_id, var_name, current_category):
            missing_count += 1

    return missing_count == 0

def show_all_ai_instructions_for_category():
    """
    Отображает все сгенерированные AI-инструкции для текущей категории.
    Инструкции группируются по блокам и переменным, доступно редактирование.
    """
    phase2_data = get_phase2_data()
    category = phase2_data.get('category', '').strip()
    if not category:
        st.warning("⚠️ Категория не загружена. Сначала выполните фазу 2.")
        return

    if 'ai_instruction_manager' not in st.session_state:
        st.error("❌ Менеджер AI-инструкций не инициализирован.")
        return

    blocks = st.session_state.block_manager.get_all_blocks()
    found = False

    st.subheader(f"📋 Все сгенерированные инструкции для категории: **{category}**")
    st.markdown("---")

    for block_id, block in blocks.items():
        variables_data = block.get("variables_data", {})
        for var_name, var_data in variables_data.items():
            if var_data.get("type") == "ai":
                # Проверяем, есть ли инструкции для этой категории
                if has_instructions_for_category(block_id, var_name, category):
                    found = True
                    block_name = block.get("name", block_id)
                    st.markdown(f"### 🧱 Блок: {block_name}  |  Переменная: `{var_name}`")
                    # Используем существующую функцию для отображения и редактирования
                    show_ai_instructions_full(block_id, var_name, block)
                    st.divider()

    if not found:
        st.info(f"📭 Нет сгенерированных инструкций для категории «{category}».")
def main(app_state=None, settings_mode=False, context=None, show_instructions_only=False):
    load_css()

    # ✅ ПРИНУДИТЕЛЬНАЯ СИНХРОНИЗАЦИЯ ДОМЕНА ИЗ ФАЙЛА
    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    user_id = st.session_state.get('user_id')

    # ✅ ЗАГРУЖАЕМ НАСТРОЙКИ ИЗ ФАЙЛА ПОЛЬЗОВАТЕЛЯ
    if user_id:
        settings = dm.load_user_settings(user_id)
        saved_domain = settings.get('selected_domain', 'default')
        saved_site = settings.get('selected_site', 'steelborg')

        # ✅ ОБНОВЛЯЕМ session_state из файла
        st.session_state.current_domain = saved_domain
        st.session_state.selected_domain = saved_domain
        st.session_state.current_site = saved_site
        st.session_state.selected_site = saved_site
        st.session_state[f'domain_system_{saved_site}'] = saved_domain

        # ✅ ОБНОВЛЯЕМ domain_manager
        dm.site_name = saved_site
        dm.current_domain = saved_domain
        dm.selected_domain = saved_domain
        dm.selected_site = saved_site

        print(f"✅ Phase3 загружен домен из файла: {saved_domain}, сайт: {saved_site}")
    else:
        saved_domain = st.session_state.get('current_domain', 'default')
        saved_site = st.session_state.get('current_site', 'steelborg')
        print(f"⚠️ Phase3: user_id не найден, использую домен по умолчанию: {saved_domain}")

    # ========== ИСПОЛЬЗУЕМ ЗАГРУЖЕННЫЕ ЗНАЧЕНИЯ ==========
    current_domain = st.session_state.get('current_domain', 'default')
    current_site = st.session_state.get('current_site', 'steelborg')

    # ✅ ОБНОВЛЯЕМ AIInstructionManager с правильным доменом
    from ai_settings.ai_module import AIInstructionManager

    domain_key = f"ai_mgr_{current_site}_{current_domain}"
    if st.session_state.get('ai_mgr_domain_key') != domain_key:
        st.session_state.ai_instruction_manager = AIInstructionManager(
            domain_name=current_domain,
            site_name=current_site
        )
        st.session_state.ai_mgr_domain_key = domain_key
        print(f"🔄 AIInstructionManager обновлён для домена {current_domain}")

    # ✅ СОЗДАЕМ BlockManager ТОЛЬКО ОДИН РАЗ
    # ✅ СОЗДАЕМ BlockManager
    # ✅ СОЗДАЕМ BlockManager
    if ('block_manager' not in st.session_state or
            st.session_state.get('_bm_domain_key') != f"{current_site}_{current_domain}"):

        st.session_state.block_manager = BlockManager(
            domain_name=current_domain,
            site_name=current_site
        )
        st.session_state._bm_domain_key = f"{current_site}_{current_domain}"
        print(f"📦 Создан новый BlockManager для домена '{current_domain}'")
    else:
        st.session_state.block_manager.load_blocks()
        print(f"📦 Перезагружены блоки для домена '{current_domain}'")

    # ====================== ОТЛАДКА ======================
    current_blocks = st.session_state.block_manager.get_all_blocks()
    print(f"📊 ЗАГРУЖЕНО БЛОКОВ ИЗ ДОМЕНА: {len(current_blocks)}")
    if current_blocks:
        print(f"   Блоки: {list(current_blocks.keys())}")
    else:
        print(f"   ⚠️ Блоков в домене НЕТ")
    # ====================================================
    if show_instructions_only:
        show_all_ai_instructions_for_category()
        return
    # === ЗАЩИТА ОТ АВТОМАТИЧЕСКОГО СОЗДАНИЯ ДЕФОЛТНЫХ БЛОКОВ ===
    is_auto_mode = context is not None and hasattr(context, 'project_id')

    # Проверка наличия блоков
    blocks_count = len(st.session_state.block_manager.get_all_blocks())

    if blocks_count == 0:
        if is_auto_mode:
            # АВТОГЕНЕРАЦИЯ - НЕ СОЗДАЕМ!
            st.error("""
            ## ❌ В домене нет блоков!
            
            Для автогенерации необходимо:
            1. Запустить проект в ручном режиме
            2. Создать блоки в фазе 3
            3. Сохранить настройки
            4. Затем использовать автогенерацию
            """)
            return {'success': False, 'blocks_count': 0, 'message': 'Нет блоков в домене'}
        else:
            # РУЧНОЙ РЕЖИМ - показываем кнопку создания
            st.warning("⚠️ Нет созданных блоков. Создайте первый блок ниже.")
            if st.button("➕ Создать первый блок", use_container_width=True):
                new_id, new_block, vars_data = st.session_state.block_manager.create_new_block()
                st.session_state.block_manager.save_block(new_block, vars_data)
                st.rerun()
            return {'success': False, 'blocks_count': 0, 'message': 'Нет созданных блоков'}
    # ========================================================

    # ✅ УБИРАЕМ ВТОРОЙ ВЫЗОВ load_blocks() - он уже вызван в __init__
    # st.session_state.block_manager.load_blocks()  # ← ЗАКОММЕНТИРОВАТЬ!

    # Проверяем, что блоки загрузились
    current_blocks = st.session_state.block_manager.get_all_blocks()
    print(f"📦 ИТОГО загружено блоков из домена '{current_domain}': {len(current_blocks)}")

    # ... остальной код main() без изменений ...

    # Инициализация остальных менеджеров
    if 'variable_manager' not in st.session_state:
        st.session_state.variable_manager = VariableManager(st.session_state.block_manager)

    if 'dynamic_var_manager' not in st.session_state:
        st.session_state.dynamic_var_manager = DynamicVariableManager()

    if 'session_temp_vars' not in st.session_state:
        st.session_state.session_temp_vars = {}

    # ✅ Инициализируем AI менеджеры с передачей app_state и правильного контекста
    init_ai_managers(app_state, context)

    # ... остальной код без изменений ...

    # ========== ЗАГРУЖАЕМ ДАННЫЕ ФАЗ 1 И 2 ==========
    # ========== ЗАГРУЖАЕМ ДАННЫЕ ФАЗ 1 И 2 ИЗ ПРОЕКТА (app_state) ==========
    # ========== ЗАГРУЖАЕМ ДАННЫЕ ФАЗ 1 И 2 ==========
    ctx_data = _get_context_data(context, st.session_state)

    # ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
    if ctx_data['has_context'] and context is not None:
        phase1_data = context.get_phase_data(1)
        if phase1_data:
            st.session_state.loaded_data = {
                'category': phase1_data.get('category', ''),
                'characteristics': phase1_data.get('characteristics', [])
            }
            print(f"📂 Загружена фаза 1 из контекста: категория '{phase1_data.get('category', '')}'")

        phase2_data = context.get_phase_data(2)
        if phase2_data:
            st.session_state.phase2_data = phase2_data
            print(f"📂 Загружена фаза 2 из контекста: категория '{phase2_data.get('category', '')}'")

    # ПРИОРИТЕТ 2: ИЗ APP_STATE
    elif app_state:
        phase1_data = app_state.get_phase_data(1)
        if phase1_data:
            st.session_state.loaded_data = {
                'category': phase1_data.get('category', ''),
                'characteristics': phase1_data.get('characteristics', [])
            }
            print(f"📂 Загружена фаза 1 из проекта: категория '{phase1_data.get('category', '')}'")

        phase2_data = app_state.get_phase_data(2)
        if phase2_data:
            st.session_state.phase2_data = phase2_data
            print(f"📂 Загружена фаза 2 из проекта: категория '{phase2_data.get('category', '')}'")

    # ========== ОСНОВНАЯ ЛОГИКА ==========

    # РЕЖИМ НАСТРОЕК - показываем редактор блоков
    if settings_mode:
        st.markdown("### 📝 Настройка блоков и шаблонов (Фаза 3)")
        st.caption("Настройте блоки и шаблоны промптов для автоматической генерации")
        st.markdown("---")
        show_edit_mode(app_state)
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Сохранить настройки фазы 3", type="primary", use_container_width=True):
                if save_phase3_settings(app_state):
                    st.success("✅ Настройки фазы 3 сохранены в проект!")
                else:
                    st.error("❌ Ошибка сохранения настроек")
        with col2:
            if st.button("← Назад к настройкам проекта", use_container_width=True):
                st.session_state.show_settings = True
                st.rerun()
        st.markdown("---")
        return {'success': True, 'blocks_count': len(current_blocks), 'message': 'Режим настроек'}

    # ========== РУЧНОЙ РЕЖИМ ==========
    # Проверка наличия данных
    phase2_data = get_phase2_data()
    if not phase2_data or not phase2_data.get('category'):
        st.warning("⚠️ Нет данных из фазы 2. Сначала настройте фазу 2.")
        return {'success': False, 'blocks_count': 0, 'message': 'Нет данных из фазы 2'}

    characteristics_data = get_characteristics_data()
    if not characteristics_data:
        st.warning("⚠️ Нет данных характеристик из фазы 1. Сначала настройте фазу 1.")
        return {'success': False, 'blocks_count': 0, 'message': 'Нет данных из фазы 1'}

    # Проверка наличия блоков
    # Проверка наличия блоков
    if len(current_blocks) == 0:
        st.warning("⚠️ Нет созданных блоков. Создайте первый блок ниже.")
        if st.button("➕ Создать первый блок", use_container_width=True):
            print("🛠 Пользователь нажал 'Создать первый блок'")
            new_id, new_block, vars_data = st.session_state.block_manager.create_new_block()
            st.session_state.block_manager.save_block(new_block, vars_data)
            st.rerun()
        return {'success': False, 'blocks_count': 0, 'message': 'Нет созданных блоков'}

    # РУЧНОЙ РЕЖИМ - показываем ПОЛНЫЙ РЕДАКТОР
    st.markdown("### 📝 Редактор блоков и переменных (Фаза 3)")
    st.caption("Настройте блоки, переменные и AI-генерацию")
    st.markdown("---")

    # Показываем загруженную категорию
    if st.session_state.loaded_data:
        category = st.session_state.loaded_data.get('category', '')
        if category:
            st.success(f"✅ Загружена категория: **{category}**")

    # Показываем ПОЛНЫЙ РЕДАКТОР (все 5 вкладок)
    show_edit_mode(app_state)

    st.markdown("---")

    # Кнопки сохранения и перехода
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("💾 Сохранить изменения", type="primary", use_container_width=True):
            force_save_phase3_blocks(app_state)
            if app_state:
                app_state.save_project()
            st.success("✅ Настройки фазы 3 сохранены!")
            st.rerun()

    with col2:
        if st.button("🔄 Перезагрузить блоки", use_container_width=True):
            st.session_state.block_manager.load_blocks()
            st.rerun()

    # ========== КНОПКА ПЕРЕХОДА К ФАЗЕ 4 ==========
    with col3:
        # Проверяем, сохранены ли данные
        phase3_saved = False
        if 'app_data' in st.session_state and 'phase3' in st.session_state.app_data:
            phase3_data = st.session_state.app_data['phase3']
            if phase3_data and phase3_data.get('blocks_count', 0) > 0:
                phase3_saved = True

        if not phase3_saved and 'block_manager' in st.session_state:
            blocks = st.session_state.block_manager.get_all_blocks()
            if blocks and len(blocks) > 0:
                phase3_saved = True

        if phase3_saved:
            if st.button("➡️ Фаза 4", type="primary", use_container_width=True, help="Перейти к генерации промптов"):
                force_save_phase3_blocks(app_state)
                if app_state:
                    app_state.save_project()
                st.session_state.current_phase = 4
                if app_state:
                    app_state.current_phase = 4
                st.rerun()
        else:
            st.button("➡️ Фаза 4", disabled=True, use_container_width=True, help="Сначала создайте и сохраните блоки")

    # Сохранение после любого взаимодействия
    if app_state:
        force_save_phase3_blocks(app_state)
        save_data_to_app_state()
        blocks = st.session_state.block_manager.get_all_blocks()
        if blocks:
            dm = st.session_state.domain_manager
            blocks_data = {}
            for block_id, block in blocks.items():
                blocks_data[block_id] = {
                    'block_id': block_id,
                    'name': block.get('name', ''),
                    'block_type': block.get('block_type', 'other'),
                    'description': block.get('description', ''),
                    'template': block.get('template', ''),
                    'variables': block.get('variables', []),
                    'settings': block.get('settings', {}),
                    'variables_data': block.get('variables_data', {})
                }
            dm.save_phase_data(3, {
                'blocks': blocks_data,
                'blocks_count': len(blocks),
                'characteristic_blocks': len([b for b in blocks.values() if b.get('block_type') == 'characteristic']),
                'other_blocks': len([b for b in blocks.values() if b.get('block_type') == 'other']),
                'settings_saved': True,
                'saved_at': datetime.now().isoformat()
            })
            app_state.save_project()

    return {
        'success': True,
        'blocks_count': len(current_blocks),
        'message': f'Редактор блоков. Блоков: {len(current_blocks)}'
    }



    # Добавить в phase3.py

def get_all_ai_variables_with_details():
    """Возвращает список всех AI переменных с деталями для выбора"""
    if 'block_manager' not in st.session_state:
        return []

    blocks = st.session_state.block_manager.get_all_blocks()
    ai_vars = []

    for block_id, block in blocks.items():
        block_name = block.get('name', block_id)
        variables_data = block.get("variables_data", {})

        for var_name, var_data in variables_data.items():
            if var_data.get("type") == "ai":
                ai_vars.append((
                    block_name,      # имя блока для отображения
                    var_name,        # имя переменной
                    block_id,        # ID блока
                    var_data         # данные переменной
                ))

    return ai_vars
def show_ai_variables_overview():
    """Отображает обзор всех AI-переменных с возможностью выбора для массовой генерации"""
    st.subheader("🤖 Все AI-переменные")

    if 'ai_instruction_manager' not in st.session_state:
        init_ai_managers()

    phase2_data = get_phase2_data()
    current_category = phase2_data.get('category', '')

    if current_category:
        all_exist = check_all_instructions_exist()
        if all_exist:
            st.success(f"✅ Для категории **{current_category}** уже есть сгенерированные инструкции")
        else:
            st.info(f"📝 Для категории **{current_category}** ещё нет инструкций.")

    blocks = st.session_state.block_manager.get_all_blocks()
    ai_vars = []
    for block_id, block in blocks.items():
        variables_data = block.get("variables_data", {})
        for var_name, var_data in variables_data.items():
            if var_data.get("type") == "ai":
                ai_vars.append((block_id, block, var_name, var_data))

    if not ai_vars:
        st.info("Нет AI-переменных.")
        return

    # Инициализация
    if 'selected_ai_vars' not in st.session_state:
        st.session_state.selected_ai_vars = set()

    # --- Кнопки управления ---
    col1, col2, col3, col4 = st.columns([1, 1, 2, 4])

    with col1:
        if st.button("✅ Выбрать всё", key="select_all_ai", use_container_width=True):
            st.session_state.selected_ai_vars = {
                f"{block_id}||{var_name}" for block_id, _, var_name, _ in ai_vars
            }
            st.rerun()

    with col2:
        if st.button("❌ Снять всё", key="deselect_all_ai", use_container_width=True):
            st.session_state.selected_ai_vars.clear()
            st.rerun()

    # Выбор провайдера
    with col3:
        available_providers = ["agentplatform", "deepseek"]
        provider_labels = {"agentplatform": "AgentPlatform", "deepseek": "DeepSeek"}
        mass_provider = st.session_state.get("mass_ai_provider", "agentplatform")
        mass_provider = st.selectbox(
            "Провайдер",
            available_providers,
            format_func=lambda x: provider_labels.get(x, x),
            index=available_providers.index(mass_provider) if mass_provider in available_providers else 0,
            key="mass_ai_provider_select"
        )
        st.session_state["mass_ai_provider"] = mass_provider

    with col4:
        selected_count = len(st.session_state.selected_ai_vars)
        button_label = f"🚀 Массовая генерация ({selected_count})" if selected_count > 0 else "🚀 Массовая генерация"

        if st.button(button_label, type="primary", use_container_width=True, key="mass_gen_ai"):
            selected = list(st.session_state.selected_ai_vars)
            if selected:
                progress_bar = st.progress(0)
                status_text = st.empty()

                success_total = 0
                errors_total = 0
                results_details = []
                total_items = len(selected)

                for idx, item in enumerate(selected):
                    progress = (idx + 1) / total_items
                    progress_bar.progress(progress)
                    status_text.text(f"Генерация {idx + 1} из {total_items}...")

                    if "||" in item:
                        b_id, v_name = item.split("||", 1)
                    else:
                        parts = item.split("_", 1)
                        if len(parts) == 2:
                            b_id, v_name = parts[0], parts[1]
                        else:
                            errors_total += 1
                            results_details.append({"item": item, "error": "Неверный формат ключа"})
                            continue

                    block = st.session_state.block_manager.get_block(b_id)
                    if not block:
                        errors_total += 1
                        results_details.append({"item": item, "error": f"Блок {b_id} не найден"})
                        continue

                    variables_data = block.get("variables_data", {})
                    var_data = variables_data.get(v_name)
                    if not var_data:
                        errors_total += 1
                        results_details.append({"item": item, "error": f"Переменная {v_name} не найдена"})
                        continue

                    try:
                        if block.get("block_type") == "characteristic":
                            result = batch_generate_for_characteristic(b_id, v_name, var_data, block, mass_provider)
                        else:
                            result = batch_generate_for_other(b_id, v_name, var_data, block, mass_provider)

                        success_total += result.get("success", 0)
                        errors_total += result.get("errors", 0)
                        results_details.append({
                            "item": item,
                            "success": result.get("success", 0),
                            "errors": result.get("errors", 0)
                        })
                    except Exception as e:
                        errors_total += 1
                        results_details.append({"item": item, "error": str(e)})

                progress_bar = st.progress(0)
                status_text = st.empty()

                if 'ai_instruction_manager' in st.session_state:
                    st.session_state.ai_instruction_manager.reload()

                st.success(f"✅ Массовая генерация завершена! Успешно: {success_total}, ошибок: {errors_total}")

                if errors_total > 0:
                    with st.expander(f"📋 Детали ошибок ({errors_total})", expanded=False):
                        for detail in results_details:
                            if "error" in detail:
                                st.error(f"**{detail['item']}**: {detail['error']}")
                            elif detail.get("errors", 0) > 0:
                                st.warning(f"**{detail['item']}**: успешно {detail['success']}, ошибок {detail['errors']}")

                st.rerun()
            else:
                st.warning("⚠️ Не выбрано ни одной переменной")

    st.divider()

    # Таблица переменных
    cols = st.columns([0.5, 2, 2, 1, 2, 3])
    cols[0].write("")
    cols[1].write("**Переменная**")
    cols[2].write("**Блок**")
    cols[3].write("**Тип**")
    cols[4].write("**Статус**")
    cols[5].write("**Действия**")

    for idx, (block_id, block, var_name, var_data) in enumerate(ai_vars):
        unique_key = f"{block_id}||{var_name}"
        checkbox_key = f"ai_chk_{idx}_{block_id}_{var_name}"

        col_chk, col_var, col_block, col_type, col_status, col_action = st.columns([0.5, 2, 2, 1, 2, 3])

        with col_chk:
            # Прямое присвоение через session_state
            st.session_state[f"_temp_{checkbox_key}"] = unique_key in st.session_state.selected_ai_vars

            if st.checkbox(
                    "Показать переменные",
                    key=f"_temp_{checkbox_key}",
                    label_visibility="collapsed"
            ):
                st.session_state.selected_ai_vars.add(unique_key)
            else:
                st.session_state.selected_ai_vars.discard(unique_key)

        with col_var:
            st.write(f"`{var_name}`")
        with col_block:
            st.write(block.get("name", block_id)[:30])
        with col_type:
            st.write("📊" if block.get("block_type") == "characteristic" else "📄")
        with col_status:
            st.success("✅ сгенерирована") if has_ai_values(block_id, var_name) else st.error("❌ не сгенерирована")
        with col_action:
            if st.button("🚀", key=f"gen_single_{block_id}_{var_name}"):
                # одиночная генерация
                pass
    if st.button("📋 Показать все инструкции для текущей категории", use_container_width=True):
        st.session_state.phase3_tab = 6  # индекс вкладки "Все инструкции"
        st.rerun()
def show_edit_mode(app_state=None):
    # Проверяем, нужно ли переключиться на редактирование переменной
    if st.session_state.get('edit_variable_direct', False):
        # Показываем сразу редактор переменной
        st.button("← Назад к обзору переменных",
                  on_click=lambda: st.session_state.pop('edit_variable_direct', None),
                  use_container_width=True)
        st.markdown("---")

        # Получаем данные о переменной
        var_info = st.session_state.edit_variable_direct
        block_id = var_info['block_id']
        var_name = var_info['var_name']
        var_type = var_info.get('type', 'static')

        # Получаем блок
        block = st.session_state.block_manager.get_block(block_id)
        if not block:
            st.error("Блок не найден")
            st.session_state.pop('edit_variable_direct', None)
            st.rerun()

        # Получаем данные переменной
        variables_data = block.get("variables_data", {})
        var_data = variables_data.get(var_name, {})

        # Показываем редактор в зависимости от типа
        if var_type == 'static':
            show_static_variable_editor(block_id, var_name, var_data, block)
        elif var_type == 'ai':
            show_ai_variable_editor(block_id, var_name, var_data, block)
        elif var_type == 'dynamic':
            show_dynamic_variable_info(var_name)

        return  # Важно! Не показываем остальной интерфейс

    # Проверяем, нужно ли переключиться на вкладку редактирования блока
    if st.session_state.get('switch_to_edit_tab', False):
        # Сбрасываем флаг
        st.session_state.switch_to_edit_tab = False
        # Показываем сразу вкладку редактирования
        show_edit_tab_directly = True
    else:
        show_edit_tab_directly = False

    if show_edit_tab_directly:
        # Показываем только вкладку редактирования
        st.button("← Назад к списку блоков",
                  on_click=lambda: setattr(st.session_state, 'show_only_edit', False),
                  use_container_width=True)
        st.markdown("---")
        show_block_editor()
    else:
        # Показываем все вкладки
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📋 Управление блоками",
            "✏️ Редактирование блока",
            "📊 Обзор переменных",
            "🌀 Редактирование глобальных переменных",
            "🤖 Управление AI‑переменными",
            "📋 Все инструкции"
        ])

        with tab1:
            show_blocks_management(app_state)

        with tab2:
            show_block_editor()

        with tab3:
            show_variables_overview()

        with tab4:
            show_dynamic_variables_editor()

        with tab5:
            show_ai_variables_overview()
        with tab6:
            show_all_ai_instructions_for_category()
    # Сохраняем блоки после любых изменений


def show_dynamic_variables_editor():
    """Редактор глобальных переменных с поддержкой временных сессионных переменных"""

    # Инициализация менеджера глобальных переменных
    if 'dynamic_var_manager' not in st.session_state:
        st.session_state.dynamic_var_manager = DynamicVariableManager()

    dynamic_manager = st.session_state.dynamic_var_manager

    # Получаем все переменные (постоянные и временные)
    permanent_vars = dynamic_manager.dynamic_vars
    session_vars = dynamic_manager.session_var_manager.get_all_session_vars()

    st.subheader("🌀 Управление глобальными переменными")

    # Создаем табы для постоянных и временных переменных
    tab_permanent, tab_session = st.tabs([
        f"📁 Постоянные ({len(permanent_vars)})",
        f"⏰ Временные (сессия) ({len(session_vars)})"
    ])

    with tab_permanent:
        st.markdown("""
        **Постоянные переменные** - сохраняются в файл и доступны после перезапуска.
        """)

        # Список постоянных переменных
        if permanent_vars:
            # Создаем колонки для отображения
            cols = st.columns(4)
            for idx, (var_name, var_data) in enumerate(permanent_vars.items()):
                with cols[idx % 4]:
                    source = var_data.get("source", "config")
                    source_icon = {
                        "config": "⚙️",
                        "data": "📊",
                        "processing": "🔄",
                        "unknown": "❓"
                    }.get(source, "❓")

                    st.markdown(f"""
                    <div style="
                        background-color: #f8f9fa;
                        padding: 10px;
                        border-radius: 8px;
                        border: 1px solid #dee2e6;
                        margin-bottom: 10px;
                    ">
                        <div style="font-weight: bold; color: #495057;">{{{var_name}}}</div>
                        <div style="font-size: 0.8em; color: #6c757d; margin-top: 5px;">
                            {var_data.get('description', '')}
                        </div>
                        <div style="font-size: 0.7em; color: #adb5bd; margin-top: 5px;">
                            {source_icon} {source} • {len(var_data.get('values', []))} значений
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("Нет постоянных переменных")

        st.divider()

        # Редактирование конкретной постоянной переменной
        if permanent_vars:
            st.markdown("### ✏️ Редактирование постоянной переменной")
            selected_var = st.selectbox(
                "Выберите переменную:",
                list(permanent_vars.keys()),
                key="permanent_var_select"
            )

            if selected_var:
                var_data = permanent_vars[selected_var]

                with st.form(key=f"edit_permanent_{selected_var}"):
                    description = st.text_input("Описание:", value=var_data.get("description", ""))
                    source = st.selectbox(
                        "Источник:",
                        ["config", "data", "processing"],
                        index=["config", "data", "processing"].index(var_data.get("source", "config"))
                    )

                    current_values = var_data.get("values", [])
                    values_text = "\n".join(current_values)
                    new_values = st.text_area("Значения (каждое с новой строки):", value=values_text, height=150)

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.form_submit_button("💾 Сохранить", use_container_width=True):
                            updated_data = {
                                "name": selected_var,
                                "description": description,
                                "type": "dynamic",
                                "source": source,
                                "values": [v.strip() for v in new_values.split("\n") if v.strip()]
                            }
                            if dynamic_manager.update_dynamic_variable(selected_var, updated_data):
                                st.success(f"✅ Переменная '{selected_var}' сохранена!")
                                st.rerun()
                    with col2:
                        if st.form_submit_button("⏰ Создать временную копию", use_container_width=True):
                            # Создаем временную копию
                            temp_var_name = f"{selected_var}_temp_{int(time.time())}"
                            dynamic_manager.create_session_variable(temp_var_name, var_data)
                            st.success(f"✅ Создана временная переменная '{temp_var_name}'")
                            st.rerun()
                    with col3:
                        if st.form_submit_button("🗑️ Удалить", type="secondary", use_container_width=True):
                            if dynamic_manager.update_dynamic_variable(selected_var, None):
                                st.success(f"✅ Переменная '{selected_var}' удалена!")
                                st.rerun()

    with tab_session:
        st.markdown("""
        **Временные переменные** - существуют только в текущей сессии и исчезают после перезагрузки.
        Подходят для тестирования и временных правок.
        """)

        # Кнопка для массовой вставки во все блоки
        if session_vars:
            col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 1])
            with col_btn1:
                if st.button("📌 Вставить ВО ВСЕ блоки (в начало)", type="primary", use_container_width=True):
                    insert_session_vars_to_all_blocks(session_vars)
            with col_btn2:
                if st.button("🗑️ Очистить все временные переменные", use_container_width=True):
                    dynamic_manager.clear_all_session_variables()
                    st.success("✅ Все временные переменные очищены!")
                    st.rerun()
            with col_btn3:
                if st.button("💾 Сохранить все в постоянные", use_container_width=True):
                    saved_count = 0
                    for var_name in list(session_vars.keys()):
                        if dynamic_manager.promote_session_to_permanent(var_name):
                            saved_count += 1
                    st.success(f"✅ Сохранено {saved_count} переменных в постоянные!")
                    st.rerun()

            st.divider()

            # Отображение временных переменных
            for var_name, var_data in session_vars.items():
                with st.expander(f"⏰ {var_name}", expanded=True):
                    col_edit, col_del = st.columns([4, 1])
                    with col_edit:
                        st.write(f"**Описание:** {var_data.get('description', 'Нет описания')}")
                        st.write(f"**Источник:** {var_data.get('source', 'config')}")

                        # Отображаем значения
                        values = var_data.get("values", [])
                        st.write(f"**Значения ({len(values)}):**")
                        for val in values:
                            st.write(f"- {val}")
                    with col_del:
                        if st.button("❌", key=f"del_session_{var_name}", help="Удалить временную переменную"):
                            dynamic_manager.delete_session_variable(var_name)
                            st.rerun()
        else:
            st.info("Нет временных переменных. Создайте их в разделе 'Создание временной переменной' ниже.")

        st.divider()

        # Создание новой временной переменной
        st.markdown("### ➕ Создать временную переменную")
        with st.form("create_session_var_form"):
            new_var_name = st.text_input("Имя переменной (без фигурных скобок):")
            new_var_desc = st.text_input("Описание:")
            new_var_source = st.selectbox("Источник:", ["config", "data", "processing"])
            new_var_values = st.text_area("Значения (каждое с новой строки):", height=150)

            col_create1, col_create2 = st.columns(2)
            with col_create1:
                if st.form_submit_button("➕ Создать временную", use_container_width=True):
                    if new_var_name:
                        new_var_data = {
                            "name": new_var_name,
                            "description": new_var_desc or f"Временная переменная {new_var_name}",
                            "type": "dynamic",
                            "source": new_var_source,
                            "values": [v.strip() for v in new_var_values.split("\n") if v.strip()]
                        }
                        dynamic_manager.create_session_variable(new_var_name, new_var_data)
                        st.success(f"✅ Создана временная переменная '{new_var_name}'")
                        st.rerun()
                    else:
                        st.error("❌ Введите имя переменной")
            with col_create2:
                if st.form_submit_button("📌 Создать и вставить во все блоки", use_container_width=True):
                    if new_var_name:
                        new_var_data = {
                            "name": new_var_name,
                            "description": new_var_desc or f"Временная переменная {new_var_name}",
                            "type": "dynamic",
                            "source": new_var_source,
                            "values": [v.strip() for v in new_var_values.split("\n") if v.strip()]
                        }
                        dynamic_manager.create_session_variable(new_var_name, new_var_data)
                        # Вставляем во все блоки
                        insert_session_var_to_all_blocks(new_var_name, new_var_data)
                        st.success(f"✅ Создана временная переменная '{new_var_name}' и вставлена во все блоки!")
                        st.rerun()
                    else:
                        st.error("❌ Введите имя переменной")


def insert_session_vars_to_all_blocks(session_vars):
    """Вставляет все временные переменные во все блоки (в начало каждого блока)"""

    blocks = st.session_state.block_manager.get_all_blocks()
    if not blocks:
        st.warning("Нет блоков для вставки")
        return

    modified_blocks = 0
    total_insertions = 0

    for block_id, block in blocks.items():
        template = block.get("template", "")

        # Формируем строку для вставки в начало блока
        insert_lines = []
        for var_name, var_data in session_vars.items():
            # Берем первое значение переменной для примера
            first_value = var_data.get("values", [""])[0] if var_data.get("values") else f"{{{var_name}}}"
            insert_lines.append(f"{{{var_name}}} - {first_value}")

        if insert_lines:
            # Вставляем в начало шаблона
            new_template = "\n".join(insert_lines) + "\n\n" + template

            # Обновляем блок
            block["template"] = new_template

            # Добавляем переменные в список variables, если их там нет
            variables = block.get("variables", [])
            for var_name in session_vars.keys():
                if var_name not in variables:
                    variables.append(var_name)
            block["variables"] = variables

            # Сохраняем блок
            if st.session_state.block_manager.save_block(block):
                modified_blocks += 1
                total_insertions += len(insert_lines)

    if modified_blocks > 0:
        st.success(f"✅ Вставлено {total_insertions} переменных в {modified_blocks} блоков!")
        st.session_state.block_manager.load_blocks()
        st.rerun()
    else:
        st.warning("Не удалось вставить переменные в блоки")


def insert_session_var_to_all_blocks(var_name, var_data):
    """Вставляет одну временную переменную во все блоки (в начало каждого блока)"""

    blocks = st.session_state.block_manager.get_all_blocks()
    if not blocks:
        return

    modified_blocks = 0

    for block_id, block in blocks.items():
        template = block.get("template", "")

        # Проверяем, есть ли уже такая переменная в шаблоне
        if f"{{{var_name}}}" not in template:
            # Формируем строку для вставки
            first_value = var_data.get("values", [""])[0] if var_data.get("values") else f"{{{var_name}}}"
            insert_line = f"{{{var_name}}} - {first_value}"

            # Вставляем в начало
            new_template = insert_line + "\n\n" + template

            # Обновляем блок
            block["template"] = new_template

            # Добавляем переменную в список variables
            variables = block.get("variables", [])
            if var_name not in variables:
                variables.append(var_name)
            block["variables"] = variables

            # Сохраняем блок
            if st.session_state.block_manager.save_block(block):
                modified_blocks += 1

    if modified_blocks > 0:
        st.session_state.block_manager.load_blocks()
def show_variables_overview():
    """Отображает все переменные (локальные и AI) с привязкой к блокам"""
    st.subheader("📊 Обзор всех переменных")

    blocks = st.session_state.block_manager.get_all_blocks()
    if not blocks:
        st.info("Нет созданных блоков")
        return

    # Собираем переменные
    all_vars = []
    for block_id, block in blocks.items():
        block_name = block.get("name", block_id)
        variables_data = block.get("variables_data", {})
        for var_name, var_data in variables_data.items():
            var_type = var_data.get("type", "static")
            if var_type in ["static", "ai"]:
                all_vars.append({
                    "block_id": block_id,
                    "block_name": block_name,
                    "var_name": var_name,
                    "type": var_type,
                    "values_count": len(var_data.get("values", [])),
                    "description": var_data.get("description", "")
                })

    if not all_vars:
        st.info("Нет локальных или AI-переменных")
        return

    # Фильтры
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        type_filter = st.multiselect(
            "Тип переменной",
            options=["static", "ai"],
            default=["static", "ai"],
            format_func=lambda x: "локальная" if x == "static" else "AI"
        )
    with col_f2:
        blocks_list = sorted(set(v["block_name"] for v in all_vars))
        block_filter = st.multiselect("Блок", options=blocks_list, default=[])

    filtered = [v for v in all_vars if v["type"] in type_filter]
    if block_filter:
        filtered = [v for v in filtered if v["block_name"] in block_filter]

    if filtered:
        st.markdown(f"**Найдено переменных: {len(filtered)}**")

        # Заголовки таблицы
        cols = st.columns([2, 2, 1, 1, 2, 2])
        cols[0].write("**Переменная**")
        cols[1].write("**Блок**")
        cols[2].write("**Тип**")
        cols[3].write("**Кол-во значений**")
        cols[4].write("**Описание**")
        cols[5].write("**Действия**")

        for var in filtered:
            row = st.columns([2, 2, 1, 1, 2, 2])
            row[0].write(f"`{var['var_name']}`")
            row[1].write(var['block_name'])
            row[2].write("📝" if var['type'] == "static" else "🤖")
            row[3].write(str(var['values_count']))
            row[4].caption(var['description'][:50] + ("..." if len(var['description']) > 50 else ""))
            with row[5]:
                if st.button("✏️", key=f"goto_{var['block_id']}_{var['var_name']}", help="Редактировать переменную"):
                    st.session_state.edit_variable_direct = {
                        'block_id': var['block_id'],
                        'var_name': var['var_name'],
                        'type': var['type']
                    }
                    st.rerun()
    else:
        st.info("Нет переменных, соответствующих фильтрам")
def show_blocks_management(app_state=None):
    """Управление блоками: список, создание, удаление"""
    st.subheader("📋 Управление блоками")

    blocks = st.session_state.block_manager.get_all_blocks()

    if not blocks:
        st.info("Блоки не найдены. Создайте первый блок.")

        # ========== СОЗДАНИЕ НОВОГО БЛОКА ==========
        # ========== СОЗДАНИЕ НОВОГО БЛОКА ==========
    st.markdown("### ➕ Создать новый блок")

    col_create1, col_create2, col_create3, col_create4 = st.columns([2.2, 2, 1.2, 1])

    with col_create1:
        base_block_options = ["(пустой блок)"] + list(blocks.keys())
        base_block = st.selectbox(
            "На основе блока:",
            base_block_options,
            format_func=lambda x: "(пустой блок)" if x == "(пустой блок)"
            else f"{blocks[x].get('name', x)} ({blocks[x].get('block_type', 'other')})",
            key="new_block_base"
        )

    with col_create2:
        block_type = st.selectbox(
            "Тип блока:",
            ["characteristic", "other"],
            format_func=lambda x: "Характеристика" if x == "characteristic" else "Другой блок",
            key="new_block_type"
        )

    with col_create3:
        characteristic_type = None
        if block_type == "characteristic":
            characteristic_type = st.selectbox(
                "Тип характеристики:",
                ["regular", "unique"],
                key="new_char_type"
            )

    with col_create4:
        if st.button("✅ Создать", key="create_new_block_button", use_container_width=True, type="primary"):
            print(f"🚀 Кнопка 'Создать' нажата! base_block={base_block}, type={block_type}")

            base_block_id = None if base_block == "(пустой блок)" else base_block

            new_block_id, new_block, variables_data = st.session_state.block_manager.create_new_block(base_block_id)

            new_block["block_type"] = block_type

            # Только устанавливаем тип — БЕЗ гигантских дефолтных шаблонов!
            if block_type == "characteristic" and characteristic_type:
                if "settings" not in new_block:
                    new_block["settings"] = {}
                new_block["settings"]["characteristic_type"] = characteristic_type
                print(f"   → characteristic_type установлен: {characteristic_type}")

            if st.session_state.block_manager.save_block(new_block, variables_data):
                st.success(f"✅ Создан новый блок: **{new_block['name']}**")
                force_save_phase3_blocks(app_state)
                st.session_state.current_edit_block = new_block_id
                st.session_state.switch_to_edit_tab = True
                st.rerun()
            else:
                st.error("❌ Ошибка создания блока")

    st.divider()

    # Список блоков
    st.markdown("### 📋 Список блоков")

    if blocks:
        # Фильтрация блоков
        filter_type = st.selectbox(
            "Фильтр по типу:",
            ["Все", "characteristic", "other"],
            format_func=lambda x: "Все" if x == "Все" else ("Характеристика" if x == "characteristic" else "Другие блоки")
        )

        filtered_blocks = blocks
        if filter_type != "Все":
            filtered_blocks = {k: v for k, v in blocks.items() if v.get("block_type") == filter_type}

        for block_id, block in filtered_blocks.items():
            block_type = block.get("block_type", "other")
            block_type_display = "Характеристика" if block_type == "characteristic" else "Другой блок"

            # Для characteristic блоков показываем дополнительную информацию
            char_type_info = ""
            if block_type == "characteristic":
                char_type = block.get("settings", {}).get("characteristic_type", "regular")
                char_type_info = f" • {char_type.upper()}"

            col_list1, col_list2, col_list3, col_list4 = st.columns([3, 2, 1, 1])

            with col_list1:
                st.write(f"**{block.get('name', 'Без названия')}**")
                st.caption(f"ID: {block_id}{char_type_info}")
                if block.get('description'):
                    st.caption(
                        block.get('description')[:100] + "..." if len(block.get('description')) > 100 else block.get(
                            'description'))

            with col_list2:
                st.markdown(f'<span class="block-type-chip block-type-{block_type}">{block_type_display}</span>',
                            unsafe_allow_html=True)

            with col_list3:
                if st.button("✏️", key=f"edit_{block_id}", help="Редактировать блок", use_container_width=True):
                    st.session_state.current_edit_block = block_id
                    st.session_state.switch_to_edit_tab = True  # Устанавливаем флаг
                    st.rerun()

            with col_list4:
                # Запрещаем удаление только стандартных блоков, если они есть
                if st.button("🗑️", key=f"delete_{block_id}", help="Удалить блок", use_container_width=True):
                    if st.session_state.block_manager.delete_block(block_id):
                        st.success(f"✅ Блок '{block.get('name', '')}' удален")
                        st.rerun()
    else:
        st.info("Нет созданных блоков")

# Добавьте эти функции в конец phase3.py

def show_static_variable_editor(block_id, var_name, var_data, block):
    """Редактор статической переменной"""

    st.subheader(f"📝 Редактирование статической переменной: `{var_name}`")

    with st.form(key=f"direct_edit_static_{block_id}_{var_name}"):
        description = st.text_input(
            "Описание переменной",
            value=var_data.get("description", "")
        )

        # Значения
        current_values = var_data.get("values", [])
        values_text = "\n".join(current_values)

        st.markdown("**Значения переменной (каждое с новой строки):**")
        new_values = st.text_area(
            "Значения",
            value=values_text,
            height=200,
            label_visibility="collapsed"
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.form_submit_button("💾 Сохранить", use_container_width=True):
                # Обновляем данные
                variables_data = block.get("variables_data", {})
                variables_data[var_name] = {
                    "name": var_name,
                    "description": description,
                    "type": "static",
                    "values": [v.strip() for v in new_values.split("\n") if v.strip()]
                }
                block["variables_data"] = variables_data

                if st.session_state.block_manager.save_block(block, variables_data):
                    st.success(f"✅ Переменная '{var_name}' сохранена")
                    force_save_phase3_blocks()
                    st.session_state.pop('edit_variable_direct', None)
                    st.rerun()

        with col2:
            if st.form_submit_button("🤖 В AI", use_container_width=True):
                # Преобразуем в AI
                variables_data = block.get("variables_data", {})
                variables_data[var_name] = {
                    "name": var_name,
                    "description": description,
                    "type": "ai",
                    "ai_prompt": "Сгенерируй текст...",
                    "ai_num_variants": 3,
                    "ai_provider": "openai",
                    "values": []
                }
                block["variables_data"] = variables_data

                if st.session_state.block_manager.save_block(block, variables_data):
                    st.success(f"✅ Переменная '{var_name}' преобразована в AI")
                    # Обновляем тип в edit_variable_direct
                    if 'edit_variable_direct' in st.session_state:
                        st.session_state.edit_variable_direct['type'] = 'ai'
                    st.rerun()

        with col3:
            if st.form_submit_button("🗑️ Удалить", type="secondary", use_container_width=True):
                if st.session_state.get(f"confirm_del_{block_id}_{var_name}", False):
                    # Удаляем переменную
                    variables = block.get("variables", [])
                    if var_name in variables:
                        variables.remove(var_name)

                    variables_data = block.get("variables_data", {})
                    if var_name in variables_data:
                        del variables_data[var_name]

                    block["variables"] = variables
                    block["variables_data"] = variables_data

                    if st.session_state.block_manager.save_block(block, variables_data):
                        st.success(f"✅ Переменная '{var_name}' удалена")
                        st.session_state.pop('edit_variable_direct', None)
                        st.rerun()
                else:
                    st.session_state[f"confirm_del_{block_id}_{var_name}"] = True
                    st.warning("Нажмите 'Удалить' ещё раз для подтверждения")


def show_ai_variable_editor(block_id, var_name, var_data, block):
    """Редактор AI переменной"""

    st.subheader(f"🤖 Редактирование AI переменной: `{var_name}`")

    # Создаем вкладки для настроек и результатов
    tab_settings, tab_results = st.tabs(["⚙️ Настройки генерации", "📋 Сохраненные результаты"])

    with tab_settings:
        with st.form(key=f"direct_edit_ai_{block_id}_{var_name}"):
            description = st.text_input(
                "Описание переменной",
                value=var_data.get("description", "")
            )

            col1, col2 = st.columns(2)
            with col1:
                current_provider = var_data.get("ai_provider", "deepseek")

                # Определяем индекс для выбора
                if current_provider in ["agentplatform", "deepseek"]:
                    default_index = ["agentplatform", "deepseek"].index(current_provider)
                else:
                    # Если сохранен старый провайдер, по умолчанию выбираем agentplatform
                    default_index = 0

                provider = st.selectbox(
                    "AI провайдер",
                    ["agentplatform", "deepseek"],
                    index=default_index,
                    format_func=lambda x: {
                        "agentplatform": "AgentPlatform (OpenAI/Anthropic/Google/Mistral и др.)",
                        "deepseek": "DeepSeek (прямой доступ)"
                    }.get(x, x)
                )

            with col2:
                num_variants = st.number_input(
                    "Количество вариантов",
                    min_value=1, max_value=10,
                    value=var_data.get("ai_num_variants", 3)
                )

            st.markdown("**Промпт для генерации:**")
            st.caption("Доступны переменные: {категория}, {характеристика}, {значение}, {тип}")
            prompt = st.text_area(
                "Промпт",
                value=var_data.get("ai_prompt", ""),
                height=250,
                label_visibility="collapsed"
            )

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.form_submit_button("💾 Сохранить настройки", use_container_width=True):
                    variables_data = block.get("variables_data", {})
                    variables_data[var_name] = {
                        "name": var_name,
                        "description": description,
                        "type": "ai",
                        "ai_prompt": prompt,
                        "ai_num_variants": num_variants,
                        "ai_provider": provider,
                        "values": var_data.get("values", [])
                    }
                    block["variables_data"] = variables_data

                    if st.session_state.block_manager.save_block(block, variables_data):
                        st.success(f"✅ Настройки сохранены")
                        force_save_phase3_blocks()
                        st.rerun()

            with col_btn2:
                if st.form_submit_button("🚀 Генерировать", use_container_width=True):
                    # Сохраняем и запускаем генерацию
                    variables_data = block.get("variables_data", {})
                    variables_data[var_name] = {
                        "name": var_name,
                        "description": description,
                        "type": "ai",
                        "ai_prompt": prompt,
                        "ai_num_variants": num_variants,
                        "ai_provider": provider,
                        "values": var_data.get("values", [])
                    }
                    block["variables_data"] = variables_data
                    st.session_state.block_manager.save_block(block, variables_data)

                    # Запускаем генерацию
                    if block.get("block_type") == "characteristic":
                        show_ai_generation_for_characteristics(block_id, var_name, variables_data[var_name], block)
                    else:
                        show_ai_generation_for_other_blocks(block_id, var_name, variables_data[var_name], block)

    with tab_results:
        if 'ai_instruction_manager' in st.session_state:
            ai_mgr = st.session_state.ai_instruction_manager
            if block_id in ai_mgr.instructions and var_name in ai_mgr.instructions[block_id]:
                for ctx_hash, ctx_data in ai_mgr.instructions[block_id][var_name].items():
                    context = ctx_data.get("context", {})
                    values = ctx_data.get("values", [])

                    with st.expander(f"📌 {context.get('характеристика', 'Общий контекст')}"):
                        st.json(context)
                        for i, val in enumerate(values):
                            st.text_area(
                                f"Вариант {i+1}",
                                value=val,
                                height=100,
                                key=f"view_{block_id}_{var_name}_{ctx_hash}_{i}",
                                disabled=True
                            )
            else:
                st.info("Нет сохраненных результатов генерации")


def show_dynamic_variable_info(var_name):
    """Информация о глобальной переменной"""
    st.subheader(f"🌀 глобальная переменная: `{var_name}`")
    st.info("глобальные переменные настраиваются централизованно и доступны во всех блоках")

    if 'dynamic_var_manager' in st.session_state:
        var_info = st.session_state.dynamic_var_manager.get_dynamic_variable(var_name)
        if var_info:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Источник", var_info.get('source', 'unknown'))
            with col2:
                st.metric("Тип", "глобальная")

            st.markdown("**Описание:**")
            st.write(var_info.get('description', 'Нет описания'))

            if var_info.get('source') == 'config':
                values = var_info.get('values', [])
                st.markdown(f"**Значения ({len(values)}):**")
                for val in values[:10]:
                    st.write(f"- {val}")

        if st.button("⚙️ Перейти к редактору глобальных переменных", use_container_width=True):
            st.session_state.switch_to_tab = 3
            st.session_state.pop('edit_variable_direct', None)
            st.rerun()
def show_block_editor():
    """Редактор блока"""

    # Выбор блока для редактирования
    blocks = st.session_state.block_manager.get_all_blocks()

    if not blocks:
        st.info("Нет блоков для редактирования")
        return

    # Инициализируем текущий редактируемый блок
    if 'current_edit_block' not in st.session_state or st.session_state.current_edit_block not in blocks:
        block_ids = list(blocks.keys())
        st.session_state.current_edit_block = block_ids[0] if block_ids else None

    # Выбор блока
    block_ids = list(blocks.keys())
    # Убеждаемся, что current_edit_block существует
    if st.session_state.current_edit_block not in block_ids:
        st.session_state.current_edit_block = block_ids[0]

    selected_block_id = st.selectbox(
        "Выберите блок для редактирования:",
        block_ids,
        index=block_ids.index(
            st.session_state.current_edit_block) if st.session_state.current_edit_block in block_ids else 0,
        format_func=lambda x: f"{blocks[x].get('name', x)} ({blocks[x].get('block_type', 'other')})",
        key="block_editor_select"
    )

    if selected_block_id != st.session_state.current_edit_block:
        st.session_state.current_edit_block = selected_block_id
        st.rerun()

    selected_block = blocks[selected_block_id]
    if 'edit_variable_direct' in st.session_state:
        var_to_edit = st.session_state.edit_variable_direct
        # Проверяем, что это тот же блок
        if var_to_edit['block_id'] == selected_block_id:
            # Показываем редактор переменной
            st.markdown("---")
            st.markdown(f"### ✏️ Редактирование переменной: `{var_to_edit['var_name']}`")

            # Получаем данные переменной
            variables_data = selected_block.get("variables_data", {})
            var_data = variables_data.get(var_to_edit['var_name'], {})

            # Создаем табы для разных типов (если нужно)
            if var_to_edit['type'] == 'static':
                show_static_variable_editor(selected_block_id, var_to_edit['var_name'], var_data, selected_block)
            elif var_to_edit['type'] == 'ai':
                show_ai_variable_editor(selected_block_id, var_to_edit['var_name'], var_data, selected_block)
            elif var_to_edit['type'] == 'dynamic':
                show_dynamic_variable_info(var_to_edit['var_name'])

            # Кнопка "Назад"
            if st.button("← Назад к списку переменных блока"):
                del st.session_state.edit_variable_direct
                st.rerun()

            st.markdown("---")
            # Не показываем остальной интерфейс
            return
        else:
            # Если блок не совпадает, сбрасываем
            del st.session_state.edit_variable_direct
    # Редактирование блока
    with st.form(key="edit_block_form"):
        st.subheader(f"✏️ Редактирование блока: {selected_block['name']}")

        # Основные поля
        col1, col2 = st.columns([3, 1])
        with col1:
            block_name = st.text_input("Название блока", value=selected_block.get("name", ""))
        with col2:
            block_type = st.selectbox(
                "Тип блока:",
                ["characteristic", "other"],
                index=0 if selected_block.get("block_type", "other") == "characteristic" else 1,
                format_func=lambda x: "Характеристика" if x == "characteristic" else "Другой блок"
            )

        block_desc = st.text_area("Описание блока", value=selected_block.get("description", ""))

        # Для characteristic блоков - выбор типа характеристики
        if block_type == "characteristic":
            char_type = st.selectbox(
                "Тип характеристики:",
                ["regular", "unique"],
                index=0 if selected_block.get("settings", {}).get("characteristic_type", "regular") == "regular" else 1,
                format_func=lambda x: "Regular (обычная)" if x == "regular" else "Unique (уникальная)"
            )

            # Информация о форматах значений


        # Шаблон
        st.markdown("### Шаблон промпта")
        st.caption("Используйте `{имя_переменной}` для вставки переменных. Доступные переменные зависят от типа блока и настроек.")
        template = st.text_area(
            "Шаблон",
            value=selected_block.get("template", ""),
            height=300
        )

        # Переменные блока
        st.markdown("### Переменные блока")
        st.caption("Переменные автоматически определяются из шаблона и настроек ниже")
        if selected_block.get("variables", []):
            st.write("**Используемые переменные:** " + ", ".join([f"`{v}`" for v in selected_block.get("variables", [])]))
        else:
            st.info("Переменные не найдены. Добавьте их в шаблоне с помощью {имя_переменной}")

        # Кнопки сохранения
        col_save1, col_save2 = st.columns(2)
        with col_save1:
            if st.form_submit_button("💾 Сохранить блок", use_container_width=True):
                # Обновляем блок
                selected_block["name"] = block_name
                selected_block["description"] = block_desc
                selected_block["template"] = template
                template_vars = set(re.findall(r'\{([^}]+)\}', template))
                existing_vars = set(selected_block.get("variables", []))
                all_vars = list(template_vars | existing_vars)
                selected_block["variables"] = all_vars
                selected_block["block_type"] = block_type

                # Обновляем настройки для characteristic блоков
                if block_type == "characteristic":
                    # Автоматически добавляем/убираем переменную скобки в зависимости от типа
                    variables_list = all_vars.copy()
                    if char_type == "regular":
                        # Для regular характеристик добавляем скобки_характеристика если еще нет
                        if "скобки_характеристика" not in variables_list:
                            variables_list.append("скобки_характеристика")
                    else:  # unique
                        # Для unique характеристик убираем скобки_характеристика если есть
                        if "скобки_характеристика" in variables_list:
                            variables_list.remove("скобки_характеристика")

                    selected_block["variables"] = variables_list

                    selected_block["settings"] = {
                        "маркер_позиция": "начало",  # фиксированное значение
                        "формат_значения_regular": "[[значение]]",  # фиксированное значение
                        "формат_значения_unique": "\"[значение]\"",  # фиксированное значение
                        "добавлять_скобки_переменную": (char_type == "regular"),  # автоматически
                        "characteristic_type": char_type
                    }
                elif "settings" not in selected_block:
                    selected_block["settings"] = {}

                # Сохраняем
                if st.session_state.block_manager.save_block(selected_block):
                    st.success("✅ Блок сохранен!")
                    st.rerun()
                else:
                    st.error("❌ Ошибка сохранения блока")

        with col_save2:
            if st.form_submit_button("❌ Отмена", type="secondary", use_container_width=True):
                st.rerun()
    # После формы редактирования блока добавляем управление статическими переменными
    st.markdown("---")
    st.subheader("📦 Переменные этого блока")

    # Получаем текущие переменные блока
    variables = selected_block.get("variables", [])
    variables_data = selected_block.get("variables_data", {})

    # Объединяем имена из обоих списков
    all_var_names = set(variables) | set(variables_data.keys())
    variables = list(all_var_names)

    # Для тех, что есть в all_var_names, но нет в variables_data, создаём запись по умолчанию
    for var in all_var_names:
        if var not in variables_data:
            variables_data[var] = {
                "name": var,
                "description": f"Автоматически созданная переменная {var}",
                "type": "static",
                "values": []
            }

    selected_block["variables"] = variables
    selected_block["variables_data"] = variables_data
    template = selected_block.get("template", "")

    # Определяем глобальные переменные, доступные в системе
    dynamic_var_names = []
    if 'dynamic_var_manager' in st.session_state:
        dynamic_var_names = list(st.session_state.dynamic_var_manager.get_all_dynamic_vars().keys())

    # Разделяем переменные по типам
    static_vars = []
    ai_vars = []
    dynamic_vars = []

    for var_name in variables:
        var_type = variables_data.get(var_name, {}).get("type", "static")
        if var_type == "ai":
            ai_vars.append(var_name)
        elif var_name in dynamic_var_names:
            dynamic_vars.append(var_name)
        else:
            static_vars.append(var_name)

    # Добавляем переменные, которые есть только в шаблоне, но не в списке variables
    template_vars = set(re.findall(r'\{([^}]+)\}', template))
    for var_name in template_vars:
        if var_name not in variables:
            # Автоматически добавляем в список, но не создаём данные
            if var_name not in variables:
                variables.append(var_name)
                # Определяем предполагаемый тип
                if var_name in dynamic_var_names:
                    dynamic_vars.append(var_name)
                else:
                    # По умолчанию считаем статической, но данные не создаём
                    static_vars.append(var_name)
                    # Можно создать пустую запись, но лучше оставить на усмотрение пользователя
                    # Для простоты пока не создаём
                    pass

    # Создаём табы для разных типов переменных
    tab_static, tab_ai, tab_dynamic = st.tabs([
        f"📝 локальные ({len(static_vars)})",
        f"🤖 AI ({len(ai_vars)})",
        f"🌀 глобальные ({len(dynamic_vars)})"
    ])

    # --- Вкладка локальных переменных ---
    with tab_static:
        # Кнопка добавления новой статической переменной
        with st.expander("➕ Добавить новую локальную переменную", expanded=False):
            new_static_name = st.text_input(
                "Имя переменной (без фигурных скобок)",
                key=f"new_static_{selected_block_id}"
            )
            col_new1, col_new2 = st.columns([3, 1])
            with col_new1:
                if st.button("Создать локальную", key=f"create_static_{selected_block_id}") and new_static_name:
                    if new_static_name not in variables:
                        variables.append(new_static_name)
                        variables_data[new_static_name] = {
                            "name": new_static_name,
                            "description": f"локальная переменная {new_static_name}",
                            "type": "static",
                            "values": ["Пример значения 1", "Пример значения 2"]
                        }
                        selected_block["variables"] = variables
                        selected_block["variables_data"] = variables_data
                        if st.session_state.block_manager.save_block(selected_block, variables_data):
                            st.success(f"Переменная '{new_static_name}' создана")
                            st.rerun()
                    else:
                        st.error("Переменная с таким именем уже существует")

        # Список локальных переменных для редактирования
        if static_vars:
            for var_name in static_vars:
                var_data = variables_data.get(var_name, {
                    "name": var_name,
                    "description": f"локальная переменная {var_name}",
                    "type": "static",
                    "values": []
                })
                with st.expander(f"📝 {var_name}", expanded=False):
                    with st.form(key=f"edit_static_{selected_block_id}_{var_name}"):
                        desc = st.text_input("Описание", value=var_data.get("description", ""))
                        values_text = "\n".join(var_data.get("values", []))
                        new_values = st.text_area("Значения (каждое с новой строки)", value=values_text, height=150)

                        col_act1, col_act2, col_act3 = st.columns([2, 1, 1])
                        with col_act1:
                            if st.form_submit_button("💾 Сохранить"):
                                var_data["description"] = desc
                                var_data["values"] = [v.strip() for v in new_values.split("\n") if v.strip()]
                                variables_data[var_name] = var_data
                                selected_block["variables_data"] = variables_data
                                if st.session_state.block_manager.save_block(selected_block, variables_data):
                                    st.success(f"Переменная '{var_name}' сохранена")
                                    st.rerun()
                        with col_act2:
                            if st.form_submit_button("🗑️ Удалить"):
                                if st.session_state.get(f"confirm_del_static_{selected_block_id}_{var_name}", False):
                                    variables.remove(var_name)
                                    del variables_data[var_name]
                                    selected_block["variables"] = variables
                                    selected_block["variables_data"] = variables_data
                                    if st.session_state.block_manager.save_block(selected_block, variables_data):
                                        st.success(f"Переменная '{var_name}' удалена")
                                        st.rerun()
                                else:
                                    st.session_state[f"confirm_del_static_{selected_block_id}_{var_name}"] = True
                                    st.warning("Нажмите 'Удалить' ещё раз для подтверждения")
                        with col_act3:
                            # Кнопка преобразования в AI
                            if st.form_submit_button("🤖 Преобразовать в AI"):
                                var_data["type"] = "ai"
                                var_data["ai_prompt"] = "Сгенерируй текст для {характеристика}..."
                                var_data["ai_num_variants"] = 3
                                var_data["ai_provider"] = "openai"
                                variables_data[var_name] = var_data
                                selected_block["variables_data"] = variables_data
                                if st.session_state.block_manager.save_block(selected_block, variables_data):
                                    st.success(f"Переменная '{var_name}' теперь AI")
                                    st.rerun()
        else:
            st.info("Нет локальных переменных")

    # --- Вкладка AI переменных ---
    with tab_ai:
        # Кнопка добавления новой AI переменной
        with st.expander("➕ Добавить новую AI переменную", expanded=False):
            new_ai_name = st.text_input(
                "Имя переменной (без фигурных скобок)",
                key=f"new_ai_{selected_block_id}"
            )
            if st.button("Создать AI", key=f"create_ai_{selected_block_id}") and new_ai_name:
                if new_ai_name not in variables:
                    variables.append(new_ai_name)
                    # Базовый промпт в зависимости от типа блока
                    if block_type == "characteristic":
                        base_prompt = """Сгенерируй перечень аналитических тезисов для характеристики {характеристика} в категории {категория}."""
                    else:
                        base_prompt = "Сгенерируй контент для категории {контекст_категория}."
                    variables_data[new_ai_name] = {
                        "name": new_ai_name,
                        "description": f"AI переменная {new_ai_name}",
                        "type": "ai",
                        "ai_prompt": base_prompt,
                        "ai_num_variants": 3,
                        "ai_provider": "openai",
                        "values": []
                    }
                    selected_block["variables"] = variables
                    selected_block["variables_data"] = variables_data
                    if st.session_state.block_manager.save_block(selected_block, variables_data):
                        st.success(f"AI переменная '{new_ai_name}' создана")
                        st.rerun()
                else:
                    st.error("Переменная с таким именем уже существует")

        # Список AI переменных для редактирования
        if ai_vars:
            for var_name in ai_vars:
                var_data = variables_data.get(var_name, {
                    "name": var_name,
                    "description": f"AI переменная {var_name}",
                    "type": "ai",
                    "ai_prompt": "",
                    "ai_num_variants": 3,
                    "ai_provider": "openai",
                    "values": []
                })
                with st.expander(f"🤖 {var_name}", expanded=False):
                    with st.form(key=f"edit_ai_{selected_block_id}_{var_name}"):
                        desc = st.text_input("Описание", value=var_data.get("description", ""))
                        available_providers = ["agentplatform", "deepseek"]

                        provider_labels = {
                            "agentplatform": "AgentPlatform (OpenAI/Anthropic/Google/Mistral и др.)",
                            "deepseek": "DeepSeek (прямой доступ)"
                        }

                        current_provider = var_data.get("ai_provider", "deepseek")

                        provider = st.selectbox(
                            "Провайдер",
                            available_providers,
                            format_func=lambda x: provider_labels.get(x, x),
                            index=available_providers.index(current_provider)
                            if current_provider in available_providers else 1,
                            key=f"ai_provider_{selected_block_id}_{var_name}"
                        )

                        # Дополнительные подсказки
                        if provider == "true_gemini":
                            st.caption("⚠️ Требует VPN из России")
                        elif provider == "genapi_gemini":
                            st.info("Работает без VPN, оплата рублями")
                        num_variants = st.number_input(
                            "Количество вариантов",
                            min_value=1, max_value=10,
                            value=var_data.get("ai_num_variants", 3)
                        )
                        prompt = st.text_area(
                            "Промпт для AI",
                            value=var_data.get("ai_prompt", ""),
                            height=150
                        )

                        col_act1, col_act2, col_act3 = st.columns([2, 1, 1])
                        with col_act1:
                            if st.form_submit_button("💾 Сохранить настройки"):
                                var_data.update({
                                    "description": desc,
                                    "ai_provider": provider,
                                    "ai_num_variants": num_variants,
                                    "ai_prompt": prompt
                                })
                                variables_data[var_name] = var_data
                                selected_block["variables_data"] = variables_data
                                if st.session_state.block_manager.save_block(selected_block, variables_data):
                                    st.success(f"AI переменная '{var_name}' сохранена")
                                    st.rerun()
                        with col_act2:
                            if st.form_submit_button("🚀 Генерировать"):
                                # Сохраняем и переходим к генерации
                                var_data.update({
                                    "description": desc,
                                    "ai_provider": provider,
                                    "ai_num_variants": num_variants,
                                    "ai_prompt": prompt
                                })
                                variables_data[var_name] = var_data
                                selected_block["variables_data"] = variables_data
                                st.session_state.block_manager.save_block(selected_block, variables_data)
                                st.session_state.current_ai_var_for_generation = var_name
                                st.session_state.current_block_for_ai = selected_block_id
                                st.rerun()
                        with col_act3:
                            if st.form_submit_button("🗑️ Удалить"):
                                if st.session_state.get(f"confirm_del_ai_{selected_block_id}_{var_name}", False):
                                    variables.remove(var_name)
                                    del variables_data[var_name]
                                    selected_block["variables"] = variables
                                    selected_block["variables_data"] = variables_data
                                    if st.session_state.block_manager.save_block(selected_block, variables_data):
                                        st.success(f"AI переменная '{var_name}' удалена")
                                        st.rerun()
                                else:
                                    st.session_state[f"confirm_del_ai_{selected_block_id}_{var_name}"] = True
                                    st.warning("Нажмите 'Удалить' ещё раз для подтверждения")

                    # Если выбрана генерация для этой переменной
                    if (st.session_state.get("current_ai_var_for_generation") == var_name and
                            st.session_state.get("current_block_for_ai") == selected_block_id):
                        st.markdown("---")
                        if block_type == "characteristic":
                            show_ai_generation_for_characteristics(selected_block_id, var_name, var_data,
                                                                   selected_block)
                        else:
                            show_ai_generation_for_other_blocks(selected_block_id, var_name, var_data, selected_block)
                        if st.button("❌ Отменить генерацию", key=f"cancel_gen_ai_{var_name}"):
                            del st.session_state.current_ai_var_for_generation
                            del st.session_state.current_block_for_ai
                            st.rerun()
        else:
            st.info("Нет AI переменных")

    # --- Вкладка глобальных переменных ---
    with tab_dynamic:
        if dynamic_vars:
            st.info("глобальные переменные настраиваются во вкладке «🌀 Редактирование глобальных переменных».")
            for var_name in dynamic_vars:
                var_info = st.session_state.dynamic_var_manager.get_dynamic_variable(var_name)
                with st.expander(f"🌀 {var_name}", expanded=False):
                    if var_info:
                        st.write(f"**Описание:** {var_info.get('description', '')}")
                        st.write(f"**Источник:** {var_info.get('source', 'unknown')}")
                        if var_info.get('source') == 'config':
                            values = var_info.get('values', [])
                            st.write(f"**Количество значений:** {len(values)}")
                            if values:
                                st.write("**Примеры:**")
                                for val in values[:3]:
                                    st.write(f"- {val}")
                    else:
                        st.write("Информация о переменной не найдена")
        else:
            st.info(
                "глобальные переменные не используются в этом блоке. Чтобы добавить, используйте `{имя}` в шаблоне и создайте переменную во вкладке «🌀 Редактирование глобальных переменных».")

    # Информация о переменных блока
    with st.expander("📊 Статистика по переменным", expanded=False):
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("Всего переменных", len(variables))
        with col_stat2:
            st.metric("локальных", len(static_vars))
        with col_stat3:
            st.metric("AI", len(ai_vars))
        if dynamic_vars:
            st.metric("глобальных", len(dynamic_vars))


# Заменить функцию show_ai_generation_for_characteristics на новую версию:
def show_ai_generation_for_characteristics(block_id, var_name, var_data, block):
    """Показывает интерфейс генерации AI для characteristic блоков с отображением промпта и ответа"""

    # Проверяем наличие данных из фазы 2
    phase2_data = get_phase2_data()
    category = phase2_data.get('category', '')
    characteristics = get_characteristics_data()

    if not category:
        st.error("❌ Нет данных о категории. Загрузите данные в фазу 2.")
        return

    st.success(f"✅ Категория: **{category}**")
    st.info(f"📊 Найдено характеристик: **{len(characteristics)}**")

    # Определяем тип характеристики (regular/unique)
    block_char_type = block.get("settings", {}).get("characteristic_type", "regular")

    # Показываем характеристики для генерации
    with st.expander("📋 Характеристики для генерации", expanded=True):
        char_selection = {}

        for char in characteristics:
            char_id = char.get('char_id', '')
            char_name = char.get('char_name', 'Без названия')
            is_unique = char.get('is_unique', False)
            values_count = len(char.get('values', []))

            # Фильтруем по типу, если нужно
            if block_char_type == "regular" and is_unique:
                continue
            elif block_char_type == "unique" and not is_unique:
                continue

            col_char1, col_char2, col_char3, col_char4 = st.columns([3, 1, 1, 1])
            with col_char1:
                st.write(f"**{char_name}**")
                st.caption(f"ID: {char_id}")
            with col_char2:
                st.write(f"**{values_count}**")
                st.caption("значений")
            with col_char3:
                st.write(f"**{'Unique' if is_unique else 'Regular'}**")
            with col_char4:
                # ИСПРАВЛЕНО: используем уникальный ключ с timestamp
                unique_key = f"select_char_{block_id}_{var_name}_{char_id}_{int(time.time()*1000000)}"
                char_selection[char_id] = st.checkbox(
                    "Выбрать",
                    value=True,
                    key=unique_key
                )

        if not char_selection:
            st.warning(f"Нет характеристик типа '{block_char_type}' для генерации")
            return

        st.divider()
        selected_count = sum(char_selection.values())
        st.write(f"**Выбрано:** {selected_count} характеристик")

    # Проверка API ключа
    if 'ai_config_manager' not in st.session_state:
        st.warning("⚠️ Менеджер AI не инициализирован")
        if st.button("🔄 Инициализировать AI", key=f"init_ai_{block_id}_{var_name}_{int(time.time())}"):
            init_ai_managers()
            st.rerun()
        return

    provider = var_data.get("ai_provider", "openai")
    from api_key_manager import APIKeyManager

    key_manager = APIKeyManager()
    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()
    dm = st.session_state.domain_manager
    api_key = key_manager.get_api_key(dm.site_name, dm.get_current_domain(), provider)

    if not api_key:
        st.error(f"❌ API ключ для провайдера '{provider}' не настроен для домена {dm.get_current_domain()}!")
        if st.button("⚙️ Настроить API ключ", use_container_width=True):
            st.session_state.show_ai_config = True
            st.rerun()
        return

    # Кнопка запуска генерации
    if st.button("🚀 Запустить генерацию AI-инструкций", type="primary",
                 use_container_width=True, key=f"run_gen_{block_id}_{var_name}_{int(time.time())}"):

        with st.spinner("Генерация AI-инструкций..."):
            init_ai_managers()

            selected_chars = [c for c in characteristics if char_selection.get(c.get('char_id', ''))]
            all_generation_results = []
            progress_bar = st.progress(0)

            for idx, char in enumerate(selected_chars):
                char_id = char.get('char_id', '')
                char_name = char.get('char_name', '')
                is_unique = char.get('is_unique', False)
                values = char.get('values', [])

                if block_char_type == "regular" and is_unique:
                    continue
                elif block_char_type == "unique" and not is_unique:
                    continue

                progress = (idx + 1) / len(selected_chars)
                progress_bar.progress(progress)

                if is_unique:
                    for value_idx, value_item in enumerate(values):
                        value = value_item.get('value', '')

                        context = {
                            "категория": category.strip(),
                            "характеристика": char_name.strip(),
                            "значение": value,
                            "тип": "unique",
                            "block_id": block_id,
                            "var_name": var_name
                        }

                        final_prompt = var_data.get("ai_prompt", "")
                        for key, val in context.items():
                            placeholder = f"{{{key}}}"
                            final_prompt = final_prompt.replace(placeholder, str(val))

                        results = st.session_state.ai_generator.generate_instruction(
                            var_data.get("ai_prompt", ""),
                            context,
                            provider=provider,
                            num_variants=1,
                            return_full_response=True
                        )

                        if results and results[0]["success"]:
                            instruction = results[0]["text"]
                            full_response = results[0].get("full_response", {})

                            all_generation_results.append({
                                "характеристика": char_name,
                                "значение": value,
                                "тип": "unique",
                                "промпт": final_prompt,
                                "ответ": instruction,
                                "полный_ответ": full_response,
                                "результат": results[0],
                                "char_id": char_id,
                                "value_idx": value_idx
                            })

                            st.session_state.ai_instruction_manager.save_instruction(
                                block_id, var_name, [instruction], context,
                                {"provider": provider, "char_id": char_id, "char_name": char_name, "value": value}
                            )
                        else:
                            error_msg = results[0].get('error', 'Неизвестная ошибка') if results else 'Нет ответа'
                            all_generation_results.append({
                                "характеристика": char_name,
                                "значение": value,
                                "тип": "unique",
                                "промпт": final_prompt,
                                "ошибка": error_msg,
                                "char_id": char_id,
                                "value_idx": value_idx
                            })
                else:
                    context = {
                        "категория": category,
                        "характеристика": char_name,
                        "тип": "regular",
                        "block_id": block_id,
                        "var_name": var_name
                    }

                    final_prompt = var_data.get("ai_prompt", "")
                    for key, val in context.items():
                        placeholder = f"{{{key}}}"
                        final_prompt = final_prompt.replace(placeholder, str(val))

                    results = st.session_state.ai_generator.generate_instruction(
                        var_data.get("ai_prompt", ""),
                        context,
                        provider=provider,
                        num_variants=var_data.get("ai_num_variants", 1),
                        return_full_response=True
                    )

                    for i, result in enumerate(results):
                        if result.get("success"):
                            all_generation_results.append({
                                "характеристика": char_name,
                                "тип": "regular",
                                "вариант": i + 1,
                                "промпт": final_prompt,
                                "ответ": result["text"],
                                "полный_ответ": result.get("full_response", {}),
                                "результат": result,
                                "char_id": char_id,
                                "variant_idx": i
                            })
                        else:
                            all_generation_results.append({
                                "характеристика": char_name,
                                "тип": "regular",
                                "вариант": i + 1,
                                "промпт": final_prompt,
                                "ошибка": result.get('error', 'Неизвестная ошибка'),
                                "char_id": char_id,
                                "variant_idx": i
                            })

                    successful_results = [r["text"] for r in results if r.get("success")]
                    if successful_results:
                        st.session_state.ai_instruction_manager.save_instruction(
                            block_id, var_name, successful_results, context,
                            {"provider": provider, "char_id": char_id, "char_name": char_name}
                        )

            progress_bar.empty()

            st.markdown("### 📊 Результаты генерации с промптами и ответами")

            success_count = sum(1 for r in all_generation_results if "ответ" in r)
            error_count = sum(1 for r in all_generation_results if "ошибка" in r)

            st.metric("✅ Успешно", success_count)
            st.metric("❌ Ошибок", error_count)

            for i, result in enumerate(all_generation_results):
                if "ошибка" in result:
                    with st.expander(f"❌ {i+1}. {result['характеристика']} - ОШИБКА", expanded=False):
                        st.error(f"**Ошибка:** {result['ошибка']}")
                        st.markdown("**Отправленный промпт:**")
                        st.code(result['промпт'], language="markdown")
                else:
                    title = f"{i+1}. {result['характеристика']}"
                    if "значение" in result:
                        title += f" = {result['значение']}"
                    if "вариант" in result:
                        title += f" (вариант {result['вариант']})"

                    with st.expander(f"✅ {title}", expanded=False):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("**Отправленный промпт:**")
                            st.code(result['промпт'], language="markdown")

                        with col2:
                            st.markdown("**Ответ ИИ:**")
                            st.code(result['ответ'], language="markdown")

                        if "полный_ответ" in result and result["полный_ответ"]:
                            with st.expander("📄 Полный ответ API", expanded=False):
                                st.json(result["полный_ответ"])

                        st.markdown("**✏️ Редактировать ответ:**")
                        # ИСПРАВЛЕНО: уникальный ключ с использованием всех идентификаторов
                        edit_key = f"edit_response_{block_id}_{var_name}_{result.get('char_id', '')}_{result.get('value_idx', i)}_{result.get('variant_idx', i)}_{int(time.time()*1000)}_{i}"
                        edited_response = st.text_area(
                            f"Редактирование ответа {i+1}:",
                            value=result['ответ'],
                            height=200,
                            key=edit_key
                        )

                        # ИСПРАВЛЕНО: уникальный ключ для кнопки сохранения
                        save_key = f"save_edit_{block_id}_{var_name}_{result.get('char_id', '')}_{result.get('value_idx', i)}_{result.get('variant_idx', i)}_{int(time.time()*1000)}_{i}"
                        if st.button(f"💾 Сохранить изменения", key=save_key):
                            if "значение" in result:
                                context_for_update = {
                                    "категория": category,
                                    "характеристика": result['характеристика'],
                                    "значение": result.get('значение', ''),
                                    "тип": result['тип']
                                }
                                context_hash = st.session_state.ai_instruction_manager.find_matching_context_hash(
                                    block_id, var_name, context_for_update
                                )
                                if context_hash:
                                    st.session_state.ai_instruction_manager.update_full_instruction(
                                        block_id, var_name, context_hash, 0, edited_response
                                    )
                                    st.success("✅ Ответ обновлен!")
                                    st.rerun()
                            else:
                                context_for_update = {
                                    "категория": category,
                                    "характеристика": result['характеристика'],
                                    "тип": result['тип']
                                }
                                context_hash = st.session_state.ai_instruction_manager.find_matching_context_hash(
                                    block_id, var_name, context_for_update
                                )
                                if context_hash:
                                    variant_idx = result.get('вариант', 1) - 1
                                    st.session_state.ai_instruction_manager.update_full_instruction(
                                        block_id, var_name, context_hash, variant_idx, edited_response
                                    )
                                    st.success("✅ Ответ обновлен!")
                                    st.rerun()

            if success_count > 0:
                st.success(f"✅ Сгенерировано {success_count} AI-инструкций!")
            else:
                st.error("❌ Не удалось сгенерировать ни одну инструкцию")
            st.session_state.ai_instruction_manager.reload()
            st.rerun()


def show_ai_generation_for_other_blocks(block_id, var_name, var_data, block):
    """Показывает интерфейс генерации AI для других типов блоков с отображением промпта и ответа"""

    st.info("""
    **Генерация для общих блоков**    """)

    # Проверяем наличие данных из фазы 2
    phase2_data = get_phase2_data()
    category = phase2_data.get('category', '')

    if not category:
        st.error("❌ Нет данных о категории. Загрузите данные в фазу 2.")
        return

    st.success(f"✅ Категория для генерации: **{category}**")

    # Количество вариантов
    num_variants = st.number_input(
        "Количество вариантов для генерации:",
        min_value=1,
        max_value=10,
        value=var_data.get("ai_num_variants", 3),
        key=f"num_variants_{block_id}_{var_name}"
    )

    # Проверка API ключа
    if 'ai_config_manager' not in st.session_state:
        st.warning("⚠️ Менеджер AI не инициализирован")
        if st.button("🔄 Инициализировать AI", key=f"init_ai_other_{block_id}_{var_name}"):
            init_ai_managers()
            st.rerun()
        return

    provider = var_data.get("ai_provider", "openai")
    provider_config = st.session_state.ai_config_manager.get_provider_config(provider)

    if not provider_config.get("api_key"):
        st.error(f"❌ API ключ для провайдера '{provider}' не настроен!")
        if st.button("⚙️ Настроить API ключ", use_container_width=True, key=f"setup_api_other_{block_id}_{var_name}"):
            st.session_state.show_ai_config = True
            st.rerun()
        return

    # УБРАЛИ тестовую генерацию - оставляем только основную

    # Кнопка основной генерации
    if st.button("🚀 Запустить генерацию", type="primary",
                 use_container_width=True, key=f"main_gen_{block_id}_{var_name}"):

        with st.spinner(f"Генерация {num_variants} вариантов..."):
            init_ai_managers()

            # Контекст для блока "other" - только категория
            context = {
                "категория": category.strip(),
                "тип": "other",
                "block_id": block_id,
                "var_name": var_name
            }

            # Формируем финальный промпт с подстановкой контекста
            final_prompt = var_data.get("ai_prompt", "")
            for key, value in context.items():
                placeholder = f"{{{key}}}"
                final_prompt = final_prompt.replace(placeholder, str(value))

            # Генерируем инструкции с возвратом полного ответа
            results = st.session_state.ai_generator.generate_instruction(
                var_data.get("ai_prompt", ""),
                context,
                provider=provider,
                num_variants=num_variants,
                return_full_response=True
            )

            # Отображаем все результаты
            st.markdown("### 📊 Результаты генерации")

            success_count = 0
            error_count = 0

            for i, result in enumerate(results):
                if result.get("success"):
                    success_count += 1

                    with st.expander(f"✅ Вариант {i + 1} (успешно)", expanded=False):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("**Отправленный промпт:**")
                            st.code(final_prompt, language="markdown")

                        with col2:
                            st.markdown("**Ответ ИИ:**")
                            st.code(result["text"], language="markdown")

                        # Показываем полный ответ API если есть
                        if "full_response" in result and result["full_response"]:
                            with st.expander("📄 Полный ответ API", expanded=False):
                                st.json(result["full_response"])

                        # Редактирование ответа
                        st.markdown("**✏️ Редактировать ответ:**")
                        edited_response = st.text_area(
                            f"Редактирование варианта {i + 1}:",
                            value=result["text"],
                            height=200,
                            key=f"edit_other_{block_id}_{var_name}_{i}"
                        )

                        if st.button(f"💾 Сохранить изменения", key=f"save_edit_other_{block_id}_{var_name}_{i}"):
                            # Сохраняем отредактированный вариант
                            successful_results = [r["text"] for r in results if r.get("success")]
                            # Заменяем соответствующий результат
                            successful_results[i] = edited_response

                            # Сохраняем инструкции с контекстом блока
                            st.session_state.ai_instruction_manager.save_instruction(
                                block_id,
                                var_name,
                                successful_results,
                                context,
                                {
                                    "provider": provider,
                                    "block_type": "other",
                                    "num_variants": num_variants
                                }
                            )

                            st.success("✅ Ответ обновлен!")
                            st.rerun()
                else:
                    error_count += 1
                    with st.expander(f"❌ Вариант {i + 1} (ошибка)", expanded=False):
                        st.error(f"**Ошибка:** {result.get('error', 'Неизвестная ошибка')}")
                        st.markdown("**Отправленный промпт:**")
                        st.code(final_prompt, language="markdown")

            # Статистика
            st.metric("✅ Успешно", success_count)
            st.metric("❌ Ошибок", error_count)

            successful_results = [r["text"] for r in results if r.get("success")]

            if successful_results:
                # Сохраняем инструкции с контекстом блока
                st.session_state.ai_instruction_manager.save_instruction(
                    block_id,
                    var_name,
                    successful_results,
                    context,
                    {
                        "provider": provider,
                        "block_type": "other",
                        "num_variants": num_variants
                    }
                )

                st.success(f"✅ Сгенерировано {len(successful_results)} вариантов!")
            else:
                st.error("❌ Не удалось сгенерировать ни одного варианта")

def show_variables_editor():
    """Редактор переменных с поддержкой AI"""

    blocks = st.session_state.block_manager.get_all_blocks()

    if not blocks:
        st.info("Нет блоков для редактирования переменных")
        return

    # Выбор блока
    block_ids = list(blocks.keys())
    selected_block_id = st.selectbox(
        "Выберите блок:",
        block_ids,
        format_func=lambda x: f"{blocks[x].get('name', x)} ({blocks[x].get('block_type', 'other')})",
        key="var_editor_block"
    )

    selected_block = blocks[selected_block_id]
    variables = selected_block.get("variables", [])
    variables_data = selected_block.get("variables_data", {})

    if not variables:
        st.info("У этого блока нет переменных")
        return

    st.subheader(f"🔧 Редактирование переменных блока: {selected_block['name']}")

    # Добавляем табы для разных типов переменных
    tab_static, tab_ai, tab_dynamic = st.tabs(["📝 локальные", "🤖 AI", "🌀 глобальные"])

    with tab_static:
        # локальные переменные
        static_vars = [v for v in variables if variables_data.get(v, {}).get("type", "static") == "static"]

        if not static_vars:
            st.info("Нет локальных переменных. Создайте новую переменную или используйте AI/глобальные переменные.")

            # Кнопка создания новой статической переменной
            new_static_var_name = st.text_input("Название новой статической переменной:")
            if st.button("➕ Создать локальную переменную") and new_static_var_name:
                # Добавляем переменную в список
                variables.append(new_static_var_name)
                variables_data[new_static_var_name] = {
                    "name": new_static_var_name,
                    "description": f"локальная переменная: {new_static_var_name}",
                    "type": "static",
                    "values": [f"Значение для {new_static_var_name} 1", f"Значение для {new_static_var_name} 2"]
                }

                # Сохраняем блок
                selected_block["variables"] = variables
                selected_block["variables_data"] = variables_data
                st.session_state.block_manager.save_block(selected_block, variables_data)
                st.success(f"Создана локальная переменная '{new_static_var_name}'")
                st.rerun()
        else:
            selected_static_var = st.selectbox(
                "Выберите локальную переменную:",
                static_vars,
                key="var_selector_static"
            )

            if selected_static_var:
                var_data = variables_data.get(selected_static_var, {
                    "name": selected_static_var,
                    "description": f"Описание для {selected_static_var}",
                    "type": "static",
                    "values": ["Пример значения 1", "Пример значения 2"]
                })

                # Редактирование статической переменной
                with st.form(key=f"edit_static_var_form_{selected_static_var}"):
                    st.write(f"**локальная переменная:** `{selected_static_var}`")

                    description = st.text_input(
                        "Описание переменной:",
                        value=var_data.get("description", "")
                    )

                    # Значения переменной
                    st.markdown("**Значения переменной:**")
                    current_values = var_data.get("values", [])
                    values_text = "\n".join(current_values)

                    new_values = st.text_area(
                        "Значения (каждое с новой строки):",
                        value=values_text,
                        height=200,
                        key=f"static_values_{selected_static_var}"
                    )

                    col_save1, col_save2 = st.columns(2)
                    with col_save1:
                        if st.form_submit_button("💾 Сохранить переменную", use_container_width=True):
                            # Обновляем данные переменной
                            variables_data[selected_static_var] = {
                                "name": selected_static_var,
                                "description": description,
                                "type": "static",
                                "values": [v.strip() for v in new_values.split("\n") if v.strip()]
                            }

                            # Сохраняем в блок
                            selected_block["variables_data"] = variables_data
                            if st.session_state.block_manager.save_block(selected_block, variables_data):
                                st.success(f"✅ Переменная '{selected_static_var}' сохранена!")
                                st.rerun()
                            else:
                                st.error(f"❌ Ошибка сохранения переменной")

                    with col_save2:
                        if st.form_submit_button("🗑️ Удалить переменную", type="secondary", use_container_width=True):
                            # Удаляем из списка переменных блока
                            if selected_static_var in variables:
                                variables.remove(selected_static_var)

                            # Удаляем из variables_data
                            if selected_static_var in variables_data:
                                del variables_data[selected_static_var]

                            # Сохраняем блок
                            selected_block["variables"] = variables
                            selected_block["variables_data"] = variables_data
                            if st.session_state.block_manager.save_block(selected_block, variables_data):
                                st.success(f"✅ Переменная '{selected_static_var}' удалена!")
                                st.rerun()

    # В функции show_variables_editor, в разделе AI (таб "🤖 AI"):

    with tab_ai:
        # AI переменные
        ai_vars = [v for v in variables if variables_data.get(v, {}).get("type") == "ai"]

        # Кнопка создания новой AI переменной (всегда видна)
        with st.expander("➕ Создать новую AI переменную", expanded=False):
            col_new1, col_new2 = st.columns([3, 1])
            with col_new1:
                new_ai_var_name = st.text_input(
                    "Название новой AI переменной:",
                    key="new_ai_var_name_input"
                )

            with col_new2:
                if st.button("➕ Создать", use_container_width=True, key="create_new_ai_var_btn") and new_ai_var_name:
                    # Проверяем, что переменная не существует
                    if new_ai_var_name in variables:
                        st.error(f"Переменная '{new_ai_var_name}' уже существует!")
                    else:
                        # Добавляем переменную в список
                        variables.append(new_ai_var_name)

                        # Базовый промпт для AI переменной (зависит от типа блока)
                        base_ai_prompt = ""
                        if selected_block.get("block_type") == "characteristic":
                            char_type = selected_block.get("settings", {}).get("characteristic_type", "regular")
                            if char_type == "regular":
                                base_ai_prompt = """Сгенерируй линейный перечень (8-12 пунктов) обобщённых аналитических тезисов-вопросов, разделённых “;”, для глубокого инженерно-технического анализа заданной ХАРАКТЕРИСТИКИ в рамках указанной КАТЕГОРИИ продукции.

    Категория: {категория}
    Характеристика: {характеристика}

    Формат вывода:
    - Требуется: Строго один абзац, где пункты разделены только точкой с запятой (;). Не используй маркеры списка (цифры, точки, тире), не разбивай на отдельные строки. Каждый пункт должен начинаться с глагола-запроса в повелительном наклонении.
    - Пример формата: Опиши...; укажи...; поясни...; объясни...; (и так далее).

    Каждый тезис должен:
    - Начинаться с глагола-запроса (опиши, укажи, поясни, объясни, покажи, расскажи, оцени, сравни, определи).
    - Содержать общие формулировки, на место которых потом можно будет подставить конкретное значение характеристики. Использовать местоимения и выражения типа 'данная характеристика', 'этот параметр', 'выбранное значение'.
    - Фокусироваться на практическом влиянии: на применение, монтаж, эксплуатацию, надёжность, стоимость и безопасность в рамках указанной категории.
    - Быть строго техническим и нейтральным, без упоминания конкретных марок, типоразмеров, ГОСТов или торговых названий."""
                            else:  # unique
                                base_ai_prompt = """Сгенерируй техническое описание для конкретного значения характеристики в рамках указанной категории.

    Категория: {категория}
    Характеристика: {характеристика}
    Значение: {значение}

    Требования:
    1. Сфокусируйся на конкретном значении характеристики
    2. Объясни практическую значимость этого значения
    3. Сравни с другими возможными значениями (если уместно)
    4. Укажи преимущества и особенности этого конкретного значения
    5. Будь технически точным, но понятным"""
                        else:
                            # Для других типов блоков
                            base_ai_prompt = """Сгенерируй контент на основе предоставленного контекста.

    Контекст:
    {контекст_категория}

    Требования:
    1. Будь информативным и полезным
    2. Используй технический, но понятный язык
    3. Избегай маркетинговых клише
    4. Сфокусируйся на практической пользе"""

                        variables_data[new_ai_var_name] = {
                            "name": new_ai_var_name,
                            "description": f"AI переменная: {new_ai_var_name}",
                            "type": "ai",
                            "ai_prompt": base_ai_prompt,
                            "ai_num_variants": 3,
                            "ai_provider": "openai",
                            "ai_context_type": selected_block.get("block_type", "other"),
                            "values": []
                        }

                        # Сохраняем блок
                        selected_block["variables"] = variables
                        selected_block["variables_data"] = variables_data
                        st.session_state.block_manager.save_block(selected_block, variables_data)
                        st.success(f"Создана AI переменная '{new_ai_var_name}'")
                        st.rerun()

        # Редактирование существующих AI переменных
        if ai_vars:
            st.markdown("### ✏️ Редактирование AI переменных")

            # Создаем табы для каждой AI переменной
            ai_tabs = st.tabs([f"🤖 {var}" for var in ai_vars])

            for tab_idx, ai_var in enumerate(ai_vars):
                with ai_tabs[tab_idx]:
                    var_data = variables_data.get(ai_var, {
                        "name": ai_var,
                        "description": f"Описание для {ai_var}",
                        "type": "ai",
                        "ai_prompt": "",
                        "ai_num_variants": 3,
                        "ai_provider": "openai",
                        "ai_context_type": selected_block.get("block_type", "other"),
                        "values": []
                    })

                    # Основные поля переменной
                    st.markdown(f"#### AI переменная: `{ai_var}`")

                    with st.form(key=f"edit_ai_var_form_{ai_var}_{tab_idx}"):
                        description = st.text_input(
                            "Описание переменной:",
                            value=var_data.get("description", ""),
                            key=f"ai_desc_{ai_var}_{tab_idx}"
                        )

                        # AI настройки
                        st.markdown("##### 🤖 Настройки AI генерации")

                        col_ai1, col_ai2 = st.columns(2)
                        with col_ai1:
                            # Расширяем список доступных провайдеров
                            available_ai_providers = ["openai", "deepseek", "genapi_gemini", "true_gemini"]

                            ai_provider = st.selectbox(
                                "AI провайдер:",
                                available_ai_providers,
                                index=available_ai_providers.index(var_data.get("ai_provider", "deepseek"))
                                if var_data.get("ai_provider") in available_ai_providers else 1,
                                key=f"ai_provider_{ai_var}_{tab_idx}"
                            )

                        with col_ai2:
                            ai_num_variants = st.number_input(
                                "Количество вариантов:",
                                min_value=1,
                                max_value=10,
                                value=var_data.get("ai_num_variants", 3),
                                key=f"ai_num_variants_{ai_var}_{tab_idx}"
                            )

                        # Промпт для AI
                        st.markdown("##### 📝 Промпт для генерации")
                        st.caption("""
                        Доступные переменные для подстановки:
                        - Для characteristic блоков: {категория}, {характеристика}, {значение}, {тип}
                        - Для других блоков: {контекст_категория}, {маркер}
                        """)

                        ai_prompt = st.text_area(
                            "Промпт:",
                            value=var_data.get("ai_prompt", ""),
                            height=300,
                            key=f"ai_prompt_{ai_var}_{tab_idx}"
                        )

                        # Кнопки управления
                        col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])
                        with col_btn1:
                            save_btn = st.form_submit_button("💾 Сохранить настройки", use_container_width=True)
                            if save_btn:
                                # Обновляем данные переменной
                                var_data.update({
                                    "description": description,
                                    "type": "ai",
                                    "ai_prompt": ai_prompt,
                                    "ai_num_variants": ai_num_variants,
                                    "ai_provider": ai_provider,
                                    "ai_context_type": selected_block.get("block_type", "other")
                                })

                                variables_data[ai_var] = var_data
                                selected_block["variables_data"] = variables_data
                                if st.session_state.block_manager.save_block(selected_block, variables_data):
                                    st.success(f"✅ Настройки AI переменной '{ai_var}' сохранены!")
                                    st.rerun()

                        with col_btn2:
                            if st.form_submit_button("🚀 Генерировать", type="primary", use_container_width=True):
                                # Сохраняем сначала настройки
                                var_data.update({
                                    "description": description,
                                    "type": "ai",
                                    "ai_prompt": ai_prompt,
                                    "ai_num_variants": ai_num_variants,
                                    "ai_provider": ai_provider
                                })

                                variables_data[ai_var] = var_data
                                selected_block["variables_data"] = variables_data
                                st.session_state.block_manager.save_block(selected_block, variables_data)

                                # Устанавливаем контекст для генерации
                                st.session_state.current_ai_var_for_generation = ai_var
                                st.session_state.current_block_for_ai = selected_block_id
                                st.session_state.current_ai_tab_idx = tab_idx
                                st.rerun()

                        with col_btn3:
                            if st.form_submit_button("🗑️ Удалить", type="secondary", use_container_width=True):
                                # Подтверждение удаления
                                if st.session_state.get(f"confirm_delete_{ai_var}", False):
                                    # Удаляем из списка переменных блока
                                    if ai_var in variables:
                                        variables.remove(ai_var)

                                    # Удаляем из variables_data
                                    if ai_var in variables_data:
                                        del variables_data[ai_var]

                                    # Удаляем сохраненные инструкции
                                    if 'ai_instruction_manager' in st.session_state:
                                        st.session_state.ai_instruction_manager.delete_instruction(
                                            selected_block_id, ai_var
                                        )

                                    # Сохраняем блок
                                    selected_block["variables"] = variables
                                    selected_block["variables_data"] = variables_data
                                    if st.session_state.block_manager.save_block(selected_block, variables_data):
                                        st.success(f"✅ AI переменная '{ai_var}' удалена!")
                                        st.rerun()
                                else:
                                    st.session_state[f"confirm_delete_{ai_var}"] = True
                                    st.warning(
                                        f"Нажмите '🗑️ Удалить' еще раз для подтверждения удаления переменной '{ai_var}'")
                                    st.rerun()

                    # Если для этой переменной выбрана генерация
                    if (hasattr(st.session_state, 'current_ai_var_for_generation') and
                            st.session_state.current_ai_var_for_generation == ai_var and
                            hasattr(st.session_state, 'current_block_for_ai') and
                            st.session_state.current_block_for_ai == selected_block_id):

                        st.markdown("---")
                        st.markdown("### 🚀 Генерация AI-инструкций")

                        # Определяем тип блока и соответствующий контекст генерации
                        block_type = selected_block.get("block_type", "other")

                        if block_type == "characteristic":
                            # Генерация для characteristic блоков
                            show_ai_generation_for_characteristics(
                                selected_block_id, ai_var, var_data, selected_block
                            )
                        else:
                            # Генерация для других типов блоков
                            show_ai_generation_for_other_blocks(
                                selected_block_id, ai_var, var_data, selected_block
                            )

                        # Кнопка отмены генерации
                        if st.button("❌ Отменить генерацию", key=f"cancel_gen_{ai_var}", use_container_width=True):
                            del st.session_state.current_ai_var_for_generation
                            if hasattr(st.session_state, 'current_block_for_ai'):
                                del st.session_state.current_block_for_ai
                            if hasattr(st.session_state, 'current_ai_tab_idx'):
                                del st.session_state.current_ai_tab_idx
                            st.rerun()

        else:
            st.info("""
            **AI переменные**

            AI переменные позволяют генерировать глобальний контент с помощью искусственного интеллекта.

            **Преимущества:**
            - Автоматическая генерация уникального контента
            - Адаптация под разные типы блоков
            - Поддержка нескольких AI провайдеров
            - Сохранение и редактирование сгенерированных результатов

            **Как использовать:**
            1. Создайте новую AI переменную с помощью кнопки выше
            2. Настройте промпт для генерации
            3. Запустите генерацию для создания контента
            4. Редактируйте и сохраняйте результаты

            **Поддерживаемые типы блоков:**
            - Characteristic блоки: генерация для характеристик товаров
            - Other блоки: генерация общего контента (введения, заключения и т.д.)
            """)

    with tab_dynamic:
        # глобальные переменные (извлекаем из блока)
        dynamic_vars = []

        # Ищем глобальные переменные в шаблоне
        template = selected_block.get("template", "")
        all_vars_in_template = re.findall(r'\{([^}]+)\}', template)

        # Получаем список глобальных переменных из менеджера
        if 'dynamic_var_manager' in st.session_state:
            dynamic_var_names = list(st.session_state.dynamic_var_manager.get_all_dynamic_vars().keys())

            # Находим пересечение - переменные, которые есть и в шаблоне и в глобальных
            dynamic_vars = [v for v in dynamic_var_names if v in all_vars_in_template]

        if not dynamic_vars:
            st.info("""
            **глобальные переменные**

            глобальные переменные автоматически подставляются из конфигурации.
            Они доступны для использования в любом блоке.

            Чтобы добавить глобальную переменную:
            1. Перейдите на вкладку "🌀 Редактирование глобальных переменных"
            2. Создайте новую глобальную переменную
            3. Используйте `{название_переменной}` в шаблоне блока

            **Примеры доступных глобальных переменных:**
            - `{стоп}` - стоп-слова и ограничения
            - `{контекст_категория}` - категория товара
            - `{значение_форматированное}` - значение характеристики
            - `{название_характеристики}` - название характеристики
            - `{характеристика_маркер}` - маркер для характеристик
            - `{маркер}` - общий маркер
            """)
        else:
            st.success(f"✅ Найдено {len(dynamic_vars)} глобальных переменных в шаблоне")

            for dyn_var in dynamic_vars:
                # Получаем информацию о глобальной переменной
                if 'dynamic_var_manager' in st.session_state:
                    var_info = st.session_state.dynamic_var_manager.get_dynamic_variable(dyn_var)

                    if var_info:
                        with st.expander(f"глобальная переменная: `{{{dyn_var}}}`"):
                            st.write(f"**Описание:** {var_info.get('description', 'Нет описания')}")
                            st.write(f"**Источник:** {var_info.get('source', 'unknown')}")

                            values = var_info.get("values", [])
                            if values and var_info.get("source") == "config":
                                st.write(f"**Количество значений:** {len(values)}")
                                st.write("**Примеры значений:**")
                                for val in values[:3]:  # Показываем первые 3 значения
                                    st.write(f"- {val}")
                                if len(values) > 3:
                                    st.write(f"... и еще {len(values) - 3} значений")

            st.info(
                "💡 Для редактирования глобальных переменных перейдите на соответствующую вкладку в основном интерфейсе")

    # Информация о переменных блока
    with st.expander("📊 Статистика по переменным", expanded=False):
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("Всего переменных", len(variables))
        with col_stat2:
            static_count = len([v for v in variables if variables_data.get(v, {}).get("type", "static") == "static"])
            st.metric("локальных", static_count)
        with col_stat3:
            ai_count = len([v for v in variables if variables_data.get(v, {}).get("type") == "ai"])
            st.metric("AI", ai_count)

def load_blocks(self):
    """Загружает все блоки из файлов"""
    self.blocks = {}

    # Проверяем, есть ли папки блоков
    print(f"🔍 BlockManager.load_blocks() — сканируем папку: {self.blocks_dir}")
    block_dirs = [d for d in self.blocks_dir.iterdir() if d.is_dir()]
    print(f"   Найдено папок блоков: {len(block_dirs)}")

    # Загружаем все блоки
    for block_dir in block_dirs:
        block_file = block_dir / "block.json"
        variables_file = block_dir / "variables.json"

        if block_file.exists():
            try:
                with open(block_file, 'r', encoding='utf-8') as f:
                    block_data = json.load(f)

                # Устанавливаем тип блока по умолчанию, если не указан
                if "block_type" not in block_data:
                    # Определяем тип по названию или другим признакам
                    if "характеристика" in block_data.get("name", "").lower() or "характеристик" in block_data.get(
                            "description", "").lower():
                        block_data["block_type"] = "characteristic"
                    else:
                        block_data["block_type"] = "other"

                # Для characteristic блоков устанавливаем characteristic_type по умолчанию, если не указан
                if block_data.get("block_type") == "characteristic":
                    if "settings" not in block_data:
                        block_data["settings"] = {}
                    if "characteristic_type" not in block_data["settings"]:
                        # Определяем по названию
                        block_name = block_data.get("name", "").lower()
                        if "unique" in block_name:
                            block_data["settings"]["characteristic_type"] = "unique"
                        else:
                            block_data["settings"]["characteristic_type"] = "regular"

                # Загружаем переменные
                if variables_file.exists():
                    with open(variables_file, 'r', encoding='utf-8') as f:
                        block_data["variables_data"] = json.load(f)
                else:
                    block_data["variables_data"] = {}

                self.blocks[block_data["block_id"]] = block_data

            except Exception as e:
                st.error(f"Ошибка загрузки блока {block_dir.name}: {e}")
# В конец phase3.py (перед if __name__ == "__main__":)

# ===== Новые функции для массовой генерации AI =====
def save_phase3_settings(app_state=None):
    """Сохраняет ТОЛЬКО выбранные блоки в ПРОЕКТ (сами блоки уже в домене)"""
    if 'block_manager' in st.session_state:
        # ❌ НЕ сохраняем блоки в домен - они уже там через BlockManager
        # ✅ Сохраняем ТОЛЬКО информацию о выбранных блоках в проект
        selected_blocks = st.session_state.get('selected_blocks', {})

        phase3_data = {
            'selected_blocks': selected_blocks,
            'blocks_count': len(st.session_state.block_manager.get_all_blocks()),
            'settings_saved': True,
            'saved_at': datetime.now().isoformat()
        }

        if 'app_data' in st.session_state:
            st.session_state.app_data['phase3'] = phase3_data

        if app_state:
            app_state.set_phase_data(3, phase3_data)
            app_state.save_project()

        print(f"💾 Phase3 settings saved to project")
        return True
    return False
# ЗАМЕНИТЕ существующие функции batch_generate_for_characteristic и batch_generate_for_other
# на этот исправленный код:

def batch_generate_for_characteristic(block_id, var_name, var_data, block, provider=None):
    """
    Генерирует AI-инструкции для characteristic-блока.
    Данные берутся из ПРОЕКТА (app_state / session_state), а не из домена!
    """
    used_provider = provider or var_data.get("ai_provider", "deepseek")

    print(f"🔍 batch_generate_for_characteristic START")
    print(f"   block_id: {block_id}, var_name: {var_name}, provider: {used_provider}")

    # ===== БЕРЁМ ДАННЫЕ ИЗ ПРОЕКТА (session_state) =====
    # Данные фазы 2 (категория)
    phase2_data = get_phase2_data()
    category = phase2_data.get('category', '') if phase2_data else ''

    # Данные фазы 1 (характеристики)
    characteristics = get_characteristics_data()

    print(f"   Категория из проекта: '{category}'")
    print(f"   Характеристик из проекта: {len(characteristics)}")

    if not category:
        print(f"   ❌ Нет категории в проекте!")
        return {"success": 0, "errors": 0, "error": "Нет данных категории. Сначала загрузите данные в фазу 2."}

    if not characteristics:
        print(f"   ❌ Нет характеристик в проекте!")
        return {"success": 0, "errors": 0, "error": "Нет данных характеристик. Сначала загрузите данные в фазу 1."}

    # Инициализируем AI менеджеры (они работают с проектом)
    init_ai_managers()

    prompt_template = var_data.get("ai_prompt", "")
    num_variants = var_data.get("ai_num_variants", 1)
    block_char_type = block.get("settings", {}).get("characteristic_type", "regular")

    print(f"   block_char_type: {block_char_type}")

    success_count = 0
    error_count = 0
    details = []

    for char in characteristics:
        try:
            char_id = char.get('char_id')
            char_name = char.get('char_name')
            is_unique = char.get('is_unique', False)
            values = char.get('values', [])

            # Пропускаем неподходящие типы
            if block_char_type == "regular" and is_unique:
                print(f"   Пропуск {char_name} (regular блок, unique характеристика)")
                continue
            elif block_char_type == "unique" and not is_unique:
                print(f"   Пропуск {char_name} (unique блок, regular характеристика)")
                continue

            print(f"   Обработка: {char_name} (unique={is_unique}, значений={len(values)})")

            if is_unique:
                for value_item in values:
                    try:
                        value = value_item.get('value', '')
                        context = {
                            "категория": category,
                            "характеристика": char_name,
                            "значение": value,
                            "тип": "unique"
                        }

                        gen_results = st.session_state.ai_generator.generate_instruction(
                            prompt_template, context, provider=used_provider, num_variants=1
                        )

                        if gen_results and gen_results[0].get("success"):
                            instruction = gen_results[0]["text"]
                            # Сохраняем в менеджер инструкций (работает с ПРОЕКТОМ)
                            st.session_state.ai_instruction_manager.save_instruction(
                                block_id, var_name, [instruction], context,
                                {"provider": used_provider, "char_id": char_id, "char_name": char_name, "value": value}
                            )
                            success_count += 1
                            print(f"      ✅ Успешно: {value}")
                        else:
                            error_msg = gen_results[0].get('error', 'Ошибка генерации') if gen_results else 'Нет ответа'
                            error_count += 1
                            details.append({"char": char_name, "value": value, "status": "error", "error": error_msg})
                            print(f"      ❌ Ошибка: {error_msg}")
                    except Exception as e:
                        error_count += 1
                        details.append({"char": char_name, "value": value, "status": "error", "error": str(e)})
                        print(f"      ❌ Exception: {e}")
            else:
                try:
                    context = {
                        "категория": category,
                        "характеристика": char_name,
                        "тип": "regular"
                    }

                    gen_results = st.session_state.ai_generator.generate_instruction(
                        prompt_template, context, provider=used_provider, num_variants=num_variants
                    )

                    successful = [r["text"] for r in gen_results if r.get("success")]
                    failed = [r for r in gen_results if not r.get("success")]

                    if successful:
                        # Сохраняем в менеджер инструкций (работает с ПРОЕКТОМ)
                        st.session_state.ai_instruction_manager.save_instruction(
                            block_id, var_name, successful, context,
                            {"provider": used_provider, "char_id": char_id, "char_name": char_name}
                        )
                        success_count += len(successful)
                        print(f"      ✅ Успешно: {len(successful)} вариантов")

                    if failed:
                        error_count += len(failed)
                        print(f"      ⚠️ Ошибок: {len(failed)}")
                except Exception as e:
                    error_count += num_variants
                    details.append({"char": char_name, "status": "error", "error": str(e)})
                    print(f"      ❌ Exception: {e}")

        except Exception as e:
            error_count += 1
            details.append({"char": "unknown", "status": "error", "error": str(e)})
            print(f"   ❌ Общая ошибка: {e}")

    # Перезагружаем инструкции после генерации
    if 'ai_instruction_manager' in st.session_state:
        st.session_state.ai_instruction_manager.reload()

    result = {"success": success_count, "errors": error_count, "details": details}
    print(f"🔍 batch_generate_for_characteristic END: success={success_count}, errors={error_count}")

    if error_count > 0 and success_count == 0:
        result["error"] = "Полная ошибка генерации"
    elif error_count > 0 and success_count > 0:
        result["error"] = f"Частичная генерация: {success_count} успешно, {error_count} ошибок"

    return result


def batch_generate_for_other(block_id, var_name, var_data, block, provider=None):
    """
    Генерирует AI-инструкции для other-блока без UI.
    Данные берутся из ПРОЕКТА (session_state)!
    """
    used_provider = provider or var_data.get("ai_provider", "deepseek")

    # Берём данные из ПРОЕКТА
    phase2_data = get_phase2_data()
    category = phase2_data.get('category', '') if phase2_data else ''

    if not category:
        return {"success": 0, "errors": 0, "error": "Нет категории в проекте"}

    # Инициализируем AI менеджеры
    init_ai_managers()

    prompt_template = var_data.get("ai_prompt", "")
    num_variants = var_data.get("ai_num_variants", 3)

    context = {
        "категория": category,
        "тип": "other",
        "block_id": block_id,
        "var_name": var_name
    }

    success_count = 0
    error_count = 0

    try:
        gen_results = st.session_state.ai_generator.generate_instruction(
            prompt_template, context, provider=used_provider, num_variants=num_variants
        )

        for result in gen_results:
            if result.get("success"):
                success_count += 1
            else:
                error_count += 1

        successful = [r["text"] for r in gen_results if r.get("success")]

        if successful:
            st.session_state.ai_instruction_manager.save_instruction(
                block_id, var_name, successful, context,
                {"provider": used_provider, "block_type": "other", "num_variants": num_variants}
            )

        # Перезагружаем инструкции после генерации
        st.session_state.ai_instruction_manager.reload()

        return {"success": success_count, "errors": error_count}

    except Exception as e:
        return {"success": 0, "errors": num_variants, "error": str(e)}
def has_ai_values(block_id, var_name):
    phase2_data = get_phase2_data()
    current_category = phase2_data.get('category', '').strip()

    # Нормализуем текущую категорию
    current_category_norm = normalize_string(current_category)

    if not current_category_norm:
        return False

    ai_mgr = st.session_state.get('ai_instruction_manager')
    if not ai_mgr or block_id not in ai_mgr.instructions or var_name not in ai_mgr.instructions[block_id]:
        return False

    for context_hash, data in ai_mgr.instructions[block_id][var_name].items():
        context = data.get("context", {})
        cat_in_context = context.get("категория") or context.get("category", "")

        # Нормализуем категорию из контекста
        cat_in_context_norm = normalize_string(cat_in_context)

        # Сравниваем нормализованные строки
        if cat_in_context_norm == current_category_norm:
            if data.get("values"):
                return True

    return False
# Добавить в phase3.py

def get_all_ai_variables():
    """Возвращает список всех AI переменных с их данными"""
    if 'block_manager' not in st.session_state:
        return []

    blocks = st.session_state.block_manager.get_all_blocks()
    ai_vars = []

    for block_id, block in blocks.items():
        variables_data = block.get("variables_data", {})
        for var_name, var_data in variables_data.items():
            if var_data.get("type") == "ai":
                ai_vars.append((block_id, var_name, block, var_data))

    return ai_vars


def run_autopilot_if_needed():
    """Запускает автопилот для фазы 3, если он активен"""

    if 'autopilot_config' not in st.session_state:
        return False

    config = st.session_state.autopilot_config

    # Проверяем, нужно ли запустить автопилот
    if (config.get('enabled', False) and
            3 in config.get('active_phases', []) and
            config['phases'].get(3, {}).get('auto_enabled', False) and
            not config.get('current_phase_running', False)):

        # Запускаем автопилот
        from auto.autopilot import run_autopilot_phase3, AutoPilotManager

        manager = AutoPilotManager()
        manager.start_phase(3)

        # Выполняем автопилот
        success = run_autopilot_phase3()

        if not success:
            st.rerun()  # Останавливаемся, если ошибка

        return True

    return False
# Добавить в phase3.py

def get_expected_generation_count(block_id, var_name, block):
    """Возвращает ожидаемое количество генерируемых инструкций"""

    # Получаем данные из фазы 2
    phase2_data = get_phase2_data()
    characteristics = get_characteristics_data()

    block_type = block.get('block_type', 'other')

    if block_type == 'characteristic':
        # Для characteristic блоков считаем количество значений
        block_char_type = block.get('settings', {}).get('characteristic_type', 'regular')
        count = 0

        for char in characteristics:
            is_unique = char.get('is_unique', False)

            if block_char_type == 'regular' and not is_unique:
                count += 1  # Одна инструкция на характеристику
            elif block_char_type == 'unique' and is_unique:
                values = char.get('values', [])
                count += len(values)  # Инструкция на каждое значение

        return count
    else:
        # Для other блоков - нужно получить var_data из блока
        variables_data = block.get("variables_data", {})
        var_data = variables_data.get(var_name, {})
        return var_data.get('ai_num_variants', 3)
# phase3.py - добавить в конец файла


def is_valid_context(context) -> bool:
    """Проверяет, является ли context объектом ProjectContext"""
    if context is None:
        return False
    return hasattr(context, 'project_id') and hasattr(context, 'set_phase_data')
def batch_generate_for_characteristic_with_data(block_id, var_name, var_data, block, provider, category, characteristics, app_state=None, context=None):
    """Генерирует AI-инструкции для characteristic-блока с данными из проекта"""

    print(f"🔍 batch_generate_for_characteristic_with_data START")
    print(f"   block_id: {block_id}, var_name: {var_name}")
    print(f"   provider: {provider}")
    print(f"   category: '{category}'")
    print(f"   characteristics count: {len(characteristics)}")

    if not category:
        print("❌ Нет категории")
        return {"success": 0, "errors": 0, "error": "Нет категории"}

    if not characteristics:
        print("❌ Нет характеристик")
        return {"success": 0, "errors": 0, "error": "Нет характеристик"}

    # ========== ПОЛУЧАЕМ PROJECT_ID И USER_ID ==========
    project_id = None
    user_id = None
    site_name = None
    domain_name = None

    # ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
    if context is not None:
        project_id = getattr(context, 'project_id', None)
        user_id = getattr(context, 'user_id', None)
        site_name = getattr(context, 'site_name', None)
        domain_name = getattr(context, 'domain_name', None)
        print(f"   project_id из контекста: {project_id}")
        print(f"   user_id из контекста: {user_id}")

    # ПРИОРИТЕТ 2: ИЗ APP_STATE
    if project_id is None and app_state is not None:
        if hasattr(app_state, 'current_project_id'):
            project_id = app_state.current_project_id
        elif hasattr(app_state, 'get_current_project_id'):
            project_id = app_state.get_current_project_id()
        if hasattr(app_state, 'user_id'):
            user_id = app_state.user_id

    # ПРИОРИТЕТ 3: ИЗ SESSION_STATE
    if project_id is None:
        project_id = st.session_state.get('current_project_id')
    if user_id is None:
        user_id = st.session_state.get('user_id')
    if site_name is None:
        site_name = st.session_state.get('current_site', 'steelborg')
    if domain_name is None:
        domain_name = st.session_state.get('current_domain', 'default')

    print(f"   ИТОГО: project_id={project_id}, user_id={user_id}, site={site_name}, domain={domain_name}")

    # ========== ИНИЦИАЛИЗИРУЕМ AI МЕНЕДЖЕРЫ С ПРОЕКТОМ ==========
    # ✅ СОЗДАЕМ AIInstructionManager С ПРАВИЛЬНЫМИ ПАРАМЕТРАМИ
    if 'ai_instruction_manager' not in st.session_state:
        from ai_settings.ai_module import AIInstructionManager
        st.session_state.ai_instruction_manager = AIInstructionManager(
            project_id=project_id,
            user_id=user_id,
            site_name=site_name,
            domain_name=domain_name,
            context=context
        )
        print(f"   ✅ AIInstructionManager создан с project_id={project_id}")

    ai_mgr = st.session_state.ai_instruction_manager

    # ✅ ПРОВЕРЯЕМ, ЧТО МЕНЕДЖЕР ПРИВЯЗАН К ПРАВИЛЬНОМУ ПРОЕКТУ
    if project_id and str(project_id) not in str(ai_mgr.storage_dir):
        print(f"   ⚠️ AIInstructionManager привязан к другому проекту, пересоздаем...")
        from ai_settings.ai_module import AIInstructionManager
        st.session_state.ai_instruction_manager = AIInstructionManager(
            project_id=project_id,
            user_id=user_id,
            site_name=site_name,
            domain_name=domain_name,
            context=context
        )
        ai_mgr = st.session_state.ai_instruction_manager
        print(f"   ✅ Пересоздан: {ai_mgr.storage_dir}")

    # ========== ПРОВЕРЯЕМ API КЛЮЧ ==========
    from api_key_manager import APIKeyManager
    key_manager = APIKeyManager(user_id=user_id, context=context)
    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()
    dm = st.session_state.domain_manager

    api_key = key_manager.get_api_key(dm.site_name, dm.get_current_domain(), provider)
    if not api_key:
        print(f"❌ Нет API ключа для {provider} в домене {dm.get_current_domain()}")
        return {"success": 0, "errors": 0, "error": f"Нет API ключа для {provider}"}

    # ========== ЗАПУСКАЕМ ГЕНЕРАЦИЮ ==========
    prompt_template = var_data.get("ai_prompt", "")
    num_variants = var_data.get("ai_num_variants", 1)
    block_char_type = block.get("settings", {}).get("characteristic_type", "regular")

    print(f"   prompt_template: {prompt_template[:100]}...")
    print(f"   num_variants: {num_variants}")
    print(f"   block_char_type: {block_char_type}")

    success_count = 0
    error_count = 0
    errors_list = []

    for char in characteristics:
        try:
            char_id = char.get('char_id')
            char_name = char.get('char_name')
            is_unique = char.get('is_unique', False)
            values = char.get('values', [])

            # Пропускаем неподходящие типы
            if block_char_type == "regular" and is_unique:
                print(f"   Пропуск {char_name} (regular блок, unique характеристика)")
                continue
            elif block_char_type == "unique" and not is_unique:
                print(f"   Пропуск {char_name} (unique блок, regular характеристика)")
                continue

            print(f"   Обработка: {char_name} (unique={is_unique}, значений={len(values)})")

            if is_unique:
                for value_idx, value_item in enumerate(values):
                    try:
                        value = value_item.get('value', '')
                        context = {
                            "категория": category,
                            "характеристика": char_name,
                            "значение": value,
                            "тип": "unique"
                        }

                        print(f"      Генерация для {char_name} = {value}")

                        gen_results = st.session_state.ai_generator.generate_instruction(
                            prompt_template,
                            context,
                            provider=provider,
                            num_variants=1,
                            user_id=user_id,
                            project_id=project_id
                        )

                        if gen_results and gen_results[0].get("success"):
                            instruction = gen_results[0]["text"]
                            print(f"      ✅ Получен ответ: {instruction[:50]}...")

                            # ЯВНО СОХРАНЯЕМ В МЕНЕДЖЕР
                            saved = ai_mgr.save_instruction(
                                block_id,
                                var_name,
                                [instruction],
                                context,
                                {
                                    "provider": provider,
                                    "char_id": char_id,
                                    "char_name": char_name,
                                    "value": value,
                                    "value_idx": value_idx
                                }
                            )

                            if saved:
                                success_count += 1
                                print(f"      ✅ Сохранено для {value}")
                            else:
                                error_count += 1
                                errors_list.append({
                                    "char": char_name,
                                    "value": value,
                                    "error": "Ошибка сохранения"
                                })
                                print(f"      ❌ Ошибка сохранения для {value}")
                        else:
                            error_msg = gen_results[0].get('error', 'Ошибка генерации') if gen_results else 'Нет ответа'
                            error_count += 1
                            errors_list.append({
                                "char": char_name,
                                "value": value,
                                "error": error_msg
                            })
                            print(f"      ❌ Ошибка генерации: {error_msg}")
                    except Exception as e:
                        error_count += 1
                        errors_list.append({
                            "char": char_name,
                            "value": value_item.get('value', ''),
                            "error": str(e)
                        })
                        print(f"      ❌ Exception: {e}")
            else:
                try:
                    context = {
                        "категория": category,
                        "характеристика": char_name,
                        "тип": "regular"
                    }

                    print(f"      Генерация для {char_name} (regular)")

                    gen_results = st.session_state.ai_generator.generate_instruction(
                        prompt_template,
                        context,
                        provider=provider,
                        num_variants=num_variants,
                        user_id=user_id,
                        project_id=project_id
                    )

                    successful = [r["text"] for r in gen_results if r.get("success")]
                    failed = [r for r in gen_results if not r.get("success")]

                    print(f"      Успешно: {len(successful)}, Ошибок: {len(failed)}")

                    if successful:
                        saved = ai_mgr.save_instruction(
                            block_id,
                            var_name,
                            successful,
                            context,
                            {
                                "provider": provider,
                                "char_id": char_id,
                                "char_name": char_name,
                                "num_variants": len(successful)
                            }
                        )

                        if saved:
                            success_count += len(successful)
                            print(f"      ✅ Сохранено {len(successful)} вариантов для {char_name}")
                        else:
                            error_count += len(successful)
                            errors_list.append({
                                "char": char_name,
                                "error": "Ошибка сохранения"
                            })
                            print(f"      ❌ Ошибка сохранения для {char_name}")

                    if failed:
                        error_count += len(failed)
                        for f in failed:
                            errors_list.append({
                                "char": char_name,
                                "error": f.get('error', 'Ошибка генерации')
                            })
                        print(f"      ❌ Ошибок генерации: {len(failed)}")
                except Exception as e:
                    error_count += num_variants
                    errors_list.append({
                        "char": char_name,
                        "error": str(e)
                    })
                    print(f"      ❌ Exception для {char_name}: {e}")
        except Exception as e:
            error_count += 1
            errors_list.append({
                "char": char.get('char_name', 'unknown'),
                "error": str(e)
            })
            print(f"   ❌ Общая ошибка: {e}")

    # ========== ПРИНУДИТЕЛЬНО СОХРАНЯЕМ ==========
    ai_mgr.save_instructions()

    # Перезагружаем инструкции
    # batch_generate_for_characteristic_with_data - исправленный блок сохранения

    # ========== СОХРАНЯЕМ В КОНТЕКСТ ==========
    if context is not None and hasattr(context, 'set_phase_data'):
        context.set_phase_data(3, {
            'ai_instructions': ai_mgr.instructions,
            'blocks_count': len(st.session_state.block_manager.get_all_blocks()) if 'block_manager' in st.session_state else 0,
            'phase3_generated': True
        })
        context.save()  # ✅ ТОЛЬКО ЗДЕСЬ, ВНУТРИ ПРОВЕРКИ
        print(f"   ✅ Phase3 сохранена в контекст")
    else:
        print(f"   ⚠️ Контекст не является объектом ProjectContext, пропускаем сохранение")

    # Перезагружаем инструкции
    ai_mgr.reload()

    print(f"🔍 batch_generate_for_characteristic_with_data END: success={success_count}, errors={error_count}")

    result = {
        "success": success_count,
        "errors": error_count,
        "errors_list": errors_list
    }

    if error_count > 0 and success_count == 0:
        result["error"] = "Полная ошибка генерации"
    elif error_count > 0 and success_count > 0:
        result["error"] = f"Частичная генерация: {success_count} успешно, {error_count} ошибок"

    return result

def batch_generate_for_other_with_data(block_id, var_name, var_data, block, provider, category, app_state=None, context=None):
    """Генерирует AI-инструкции для other-блока с данными из проекта"""

    print(f"🔍 batch_generate_for_other_with_data START")
    print(f"   block_id: {block_id}, var_name: {var_name}")
    print(f"   provider: {provider}")
    print(f"   category: '{category}'")

    if not category:
        print("❌ Нет категории")
        return {"success": 0, "errors": 0, "error": "Нет категории"}

    # ========== ПОЛУЧАЕМ PROJECT_ID И USER_ID ==========
    project_id = None
    user_id = None
    site_name = None
    domain_name = None

    # ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
    if context is not None:
        # ✅ ПРОВЕРЯЕМ, ЧТО context - ЭТО ОБЪЕКТ, А НЕ СЛОВАРЬ
        if hasattr(context, 'project_id'):
            project_id = context.project_id
            user_id = context.user_id
            site_name = context.site_name
            domain_name = context.domain_name
        else:
            # Если context - словарь
            project_id = context.get('project_id')
            user_id = context.get('user_id')
            site_name = context.get('site_name')
            domain_name = context.get('domain_name')
        print(f"   project_id из контекста: {project_id}")
        print(f"   user_id из контекста: {user_id}")

    # ПРИОРИТЕТ 2: ИЗ SESSION_STATE
    if project_id is None:
        project_id = st.session_state.get('current_project_id')
    if user_id is None:
        user_id = st.session_state.get('user_id')
    if site_name is None:
        site_name = st.session_state.get('current_site', 'steelborg')
    if domain_name is None:
        domain_name = st.session_state.get('current_domain', 'default')

    print(f"   ИТОГО: project_id={project_id}, user_id={user_id}, site={site_name}, domain={domain_name}")

    # ========== ИНИЦИАЛИЗИРУЕМ AI МЕНЕДЖЕРЫ ==========
    if 'ai_instruction_manager' not in st.session_state:
        from ai_settings.ai_module import AIInstructionManager
        st.session_state.ai_instruction_manager = AIInstructionManager(
            project_id=project_id,
            user_id=user_id,
            site_name=site_name,
            domain_name=domain_name,
            context=context if hasattr(context, 'project_id') else None
        )
        print(f"   ✅ AIInstructionManager создан с project_id={project_id}")

    ai_mgr = st.session_state.ai_instruction_manager

    # ✅ ПРОВЕРЯЕМ ПРИВЯЗКУ К ПРОЕКТУ
    if project_id and str(project_id) not in str(ai_mgr.storage_dir):
        print(f"   ⚠️ AIInstructionManager привязан к другому проекту, пересоздаем...")
        from ai_settings.ai_module import AIInstructionManager
        st.session_state.ai_instruction_manager = AIInstructionManager(
            project_id=project_id,
            user_id=user_id,
            site_name=site_name,
            domain_name=domain_name,
            context=context if hasattr(context, 'project_id') else None
        )
        ai_mgr = st.session_state.ai_instruction_manager
        print(f"   ✅ Пересоздан: {ai_mgr.storage_dir}")

    # ========== ПРОВЕРЯЕМ API КЛЮЧ ==========
    from api_key_manager import APIKeyManager
    key_manager = APIKeyManager(user_id=user_id, context=context if hasattr(context, 'project_id') else None)
    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()
    dm = st.session_state.domain_manager

    api_key = key_manager.get_api_key(dm.site_name, dm.get_current_domain(), provider)
    if not api_key:
        print(f"❌ Нет API ключа для {provider} в домене {dm.get_current_domain()}")
        return {"success": 0, "errors": 0, "error": f"Нет API ключа для {provider}"}

    # ========== ЗАПУСКАЕМ ГЕНЕРАЦИЮ ==========
    prompt_template = var_data.get("ai_prompt", "")
    num_variants = var_data.get("ai_num_variants", 3)

    print(f"   prompt_template: {prompt_template[:100]}...")
    print(f"   num_variants: {num_variants}")

    context_data = {
        "категория": category,
        "тип": "other",
        "block_id": block_id,
        "var_name": var_name
    }

    success_count = 0
    error_count = 0
    errors_list = []

    try:
        print(f"   Запуск генерации для other-блока...")

        gen_results = st.session_state.ai_generator.generate_instruction(
            prompt_template,
            context_data,
            provider=provider,
            num_variants=num_variants,
            user_id=user_id,
            project_id=project_id
        )

        successful = [r["text"] for r in gen_results if r.get("success")]
        failed = [r for r in gen_results if not r.get("success")]

        print(f"   Успешно: {len(successful)}, Ошибок: {len(failed)}")

        if successful:
            saved = ai_mgr.save_instruction(
                block_id,
                var_name,
                successful,
                context_data,
                {
                    "provider": provider,
                    "block_type": "other",
                    "num_variants": len(successful)
                }
            )

            if saved:
                success_count = len(successful)
                print(f"   ✅ Сохранено {len(successful)} вариантов для other-блока")
            else:
                error_count = len(successful)
                errors_list.append({
                    "block": block.get('name', block_id),
                    "error": "Ошибка сохранения"
                })
                print(f"   ❌ Ошибка сохранения для other-блока")

        if failed:
            error_count += len(failed)
            for f in failed:
                errors_list.append({
                    "block": block.get('name', block_id),
                    "error": f.get('error', 'Ошибка генерации')
                })
            print(f"   ❌ Ошибок генерации: {len(failed)}")

    except Exception as e:
        error_count = num_variants
        errors_list.append({
            "block": block.get('name', block_id),
            "error": str(e)
        })
        print(f"   ❌ Exception: {e}")

    # ========== ПРИНУДИТЕЛЬНО СОХРАНЯЕМ ==========
    ai_mgr.save_instructions()

    # ========== СОХРАНЯЕМ В КОНТЕКСТ (ЕСЛИ ЭТО ОБЪЕКТ) ==========
    # ========== СОХРАНЯЕМ В КОНТЕКСТ (ЕСЛИ ЭТО ОБЪЕКТ) ==========
    if context is not None and hasattr(context, 'set_phase_data'):
        context.set_phase_data(3, {
            'ai_instructions': ai_mgr.instructions,
            'phase3_generated': True
        })
        context.save()
        print(f"   ✅ Phase3 сохранена в контекст")
    else:
        print(f"   ⚠️ Контекст не является объектом ProjectContext, пропускаем сохранение")

    # Перезагружаем инструкции
    ai_mgr.reload()

    print(f"🔍 batch_generate_for_other_with_data END: success={success_count}, errors={error_count}")

    result = {
        "success": success_count,
        "errors": error_count,
        "errors_list": errors_list
    }

    if error_count > 0 and success_count == 0:
        result["error"] = "Полная ошибка генерации"
    elif error_count > 0 and success_count > 0:
        result["error"] = f"Частичная генерация: {success_count} успешно, {error_count} ошибок"

    return result
def show_ai_instructions_full(block_id, var_name, block):
    """Отображает все сгенерированные инструкции для AI-переменной с возможностью редактирования"""
    if 'ai_instruction_manager' not in st.session_state:
        st.error("Менеджер AI не инициализирован")
        return

    # Получаем текущую категорию из данных фазы 2
    phase2_data = get_phase2_data()
    current_category = phase2_data.get('category', '')

    # Нормализуем текущую категорию
    current_category_norm = normalize_string(current_category)

    if not current_category_norm:
        st.warning("⚠️ Категория не загружена. Невозможно отфильтровать инструкции. Загрузите данные в фазе 2.")
        return

    ai_mgr = st.session_state.ai_instruction_manager

    if block_id not in ai_mgr.instructions or var_name not in ai_mgr.instructions[block_id]:
        st.info("Нет сохранённых инструкций для этой переменной.")
        return

    instructions_dict = ai_mgr.instructions[block_id][var_name]

    # Отладка: покажем все сохраненные категории
    with st.expander("🔍 Отладка: все сохраненные категории", expanded=False):
        for ctx_hash, data in instructions_dict.items():
            context = data.get("context", {})
            cat = context.get("категория") or context.get("category", "")
            cat_norm = normalize_string(cat)
            st.write(f"Контекст: {cat} (нормализовано: '{cat_norm}')")
            st.write(f"Текущая категория: '{current_category}' (нормализовано: '{current_category_norm}')")
            st.write(f"Совпадают: {cat_norm == current_category_norm}")
            st.divider()

    # Фильтруем только те контексты, у которых категория совпадает с текущей
    filtered_items = []
    for context_hash, data in instructions_dict.items():
        context = data.get("context", {})
        cat_in_context = context.get("категория") or context.get("category", "")
        cat_in_context_norm = normalize_string(cat_in_context)

        if cat_in_context_norm == current_category_norm:
            filtered_items.append((context_hash, data))

    if not filtered_items:
        st.info(f"Нет инструкций для текущей категории «{current_category}».")

        # Предложим посмотреть все инструкции
        if st.button("Показать все инструкции (без фильтрации)"):
            filtered_items = list(instructions_dict.items())
        else:
            return

    # Отображаем отфильтрованные инструкции с возможностью редактирования
    for context_hash, data in filtered_items:
        context = data.get("context", {})
        values = data.get("values", [])
        original_values = data.get("original_values", [])
        metadata = data.get("metadata", {})

        # Заголовок в зависимости от типа
        context_type = context.get("тип", "unknown")
        characteristic = context.get("характеристика", "")
        value = context.get("значение", "")

        if context_type == "regular":
            title = f"**Regular**: {characteristic}"
        elif context_type == "unique":
            title = f"**Unique**: {characteristic} = {value}"
        elif context_type == "other":
            title = f"**Other**: блок {block.get('name', block_id)}"
        else:
            title = f"**Контекст**: {current_category} / {characteristic}"

        with st.expander(title, expanded=False):
            st.markdown("**Контекст генерации:**")
            st.json(context)

            if metadata:
                st.markdown("**Метаданные:**")
                st.json(metadata)

            # Редактирование инструкций
            st.markdown("**Редактирование инструкций:**")

            # Если есть оригинальные значения (полные ответы) – редактируем их
            if original_values:
                for idx, orig in enumerate(original_values):
                    col_edit1, col_edit2 = st.columns([5, 1])
                    with col_edit1:
                        new_value = st.text_area(
                            f"Вариант {idx+1}:",
                            value=orig,
                            height=150,
                            key=f"edit_full_{block_id}_{var_name}_{context_hash}_{idx}"
                        )
                    with col_edit2:
                        if st.button("💾", key=f"save_full_{block_id}_{var_name}_{context_hash}_{idx}"):
                            # Обновляем полное значение и переразбиваем на пункты
                            if ai_mgr.update_full_instruction(block_id, var_name, context_hash, idx, new_value):
                                st.success("✅ Сохранено!")
                                st.rerun()
            else:
                # Если нет оригинальных, редактируем разбитые пункты
                for idx, val in enumerate(values):
                    col_edit1, col_edit2 = st.columns([5, 1])
                    with col_edit1:
                        new_val = st.text_area(
                            f"Пункт {idx+1}:",
                            value=val,
                            height=100,
                            key=f"edit_split_{block_id}_{var_name}_{context_hash}_{idx}"
                        )
                    with col_edit2:
                        if st.button("💾", key=f"save_split_{block_id}_{var_name}_{context_hash}_{idx}"):
                            if ai_mgr.update_instruction_value(block_id, var_name, context_hash, idx, new_val):
                                st.success("✅ Сохранено!")
                                st.rerun()

            # Кнопка удаления всех инструкций для этого контекста
            if st.button("🗑️ Удалить все инструкции для этого контекста",
                         key=f"delete_ctx_{block_id}_{var_name}_{context_hash}"):
                if ai_mgr.delete_instruction(block_id, var_name, context_hash):
                    st.success("✅ Инструкции удалены!")
                    st.rerun()

def has_phase3_data(app_state=None):
    """Проверяет, есть ли данные в фазе 3 (созданы ли блоки)"""
    # Проверяем через app_data
    if 'app_data' in st.session_state and 'phase3' in st.session_state.app_data:
        phase3_data = st.session_state.app_data['phase3']
        if phase3_data.get('blocks_count', 0) > 0:
            return True
        if phase3_data.get('blocks'):
            return True

    # Проверяем через block_manager
    if 'block_manager' in st.session_state:
        blocks = st.session_state.block_manager.get_all_blocks()
        if len(blocks) > 0:
            return True

    return False
if __name__ == "__main__":
    main()