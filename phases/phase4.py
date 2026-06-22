
import html
import json
import random
import time
import re
from datetime import datetime
from file_data_manager import FileDataManager
import streamlit as st
from domain_manager import DomainManager
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
if 'update_counter' not in st.session_state:
    st.session_state.update_counter = 0
try:
    from phase3 import BlockManager, VariableManager, DynamicVariableManager, local_css
except ImportError:
    from phases.phase3 import BlockManager, VariableManager, DynamicVariableManager, local_css

from ai_settings.ai_module import AIInstructionManager
from styles import load_css

def restore_ai_instructions(context=None):
    """Восстанавливает AI-инструкции из app_data или контекста"""
    if 'ai_instruction_manager' not in st.session_state:
        from ai_settings.ai_module import AIInstructionManager
        st.session_state.ai_instruction_manager = AIInstructionManager(context=context)

    ai_mgr = st.session_state.ai_instruction_manager

    # ========== ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА ==========
    if context is not None:
        phase3_data = context.get_phase_data(3)
        if phase3_data and phase3_data.get('ai_instructions'):
            ai_mgr.instructions = phase3_data['ai_instructions']
            total = sum(len(b) for b in phase3_data['ai_instructions'].values())
            print(f"✅ Восстановлены AI инструкции из контекста: {total} контекстов")
            return True

    # ========== ПРИОРИТЕТ 2: ИЗ SESSION_STATE ==========
    try:
        if 'app_data' in st.session_state:
            phase3_data = st.session_state.app_data.get('phase3', {})
            saved_instructions = phase3_data.get('ai_instructions', {})
            if saved_instructions:
                ai_mgr.instructions = saved_instructions
                total = sum(len(b) for b in saved_instructions.values())
                print(f"✅ Восстановлены AI инструкции из app_data: {total} контекстов")
                return True
    except Exception as e:
        print(f"⚠️ Ошибка загрузки из app_data: {e}")

    print("⚠️ Нет AI инструкций")
    return False
def load_phase3_blocks():
    """Загружает блоки из фазы 3 для использования в фазе 4 (из домена)"""

    # Загружаем блоки из домена
    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    phase3_data = dm.load_phase_data(3)

    if phase3_data and phase3_data.get('blocks'):
        blocks = phase3_data.get('blocks', {})
        print(f"✅ Загружены блоки из домена {dm.get_current_domain()}: {len(blocks)} блоков")
        return blocks

    # Если нет в домене, пробуем из app_data (для обратной совместимости)
    phase3_data = st.session_state.app_data.get('phase3', {})
    blocks = phase3_data.get('blocks', {})

    if blocks:
        print(f"⚠️ Блоки загружены из app_data (fallback)")
        return blocks

    print(f"❌ Нет блоков в домене {dm.get_current_domain()}")
    return {}
class DataLoader:
    """Загрузчик данных из файлов"""

    @staticmethod
    def load_stop_words(stop_words_file="data/stop_words.txt"):
        """Загружает стоп-слова из файла"""
        try:
            with open(stop_words_file, 'r', encoding='utf-8') as f:
                stop_words = [line.strip() for line in f if line.strip()]
                return ", ".join(stop_words)
        except:
            # Возвращаем стандартные стоп-слова
            return "купить, заказать, цена, дешево, скидка, акция"

    @staticmethod
    def load_feature_data(feature_id, feature_data_file="data/features.json"):
        """Загружает дополнительные данные характеристики"""
        try:
            with open(feature_data_file, 'r', encoding='utf-8') as f:
                features_data = json.load(f)
                return features_data.get(feature_id, {})
        except:
            return {}


class WeightedRandomSelector:
    """Взвешенный случайный выбор с ранжированием"""

    @staticmethod
    def weighted_choice(items, weights=None):
        """Выбирает элемент с учетом весов"""
        if not items:
            return None

        # Если веса не указаны, используем равномерное распределение
        if weights is None or len(weights) != len(items):
            return random.choice(items)

        # Проверяем, что все веса неотрицательные
        valid_weights = [max(w, 0) for w in weights]
        total = sum(valid_weights)

        # Если все веса равны 0, используем равномерное распределение
        if total == 0:
            return random.choice(items)

        # Взвешенный случайный выбор
        r = random.uniform(0, total)
        cumulative = 0

        for i, weight in enumerate(valid_weights):
            cumulative += weight
            if r <= cumulative:
                return items[i]

        # На всякий случай возвращаем последний элемент
        return items[-1]


# --- Дополнительные классы для генерации ---
class MarkerRotator:
    """Ротация маркеров для равномерного использования"""

    def __init__(self, markers):
        self.markers = markers
        self.usage_counter = {marker: 0 for marker in markers}
        self.reset_cycle()

    def reset_cycle(self):
        """Сбрасывает цикл ротации"""
        self.available_markers = self.markers.copy()
        random.shuffle(self.available_markers)
        self.current_index = 0

    def get_next_marker(self, with_quotes=False):
        """Возвращает следующий маркер с ротацией"""
        if not self.markers:
            return ""

        # Если доступные маркеры закончились, сбрасываем цикл
        if not self.available_markers:
            self.reset_cycle()

        # Берем следующий маркер
        marker = self.available_markers[self.current_index]
        self.usage_counter[marker] += 1



        # Увеличиваем индекс
        self.current_index += 1
        if self.current_index >= len(self.available_markers):
            self.reset_cycle()

        return marker

    def get_marker_stats(self):
        """Возвращает статистику использования маркеров"""
        return self.usage_counter


# --- НОВЫЙ КЛАСС: Трекинг использования значений ---
class UsageTracker:
    """Отслеживает использование значений с учетом контекста"""

    def __init__(self, history_window=100):
        self.history = {}  # key -> list of recent choices
        self.total_counts = {}  # key -> total usage count
        self.history_window = history_window

    def get_key(self, block_id, var_name, context_hash=None):
        """Создает ключ для трекинга"""
        if context_hash:
            return f"{block_id}:{var_name}:{context_hash}"
        return f"{block_id}:{var_name}"

    def track_usage(self, key, value):
        """Добавляет использование значения"""
        if key not in self.history:
            self.history[key] = []
            self.total_counts[key] = {}

        # Обновляем историю
        self.history[key].append(value)

        # Ограничиваем размер истории
        if len(self.history[key]) > self.history_window:
            self.history[key].pop(0)

        # Обновляем общий счетчик
        self.total_counts[key][value] = self.total_counts[key].get(value, 0) + 1

    def get_recent_usage(self, key, value):
        """Возвращает количество недавних использований значения"""
        if key not in self.history:
            return 0
        return self.history[key].count(value)

    def get_total_usage(self, key, value):
        """Возвращает общее количество использований"""
        return self.total_counts.get(key, {}).get(value, 0)

    def get_usage_penalty(self, key, value):
        """Рассчитывает штраф за использование (от 0 до 1)"""
        recent_count = self.get_recent_usage(key, value)
        total_count = self.get_total_usage(key, value)

        # Штрафуем за недавнее использование сильнее
        recent_penalty = 1.0 / (recent_count * 2 + 1)

        # И за общее использование (но слабее)
        total_penalty = 1.0 / (total_count * 0.5 + 1)

        return recent_penalty * total_penalty

    def reset_for_key(self, key):
        """Сбрасывает статистику для ключа"""
        if key in self.history:
            self.history[key] = []
        if key in self.total_counts:
            self.total_counts[key] = {}

    def reset_all(self):
        """Сбрасывает всю статистику"""
        self.history = {}
        self.total_counts = {}
