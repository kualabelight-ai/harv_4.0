

import streamlit as st
import re
import json
from datetime import datetime
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import uuid
import time
from enum import Enum
from io import BytesIO
from styles import load_css
from domain_manager import DomainManager
import warnings
from pathlib import Path


# ==================== ЛОГИРОВАНИЕ ====================
def log(msg: str, level: str = "INFO"):
    """Логирование для отладки"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {level} | {msg}"
    print(log_line)

    if "phase7_logs" not in st.session_state:
        st.session_state.phase7_logs = []
    st.session_state.phase7_logs.append(log_line)
    if len(st.session_state.phase7_logs) > 100:
        st.session_state.phase7_logs = st.session_state.phase7_logs[-100:]
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
@dataclass
class TemplateVariant:
    name: str                     # "Основной", "Короткий", "С акциями" и т.д.
    order: List[str]              # порядок имён фрагментов
    is_default: bool = False
    description: str = ""
# ====================== ОСНОВНЫЕ СТРУКТУРЫ ДАННЫХ ======================
class ErrorType(Enum):
    MISSING_BRACKET = "missing_bracket"      # отсутствует [значение] в regular-блоке
    WRONG_BRACKET = "wrong_bracket"          # найдены другие скобки вместо ожидаемого значения
    UNKNOWN_VARIABLE = "unknown_variable"    # неизвестная переменная в non-regular блоке
    SPECIAL_SYMBOL = "special_symbol"        # нежелательный спецсимвол (можно использовать как предупреждение)
    GENERIC = "generic"
    MISSING_VARIABLE = "missing_variable"  # отсутствует {prop ...} в regular
    UNWANTED_BRACKETS = "unwanted_brackets"
    FORBIDDEN_MARKDOWN = "forbidden_markdown"
    DIGITS_FOUND = "digits_found"            # цифры после замены переменных
    WRONG_CITY_VARIABLE = "wrong_city_variable"  # {system город} вместо городе/по_городу
    AI_MARKER_WORD = "ai_marker_word"        # слова "Заголовок", "Описание" и т.п.
    DOUBLE_BRACKETS = "double_brackets"      # {{, }}, ((, ))
    INVALID_SYSTEM_VARIABLE = "invalid_system_variable"  # недопустимая {system ...}
    GOST_TU_OUTSIDE = "gost_tu_outside"      # ГОСТ/ТУ вне переменной
    FOREIGN_LANGUAGE = "foreign_language"    # слова на другом языке
    STOP_WORD_FOUND = "stop_word_found"      # стоп-слова
    # Ошибки HTML
    H2_IN_P_OR_UL = "h2_in_p_or_ul"          # <h2> внутри <p> или <ul>
    UL_WITHOUT_LIST_KEYWORD = "ul_without_list_keyword"  # список без указания в названии
    TEXT_STARTS_WITH_UL = "text_starts_with_ul"  # текст начинается с <ul>
    # общая ошибка
class TransformationType(Enum):
    VARIABLE_REPLACE = "variable_replace"
    UNIT_REMOVED = "unit_removed"
    SPECIAL_SYMBOL_REMOVED = "special_symbol_removed"
    AUTO_INSERT = "auto_insert"
    WARNING = "warning"
    ERROR = "error"
    MANUAL_CORRECTION = "manual_correction"
    HTML_GENERATION = "html_generation"
    POSTPROCESSING = "postprocessing"


class SeverityLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"

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
@dataclass
class TextTransformation:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    block_id: str = ""
    fragment_name: str = ""
    transformation_type: TransformationType = TransformationType.MANUAL_CORRECTION
    original: str = ""
    result: str = ""
    start: int = -1
    end: int = -1
    meta: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    severity: SeverityLevel = SeverityLevel.INFO
    user: str = "system"

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'block_id': self.block_id,
            'fragment_name': self.fragment_name,
            'transformation_type': self.transformation_type.value,
            'original': self.original,
            'result': self.result,
            'start': self.start,
            'end': self.end,
            'meta': self.meta,
            'timestamp': self.timestamp.isoformat(),
            'severity': self.severity.value,
            'user': self.user
        }


class TransformationRegistry:
    def __init__(self):
        self.transformations: List[TextTransformation] = []
        self._block_index: Dict[str, List[TextTransformation]] = defaultdict(list)
        self._fragment_index: Dict[str, List[TextTransformation]] = defaultdict(list)

    def add(self, transformation: TextTransformation):
        self.transformations.append(transformation)
        self._block_index[transformation.block_id].append(transformation)
        self._fragment_index[transformation.fragment_name].append(transformation)

    def get_by_block_id(self, block_id: str) -> List[TextTransformation]:
        return self._block_index.get(block_id, [])

    def get_by_fragment(self, fragment_name: str) -> List[TextTransformation]:
        return self._fragment_index.get(fragment_name, [])

    def get_errors(self) -> List[TextTransformation]:
        return [t for t in self.transformations if t.severity == SeverityLevel.ERROR]

    def get_warnings(self) -> List[TextTransformation]:
        return [t for t in self.transformations if t.severity == SeverityLevel.WARNING]

    def clear(self):
        self.transformations.clear()
        self._block_index.clear()
        self._fragment_index.clear()


class VariableManager:
    def __init__(self):
        self.prefixes = {"prop": "prop", "system": "system", "fragment": "fragment"}

        self.system_vars = {
            "город": {
                "variants": ["{system город}", "{system городе}", "{system по_городу}"],
                "description": "Название города с вариантами падежей"
            },
            "название товара": {
                "variants": ["{system название_категории} {system название_товара}"],
                "description": "Название товара"
            },
            "цена": {
                "variants": ["{system цена_товара}, руб."],
                "description": "Цена товара"
            },
            "единица измерения": {
                "variants": ["{system количество}"],
                "description": "Единица измерения"
            },
            "телефон": {
                "variants": ["8 495 969-51-08"],
                "description": "Телефон компании"
            },
            "email": {
                "variants": ["msk@steelborg.ru"],
                "description": "Email компании"
            },
            "компания": {
                "variants": ["Steelborg"],
                "description": "Название компании"
            },
            "категория РП": {
                "variants": ["{system название_категории_РП}"],
                "description": "Категория в родительном падеже"
            },
            "категория ВП": {
                "variants": ["{system название_категории_ВП}"],
                "description": "Категория в винительном падеже"
            },
            "категория ИП": {
                "variants": ["{system название_категории}"],
                "description": "Категория в именительном падеже"
            },
            "сайт": {
                "variants": ["steelborg.ru"],
                "description": "Сайт компании"
            },
            "адрес": {
                "variants": ["г. Москва, ул. Примерная, д. 1"],
                "description": "Адрес компании"
            },
            "рабочие часы": {
                "variants": ["пн-пт с 9:00 до 18:00"],
                "description": "Рабочие часы"
            }

        }
        self.city_rules = {
            "в {system город}": "в {system городе}",
            "по {system город}": "по {system по_городу}"
        }

    def get_variable_suggestions(self) -> List[Dict]:
        suggestions = []
        for name, data in self.system_vars.items():
            for variant in data.get("variants", []):
                suggestions.append({
                    "type": "system",
                    "name": name,
                    "value": variant,
                    "description": data.get("description", f"Системная переменная: {name}")
                })
        suggestions.extend([
            {"type": "prop", "name": "prop", "value": "{prop }", "description": "Свойство характеристики"},
            {"type": "fragment", "name": "fragment", "value": "{fragment }", "description": "Фрагмент текста"}
        ])
        return suggestions

    def format_variable(self, var_type: str, var_name: str) -> str:
        if var_type == "system":
            return f"{{{self.prefixes['system']} {var_name}}}"
        elif var_type == "prop":
            return f"{{{self.prefixes['prop']} {var_name}}}"
        elif var_type == "fragment":
            return f"{{{self.prefixes['fragment']} {var_name}}}"
        return var_name


@dataclass
class FragmentBlock:
    id: str
    fragment_name: str
    original_text: str
    processed_text: str
    block_type: str
    html_text: str = ""
    characteristic_name: Optional[str] = None
    characteristic_value: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)  # каждый элемент: {'type': ErrorType, 'message': str}
    manually_fixed: bool = False
    warnings: List[str] = field(default_factory=list)
    status: str = "pending"
    manual_correction: Optional[str] = None
    auto_corrected: bool = False
    added_value: Optional[str] = None
    special_symbols: List[Tuple[str, int, int]] = field(default_factory=list)
    last_modified: datetime = field(default_factory=datetime.now)
    units_removed: List[str] = field(default_factory=list)
    symbols_removed: List[str] = field(default_factory=list)
    html_generated: bool = False

    def to_dict(self):
        return {
            'id': self.id,
            'fragment_name': self.fragment_name,
            'original_text': self.original_text,
            'processed_text': self.processed_text,
            'html_text': self.html_text,
            'block_type': self.block_type,
            'characteristic_name': self.characteristic_name,
            'characteristic_value': self.characteristic_value,
            'errors': self.errors,  # теперь это список словарей, сериализуется нормально
            'manually_fixed': self.manually_fixed,
            'warnings': self.warnings,
            'status': self.status,
            'manual_correction': self.manual_correction,
            'auto_corrected': self.auto_corrected,
            'added_value': self.added_value,
            'special_symbols': self.special_symbols,
            'last_modified': self.last_modified.isoformat()
        }


class FragmentManager:

    def __init__(self, category: str):
        self.category = category
        self.fragments: List[FragmentBlock] = []
        self.fragment_names: set = set()
        self.fragment_properties: Dict[str, List[Dict]] = defaultdict(list)
        self.category_code: str = category or "Без_кода"
        self.templates: Dict[str, TemplateVariant] = {}

    def add_block(self, block_data: Dict) -> FragmentBlock:
        fragment_block = FragmentBlock(
            id=block_data.get('id', str(uuid.uuid4())),
            fragment_name=block_data['fragment_name'],
            original_text=block_data.get('original_text', ''),
            processed_text=block_data.get('processed_text', ''),
            block_type=block_data.get('block_type', 'unknown'),
            html_text=block_data.get('html_text', ''),
            characteristic_name=block_data.get('characteristic_name'),
            characteristic_value=block_data.get('characteristic_value'),
            errors=block_data.get('errors', []),
            warnings=block_data.get('warnings', []),
            status=block_data.get('status', 'pending'),
            auto_corrected=block_data.get('auto_corrected', False),
            added_value=block_data.get('added_value'),
            special_symbols=block_data.get('special_symbols', [])
        )
        self.fragments.append(fragment_block)
        self.fragment_names.add(fragment_block.fragment_name)
        self._extract_properties(fragment_block)
        return fragment_block

    def _extract_properties(self, fragment: FragmentBlock):
        if fragment.block_type == 'regular' and fragment.characteristic_name:
            self.fragment_properties[fragment.fragment_name].append({
                'characteristic': fragment.characteristic_name,
                'value': None,
                'is_unique': False
            })
        elif fragment.block_type == 'unique' and fragment.characteristic_name and fragment.characteristic_value:
            self.fragment_properties[fragment.fragment_name].append({
                'characteristic': fragment.characteristic_name,
                'value': fragment.characteristic_value,
                'is_unique': True
            })

    def rename_fragment(self, old_name: str, new_name: str) -> bool:
        if old_name not in self.fragment_names:
            return False
        for fragment in self.fragments:
            if fragment.fragment_name == old_name:
                fragment.fragment_name = new_name
        self.fragment_names.remove(old_name)
        self.fragment_names.add(new_name)
        if old_name in self.fragment_properties:
            self.fragment_properties[new_name] = self.fragment_properties.pop(old_name)
        if old_name in self.template_order:
            self.template_order[self.template_order.index(old_name)] = new_name
        return True

    def get_fragment_blocks(self, fragment_name: str) -> List[FragmentBlock]:
        return [f for f in self.fragments if f.fragment_name == fragment_name]

    def get_all_properties(self) -> List[Dict]:
        props = []
        for frag_name in sorted(self.fragment_names):
            for prop in self.fragment_properties.get(frag_name, []):
                props.append({
                    'fragment_name': frag_name,
                    'characteristic': prop['characteristic'],
                    'value': prop['value'],
                    'is_unique': prop['is_unique']
                })
        return props

    def get_default_template(self) -> Optional[Dict]:
        for tpl in self.templates.values():
            if tpl.is_default:
                return {
                    'category_code': self.category_code,
                    'template_name': tpl.name,
                    'template': " ".join(f"{{fragment {f}}}" for f in tpl.order),
                    'fragment_variables': {f: f"{{fragment {f}}}" for f in self.fragment_names},
                    'order': tpl.order,
                    'is_default': True
                }
        # если нет дефолтного — берём первый
        if self.templates:
            first = next(iter(self.templates.values()))
            return {
                'category_code': self.category_code,
                'template_name': first.name,
                'template': " ".join(f"{{fragment {f}}}" for f in first.order),
                'fragment_variables': {f: f"{{fragment {f}}}" for f in self.fragment_names},
                'order': first.order,
                'is_default': False
            }
        return None

    def add_template(self, name: str, order: List[str], description: str = "", set_as_default: bool = False):
        if name in self.templates:
            name = f"{name}_{len(self.templates)+1}"
        self.templates[name] = TemplateVariant(
            name=name,
            order=order,
            description=description,
            is_default=set_as_default
        )
        if set_as_default:
            for tpl in self.templates.values():
                tpl.is_default = (tpl.name == name)
        self.category_code = st.session_state.get('category_code', self.category_code)

    def set_default_template(self, template_name: str):
        if template_name in self.templates:
            for tpl in self.templates.values():
                tpl.is_default = (tpl.name == template_name)

    def delete_template(self, template_name: str):
        if template_name in self.templates:
            was_default = self.templates[template_name].is_default
            del self.templates[template_name]
            if was_default and self.templates:
                next(iter(self.templates.values())).is_default = True

    def update_block(self, block_id: str, updates: Dict) -> bool:
        for fragment in self.fragments:
            if fragment.id == block_id:
                for key, value in updates.items():
                    if hasattr(fragment, key):
                        setattr(fragment, key, value)
                fragment.last_modified = datetime.now()
                return True
        return False

    def delete_block(self, block_id: str) -> bool:
        for i, fragment in enumerate(self.fragments):
            if fragment.id == block_id:
                del self.fragments[i]
                if not any(f.fragment_name == fragment.fragment_name for f in self.fragments):
                    self.fragment_names.discard(fragment.fragment_name)
                return True
        return False


class EnhancedTextProcessor:
    def __init__(self, variable_manager: VariableManager):
        self.vm = variable_manager
        self.pattern = re.compile(r'\[([^\]]+)\]')
        self.special_symbols_pattern = re.compile(r'[<>{}|\\^`~!@#$%^&*()_\+=\[\]\'":;?/]')
        self.units_to_remove = [
            "мм", "метр", "м", "см", "дм", "км", "миллиметр", "сантиметр", "дециметр", "километр",
            "кг", "г", "мг", "тонна", "т", "грамм", "миллиграмм", "килограмм",
            "л", "мл", "литр", "миллилитр", "шт", "штук", "штука", "штуки",
            "кг/м", "г/см³", "г/см3", "кг/м³", "кг/м3", "°C", "°F", "град", "градус", "градусов", "дюйм"
        ]
        self.instruction_keywords = [
            "инструкция:", "промпт:", "введите:", "создайте:", "напишите:",
            "instruction:", "prompt:", "write:", "create:", "generate:",
            "опишите:", "сформулируйте:", "составьте:", "подготовьте:"
        ]
    def process_product_with_category(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Обрабатывает переменную товара, добавляя перед ней системную переменную категории
        {system название_товара} -> {system название_категории} {system название_товара}
        """
        errors = []
        processed_text = text

        # Ищем {system название_товара}
        product_pattern = r'\{system\s+название_товара\}'

        if re.search(product_pattern, processed_text):
            # Проверяем, нет ли уже категории перед товаром
            # Ищем паттерн: {system название_категории} {system название_товара}
            already_has_category = re.search(
                r'\{system\s+название_категории[^}]*\}\s*\{system\s+название_товара\}',
                processed_text
            )

            if not already_has_category:
                # Заменяем {system название_товара} на "{system название_категории} {system название_товара}"
                processed_text = re.sub(
                    product_pattern,
                    r'{system название_категории} {system название_товара}',
                    processed_text
                )

                # Добавляем информацию о трансформации
                errors.append({
                    'type': 'auto_insert',
                    'message': 'Автоматически добавлена системная переменная категории перед товаром',
                    'severity': 'info'
                })

        return processed_text, errors
    def fix_punctuation(self, text: str) -> str:
        """Исправляет типичные пунктуационные ошибки + двойные точки."""
        if not text:
            return text

        # Убираем лишние пробелы
        text = re.sub(r' {2,}', ' ', text)

        # Пробел перед запятой
        text = re.sub(r'\s+,', ',', text)

        # Запятая + пробел
        text = re.sub(r',(?!\s)(?=\S)', ', ', text)

        # === ОСНОВНЫЕ ИСПРАВЛЕНИЯ ДЛЯ ТВОЕЙ ПРОБЛЕМЫ ===
        text = re.sub(r'\.{2,}', '.', text)           # .. → .
        text = re.sub(r'!\.{1,}', '!', text)          # !. → !
        text = re.sub(r'\?\.{1,}', '?', text)         # ?. → ?
        text = re.sub(r'\s+\.', '.', text)            # "слово ." → "слово."
        text = re.sub(r'\.\s+\.', '.', text)          # ". ." → "."

        # Длинные тире
        text = text.replace('—', '-').replace('–', '-')

        # Убираем пробелы в начале/конце
        text = text.strip()

        return text

    def process_city_variable(self, text: str) -> Tuple[str, List[Dict]]:

        errors = []
        processed_text = text

        if not text:
            return processed_text, errors

        # Более гибкие замены
        replacements = [
            (r'в\s*\{system\s*город\}', 'в {system городе}'),
            (r'по\s*\{system\s*город\}', 'по {system по_городу}'),
            (r'(?<!\w)\{system\s*город\}(?!\w)', '{system городе}'),  # изолированный
            (r'\{system\s+городе\}', '{system городе}'),             # нормализация
            (r'\{system\s+по_городу\}', '{system по_городу}'),
        ]

        for pattern, replacement in replacements:
            if re.search(pattern, processed_text, re.IGNORECASE):
                old = processed_text
                processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
                if old != processed_text:
                    errors.append({
                        'type': 'auto_insert',
                        'message': f'Исправлена переменная города: {replacement}',
                        'severity': 'info'
                    })

        return processed_text, errors

    def check_city_variables(self, text: str) -> List[Dict]:
        """
        Проверяет наличие необработанных переменных города
        """
        errors = []

        # Ищем {system город} без обработки
        if re.search(r'\{system\s+город\}', text):
            errors.append({
                'type': ErrorType.UNKNOWN_VARIABLE.value,
                'message': 'Обнаружена необработанная переменная {system город}. '
                           'Используйте "в {system город}" или "по {system по_городу}"'
            })

        return errors
    def _get_numeric_variants(self, value: str) -> List[str]:
        """Если value похоже на число с плавающей точкой, возвращает варианты с точкой и запятой."""
        if re.match(r'^\d+[.,]\d+$', value):
            if '.' in value:
                other = value.replace('.', ',')
            else:
                other = value.replace(',', '.')
            return [value, other]
        return [value]

    def check_regular_brackets(self, text: str, expected_value: str) -> List[Dict]:
        if not expected_value:
            return []

        # После замены переменных, ищем {prop ...} вместо [значение]
        # Но в processed_text уже могут быть и те, и другие

        # Проверяем наличие значения в квадратных скобках
        variants = self._get_numeric_variants(expected_value)
        for val in variants:
            pattern = r'\[' + re.escape(val) + r'\]'
            if re.search(pattern, text):
                return []

        # Если нет квадратных скобок, проверяем наличие {prop ...}
        if re.search(r'\{prop\s+[^}]+\}', text):
            return []  # Есть переменная - это ок

        # Если есть другие квадратные скобки
        if self.pattern.search(text):
            return [{'type': ErrorType.WRONG_BRACKET.value,
                     'message': f"В regular-блоке ожидается значение [{expected_value}], но найдены другие скобки"}]
        else:
            return [{'type': ErrorType.MISSING_BRACKET.value,
                     'message': f"В regular-блоке отсутствует значение [{expected_value}]"}]
    # --------------------------------------------------------------
    #  ЗАМЕНА ПЕРЕМЕННЫХ (ТОЛЬКО ЗАМЕНА, БЕЗ АВТОДОБАВЛЕНИЯ)
    # --------------------------------------------------------------
    def replace_variables(self, text: str, block_type: str,
                          char_name: Optional[str] = None,
                          char_value: Optional[str] = None) -> Dict:
        """
        Заменяет выражения [variable] на соответствующие переменные.
        НЕ добавляет автоматически новые скобки.
        Для non-regular блоков, если переменная не найдена, заменяет на {system var_name} и добавляет ошибку.
        """
        errors = []
        warnings = []
        special_symbols = self._find_special_symbols(text)


        matches = list(self.pattern.finditer(text))
        processed_text = text
        offset = 0
        replacements = []
        if '{system название_товара}' in processed_text:
            processed_text, _ = self.process_product_with_category(processed_text)
        for match in matches:
            var_name = match.group(1).strip()
            start, end = match.span()

            if block_type == 'regular':
                # Для regular блока заменяем на {prop ...}
                replacement = f"{{prop {char_name if char_name else var_name}}}"
            else:
                # Для non-regular пытаемся найти системную переменную
                var_lower = var_name.lower()
                found = False
                replacement = None
                for sys_var, data in self.vm.system_vars.items():
                    if sys_var.lower() == var_lower:
                        replacement = data['variants'][0]
                        found = True
                        break
                if not found:
                    replacement = match.group()

            new_start = start + offset
            new_end = end + offset
            processed_text = processed_text[:new_start] + replacement + processed_text[new_end:]
            offset += len(replacement) - (end - start)

            replacements.append({
                'original': match.group(),
                'replacement': replacement,
                'position': (start, end)
            })

        return {
            'processed_text': processed_text,
            'replacements': replacements,
            'errors': errors,
            'warnings': warnings,
            'special_symbols': special_symbols
        }

    def normalize_text(self, text: str) -> str:
        """Замена ё на е."""
        return text.replace('ё', 'е').replace('Ё', 'Е')
    # --------------------------------------------------------------
    #  АВТОМАТИЧЕСКОЕ ДОБАВЛЕНИЕ СКОБОК (ТОЛЬКО ДЛЯ REGULAR)
    # --------------------------------------------------------------
    # --------------------------------------------------------------
    #  АВТОМАТИЧЕСКОЕ ДОБАВЛЕНИЕ СКОБОК (ТОЛЬКО ДЛЯ REGULAR)
    # --------------------------------------------------------------
    def auto_insert_bracket(self, text: str, char_value: str) -> Tuple[str, bool, Optional[str], bool]:
        """
        Возвращает: (новый_текст, был_ли_изменен, найденное_значение, есть_ошибка)
        """
        if not char_value:
            return text, False, None, False

        if self.pattern.search(text):  # если уже есть скобки []
            return text, False, None, False

        variants = self._get_numeric_variants(char_value)
        for val in variants:
            escaped = re.escape(val)
            pattern = r'\b' + escaped + r'\b'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start, end = match.span()
                new_text = text[:start] + '[' + text[start:end] + ']' + text[end:]
                return new_text, True, text[start:end], False

        # Значение не найдено - возвращаем ошибку, текст не меняем
        return text, False, None, True

    # --------------------------------------------------------------
    #  ПРОВЕРКА ОТСУТСТВИЯ СКОБОК (ДЛЯ REGULAR)
    # --------------------------------------------------------------


    # --------------------------------------------------------------
    #  УДАЛЕНИЕ ЕДИНИЦ
    # --------------------------------------------------------------
    def remove_units(self, text: str, units_list: List[str]) -> Tuple[str, List[str]]:
        removed = []
        cleaned = text
        for unit in units_list:
            # Если единица короткая (<=2 символов) или содержит не только буквы, ищем точно
            if len(unit) <= 2 or not re.match(r'^[а-яё]+$', unit, re.IGNORECASE):
                pattern = r'\b' + re.escape(unit.lower()) + r'\b'
            else:
                # Строим регулярку: основа + возможные окончания
                endings = ['', 'а', 'у', 'ом', 'е', 'ы', 'ов', 'ам', 'ами', 'ах']
                base = re.escape(unit.lower())
                endings_pattern = '(?:' + '|'.join(re.escape(e) for e in endings) + ')'
                pattern = r'\b' + base + endings_pattern + r'\b'
            # Ищем все вхождения и удаляем
            for m in reversed(list(re.finditer(pattern, cleaned, re.IGNORECASE))):
                cleaned = cleaned[:m.start()] + cleaned[m.end():]
                removed.append(unit)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned, removed

    # --------------------------------------------------------------
    #  УДАЛЕНИЕ СПЕЦСИМВОЛОВ
    # --------------------------------------------------------------
    def remove_special_symbols(self, text: str, symbols_to_remove: List[str]) -> Tuple[str, List[str], List[Tuple[str, int, int]]]:
        removed = []
        cleaned = text
        for symbol in symbols_to_remove:
            escaped = re.escape(symbol)
            pattern = escaped
            for m in reversed(list(re.finditer(pattern, cleaned))):
                cleaned = cleaned[:m.start()] + cleaned[m.end():]
                removed.append(symbol)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        new_special_symbols = self._find_special_symbols(cleaned)
        return cleaned, removed, new_special_symbols

    # --------------------------------------------------------------
    #  ПОИСК СПЕЦСИМВОЛОВ
    # --------------------------------------------------------------
    def _find_special_symbols(self, text: str) -> List[Tuple[str, int, int]]:
        specials = []
        for match in self.special_symbols_pattern.finditer(text):
            symbol = match.group()
            # Исключаем разрешённые символы: [ ] , . - _ пробел и табуляция
            # и ДОБАВЛЯЕМ { } в список разрешённых!
            if symbol not in ['[', ']', '{', '}', ',', '.', '-', '_', ' ', '\t', '\n']:
                specials.append((symbol, match.start(), match.end()))
        return specials

    # --------------------------------------------------------------
    #  ГЕНЕРАЦИЯ HTML
    # --------------------------------------------------------------
    def convert_to_html(self, text: str, block_id: str = None) -> Tuple[str, List[Dict]]:
        """
        Конвертирует текст в HTML.
        Возвращает: (html_текст, список_ошибок)
        """
        if not text:
            return "", []

        errors = []
        lines = text.split('\n')
        html_lines = []
        in_list = False
        list_type = None  # 'ul' или 'ol'

        for line_num, line in enumerate(lines):
            line = line.rstrip()

            # Пропускаем пустые строки
            if not line:
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                continue

            # Проверка на запрещённое форматирование (** и * не для списков)
            if re.search(r'(?<!^)\*\*', line) or re.search(r'(?<!^)\*[^*]', line):
                if not re.match(r'^\s*\*\s+', line):
                    errors.append({
                        'type': ErrorType.FORBIDDEN_MARKDOWN.value,
                        'message': f"Найдено запрещённое форматирование '*': строка {line_num + 1}",
                        'line': line_num + 1,
                        'text': line[:50] + '...' if len(line) > 50 else line
                    })

            # --- ИСПРАВЛЕНО: обработка h2 с последующим текстом ---
            h2_match = re.match(r'^(<h2>.*?</h2>)(.*)$', line, re.IGNORECASE | re.DOTALL)
            if h2_match:
                # Закрываем предыдущий список если был
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None

                # Добавляем h2 как есть
                h2_part = h2_match.group(1).strip()
                html_lines.append(h2_part)

                # Обрабатываем остаток строки после h2
                rest_part = h2_match.group(2).strip()
                if rest_part:
                    # Проверяем наличие маркеров списка (* или -)
                    if '* ' in rest_part or '- ' in rest_part:
                        # Определяем, какой маркер используется
                        if '* ' in rest_part:
                            marker = '* '
                        else:
                            marker = '- '

                        # Разбиваем по маркеру
                        parts = rest_part.split(marker)
                        first_part = parts[0].strip()
                        list_items = [p.strip() for p in parts[1:] if p.strip()]

                        # Убираем возможные точки в конце элементов
                        list_items = [item.rstrip('.') for item in list_items]

                        if first_part:
                            html_lines.append(f'<p>{first_part}</p>')

                        if list_items:
                            html_lines.append('<ul>')
                            for item in list_items:
                                html_lines.append(f'<li>{item}</li>')
                            html_lines.append('</ul>')
                    else:
                        # Просто текст
                        html_lines.append(f'<p>{rest_part}</p>')
                continue

            # Если строка уже содержит HTML-тег - пропускаем
            if re.match(r'^\s*<[a-z][a-z0-9]*[^>]*>.*</[a-z][a-z0-9]*>\s*$', line, re.IGNORECASE):
                if not line.strip().startswith('<h2>'):
                    html_lines.append(line)
                continue

            # --- ИСПРАВЛЕНО: обработка inline-списка с маркерами * или - ---
            # Ищем маркеры в строке (* или - с пробелом)
            markers = []
            if '* ' in line:
                markers.append('* ')
            if '- ' in line:
                markers.append('- ')

            if markers and (line.count('* ') + line.count('- ')) >= 2:  # минимум 2 маркера = 3+ элемента
                # Используем первый найденный маркер
                marker = markers[0]
                parts = line.split(marker)

                if in_list:
                    # Добавляем все части как элементы списка
                    for part in parts:
                        if part.strip():
                            # Убираем точку в конце если есть
                            clean_part = part.strip().rstrip('.')
                            html_lines.append(f'<li>{clean_part}</li>')
                else:
                    # Создаём новый список
                    if len(parts) >= 2:
                        first_part = parts[0].strip()
                        rest_parts = [p.strip().rstrip('.') for p in parts[1:] if p.strip()]

                        # Проверяем, является ли первый элемент вводным текстом
                        intro_indicators = [
                            'такой', 'следующий', 'ниже', ':', 'это', 'включает',
                            'предлагаем', 'обеспечивает', 'предоставляет', 'включает',
                            'состоит', 'имеет', 'представлен', 'доступен'
                        ]

                        # Если первый элемент заканчивается на : или содержит ключевые слова
                        is_intro = (first_part.endswith(':') or
                                    any(ind in first_part.lower() for ind in intro_indicators))

                        if is_intro and len(first_part) < 150:  # вводный текст
                            html_lines.append(f'<p>{first_part}</p>')
                            if rest_parts:
                                html_lines.append('<ul>')
                                for part in rest_parts:
                                    if part:
                                        html_lines.append(f'<li>{part}</li>')
                                html_lines.append('</ul>')
                        else:
                            # Все части - элементы списка (включая первую)
                            all_items = [first_part] + rest_parts if first_part else rest_parts
                            all_items = [item for item in all_items if item]

                            if all_items:
                                html_lines.append('<ul>')
                                for item in all_items:
                                    html_lines.append(f'<li>{item}</li>')
                                html_lines.append('</ul>')
                continue

            # Обычный текст
            else:
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None

                html_lines.append(f'<p>{line}</p>')

        # Закрываем список, если остался открытым
        if in_list:
            html_lines.append(f'</{list_type}>')
        html_lines.append('<br>')

        return '\n'.join(html_lines), errors

    # --------------------------------------------------------------
    #  УПРАВЛЕНИЕ СПИСКОМ ЕДИНИЦ
    # --------------------------------------------------------------
    def add_unit_to_remove(self, unit: str):
        if unit and unit not in self.units_to_remove:
            self.units_to_remove.append(unit)

    def remove_unit_from_list(self, unit: str):
        if unit in self.units_to_remove:
            self.units_to_remove.remove(unit)

    def find_units_in_text(self, text: str) -> List[str]:
        found = set()
        text_lower = text.lower()
        # Окончания для существительных (мужской род, множественное число и т.п.)
        endings = ['', 'а', 'у', 'ом', 'е', 'ы', 'ов', 'ам', 'ами', 'ах']
        for unit in self.units_to_remove:
            # Если единица короткая (<=2 символов) или содержит не только буквы, ищем точно
            if len(unit) <= 2 or not re.match(r'^[а-яё]+$', unit, re.IGNORECASE):
                pattern = r'\b' + re.escape(unit.lower()) + r'\b'
            else:
                # Строим регулярку: основа + возможные окончания
                base = re.escape(unit.lower())
                endings_pattern = '(?:' + '|'.join(re.escape(e) for e in endings) + ')'
                pattern = r'\b' + base + endings_pattern + r'\b'
            if re.search(pattern, text_lower):
                found.add(unit)
        return sorted(found)
    def check_digits_after_replacement(self, text: str) -> List[Dict]:
        """Проверяет наличие цифр после замены переменных (исключая HTML-теги)"""
        errors = []

        # Удаляем HTML-теги перед проверкой цифр
        text_without_tags = re.sub(r'<[^>]+>', ' ', text)

        # Ищем любые цифры (включая десятичные дроби и числа)
        digit_pattern = r'\d+'
        matches = re.finditer(digit_pattern, text_without_tags)

        for match in matches:
            # Получаем позицию в исходном тексте (приблизительно)
            digit = match.group()
            errors.append({
                'type': ErrorType.DIGITS_FOUND.value,
                'message': f'Найдены цифры "{digit}" после замены переменных',
                'position': (match.start(), match.end())
            })
        return errors

    def check_wrong_city_variable(self, text: str) -> List[Dict]:
        """Проверяет наличие необработанной переменной {system город}"""
        errors = []
        # Ищем {system город} (без предлогов)
        pattern = r'\{system\s+город\}'
        if re.search(pattern, text):
            errors.append({
                'type': ErrorType.WRONG_CITY_VARIABLE.value,
                'message': 'Обнаружена {system город}. Используйте {system городе} или {system по_городу}'
            })
        return errors

    def check_ai_marker_words(self, text: str) -> List[Dict]:
        """Проверяет наличие слов-маркеров ИИ"""
        errors = []
        markers = [
            r'(?i)^заголовок[:.\s]',
            r'(?i)^описание[:.\s]',
            r'(?i)^вот вам заключение',
            r'(?i)^вот вам описание',
            r'(?i)^текст применения',
            r'(?i)^заключение[:.\s]',
            r'(?i)^применение[:.\s]',
            r'(?i)^характеристики[:.\s]',
            r'(?i)^список[:.\s]',
            r'(?i)^блок[:.\s]',
            r'(?i)^фрагмент[:.\s]',
        ]
        for marker in markers:
            if re.search(marker, text):
                errors.append({
                    'type': ErrorType.AI_MARKER_WORD.value,
                    'message': f'Найдено слово-маркер ИИ: "{marker.strip("()?i ")}"'
                })
                break  # достаточно одного
        return errors

    def check_double_brackets(self, text: str) -> List[Dict]:
        """Проверяет наличие двойных скобок"""
        errors = []
        patterns = [
            (r'{{', '{{'),
            (r'}}', '}}'),
            (r'\(\(', '(('),
            (r'\)\)', '))'),
        ]
        for pattern, bracket_type in patterns:
            if re.search(pattern, text):
                errors.append({
                    'type': ErrorType.DOUBLE_BRACKETS.value,
                    'message': f'Найдены двойные скобки "{bracket_type}"'
                })
        return errors

    def check_invalid_system_variables(self, text: str, valid_system_vars: List[str]) -> List[Dict]:
        """Проверяет наличие недопустимых системных переменных"""
        errors = []
        # Ищем все {system ...}
        pattern = r'\{system\s+([^}]+)\}'
        matches = re.finditer(pattern, text)
        for match in matches:
            var_name = match.group(1).strip()
            # Проверяем, есть ли в списке допустимых
            if var_name not in valid_system_vars:
                errors.append({
                    'type': ErrorType.INVALID_SYSTEM_VARIABLE.value,
                    'message': f'Недопустимая системная переменная: {{system {var_name}}}',
                    'var_name': var_name
                })
        return errors

    def check_square_brackets(self, text: str) -> List[Dict]:
        """Проверяет наличие квадратных скобок после замены переменных"""
        errors = []
        if '[' in text or ']' in text:
            errors.append({
                'type': ErrorType.UNWANTED_BRACKETS.value,
                'message': 'Найдены квадратные скобки [...] после замены переменных'
            })
        return errors

    def check_gost_tu_outside(self, text: str) -> List[Dict]:
        """Проверяет наличие ГОСТ/ТУ вне переменных"""
        errors = []
        # Ищем ГОСТ и ТУ паттерны
        patterns = [
            r'(?i)\bгост\b',   # ГОСТ как отдельное слово
            r'(?i)\bту\b',     # ТУ как отдельное слово
        ]
        for pattern in patterns:
            if re.search(pattern, text):
                errors.append({
                    'type': ErrorType.GOST_TU_OUTSIDE.value,
                    'message': 'Найден ГОСТ/ТУ вне переменной. Используйте {prop название_гост} или оберните в переменную'
                })
                break
        return errors

    def check_foreign_language(self, text: str) -> List[Dict]:
        """Проверяет наличие слов на другом языке (латиница), исключая содержимое переменных {...}"""
        errors = []

        # Сначала удаляем все переменные {prop ...} и {system ...} и {fragment ...}
        # Заменяем их на пустую строку или плейсхолдер
        text_without_vars = re.sub(r'\{[^}]+\}', ' ', text)

        # Исключаем распространённые технические аббревиатуры
        exclude_pattern = r'(?i)^(html|css|json|xml|pdf|doc|txt|url|id|sku|upc|ean|gtin|http|https|www|com|ru|en|de|fr|it|es|pt|system|prop|fragment)$'

        latin_word_pattern = r'\b[a-zA-Z]{3,}\b'
        matches = re.finditer(latin_word_pattern, text_without_vars)

        for match in matches:
            word = match.group()
            # Пропускаем аббревиатуры и зарезервированные слова
            if re.match(exclude_pattern, word, re.IGNORECASE):
                continue
            errors.append({
                'type': ErrorType.FOREIGN_LANGUAGE.value,
                'message': f'Найдено слово на другом языке: "{word}"'
            })
        return errors

    def check_special_symbols_separate(self, text: str, symbols: List[str] = None) -> List[Dict]:
        """Проверка на спецсимволы * и #"""
        if symbols is None:
            symbols = ['*', '#']
        errors = []
        for symbol in symbols:
            if symbol in text:
                # Проверяем, не внутри ли переменной
                # Простая проверка: ищем символ не внутри {}
                in_bracket = False
                bracket_depth = 0
                for i, ch in enumerate(text):
                    if ch == '{':
                        bracket_depth += 1
                    elif ch == '}':
                        bracket_depth -= 1
                    elif ch == symbol and bracket_depth == 0:
                        errors.append({
                            'type': ErrorType.SPECIAL_SYMBOL.value,
                            'message': f'Найден спецсимвол "{symbol}" вне переменной'
                        })
                        break
        return errors
    def validate_html_structure(self, html: str, fragment_name: str) -> List[Dict]:
        """Проверяет структуру HTML после генерации"""
        errors = []

        # 1. Проверка <h2> внутри <p> или <ul>
        if re.search(r'<p[^>]*>.*?<h2', html, re.IGNORECASE | re.DOTALL):
            errors.append({
                'type': ErrorType.H2_IN_P_OR_UL.value,
                'message': '<h2> находится внутри <p>'
            })

        if re.search(r'<ul[^>]*>.*?<h2', html, re.IGNORECASE | re.DOTALL):
            errors.append({
                'type': ErrorType.H2_IN_P_OR_UL.value,
                'message': '<h2> находится внутри <ul>'
            })

        # 2. Списки без указания в названии
        if '<ul>' in html and 'список' not in fragment_name.lower() and 'list' not in fragment_name.lower() and 'перечень' not in fragment_name.lower():
            errors.append({
                'type': ErrorType.UL_WITHOUT_LIST_KEYWORD.value,
                'message': f'Найден тег <ul>, но в названии фрагмента "{fragment_name}" нет слова "список" или "list"'
            })

        # 3. Текст начинается с <ul>
        # Убираем пробелы, переносы, комментарии в начале
        cleaned_start = re.sub(r'^[\s\n\r\t]*(?:<!--.*?-->[\s\n\r\t]*)*', '', html)
        if cleaned_start.startswith('<ul>'):
            errors.append({
                'type': ErrorType.TEXT_STARTS_WITH_UL.value,
                'message': 'Текст начинается с тега <ul>. Рекомендуется добавить вводный текст или заголовок'
            })

        return errors
    def check_stop_words(self, text: str) -> List[Dict]:
        """Проверка на стоп-слова (по вхождению)"""
        errors = []
        stop_words = [
            'выдача', 'гибкие услуги', 'известно', 'магазин', 'на рынке',
            'спрос на товары', 'предмет', 'приложен', 'угол с углом',
            'товар обеспечивает', 'предлагаем услуги', 'доставке и монтажу',
            'доставку и монтаж', 'доставку, монтаж', 'монтажные работы', 'по монтажу',
            'подбору и монтажу', 'проектирование и монтаж', 'проектированию и монтажу',
            'выбору и монтажу', 'услуг монтажа', 'услуги монтажа', 'доставка и установка',
            'доставку и установку', 'по установке', 'профессиональную установку',
            'услуг по установке', 'настройка', 'настройке', 'обучаем', 'обучение',
            'обучению', 'техническому обслуживанию', 'индивидуального заказа',
            'изготавливаем', 'услуги по индивидуальному', 'услуги по резке',
            'услуги по упаковке', 'по ремонту', 'по обработке', 'под ключ',
            'долговеч', 'идеал', "услуг", 'наш продукт','наша продукция','наши решения','нашу продукцию'
        ]

        text_lower = text.lower()

        # Удаляем содержимое переменных перед проверкой
        text_without_vars = re.sub(r'\{[^}]+\}', ' ', text_lower)

        for word in stop_words:
            if word.lower() in text_without_vars:
                errors.append({
                    'type': ErrorType.STOP_WORD_FOUND.value,
                    'message': f'Найдено стоп-слово: "{word}"'
                })
        return errors