class PromptGenerator:
    """Генератор промптов с поддержкой динамических переменных"""
    @staticmethod
    def normalize_string(s):
        """Удаляет лишние пробелы и приводит к нижнему регистру"""
        if not isinstance(s, str):
            return ""
        return re.sub(r'\s+', ' ', s.strip()).lower()
    def __init__(self, block_manager, variable_manager, dynamic_var_manager):
        self.block_manager = block_manager
        self.variable_manager = variable_manager
        self.dynamic_var_manager = dynamic_var_manager
        self.data_loader = DataLoader()
        self.random_selector = WeightedRandomSelector()

        # НОВОЕ: Трекер использования
        self.usage_tracker = UsageTracker(history_window=50)  # Учитываем последние 50 использований

        # Для обратной совместимости - режимы рандомизации
        self.randomization_mode = "adaptive"  # "adaptive", "uniform", "weighted_only"

        # НОВЫЙ МЕТОД: Адаптивный выбор с учетом использования

    def get_adaptive_static_value(self, block_id, var_name, context=None):
        """Возвращает значение статической переменной с учетом истории использования"""
        var_data = self.variable_manager.get_variable_data(block_id, var_name)

        if not var_data or "values" not in var_data or not var_data["values"]:
            return ""

        values_list = var_data["values"]

        # Подготавливаем список значений и базовых весов
        items = []
        base_weights = []

        for item in values_list:
            if isinstance(item, str):
                items.append(item)
                base_weights.append(1.0)
            elif isinstance(item, dict) and "value" in item:
                items.append(item["value"])
                weight = item.get("weight", 1.0)
                if isinstance(weight, str):
                    try:
                        weight = float(weight)
                    except:
                        weight = 1.0
                base_weights.append(max(0.1, weight))  # Минимальный вес 0.1

        if not items:
            return ""

        # Создаем ключ для трекинга
        context_hash = ""
        if context:
            context_keys = ["категория", "характеристика", "значение", "тип"]
            # Нормализуем строковые значения перед построением строки
            normalized_values = []
            for k in context_keys:
                val = context.get(k, "")
                if isinstance(val, str):
                    val = self.normalize_string(val)
                normalized_values.append(str(val))
            context_str = "|".join(normalized_values)
            import hashlib
            context_hash = hashlib.md5(context_str.encode()).hexdigest()[:8]

        tracker_key = self.usage_tracker.get_key(block_id, var_name, context_hash)

        # Рассчитываем скорректированные веса
        adjusted_weights = []
        for i, value in enumerate(items):
            base_weight = base_weights[i]

            if self.randomization_mode == "uniform":
                # Равномерное распределение (старый режим)
                adjusted = 1.0
            elif self.randomization_mode == "weighted_only":
                # Только по базовым весам (старый режим)
                adjusted = base_weight
            else:
                # Адаптивный режим: учитываем использование
                penalty = self.usage_tracker.get_usage_penalty(tracker_key, value)
                adjusted = base_weight * penalty

            adjusted_weights.append(adjusted)

        # Взвешенный выбор
        chosen = self.random_selector.weighted_choice(items, adjusted_weights)

        # Отслеживаем использование
        self.usage_tracker.track_usage(tracker_key, chosen)

        return self.escape_html(chosen)

    def generate_prompts_for_block(self, block, num_prompts, category="", markers=None, marker_rotator=None):
        """Генерирует промпты для блока (не характеристика)"""

        if not block:
            return []

        prompts = []

        for prompt_num in range(num_prompts):
            # Подготавливаем контекст для "other" блоков
            context = {
                "категория": self.escape_html(category),
                "стоп_слова": self.data_loader.load_stop_words(),
                "prompt_num": prompt_num + 1,
                "total_prompts": num_prompts,
                "тип": "other",
                "block_id": block.get("block_id", ""),
                "block_type": block.get("block_type", "other")
            }

            # Добавляем маркер в контекст, если есть
            if markers and marker_rotator:
                marker = marker_rotator.get_next_marker(with_quotes=True)
                context["маркер"] = marker
                context["маркер_заголовка"] = marker
                context["маркер_описания"] = marker
                context["маркер_применения"] = marker
                context["маркер_блока"] = marker
                context["характеристика_маркер"] = marker

            # Генерируем промпт с правильным типом блока
            prompt, unresolved = self.generate_single_prompt(block, context, char_type=None)

            if prompt:
                prompts.append({
                    "block_id": block.get("block_id", ""),
                    "block_name": block.get("name", ""),
                    "block_type": block.get("block_type", "other"),
                    "prompt_num": prompt_num + 1,
                    "prompt": prompt,
                    "unresolved_variables": unresolved,  # добавлено
                    "context": context
                })

        return prompts

    def generate_single_other_block_prompt(self, block, context):
        """Генерирует промпт для блока (не характеристика)"""

        template = block.get("template", "")

        # 1. Обрабатываем динамические переменные
        if self.dynamic_var_manager:
            processor = self.dynamic_var_manager.get_processor()
            template = processor.render_template_with_context(template, context, include_dynamic=True)

        # 2. Обрабатываем статические переменные с взвешенным выбором
        for var_name in block.get("variables", []):
            placeholder = f"{{{var_name}}}"
            if placeholder in template:
                var_value = self.get_weighted_static_value(block["block_id"], var_name)
                # Если переменная содержит плейсхолдер маркера, заменяем его
                if "{маркер}" in var_value and "маркер" in context:
                    var_value = var_value.replace("{маркер}", context["маркер"])
                if "{маркер_заголовка}" in var_value and "маркер_заголовка" in context:
                    var_value = var_value.replace("{маркер_заголовка}", context["маркер_заголовка"])
                if "{маркер_описания}" in var_value and "маркер_описания" in context:
                    var_value = var_value.replace("{маркер_описания}", context["маркер_описания"])
                if "{характеристика_маркер}" in var_value and "характеристика_маркер" in context:
                    var_value = var_value.replace("{характеристика_маркер}", context["характеристика_маркер"])

                template = template.replace(placeholder, var_value)

        # 3. Заменяем оставшиеся плейсхолдеры маркера
        if "маркер" in context:
            possible_placeholders = [
                "{маркер_заголовка}",
                "{маркер_описания}",
                "{маркер_применения}",
                "{маркер_блока}",
                "{характеристика_маркер}",
                "{маркер}",
                "[МАРКЕР]",
                "{МАРКЕР}"
            ]
            for placeholder in possible_placeholders:
                if placeholder in template:
                    template = template.replace(placeholder, context["маркер"])

        # 4. Очищаем результат
        template = re.sub(r'\n{3,}', '\n\n', template.strip())

        return template

    def escape_html(self, text):
        """Экранирует HTML-сущности в тексте"""
        if not isinstance(text, str):
            text = str(text)
        return html.escape(text)



    def get_weighted_static_value(self, block_id, var_name):
        """Возвращает значение статической переменной с учетом весов и истории использования"""
        # Используем новый адаптивный метод без контекста для обратной совместимости
        return self.get_adaptive_static_value(block_id, var_name)

    # Обновим метод для AI-переменных:
    def get_weighted_ai_value(self, block_id, var_name, context):
        """Получает значение AI-переменной с учетом контекста, весов и использования"""
        print(f"\n🔍 get_weighted_ai_value called:")
        print(f"   block_id: {block_id}")
        print(f"   var_name: {var_name}")

        # Проверяем наличие AI инструкций
        if ('ai_instruction_manager' not in st.session_state or
                not st.session_state.ai_instruction_manager.instructions):
            print(f"   ⚠️ Нет AI инструкций, пробуем восстановить...")
            restore_ai_instructions(context)

        # Инициализируем менеджер инструкций если нужно
        if 'ai_instruction_manager' not in st.session_state:
            from ai_settings.ai_module import AIInstructionManager
            st.session_state.ai_instruction_manager = AIInstructionManager()

        # ✅ ПРОВЕРЯЕМ, ЕСТЬ ЛИ ИНСТРУКЦИИ ДЛЯ ЭТОЙ ПЕРЕМЕННОЙ
        has_instructions = False
        if block_id in st.session_state.ai_instruction_manager.instructions:
            if var_name in st.session_state.ai_instruction_manager.instructions[block_id]:
                has_instructions = True
                print(f"   ✅ Найдены инструкции для {block_id}/{var_name}")

        # ✅ ЕСЛИ НЕТ ИНСТРУКЦИЙ - ПРОСТО ПРОПУСКАЕМ (возвращаем пустую строку)
        if not has_instructions:
            print(f"   ⚠️ Нет AI инструкций для {var_name}, пропускаем")
            return ""  # ← ПРОСТО ВОЗВРАЩАЕМ ПУСТУЮ СТРОКУ

        # Получаем сохраненные инструкции для этого контекста
        normalized_context = {k: self.normalize_string(v) for k, v in context.items() if isinstance(v, str)}
        print(f"   normalized_context: {normalized_context}")

        instructions = st.session_state.ai_instruction_manager.get_instruction(
            block_id, var_name, normalized_context
        )
        print(f"   instructions found: {len(instructions) if instructions else 0}")

        if instructions:
            all_items = []
            for instruction in instructions:
                if isinstance(instruction, str):
                    items = [item.strip() for item in instruction.split(';') if item.strip()]
                    all_items.extend(items)
                elif isinstance(instruction, list):
                    all_items.extend(instruction)

            if all_items:
                # Создаем ключ для трекинга
                context_keys = ["категория", "характеристика", "значение", "тип"]
                context_str = "|".join(str(context.get(k, "")) for k in context_keys)
                import hashlib
                context_hash = hashlib.md5(context_str.encode()).hexdigest()[:8]

                tracker_key = self.usage_tracker.get_key(block_id, var_name, context_hash)

                # Рассчитываем веса с учетом использования
                weights = []
                for item in all_items:
                    base_weight = 1.0
                    if self.randomization_mode == "adaptive":
                        penalty = self.usage_tracker.get_usage_penalty(tracker_key, item)
                        adjusted = base_weight * penalty
                    else:
                        adjusted = base_weight
                    weights.append(adjusted)

                # Выбираем ОДИН пункт с учетом весов
                chosen_item = self.random_selector.weighted_choice(all_items, weights)

                # Отслеживаем использование
                self.usage_tracker.track_usage(tracker_key, chosen_item)
                print(f"   ✅ Using AI instruction: {chosen_item[:100]}...")
                return self.escape_html(chosen_item)

        print(f"   ⚠️ Нет инструкций для этого контекста, пропускаем")
        return ""  # ← ПРОСТО ВОЗВРАЩАЕМ ПУСТУЮ СТРОКУ

    # НОВЫЙ МЕТОД: Сброс трекера использования
    def reset_usage_tracking(self):
        """Сбрасывает статистику использования"""
        self.usage_tracker.reset_all()

    # НОВЫЙ МЕТОД: Установка режима рандомизации
    def set_randomization_mode(self, mode):
        """Устанавливает режим рандомизации"""
        valid_modes = ["adaptive", "uniform", "weighted_only"]
        if mode in valid_modes:
            self.randomization_mode = mode
        else:
            self.randomization_mode = "adaptive"

    def prepare_context(self, characteristic=None, category="", char_type="regular",
                        feature_data=None, additional_context=None):
        """Подготавливает контекст для подстановки"""
        context = {
            "категория": self.normalize_string(category),  # ← нормализуем
            "стоп_слова": self.data_loader.load_stop_words(),
            "маркер": "[МАРКЕР]",
            "название_характеристики": "",
            "значение": "",
            "тип": char_type
        }

        if characteristic:
            context.update({
                "название_характеристики": self.normalize_string(characteristic.get("char_name", "")),  # ← нормализуем
                "значение": self.escape_html(characteristic.get("value", "")),
                "характеристика": self.normalize_string(characteristic.get("char_name", ""))  # ← нормализуем
            })

        # Добавляем feature_data
        if feature_data:
            for key, value in feature_data.items():
                safe_key = key.replace("-", "_").replace(" ", "_")
                context[safe_key] = self.escape_html(value)

        # Добавляем дополнительный контекст
        if additional_context:
            for key, value in additional_context.items():
                context[key] = self.escape_html(value)

        return context

    def generate_prompts_for_characteristic(self, characteristic, block_id, num_prompts_per_value,
                                            char_type="regular", category="", markers=None,
                                            marker_rotator=None, feature_id=None):
        """Генерирует промпты для характеристики"""

        block = self.block_manager.get_block(block_id)
        if not block:
            return []

        prompts = []

        # Загружаем дополнительные данные характеристики
        feature_data = {}
        if feature_id:
            feature_data = self.data_loader.load_feature_data(feature_id)

        # Получаем значения характеристики
        values_list = characteristic.get("values", [])
        if not values_list:
            return []

        # Обрабатываем каждое значение
        for value_item in values_list:
            value = value_item.get("value", "")

            for prompt_num in range(num_prompts_per_value):
                # Создаем характеристику с конкретным значением
                char_with_value = characteristic.copy()
                char_with_value["value"] = value

                # Подготавливаем контекст
                context = self.prepare_context(
                    characteristic=char_with_value,
                    category=category,
                    char_type=char_type,
                    feature_data=feature_data,
                    additional_context={
                        "prompt_num": prompt_num + 1,
                        "total_prompts": num_prompts_per_value
                    }
                )

                # Добавляем маркер в контекст
                if markers and marker_rotator:
                    marker = marker_rotator.get_next_marker(with_quotes=True)
                    context["маркер"] = marker
                    context["характеристика_маркер"] = marker

                # Генерируем промпт
                prompt, unresolved = self.generate_single_prompt(block, context, char_type)

                if prompt:
                    prompts.append({
                        "characteristic_id": characteristic.get("char_id", ""),
                        "characteristic_name": characteristic.get("char_name", ""),
                        "value": value,
                        "prompt_num": prompt_num + 1,
                        "type": char_type,
                        "prompt": prompt,
                        "unresolved_variables": unresolved,  # добавлено
                        "context": context,
                        "feature_id": feature_id
                    })

        return prompts

    # В phase4.py в классе PromptGenerator:


    def get_ai_variable_value(self, block_id, var_name, context):
        """Получает значение AI-переменной с учетом контекста"""

        if 'ai_instruction_manager' not in st.session_state:
            st.session_state.ai_instruction_manager = AIInstructionManager()

        # Создаем упрощенный контекст для поиска
        search_context = {
            "категория": context.get("категория", ""),
            "характеристика": context.get("характеристика", context.get("название_характеристики", "")),
            "тип": context.get("тип", "regular"),
            "значение": context.get("значение", "")
        }

        # Ищем инструкции с проверкой контекста (используем новый метод)
        normalized_search = {k: self.normalize_string(v) for k, v in search_context.items() if isinstance(v, str)}
        instructions = st.session_state.ai_instruction_manager.get_instruction(
            block_id, var_name, normalized_search
        )

        if instructions:
            # Выбираем случайный пункт из найденных инструкций
            if instructions:
                return self.escape_html(random.choice(instructions))

        # Если не нашли по точному контексту, ищем любые инструкции для этой характеристики
        # Более гибкий поиск - только по характеристике и категории
        if search_context["характеристика"]:
            all_contexts = st.session_state.ai_instruction_manager.get_all_contexts_for_variable(
                block_id, var_name
            )

            for ctx_info in all_contexts:
                stored_ctx = ctx_info.get("context", {})
                # Нормализуем сохранённый контекст
                stored_norm = {k: self.normalize_string(v) for k, v in stored_ctx.items() if isinstance(v, str)}
                # Нормализуем искомый контекст
                search_norm = {k: self.normalize_string(v) for k, v in search_context.items() if isinstance(v, str)}

                if (stored_norm.get("категория") == search_norm["категория"] and
                        stored_norm.get("характеристика") == search_norm["характеристика"]):
                    # Нашли подходящий контекст
                    context_hash = ctx_info["hash"]
                    instructions = st.session_state.ai_instruction_manager.get_instruction(
                        block_id, var_name, stored_ctx  # можно передать оригинальный stored_ctx или нормализованный
                    )
                    if instructions:
                        return self.escape_html(random.choice(instructions))

        # Логируем, если не нашли
        if st.session_state.get('debug_mode', False):
            st.warning(f"Не найдены AI-инструкции для: {var_name} в контексте {search_context}")

        # Пробуем получить любые инструкции для этой переменной (fallback)
        all_instructions = st.session_state.ai_instruction_manager.get_instruction(block_id, var_name)
        if all_instructions and isinstance(all_instructions, list) and len(all_instructions) > 0:
            return self.escape_html(random.choice(all_instructions))

        # Последний fallback - стандартные значения
        var_data = self.variable_manager.get_variable_data(block_id, var_name)
        if var_data and "values" in var_data and var_data["values"]:
            # Пытаемся разбить стандартные значения
            all_values = []
            for value in var_data["values"]:
                if isinstance(value, str):
                    items = [item.strip() for item in value.split(';') if item.strip()]
                    all_values.extend(items)

            if all_values:
                return self.escape_html(random.choice(all_values))

        return ""

    def generate_single_prompt(self, block, context, char_type=None):
        """Генерирует один промпт с поддержкой AI-переменных.
           Возвращает кортеж (prompt, unresolved_vars)"""

        # ✅ СНАЧАЛА определяем template
        template = block.get("template", "")

        # Отладка
        print(f"\n{'='*50}")
        print(f"🔍 generate_single_prompt for block: {block.get('block_id')}")
        print(f"   Block type: {block.get('block_type')}")
        print(f"   Variables in block: {block.get('variables', [])}")
        print(f"   Template preview: {template[:200] if template else 'EMPTY'}...")

        block_type = block.get("block_type", "characteristic" if char_type else "other")
        settings = block.get("settings", {})

        # 1. Обрабатываем AI-переменные (ПЕРВЫЕ, так как они могут содержать другие переменные)
        for var_name in block.get("variables", []):
            placeholder = f"{{{var_name}}}"
            if placeholder in template:
                var_data = self.variable_manager.get_variable_data(block["block_id"], var_name)
                print(f"   Variable {var_name}: type={var_data.get('type') if var_data else 'None'}")
                if var_data and var_data.get("type") == "ai":
                    print(f"🤖 Processing AI variable: {var_name} in block {block['block_id']}")
                    # Это AI-переменная
                    if block_type == "other":
                        block_context = {
                            "категория": context.get("категория", ""),
                            "тип": "other",
                            "block_id": block["block_id"],
                            "var_name": var_name
                        }
                    else:
                        block_context = context
                    print(f"   AI context: {block_context}")
                    ai_value = self.get_weighted_ai_value(block["block_id"], var_name, block_context)
                    print(f"   AI value: {ai_value[:100] if ai_value else 'EMPTY'}...")
                    template = template.replace(placeholder, ai_value)

            # ... остальной код без изменений ...

        # 2. Обрабатываем динамические переменные
        if self.dynamic_var_manager:
            processor = self.dynamic_var_manager.get_processor()
            template = processor.render_template_with_context(template, context, include_dynamic=True)

        # 3. Форматированное значение (только для characteristic блоков)
        if char_type == "unique":
            format_template = settings.get("формат_значения_unique", "\"[значение]\"")
            value_formatted = format_template.replace("[значение]", context.get("значение", ""))
            value_formatted = value_formatted.replace("значение", context.get("значение", ""))
            template = template.replace("{значение_форматированное}", value_formatted)
        elif char_type == "regular":
            format_template = settings.get("формат_значения_regular", "[[значение]]")
            value_formatted = format_template.replace("[значение]", context.get("значение", ""))
            value_formatted = value_formatted.replace("значение", context.get("значение", ""))
            template = template.replace("{значение_форматированное}", value_formatted)

        # 4. Обрабатываем скобки_характеристика для regular характеристик
        if char_type == "regular" and settings.get("добавлять_скобки_переменную", True):
            brackets_value = self.get_weighted_static_value(block["block_id"], "скобки_характеристика")
            template = template.replace("{скобки_характеристика}", brackets_value)
        else:
            template = template.replace("{скобки_характеристика}", "")

        # 5. Обрабатываем остальные статические переменные с адаптивным выбором
        for var_name in block.get("variables", []):
            # Пропускаем уже обработанные
            if var_name in ["скобки_характеристика", "значение_форматированное"]:
                continue

            placeholder = f"{{{var_name}}}"
            if placeholder in template:
                var_data = self.variable_manager.get_variable_data(block["block_id"], var_name)

                if var_data and var_data.get("type") == "ai":
                    # Уже обработали выше
                    continue
                else:
                    # Для всех типов переменных используем адаптивный выбор с контекстом
                    var_context = {
                        "категория": context.get("категория", ""),
                        "характеристика": context.get("характеристика", ""),
                        "значение": context.get("значение", ""),
                        "тип": context.get("тип", ""),
                        "block_id": block["block_id"],
                        "var_name": var_name
                    }
                    var_value = self.get_adaptive_static_value(block["block_id"], var_name, var_context)

                # Если переменная содержит плейсхолдеры, заменяем их
                if var_value and isinstance(var_value, str):
                    # Подставляем маркер если есть в контексте
                    if "{характеристика_маркер}" in var_value and "характеристика_маркер" in context:
                        var_value = var_value.replace("{характеристика_маркер}", context["характеристика_маркер"])
                    if "{маркер}" in var_value and "маркер" in context:
                        var_value = var_value.replace("{маркер}", context["маркер"])

                    # Подставляем другие переменные из контекста
                    for key, val in context.items():
                        placeholder_key = f"{{{key}}}"
                        if placeholder_key in var_value:
                            var_value = var_value.replace(placeholder_key, str(val))

                template = template.replace(placeholder, var_value)

        # 6. Заменяем оставшиеся плейсхолдеры маркера
        if "характеристика_маркер" in context:
            template = template.replace("{характеристика_маркер}", context["характеристика_маркер"])
        if "маркер" in context:
            template = template.replace("{маркер}", context["маркер"])

        # 7. Очищаем результат
        template = re.sub(r'\n{3,}', '\n\n', template.strip())

        # 8. Поиск необработанных плейсхолдеров (добавлено)
        unresolved = re.findall(r'\{([^}]+)\}', template)

        return template, unresolved

# --- Основное приложение фазы 4 ---





# Добавить в phase4.py

def get_char_prompts_settings():
    """Возвращает настройки количества промптов для характеристик"""
    if 'phase4_char_settings' not in st.session_state:
        st.session_state.phase4_char_settings = {}

    return st.session_state.phase4_char_settings
def save_phase4_settings(app_state=None, context=None):
    """Сохраняет настройки фазы 4 с приоритетом контекста"""

    # Получаем значения из session_state
    global_prompts = st.session_state.get('phase4_global_prompts', 3)
    global_other = st.session_state.get('phase4_global_other_prompts', 20)
    char_settings = st.session_state.get('phase4_char_settings', {})
    other_settings = st.session_state.get('phase4_other_blocks_settings', {})
    selected_regular = st.session_state.get('selected_regular_block_id')
    selected_unique = st.session_state.get('selected_unique_block_id')

    # Формируем настройки
    settings = {
        'char_settings': char_settings,
        'other_blocks_settings': other_settings,
        'selected_regular_block_id': selected_regular,
        'selected_unique_block_id': selected_unique,
        'global_prompts': int(global_prompts) if global_prompts else 0,
        'global_other_prompts': int(global_other) if global_other else 0
    }

    # Сохраняем в session_state
    st.session_state.phase4_settings = settings

    # ✅ ПРИОРИТЕТ 1: СОХРАНЯЕМ В КОНТЕКСТ
    if context is not None:
        # Получаем текущие данные фазы 4
        phase4_data = context.get_phase_data(4) or {}
        phase4_data['settings'] = settings

        # Сохраняем промпты если есть
        if 'phase4_generated_prompts' in st.session_state:
            phase4_data['prompts'] = st.session_state.phase4_generated_prompts
            phase4_data['generated_count'] = len(st.session_state.phase4_generated_prompts)
        phase4_data = context.get_phase_data(4) or {}
        phase4_data['settings'] = settings
        context.set_phase_data(4, phase4_data)
        context.save()
        print(f"💾 Settings saved to CONTEXT: global_prompts={settings['global_prompts']}")
        return True

    # ✅ ПРИОРИТЕТ 2: СОХРАНЯЕМ В APP_STATE
    if 'app_data' not in st.session_state:
        st.session_state.app_data = {}

    st.session_state.app_data['phase4_settings'] = settings
    st.session_state.app_data['phase4_configured'] = True

    if 'phase4_generated_prompts' in st.session_state:
        st.session_state.app_data['phase4'] = {
            'prompts': st.session_state.phase4_generated_prompts,
            'generated_count': len(st.session_state.phase4_generated_prompts),
            'settings': settings
        }

    if app_state:
        app_state.set_phase_data(4, {
            'settings': settings,
            'prompts': st.session_state.get('phase4_generated_prompts', [])
        })
        app_state.save_project()
        print(f"💾 Settings saved to APP_STATE: global_prompts={settings['global_prompts']}")
        return True

    # ✅ ПРИОРИТЕТ 3: СОХРАНЯЕМ В ФАЙЛ
    try:
        from pathlib import Path
        import json
        from datetime import datetime

        user_id = st.session_state.get('user_id')
        site = st.session_state.get('current_site', 'steelborg')
        domain = st.session_state.get('current_domain', 'default')
        project_id = st.session_state.get('current_project_id')

        if user_id and project_id:
            project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

            if project_file.exists():
                with open(project_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
            else:
                file_data = {
                    "project_id": project_id,
                    "user_id": user_id,
                    "site_name": site,
                    "domain_name": domain,
                    "created_at": datetime.now().isoformat()
                }

            if 'app_data' not in file_data:
                file_data['app_data'] = {}

            file_data['app_data']['phase4_settings'] = settings
            file_data['app_data']['phase4_configured'] = True

            if 'phase4_generated_prompts' in st.session_state:
                file_data['app_data']['phase4'] = {
                    'prompts': st.session_state.phase4_generated_prompts,
                    'generated_count': len(st.session_state.phase4_generated_prompts)
                }

            file_data['updated_at'] = datetime.now().isoformat()

            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, ensure_ascii=False, indent=2)

            print(f"💾 Settings saved to FILE: {project_file}")
            return True
    except Exception as e:
        print(f"⚠️ Ошибка сохранения в файл: {e}")

    print(f"💾 Settings saved to session_state only")
    return True