class ExportManager:




    @staticmethod
    def export_to_excel(fragment_manager: FragmentManager, template_data: Dict = None, use_html: bool = False) -> BytesIO:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            fm = fragment_manager
            if not fm.fragments:
                pd.DataFrame({'Сообщение': ['Нет данных для экспорта']}).to_excel(writer, sheet_name='Инфо', index=False)
                output.seek(0)
                return output
            category_code = fm.category_code or "без_кода"

            if template_data and not template_data.get('category_code'):
                template_data['category_code'] = category_code

            # ── Лист "Шаблоны" ──
            templates_rows = []
            added_templates = set()

            if template_data and template_data.get('template'):
                template_str = template_data.get('template', '')
                if template_str not in added_templates:
                    templates_rows.append({
                        'Код категории': template_data.get('category_code', category_code),
                        'Название шаблона': template_data.get('template_name', 'Основной'),
                        'Шаблон': template_str
                    })
                    added_templates.add(template_str)

            for tpl_name, tpl in fm.templates.items():
                template_str = " ".join(f"{{fragment {f}}}" for f in tpl.order)
                if template_str in added_templates:
                    continue
                templates_rows.append({
                    'Код категории': category_code,
                    'Название шаблона': tpl_name,
                    'Шаблон': template_str
                })
                added_templates.add(template_str)

            if templates_rows:
                df_templates = pd.DataFrame(templates_rows)
                df_templates.to_excel(writer, sheet_name='Шаблоны', index=False)
            else:
                pd.DataFrame({'Сообщение': ['Нет созданных шаблонов']}).to_excel(writer, sheet_name='Шаблоны', index=False)

            # ── Лист "Фрагменты" ──
            pd.DataFrame({
                'Название фрагмента': sorted(fm.fragment_names)
            }).to_excel(writer, sheet_name='Фрагменты', index=False)

            # ── Лист "Свойства фрагментов" ──
            props = fm.get_all_properties()
            if props:
                df_props = pd.DataFrame(props)
                df_props = df_props.drop_duplicates()
                df_props.to_excel(writer, sheet_name='Свойства фрагментов', index=False)
            else:
                pd.DataFrame({'Сообщение': ['Нет данных']}).to_excel(writer, sheet_name='Свойства фрагментов', index=False)

            # ── Лист "Элементы фрагментов" ──
            elements = []
            for f in fm.fragments:
                # ВСЕГДА используем актуальный processed_text
                text_for_export = f.processed_text

                if use_html and f.html_text:
                    text_for_export = f.html_text

                elements.append({
                    'Название блока': f.fragment_name,
                    'Текстовый фрагмент': text_for_export,
                    'HTML версия': f.html_text or '',
                    'Обычный текст (с переменными)': f.processed_text,
                    'Тип': f.block_type,
                    'Характеристика': f.characteristic_name or '',
                    'Значение': f.characteristic_value or '',
                    'Статус': f.status,
                    'Удалённые единицы': ', '.join(f.units_removed) if f.units_removed else '',
                    'Удалённые символы': ', '.join(f.symbols_removed) if f.symbols_removed else '',
                    'Автоисправлен': 'Да' if f.auto_corrected else 'Нет',
                    'Ошибки': '; '.join([err.get('message', str(err)) for err in f.errors]),
                    'Предупреждения': '; '.join(f.warnings)
                })
            pd.DataFrame(elements).to_excel(writer, sheet_name='Элементы фрагментов', index=False)

        output.seek(0)
        return output

    @staticmethod
    def export_verification_json(fragment_manager: FragmentManager, phase5_data: Dict) -> str:
        fm = fragment_manager
        prompts = phase5_data.get('prompts', {})
        results = phase5_data.get('results', [])
        original_by_id = {r.get('prompt_id'): r.get('edited_text', '') for r in results}

        blocks_info = []
        for block in fm.fragments:
            info = {
                'block_id': block.id,
                'fragment_name': block.fragment_name,
                'block_type': block.block_type,
                'original_text': original_by_id.get(block.id, block.original_text),
                'processed_text': block.processed_text,
                'html_text': block.html_text,
                'characteristic_name': block.characteristic_name,
                'characteristic_value': block.characteristic_value,
                'errors': block.errors,
                'warnings': block.warnings,
                'special_symbols': block.special_symbols,
                'status': block.status,
                'auto_corrected': block.auto_corrected,
                'added_value': block.added_value,
                'prompt_id': block.id,
            }
            prompt_text = prompts.get(block.id)
            if prompt_text:
                info['prompt_text'] = prompt_text
            blocks_info.append(info)

        export_data = {
            'timestamp': datetime.now().isoformat(),
            'category': fm.category,
            'blocks': blocks_info,
            'phase5_meta': {
                'total_results': len(results),
                'prompts_count': len(prompts)
            }
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def export_verification_excel(fragment_manager: FragmentManager, phase5_data: Dict) -> BytesIO:
        fm = fragment_manager
        prompts = phase5_data.get('prompts', {})
        results = phase5_data.get('results', [])
        original_by_id = {r.get('prompt_id'): r.get('edited_text', '') for r in results}

        data = []
        for block in fm.fragments:
            data.append({
                'ID блока': block.id,
                'Фрагмент': block.fragment_name,
                'Тип': block.block_type,
                'Исходный текст (фаза 5)': original_by_id.get(block.id, block.original_text),
                'Обработанный текст': block.processed_text,
                'HTML': block.html_text,
                'Характеристика': block.characteristic_name,
                'Значение': block.characteristic_value,
                'Ошибки': '; '.join([err.get('message', str(err)) for err in block.errors]),
                'Предупреждения': '; '.join(block.warnings),
                'Статус': block.status,
                'Автоисправлено': block.auto_corrected,
                'Добавленное значение': block.added_value,
                'Текст промпта': prompts.get(block.id, ''),
            })

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(data).to_excel(writer, sheet_name='Блоки', index=False)
            # Добавим лист с промптами, если есть
            if prompts:
                prompts_df = pd.DataFrame([
                    {'prompt_id': pid, 'prompt_text': ptext}
                    for pid, ptext in prompts.items()
                ])
                prompts_df.to_excel(writer, sheet_name='Промпты', index=False)
        output.seek(0)
        return output


class Phase7Interface:
    def __init__(self, context=None):
        self.context = context
        self.vm = VariableManager()
        self.text_processor = EnhancedTextProcessor(self.vm)
        self._init_session_state()
        self._init_ui_state()

        # === ДОМЕН ===
        if 'domain_manager' not in st.session_state:
            st.session_state.domain_manager = DomainManager()
        self.dm = st.session_state.domain_manager

        # ✅ ДОБАВИТЬ СИНХРОНИЗАЦИЮ ДОМЕНА ИЗ ФАЙЛА
        user_id = st.session_state.get('user_id')
        if user_id:
            settings = self.dm.load_user_settings(user_id)
            saved_domain = settings.get('selected_domain', 'default')
            saved_site = settings.get('selected_site', 'steelborg')

            st.session_state.current_domain = saved_domain
            st.session_state.selected_domain = saved_domain
            st.session_state.current_site = saved_site
            st.session_state.selected_site = saved_site
            st.session_state[f'domain_system_{saved_site}'] = saved_domain

            print(f"✅ Phase7 загружен домен из файла: {saved_domain}")

        # ✅ НОВОЕ: обновляем переменную цены из домена
        self._update_price_variable_from_domain()

        # ✅ ИЗМЕНЕНО: СНАЧАЛА загружаем данные, ПОТОМ создаём шаблоны
        self._ensure_data_loaded()

        # ✅ ТЕПЕРЬ загружаем шаблоны из домена (после того как данные загружены)
        self._load_templates_from_domain()

        config = self.dm.load_domain_config()

        # Загружаем category_code
        if 'app_data' in st.session_state:
            phase7_saved = st.session_state.app_data.get('phase7', {})
            saved_category_code = phase7_saved.get('category_code') or phase7_saved.get('manual_category_code')
            if saved_category_code:
                fm = st.session_state.get('fragment_manager')
                if fm:
                    fm.category_code = saved_category_code
                    fm.category = saved_category_code
    def _update_price_variable_from_domain(self):
        """Обновляет переменную цены с учётом валюты текущего домена"""
        price_var = self.dm.get_price_variable()

        # Обновляем в VariableManager
        if 'цена' in self.vm.system_vars:
            self.vm.system_vars['цена']['variants'] = [price_var]
            self.vm.system_vars['цена']['description'] = f"Цена товара ({self.dm.get_currency_settings()['symbol']})"

    def _match_block_name(self, fragment_name: str, mask_name: str) -> bool:
        """
        Гибкое сопоставление имени фрагмента с маской.
        - Регистронезависимо
        - Игнорирует разницу между пробелом и подчёркиванием
        - Поддерживает частичное вхождение (маска может быть частью имени)
        """
        # Нормализуем оба имени: нижний регистр, заменяем подчёркивания на пробелы
        frag_normalized = fragment_name.lower().replace('_', ' ').strip()
        mask_normalized = mask_name.lower().replace('_', ' ').strip()

        # Точное совпадение
        if frag_normalized == mask_normalized:
            return True

        # Маска содержится в имени фрагмента (например: "заголовок" в "металлопрокат_заголовок")
        if mask_normalized in frag_normalized:
            return True

        # Имя фрагмента содержится в маске
        if frag_normalized in mask_normalized:
            return True

        return False

    def _get_non_characteristic_blocks(self) -> List[str]:
        """Получает список блоков, не являющихся характеристиками, из конфига домена"""
        phase_config = self.dm.get_phase_config(7)
        return phase_config.get("non_characteristic_blocks", [])

    def _get_template_patterns(self) -> List[List[str]]:
        """Получает шаблоны из конфига домена"""
        phase_config = self.dm.get_phase_config(7)
        return phase_config.get("template_patterns", [])

    def _get_postprocessing_rules(self) -> Dict:
        """Получает правила постобработки из конфига домена"""
        phase_config = self.dm.get_phase_config(7)
        return phase_config.get("postprocessing_rules", {})
    def _get_characteristics_priority(self) -> Dict[str, int]:
        """Получает приоритеты характеристик из фазы 1 (ТОЛЬКО из файла)"""
        characteristics_priority = {}

        try:
            # Получаем путь к файлу проекта
            ctx_data = _get_context_data(self.context, st.session_state)

            if ctx_data['has_context'] and self.context is not None:
                current_project_id = self.context.project_id
                user_id = self.context.user_id
                site = self.context.site_name
                domain = self.context.domain_name
            else:
                current_project_id = st.session_state.get('current_project_id', '')
                user_id = st.session_state.get('user_id')
                site = st.session_state.get('current_site', 'steelborg')
                domain = st.session_state.get('current_domain', 'default')

            if not current_project_id:
                return characteristics_priority

            project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{current_project_id}.json")

            if not project_file.exists():
                return characteristics_priority

            with open(project_file, 'r', encoding='utf-8') as f:
                project_data = json.load(f)

            phase1_data = project_data.get('app_data', {}).get('phase1', {})

            if phase1_data and 'characteristics' in phase1_data:
                for char in phase1_data['characteristics']:
                    char_name = char.get('char_name', '')
                    priority = char.get('priority', 0)
                    if char_name:
                        characteristics_priority[char_name] = priority

        except Exception as e:
            print(f"❌ Ошибка загрузки приоритетов: {e}")

        return characteristics_priority

    def _load_templates_from_domain(self):
        """Загружает шаблоны для текущего домена и категории"""
        fm = st.session_state.get('fragment_manager')
        if not fm:
            print("⚠️ _load_templates_from_domain: fragment_manager отсутствует")
            return

        # Получаем код категории
        category_code = fm.category_code or "default"

        # Загружаем шаблоны из домена
        templates = self.dm.get_templates(category_code)

        # ✅ ОЧИЩАЕМ СТАРЫЕ ШАБЛОНЫ
        fm.templates.clear()

        if templates:
            # Загружаем шаблоны из домена
            for tpl_name, tpl_data in templates.items():
                fm.add_template(
                    name=tpl_name,
                    order=tpl_data.get('order', []),
                    description=tpl_data.get('description', ''),
                    set_as_default=tpl_data.get('is_default', False)
                )
            print(f"✅ Загружено {len(templates)} шаблонов из домена для категории {category_code}")
        else:
            # Если нет шаблонов в домене — создаём стандартные
            print(f"⚠️ Нет шаблонов в домене для категории {category_code}, создаём стандартные")
            self._create_default_templates()
            # И сохраняем их в домен
            self._save_templates_to_domain()
            st.info(f"✨ Созданы стандартные шаблоны для домена {self.dm.get_domain_display_name()}")

    def _save_templates_to_domain(self):
        """Сохраняет текущие шаблоны в домен"""
        fm = st.session_state.get('fragment_manager')
        if not fm or not fm.templates:
            return

        category_code = fm.category_code or "default"

        templates_to_save = {}
        for tpl_name, tpl in fm.templates.items():
            templates_to_save[tpl_name] = {
                'name': tpl.name,
                'order': tpl.order,
                'description': tpl.description,
                'is_default': tpl.is_default
            }

        self.dm.save_templates(templates_to_save, category_code)

    def _on_domain_change(self):
        """Вызывается при смене домена — перезагружает шаблоны и валюту"""
        # Обновляем валюту
        self._update_price_variable_from_domain()

        # Перезагружаем шаблоны
        self._load_templates_from_domain()

        # Пересчитываем ошибки (если нужно)
        fm = st.session_state.get('fragment_manager')
        if fm:
            for block in fm.fragments:
                self._recalculate_block_errors(block)

        st.success(f"🔄 Данные обновлены для домена {self.dm.get_domain_display_name()}")

    def _ensure_data_loaded(self):
        """Гарантирует загрузку данных при каждом запуске"""
        fm = st.session_state.get('fragment_manager')
        if not fm:
            fm = FragmentManager("Без_категории")
            st.session_state.fragment_manager = fm

        # ===== ДОБАВИТЬ СИНХРОНИЗАЦИЮ ID ПРОЕКТА =====
        current_project_id = st.session_state.get('current_project_id')

        # Если ID проекта не совпадает с сохраненным - синхронизируем
        if current_project_id and st.session_state.get('phase7_last_loaded_project') != current_project_id:
            # Обновляем ID, НО НЕ ОЧИЩАЕМ ДАННЫЕ (они еще не загружены)
            st.session_state.phase7_last_loaded_project = current_project_id
            print(f"🔄 phase7_last_loaded_project синхронизирован: {current_project_id}")

        # Если уже есть блоки - проверяем соответствие
        if len(fm.fragments) > 0:
            return True

        # === ПРИОРИТЕТ ВОССТАНОВЛЕНИЯ ===
        current_project_id = st.session_state.get('current_project_id', 'default')

        # 1. Из phase7_projects_data
        phase7_projects = st.session_state.app_data.get('phase7_projects_data', {})
        project_data = phase7_projects.get(current_project_id)

        if project_data and project_data.get('blocks'):
            self._restore_from_saved(project_data)
            st.session_state.phase7_last_loaded_project = current_project_id
            print(f"✅ Восстановлено {len(fm.fragments)} блоков из сохранённого проекта")
            return True

        # 2. Из файла проекта
        if self._load_data():
            st.session_state.phase7_last_loaded_project = current_project_id
            return True

        # 3. Из phase6
        if 'phase6' in st.session_state.app_data:
            success = self._load_data()
            if success:
                st.session_state.phase7_last_loaded_project = current_project_id
                return True

        print("⚠️ Данные не найдены. Нажмите 'Обновить данные из фазы 6'")
        return False

    def _restore_from_saved(self, saved_data: dict):
        """Надёжное восстановление"""
        fm = st.session_state.fragment_manager
        fm.fragments = []
        fm.fragment_names = set()
        fm.fragment_properties = defaultdict(list)


        for block_data in saved_data.get('blocks', []):
            fm.add_block(block_data)



        if saved_data.get('category_code'):
            fm.category_code = saved_data['category_code']
            fm.category = saved_data['category_code']

        # Пересчёт ошибок после восстановления
        for block in fm.fragments:
            self._recalculate_block_errors(block)
    def force_save(self):
        """ЕДИНСТВЕННАЯ функция, которая гарантированно сохраняет всё"""
        fm = st.session_state.get('fragment_manager')
        if not fm:
            return

        # Принудительно обновляем все mutable поля
        for block in fm.fragments:
            block.last_modified = datetime.now()
            # Синхронизируем text_area → block
            text_key = f"edit_text_{block.id}"
            if text_key in st.session_state:
                block.processed_text = st.session_state[text_key]

            html_key = f"edit_html_{block.id}"
            if html_key in st.session_state:
                block.html_text = st.session_state[html_key]
    def _recalculate_block_errors(self, block: FragmentBlock):
        """Полный пересчёт ошибок для одного блока (без дублирования)"""
        new_errors = []

        # 1. Regular блоки — проверка скобок
        if block.block_type == 'regular':
            bracket_errors = self.text_processor.check_regular_brackets(
                block.processed_text, block.characteristic_value
            )
            new_errors.extend(bracket_errors)

        # 2. Non-regular — неизвестные переменные
        else:
            matches = self.text_processor.pattern.finditer(block.processed_text)
            for match in matches:
                var_name = match.group(1).strip().lower()
                if not any(sys_var.lower() == var_name for sys_var in self.vm.system_vars.keys()):
                    new_errors.append({
                        'type': ErrorType.UNKNOWN_VARIABLE.value,
                        'message': f"Неизвестная переменная '{var_name}' в non-regular блоке"
                    })

        # 3. Общие проверки (всегда выполняем)
        new_errors.extend(self.text_processor.check_square_brackets(block.processed_text))
        new_errors.extend(self.text_processor.check_wrong_city_variable(block.processed_text))
        new_errors.extend(self.text_processor.check_ai_marker_words(block.processed_text))
        new_errors.extend(self.text_processor.check_double_brackets(block.processed_text))
        new_errors.extend(self.text_processor.check_gost_tu_outside(block.processed_text))
        new_errors.extend(self.text_processor.check_foreign_language(block.processed_text))
        new_errors.extend(self.text_processor.check_stop_words(block.processed_text))
        new_errors.extend(self.text_processor.check_digits_after_replacement(block.processed_text))

        # 4. Специальные символы
        specials = self.text_processor._find_special_symbols(block.processed_text)
        if specials:
            sym_list = ', '.join(set(s[0] for s in specials))
            new_errors.append({
                'type': ErrorType.SPECIAL_SYMBOL.value,
                'message': f"Найдены специальные символы: {sym_list}"
            })

        # Убираем дубликаты (по типу + сообщению)
        unique_errors = []
        seen = set()
        for err in new_errors:
            key = (err.get('type'), err.get('message'))
            if key not in seen:
                seen.add(key)
                unique_errors.append(err)

        block.errors = unique_errors
        block.special_symbols = specials

        # Обновляем статус
        if block.errors:
            block.status = 'error'
        elif block.manually_fixed:
            block.status = 'fixed'
        else:
            block.status = 'processed'
    def _sync_session_state_to_blocks(self):
        """Синхронизация session_state ↔ blocks (в обе стороны)"""
        fm = st.session_state.get('fragment_manager')
        if not fm:
            return False

        changed = False
        for block in fm.fragments:
            text_key = f"edit_text_{block.id}"
            html_key = f"edit_html_{block.id}"

            # Из session_state в block
            if text_key in st.session_state:
                new_text = st.session_state[text_key]
                if new_text != block.processed_text:
                    block.processed_text = new_text
                    changed = True

            if html_key in st.session_state and block.html_text != st.session_state[html_key]:
                block.html_text = st.session_state[html_key]
                changed = True

            # Из block в session_state (чтобы всегда было актуально)
            if text_key not in st.session_state or st.session_state[text_key] != block.processed_text:
                st.session_state[text_key] = block.processed_text

            if html_key not in st.session_state or st.session_state[html_key] != block.html_text:
                st.session_state[html_key] = block.html_text

        return changed
    def _init_session_state(self):
        if 'fragment_manager' not in st.session_state:
            st.session_state.fragment_manager = FragmentManager("Без_категории")
        if 'app_data' in st.session_state and 'category' in st.session_state.app_data:
            st.session_state.fragment_manager.category = st.session_state.app_data['category']
            st.session_state.fragment_manager.category_code = st.session_state.app_data.get('category', 'Без_категории')
        if 'transformation_registry' not in st.session_state:
            st.session_state.transformation_registry = TransformationRegistry()
        if 'units_manager' not in st.session_state:
            st.session_state.units_manager = {
                'units': self.text_processor.units_to_remove.copy(),
                'custom_units': []
            }
        if 'found_units' not in st.session_state:
            st.session_state.found_units = []
        if 'found_special_symbols' not in st.session_state:
            st.session_state.found_special_symbols = []
    def _debug_template_creation(self, mask_fragments: Dict, characteristic_fragments: List,
                                 template_patterns: List[List[str]], created_templates: List[str]):
        st.markdown("---")
        st.markdown("### 🔍 Отладка создания шаблонов")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**📦 Найдено фрагментов по маске:**")
            if mask_fragments:
                for mask, frag in mask_fragments.items():
                    st.write(f"  ✅ `{mask}` → `{frag}`")
            else:
                st.write("  ❌ Нет ни одного фрагмента из маски")

            st.markdown("**📊 Характеристики:**")
            st.write(f"  Найдено: {len(characteristic_fragments)} шт")
            if characteristic_fragments:
                st.write(f"  Первые 5: {characteristic_fragments[:5]}")

        with col2:
            st.markdown("**🎯 Ожидалось шаблонов:**")
            st.write(f"  {len(template_patterns)} шт")

            '''st.markdown("**✅ Создано шаблонов:**")'''
            st.write(f"  {len(created_templates)} шт")
            if created_templates:
                st.write(f"  Список: {created_templates[:10]}")
                if len(created_templates) > 10:
                    st.write(f"  ... и ещё {len(created_templates) - 10}")

        st.markdown("**❌ Каких блоков из маски нет в проекте:**")
        all_masks = [p for pattern in template_patterns for p in pattern if p != "характеристики"]
        unique_masks = list(set(all_masks))

        missing_masks = []
        for mask in unique_masks:
            if mask not in mask_fragments:
                missing_masks.append(mask)

        if missing_masks:
            st.warning(f"Отсутствуют {len(missing_masks)} блоков из маски:")
            for mask in sorted(missing_masks):
                st.write(f"  ⚠️ `{mask}` — шаблоны с ним не созданы")
        else:
            st.success("✅ Все блоки из маски присутствуют в проекте!")
    def refresh_templates_and_export(self):
        """Обновляет шаблоны и данные экспорта из файла"""
        with st.spinner("🔄 Обновление шаблонов и данных экспорта..."):

            # 1. Перезагружаем данные из файла
            success = self._load_data()

            if not success:
                st.error("❌ Не удалось загрузить данные из файла")
                return False

            # 2. Обновляем шаблоны
            fm = st.session_state.fragment_manager

            # Очищаем старые шаблоны
            fm.templates.clear()

            # Создаём новые шаблоны из конфига домена
            self._create_default_templates()

            # 3. Пересчитываем ошибки для всех блоков
            for block in fm.fragments:
                self._recalculate_block_errors(block)

            # 4. Сканируем единицы и символы
            st.session_state.found_units = self._scan_units_in_texts()
            st.session_state.found_special_symbols = self._scan_special_symbols_in_texts()

            # 5. Сохраняем обновлённые данные
            self.save_data_to_app_state()

            # 6. ✅ ПРИНУДИТЕЛЬНО ОБНОВЛЯЕМ ИНТЕРФЕЙС
            st.session_state._templates_updated = True
            st.session_state._last_template_update = datetime.now().isoformat()

            # 7. Показываем статистику
            # 7. Показываем статистику
            st.success(f"✅ Шаблоны и данные экспорта обновлены!")
            st.info(f"📊 Загружено {len(fm.fragments)} блоков, создано {len(fm.templates)} шаблонов")

            # Показываем детали шаблонов
            if fm.templates:
                with st.expander("📋 Созданные шаблоны", expanded=True):
                    for tpl_name, tpl in list(fm.templates.items())[:10]:
                        st.write(f"**{tpl_name}** ({len(tpl.order)} фрагментов)")
                        if tpl.is_default:
                            st.write("  ⭐ По умолчанию")
                        # Показываем первые 5 фрагментов
                        preview = tpl.order[:5]
                        if len(tpl.order) > 5:
                            preview.append(f"... и ещё {len(tpl.order) - 5}")
                        st.write(f"  → {' → '.join(preview)}")
                    if len(fm.templates) > 10:
                        st.write(f"... и ещё {len(fm.templates) - 10} шаблонов")

            # ✅ ПРИНУДИТЕЛЬНО ОБНОВЛЯЕМ UI
            st.session_state._force_ui_update = True
            return True
    def _display_templates_list(self):
        """Отображает список созданных шаблонов"""
        fm = st.session_state.fragment_manager

        if not fm.templates:
            st.info("Нет созданных шаблонов")
            return

        st.subheader(f"📋 Шаблоны ({len(fm.templates)} шт)")

        # Группируем по типу (для наглядности)
        '''col1, col2 = st.columns(2)

        with col1:
            st.markdown("**С шаблонами:**")
            templates_list = list(fm.templates.items())

            # Показываем первые 30
            for tpl_name, tpl in templates_list[:30]:
                with st.expander(f"📄 {tpl_name}", expanded=False):
                    st.write(f"**Описание:** {tpl.description or 'Нет'}")
                    st.write(f"**⭐ По умолчанию:** {'Да' if tpl.is_default else 'Нет'}")
                    st.write(f"**Фрагментов:** {len(tpl.order)}")
                    st.write("**Порядок:**")
                    for i, frag in enumerate(tpl.order, 1):
                        st.write(f"  {i}. {frag}")

            if len(templates_list) > 30:
                st.info(f"... и ещё {len(templates_list) - 30} шаблонов")

        with col2:
            # Статистика
            st.markdown("**📊 Статистика:**")

            # Количество шаблонов по длине
            lengths = [len(tpl.order) for tpl in fm.templates.values()]
            if lengths:
                st.metric("Средняя длина", f"{sum(lengths)/len(lengths):.1f} фрагментов")
                st.metric("Минимум", f"{min(lengths)} фрагментов")
                st.metric("Максимум", f"{max(lengths)} фрагментов")

            # Частота использования фрагментов
            st.markdown("**🔥 Частота использования фрагментов:**")
            frag_counter = {}
            for tpl in fm.templates.values():
                for frag in tpl.order:
                    frag_counter[frag] = frag_counter.get(frag, 0) + 1

            # Топ-10 самых используемых
            top_frags = sorted(frag_counter.items(), key=lambda x: x[1], reverse=True)[:10]
            for frag, count in top_frags:
                st.progress(count / len(fm.templates), text=f"{frag[:30]}: {count}/{len(fm.templates)}")'''
    def _debug_fragment_names(self):
        """Показывает все имена фрагментов и их сопоставление с масками"""
        fm = st.session_state.fragment_manager
        non_characteristic_blocks = self._get_non_characteristic_blocks()

        st.markdown("### 📋 Проверка имен фрагментов")

        data = []
        for frag_name in fm.fragment_names:
            matched_mask = None
            for mask in non_characteristic_blocks:
                mask_lower = mask.lower().replace('_', ' ')
                frag_lower = frag_name.lower()

                if frag_lower.endswith(f'_{mask_lower}') or frag_lower.endswith(f'_{mask_lower.replace(" ", "_")}'):
                    matched_mask = mask
                    break
                if mask_lower in frag_lower:
                    matched_mask = mask
                    break

            data.append({
                'Фрагмент': frag_name,
                'Сопоставлен с маской': matched_mask or '❌ НЕТ',
                'Тип': 'Характеристика' if matched_mask is None else 'Блок'
            })

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    def _show_template_debug(self):
        """Показывает отладочную информацию"""
        debug = st.session_state.get('_template_debug')
        if not debug:
            st.info("Нет отладочной информации. Нажмите 'Обновить шаблоны'")
            return

        with st.expander("🔍 Отладка создания шаблонов", expanded=True):
            st.markdown("---")

            # Все фрагменты
            st.markdown("**📋 Все фрагменты в проекте (первые 10):**")
            all_frags = debug.get('all_fragments', [])
            for frag in all_frags:
                st.write(f"  • {frag}")
            if len(debug.get('all_fragments', [])) > 10:
                st.write(f"  ... и ещё {len(debug.get('all_fragments', [])) - 10}")

            st.markdown("---")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**📦 Найдено фрагментов по маске:**")
                mask_fragments = debug.get('mask_fragments', {})
                if mask_fragments:
                    for mask, frag in mask_fragments.items():
                        st.write(f"  ✅ `{mask}` → `{frag}`")
                else:
                    st.write("  ❌ Нет ни одного фрагмента из маски")
                    st.write("  💡 Проверьте имена фрагментов и маски в конфиге")

                st.markdown("**📊 Характеристики (отсортированы):**")
                char_fragments = debug.get('characteristic_fragments', [])
                st.write(f"  Найдено: {len(char_fragments)} шт")
                if char_fragments:
                    for frag in char_fragments[:5]:
                        st.write(f"  • {frag}")
                    if len(char_fragments) > 5:
                        st.write(f"  ... и ещё {len(char_fragments) - 5}")

            with col2:
                st.markdown("**🎯 Ожидалось шаблонов:**")
                st.write(f"  {debug.get('total_patterns', 0)} шт")

                '''st.markdown("**✅ Создано шаблонов:**")'''
                created = debug.get('created_templates', [])
                st.write(f"  {len(created)} шт")
                if created:
                    for tpl in created[:5]:
                        st.write(f"  • {tpl['name']}: {len(tpl['order'])} фрагментов")
                    if len(created) > 5:
                        st.write(f"  ... и ещё {len(created) - 5}")

            # Показываем сопоставление масок
            st.markdown("---")
            st.markdown("**🔍 Сопоставление масок с фрагментами:**")

            # Получаем все маски из паттернов
            all_masks = set()
            for pattern in debug.get('template_patterns', []):
                for item in pattern:
                    if item != "характеристики":
                        all_masks.add(item)

            # Проверяем каждую маску
            for mask in sorted(all_masks):
                found = mask in mask_fragments
                status = "✅" if found else "❌"
                frag = mask_fragments.get(mask, "НЕ НАЙДЕН")
                st.write(f"  {status} `{mask}` → `{frag}`")

            # Пропущенные шаблоны
            skipped = debug.get('skipped_patterns', [])
            if skipped:
                st.markdown("---")
                st.warning(f"⚠️ Пропущено {len(skipped)} шаблонов:")
                for item in skipped[:3]:
                    st.write(f"  • Паттерн: {' → '.join(item['pattern'])}")
                    st.write(f"    ❌ Отсутствуют: {', '.join(item['missing'])}")
                if len(skipped) > 3:
                    st.write(f"  ... и ещё {len(skipped) - 3}")

            st.markdown("---")
            if st.button("🗑️ Очистить отладку", key=f"clear_debug_main_{uuid.uuid4().hex[:8]}"):
                del st.session_state._template_debug
                st.rerun()

    def _create_default_templates(self):
        """Создаёт шаблоны на основе конфига домена"""
        fm = st.session_state.fragment_manager

        log("=" * 60, "INFO")
        log("🔧 _create_default_templates() STARTED", "INFO")
        log(f"   fm.fragment_names: {list(fm.fragment_names)}", "INFO")
        log(f"   fm.templates before: {len(fm.templates)}", "INFO")

        # Получаем конфиг домена
        non_characteristic_blocks = self._get_non_characteristic_blocks()
        template_patterns = self._get_template_patterns()

        log(f"   non_characteristic_blocks: {non_characteristic_blocks}", "INFO")
        log(f"   template_patterns: {template_patterns}", "INFO")

        if not template_patterns:
            log("⚠️ template_patterns ПУСТЫЕ! Создаём стандартные шаблоны", "WARNING")
            self._create_standard_templates(fm)
            log("=" * 60, "INFO")
            return

        # === НОВАЯ ЛОГИКА СОПОСТАВЛЕНИЯ ===
        mask_fragments = {}
        characteristic_fragments = []

        log("🔍 СОПОСТАВЛЯЕМ ФРАГМЕНТЫ С МАСКАМИ:", "INFO")

        for frag_name in fm.fragment_names:
            is_characteristic = True
            frag_lower = frag_name.lower()
            log(f"   Проверяем фрагмент: '{frag_name}'", "DEBUG")

            for mask in non_characteristic_blocks:
                mask_lower = mask.lower().replace('_', ' ')
                log(f"      Сравниваем с маской: '{mask}' (normalized: '{mask_lower}')", "DEBUG")

                # 1. Точное совпадение
                if frag_lower == mask_lower:
                    mask_fragments[mask] = frag_name
                    is_characteristic = False
                    log(f"      ✅ ТОЧНОЕ СОВПАДЕНИЕ: '{frag_name}' == '{mask}'", "INFO")
                    break

                # 2. Фрагмент заканчивается на маску (категория_маска)
                if frag_lower.endswith(f'_{mask_lower}') or frag_lower.endswith(f'_{mask_lower.replace(" ", "_")}'):
                    mask_fragments[mask] = frag_name
                    is_characteristic = False
                    log(f"      ✅ ЗАКАНЧИВАЕТСЯ НА МАСКУ: '{frag_name}' заканчивается на '_{mask}'", "INFO")
                    break

                # 3. Маска содержится в имени
                if mask_lower in frag_lower:
                    mask_fragments[mask] = frag_name
                    is_characteristic = False
                    log(f"      ✅ МАСКА СОДЕРЖИТСЯ: '{mask}' в '{frag_name}'", "INFO")
                    break

                # 4. Специальные случаи для "характеристики" - пропускаем
                if mask_lower == 'характеристики':
                    continue

            if is_characteristic:
                characteristic_fragments.append(frag_name)
                log(f"   📊 ХАРАКТЕРИСТИКА: '{frag_name}'", "INFO")

        log(f"📦 mask_fragments: {mask_fragments}", "INFO")
        log(f"📊 characteristic_fragments: {characteristic_fragments}", "INFO")

        # === СОРТИРОВКА ХАРАКТЕРИСТИК ПО ПРИОРИТЕТУ ===
        characteristics_priority = self._get_characteristics_priority()
        log(f"📊 characteristics_priority: {characteristics_priority}", "INFO")

        characteristic_fragments.sort(
            key=lambda x: (
                -characteristics_priority.get(x, 0),
                x
            )
        )
        log(f"📊 Отсортированные характеристики: {characteristic_fragments}", "INFO")

        if not characteristic_fragments:
            log("❌ НЕТ ХАРАКТЕРИСТИК для создания шаблонов!", "ERROR")
            st.warning("⚠️ Нет характеристик для создания шаблонов")
            log("=" * 60, "INFO")
            return

        # === ОЧИЩАЕМ СТАРЫЕ ШАБЛОНЫ ===
        fm.templates.clear()
        log("🗑️ Старые шаблоны очищены", "INFO")

        # === СОЗДАНИЕ ШАБЛОНОВ ===
        template_index = 1
        created_templates = []
        skipped_patterns = []

        log(f"🔧 СОЗДАЁМ ШАБЛОНЫ из {len(template_patterns)} паттернов:", "INFO")
        for pattern_idx, pattern in enumerate(template_patterns):
            log(f"   Паттерн #{pattern_idx + 1}: {pattern}", "INFO")
            order = []
            skip_template = False
            missing_items = []

            for item in pattern:
                if item == "характеристики":
                    log(f"      Добавляем характеристики: {characteristic_fragments}", "DEBUG")
                    order.extend(characteristic_fragments)
                else:
                    log(f"      Ищем маску '{item}' в mask_fragments...", "DEBUG")
                    found = False
                    for mask, frag in mask_fragments.items():
                        if mask == item:
                            order.append(frag)
                            found = True
                            log(f"      ✅ Найден фрагмент для маски '{item}': '{frag}'", "INFO")
                            break

                    if not found:
                        log(f"      ❌ НЕ НАЙДЕН фрагмент для маски '{item}'", "WARNING")
                        skip_template = True
                        missing_items.append(item)

            if skip_template:
                log(f"   ⚠️ Шаблон пропущен, отсутствуют: {missing_items}", "WARNING")
                skipped_patterns.append({
                    'pattern': pattern,
                    'missing': missing_items
                })
                continue

            # Убираем дубликаты
            order = list(dict.fromkeys(order))
            log(f"   Порядок после удаления дубликатов: {order}", "DEBUG")

            if order:
                template_name = f"Шаблон_{template_index}"
                fm.add_template(
                    name=template_name,
                    order=order,
                    description=f"Автошаблон: {' → '.join(pattern)}",
                    set_as_default=(template_index == 1)
                )
                created_templates.append({
                    'name': template_name,
                    'pattern': pattern,
                    'order': order
                })
                log(f"   ✅ СОЗДАН ШАБЛОН: '{template_name}' с {len(order)} фрагментами", "INFO")
                template_index += 1

        log(f"✅ СОЗДАНО ШАБЛОНОВ: {template_index - 1}", "INFO")
        if skipped_patterns:
            log(f"⚠️ ПРОПУЩЕНО ШАБЛОНОВ: {len(skipped_patterns)}", "WARNING")

        # === СОХРАНЯЕМ ОТЛАДКУ ===
        st.session_state._template_debug = {
            'mask_fragments': mask_fragments,
            'characteristic_fragments': characteristic_fragments,
            'total_patterns': len(template_patterns),
            'created_templates': created_templates,
            'skipped_patterns': skipped_patterns,
            'all_fragments': list(fm.fragment_names),
            'template_patterns': template_patterns,
            'non_characteristic_blocks': non_characteristic_blocks,
            'timestamp': datetime.now().isoformat()
        }
        log("=" * 60, "INFO")

        if template_index > 1:
            st.info(f"✅ Создано {template_index - 1} шаблонов")
            self._save_templates_to_domain()
        else:
            log("❌ НЕ УДАЛОСЬ СОЗДАТЬ НИ ОДНОГО ШАБЛОНА!", "ERROR")
            st.warning("⚠️ Не удалось создать ни одного шаблона")



    def _init_ui_state(self):
        default_ui_state = {
            'selected_block_id': None,
            # 'editing_mode': False,            # удалить
            'active_tab': 'fragments',
            'show_html': False,
            # 'selected_issues': set(),         # можно удалить
            'fragments_page': 1,
            'fragments_per_page': 20,
            'fragment_search': '',
            'fragment_group_by': 'none',
            'insert_position_mode': 'end',
            'insert_position_word_index': 0,
            'selected_units_global': [],
            'selected_symbols_global': [],
            'compact_view': True,  # оставляем
            'filtered_block_ids': [],  # новый список id после фильтрации
            'current_block_index': 0, # индекс в этом списке
            'editing_block_id': None
        }
        if 'ui_state' not in st.session_state:
            st.session_state.ui_state = default_ui_state.copy()
        else:
            for key, value in default_ui_state.items():
                if key not in st.session_state.ui_state:
                    st.session_state.ui_state[key] = value

    def save_data_to_app_state(self, app_state=None):
        """Сохраняет данные фазы 7 в файл ТЕКУЩЕГО ПРОЕКТА"""
        fm = st.session_state.get('fragment_manager')
        if not fm:
            return False

        # ========== ПОЛУЧАЕМ КОНТЕКСТ ==========
        ctx_data = _get_context_data(self.context, st.session_state)

        if ctx_data['has_context'] and self.context is not None:
            current_project_id = self.context.project_id
            user_id = self.context.user_id
            site = self.context.site_name
            domain = self.context.domain_name
        else:
            current_project_id = st.session_state.get('current_project_id', '')
            user_id = st.session_state.get('user_id')
            site = st.session_state.get('current_site', 'steelborg')
            domain = st.session_state.get('current_domain', 'default')

        if not current_project_id:
            return False

        # ===== ДОБАВИТЬ: обновляем ID последнего загруженного проекта =====
        st.session_state.phase7_last_loaded_project = current_project_id
        # ===== КОНЕЦ ДОБАВЛЕНИЯ =====

        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{current_project_id}.json")




        if not project_file.exists():
            return False

        blocks_dict = [f.to_dict() for f in fm.fragments]

        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)

            if 'app_data' not in file_data:
                file_data['app_data'] = {}

            file_data['app_data']['phase7'] = {
                'fragments_count': len(fm.fragments),
                'fragment_names': list(fm.fragment_names),
                'category_code': fm.category_code,
                'last_modified': datetime.now().isoformat(),
                'blocks': blocks_dict,
            }
            file_data['updated_at'] = datetime.now().isoformat()

            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, ensure_ascii=False, indent=2)

            return True

        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False
    def _display_postprocessing_results(self):
        """Отображает результаты последней постобработки"""
        results = st.session_state.get('postprocessing_results', {})
        if not results:
            return

        st.subheader("📊 Результаты последней постобработки")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Блоков обработано", results.get('total_processed', 0))
        col2.metric("Удалено единиц", results.get('total_units_removed', 0))
        col3.metric("Удалено символов", results.get('total_symbols_removed', 0))
        col4.metric("Ошибок после обработки",
                    results.get('total_errors', 0),
                    delta="Обновлено" if results.get('total_errors', 0) > 0 else None)

        if results.get('details'):
            with st.expander("📋 Детали по блокам", expanded=True):
                df = pd.DataFrame(results['details'])
                st.dataframe(df, use_container_width=True, hide_index=True)
    def _migrate_fragments(self):
        fm = st.session_state.fragment_manager
        if not fm.templates:  # если ещё не мигрировали
            if hasattr(fm, 'template_order') and fm.template_order:
                fm.add_template(
                    name="Основной",
                    order=fm.template_order.copy(),
                    set_as_default=True
                )
        for frag in fm.fragments:
            if not hasattr(frag, 'special_symbols'):
                frag.special_symbols = []
            if not hasattr(frag, 'html_text'):
                frag.html_text = ""
            if not hasattr(frag, 'auto_corrected'):
                frag.auto_corrected = False
            if not hasattr(frag, 'added_value'):
                frag.added_value = None
            if not hasattr(frag, 'last_modified'):
                frag.last_modified = datetime.now()
            if not hasattr(frag, 'html_generated'):
                frag.html_generated = False
            if not hasattr(frag, 'units_removed'):
                frag.units_removed = []
            if not hasattr(frag, 'symbols_removed'):
                frag.symbols_removed = []
            if frag.errors and all(isinstance(e, str) for e in frag.errors):
                # конвертируем строки в словари с типом GENERIC
                frag.errors = [{'type': ErrorType.GENERIC.value, 'message': e} for e in frag.errors]
            if not hasattr(frag, 'manually_fixed'):
                frag.manually_fixed = False
            if isinstance(frag.last_modified, str):
                try:
                    frag.last_modified = datetime.fromisoformat(frag.last_modified)
                except:
                    frag.last_modified = datetime.now()
    def refresh_from_phase6(self) -> bool:
        """Полное обновление данных из фазы 6 (С ОБНОВЛЕНИЕМ существующих блоков)"""
        fm = st.session_state.fragment_manager

        # Загружаем новые данные
        new_blocks_data = self._load_new_data_from_phase6()

        if not new_blocks_data:
            st.error("❌ Не удалось загрузить данные из фазы 6")
            return False

        # Обновляем или добавляем блоки
        updated_count = 0
        added_count = 0

        for prompt_id, new_data in new_blocks_data.items():
            existing_block = next((b for b in fm.fragments if b.id == prompt_id), None)

            if existing_block:
                # Обновляем существующий блок
                existing_block.original_text = new_data['processed_text']
                existing_block.processed_text = new_data['processed_text']
                existing_block.html_text = ''
                existing_block.errors = []
                existing_block.warnings = []
                existing_block.status = 'pending'
                existing_block.auto_corrected = False
                existing_block.last_modified = datetime.now()

                # Обновляем characteristic если изменилось
                if new_data.get('characteristic_name'):
                    existing_block.characteristic_name = new_data['characteristic_name']
                if new_data.get('characteristic_value'):
                    existing_block.characteristic_value = new_data['characteristic_value']

                updated_count += 1
            else:
                # Добавляем новый блок
                block_data = {
                    'id': prompt_id,
                    'fragment_name': new_data['fragment_name'],
                    'original_text': new_data['processed_text'],
                    'processed_text': new_data['processed_text'],
                    'html_text': '',
                    'block_type': new_data.get('block_type', 'unknown'),
                    'characteristic_name': new_data.get('characteristic_name'),
                    'characteristic_value': new_data.get('characteristic_value'),
                    'errors': [],
                    'warnings': [],
                    'status': 'pending',
                    'auto_corrected': False
                }
                fm.add_block(block_data)
                added_count += 1

        # Пересчитываем ошибки для всех блоков
        for block in fm.fragments:
            self._recalculate_block_errors(block)

        # Обновляем шаблоны
        self._create_default_templates()

        # Сохраняем
        self.save_data_to_app_state()

        st.success(f"✅ Обновлено: {updated_count} блоков обновлено, {added_count} добавлено")
        return True

    def _load_new_data_from_phase6(self) -> dict:
        """Загружает свежие данные из фазы 6 без проверки существующих блоков"""
        try:
            ctx_data = _get_context_data(self.context, st.session_state)

            if ctx_data['has_context'] and self.context is not None:
                app_data = self.context.data
            else:
                app_data = st.session_state.app_data
            phase6_data = app_data.get('phase6', {})

            results_dict = {}

            if isinstance(phase6_data, dict) and 'results' in phase6_data:
                results_dict = phase6_data['results']
            elif isinstance(phase6_data, dict) and 'processed_texts' in phase6_data:
                processed_texts = phase6_data['processed_texts']
                original_texts = phase6_data.get('original_texts', [])
                metadata = phase6_data.get('texts_metadata', [])

                for idx, text in enumerate(processed_texts):
                    meta = metadata[idx] if idx < len(metadata) else {}
                    prompt_id = meta.get('prompt_id', f"text_{idx}")
                    results_dict[prompt_id] = {
                        'prompt_id': prompt_id,
                        'ai_response': text,
                        'edited_text': text,
                        'original_text': original_texts[idx] if idx < len(original_texts) else '',
                        'status': 'success',
                        'type': meta.get('type', 'unknown'),
                        'characteristic_name': meta.get('characteristic_name', ''),
                        'characteristic_value': meta.get('characteristic_value', ''),
                        'block_name': meta.get('block_name', ''),
                        'is_synonymized': phase6_data.get('replacements_applied', False)
                    }

            # Конвертируем в удобный формат
            new_data = {}
            for prompt_id, result in results_dict.items():
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except:
                        continue

                if not isinstance(result, dict) or result.get('status') == 'error':
                    continue

                text = result.get('edited_text', '') or result.get('ai_response', '') or result.get('processed_text', '')
                if not text:
                    continue

                normalized_text = self.text_processor.normalize_text(text)
                frag_name = self._generate_fragment_name(result)
                block_type = result.get('type', 'unknown')

                if block_type == 'unknown':
                    if result.get('characteristic_name'):
                        block_type = 'unique' if result.get('characteristic_value') else 'regular'

                new_data[prompt_id] = {
                    'processed_text': normalized_text,
                    'fragment_name': frag_name,
                    'block_type': block_type,
                    'characteristic_name': result.get('characteristic_name'),
                    'characteristic_value': result.get('characteristic_value'),
                    'is_synonymized': result.get('is_synonymized', False)
                }

            return new_data

        except Exception as e:
            st.error(f"Ошибка загрузки: {str(e)}")
            return {}
    # ------------------------------------------------------------------
    #                     ЗАГРУЗКА ДАННЫХ (БЕЗ ОБРАБОТКИ)
    # ------------------------------------------------------------------
    def _load_data(self) -> bool:
        """Загружает данные из фазы 6 ТОЛЬКО из файла"""
        log("=" * 60, "INFO")
        log("🔍 _load_data() CALLED", "INFO")

        # Получаем путь к файлу проекта
        ctx_data = _get_context_data(self.context, st.session_state)

        if ctx_data['has_context'] and self.context is not None:
            current_project_id = self.context.project_id
            user_id = self.context.user_id
            site = self.context.site_name
            domain = self.context.domain_name
        else:
            current_project_id = st.session_state.get('current_project_id', '')
            user_id = st.session_state.get('user_id')
            site = st.session_state.get('current_site', 'steelborg')
            domain = st.session_state.get('current_domain', 'default')

        log(f"   current_project_id: {current_project_id}", "INFO")
        log(f"   user_id: {user_id}", "INFO")
        log(f"   site: {site}", "INFO")
        log(f"   domain: {domain}", "INFO")

        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{current_project_id}.json")
        log(f"   project_file: {project_file}", "INFO")
        log(f"   project_file.exists(): {project_file.exists()}", "INFO")

        if not project_file.exists():
            log(f"❌ Файл проекта НЕ СУЩЕСТВУЕТ: {project_file}", "ERROR")
            return False

        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)

            log(f"   ✅ Файл загружен, keys: {list(file_data.keys())}", "INFO")
            log(f"   app_data keys: {list(file_data.get('app_data', {}).keys())}", "INFO")

            # Проверяем phase6
            phase6_data = file_data.get('app_data', {}).get('phase6', {})
            log(f"   phase6_data type: {type(phase6_data)}", "INFO")

            if phase6_data:
                log(f"   phase6_data keys: {list(phase6_data.keys())}", "INFO")
                log(f"   phase6_data has 'results': {'results' in phase6_data}", "INFO")
                log(f"   phase6_data has 'processed_texts': {'processed_texts' in phase6_data}", "INFO")

                if 'results' in phase6_data:
                    log(f"   results count: {len(phase6_data['results'])}", "INFO")
                if 'processed_texts' in phase6_data:
                    log(f"   processed_texts count: {len(phase6_data['processed_texts'])}", "INFO")

            # ===== ЕСЛИ В PHASE6 НЕТ processed_texts, ИСПОЛЬЗУЕМ PHASE5 =====
            if not phase6_data.get('processed_texts') and not phase6_data.get('results'):
                log(f"⚠️ В phase6 нет processed_texts и results, используем phase5", "WARNING")

                # Пробуем взять из phase5
                phase5_data = file_data.get('app_data', {}).get('phase5', {})
                results = phase5_data.get('results', {})

                if results:
                    log(f"✅ Найдены phase5 results: {len(results)}", "INFO")

                    # Конвертируем phase5 в формат phase6
                    phase6_data = {
                        'results': results,
                        'processed_texts': [],
                        'original_texts': [],
                        'statistics': phase5_data.get('statistics', {})
                    }

                    # Извлекаем тексты из результатов
                    for prompt_id, result in results.items():
                        if isinstance(result, dict):
                            text = result.get('edited_text') or result.get('ai_response', '')
                            if text:
                                phase6_data['processed_texts'].append(text)
                                phase6_data['original_texts'].append(text)

                    log(f"✅ Извлечено {len(phase6_data['processed_texts'])} текстов из phase5", "INFO")
                else:
                    log(f"❌ Нет данных ни в phase6, ни в phase5", "ERROR")
                    return False

            # Проверяем phase5
            phase5_data = file_data.get('app_data', {}).get('phase5', {})
            log(f"   phase5_data keys: {list(phase5_data.keys())}", "INFO")
            if phase5_data and 'results' in phase5_data:
                log(f"   phase5 results count: {len(phase5_data['results'])}", "INFO")

            # Проверяем phase5_results в корне
            phase5_results_root = file_data.get('phase5_results', {})
            log(f"   phase5_results_root count: {len(phase5_results_root)}", "INFO")

        except Exception as e:
            log(f"❌ Ошибка чтения файла: {e}", "ERROR")
            return False

        # Извлекаем результаты
        results_dict = {}

        if 'results' in phase6_data:
            results_dict = phase6_data['results']
        elif 'processed_texts' in phase6_data:
            processed_texts = phase6_data['processed_texts']
            original_texts = phase6_data.get('original_texts', [])
            metadata = phase6_data.get('texts_metadata', [])

            for idx, text in enumerate(processed_texts):
                if isinstance(text, dict):
                    prompt_id = text.get('prompt_id', f"text_{idx}")
                    results_dict[prompt_id] = text
                else:
                    prompt_id = f"text_{idx}"
                    meta = metadata[idx] if idx < len(metadata) else {}
                    results_dict[prompt_id] = {
                        'prompt_id': prompt_id,
                        'ai_response': text,
                        'edited_text': text,
                        'original_text': original_texts[idx] if idx < len(original_texts) else '',
                        'status': 'success',
                        'type': meta.get('type', 'unknown'),
                        'characteristic_name': meta.get('characteristic_name', ''),
                        'characteristic_value': meta.get('characteristic_value', ''),
                        'block_name': meta.get('block_name', ''),
                        'prompt_num': meta.get('prompt_num', 1),
                        'is_synonymized': phase6_data.get('is_synonymized', False)
                    }

        if not results_dict:
            log(f"❌ Нет результатов в phase6_data", "ERROR")
            return False

        log(f"✅ Загружено {len(results_dict)} результатов")

        fm = st.session_state.fragment_manager

        # Очищаем старые блоки
        fm.fragments = []
        fm.fragment_names = set()
        fm.fragment_properties = defaultdict(list)

        # Создаём блоки из файла
        for prompt_id, result in results_dict.items():
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except:
                    continue

            if not isinstance(result, dict) or result.get('status') == 'error':
                continue

            # Извлекаем текст с приоритетом
            text = (result.get('edited_text') or
                    result.get('ai_response') or
                    result.get('processed_text') or
                    result.get('text', ''))

            # Если текст - это результат из phase5
            if not text and 'ai_response' in result:
                text = result['ai_response']

            # Если результат - строка, используем её
            if not text and isinstance(result, str):
                text = result

            # Если ничего не нашли - пропускаем
            if not text:
                log(f"⚠️ Нет текста для prompt_id: {prompt_id}", "WARNING")
                continue

            normalized_text = self.text_processor.normalize_text(text)
            frag_name = self._generate_fragment_name(result)
            block_type = result.get('type', 'unknown')

            if block_type == 'unknown':
                if result.get('characteristic_name'):
                    block_type = 'unique' if result.get('characteristic_value') else 'regular'

            block_data = {
                'id': result.get('prompt_id', prompt_id),
                'fragment_name': frag_name,
                'original_text': normalized_text,
                'processed_text': normalized_text,
                'html_text': '',
                'block_type': block_type,
                'characteristic_name': result.get('characteristic_name'),
                'characteristic_value': result.get('characteristic_value'),
                'errors': [],
                'warnings': [],
                'manually_fixed': False,
                'special_symbols': [],
                'status': 'pending',
                'auto_corrected': False,
                'added_value': None,
                'is_synonymized': result.get('is_synonymized', False)
            }

            fm.add_block(block_data)

        # Пересчитываем ошибки
        for block in fm.fragments:
            self._recalculate_block_errors(block)

        # Создаём шаблоны
        self._create_default_templates()

        # Сохраняем
        self.save_data_to_app_state()

        log(f"✅ _load_data() завершена, загружено {len(fm.fragments)} блоков", "INFO")
        log("=" * 60, "INFO")
        return True
    def _load_from_phase5(self) -> bool:
        """Загрузка напрямую из фазы 5, если фаза 6 отсутствует"""
        try:
            ctx_data = _get_context_data(self.context, st.session_state)

            # Если есть контекст, используем его данные
            if ctx_data['has_context'] and self.context is not None:
                app_data = self.context.data
            else:
                app_data = st.session_state.app_data
            phase5_data = app_data.get('phase5', {})

            if not phase5_data:
                return False

            results = phase5_data.get('results', {})

            if not results:
                return False

            fm = st.session_state.fragment_manager

            if not fm.fragments:
                category = app_data.get('category', '')
                if category:
                    fm.category = category
                    fm.category_code = category

                loaded_count = 0
                for prompt_id, result in results.items():
                    if isinstance(result, dict) and result.get('status') == 'success':
                        text = result.get('edited_text', result.get('ai_response', ''))
                        if text:
                            block_data = {
                                'id': prompt_id,
                                'fragment_name': self._generate_fragment_name(result),
                                'original_text': text,
                                'processed_text': text,
                                'html_text': '',
                                'block_type': result.get('type', 'unknown'),
                                'characteristic_name': result.get('characteristic_name'),
                                'characteristic_value': result.get('characteristic_value'),
                                'errors': [],
                                'warnings': [],
                                'manually_fixed': False,
                                'special_symbols': [],
                                'status': 'pending',
                                'auto_corrected': False,
                                'added_value': None,
                                'is_synonymized': False
                            }
                            fm.add_block(block_data)
                            loaded_count += 1

                if loaded_count > 0:
                    st.info(f"📄 Загружено {loaded_count} блоков напрямую из фазы 5 (синонимизация не выполнялась)")
                    return True

            return False

        except Exception as e:

            return False
    def _fix_city_variables_in_text(self, text: str) -> str:
        """Дополнительная проверка и исправление городских переменных"""
        if not text:
            return text

        # Заменяем {system городе} на корректную форму если нужно
        # (убеждаемся что нет пробелов и т.д.)
        text = re.sub(r'\{system\s+городе\}', '{system городе}', text)
        text = re.sub(r'\{system\s+по_городу\}', '{system по_городу}', text)

        # Проверяем {system город} без предлога - заменяем на {system городе}
        # но только если нет предлога "в" или "по" перед ним
        text = re.sub(r'(?<![вВоПо])\{system\s+город\}', '{system городе}', text)

        return text
    def _apply_postprocessing(self, block_id: str = None):
        """Применяет постобработку с учётом правил из конфига домена"""
        self._sync_session_state_to_blocks()

        rules = self._get_postprocessing_rules()

        fm = st.session_state.fragment_manager
        registry = st.session_state.transformation_registry

        if block_id:
            blocks = [b for b in fm.fragments if b.id == block_id]
        else:
            blocks = fm.fragments.copy()

        if not blocks:
            st.warning("Нет блоков для обработки")
            return

        processed_count = 0
        total_units_removed = 0
        total_symbols_removed = 0
        details = []

        for block in blocks:
            old_text = block.processed_text
            new_text = old_text
            if rules.get("punctuation_fix", True):
                new_text = self.text_processor.fix_punctuation(new_text)

            if rules.get("city_variable_fix", True):
                new_text, _ = self.text_processor.process_city_variable(new_text)

            # Кастомные замены из конфига
            custom_replacements = rules.get("custom_replacements", [])
            for repl in custom_replacements:
                new_text = new_text.replace(repl["from"], repl["to"])
            # === Постобработка ===
            new_text = self.text_processor.fix_punctuation(new_text)
            new_text, city_errors = self.text_processor.process_city_variable(new_text)

            units = st.session_state.ui_state.get('selected_units_global', [])
            if units:
                new_text, removed = self.text_processor.remove_units(new_text, units)
                if removed:
                    block.units_removed = list(set(block.units_removed + removed))
                    total_units_removed += len(removed)

            symbols = st.session_state.ui_state.get('selected_symbols_global', [])
            if symbols:
                new_text, removed_sym, new_specials = self.text_processor.remove_special_symbols(new_text, symbols)
                if removed_sym:
                    block.symbols_removed = list(set(block.symbols_removed + removed_sym))
                    total_symbols_removed += len(removed_sym)
                block.special_symbols = new_specials

            # Обновляем текст
            block.processed_text = new_text
            block.last_modified = datetime.now()
            block.manually_fixed = True

            # Критично: обновляем session_state
            text_key = f"edit_text_{block.id}"
            if text_key in st.session_state:
                st.session_state[text_key] = new_text

            # Пересчёт ошибок ПОСЛЕ всех изменений
            self._recalculate_block_errors(block)

            # Регистрация трансформации
            trans = TextTransformation(
                block_id=block.id,
                fragment_name=block.fragment_name,
                transformation_type=TransformationType.POSTPROCESSING,
                original=old_text,
                result=new_text,
                severity=SeverityLevel.INFO if not block.errors else SeverityLevel.WARNING,
                user="system"
            )
            registry.add(trans)

            processed_count += 1
            details.append({
                'Фрагмент': block.fragment_name,
                'Ошибок после': len(block.errors),
                'Статус': block.status
            })

        # === СОХРАНЯЕМ РЕЗУЛЬТАТЫ С АКТУАЛЬНЫМИ ОШИБКАМИ ===
        st.session_state.postprocessing_results = {
            'total_processed': processed_count,
            'total_units_removed': total_units_removed,
            'total_symbols_removed': total_symbols_removed,
            'total_errors': sum(len(b.errors) for b in blocks),   # ← теперь актуально
            'details': details,
            'timestamp': datetime.now().isoformat()
        }

        self.save_data_to_app_state()

        st.success(f"✅ Постобработка выполнена для {processed_count} блоков")
        if st.session_state.postprocessing_results['total_errors'] > 0:
            st.warning(f"⚠️ Найдено {st.session_state.postprocessing_results['total_errors']} ошибок после обработки")

        st.rerun()

    def _generate_fragment_name(self, result: Dict) -> str:
        bt = result.get('type', '')
        cn = result.get('characteristic_name', '')
        cv = result.get('characteristic_value', '')
        bn = result.get('block_name', '')

        # Если тип не указан, пробуем определить
        if not bt:
            if cn:
                bt = 'regular' if cv else 'unique'
            else:
                bt = 'other'

        # Получаем категорию из app_data
        if 'app_data' in st.session_state:
            cat = st.session_state.app_data.get('category', 'Без_категории')
        else:
            cat = 'Без_категории'

        # Очищаем категорию от лишних символов
        cat_clean = re.sub(r'[^\w\s-]', '', cat).strip()
        cat_clean = re.sub(r'[\s-]+', '_', cat_clean)

        # ❌ УБИРАЕМ ПРЕФИКС syn_ - он не нужен
        # prefix = "syn_" if result.get('is_synonymized') else ""

        if bt == 'regular' and cn:
            cn_clean = re.sub(r'[^\w\s-]', '', cn).strip()
            cn_clean = re.sub(r'[\s-]+', '_', cn_clean)
            return f"{cat_clean}_{cn_clean}"  # ← без prefix

        elif bt == 'unique' and cn and cv:
            cn_clean = re.sub(r'[^\w\s-]', '', cn).strip()
            cn_clean = re.sub(r'[\s-]+', '_', cn_clean)
            cv_clean = re.sub(r'[^\w\s-]', '', cv.lower())
            cv_clean = re.sub(r'[\s-]+', '_', cv_clean)[:30].strip('_')
            return f"{cat_clean}_{cn_clean}_{cv_clean}"  # ← без prefix

        else:
            if bn:
                bn_clean = re.sub(r'[^\w\s-]', '', bn.lower())
                bn_clean = re.sub(r'[\s-]+', '_', bn_clean)[:30].strip('_')
                return f"{cat_clean}_{bn_clean}"  # ← без prefix
            return f"{cat_clean}_блок_{uuid.uuid4().hex[:8]}"  # ← без prefix

    # ------------------------------------------------------------------
    #                     УПРАВЛЕНИЕ ЕДИНИЦАМИ
    # ------------------------------------------------------------------
    def _scan_units_in_texts(self) -> List[str]:
        fm = st.session_state.fragment_manager
        all_units = set()
        for frag in fm.fragments:
            units_in_text = self.text_processor.find_units_in_text(frag.original_text)
            all_units.update(units_in_text)
        return sorted(all_units)



    # ------------------------------------------------------------------
    #                     УПРАВЛЕНИЕ СПЕЦСИМВОЛАМИ
    # ------------------------------------------------------------------
    def _scan_special_symbols_in_texts(self) -> List[str]:
        fm = st.session_state.fragment_manager
        all_symbols = set()
        for frag in fm.fragments:
            sym_list = self.text_processor._find_special_symbols(frag.original_text)
            for sym, _, _ in sym_list:
                all_symbols.add(sym)
        return sorted(all_symbols)

    def _manage_units_and_symbols(self):
        with st.sidebar.expander("⚙️ Единицы и спецсимволы", expanded=False):
            st.write("### 📏 Единицы измерения, найденные в текстах")
            found_units = st.session_state.get('found_units', [])
            if found_units:
                # ✅ ФИКС: фильтруем выбранные единицы
                current_selected = st.session_state.ui_state.get('selected_units_global', [])
                valid_selected = [u for u in current_selected if u in found_units]

                if len(valid_selected) != len(current_selected):
                    st.session_state.ui_state['selected_units_global'] = valid_selected

                selected_units = st.multiselect(
                    "Выберите единицы для удаления:",
                    found_units,
                    default=valid_selected,
                    key="selected_units_global_widget"
                )
                st.session_state.ui_state['selected_units_global'] = selected_units
            else:
                st.info("В текстах не найдено стандартных единиц измерения.")
                st.session_state.ui_state['selected_units_global'] = []

            st.divider()
            new_unit = st.text_input("Добавить свою единицу:")
            if st.button("➕ Добавить единицу", use_container_width=True):
                if new_unit and new_unit not in st.session_state.units_manager['units']:
                    st.session_state.units_manager['units'].append(new_unit)
                    self.text_processor.add_unit_to_remove(new_unit)
                    st.session_state.found_units = self._scan_units_in_texts()
                    st.rerun()

            st.divider()
            st.write("### ⚡ Специальные символы, найденные в текстах")
            found_symbols = st.session_state.get('found_special_symbols', [])
            if found_symbols:
                # ✅ ФИКС: фильтруем выбранные символы
                current_selected_sym = st.session_state.ui_state.get('selected_symbols_global', [])
                valid_selected_sym = [s for s in current_selected_sym if s in found_symbols]

                if len(valid_selected_sym) != len(current_selected_sym):
                    st.session_state.ui_state['selected_symbols_global'] = valid_selected_sym

                selected_symbols = st.multiselect(
                    "Выберите символы для удаления:",
                    found_symbols,
                    default=valid_selected_sym,
                    key="selected_symbols_global_widget"
                )
                st.session_state.ui_state['selected_symbols_global'] = selected_symbols
            else:
                st.info("Специальные символы не найдены.")
                st.session_state.ui_state['selected_symbols_global'] = []

            st.divider()
            if st.button("🗑️ Удалить единицы и символы из ВСЕХ блоков", use_container_width=True):
                units = st.session_state.ui_state.get('selected_units_global', [])
                symbols = st.session_state.ui_state.get('selected_symbols_global', [])
                if units:
                    self._apply_unit_removal(units_to_remove=units)
                if symbols:
                    self._apply_special_symbol_removal(symbols_to_remove=symbols)
                st.rerun()

    # ------------------------------------------------------------------
    #                     ОПЕРАЦИИ НАД БЛОКАМИ (ИНДИВИДУАЛЬНЫЕ И ОБЩИЕ)
    # ------------------------------------------------------------------
    def _apply_variable_replacement(self, block_id: str = None):
        """Замена переменных (только замена существующих скобок)."""
        self._sync_session_state_to_blocks()
        with st.spinner("🔄 Замена переменных... Пожалуйста, подождите"):

            fm = st.session_state.fragment_manager
            registry = st.session_state.transformation_registry

            if block_id:
                blocks = [next((b for b in fm.fragments if b.id == block_id), None)]
                blocks = [b for b in blocks if b is not None]
            else:
                blocks = fm.fragments

            if not blocks:
                st.info("Нет блоков для обработки")
                return

            all_replacements = []
            errors_occurred = False

            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, block in enumerate(blocks):
                progress = (idx + 1) / len(blocks)
                progress_bar.progress(progress)
                status_text.text(f"Обработка {idx + 1} из {len(blocks)}: {block.fragment_name}")

                result = self.text_processor.replace_variables(
                    text=block.processed_text,
                    block_type=block.block_type,
                    char_name=block.characteristic_name,
                    char_value=block.characteristic_value
                )

                old_text = block.processed_text
                block.processed_text = result['processed_text']
                block.processed_text = self.text_processor.normalize_text(block.processed_text)
                block.special_symbols = result['special_symbols']
                text_key = f"edit_text_{block.id}"
                st.session_state[text_key] = block.processed_text
                self._recalculate_block_errors(block)
                for err in result['errors']:
                    if not any(e.get('type') == err.get('type') and e.get('message') == err.get('message')
                               for e in block.errors):
                        block.errors.append(err)
                        block.status = 'error'
                        trans = TextTransformation(
                            block_id=block.id,
                            fragment_name=block.fragment_name,
                            transformation_type=TransformationType.ERROR,
                            original="",
                            result="",
                            meta={'message': err},
                            severity=SeverityLevel.ERROR,
                            user="system"
                        )
                        registry.add(trans)
                        errors_occurred = True

                block.last_modified = datetime.now()

                # ✅ ДОБАВЛЯЕМ: Пересчёт ошибок после замены переменных
                self._recalculate_block_errors(block)

                for repl in result['replacements']:
                    trans = TextTransformation(
                        block_id=block.id,
                        fragment_name=block.fragment_name,
                        transformation_type=TransformationType.VARIABLE_REPLACE,
                        original=repl['original'],
                        result=repl['replacement'],
                        start=repl['position'][0],
                        end=repl['position'][1],
                        severity=SeverityLevel.INFO,
                        user="user"
                    )
                    registry.add(trans)
                    all_replacements.append({
                        'block': block.fragment_name,
                        'original': repl['original'],
                        'replacement': repl['replacement']
                    })

            progress_bar.empty()
            status_text.empty()

            if all_replacements:
                st.success(f"✅ Переменные заменены в {len(set(r['block'] for r in all_replacements))} блоках")
                if len(all_replacements) <= 20:
                    df = pd.DataFrame(all_replacements)
                    st.dataframe(df, use_container_width=True)
                if block_id is None:
                    st.session_state.variables_replaced = True
            else:
                st.info("Нет замен для выполнения")

            if errors_occurred:
                st.error("❌ При замене возникли ошибки. Проверьте вкладку 'Проблемы'.")
            # ✅ ИСПРАВЛЕНО: вызываем self.save_data_to_app_state()
            self.save_data_to_app_state()
            st.rerun()
    def _auto_insert_regular_blocks(self, block_id: str = None):
        self._sync_session_state_to_blocks()
        with st.spinner("🔄 Автоисправление regular-блоков... Пожалуйста, подождите"):

            fm = st.session_state.fragment_manager
            registry = st.session_state.transformation_registry

            if block_id:
                blocks = [next((b for b in fm.fragments if b.id == block_id), None)]
                blocks = [b for b in blocks if b is not None and b.block_type == 'regular']
            else:
                blocks = [b for b in fm.fragments if b.block_type == 'regular']

            if not blocks:
                st.info("Нет regular-блоков для обработки")
                return

            inserted = 0
            errors_found = 0

            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, block in enumerate(blocks):
                progress = (idx + 1) / len(blocks)
                progress_bar.progress(progress)
                status_text.text(f"Обработка {idx + 1} из {len(blocks)}: {block.fragment_name}")

                if not block.characteristic_value:
                    continue

                new_text, added, found_value, has_error = self.text_processor.auto_insert_bracket(
                    block.processed_text, block.characteristic_value
                )

                if has_error:
                    error_msg = f"Значение '{block.characteristic_value}' не найдено в тексте regular-блока"
                    block.errors.append({
                        'type': ErrorType.MISSING_BRACKET.value,
                        'message': error_msg
                    })
                    block.status = 'error'
                    block.last_modified = datetime.now()

                    trans = TextTransformation(
                        block_id=block.id,
                        fragment_name=block.fragment_name,
                        transformation_type=TransformationType.ERROR,
                        original="",
                        result="",
                        meta={'error': error_msg, 'expected_value': block.characteristic_value},
                        severity=SeverityLevel.ERROR,
                        user="system"
                    )
                    registry.add(trans)
                    errors_found += 1

                elif added:
                    block.processed_text = new_text
                    block.processed_text = self.text_processor.normalize_text(block.processed_text)
                    block.last_modified = datetime.now()
                    block.auto_corrected = True
                    block.added_value = found_value
                    text_key = f"edit_text_{block.id}"
                    st.session_state[text_key] = block.processed_text

                    self._recalculate_block_errors(block)
                    block.errors = [e for e in block.errors
                                    if e.get('type') != ErrorType.MISSING_BRACKET.value]
                    block.status = 'processed'

                    # ✅ ДОБАВЛЯЕМ: Пересчёт ошибок после автоисправления
                    self._recalculate_block_errors(block)

                    trans = TextTransformation(
                        block_id=block.id,
                        fragment_name=block.fragment_name,
                        transformation_type=TransformationType.AUTO_INSERT,
                        original="",
                        result=f"[{found_value}]",
                        meta={'value': found_value, 'method': 'wrap'},
                        severity=SeverityLevel.INFO,
                        user="system"
                    )
                    registry.add(trans)
                    inserted += 1

                if idx % 5 == 0:
                    time.sleep(0.01)

            progress_bar.empty()
            status_text.empty()

            if inserted:
                st.success(f"✅ Значения обёрнуты в скобки в {inserted} regular-блоках")
            if errors_found:
                st.error(f"❌ В {errors_found} regular-блоках значение не найдено в тексте")
            if not inserted and not errors_found:
                st.info("Нет regular-блоков, требующих обработки")
            # ✅ ИСПРАВЛЕНО: вызываем self.save_data_to_app_state()
            self.save_data_to_app_state()
            st.rerun()

    def _apply_unit_removal(self, block_id: str = None, units_to_remove: List[str] = None):
        if not units_to_remove:
            st.warning("Не выбрано ни одной единицы для удаления.")
            return

        fm = st.session_state.fragment_manager
        registry = st.session_state.transformation_registry
        blocks = [next((b for b in fm.fragments if b.id == block_id), None)] if block_id else fm.fragments
        blocks = [b for b in blocks if b is not None]

        all_removed = []

        for block in blocks:
            cleaned, removed = self.text_processor.remove_units(block.processed_text, units_to_remove)
            if removed:
                block.processed_text = cleaned
                block.processed_text = self.text_processor.normalize_text(block.processed_text)
                block.last_modified = datetime.now()
                trans = TextTransformation(
                    block_id=block.id,
                    fragment_name=block.fragment_name,
                    transformation_type=TransformationType.UNIT_REMOVED,
                    original="",
                    result="",
                    meta={'removed_units': list(set(removed))},
                    severity=SeverityLevel.INFO,
                    user="user"
                )
                registry.add(trans)
                all_removed.extend([(block.fragment_name, unit) for unit in set(removed)])
            if removed:
                block.units_removed = list(set(removed))
        if all_removed:
            st.success(f"✅ Удалены единицы из {len(set(b for b,_ in all_removed))} блоков")
            df = pd.DataFrame(all_removed, columns=["Фрагмент", "Единица"]).drop_duplicates()
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Единицы для удаления не найдены в текстах.")
        self.save_data_to_app_state()
        st.rerun()

    def _apply_special_symbol_removal(self, block_id: str = None, symbols_to_remove: List[str] = None):
        if not symbols_to_remove:
            st.warning("Не выбрано ни одного символа для удаления.")
            return

        fm = st.session_state.fragment_manager
        registry = st.session_state.transformation_registry
        blocks = [next((b for b in fm.fragments if b.id == block_id), None)] if block_id else fm.fragments
        blocks = [b for b in blocks if b is not None]

        all_removed = []

        for block in blocks:
            cleaned, removed, new_specials = self.text_processor.remove_special_symbols(
                block.processed_text, symbols_to_remove
            )
            if removed:
                block.processed_text = cleaned
                block.processed_text = self.text_processor.normalize_text(block.processed_text)
                block.special_symbols = new_specials
                block.last_modified = datetime.now()
                trans = TextTransformation(
                    block_id=block.id,
                    fragment_name=block.fragment_name,
                    transformation_type=TransformationType.SPECIAL_SYMBOL_REMOVED,
                    original="",
                    result="",
                    meta={'removed_symbols': list(set(removed))},
                    severity=SeverityLevel.INFO,
                    user="user"
                )
                registry.add(trans)
                all_removed.extend([(block.fragment_name, sym) for sym in set(removed)])
            if removed:
                block.symbols_removed = list(set(removed))
        if all_removed:
            st.success(f"✅ Удалены спецсимволы из {len(set(b for b,_ in all_removed))} блоков")
            df = pd.DataFrame(all_removed, columns=["Фрагмент", "Символ"]).drop_duplicates()
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Выбранные символы не найдены в текстах.")
        self.save_data_to_app_state()
        st.rerun()

    def _apply_generate_html(self, block_id: str = None):
        self._sync_session_state_to_blocks()  # <-- ДОБАВИТЬ ЭТУ СТРОКУ
        fm = st.session_state.fragment_manager
        registry = st.session_state.transformation_registry
        blocks = [next((b for b in fm.fragments if b.id == block_id), None)] if block_id else fm.fragments
        blocks = [b for b in blocks if b is not None]

        generated = 0
        total_errors = 0

        for block in blocks:
            html, errors = self.text_processor.convert_to_html(block.processed_text, block.id)

            html_errors = self.text_processor.validate_html_structure(html, block.fragment_name)
            errors.extend(html_errors)

            block.html_text = html
            block.last_modified = datetime.now()
            block.html_generated = True

            # ДОБАВИТЬ: синхронизируем с session_state
            html_key = f"edit_html_{block.id}"
            st.session_state[html_key] = html

            for err in errors:
                if not any(e.get('type') == err['type'] and e.get('message') == err['message']
                           for e in block.errors):
                    block.errors.append(err)
                    block.status = 'error'
                    total_errors += 1

            trans = TextTransformation(
                block_id=block.id,
                fragment_name=block.fragment_name,
                transformation_type=TransformationType.HTML_GENERATION,
                original=block.processed_text,
                result=html,
                meta={'errors_count': len(errors)},
                severity=SeverityLevel.WARNING if errors else SeverityLevel.INFO,
                user="system"
            )
            registry.add(trans)
            generated += 1

        # ... остальной код

        if total_errors:
            st.error(f"❌ Найдено {total_errors} ошибок форматирования или структуры HTML")
        st.success(f"🌐 HTML сгенерирован для {generated} блоков")
        if generated == 1 and block_id:
            st.markdown(blocks[0].html_text, unsafe_allow_html=True)
        self.save_data_to_app_state()
        st.rerun()

    def _check_all_errors(self):
        """Полная проверка ошибок во всех блоках."""
        fm = st.session_state.fragment_manager
        if not fm:
            st.warning("Нет блоков для проверки")
            return

        with st.spinner("Проверка ошибок..."):
            for block in fm.fragments:
                self._recalculate_block_errors(block)

            self.save_data_to_app_state()

            total_errors = sum(len(b.errors) for b in fm.fragments)
            blocks_with_errors = sum(1 for b in fm.fragments if b.errors)

            if total_errors > 0:
                st.error(f"❌ Найдено {total_errors} ошибок в {blocks_with_errors} блоках")
            else:
                st.success("✅ Ошибок не найдено")

            st.rerun()

    # ------------------------------------------------------------------
    #                     СБРОС СОСТОЯНИЯ
    # ------------------------------------------------------------------
    def _reset_state(self):
        """Полный и надёжный сброс фазы 7 (очищает всё и загружает заново из фазы 6)"""

        # ===== ДОБАВИТЬ ОЧИСТКУ ID ПРОЕКТА =====
        st.session_state.phase7_last_loaded_project = None
        # ===== КОНЕЦ ДОБАВЛЕНИЯ =====

        # 1. Полностью очищаем fragment_manager
        if 'fragment_manager' in st.session_state:
            fm = st.session_state.fragment_manager
            fm.fragments = []
            fm.fragment_names = set()
            fm.fragment_properties = defaultdict(list)
            fm.templates = {}


        # 2. Очищаем все связанные session_state ключи
        keys_to_clear = [
            'fragment_manager',
            'transformation_registry',
            'postprocessing_results',
            'variables_replaced',
            'phase7_initialized',
            'found_units',
            'found_special_symbols',
            'ui_state',
        ]

        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]

        # 3. Очищаем все динамические ключи (text_area, html и т.д.)
        dynamic_keys = [key for key in st.session_state.keys()
                        if key.startswith('edit_text_') or
                        key.startswith('edit_html_') or
                        key.startswith('inline_editor_text_') or
                        key.startswith('selected_units_global_widget') or
                        key.startswith('selected_symbols_global_widget')]

        for key in dynamic_keys:
            if key in st.session_state:
                del st.session_state[key]

        # 4. Очищаем данные в app_data для текущего проекта
        current_project_id = st.session_state.get('current_project_id', 'default')

        if 'phase7_projects_data' in st.session_state.app_data:
            if current_project_id in st.session_state.app_data['phase7_projects_data']:
                del st.session_state.app_data['phase7_projects_data'][current_project_id]

        if 'phase7' in st.session_state.app_data:
            st.session_state.app_data['phase7'] = {}

        # 5. Очищаем в DomainManager
        if 'domain_manager' in st.session_state:
            dm = st.session_state.domain_manager
            dm.save_phase_data(7, {})

        # 6. Создаём новый fragment_manager
        st.session_state.fragment_manager = FragmentManager("Без_категории")

        # 7. Заново инициализируем
        self._init_session_state()
        self._init_ui_state()

        # 8. Очищаем старые шаблоны
        if 'fragment_manager' in st.session_state:
            st.session_state.fragment_manager.templates.clear()

        # 9. Загружаем свежие данные из фазы 6
        success = self._load_data()

        if success:
            fm = st.session_state.fragment_manager
            # Пересчитываем ошибки
            for block in fm.fragments:
                self._recalculate_block_errors(block)

            # Создаём шаблоны
            self._create_default_templates()

            # Сканируем единицы и символы
            st.session_state.found_units = self._scan_units_in_texts()
            st.session_state.found_special_symbols = self._scan_special_symbols_in_texts()

            # Устанавливаем флаг инициализации
            st.session_state.phase7_initialized = True

            st.success(f"✅ Фаза 7 полностью сброшена и загружена из фазы 6 ({len(fm.fragments)} блоков)")
        else:
            st.error("❌ Не удалось загрузить данные из фазы 6")
            st.session_state.phase7_initialized = False

        time.sleep(1)
        st.rerun()

    def _add_reset_button(self):
        with st.sidebar:
            st.divider()
            st.write("### 🛑 Управление состоянием")

            col1, col2 = st.columns(2)
            with col1:
                confirm = st.checkbox("Подтвердить сброс", key="confirm_reset_full")
            with col2:
                if st.button("🔄 Сбросить фазу 7", type="secondary", use_container_width=True):
                    if confirm:
                        self._reset_state()
                    else:
                        st.warning("Поставьте галочку для подтверждения")
    def _add_force_save_button(self):
        """Кнопка принудительного сохранения всех данных"""
        with st.sidebar:
            st.divider()
            if st.button("💾 ПРИНУДИТЕЛЬНО СОХРАНИТЬ ВСЁ", type="primary", use_container_width=True):
                fm = st.session_state.get('fragment_manager')
                if fm:
                    # Принудительно обновляем все блоки
                    for block in fm.fragments:
                        block.last_modified = datetime.now()
                        # Синхронизируем text_area
                        text_key = f"edit_text_{block.id}"
                        if text_key in st.session_state:
                            block.processed_text = st.session_state[text_key]
                        html_key = f"edit_html_{block.id}"
                        if html_key in st.session_state:
                            block.html_text = st.session_state[html_key]

                    self.save_data_to_app_state(st.session_state.get('app_state'))
                    st.success("✅ Все данные принудительно сохранены!")
                    time.sleep(0.5)
                    st.rerun()
    # ------------------------------------------------------------------
    #                     ОСНОВНОЙ ИНТЕРФЕЙС
    # ------------------------------------------------------------------
    def display_main_interface(self):
        if 'app_data' not in st.session_state:
            st.error("❌ Нет данных приложения.")
            return

        # ✅ ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ UI
        if st.session_state.get('_force_ui_update', False):
            st.session_state._force_ui_update = False

        # ✅ НОВАЯ ПАНЕЛЬ С КНОПКОЙ ОБНОВЛЕНИЯ
        with st.container():
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown("---")

            with col2:
                if st.button("🔄 Обновить шаблоны и данные экспорта", key="refresh_templates_main", type="primary", use_container_width=True):
                    if self.refresh_templates_and_export():
                        time.sleep(0.5)
                        st.rerun()

            with col3:
                if st.button("📊 Статистика", use_container_width=True):
                    fm = st.session_state.fragment_manager
                    '''st.info(f"""
                    📊 **Статистика:**
                    - Блоков: {len(fm.fragments)}
                    - Фрагментов: {len(fm.fragment_names)}
                    - Шаблонов: {len(fm.templates)}
                    - Ошибок: {sum(1 for b in fm.fragments if b.errors)}
                    """)'''

        st.markdown("---")

        # ... остальной код

        # === Проверка изменений в phase6 ===
        if st.session_state.get('phase6_changed', False):
            st.warning("Обнаружены изменения в фазе 6. Рекомендуется обновить данные.")
            if st.button("🔄 Обновить сейчас"):
                self.refresh_from_phase6()
                st.session_state.phase6_changed = False  # сброс флага

        # ==================== КРИТИЧЕСКИЙ ФИКС ====================
        if not st.session_state.get('phase7_initialized', False):
            success = self._load_data()
            if success:
                st.session_state.phase7_initialized = True
                self._migrate_fragments()
                self._create_default_templates()
                st.session_state.found_units = self._scan_units_in_texts()
                st.session_state.found_special_symbols = self._scan_special_symbols_in_texts()

                # ✅ ДОБАВЛЯЕМ: Пересчёт ошибок после загрузки
                fm = st.session_state.fragment_manager
                for block in fm.fragments:
                    self._recalculate_block_errors(block)

                st.success("✅ Фаза 7 загружена", icon="🎉")
            else:
                st.error("Не удалось загрузить данные для фазы 7")
                return
        # =========================================================

        fm = st.session_state.fragment_manager
        current_domain = self.dm.get_current_domain()
        last_domain = st.session_state.get('_last_domain', None)

        if current_domain != last_domain:
            self._on_domain_change()
            st.session_state._last_domain = current_domain
        # Принудительная синхронизация ПЕРЕД отрисовкой
        self._sync_session_state_to_blocks()
        self._sync_html_to_session_state()

        # ... остальной код без изменений
        # Сканируем единицы и спецсимволы в текстах
        st.session_state.found_units = self._scan_units_in_texts()
        st.session_state.found_special_symbols = self._scan_special_symbols_in_texts()

        self._display_top_panel()
        # Кнопка сброса состояния

        # Общие кнопки для массовых операций
        if 'variables_replaced' not in st.session_state:
            st.session_state.variables_replaced = False

        # ---------- Этап 1: Первичная обработка ----------
        with st.container():
            st.subheader("🛠️ Постобработка")
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔧 1. Автоисправить regular-блоки", use_container_width=True):
                    self._auto_insert_regular_blocks()

            with col2:

                if st.button("🔄 2. Заменить переменные во всех блоках",
                             use_container_width=True):
                    st.warning("Выполняется замена переменных...")
                    self._apply_variable_replacement()
                    st.session_state.variables_replaced = True
                    st.rerun()

        st.markdown("---")

        # Этап 2: Постобработка (появляется после замены переменных)
        if st.session_state.variables_replaced:
            with st.container():
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("🧹 3. Выполнить постобработку всех блоков", use_container_width=True):
                        self._apply_postprocessing()
                with col2:
                    if st.button("🌐 4. Сгенерировать HTML для всех блоков", use_container_width=True):
                        self._apply_generate_html()



                # Здесь можно показывать результаты последней постобработки, если они есть
                if 'postprocessing_results' in st.session_state:
                    self._display_postprocessing_results()

        st.markdown("---")


        self._sync_session_state_to_blocks()
        tab_options = ["🏷️ Фрагменты", "📋 История замен", "🧩 Шаблоны и HTML", "📤 Экспорт отчета"]
        default_tab = st.session_state.ui_state.get('active_tab', tab_options[0])
        if default_tab not in tab_options:
            default_tab = tab_options[0]

        active_tab = st.radio(
            "Выберите вкладку",
            tab_options,
            horizontal=True,
            label_visibility="collapsed",
            index=tab_options.index(default_tab),
            key="main_tabs"
        )

        # ✅ ПРИ ПЕРЕКЛЮЧЕНИИ ВКЛАДКИ - СОХРАНЯЕМ ДАННЫЕ
        old_tab = st.session_state.ui_state.get('active_tab')
        if old_tab != active_tab:
            self._sync_session_state_to_blocks()      # ← обязательно
            self.save_data_to_app_state(st.session_state.get('app_state'))  # ← сохраняем

        st.session_state.ui_state['active_tab'] = active_tab

        # Отображаем выбранную вкладку
        if active_tab == tab_options[0]:
            self._display_fragments_interface()
        elif active_tab == tab_options[1]:
            self._display_transformations_interface()
        elif active_tab == tab_options[2]:
            self._display_templates_interface()
        elif active_tab == tab_options[3]:
            self._display_export_interface()

    def _display_top_panel(self):
        with st.sidebar:
            st.header("⚙️ Настройки обработки")

            # ✅ КНОПКА ОБНОВЛЕНИЯ
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Обновить шаблоны", key="refresh_templates_sidebar", use_container_width=True, type="primary"):
                    if self.refresh_templates_and_export():
                        time.sleep(0.5)
                        st.rerun()

            with col2:
                if st.button("📊 Статистика", key="show_stats_sidebar", use_container_width=True):
                    fm = st.session_state.fragment_manager
                    st.info(f"📊 Блоков: {len(fm.fragments)}, Шаблонов: {len(fm.templates)}")

            st.markdown("---")

            # 📏 Единицы измерения
            with st.expander("📏 Единицы измерения", expanded=True):
                found_units = st.session_state.get('found_units', [])
                current_selected = st.session_state.ui_state.get('selected_units_global', [])
                valid_selected = [u for u in current_selected if u in found_units]

                if len(valid_selected) != len(current_selected):
                    st.session_state.ui_state['selected_units_global'] = valid_selected

                if found_units:
                    selected_units = st.multiselect(
                        "Выберите единицы для удаления:",
                        found_units,
                        default=valid_selected,
                        key="selected_units_global_widget"
                    )
                    st.session_state.ui_state['selected_units_global'] = selected_units
                else:
                    st.info("В текстах не найдено стандартных единиц.")
                    st.session_state.ui_state['selected_units_global'] = []

                st.divider()
                new_unit = st.text_input("Добавить свою единицу:", key="new_unit_input")
                if st.button("➕ Добавить единицу", key="add_unit_button", use_container_width=True):
                    if new_unit and new_unit not in st.session_state.units_manager['units']:
                        st.session_state.units_manager['units'].append(new_unit)
                        self.text_processor.add_unit_to_remove(new_unit)
                        st.session_state.found_units = self._scan_units_in_texts()
                        st.rerun()

            # ⚡ Специальные символы
            with st.expander("⚡ Специальные символы", expanded=True):
                found_symbols = st.session_state.get('found_special_symbols', [])
                current_selected_sym = st.session_state.ui_state.get('selected_symbols_global', [])
                valid_selected_sym = [s for s in current_selected_sym if s in found_symbols]

                if len(valid_selected_sym) != len(current_selected_sym):
                    st.session_state.ui_state['selected_symbols_global'] = valid_selected_sym

                if found_symbols:
                    selected_symbols = st.multiselect(
                        "Выберите символы для удаления:",
                        found_symbols,
                        default=valid_selected_sym,
                        key="selected_symbols_global_widget"
                    )
                    st.session_state.ui_state['selected_symbols_global'] = selected_symbols
                else:
                    st.info("Специальные символы не найдены.")
                    st.session_state.ui_state['selected_symbols_global'] = []

            st.divider()
            st.markdown("**🗑️ Удаление из всех блоков**")

            if st.button(
                    "🗑️ УДАЛИТЬ ВЫБРАННЫЕ ЕДИНИЦЫ И СИМВОЛЫ ИЗ ВСЕХ БЛОКОВ",
                    key="remove_units_symbols_all",
                    use_container_width=True,
                    type="secondary"
            ):
                units = st.session_state.ui_state.get('selected_units_global', [])
                symbols = st.session_state.ui_state.get('selected_symbols_global', [])

                if not units and not symbols:
                    st.warning("⚠️ Ничего не выбрано для удаления")
                else:
                    if units:
                        self._apply_unit_removal(units_to_remove=units)
                    if symbols:
                        self._apply_special_symbol_removal(symbols_to_remove=symbols)

                    st.session_state.found_units = self._scan_units_in_texts()
                    st.session_state.found_special_symbols = self._scan_special_symbols_in_texts()

                    st.success("✅ Удалено из всех блоков")
                    st.rerun()

            st.divider()

            # Кнопка сброса состояния
            confirm = st.checkbox("Подтвердите сброс", key="top_reset_confirm")
            if st.button("🔄 Сбросить состояние фазы 6", key="reset_phase6_top", use_container_width=True, disabled=not confirm):
                self._reset_state()
    def _show_updated_stats(self):
        """Показывает статистику после обновления"""
        fm = st.session_state.fragment_manager

        if not fm.fragments:
            st.warning("⚠️ Нет данных для отображения")
            return

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("📦 Блоков", len(fm.fragments))

        with col2:
            st.metric("🏷️ Фрагментов", len(fm.fragment_names))

        with col3:
            st.metric("🧩 Шаблонов", len(fm.templates))

        with col4:
            errors = sum(1 for b in fm.fragments if b.errors)
            st.metric("❌ Ошибок", errors, delta="⚠️" if errors else "✅")

        # Детали по шаблонам (без кнопок)
        if fm.templates:
            with st.expander("📋 Детали шаблонов"):
                for tpl_name, tpl in fm.templates.items():
                    st.write(f"**{tpl_name}** ({len(tpl.order)} фрагментов)")
                    st.write(f"  → {' → '.join(tpl.order[:5])}{' ...' if len(tpl.order) > 5 else ''}")
                    if tpl.is_default:
                        st.write("  ⭐ По умолчанию")
    def _add_refresh_button_to_sidebar(self):
        """Добавляет кнопку обновления в sidebar"""
        with st.sidebar:
            st.divider()
            st.markdown("### 🔄 Управление данными")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Обновить шаблоны", key="refresh_templates_sidebar24556", use_container_width=True, type="primary"):
                    if self.refresh_templates_and_export():
                        time.sleep(0.5)
                        st.rerun()

            with col2:
                if st.button("🗑️ Сбросить", use_container_width=True):
                    if st.checkbox("Подтвердить сброс", key="sidebar_reset_confirm"):
                        self._reset_state()
                        st.rerun()
    # ------------------------------------------------------------------
    #                        ЭКСПОРТ
    # ------------------------------------------------------------------
    def _display_export_interface(self):
        self._sync_session_state_to_blocks()
        self.save_data_to_app_state(st.session_state.get('app_state'))

        st.header("📤 Экспорт отчета")

        # ✅ КНОПКА ОБНОВЛЕНИЯ ДАННЫХ ЭКСПОРТА
        col1, col2 = st.columns([4, 1])
        with col1:
            fm = st.session_state.fragment_manager
            st.write(f"**Готово к экспорту:** {len(fm.fragments)} блоков, {len(fm.fragment_names)} фрагментов")
        with col2:
            if st.button("🔄 Обновить данные", key="refresh_export_data", use_container_width=True, type="secondary"):
                if self.refresh_templates_and_export():
                    time.sleep(0.5)
                    st.rerun()

        st.markdown("---")

        fm = st.session_state.fragment_manager

        if not fm.fragments:
            st.info("Нет данных для экспорта")
            return

            # ... остальной код экспорта

        # ✅ БЕРЁМ КОД КАТЕГОРИИ ПРЯМО ИЗ fragment_manager
        cat_code = fm.category_code or "без_кода"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        st.divider()
        st.subheader("🔍 Экспорт для проверки (входные данные фазы 5 + текущее состояние)")

        phase5_data = st.session_state.app_data.get('phase5', {})
        if not phase5_data:
            st.warning("Данные фазы 5 отсутствуют, экспорт будет неполным.")

        col_json, col_xlsx = st.columns(2)
        with col_json:
            if st.button("📥 JSON (проверка)", use_container_width=True):
                json_data = ExportManager.export_verification_json(fm, phase5_data)
                st.download_button(
                    "⬇️ Сохранить JSON",
                    data=json_data,
                    file_name=f"проверка_{cat_code}_{ts}.json",
                    mime="application/json",
                    use_container_width=True
                )
        with col_xlsx:
            if st.button("📥 Excel (проверка)", use_container_width=True):
                excel_data = ExportManager.export_verification_excel(fm, phase5_data)
                st.download_button(
                    "⬇️ Сохранить Excel",
                    data=excel_data,
                    file_name=f"проверка_{cat_code}_{ts}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

        fmt = st.radio("Формат:", ["XLSX (Excel)", "JSON"], horizontal=True)
        use_html = st.checkbox("Использовать HTML версию", value=st.session_state.ui_state.get('show_html', True))
        st.session_state.ui_state['show_html'] = use_html

        # ✅ ПРИНУДИТЕЛЬНО СОЗДАЁМ АКТУАЛЬНЫЙ template_data С ТЕКУЩИМ КОДОМ
        default_tmpl = fm.get_default_template()
        if default_tmpl is None:
            st.warning("Нет созданных шаблонов → экспорт без шаблона")
            default_tmpl = {
                'category_code': fm.category_code,  # ← ЯВНО БЕРЁМ ИЗ fm
                'template': '',
                'order': [],
                'template_name': 'Нет шаблона'
            }
        else:
            # ✅ ОБНОВЛЯЕМ КОД КАТЕГОРИИ В ШАБЛОНЕ
            default_tmpl['category_code'] = fm.category_code

        if fmt == "XLSX (Excel)":
            col1, col2, col3 = st.columns(3)
            col1.metric("Фрагментов", len(fm.fragment_names))
            col2.metric("Блоков", len(fm.fragments))
            err_cnt = sum(len(f.errors) for f in fm.fragments)
            col3.metric("Ошибок", err_cnt, delta_color="inverse")

            if st.button("📥 Экспорт в Excel", type="primary", use_container_width=True):
                with st.spinner("Создание Excel..."):
                    excel = ExportManager.export_to_excel(
                        fm,
                        template_data=default_tmpl,   # ← ПЕРЕДАЁМ ОБНОВЛЁННЫЙ
                        use_html=use_html
                    )
                    st.download_button(
                        "⬇️ Скачать",
                        data=excel,
                        file_name=f"отчет_{cat_code}_{ts}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
        else:
            st.subheader("Экспорт в JSON")
            fragments_data = [f.to_dict() for f in fm.fragments]
            export_data = {
                'timestamp': datetime.now().isoformat(),
                'category': fm.category_code,  # ← БЕРЁМ ИЗ fm
                'template': default_tmpl['template'],
                'fragments': fragments_data,
                'statistics': {
                    'total_fragments': len(fm.fragment_names),
                    'total_blocks': len(fm.fragments),
                    'error_blocks': sum(1 for f in fm.fragments if f.errors),
                    'warning_blocks': sum(1 for f in fm.fragments if f.warnings),
                    'template_order': default_tmpl['order']
                }
            }
            json_data = json.dumps(export_data, ensure_ascii=False, indent=2, default=str)
            st.download_button(
                "📥 Скачать JSON",
                data=json_data,
                file_name=f"отчет_{cat_code}_{ts}.json",
                mime="application/json",
                use_container_width=True
            )
        # ------------------------------------------------------------------
    #                     ФРАГМЕНТЫ (СПИСОК И РЕДАКТОР)
    # ------------------------------------------------------------------
    def _display_fragments_interface(self):
        self._sync_session_state_to_blocks()  # <-- ДОБАВИТЬ ЭТУ СТРОКУ
        st.header("🏷️ Фрагменты и блоки")
        fm = st.session_state.fragment_manager

        # ДОБАВИТЬ ЭТУ КНОПКУ СИНХРОНИЗАЦИИ
        col_sync, col_empty = st.columns([1, 5])
        with col_sync:
            if st.button("🔄 Синхронизировать всё", key="force_sync_all", use_container_width=True):
                self._sync_session_state_to_blocks()
                st.success("✅ Все данные синхронизированы!")
                time.sleep(0.5)
                st.rerun()

        if not fm.fragments:
            st.info("Нет фрагментов для отображения")
            return

            # --- Фильтры (без изменений) ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            filter_type = st.selectbox("Тип блока", ["Все", "regular", "unique", "other"], key="frag_filter_type")
        with col2:
            status_options = ["Все", "pending", "error", "warning", "processed", "fixed"]
            filter_status = st.selectbox("Статус", status_options, key="frag_filter_status")
        with col3:
            search_text = st.text_input("🔍 Поиск по тексту", value=st.session_state.ui_state.get('fragment_search', ''))
            st.session_state.ui_state['fragment_search'] = search_text
        with col4:
            fragment_names = ["Все фрагменты"] + sorted(fm.fragment_names)
            selected_fragment = st.selectbox("Фрагмент", fragment_names, key="frag_filter_fragment")
        all_error_types = set()
        for b in fm.fragments:
            for err in b.errors:
                if 'type' in err:
                    all_error_types.add(err['type'])
        error_type_options = ["Все"] + sorted(all_error_types)
        selected_error_type = st.selectbox("Тип ошибки", error_type_options, key="frag_error_type")
        # Применяем фильтры (как раньше)...
        filtered_blocks = fm.fragments.copy()
        if filter_type != "Все":
            filtered_blocks = [b for b in filtered_blocks if b.block_type == filter_type]
        if filter_status != "Все":
            filtered_blocks = [b for b in filtered_blocks if b.status == filter_status]
        if selected_error_type != "Все":
            filtered_blocks = [
                b for b in filtered_blocks
                if any(err.get('type') == selected_error_type for err in b.errors)
            ]
        if search_text:
            search_lower = search_text.lower()
            filtered_blocks = [
                b for b in filtered_blocks
                if search_lower in b.original_text.lower() or search_lower in b.processed_text.lower()
            ]
        if selected_fragment != "Все фрагменты":
            filtered_blocks = [b for b in filtered_blocks if b.fragment_name == selected_fragment]

        if not filtered_blocks:
            st.info("Нет блоков, соответствующих фильтрам")
            return

        # Пагинация (как раньше)
        per_page = st.selectbox("Блоков на странице", [10, 20, 50, 100], index=1, key="frag_per_page")
        total_blocks = len(filtered_blocks)
        total_pages = max(1, (total_blocks + per_page - 1) // per_page)
        current_page = st.session_state.ui_state.get('fragments_page', 1)
        if current_page > total_pages:
            current_page = total_pages
            st.session_state.ui_state['fragments_page'] = current_page

        # Навигация по страницам (как раньше)
        col_prev, col_page, col_next, col_info = st.columns([1, 2, 1, 3])
        with col_prev:
            if st.button("◀ Предыдущая", disabled=current_page <= 1, key="prev_page"):
                st.session_state.ui_state['fragments_page'] = current_page - 1
                time.sleep(0.35)          # ← вот эта строка
                st.rerun()
        with col_page:
            page = st.number_input("Страница", min_value=1, max_value=total_pages,
                                   value=current_page, key="frag_page_input")
            if page != current_page:
                st.session_state.ui_state['fragments_page'] = page
                time.sleep(0.35)          # ← вот эта строка
                st.rerun()
        with col_next:
            if st.button("Следующая ▶", disabled=current_page >= total_pages, key="next_page"):
                st.session_state.ui_state['fragments_page'] = current_page + 1
                time.sleep(0.35)          # ← вот эта строка
                st.rerun()
        with col_info:
            st.write(f"Всего блоков: {total_blocks}, страниц: {total_pages}")

        start_idx = (current_page - 1) * per_page
        end_idx = start_idx + per_page
        page_blocks = filtered_blocks[start_idx:end_idx]

        # Группируем по фрагментам
        page_blocks_by_fragment = defaultdict(list)
        for block in page_blocks:
            page_blocks_by_fragment[block.fragment_name].append(block)

        # Отображаем
        for frag_name, blocks in page_blocks_by_fragment.items():
            with st.expander(f"📁 **{frag_name}** ({len(blocks)} блоков)", expanded=True):
                for block in blocks:
                    self._render_editable_block(block)
    def _sync_html_to_session_state(self):
        """Принудительно синхронизирует html_text из блоков в session_state"""
        fm = st.session_state.get('fragment_manager')
        if not fm:
            return

        for block in fm.fragments:
            html_key = f"edit_html_{block.id}"
            if block.html_text and (html_key not in st.session_state or st.session_state[html_key] != block.html_text):
                st.session_state[html_key] = block.html_text

    def _on_text_change(self, block_id: str):
        """Callback при изменении текста"""
        fm = st.session_state.get('fragment_manager')
        if not fm:
            return

        block = next((b for b in fm.fragments if b.id == block_id), None)
        if not block:
            return

        text_key = f"edit_text_{block_id}"
        if text_key in st.session_state:
            block.processed_text = st.session_state[text_key]
            block.last_modified = datetime.now()
            block.manually_fixed = True
            self._recalculate_block_errors(block)

            # Сохраняем мгновенно
            self.save_data_to_app_state(st.session_state.get('app_state'))

    def _on_html_change(self, block_id: str):
        """Callback при изменении HTML"""
        fm = st.session_state.get('fragment_manager')
        if not fm:
            return

        block = next((b for b in fm.fragments if b.id == block_id), None)
        if not block:
            return

        html_key = f"edit_html_{block_id}"
        if html_key in st.session_state:
            block.html_text = st.session_state[html_key]
            block.last_modified = datetime.now()
            block.manually_fixed = True

            # ✅ ДОБАВЛЯЕМ: Пересчёт ошибок при изменении HTML
            self._recalculate_block_errors(block)

            # Сохраняем мгновенно
            self.save_data_to_app_state(st.session_state.get('app_state'))


    def _render_editable_block(self, block: FragmentBlock):
        html_key = f"edit_html_{block.id}"
        if block.html_text and (html_key not in st.session_state or st.session_state[html_key] != block.html_text):
            st.session_state[html_key] = block.html_text
        border_color = "#ff4d4d" if block.errors else "#f0f2f6"
        with st.container(border=True):
            st.markdown(f"<div style='border-left: 5px solid {border_color}; padding: 10px;'>", unsafe_allow_html=True)

            # Заголовок и краткая информация
            col1, col2, col3, col4 = st.columns([3, 1, 1, 2])
            col1.markdown(f"**{block.fragment_name}** · `{block.block_type}`")
            col2.markdown(f"Статус: `{block.status}`")
            col3.markdown(f"Ошибок: {len(block.errors)}")
            if block.errors:
                for err in block.errors:
                    st.caption(f"❌ {err.get('message', 'Неизвестная ошибка')}")
            # Иконки выполненных операций
            icons = []
            if block.auto_corrected:
                icons.append("🔧")
            if block.manually_fixed and not block.errors:
                icons.append("✏️ исправлено")
            if block.html_generated:
                icons.append("🌐")
            if block.units_removed:
                icons.append("⚖️")
            if block.symbols_removed:
                icons.append("⚡")
            col4.markdown(" ".join(icons))

            # Характеристика и значение
            if block.characteristic_name or block.characteristic_value:
                st.caption(f"📌 {block.characteristic_name or '—'}: {block.characteristic_value or '—'}")

            # Текстовое поле для редактирования (всегда видимо)
            text_key = f"edit_text_{block.id}"

            # ✅ Инициализируем session_state, если нужно
            if text_key not in st.session_state:
                st.session_state[text_key] = block.processed_text

            edited_text = st.text_area(
                "Текст блока (с переменными)",
                value=st.session_state[text_key],
                height=100,
                key=text_key,
                label_visibility="collapsed",
                on_change=self._on_text_change,  # ✅ Добавляем callback
                args=(block.id,)
            )

            # HTML поле
            html_key = f"edit_html_{block.id}"
            if html_key not in st.session_state:
                st.session_state[html_key] = block.html_text

            with st.expander("🌐 HTML версия (редактируемая)", expanded=False):
                edited_html = st.text_area(
                    "HTML код",
                    value=st.session_state[html_key],
                    height=150,
                    key=html_key,
                    label_visibility="collapsed",
                    on_change=self._on_html_change,  # ✅ Добавляем callback
                    args=(block.id,)
                )

                # Если значение изменилось через виджет, оно автоматически сохранится в session_state
                # Но мы не должны присваивать st.session_state[html_key] = block.html_text вручную после создания виджета

                # Кнопка предпросмотра HTML
                if st.button("👁️ Предпросмотр", key=f"preview_html_{block.id}"):
                    st.markdown("**Рендер:**")
                    st.markdown(edited_html, unsafe_allow_html=True)

            # Кнопки действий
            col_save, col_ops, col_delete = st.columns([1, 2, 1])
            with col_save:
                with col_save:
                    if st.button("💾 Сохранить", key=f"save_{block.id}", use_container_width=True):
                        old_text = block.processed_text
                        old_html = block.html_text

                        # Используем .get() с проверкой
                        edited_text = st.session_state.get(text_key, block.processed_text)
                        edited_html = st.session_state.get(html_key, block.html_text)

                        block.processed_text = edited_text
                        block.html_text = edited_html
                        block.last_modified = datetime.now()
                        block.manually_fixed = True

                        # ✅ ИСПОЛЬЗУЕМ ЕДИНЫЙ МЕТОД ПЕРЕСЧЁТА ОШИБОК
                        self._recalculate_block_errors(block)

                        normalized = self.text_processor.normalize_text(block.processed_text)
                        if normalized != block.processed_text:
                            block.processed_text = normalized
                            st.info("Текст нормализован: ё заменена на е.")

                        # Регистрируем трансформацию
                        trans = TextTransformation(
                            block_id=block.id,
                            fragment_name=block.fragment_name,
                            transformation_type=TransformationType.MANUAL_CORRECTION,
                            original=old_text,
                            result=block.processed_text,
                            severity=SeverityLevel.INFO,
                            user="user",
                            meta={'html_changed': old_html != block.html_text}
                        )
                        st.session_state.transformation_registry.add(trans)
                        self.save_data_to_app_state()
                        st.success("✅ Текст и HTML сохранены")
                        time.sleep(0.35)
                        st.rerun()

            with col_ops:
                with st.popover("⚙️ Операции", use_container_width=True):
                    if st.button("🔄 Заменить переменные", key=f"pop_replace_{block.id}", use_container_width=True):
                        self._apply_variable_replacement(block.id)
                        time.sleep(0.35)
                        st.rerun()
                    if st.button("🔧 Добавить значение", key=f"pop_autofix_{block.id}", use_container_width=True):
                        self._auto_insert_regular_blocks(block.id)
                        time.sleep(0.35)
                        st.rerun()
                    if st.button("🌐 Сгенерировать HTML", key=f"pop_html_{block.id}", use_container_width=True):
                        self._apply_generate_html(block.id)
                        time.sleep(0.35)
                        st.rerun()
                    if st.button("🧹 Постобработка", key=f"pop_post_{block.id}", use_container_width=True):
                        self._apply_postprocessing(block.id)
                        time.sleep(0.35)
                        st.rerun()
                    if st.button("👁️ Предпросмотр HTML", key=f"pop_preview_{block.id}", use_container_width=True):
                        if block.html_text:
                            st.markdown("**Рендер:**")
                            st.markdown(block.html_text, unsafe_allow_html=True)
                            with st.expander("Показать HTML-код"):
                                st.code(block.html_text, language="html")
                        else:
                            st.info("HTML ещё не сгенерирован. Нажмите 'Сгенерировать HTML'.")

            with col_delete:
                if st.button("🗑️ Удалить", key=f"delete_{block.id}", use_container_width=True):
                    if st.session_state.fragment_manager.delete_block(block.id):
                        st.success("Блок удалён")
                        time.sleep(0.35)
                        st.rerun()
                    else:
                        st.error("Не удалось удалить блок")

            st.markdown("</div>", unsafe_allow_html=True)





    def _display_inline_block_editor(self, block: FragmentBlock):
        st.markdown("---")
        st.subheader(f"Редактирование: {block.fragment_name}")

        # Информация о блоке (как раньше)
        col1, col2, col3, col4 = st.columns(4)
        col1.write(f"**Тип:** {block.block_type}")
        col2.write(f"**Хар-ка:** {block.characteristic_name or '-'}")
        col3.write(f"**Значение:** {block.characteristic_value or '-'}")
        col4.write(f"**Статус:** {block.status}")

        # Ошибки и спецсимволы
        if block.errors:
            with st.expander(f"❌ Ошибки ({len(block.errors)})", expanded=False):
                for e in block.errors:
                    st.write(f"- {e}")
        if block.special_symbols:
            with st.expander(f"⚡ Спецсимволы ({len(block.special_symbols)})", expanded=False):
                for sym, st_pos, end_pos in block.special_symbols[:20]:
                    st.write(f"- '{sym}' на {st_pos}-{end_pos}")
                if len(block.special_symbols) > 20:
                    st.write(f"... и ещё {len(block.special_symbols) - 20}")

        # Кнопки операций (как раньше)
        with st.popover("⚙️", use_container_width=True):
            if st.button("🔄 Заменить переменные", key=f"pop_replace_{block.id}", use_container_width=True):
                self._apply_variable_replacement(block.id)
                time.sleep(0.35)
                st.rerun()

            if st.button("🔧 Добавить значение", key=f"pop_autofix_{block.id}", use_container_width=True):
                self._auto_insert_regular_blocks(block.id)
                time.sleep(0.35)
                st.rerun()
            if st.button("⚖️ Удалить единицы", key=f"pop_remove_{block.id}", use_container_width=True):
                units = st.session_state.ui_state.get('selected_units_global', [])
                self._apply_unit_removal(block.id, units)
                time.sleep(0.35)
                st.rerun()
            if st.button("🌐 HTML", key=f"pop_html_{block.id}", use_container_width=True):
                self._apply_generate_html(block.id)
                time.sleep(0.35)
                st.rerun()
            if st.button("⚡ Удалить спецсимволы", key=f"pop_spec_{block.id}", use_container_width=True):
                symbols = st.session_state.ui_state.get('selected_symbols_global', [])
                self._apply_special_symbol_removal(block.id, symbols)
                time.sleep(0.35)
                st.rerun()

        st.divider()

        # --- ПАНЕЛЬ ВСТАВКИ ПЕРЕМЕННЫХ ---
        st.subheader("🔄 Вставка переменных")
        textarea_key = f"editor_text_{block.id}"
        if textarea_key not in st.session_state:
            st.session_state[textarea_key] = block.processed_text

        col_pos1, col_pos2 = st.columns([2, 2])
        with col_pos1:
            insert_mode = st.radio(
                "Позиция вставки:",
                ["в конец", "в начало", "после слова"],
                horizontal=True,
                key=f"ins_mode_{block.id}"
            )
        with col_pos2:
            word_index = 0
            if insert_mode == "после слова":
                words = st.session_state[textarea_key].split()
                if words:
                    word_index = st.selectbox(
                        "После какого слова:",
                        options=list(range(len(words))),
                        format_func=lambda i: f"{i + 1}. {words[i][:20]}",
                        key=f"ins_word_{block.id}"
                    )
                else:
                    st.info("Текст пуст, вставка в конец")
                    insert_mode = "в конец"

        suggestions = self.vm.get_variable_suggestions()
        city_vars = [v for v in suggestions if 'город' in v['name'].lower()]
        product_vars = [v for v in suggestions if 'товар' in v['name'].lower()]
        category_vars = [v for v in suggestions if 'категория' in v['name'].lower()]
        prop_var = next((v for v in suggestions if v['type'] == 'prop'), None)
        frag_var = next((v for v in suggestions if v['type'] == 'fragment'), None)
        other_vars = [v for v in suggestions if v not in city_vars + product_vars + category_vars
                      and v != prop_var and v != frag_var]

        def insert_variable(text: str, var_value: str, mode: str, word_idx: int = 0) -> str:
            if mode == "в начало":
                return var_value + " " + text if text else var_value
            elif mode == "после слова" and word_idx < len(text.split()):
                parts = text.split()
                parts.insert(word_idx + 1, var_value)
                return " ".join(parts)
            else:
                if text and not text.endswith(' '):
                    text += ' '
                return text + var_value

        col_city, col_prod, col_cat, col_propfrag, col_other = st.columns(5)

        with col_city:
            with st.popover("🌆 Город", use_container_width=True):
                for idx, var in enumerate(city_vars):
                    if st.button(var['value'], key=f"city_{block.id}_{idx}", use_container_width=True):
                        st.session_state[textarea_key] = insert_variable(
                            st.session_state[textarea_key],
                            var['value'],
                            insert_mode,
                            word_index if insert_mode == "после слова" else 0
                        )
                        time.sleep(0.35)
                        st.rerun()
        with col_prod:
            with st.popover("🏷️ Товар", use_container_width=True):
                for idx, var in enumerate(product_vars):
                    if st.button(var['value'], key=f"prod_{block.id}_{idx}", use_container_width=True):
                        st.session_state[textarea_key] = insert_variable(
                            st.session_state[textarea_key],
                            var['value'],
                            insert_mode,
                            word_index if insert_mode == "после слова" else 0
                        )
                        time.sleep(0.35)
                        st.rerun()
        with col_cat:
            with st.popover("📂 Категория", use_container_width=True):
                for idx, var in enumerate(category_vars):
                    if st.button(var['value'], key=f"cat_{block.id}_{idx}", use_container_width=True):
                        st.session_state[textarea_key] = insert_variable(
                            st.session_state[textarea_key],
                            var['value'],
                            insert_mode,
                            word_index if insert_mode == "после слова" else 0
                        )
                        time.sleep(0.35)
                        st.rerun()
        with col_propfrag:
            col_p, col_f = st.columns(2)
            with col_p:
                if prop_var and st.button("prop", key=f"prop_{block.id}", use_container_width=True):
                    st.session_state[textarea_key] = insert_variable(
                        st.session_state[textarea_key],
                        prop_var['value'],
                        insert_mode,
                        word_index if insert_mode == "после слова" else 0
                    )
                    time.sleep(0.35)
                    st.rerun()
            with col_f:
                if frag_var and st.button("fragment", key=f"frag_{block.id}", use_container_width=True):
                    st.session_state[textarea_key] = insert_variable(
                        st.session_state[textarea_key],
                        frag_var['value'],
                        insert_mode,
                        word_index if insert_mode == "после слова" else 0
                    )
                    time.sleep(0.35)
                    st.rerun()
        with col_other:
            with st.popover("📝 Прочие", use_container_width=True):
                for idx, var in enumerate(other_vars):
                    if st.button(var['name'], key=f"other_{block.id}_{idx}", use_container_width=True):
                        st.session_state[textarea_key] = insert_variable(
                            st.session_state[textarea_key],
                            var['value'],
                            insert_mode,
                            word_index if insert_mode == "после слова" else 0
                        )
                        time.sleep(0.35)
                        st.rerun()

        st.divider()

        # --- РЕДАКТОР ТЕКСТА ---
        textarea_key = f"inline_editor_text_{block.id}"
        if textarea_key not in st.session_state:
            st.session_state[textarea_key] = block.processed_text

        edited_text = st.text_area(
            "Текст блока:",
            value=st.session_state[textarea_key],
            height=200,
            key=textarea_key,
            label_visibility="collapsed"
        )
        if st.session_state[textarea_key] != edited_text:
            st.session_state[textarea_key] = edited_text

        # Кнопки сохранения, закрытия, удаления
        col_save, col_close, col_delete = st.columns(3)
        with col_save:
            if st.button("💾 Сохранить", type="primary", key=f"inline_save_{block.id}", use_container_width=True):
                # Сохраняем, обновляем ошибки
                old_text = block.processed_text
                old_html = block.html_text or ""   # ← ИСПРАВЛЕНИЕ: добавили значение по умолчанию

                block.processed_text = edited_text
                block.last_modified = datetime.now()
                block.manually_fixed = True

                # Проверка regular-блоков
                if block.block_type == 'regular':
                    errors = self.text_processor.check_regular_brackets(
                        block.processed_text, block.characteristic_value
                    )
                    # Удаляем старые ошибки про скобки
                    block.errors = [e for e in block.errors
                                    if e.get('type') != ErrorType.MISSING_BRACKET.value
                                    and "значение" not in e.get('message', '')]
                    if errors:
                        block.errors.extend(errors)
                        block.status = 'error'
                    else:
                        block.status = 'fixed' if not block.errors else block.status

                block.special_symbols = self.text_processor._find_special_symbols(block.processed_text)

                # Регистрация трансформации
                trans = TextTransformation(
                    block_id=block.id,
                    fragment_name=block.fragment_name,
                    transformation_type=TransformationType.MANUAL_CORRECTION,
                    original=old_text,
                    result=block.processed_text,
                    severity=SeverityLevel.INFO,
                    user="user",
                    meta={'html_changed': old_html != block.html_text}
                )
                st.session_state.transformation_registry.add(trans)

                self._recalculate_block_errors(block)   # ← рекомендуется добавить
                self.save_data_to_app_state()

                st.success("✅ Текст сохранён")
                time.sleep(0.35)
                st.rerun()
        with col_close:
            if st.button("🚫 Закрыть", key=f"inline_close_{block.id}", use_container_width=True):
                st.session_state.ui_state['editing_block_id'] = None
                if textarea_key in st.session_state:
                    del st.session_state[textarea_key]
                time.sleep(0.35)
                st.rerun()
        with col_delete:
            if st.button("🗑️ Удалить", key=f"inline_delete_{block.id}", use_container_width=True):
                if st.session_state.fragment_manager.delete_block(block.id):
                    st.success("Блок удалён")
                    st.session_state.ui_state['editing_block_id'] = None
                    if textarea_key in st.session_state:
                        del st.session_state[textarea_key]
                    time.sleep(0.35)
                    st.rerun()
                else:
                    st.error("Не удалось удалить блок")

    # ------------------------------------------------------------------
    #                     ИСТОРИЯ ТРАНСФОРМАЦИЙ
    # ------------------------------------------------------------------
    def _display_transformations_interface(self):
        st.header("📋 История замен и трансформаций")
        registry = st.session_state.transformation_registry

        if not registry.transformations:
            st.info("Нет записей о трансформациях")
            return

        col1, col2 = st.columns(2)
        with col1:
            type_filter = st.selectbox(
                "Тип трансформации",
                ["Все"] + [t.value for t in TransformationType],
                key="trans_type_filter"
            )
        with col2:
            severity_filter = st.selectbox(
                "Важность",
                ["Все"] + [s.value for s in SeverityLevel],
                key="trans_sev_filter"
            )

        filtered = registry.transformations
        if type_filter != "Все":
            filtered = [t for t in filtered if t.transformation_type.value == type_filter]
        if severity_filter != "Все":
            filtered = [t for t in filtered if t.severity.value == severity_filter]

        data = []
        for t in filtered:
            data.append({
                "Время": t.timestamp.strftime("%H:%M:%S"),
                "Фрагмент": t.fragment_name,
                "Тип": t.transformation_type.value,
                "Было": t.original[:50] + ("..." if len(t.original) > 50 else ""),
                "Стало": t.result[:50] + ("..." if len(t.result) > 50 else ""),
                "Важность": t.severity.value,
                "Пользователь": t.user
            })
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, height=500)

        st.subheader("Статистика")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Всего операций", len(registry.transformations))
        col2.metric("Замен переменных", len([t for t in registry.transformations if
                                             t.transformation_type == TransformationType.VARIABLE_REPLACE]))
        col3.metric("Ошибок", len(registry.get_errors()))
        col4.metric("Предупреждений", len(registry.get_warnings()))
    def _create_standard_templates(self, fm):
        """Создаёт стандартные шаблоны, если в конфиге нет паттернов"""
        if not fm.fragment_names:
            return

        # Сортируем фрагменты
        sorted_fragments = sorted(fm.fragment_names)

        # Создаём один шаблон со всеми фрагментами
        fm.add_template(
            name="Стандартный",
            order=sorted_fragments,
            description="Стандартный шаблон со всеми фрагментами",
            set_as_default=True
        )

        st.info("✅ Создан стандартный шаблон (паттерны не найдены в конфиге)")
    # ------------------------------------------------------------------
    #                     ШАБЛОНЫ И HTML
    # ------------------------------------------------------------------
    def _display_templates_interface(self):
        st.header("🧩 Шаблоны и HTML предпросмотр")

        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            fm = st.session_state.fragment_manager
            st.write(f"**Всего шаблонов:** {len(fm.templates)} | **Фрагментов:** {len(fm.fragment_names)}")
        with col2:
            if st.button("🔄 Обновить шаблоны", key="refresh_templates_tab", use_container_width=True, type="primary"):
                if self.refresh_templates_and_export():
                    time.sleep(0.5)
                    st.rerun()
        with col3:
            if st.button("🔍 Отладка", key="show_debug_in_templates_tab", use_container_width=True):
                if '_template_debug' not in st.session_state:
                    fm.templates.clear()
                    self._create_default_templates()
                '''self._show_template_debug()'''

        st.markdown("---")

        # ✅ ПОКАЗЫВАЕМ СПИСОК ШАБЛОНОВ
        self._display_templates_list()

        st.markdown("---")

        # Остальной код (конструктор, HTML предпросмотр)
        tab1, tab2 = st.tabs(["Конструктор шаблона", "HTML предпросмотр"])

        with tab1:
            self._display_template_builder()
        with tab2:
            self._display_html_preview()
    def save_category_code(self, new_code: str):
        self._sync_session_state_to_blocks()   # ← добавь

        fm = st.session_state.get('fragment_manager')
        if not fm:
            return False

        fm.category_code = new_code.strip()
        fm.category = new_code.strip()

        # Сохраняем в phase7
        if 'phase7' not in st.session_state.app_data:
            st.session_state.app_data['phase7'] = {}

        st.session_state.app_data['phase7']['manual_category_code'] = fm.category_code
        st.session_state.app_data['phase7']['category_code'] = fm.category_code

        self.save_data_to_app_state(st.session_state.get('app_state'))
        st.success(f"✅ Код категории сохранён: {fm.category_code}")
        return True
    def _display_template_builder(self):
        fm = st.session_state.fragment_manager

        st.subheader("🏷️ Настройки категории")

        col1, col2 = st.columns([3, 1])
        with col1:
            # ✅ ИСПОЛЬЗУЕМ ТЕКУЩЕЕ ЗНАЧЕНИЕ ИЗ fm
            temp_code = st.text_input(
                "Код категории (для экспорта)",
                value=fm.category_code,
                key="template_cat_code_temp",
                help="Этот код будет использован в названиях экспортируемых файлов"
            )
        with col2:
            if st.button("💾 Сохранить код категории", key="save_cat_code", use_container_width=True):
                if temp_code != fm.category_code:
                    self.save_category_code(temp_code)
                    st.rerun()
                else:
                    st.info("Код категории не изменился")

        st.divider()
        st.subheader("📋 Варианты шаблонов")

        # Список существующих шаблонов
        if fm.templates:
            for tpl_name, tpl in list(fm.templates.items()):
                with st.expander(f"📋 {tpl_name}", expanded=False):
                    col1, col2 = st.columns([4,1])
                    with col1:
                        new_name = st.text_input("Название шаблона", value=tpl_name, key=f"tpl_name_{tpl_name}")
                        if new_name != tpl_name and new_name:
                            fm.templates[new_name] = fm.templates.pop(tpl_name)
                            tpl_name = new_name

                        new_desc = st.text_input("Описание / примечание", value=tpl.description, key=f"tpl_desc_{tpl_name}")
                        tpl.description = new_desc

                        # Порядок
                        valid_defaults = [f for f in tpl.order if f in fm.fragment_names]

                        selected_order = st.multiselect(
                            "Порядок фрагментов",
                            options=sorted(fm.fragment_names),
                            default=valid_defaults,
                            key=f"tpl_order_{tpl_name}"
                        )
                        if selected_order != tpl.order:
                            tpl.order = selected_order

                        # Кнопка сохранения изменений шаблона
                        if st.button(f"💾 Сохранить шаблон '{tpl_name}'", key=f"save_tpl_{tpl_name}", use_container_width=True):
                            self._save_templates_to_domain()
                            st.success(f"✅ Шаблон '{tpl_name}' сохранён в домене")
                            time.sleep(0.5)
                            st.rerun()

                    with col2:
                        if st.button(f"🗑️ Удалить", key=f"del_tpl_{tpl_name}", use_container_width=True):
                            fm.delete_template(tpl_name)
                            self._save_templates_to_domain()  # ← ДОБАВИТЬ
                            st.success(f"Шаблон удалён из домена")
                            time.sleep(0.5)
                            st.rerun()

        # Добавление нового шаблона
        with st.form("new_template_form"):
            st.subheader("➕ Создать новый шаблон")
            new_tpl_name = st.text_input("Название нового шаблона", "Новый шаблон")
            new_tpl_desc = st.text_input("Описание", "")

            # Получаем порядок фрагментов
            order_for_new = st.multiselect(
                "Порядок фрагментов",
                options=sorted(fm.fragment_names),
                default=sorted(fm.fragment_names)
            )

            submitted = st.form_submit_button("➕ Добавить шаблон", use_container_width=True)
            if submitted and new_tpl_name and order_for_new:
                fm.add_template(
                    name=new_tpl_name,
                    order=order_for_new,
                    description=new_tpl_desc,
                    set_as_default=False
                )
                self._save_templates_to_domain()
                st.success(f"✅ Шаблон '{new_tpl_name}' добавлен")
                time.sleep(0.5)
                st.rerun()



    def _display_html_preview(self):
        fm = st.session_state.fragment_manager

        st.subheader("🔄 Предпросмотр HTML")
        st.info("HTML генерируется из обработанного текста с заменой переменных на заглушки. "
                "Для полноценного отображения необходимы реальные данные на сайте.")

        mode = st.radio("Режим:", ["Все фрагменты", "Выбрать фрагмент"], horizontal=True, key="html_mode")

        if mode == "Все фрагменты":
            combined_html = []
            for f in fm.fragments:
                if f.html_text:
                    combined_html.append(f"<!-- Фрагмент: {f.fragment_name} -->")
                    combined_html.append(f.html_text)
                    combined_html.append("<hr>")
            if not combined_html:
                st.info("Нет сгенерированного HTML. Сначала сгенерируйте HTML для блоков.")
                return
            html_all = "\n".join(combined_html)
            st.markdown("**Предпросмотр (рендер):**")
            st.markdown(html_all, unsafe_allow_html=True)
            with st.expander("📄 Исходный HTML код"):
                st.code(html_all, language="html")
            st.download_button(
                "📥 Скачать полный HTML",
                data=html_all,
                file_name=f"все_фрагменты_{fm.category}.html",
                mime="text/html"
            )
        else:
            frag_names = sorted(fm.fragment_names)
            if not frag_names:
                return
            selected_frag = st.selectbox("Выберите фрагмент:", frag_names, key="html_frag_select")
            blocks = fm.get_fragment_blocks(selected_frag)
            html_blocks = [b.html_text for b in blocks if b.html_text]
            if not html_blocks:
                st.info("HTML для этого фрагмента не сгенерирован.")
                return
            combined_html = []
            for b in blocks:
                if b.html_text:
                    combined_html.append(f"<!-- Блок {b.id[:8]} -->")
                    combined_html.append(b.html_text)
            html_frag = "\n".join(combined_html)
            st.markdown("**Предпросмотр (рендер):**")
            st.markdown(html_frag, unsafe_allow_html=True)
            with st.expander("📄 Исходный HTML код"):
                st.code(html_frag, language="html")
            st.download_button(
                "📥 Скачать HTML фрагмента",
                data=html_frag,
                file_name=f"{selected_frag}.html",
                mime="text/html"
            )


def main(app_state=None, settings_mode=False, context=None):
    """
    Фаза 7: Подготовка к загрузке на сайт
    Получает данные из фазы 6 (синонимизатор) или напрямую из фазы 5
    """
    load_css()

    # ===== ДОБАВИТЬ ПРОВЕРКУ СМЕНЫ ПРОЕКТА =====
    current_project_id = st.session_state.get('current_project_id')
    last_loaded = st.session_state.get('phase7_last_loaded_project')

    # Если проект изменился - сбрасываем данные
    if current_project_id and last_loaded != current_project_id:
        if 'fragment_manager' in st.session_state:
            fm = st.session_state.fragment_manager
            fm.fragments = []
            fm.fragment_names = set()
            fm.fragment_properties = defaultdict(list)
            fm.templates = {}
        st.session_state.phase7_last_loaded_project = current_project_id
        st.session_state.phase7_initialized = False
    # ===== КОНЕЦ ПРОВЕРКИ =====

    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()



    dm = st.session_state.domain_manager
    st.info(f"🌐 Текущий домен: **{dm.get_domain_display_name()}**")
    # === КОНЕЦ ДОБАВЛЕНИЯ ===
    if app_state:
        st.session_state.app_state = app_state

    # Проверяем phase6 или phase5
    if 'phase6' in st.session_state.app_data:
        phase6_data = st.session_state.app_data['phase6']
        if isinstance(phase6_data, str):
            try:
                st.session_state.app_data['phase6'] = json.loads(phase6_data)
            except:
                pass

    # ========== РЕЖИМ НАСТРОЕК ==========
    if settings_mode:
        st.markdown("### 📊 Настройка анализа (Фаза 7)")
        st.caption("Настройте параметры для автоматического запуска")
        st.info("💡 Код категории будет использован при экспорте данных")
        st.markdown("---")

        category_code = st.text_input(
            "Код категории (для экспорта):",
            value=st.session_state.app_data.get('category', ''),
            key="phase7_settings_category_code",
            help="Этот код будет использован в названиях экспортируемых файлов"
        )

        if st.button("💾 Сохранить настройки фазы 7", type="primary"):
            if 'app_data' not in st.session_state:
                st.session_state.app_data = {}
            st.session_state.app_data['phase7_settings'] = {
                'category_code': category_code,
                'auto_generate': True
            }
            if app_state:
                app_state.save_project()
            st.success("✅ Настройки фазы 7 сохранены!")

        st.markdown("---")
        st.info("📌 Фаза 7 принимает тексты как с применённой синонимизацией, так и без неё")

        if st.button("← Назад к настройкам проекта", key="back_from_phase7_settings"):
            st.session_state.show_settings = True
            st.rerun()
        return

    if 'current_phase' not in st.session_state:
        st.session_state.current_phase = 7

    # Восстановление данных
    if app_state:
        if 'phase7' in st.session_state.app_data:
            phase7_saved = st.session_state.app_data['phase7']
            '''if phase7_saved:
                st.info("🔄 Данные фазы 7 восстановлены из сохранённого проекта")'''

        st.session_state.current_phase = 7
        app_state.save_project()

    if 'app_data' not in st.session_state:
        st.error("❌ Нет данных приложения")
        st.info("Завершите предыдущие фазы")
        if st.button("← Вернуться к началу", use_container_width=True):
            st.session_state.current_phase = 1
            st.rerun()
        return

    st.markdown("---")

    interface = Phase7Interface(context=context)
    interface.display_main_interface()

    if app_state:
        interface.save_data_to_app_state(app_state)




def reset_data_loaded_flag(self):
    """Сбрасывает флаг загрузки данных (для принудительной перезагрузки)"""
    st.session_state.phase7_data_loaded = False
    st.session_state.fragment_manager = FragmentManager("Без_категории")
def auto_process_all_fragments(app_state=None, context=None):
    """
    Автоматическая обработка всех фрагментов из фазы 6
    """
    # Добавьте логирование (если нет функции log)
    def log(msg):
        print(f"[{datetime.now()}] {msg}")

    log("=== auto_process_all_fragments started ===")

    # === ДОБАВИТЬ ИНИЦИАЛИЗАЦИЮ DOMAIN_MANAGER ===
    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()
    dm = st.session_state.domain_manager
    # === КОНЕЦ ДОБАВЛЕНИЯ ===

    # Инициализацияс
    if 'fragment_manager' not in st.session_state:
        st.session_state.fragment_manager = FragmentManager("Без_категории")

    interface = Phase7Interface(context=context)

    # Загружаем данные из фазы 6
    if not interface._load_data():
        return {
            'success': False,
            'message': 'Не удалось загрузить данные из фазы 6',
            'count': 0,
            'errors': 1
        }

    fm = st.session_state.fragment_manager

    # Автоматически применяем базовую обработку
    interface._auto_insert_regular_blocks()
    interface._apply_variable_replacement()
    interface._apply_postprocessing()
    interface._apply_generate_html()

    # ✅ ИСПРАВЛЕНО: сохраняем в phase7
    if interface.save_data_to_app_state(app_state):



        return {
            'success': True,
            'message': f'Обработано {len(fm.fragments)} блоков',
            'count': len(fm.fragments),
            'errors': sum(1 for f in fm.fragments if f.errors),
            'statistics': {
                'total_blocks': len(fm.fragments),
                'error_blocks': sum(1 for f in fm.fragments if f.errors),
                'regular_blocks': sum(1 for f in fm.fragments if f.block_type == 'regular'),
                'unique_blocks': sum(1 for f in fm.fragments if f.block_type == 'unique')
            }
        }
    else:
        return {
            'success': False,
            'message': 'Ошибка сохранения результатов',
            'count': 0,
            'errors': 1
        }
if __name__ == "__main__":
    main()