def show_generation_mode(phase1_data, category, markers, settings_mode=False, app_state=None, context=None):
    """Основной режим - генерация промптов"""

    # ✅ ПРИНУДИТЕЛЬНО ЗАГРУЖАЕМ НАСТРОЙКИ ИЗ ФАЙЛА
    load_phase4_settings(app_state, context)

    # ✅ ПРИНУДИТЕЛЬНО ЗАГРУЖАЕМ ДАННЫЕ ФАЗЫ 1 ИЗ ФАЙЛА
    from pathlib import Path
    import json

    ctx_data = _get_context_data(context, st.session_state)

    # Получаем параметры
    user_id = ctx_data.get('user_id')
    site = ctx_data.get('site_name', 'steelborg')
    domain = ctx_data.get('domain_name', 'default')
    project_id = ctx_data.get('project_id')

    if user_id and project_id:
        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

        if project_file.exists():
            try:
                with open(project_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)

                # Загружаем характеристики из файла
                phase1_in_file = file_data.get('app_data', {}).get('phase1', {})
                if phase1_in_file and phase1_in_file.get('characteristics'):
                    phase1_data.clear()
                    phase1_data.update(phase1_in_file)
                    category = phase1_data.get('category', category)
                    print(f"✅ Загружены данные из файла: {len(phase1_data.get('characteristics', []))} характеристик")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки данных из файла: {e}")

    # ✅ ИСПОЛЬЗУЕМ ЗАГРУЖЕННЫЕ ЗНАЧЕНИЯ
    GLOBAL_PROMPTS_PER_VALUE = st.session_state.get('phase4_global_prompts', 3)
    GLOBAL_OTHER_PROMPTS = st.session_state.get('phase4_global_other_prompts', 20)
    CHAR_SETTINGS = st.session_state.get('phase4_char_settings', {})
    OTHER_BLOCKS_SETTINGS = st.session_state.get('phase4_other_blocks_settings', {})
    SELECTED_REGULAR_BLOCK_ID = st.session_state.get('selected_regular_block_id')
    SELECTED_UNIQUE_BLOCK_ID = st.session_state.get('selected_unique_block_id')

    print(f"📊 НАСТРОЙКИ В show_generation_mode:")
    print(f"   global_prompts: {GLOBAL_PROMPTS_PER_VALUE}")
    print(f"   global_other: {GLOBAL_OTHER_PROMPTS}")
    print(f"   char_settings: {len(CHAR_SETTINGS)}")
    print(f"   has_context: {context is not None}")
    print(f"   site: {site}, domain: {domain}, project: {project_id}")



    # Инициализация marker_rotator
    marker_rotator = st.session_state.get('marker_rotator')
    if markers and marker_rotator is None:
        marker_rotator = MarkerRotator(markers)
        st.session_state.marker_rotator = marker_rotator
    # Получаем контекст для пути к файлу
    ctx_data = _get_context_data(context, st.session_state)

    if ctx_data['has_context'] and context is not None:
        user_id = context.user_id
        site = context.site_name
        domain = context.domain_name
        project_id = context.project_id
    else:
        user_id = st.session_state.get('user_id')
        site = st.session_state.get('current_site', 'steelborg')
        domain = st.session_state.get('current_domain', 'default')
        project_id = st.session_state.get('current_project_id')

    if user_id and project_id:
        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

        if project_file.exists():
            with open(project_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)

            phase1_in_file = file_data.get('app_data', {}).get('phase1', {})
            chars = phase1_in_file.get('characteristics', [])

            if chars and 'char_id' in chars[0]:
                # Правильные данные уже в файле
                phase1_data.clear()
                phase1_data.update(phase1_in_file)
                category = phase1_data.get('category', category)
                st.success(f"✅ Загружены данные из файла! is_unique={chars[0].get('is_unique', 'НЕТ')}")
            elif 'phase1_generated' in st.session_state:
                # Берем из session_state
                correct_data = st.session_state.phase1_generated
                if correct_data and correct_data.get('characteristics'):
                    phase1_data.clear()
                    phase1_data.update(correct_data)
                    category = phase1_data.get('category', category)
                    st.success(f"✅ Загружены данные из session_state! is_unique={correct_data['characteristics'][0].get('is_unique', 'НЕТ')}")

    if 'update_counter' not in st.session_state:
        st.session_state.update_counter = 0
    if 'selected_regular_block_id' not in st.session_state:
        st.session_state.selected_regular_block_id = None

    characteristics_raw = phase1_data.get('characteristics', [])

    # ✅ НОРМАЛИЗАЦИЯ ДАННЫХ
    characteristics = []
    for i, char in enumerate(characteristics_raw):
        if not isinstance(char, dict):
            continue

        if char.get('in_black_list', False):
            continue

        if char.get('is_extra', False):
            continue

        char_id = str(char.get('char_id') or char.get('id') or f'char_{i}')
        char_name = char.get('char_name') or char.get('name') or f'Характеристика_{i+1}'
        is_unique = char.get('is_unique', False)
        unit = char.get('unit', '')

        raw_values = char.get('values_data') or char.get('values', [])
        normalized_values = []

        for val in raw_values:
            if isinstance(val, dict):
                normalized_values.append({
                    'value': val.get('value', ''),
                    'count': val.get('items_count', val.get('count', 0)),
                    'offers': val.get('offers_sum', val.get('offers', 0))
                })
            elif isinstance(val, str):
                normalized_values.append({'value': val, 'count': 0, 'offers': 0})
            else:
                normalized_values.append({'value': str(val), 'count': 0, 'offers': 0})

        characteristics.append({
            'char_id': char_id,
            'char_name': char_name,
            'original_name': char.get('original_name', char_name),
            'is_unique': is_unique,
            'unit': unit,
            'values': normalized_values
        })

    phase1_data['characteristics'] = characteristics

    if not characteristics:
        st.warning("❌ Нет доступных характеристик.")
        return

    if not settings_mode:
        st.header("🎯 Генерация промптов")

    # Информация
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.info(f"**Категория:** {category}")
    with col_info2:
        regular_count = sum(1 for c in characteristics if not c.get('is_unique', False))
        unique_count = sum(1 for c in characteristics if c.get('is_unique', False))
        st.info(f"**Характеристик:** {len(characteristics)} (Regular: {regular_count}, Unique: {unique_count})")



    # Получаем блоки по типам
    blocks = st.session_state.block_manager.get_all_blocks()
    characteristic_blocks = st.session_state.block_manager.get_blocks_by_type("characteristic")
    other_blocks = st.session_state.block_manager.get_blocks_by_type("other")

    # Создаем отдельные блоки для unique и regular характеристик
    unique_blocks = {}
    regular_blocks = {}

    for block_id, block in characteristic_blocks.items():
        settings = block.get('settings', {})
        char_type = settings.get('characteristic_type', 'regular')
        if char_type == 'unique':
            unique_blocks[block_id] = block
        else:
            regular_blocks[block_id] = block

    # Для обратной совместимости
    if not unique_blocks:
        for block_id, block in characteristic_blocks.items():
            block_name = block.get('name', '').lower()
            if 'unique' in block_name:
                unique_blocks[block_id] = block

    for block_id, block in characteristic_blocks.items():
        if block_id not in unique_blocks and block_id not in regular_blocks:
            regular_blocks[block_id] = block

    # ==================== НАСТРОЙКА ХАРАКТЕРИСТИК ====================
    with st.expander("📊 Настройка промптов для характеристик", expanded=True):
        st.write("**Настройте количество промптов для каждой характеристики:**")
        st.caption("Количество промптов, которые будут сгенерированы для КАЖДОГО значения характеристики")

        if 'phase4_char_settings' not in st.session_state:
            st.session_state.phase4_char_settings = {}

        # Глобальная настройка
        # Глобальная настройка для характеристик
        col_global1, col_global2, col_global3 = st.columns([2, 1, 1])
        with col_global1:
            st.markdown("**Глобальная настройка для всех характеристик:**")
        with col_global2:
            temp_global_value = st.number_input(
                "Промптов на значение:",
                min_value=0,
                max_value=200,
                value=st.session_state.get('phase4_global_prompts', 3),
                key="temp_global_prompts_char",
                label_visibility="collapsed"
            )
        with col_global3:
            if st.button("📌 Применить ко всем", key="apply_global_char_btn", use_container_width=True):
                # Сохраняем глобальное значение
                st.session_state.phase4_global_prompts = temp_global_value

                # Обновляем для каждой характеристики
                for char in characteristics:
                    char_id = char.get('char_id', '')
                    if char_id:
                        if char_id not in st.session_state.phase4_char_settings:
                            st.session_state.phase4_char_settings[char_id] = {}
                        st.session_state.phase4_char_settings[char_id]['prompts_per_value'] = temp_global_value
                        st.session_state.phase4_char_settings[char_id]['char_name'] = char.get('char_name', '')

                # Сохраняем настройки
                save_phase4_settings(app_state)

                # Увеличиваем счетчик обновлений
                st.session_state.update_counter = st.session_state.get('update_counter', 0) + 1

                st.success(f"✅ Глобальное значение {temp_global_value} применено ко всем характеристикам!")
                time.sleep(0.3)
                st.rerun()

        st.divider()

        total_values = 0
        total_prompts = 0

        st.write("**Настройка для каждой характеристики:**")

        for idx, char in enumerate(characteristics):
            char_name = char.get('char_name', 'Без названия')
            char_id = char.get('char_id', f'char_{idx}')
            is_unique = char.get('is_unique', False)
            values_count = len(char.get('values', []))

            # Инициализируем настройки если нет
            if char_id not in st.session_state.phase4_char_settings:
                st.session_state.phase4_char_settings[char_id] = {
                    'prompts_per_value': st.session_state.get('phase4_global_prompts', 3),
                    'char_name': char_name
                }

            char_settings = st.session_state.phase4_char_settings[char_id]
            current_prompts = char_settings.get('prompts_per_value', 3)

            col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 2])

            with col1:
                st.write(f"**{char_name}**")
                st.caption(f"ID: {char_id}")

            with col2:
                st.write(f"**{values_count}**")
                st.caption("значений")

            with col3:
                # ✅ ПРАВИЛЬНОЕ ОТОБРАЖЕНИЕ ТИПА
                char_type_display = "🔷 Unique" if is_unique else "🟢 Regular"
                st.write(f"**{char_type_display}**")

            with col4:
                # Уникальный ключ
                safe_key = char_id.replace(' ', '_').replace('.', '_')
                widget_key = f"prompts_{safe_key}_{st.session_state.update_counter}"

                prompts_per_value = st.number_input(
                    "Промптов:",
                    min_value=0,
                    max_value=200,
                    value=int(current_prompts),
                    key=widget_key,
                    label_visibility="collapsed"
                )

                # Автосохранение при изменении
                if prompts_per_value != current_prompts:
                    st.session_state.phase4_char_settings[char_id]['prompts_per_value'] = prompts_per_value
                    if 'app_data' in st.session_state:
                        save_phase4_settings()

            with col5:
                char_prompts = values_count * prompts_per_value
                st.write(f"**→ {char_prompts}**")
                st.caption("промптов")

            total_values += values_count
            total_prompts += char_prompts

        st.divider()

        col_total1, col_total2, col_total3 = st.columns(3)
        with col_total1:
            st.metric("Всего характеристик", len(characteristics))
        with col_total2:
            st.metric("Всего значений", total_values)
        with col_total3:
            st.metric("Всего промптов", total_prompts)

        # ==================== НАСТРОЙКА OTHER БЛОКОВ ====================
        if other_blocks:
            with st.expander("📝 Настройка других блоков (заголовок, описание, применение и т.д.)", expanded=True):
                st.write("**Настройте количество промптов для каждого блока:**")

                # Глобальная настройка для other блоков
                col_global1, col_global2, col_global3 = st.columns([2, 1, 1])
                with col_global1:
                    st.markdown("**Глобальная настройка для всех блоков:**")
                with col_global2:
                    temp_global_other = st.number_input(
                        "Промптов на блок:",
                        min_value=0,
                        max_value=200,
                        value=st.session_state.get('phase4_global_other_prompts', 20),
                        key="temp_global_other_prompts",
                        label_visibility="collapsed"
                    )
                with col_global3:
                    if st.button("📌 Применить ко всем", key="apply_global_other_btn", use_container_width=True):
                        # Сохраняем глобальное значение
                        st.session_state.phase4_global_other_prompts = temp_global_other

                        # Обновляем для каждого блока
                        for block_id in other_blocks.keys():
                            if block_id not in st.session_state.phase4_other_blocks_settings:
                                st.session_state.phase4_other_blocks_settings[block_id] = {
                                    'enabled': True,
                                    'prompts_count': temp_global_other
                                }
                            else:
                                st.session_state.phase4_other_blocks_settings[block_id]['prompts_count'] = temp_global_other

                        # Сохраняем настройки
                        save_phase4_settings(app_state)

                        # Увеличиваем счетчик обновлений
                        st.session_state.update_counter = st.session_state.get('update_counter', 0) + 1

                        st.success(f"✅ Глобальное значение {temp_global_other} применено ко всем блокам!")
                        time.sleep(0.3)
                        st.rerun()

                st.divider()

                if 'phase4_other_blocks_settings' not in st.session_state:
                    st.session_state.phase4_other_blocks_settings = {}

                other_total_prompts = 0

                for block_id, block in other_blocks.items():
                    block_name = block.get('name', block_id)

                    if block_id not in st.session_state.phase4_other_blocks_settings:
                        st.session_state.phase4_other_blocks_settings[block_id] = {
                            'enabled': True,
                            'prompts_count': st.session_state.get('phase4_global_other_prompts', 20)
                        }

                    block_settings = st.session_state.phase4_other_blocks_settings[block_id]
                    current_count = block_settings.get('prompts_count', 20)

                    col1, col2, col3 = st.columns([3, 1, 1])

                    with col1:
                        enabled = st.checkbox(
                            f"{block_name}",
                            value=block_settings.get('enabled', True),
                            key=f"other_enabled_{block_id}_{st.session_state.update_counter}"
                        )

                    with col2:
                        safe_block_key = block_id.replace(' ', '_').replace('.', '_')
                        widget_key = f"other_count_{safe_block_key}_{st.session_state.update_counter}"
                        prompts_count = st.number_input(
                            "Промптов:",
                            min_value=0,
                            max_value=200,
                            value=int(current_count),
                            key=widget_key,
                            label_visibility="collapsed"
                        )

                    with col3:
                        st.write(f"**→ {prompts_count if enabled else 0}**")

                    if enabled != block_settings.get('enabled', True):
                        st.session_state.phase4_other_blocks_settings[block_id]['enabled'] = enabled
                        if 'app_data' in st.session_state:
                            save_phase4_settings()

                    if prompts_count != current_count:
                        st.session_state.phase4_other_blocks_settings[block_id]['prompts_count'] = prompts_count
                        if 'app_data' in st.session_state:
                            save_phase4_settings()

                    if enabled:
                        other_total_prompts += prompts_count

                st.divider()
                col_other1, col_other2 = st.columns(2)
                with col_other1:
                    st.metric("Всего других блоков", len(other_blocks))
                with col_other2:
                    st.metric("Всего промптов для других блоков", other_total_prompts)

    # ==================== ВЫБОР ШАБЛОНА ====================
    st.subheader("2. Выбор шаблона для генерации")

    if not characteristic_blocks:
        st.error("## ❌ Нет доступных блоков для характеристик")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔄 Обновить список блоков", use_container_width=True):
                st.session_state.block_manager.load_blocks()
                st.rerun()
        with col2:
            if st.button("📝 Перейти к редактированию", use_container_width=True):
                st.page_link("phase3.py", label="Открыть фазу 3")
        with col3:
            if st.button("🚀 Создать шаблоны характеристик", type="primary", use_container_width=True):
                create_default_templates()
                st.rerun()
        return

    # Выбор блока для regular характеристик
    if regular_blocks:
        regular_block_ids = list(regular_blocks.keys())
        if 'selected_regular_block_id' not in st.session_state or st.session_state.selected_regular_block_id not in regular_block_ids:
            st.session_state.selected_regular_block_id = regular_block_ids[0]

        selected_regular_block_id = st.selectbox(
            "Выберите шаблон для Regular характеристик:",
            regular_block_ids,
            format_func=lambda x: regular_blocks[x].get("name", x),
            key="regular_block_selector"
        )
        if selected_regular_block_id != st.session_state.selected_regular_block_id:
            st.session_state.selected_regular_block_id = selected_regular_block_id
            save_phase4_settings()
    else:
        selected_regular_block_id = None

    # Выбор блока для unique характеристик
    if unique_blocks:
        unique_block_ids = list(unique_blocks.keys())
        if 'selected_unique_block_id' not in st.session_state or st.session_state.selected_unique_block_id not in unique_block_ids:
            st.session_state.selected_unique_block_id = unique_block_ids[0]

        selected_unique_block_id = st.selectbox(
            "Выберите шаблон для Unique характеристик:",
            unique_block_ids,
            format_func=lambda x: unique_blocks[x].get("name", x),
            key="unique_block_selector"
        )
        if selected_unique_block_id != st.session_state.selected_unique_block_id:
            st.session_state.selected_unique_block_id = selected_unique_block_id
            save_phase4_settings()
    else:
        selected_unique_block_id = selected_regular_block_id if regular_blocks else None
        if selected_unique_block_id:
            st.warning("⚠️ Не найден шаблон для unique характеристик. Будет использован шаблон для regular.")

    # ==================== ГЕНЕРАЦИЯ ПРОМПТОВ ====================
    st.subheader("3. Генерация промптов")

    total_char_prompts = 0
    for char in characteristics:
        char_id = char.get('char_id', '')
        values_count = len(char.get('values', []))
        char_settings = st.session_state.phase4_char_settings.get(char_id, {})
        prompts_per_value = char_settings.get('prompts_per_value', st.session_state.get('phase4_global_prompts', 3))
        total_char_prompts += values_count * prompts_per_value

    total_other_prompts = 0
    if other_blocks:
        for block_id, settings in st.session_state.phase4_other_blocks_settings.items():
            if settings.get('enabled', False):
                total_other_prompts += settings.get('prompts_count', 0)

    total_all_prompts = total_char_prompts + total_other_prompts

    col_calc1, col_calc2, col_calc3 = st.columns(3)
    with col_calc1:
        st.info(f"**Промптов для характеристик:** {total_char_prompts}")
    with col_calc2:
        if other_blocks:
            st.info(f"**Промптов для других блоков:** {total_other_prompts}")
    with col_calc3:
        st.info(f"**Всего промптов:** {total_all_prompts}")

    if not settings_mode:
        if st.button("🚀 Сгенерировать все промпты", type="primary", use_container_width=True):
            with st.spinner("Генерация промптов..."):
                if markers:
                    st.session_state.marker_rotator = MarkerRotator(markers)

                st.session_state.prompt_generator.reset_usage_tracking()

                # ========== 7. ГЕНЕРАЦИЯ ПРОМПТОВ ==========
                all_prompts = []

                for char in characteristics:
                    char_id = char.get('char_id', '')
                    char_name = char.get('char_name', '')
                    is_unique = char.get('is_unique', False)
                    char_type = "unique" if is_unique else "regular"

                    char_setting = CHAR_SETTINGS.get(char_id, {})

                    # ✅ БЕЗОПАСНОЕ ПОЛУЧЕНИЕ prompts_per_value
                    prompts_per_value = char_setting.get('prompts_per_value', GLOBAL_PROMPTS_PER_VALUE)
                    if isinstance(prompts_per_value, dict):
                        prompts_per_value = GLOBAL_PROMPTS_PER_VALUE
                    try:
                        prompts_per_value = int(prompts_per_value)
                    except (TypeError, ValueError):
                        prompts_per_value = GLOBAL_PROMPTS_PER_VALUE

                    if char_type == "unique" and unique_blocks:
                        selected_block_id = SELECTED_UNIQUE_BLOCK_ID
                        if not selected_block_id or selected_block_id not in unique_blocks:
                            selected_block_id = list(unique_blocks.keys())[0] if unique_blocks else None
                    else:
                        selected_block_id = SELECTED_REGULAR_BLOCK_ID
                        if not selected_block_id or selected_block_id not in regular_blocks:
                            selected_block_id = list(regular_blocks.keys())[0] if regular_blocks else None

                    if not selected_block_id:
                        print(f"⚠️ Нет блока для {char_name}")
                        continue

                    print(f"🎯 Генерация для {char_name}: тип={char_type}, промптов на значение={prompts_per_value}")

                    prompts = st.session_state.prompt_generator.generate_prompts_for_characteristic(
                        characteristic=char,
                        block_id=selected_block_id,
                        num_prompts_per_value=prompts_per_value,
                        char_type=char_type,
                        category=category,
                        markers=markers,
                        marker_rotator=marker_rotator
                    )
                    all_prompts.extend(prompts)

                if other_blocks:
                    for block_id, settings in st.session_state.phase4_other_blocks_settings.items():
                        if settings.get('enabled', False) and block_id in other_blocks:
                            block = other_blocks[block_id]
                            prompts_count = settings.get('prompts_count', 3)
                            prompts = st.session_state.prompt_generator.generate_prompts_for_block(
                                block=block,
                                num_prompts=prompts_count,
                                category=category,
                                markers=markers,
                                marker_rotator=st.session_state.marker_rotator
                            )
                            all_prompts.extend(prompts)

                st.session_state.phase4_generated_prompts = all_prompts
                st.success(f"✅ Сгенерировано {len(all_prompts)} промптов!")

                if 'app_data' in st.session_state:
                    st.session_state.app_data['phase4'] = {
                        'prompts': all_prompts,
                        'category': category,
                        'markers': markers,
                        'characteristics_count': len(characteristics),
                        'other_blocks_count': len(other_blocks) if other_blocks else 0,
                        'total_prompts': len(all_prompts),
                        'char_settings': st.session_state.phase4_char_settings,
                        'other_blocks_settings': st.session_state.phase4_other_blocks_settings
                    }

                    # ✅ ДОБАВИТЬ ЭТО:
                    if app_state:
                        app_state.save_project()
                st.rerun()
    else:
        st.info(f"💾 Настройки сохранены. При автоматическом запуске будет сгенерировано **{total_all_prompts}** промптов.")

    if st.session_state.phase4_generated_prompts:
        display_generated_prompts(app_state)

        # ========== КНОПКА ПЕРЕХОДА К ФАЗЕ 5 ==========
        st.divider()
        st.markdown("### 🚀 Переход к следующей фазе")

        col_next1, col_next2, col_next3 = st.columns([1, 2, 1])
        with col_next2:
            if st.button("➡️ Перейти к фазе 5 (Генерация текстов)", type="primary", use_container_width=True):
                # Сохраняем настройки и промпты
                save_phase4_settings(app_state, context)
                if app_state:
                    app_state.save_project()
                # Переключаем фазу
                st.session_state.current_phase = 5
                if app_state:
                    app_state.current_phase = 5
                st.rerun()

        st.info(
            f"💡 Всего сгенерировано **{len(st.session_state.phase4_generated_prompts)}** промптов. Они будут переданы в фазу 5 для генерации текстов.")

def update_global_prompts_settings(characteristics):
    """Обновляет глобальные настройки промптов для характеристик"""
    # Получаем значение из поля ввода
    global_prompts = st.session_state.get('global_prompts_input', 3)

    print(f"🔄 update_global_prompts_settings called with value: {global_prompts}")

    # Сохраняем глобальное значение
    st.session_state.phase4_global_prompts = global_prompts

    # Обновляем для каждой характеристики
    for char in characteristics:
        char_id = char.get('char_id', '')
        if char_id:
            if char_id not in st.session_state.phase4_char_settings:
                st.session_state.phase4_char_settings[char_id] = {}
            st.session_state.phase4_char_settings[char_id]['prompts_per_value'] = global_prompts
            st.session_state.phase4_char_settings[char_id]['char_name'] = char.get('char_name', '')

    # Немедленно сохраняем в app_data
    save_phase4_settings()

    # Увеличиваем счетчик обновлений для принудительной перерисовки
    st.session_state.update_counter = st.session_state.get('update_counter', 0) + 1

    st.success(f"✅ Глобальное значение {global_prompts} применено ко всем характеристикам!")
    time.sleep(0.3)
    st.rerun()

def update_global_other_blocks_settings(other_blocks):
    """Обновляет глобальные настройки для других блоков"""
    # Получаем значение из поля ввода
    global_other = st.session_state.get('global_other_prompts_input', 20)

    print(f"🔄 update_global_other_blocks_settings called with value: {global_other}")

    # Сохраняем в session_state
    st.session_state.phase4_global_other_prompts = global_other

    for block_id in other_blocks.keys():
        if block_id not in st.session_state.phase4_other_blocks_settings:
            st.session_state.phase4_other_blocks_settings[block_id] = {
                'enabled': True,
                'prompts_count': global_other
            }
        else:
            st.session_state.phase4_other_blocks_settings[block_id]['prompts_count'] = global_other

    # Немедленно сохраняем в app_data
    save_phase4_settings()

    # Увеличиваем счетчик обновлений
    st.session_state.update_counter = st.session_state.get('update_counter', 0) + 1

    st.success(f"✅ Глобальное значение {global_other} применено ко всем блокам!")
    time.sleep(0.3)
    st.rerun()

def display_generated_prompts(app_state=None):
    """Отображает список сгенерированных промптов с пагинацией"""
    st.subheader("📋 Сгенерированные промпты")

    col_filter1, col_filter2, col_filter3 = st.columns(3)
    with col_filter1:
        # Собираем уникальные названия для фильтрации
        char_names = list(set(p.get('characteristic_name', '') for p in st.session_state.phase4_generated_prompts if 'characteristic_name' in p))
        block_names = list(set(p.get('block_name', '') for p in st.session_state.phase4_generated_prompts if 'block_name' in p and p.get('block_type') == 'other'))

        filter_options = ["Все"]
        if char_names:
            char_names_filtered = [n for n in char_names if n]
            if char_names_filtered:
                filter_options.append("--- Характеристики ---")
                filter_options.extend(sorted(char_names_filtered))
        if block_names:
            block_names_filtered = [n for n in block_names if n]
            if block_names_filtered:
                filter_options.append("--- Другие блоки ---")
                filter_options.extend(sorted(block_names_filtered))

        filter_item = st.selectbox("Фильтр по характеристике/блоку:", filter_options, key="filter_item")

    with col_filter2:
        filter_type = st.selectbox("Фильтр по типу:", ["Все", "regular", "unique", "other"], key="filter_type")

    with col_filter3:
        items_per_page = st.selectbox("Промптов на странице:", [5, 10, 20, 50], index=0, key="items_per_page")

    filtered_prompts = st.session_state.phase4_generated_prompts

    if filter_item != "Все":
        if not filter_item.startswith("---"):
            filtered_prompts = [
                p for p in filtered_prompts
                if (p.get('characteristic_name') == filter_item) or (p.get('block_name') == filter_item)
            ]

    if filter_type != "Все":
        if filter_type == "other":
            filtered_prompts = [p for p in filtered_prompts if p.get('block_type') == 'other' or p.get('type') == 'other']
        else:
            filtered_prompts = [p for p in filtered_prompts if p.get('type') == filter_type]

    st.caption(f"Показано {len(filtered_prompts)} из {len(st.session_state.phase4_generated_prompts)} промптов")

    total_pages = max(1, (len(filtered_prompts) + items_per_page - 1) // items_per_page)

    col_pag1, col_pag2, col_pag3 = st.columns([1, 3, 1])
    with col_pag1:
        if st.button("◀️ Предыдущая", disabled=st.session_state.phase4_page <= 0):
            st.session_state.phase4_page -= 1
            st.rerun()

    with col_pag2:
        st.write(f"Страница {st.session_state.phase4_page + 1} из {total_pages}")

    with col_pag3:
        if st.button("Следующая ▶️", disabled=st.session_state.phase4_page >= total_pages - 1):
            st.session_state.phase4_page += 1
            st.rerun()

    start_idx = st.session_state.phase4_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_prompts))

    for i, prompt_data in enumerate(filtered_prompts[start_idx:end_idx]):
        # Определяем заголовок
        if 'characteristic_name' in prompt_data:
            title = f"Характеристика: {prompt_data['characteristic_name']} = {prompt_data.get('value', '')} ({prompt_data.get('type', 'unknown')})"
        else:
            block_name = prompt_data.get('block_name', 'Неизвестный блок')
            title = f"Блок: {block_name} (промпт {prompt_data.get('prompt_num', 1)})"

        with st.expander(f"Промпт #{start_idx + i + 1}: {title}", expanded=False):
            st.markdown(prompt_data['prompt'], unsafe_allow_html=False)

            unresolved = prompt_data.get('unresolved_variables', [])
            if unresolved:
                st.warning(f"⚠️ **Необработанные переменные:** {', '.join(unresolved)}")

            # Информация о промпте
            if 'characteristic_name' in prompt_data:
                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.caption(f"**Характеристика:** {prompt_data['characteristic_name']}")
                with col_info2:
                    st.caption(f"**Значение:** {prompt_data.get('value', '')}")
                with col_info3:
                    st.caption(f"**Тип:** {prompt_data.get('type', 'unknown')}")
            else:
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    block_name = prompt_data.get('block_name', 'Неизвестный')
                    st.caption(f"**Блок:** {block_name}")
                with col_info2:
                    st.caption(f"**Тип блока:** {prompt_data.get('block_type', 'other')}")

    if len(filtered_prompts) > end_idx:
        st.info(f"И ещё {len(filtered_prompts) - end_idx} промптов...")

    # Экспорт
    st.divider()
    st.subheader("💾 Экспорт данных")

    col_export1, col_export2 = st.columns(2)
    with col_export1:
        export_data = {
            'category': st.session_state.get('phase1_data', {}).get('category', ''),
            'total_prompts': len(st.session_state.phase4_generated_prompts),
            'prompts': st.session_state.phase4_generated_prompts[:100]
        }

        st.download_button(
            label="📥 Скачать промпты (JSON)",
            data=json.dumps(export_data, ensure_ascii=False, indent=2),
            file_name=f"prompts_{st.session_state.get('phase1_data', {}).get('category', 'output')}.json",
            mime="application/json",
            use_container_width=True,
            key="download_prompts"
        )

    with col_export2:
        if st.button("💾 Сохранить настройки генерации", use_container_width=True, key="save_generation_settings"):
            settings = {
                'char_settings': st.session_state.phase4_char_settings,
                'other_blocks_settings': st.session_state.phase4_other_blocks_settings,
                'selected_regular_block_id': st.session_state.selected_regular_block_id,
                'selected_unique_block_id': st.session_state.selected_unique_block_id,
                'global_prompts': st.session_state.phase4_global_prompts,
                'global_other_prompts': st.session_state.phase4_global_other_prompts
            }

            # Сохраняем в session_state
            st.session_state.phase4_settings = settings

            # Сохраняем в app_data
            if 'app_data' in st.session_state:
                st.session_state.app_data['phase4_settings'] = settings
                if app_state:
                    app_state.save_project()

            st.success("✅ Настройки сохранены!")
def create_default_templates():
    """Создает шаблоны по умолчанию для характеристик"""
    regular_block_id, regular_block, regular_variables = st.session_state.block_manager.create_new_block()
    regular_block.update({
        "block_id": "characteristic_regular_template",
        "name": "Шаблон для Regular характеристики",
        "description": "Шаблон для regular характеристик",
        "block_type": "characteristic",
        "template": """Ты должен генерировать текст, полностью исключая определительные конструкции с тире и союзом 'что'.
{стиль_текста}.
Объем: {объем_характеристики}. 
{скобки_характеристика}
{контекст_категория}.
Тут крайне внимательно: {инструкция_характеристика} {название_характеристики} так, чтобы значение {значение_форматированное} было логично вставлено в текст, {подводка_характеристика}
Обязательно используй "{характеристика_маркер}" один раз в тексте.  
Структура предложения: {структура_характеристики}.
{ограничение_повторы}.
{требование_тошноты}.
{стоп}.""",
        "variables": [
            "стиль_текста",
            "объем_характеристики",
            "структура_характеристики",
            "подводка_характеристика",
            "инструкция_характеристика",
            "ограничение_повторы",
            "требование_тошноты",
            "скобки_характеристика"
        ],
        "settings": {
            "маркер_позиция": "начало",
            "формат_значения_regular": "[[значение]]",
            "формат_значения_unique": "\"[значение]\"",
            "добавлять_скобки_переменную": True,
            "characteristic_type": "regular"
        }
    })

    unique_block_id, unique_block, unique_variables = st.session_state.block_manager.create_new_block()
    unique_block.update({
        "block_id": "characteristic_unique_template",
        "name": "Шаблон для Unique характеристики",
        "description": "Шаблон для unique характеристик",
        "block_type": "characteristic",
        "template": """Ты должен генерировать текст, полностью исключая определительные конструкции с тире и союзом 'что'.
{стиль_текста}.
Объем: {объем_характеристики}. 
{контекст_категория}.
Тут крайне внимательно: {инструкция_характеристика} {название_характеристики} так, чтобы значение {значение_форматированное} было логично вставлено в текст, {подводка_характеристика}
Обязательно используй "{характеристика_маркер}" один раз в тексте.  
Структура предложения: {структура_характеристики}.
{ограничение_повторы}.
{требование_тошноты}.
{стоп}.""",
        "variables": [
            "стиль_текста",
            "объем_характеристики",
            "структура_характеристики",
            "подводка_характеристика",
            "инструкция_характеристика",
            "ограничение_повторы",
            "требование_тошноты"
        ],
        "settings": {
            "маркер_позиция": "начало",
            "формат_значения_regular": "[[значение]]",
            "формат_значения_unique": "\"[значение]\"",
            "добавлять_скобки_переменную": False,
            "characteristic_type": "unique"
        }
    })

    st.session_state.block_manager.save_block(regular_block, regular_variables)
    st.session_state.block_manager.save_block(unique_block, unique_variables)
    st.session_state.block_manager.load_blocks()
    st.success("✅ Шаблоны для regular и unique характеристик созданы!")

# phase4.py - добавить в конец файла

# phase4.py - добавить в конец файла

# phase4.py - исправленная функция

def auto_generate_all_prompts(app_state=None, context=None):
    """Генерация промптов с приоритетом контекста"""
    from pathlib import Path
    import json
    from datetime import datetime

    print("=" * 60)
    print("🔄 auto_generate_all_prompts STARTED")
    print("=" * 60)

    # ✅ ПРИОРИТЕТ 1: ВОССТАНАВЛИВАЕМ AI ИНСТРУКЦИИ ИЗ КОНТЕКСТА
    restore_ai_instructions(context)

    # ✅ ПРИОРИТЕТ 2: ПОЛУЧАЕМ КОНТЕКСТ
    ctx_data = _get_context_data(context, st.session_state)

    # ✅ ПРИОРИТЕТ 3: ЗАГРУЖАЕМ НАСТРОЙКИ
    settings = {}
    generated_prompts = []

    # ===== ПРЯМО ЗАГРУЖАЕМ ИЗ ФАЙЛА (самый надежный способ) =====
    user_id = ctx_data.get('user_id')
    site = ctx_data.get('site_name', 'steelborg')
    domain = ctx_data.get('domain_name', 'default')
    project_id = ctx_data.get('project_id')

    if user_id and project_id:
        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")
        print(f"📂 Загружаем из файла: {project_file}")

        if project_file.exists():
            try:
                with open(project_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)

                # ✅ ПРЯМО ИЩЕМ phase4_settings (ГЛАВНЫЙ ПУТЬ)
                settings = file_data.get('app_data', {}).get('phase4_settings', {})
                if settings:
                    print(f"✅ Загружены настройки из файла: {len(settings)} настроек")
                    print(f"   global_prompts: {settings.get('global_prompts')}")
                    print(f"   char_settings: {len(settings.get('char_settings', {}))}")

                # ✅ ТАКЖЕ ПРОВЕРЯЕМ phase4.settings (если есть)
                if not settings:
                    phase4_data = file_data.get('app_data', {}).get('phase4', {})
                    settings = phase4_data.get('settings', {})
                    if settings:
                        print(f"✅ Загружены настройки из phase4.settings: {len(settings)}")

                # Загружаем промпты если есть
                phase4_prompts = file_data.get('app_data', {}).get('phase4', {}).get('prompts', [])
                if phase4_prompts:
                    generated_prompts = phase4_prompts
                    print(f"   Загружено промптов: {len(generated_prompts)}")

            except Exception as e:
                print(f"⚠️ Ошибка загрузки файла: {e}")

    # ===== ЕСЛИ НЕ ЗАГРУЗИЛИСЬ - ПРОВЕРЯЕМ ДРУГИЕ ИСТОЧНИКИ =====
    if not settings:
        # ИЗ КОНТЕКСТА
        if ctx_data['has_context'] and context is not None:
            phase4_data = context.get_phase_data(4)
            if phase4_data:
                settings = phase4_data.get('settings', {})
                generated_prompts = phase4_data.get('prompts', [])
                print(f"✅ Загружены настройки из КОНТЕКСТА: {len(settings)}")

        # ИЗ APP_STATE
        if not settings and app_state:
            phase4_data = app_state.get_phase_data(4)
            if phase4_data:
                settings = phase4_data.get('settings', {})
                generated_prompts = phase4_data.get('prompts', [])
                print(f"✅ Загружены настройки из APP_STATE: {len(settings)}")

        # ИЗ SESSION_STATE
        if not settings:
            settings = st.session_state.get('phase4_settings', {})
            if settings:
                print(f"✅ Загружены настройки из SESSION_STATE: {len(settings)}")

    # ========== 4. ЗАГРУЖАЕМ ДАННЫЕ ФАЗЫ 1 ==========
    phase1_data = None

    # ИЗ КОНТЕКСТА
    if ctx_data['has_context'] and context is not None:
        phase1_data = context.get_phase_data(1)
        if phase1_data:
            print(f"✅ Phase1 из КОНТЕКСТА: {len(phase1_data.get('characteristics', []))} характеристик")

    # ИЗ APP_STATE
    if not phase1_data and app_state:
        phase1_data = app_state.get_phase_data(1)
        if phase1_data:
            print(f"✅ Phase1 из APP_STATE: {len(phase1_data.get('characteristics', []))} характеристик")

    # ИЗ SESSION_STATE
    if not phase1_data:
        phase1_data = st.session_state.get('phase1_data', {})
        if phase1_data:
            print(f"✅ Phase1 из SESSION_STATE: {len(phase1_data.get('characteristics', []))} характеристик")

    # ========== 5. ИЗВЛЕКАЕМ НАСТРОЙКИ ==========
    if not settings:
        print("⚠️ Настройки не загружены, используем значения по умолчанию")

    try:
        GLOBAL_PROMPTS_PER_VALUE = int(settings.get('global_prompts', 3))
    except (TypeError, ValueError):
        GLOBAL_PROMPTS_PER_VALUE = 3

    try:
        GLOBAL_OTHER_PROMPTS = int(settings.get('global_other_prompts', 20))
    except (TypeError, ValueError):
        GLOBAL_OTHER_PROMPTS = 20

    CHAR_SETTINGS = settings.get('char_settings', {})
    OTHER_BLOCKS_SETTINGS = settings.get('other_blocks_settings', {})
    SELECTED_REGULAR_BLOCK_ID = settings.get('selected_regular_block_id')
    SELECTED_UNIQUE_BLOCK_ID = settings.get('selected_unique_block_id')

    print(f"\n📊 ИТОГОВЫЕ НАСТРОЙКИ:")
    print(f"   global_prompts: {GLOBAL_PROMPTS_PER_VALUE}")
    print(f"   global_other: {GLOBAL_OTHER_PROMPTS}")
    print(f"   char_settings: {len(CHAR_SETTINGS)}")
    print(f"   other_blocks_settings: {len(OTHER_BLOCKS_SETTINGS)}")

    # ... остальной код без изменений ...
    # ... остальной код без изменений ...
    # ========== 6. ЗАГРУЖАЕМ БЛОКИ ==========
    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    blocks_data = {}

    # ИЗ КОНТЕКСТА
    if ctx_data['has_context'] and context is not None:
        phase3_data = context.get_phase_data(3)
        if phase3_data and phase3_data.get('blocks'):
            blocks_data = phase3_data.get('blocks', {})
            print(f"✅ Блоки из КОНТЕКСТА: {len(blocks_data)} блоков")

    # ИЗ ДОМЕНА
    if not blocks_data:
        phase3_from_domain = dm.load_phase_data(3)
        if phase3_from_domain and phase3_from_domain.get('blocks'):
            blocks_data = phase3_from_domain.get('blocks', {})
            print(f"✅ Блоки из ДОМЕНА: {len(blocks_data)} блоков")

    # ИЗ APP_STATE
    if not blocks_data:
        blocks_data = st.session_state.app_data.get('phase3', {}).get('blocks', {})
        if blocks_data:
            print(f"✅ Блоки из APP_STATE: {len(blocks_data)} блоков")

    if not blocks_data:
        return {
            'success': False,
            'message': '❌ Нет блоков. Сначала создайте блоки в фазе 3.',
            'prompts': generated_prompts,
            'count': len(generated_prompts)
        }

    # ========== 7. ИНИЦИАЛИЗАЦИЯ МЕНЕДЖЕРОВ ==========
    if 'block_manager' not in st.session_state:
        from phases.phase3 import BlockManager, VariableManager, DynamicVariableManager

        # ✅ БЕРЁМ ДОМЕН ИЗ КОНТЕКСТА
        domain_name = ctx_data.get('domain_name', 'default')
        site_name = ctx_data.get('site_name', 'steelborg')

        st.session_state.block_manager = BlockManager(
            domain_name=domain_name,
            site_name=site_name
        )
        st.session_state.variable_manager = VariableManager(st.session_state.block_manager)
        st.session_state.dynamic_var_manager = DynamicVariableManager()
    # Загружаем блоки в менеджер
    for block_id, block_info in blocks_data.items():
        existing = st.session_state.block_manager.get_block(block_id)
        if not existing:
            st.session_state.block_manager.save_block(block_info, block_info.get('variables_data', {}))

    st.session_state.block_manager.load_blocks()

    # ========== 8. ПОДГОТОВКА ДАННЫХ ==========
    characteristics = phase1_data.get('characteristics', [])
    category = phase1_data.get('category', '')

    # Получаем маркеры с приоритетом
    markers = []

    # ИЗ КОНТЕКСТА
    if ctx_data['has_context'] and context is not None:
        phase2_data = context.get_phase_data(2)
        if phase2_data:
            markers = phase2_data.get('markers', [])
            print(f"✅ Маркеры из КОНТЕКСТА: {len(markers)}")

    # ИЗ APP_STATE
    if not markers and app_state:
        phase2_data = app_state.get_phase_data(2)
        if phase2_data:
            markers = phase2_data.get('markers', [])

    # ИЗ SESSION_STATE
    if not markers:
        markers = st.session_state.app_data.get('phase2', {}).get('markers', [])

    # ... (продолжение генерации - то же самое) ...

    # Разделяем блоки по типам
    all_blocks = st.session_state.block_manager.get_all_blocks()
    regular_blocks = {}
    unique_blocks = {}
    other_blocks = {}

    for block_id, block in all_blocks.items():
        block_type = block.get('block_type', 'other')
        if block_type == 'characteristic':
            settings_block = block.get('settings', {})
            char_type = settings_block.get('characteristic_type', 'regular')
            if char_type == 'unique':
                unique_blocks[block_id] = block
            else:
                regular_blocks[block_id] = block
        elif block_type == 'other':
            other_blocks[block_id] = block

    # ========== 9. ГЕНЕРАЦИЯ ==========
    if 'prompt_generator' not in st.session_state:
        st.session_state.prompt_generator = PromptGenerator(
            st.session_state.block_manager,
            st.session_state.variable_manager,
            st.session_state.dynamic_var_manager
        )

    st.session_state.prompt_generator.reset_usage_tracking()
    marker_rotator = MarkerRotator(markers) if markers else None

    all_prompts = []

    # Генерация для характеристик
    for char in characteristics:
        char_id = char.get('char_id', '')
        char_name = char.get('char_name', '')
        is_unique = char.get('is_unique', False)
        char_type = "unique" if is_unique else "regular"

        char_setting = CHAR_SETTINGS.get(char_id, {})
        prompts_per_value = char_setting.get('prompts_per_value', GLOBAL_PROMPTS_PER_VALUE)

        try:
            prompts_per_value = int(prompts_per_value)
        except (TypeError, ValueError):
            prompts_per_value = GLOBAL_PROMPTS_PER_VALUE

        print(f"🎯 {char_name}: prompts_per_value={prompts_per_value}")

        if prompts_per_value == 0:
            continue

        if char_type == "unique" and unique_blocks:
            selected_block_id = SELECTED_UNIQUE_BLOCK_ID
            if not selected_block_id or selected_block_id not in unique_blocks:
                selected_block_id = list(unique_blocks.keys())[0] if unique_blocks else None
        else:
            selected_block_id = SELECTED_REGULAR_BLOCK_ID
            if not selected_block_id or selected_block_id not in regular_blocks:
                selected_block_id = list(regular_blocks.keys())[0] if regular_blocks else None

        if not selected_block_id:
            print(f"⚠️ Нет блока для {char_name}")
            continue

        prompts = st.session_state.prompt_generator.generate_prompts_for_characteristic(
            characteristic=char,
            block_id=selected_block_id,
            num_prompts_per_value=prompts_per_value,
            char_type=char_type,
            category=category,
            markers=markers,
            marker_rotator=marker_rotator
        )
        all_prompts.extend(prompts)

    # Генерация для other блоков
    for block_id, block in other_blocks.items():
        block_setting = OTHER_BLOCKS_SETTINGS.get(block_id, {})
        enabled = block_setting.get('enabled', True)
        prompts_count = block_setting.get('prompts_count', GLOBAL_OTHER_PROMPTS)

        if not enabled or prompts_count == 0:
            continue

        prompts = st.session_state.prompt_generator.generate_prompts_for_block(
            block=block,
            num_prompts=prompts_count,
            category=category,
            markers=markers,
            marker_rotator=marker_rotator
        )
        all_prompts.extend(prompts)

    # ========== 10. СОХРАНЕНИЕ ==========
    print(f"\n{'='*60}")
    print(f"💾 СОХРАНЕНИЕ PHASE4: {len(all_prompts)} промптов")
    print(f"{'='*60}\n")

    if not all_prompts:
        return {
            'success': False,
            'message': '❌ Не удалось сгенерировать промпты',
            'prompts': [],
            'count': 0
        }

    # ✅ ПРИОРИТЕТ 1: СОХРАНЯЕМ В КОНТЕКСТ
    if ctx_data['has_context'] and context is not None:
        phase4_data = {
            'prompts': all_prompts,
            'generated_count': len(all_prompts),
            'generated_at': datetime.now().isoformat(),
            'settings': settings
        }
        context.set_phase_data(4, phase4_data)
        context.save()
        print(f"   ✅ Сохранено в КОНТЕКСТ: {len(all_prompts)} промптов")

    # ✅ ПРИОРИТЕТ 2: СОХРАНЯЕМ В APP_STATE
    if app_state:
        app_state.set_phase_data(4, {
            'prompts': all_prompts,
            'generated_count': len(all_prompts),
            'generated_at': datetime.now().isoformat(),
            'settings': settings
        })
        app_state.save_project()
        print(f"   ✅ Сохранено в APP_STATE: {len(all_prompts)} промптов")

    # ✅ ПРИОРИТЕТ 3: СОХРАНЯЕМ В ФАЙЛ
    try:
        user_id = ctx_data.get('user_id')
        site = ctx_data.get('site_name', 'steelborg')
        domain = ctx_data.get('domain_name', 'default')
        project_id = ctx_data.get('project_id')

        if user_id and project_id:
            project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

            if project_file.exists():
                with open(project_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
            else:
                file_data = {
                    "project_id": project_id,
                    "user_id": user_id,
                    "site_name": site,
                    "domain_name": domain,
                    "created_at": datetime.now().isoformat()
                }

            if 'app_data' not in file_data:
                file_data['app_data'] = {}

            file_data['app_data']['phase4'] = {
                'prompts': all_prompts,
                'generated_count': len(all_prompts),
                'generated_at': datetime.now().isoformat(),
                'settings': settings
            }
            file_data['app_data']['phase4_generated_prompts'] = all_prompts
            file_data['app_data']['phase4_settings'] = settings
            file_data['updated_at'] = datetime.now().isoformat()
            file_data['current_phase'] = 4

            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, ensure_ascii=False, indent=2)

            print(f"   ✅ Сохранено в ФАЙЛ: {project_file}")
    except Exception as e:
        print(f"   ❌ Ошибка сохранения в файл: {e}")

    # Обновляем session_state
    st.session_state.phase4_generated_prompts = all_prompts
    st.session_state.phase4_settings = settings

    return {
        'success': True,
        'message': f'✅ Сгенерировано {len(all_prompts)} промптов',
        'prompts': all_prompts,
        'count': len(all_prompts)
    }


# phase4.py - исправленные функции

def load_settings_from_file(app_state=None, context=None):
    """Загружает настройки из файла или контекста"""
    from pathlib import Path
    import json

    # ✅ ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
    if context is not None:
        phase4_data = context.get_phase_data(4)
        if phase4_data and phase4_data.get('settings'):
            settings = phase4_data.get('settings', {})
            st.session_state.phase4_global_prompts = settings.get('global_prompts', 3)
            st.session_state.phase4_global_other_prompts = settings.get('global_other_prompts', 20)
            st.session_state.phase4_char_settings = settings.get('char_settings', {})
            st.session_state.phase4_other_blocks_settings = settings.get('other_blocks_settings', {})
            st.session_state.selected_regular_block_id = settings.get('selected_regular_block_id')
            st.session_state.selected_unique_block_id = settings.get('selected_unique_block_id')
            st.session_state.phase4_settings = settings

            prompts = phase4_data.get('prompts', [])
            if prompts:
                st.session_state.phase4_generated_prompts = prompts

            print(f"✅ Загружены настройки из КОНТЕКСТА: global_prompts={settings.get('global_prompts')}, промптов={len(prompts)}")
            return True

    # ✅ ПРИОРИТЕТ 2: ИЗ APP_STATE
    if app_state:
        phase4_data = app_state.get_phase_data(4)
        if phase4_data and phase4_data.get('settings'):
            settings = phase4_data.get('settings', {})
            st.session_state.phase4_global_prompts = settings.get('global_prompts', 3)
            st.session_state.phase4_global_other_prompts = settings.get('global_other_prompts', 20)
            st.session_state.phase4_char_settings = settings.get('char_settings', {})
            st.session_state.phase4_other_blocks_settings = settings.get('other_blocks_settings', {})
            st.session_state.selected_regular_block_id = settings.get('selected_regular_block_id')
            st.session_state.selected_unique_block_id = settings.get('selected_unique_block_id')
            st.session_state.phase4_settings = settings

            prompts = phase4_data.get('prompts', [])
            if prompts:
                st.session_state.phase4_generated_prompts = prompts

            print(f"✅ Загружены настройки из APP_STATE: global_prompts={settings.get('global_prompts')}")
            return True

    # ✅ ПРИОРИТЕТ 3: ИЗ ФАЙЛА
    # Получаем параметры из разных источников
    user_id = None
    site = None
    domain = None
    project_id = None

    # Из контекста
    if context is not None:
        if hasattr(context, 'user_id'):
            user_id = context.user_id
            site = context.site_name
            domain = context.domain_name
            project_id = context.project_id
        elif isinstance(context, dict):
            user_id = context.get('user_id')
            site = context.get('site_name')
            domain = context.get('domain_name')
            project_id = context.get('project_id')

    # Из session_state
    if user_id is None:
        user_id = st.session_state.get('user_id')
    if site is None:
        site = st.session_state.get('current_site', 'steelborg')
    if domain is None:
        domain = st.session_state.get('current_domain', 'default')
    if project_id is None:
        project_id = st.session_state.get('current_project_id')

    # Из app_state
    if app_state and project_id is None:
        if hasattr(app_state, 'project_id'):
            project_id = app_state.project_id
        elif hasattr(app_state, 'get_project_id'):
            project_id = app_state.get_project_id()

    print(f"📂 Загрузка из файла: user={user_id}, site={site}, domain={domain}, project={project_id}")

    if user_id and project_id and site and domain:
        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

        if project_file.exists():
            try:
                with open(project_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                settings = data.get('app_data', {}).get('phase4_settings', {})

                if settings:
                    st.session_state.phase4_global_prompts = settings.get('global_prompts', 3)
                    st.session_state.phase4_global_other_prompts = settings.get('global_other_prompts', 20)
                    st.session_state.phase4_char_settings = settings.get('char_settings', {})
                    st.session_state.phase4_other_blocks_settings = settings.get('other_blocks_settings', {})
                    st.session_state.selected_regular_block_id = settings.get('selected_regular_block_id')
                    st.session_state.selected_unique_block_id = settings.get('selected_unique_block_id')
                    st.session_state.phase4_settings = settings

                    prompts = data.get('app_data', {}).get('phase4', {}).get('prompts', [])
                    if prompts:
                        st.session_state.phase4_generated_prompts = prompts

                    print(f"✅ Загружены настройки из ФАЙЛА: {project_file}")
                    return True
            except Exception as e:
                print(f"⚠️ Ошибка загрузки из файла: {e}")

    print("⚠️ Настройки не загружены, используем значения по умолчанию")
    return False


def load_phase4_settings(app_state=None, context=None):
    """Загружает настройки фазы 4 с приоритетом контекста"""

    # ✅ ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
    if context is not None:
        phase4_data = context.get_phase_data(4)
        if phase4_data and phase4_data.get('settings'):
            settings = phase4_data.get('settings', {})
            st.session_state.phase4_settings = settings
            st.session_state.phase4_char_settings = settings.get('char_settings', {})
            st.session_state.phase4_other_blocks_settings = settings.get('other_blocks_settings', {})
            st.session_state.selected_regular_block_id = settings.get('selected_regular_block_id')
            st.session_state.selected_unique_block_id = settings.get('selected_unique_block_id')

            global_prompts = settings.get('global_prompts', 3)
            if isinstance(global_prompts, dict):
                global_prompts = 3
            st.session_state.phase4_global_prompts = int(global_prompts) if global_prompts else 3

            global_other = settings.get('global_other_prompts', 20)
            if isinstance(global_other, dict):
                global_other = 20
            st.session_state.phase4_global_other_prompts = int(global_other) if global_other else 20

            print(f"✅ Загружены настройки из КОНТЕКСТА: global_prompts={st.session_state.phase4_global_prompts}")
            return True

    # ✅ ПРИОРИТЕТ 2: ИЗ APP_STATE
    if app_state:
        phase4_data = app_state.get_phase_data(4)
        if phase4_data and phase4_data.get('settings'):
            settings = phase4_data.get('settings', {})
            st.session_state.phase4_settings = settings
            st.session_state.phase4_char_settings = settings.get('char_settings', {})
            st.session_state.phase4_other_blocks_settings = settings.get('other_blocks_settings', {})
            st.session_state.selected_regular_block_id = settings.get('selected_regular_block_id')
            st.session_state.selected_unique_block_id = settings.get('selected_unique_block_id')

            global_prompts = settings.get('global_prompts', 3)
            if isinstance(global_prompts, dict):
                global_prompts = 3
            st.session_state.phase4_global_prompts = int(global_prompts) if global_prompts else 3

            global_other = settings.get('global_other_prompts', 20)
            if isinstance(global_other, dict):
                global_other = 20
            st.session_state.phase4_global_other_prompts = int(global_other) if global_other else 20

            print(f"✅ Загружены настройки из APP_STATE: global_prompts={st.session_state.phase4_global_prompts}")
            return True

    # ✅ ПРИОРИТЕТ 3: ИЗ ФАЙЛА
    return load_settings_from_file(app_state, context)



def log(msg):
    """Простое логирование для отладки"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] phase4: {msg}")


def generate_prompts_auto(phase1_data, phase2_data, phase3_data, settings=None):
    """
    Автоматическая генерация промптов без UI
    Возвращает словарь с результатами
    """
    characteristics = phase1_data.get('characteristics', [])
    markers = phase2_data.get('markers', [])
    blocks = phase3_data.get('blocks', {})

    if not characteristics:
        return {"success": False, "message": "Нет характеристик", "prompts": []}

    # Настройки по умолчанию
    prompts_per_char = settings.get('prompts_per_characteristic', 3) if settings else 3
    include_markers = settings.get('include_markers', True) if settings else True

    generated_prompts = []

    for char in characteristics:
        char_name = char.get('char_name', '')
        char_values = char.get('values', [])

        # Находим подходящий блок для этой характеристики
        block_id = None
        for bid, block_data in blocks.items():
            if block_data.get('block_type') == 'characteristic':
                block_id = bid
                break

        if block_id:
            template = blocks.get(block_id, {}).get('template', '')
        else:
            # Шаблон по умолчанию
            template = "Опиши {характеристика} для {категория} со значениями: {значения}"

        # Генерируем промпты для каждой характеристики
        for i in range(prompts_per_char):
            prompt = template
            prompt = prompt.replace("{характеристика}", char_name)
            prompt = prompt.replace("{категория}", phase1_data.get('category', ''))

            if char_values:
                values_str = ", ".join([v.get('value', '') for v in char_values[:3]])
                prompt = prompt.replace("{значения}", values_str)

            if include_markers and markers:
                marker_str = " ".join([f"[{m}]" for m in markers[:3]])
                prompt = prompt.replace("{маркеры}", marker_str)

            generated_prompts.append({
                "char_id": char.get('char_id', ''),
                "char_name": char_name,
                "prompt": prompt,
                "prompt_index": i + 1
            })

    return {
        "success": True,
        "message": f"Сгенерировано {len(generated_prompts)} промптов",
        "prompts": generated_prompts,
        "count": len(generated_prompts)
    }
def save_data_to_app_state(app_state=None):
    """Сохраняет данные фазы 4 в общее состояние приложения"""
    if 'app_data' in st.session_state:
        if st.session_state.phase4_generated_prompts:
            st.session_state.app_data['phase4'] = {
                'prompts': st.session_state.phase4_generated_prompts,
                'char_settings': st.session_state.phase4_char_settings,
                'other_blocks_settings': st.session_state.phase4_other_blocks_settings,
                'selected_regular_block_id': st.session_state.get('selected_regular_block_id'),
                'selected_unique_block_id': st.session_state.get('selected_unique_block_id')
            }
            if app_state:
                app_state.save_project()

            # === ДОБАВИТЬ СОХРАНЕНИЕ В ДОМЕН ===
            if 'domain_manager' not in st.session_state:
                st.session_state.domain_manager = DomainManager()

            # === КОНЕЦ ДОБАВЛЕНИЯ ===

            return True
    return False


def main(app_state=None, settings_mode=False, context=None):
    load_css()
    load_settings_from_file(app_state, context)

    if 'update_counter' not in st.session_state:
        st.session_state.update_counter = 0

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

        print(f"✅ Phase4 загружен домен из файла: {saved_domain}")

    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    st.info(f"🌐 Текущий домен: **{dm.get_domain_display_name()}**")
    # Загружаем данные фазы 4 из домена при первом входе
    if app_state:
        phase4_data = app_state.get_phase_data(4)
        if phase4_data and phase4_data.get('prompts'):
            st.session_state.phase4_generated_prompts = phase4_data.get('prompts', [])
        if phase4_data and phase4_data.get('char_settings'):
            st.session_state.phase4_char_settings = phase4_data.get('char_settings', {})
        if phase4_data and phase4_data.get('other_blocks_settings'):
            st.session_state.phase4_other_blocks_settings = phase4_data.get('other_blocks_settings', {})
        if phase4_data and phase4_data.get('selected_regular_block_id'):
            st.session_state.selected_regular_block_id = phase4_data.get('selected_regular_block_id')
        if phase4_data and phase4_data.get('selected_unique_block_id'):
            st.session_state.selected_unique_block_id = phase4_data.get('selected_unique_block_id')
    restore_ai_instructions(context)

    if 'ai_instruction_manager' in st.session_state:
        count = 0
        for b in st.session_state.ai_instruction_manager.instructions.values():
            for v in b.values():
                for c in v.values():
                    count += len(c.get('values', []))
    if 'phase4_global_prompts' in st.session_state:
        if not isinstance(st.session_state.phase4_global_prompts, (int, float)):
            try:
                st.session_state.phase4_global_prompts = 3
            except:
                st.session_state.phase4_global_prompts = 3

    if 'phase4_global_other_prompts' in st.session_state:
        if not isinstance(st.session_state.phase4_global_other_prompts, (int, float)):
            try:
                st.session_state.phase4_global_other_prompts = 20
            except:
                st.session_state.phase4_global_other_prompts = 20
        if 'phase4_generated_prompts' not in st.session_state:
            st.session_state.phase4_generated_prompts = []

    if 'phase4_global_prompts' not in st.session_state:
        st.session_state.phase4_global_prompts = 3
    else:
        # Убеждаемся, что это число
        if not isinstance(st.session_state.phase4_global_prompts, (int, float)):
            st.session_state.phase4_global_prompts = 3

    if 'phase4_global_other_prompts' not in st.session_state:
        st.session_state.phase4_global_other_prompts = 20
    else:
        if not isinstance(st.session_state.phase4_global_other_prompts, (int, float)):
            st.session_state.phase4_global_other_prompts = 20
    # ========== ИНИЦИАЛИЗАЦИЯ ВСЕХ ПЕРЕМЕННЫХ ==========
    if 'phase4_generated_prompts' not in st.session_state:
        st.session_state.phase4_generated_prompts = []

    if 'phase4_global_prompts' not in st.session_state:
        st.session_state.phase4_global_prompts = 3

    if 'phase4_char_settings' not in st.session_state:
        st.session_state.phase4_char_settings = {}

    if 'phase4_other_blocks_settings' not in st.session_state:
        st.session_state.phase4_other_blocks_settings = {}

    if 'phase4_page' not in st.session_state:
        st.session_state.phase4_page = 0

    if 'selected_regular_block_id' not in st.session_state:
        st.session_state.selected_regular_block_id = None

    if 'selected_unique_block_id' not in st.session_state:
        st.session_state.selected_unique_block_id = None

    if 'phase4_settings' not in st.session_state:
        st.session_state.phase4_settings = {}

    if not settings_mode:
        st.title("🚀 Фаза 4: Генерация промптов")
        st.markdown("---")
    else:
        st.markdown("### 🚀 Настройка промптов (Фаза 4)")
        st.caption("Настройте параметры генерации промптов для автоматического запуска")
        #st.info("💡 Настройки будут сохранены и применены при автоматическом запуске проекта")
        st.markdown("---")

        # Кнопки сохранения и назад
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Сохранить настройки фазы 4", type="primary", use_container_width=True):
                if save_phase4_settings(app_state):
                    st.success("✅ Настройки фазы 4 сохранены в проект!")
                else:
                    st.error("❌ Ошибка сохранения настроек")


        st.markdown("---")


    # --- Инициализация менеджеров ---
    if 'block_manager' not in st.session_state:
        st.session_state.block_manager = BlockManager()

    if 'variable_manager' not in st.session_state:
        st.session_state.variable_manager = VariableManager(st.session_state.block_manager)

    if 'dynamic_var_manager' not in st.session_state:
        st.session_state.dynamic_var_manager = DynamicVariableManager()

    if app_state:
        # Загружаем сохранённые настройки
        load_phase4_settings(app_state)

        # Восстанавливаем данные из app_data
        if 'phase4' in st.session_state.app_data:
            phase4_saved = st.session_state.app_data['phase4']
            if phase4_saved:
                if 'prompts' in phase4_saved and not st.session_state.phase4_generated_prompts:
                    st.session_state.phase4_generated_prompts = phase4_saved['prompts']
                    st.info(f"🔄 Восстановлено {len(phase4_saved['prompts'])} промптов из сохранённого проекта")
                if 'char_settings' in phase4_saved:
                    st.session_state.phase4_char_settings = phase4_saved['char_settings']
                if 'other_blocks_settings' in phase4_saved:
                    st.session_state.phase4_other_blocks_settings = phase4_saved['other_blocks_settings']

        st.session_state.current_phase = 4
        app_state.save_project()

    # Инициализация генератора
    if 'prompt_generator' not in st.session_state:
        st.session_state.prompt_generator = PromptGenerator(
            st.session_state.block_manager,
            st.session_state.variable_manager,
            st.session_state.dynamic_var_manager
        )

    if 'marker_rotator' not in st.session_state:
        st.session_state.marker_rotator = None

    # Инициализация переменных сессии
    if 'phase4_generated_prompts' not in st.session_state:
        st.session_state.phase4_generated_prompts = []

    if 'phase4_global_prompts' not in st.session_state:
        st.session_state.phase4_global_prompts = 3

    if 'phase4_char_settings' not in st.session_state:
        st.session_state.phase4_char_settings = {}

    if 'phase4_other_blocks_settings' not in st.session_state:
        st.session_state.phase4_other_blocks_settings = {}

    if 'phase4_page' not in st.session_state:
        st.session_state.phase4_page = 0

    # --- Загрузка данных из предыдущих фаз ---
    phase1_data = {}
    phase2_data = {}
    category = ""
    markers = []

    ctx_data = _get_context_data(context, st.session_state)

    # ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА
    if ctx_data['has_context'] and context is not None:
        phase1_data = context.get_phase_data(1) or {}
        phase2_data = context.get_phase_data(2) or {}
        category = phase1_data.get('category', '') or ctx_data.get('category', '')
        markers = phase2_data.get('markers', [])

    # ПРИОРИТЕТ 2: ИЗ APP_STATE
    if not phase1_data and 'app_data' in st.session_state:
        app_data = st.session_state.app_data
        phase1_data = app_data.get('phase1', {})
        phase2_data = app_data.get('phase2', {})
        category = phase1_data.get('category', '') or app_data.get('category', '')
        markers = phase2_data.get('markers', [])

    # ПРИОРИТЕТ 3: ИЗ SESSION_STATE
    if not phase1_data and 'phase1_data' in st.session_state:
        phase1_data = st.session_state.phase1_data
        category = phase1_data.get('category', '')

    if not phase2_data and 'phase2_data' in st.session_state:
        phase2_data = st.session_state.phase2_data
        markers = phase2_data.get('markers', [])

        if phase1_data:
            st.session_state.phase1_data = phase1_data
        if phase2_data:
            st.session_state.phase2_data = phase2_data

    elif 'phase1_data' in st.session_state and st.session_state.phase1_data:
        phase1_data = st.session_state.phase1_data
        category = phase1_data.get('category', '')

    if 'phase2_data' in st.session_state and st.session_state.phase2_data:
        phase2_data = st.session_state.phase2_data
        markers = phase2_data.get('markers', [])

    if not phase1_data or not phase1_data.get('characteristics'):
        st.error("""
        ## ❌ Данные фазы 1 не загружены
    
        Для работы фазы 4 необходимо выполнить фазу 1.
    
        **Решение:**
        1. Перейдите к фазе 1
        2. Загрузите JSON файл
        3. Выберите характеристики
        4. Нажмите "Сформировать итоговый массив"
        5. Вернитесь к фазе 4
        """)
        return

    # --- Боковая панель (только для обычного режима) ---
    if not settings_mode:
        with st.sidebar:
            st.header("⚙️ Настройки фазы 4")
            if st.button("🔄 Сбросить ротацию маркеров", use_container_width=True):
                if markers:
                    st.session_state.marker_rotator = MarkerRotator(markers)
                    st.success("Ротация маркеров сброшена!")
                    st.rerun()

            st.divider()
            st.header("🎲 Настройки рандомизации")

            randomization_mode = st.selectbox(
                "Режим выбора значений:",
                ["adaptive", "uniform", "weighted_only"],
                index=0,
                format_func=lambda x: {
                    "adaptive": "Адаптивный (учитывает использование)",
                    "uniform": "Равномерный (чистый рандом)",
                    "weighted_only": "Только по весам (старый режим)"
                }[x],
                help="Как выбирать значения переменных"
            )

            if st.session_state.prompt_generator.randomization_mode != randomization_mode:
                st.session_state.prompt_generator.randomization_mode = randomization_mode
                st.rerun()

            if st.button("🔄 Сбросить статистику использования", use_container_width=True):
                st.session_state.prompt_generator.reset_usage_tracking()
                st.success("Статистика использования сброшена!")
                st.rerun()

    # --- Основной контент (общий для обоих режимов) ---
    # В main() phase4.py, там где вызывается show_generation_mode:
    show_generation_mode(phase1_data, category, markers, settings_mode, app_state, context)

    if app_state:
        app_state.save_project()


if __name__ == "__main__":
    main()