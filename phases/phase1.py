


import streamlit as st
import json
import os
from collections import defaultdict
from datetime import datetime
from styles import load_css
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
# --- CSS ---
# --- CSS ---
def local_css():
    st.markdown("""
    <style>
    /* Основные стили */
    .main { 
        background-color: #f5f7f9; 
    }

    /* Темный режим */
    @media (prefers-color-scheme: dark) {
        .main {
            background-color: #0e1117;
        }
        .characteristic-container {
            background-color: #262730;
            border-color: #41434d;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }
        .characteristic-container:hover {
            border-color: #4a4d57;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
        }
        .metric-box {
            background-color: #262730;
            color: #f0f2f6;
            border-color: #41434d;
        }
        .warning-box {
            background-color: #332701;
            border-color: #665c00;
            color: #ffd54f;
        }
        .stButton > button {
            background-color: #4a4d57;
            color: #f0f2f6;
            border: 1px solid #5a5d68;
        }
        .stButton > button:hover {
            background-color: #5a5d68;
            border-color: #6a6d78;
        }
        .char-header {
            color: #e2e8f0;
        }
        .char-info {
            color: #94a3b8;
        }
        .fill-rate {
            color: #34d399;
        }
    }

    .stTable { 
        font-size: 12px; 
    }

    .metric-box {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        margin-bottom: 15px;
        border: 1px solid #eaeaea;
    }

    .preview-btn {
        background-color: #e0f7fa;
        color: #00796b;
        border: none;
        border-radius: 5px;
        padding: 2px 8px;
        cursor: pointer;
    }

    .characteristic-container {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 16px;
        background-color: white;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        transition: all 0.2s ease;
    }

    .characteristic-container:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        border-color: #d0d0d0;
        transform: translateY(-1px);
    }

    /* Разделитель между карточками */
    .characteristic-container::after {
        content: '';
        display: block;
        height: 1px;
        background: linear-gradient(90deg, 
            transparent 0%, 
            rgba(0,0,0,0.1) 20%, 
            rgba(0,0,0,0.1) 80%, 
            transparent 100%);
        margin-top: 16px;
        margin-bottom: 0;
    }

    .characteristic-container:last-child::after {
        display: none;
    }

    /* Альтернативный вариант - разделитель между колонками */
    .stColumn {
        position: relative;
    }

    .stColumn:not(:last-child)::after {
        content: '';
        position: absolute;
        top: 10%;
        right: 0;
        height: 80%;
        width: 1px;
        background: linear-gradient(to bottom, 
            transparent 0%, 
            rgba(0,0,0,0.1) 20%, 
            rgba(0,0,0,0.1) 80%, 
            transparent 100%);
    }

    .mode-buttons {
        display: flex;
        gap: 5px;
    }

    .global-sync-btn {
        margin-top: 10px;
    }

    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 20px;
        color: #856404;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }

    /* Улучшенные стили для чекбоксов и радио */
    .stCheckbox > label,
    .stRadio > label {
        font-weight: 500 !important;
    }

    /* Стили для заголовков */
    .char-header {
        font-weight: 600;
        margin-bottom: 8px;
        color: #1e293b;
    }

    /* Стили для информации о характеристике */
    .char-info {
        color: #64748b;
        font-size: 0.85em;
        margin-top: 4px;
    }

    /* Дубликаты - особый стиль */
    .duplicate-char {
        border-left: 4px solid #ef4444;
        background: linear-gradient(90deg, rgba(239,68,68,0.05) 0%, transparent 100%);
    }

    /* Дополнительные характеристики */
    .extra-char {
        border-left: 4px solid #f59e0b;
        background: linear-gradient(90deg, rgba(245,158,11,0.05) 0%, transparent 100%);
    }

    /* Нормальные характеристики */
    .normal-char {
        border-left: 4px solid #10b981;
        background: linear-gradient(90deg, rgba(16,185,129,0.05) 0%, transparent 100%);
    }

    /* Темный режим для типов характеристик */
    @media (prefers-color-scheme: dark) {
        .duplicate-char {
            border-left: 4px solid #ef4444;
            background: linear-gradient(90deg, rgba(239,68,68,0.15) 0%, transparent 100%);
        }
        .extra-char {
            border-left: 4px solid #f59e0b;
            background: linear-gradient(90deg, rgba(245,158,11,0.15) 0%, transparent 100%);
        }
        .normal-char {
            border-left: 4px solid #10b981;
            background: linear-gradient(90deg, rgba(16,185,129,0.15) 0%, transparent 100%);
        }
    }

    /* Улучшение отступов в колонках */
    .stColumn > div {
        padding: 0 8px;
    }

    /* Улучшение видимости процентов заполнения */
    .fill-rate {
        font-weight: 600;
        color: #10b981;
        font-size: 1.1em;
    }

    /* Иконка дубликата */
    .duplicate-icon {
        color: #ef4444;
        margin-right: 6px;
        display: inline-block;
    }

    /* Улучшение для кнопок в карточках */
    .characteristic-container .stButton > button {
        font-size: 0.85em;
        padding: 4px 12px;
        border-radius: 6px;
    }

    /* Улучшение для селекторов и инпутов */
    .characteristic-container .stSelectbox > div,
    .characteristic-container .stNumberInput > div {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }

    .characteristic-container .stSelectbox > div:hover,
    .characteristic-container .stNumberInput > div:hover {
        border-color: #9ca3af;
    }

    /* Темный режим для инпутов */
    @media (prefers-color-scheme: dark) {
        .characteristic-container .stSelectbox > div,
        .characteristic-container .stNumberInput > div {
            border-color: #4b5563;
            background-color: #374151;
        }
        .characteristic-container .stSelectbox > div:hover,
        .characteristic-container .stNumberInput > div:hover {
            border-color: #6b7280;
        }
    }

    /* Стили для состояния активности */
    .active-char {
        opacity: 1;
    }

    .inactive-char {
        opacity: 0.7;
        background-color: #f8f9fa;
    }

    @media (prefers-color-scheme: dark) {
        .inactive-char {
            background-color: #1f2937;
        }
    }

    /* Улучшение для заголовков разделов */
    h1, h2, h3 {
        margin-top: 0 !important;
        padding-top: 0.5em !important;
    }

    /* Градиентные заголовки */
    h1 {
        background: linear-gradient(90deg, #3b82f6, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    /* Анимация при наведении на заголовки */
    h2:hover, h3:hover {
        transition: all 0.3s ease;
        transform: translateX(5px);
    }

    /* Стили для expander */
    .streamlit-expanderHeader {
        font-weight: 500 !important;
        border-radius: 6px !important;
        padding: 8px 12px !important;
    }

    .streamlit-expanderContent {
        padding: 12px !important;
    }

    /* Стили для таблиц в предпросмотре */
    .dataframe {
        border-radius: 8px !important;
        overflow: hidden !important;
        border: 1px solid #e5e7eb !important;
    }

    @media (prefers-color-scheme: dark) {
        .dataframe {
            border-color: #4b5563 !important;
        }
    }

    /* Плавные переходы */
    * {
        transition: background-color 0.3s ease, 
                    border-color 0.3s ease, 
                    box-shadow 0.3s ease,
                    transform 0.3s ease;
    }
    </style>
    """, unsafe_allow_html=True)


# --- Логика обработки ---
def normalize_string(s):
    """Нормализует строку: убирает лишние пробелы"""
    if not isinstance(s, str):
        return s
    # Заменяем множественные пробелы на один, убираем в начале и конце
    return ' '.join(s.split())  # Это преобразует "Труба  горячедеформированная" в "Труба горячедеформированная"


def normalize_data(data):
    """
    Нормализует данные: убирает лишние пробелы в названиях категорий и характеристик.
    """
    if not isinstance(data, dict):
        return data

    # Нормализуем название категории
    if "ПараметрыТовара" in data and isinstance(data["ПараметрыТовара"], dict):
        params = data["ПараметрыТовара"]
        if "Наименование" in params and isinstance(params["Наименование"], str):
            params["Наименование"] = normalize_string(params["Наименование"])
            #print(f"Нормализовано название категории: {params['Наименование']}")  # Для отладки

        # Нормализуем названия характеристик
        if "Характеристики" in params and isinstance(params["Характеристики"], list):
            for char in params["Характеристики"]:
                if "Наименование" in char and isinstance(char["Наименование"], str):
                    char["Наименование"] = normalize_string(char["Наименование"])

    return data


# Затем в функции load_data:
def load_data(uploaded_file):
    try:
        data = json.load(uploaded_file)
        # Нормализуем данные сразу после загрузки
        return normalize_data(data)
    except Exception as e:
        st.error(f"Ошибка чтения JSON: {e}")
        return None


def is_empty_value(val):
    """Проверяем, является ли значение по-настоящему пустым"""
    if val is None:
        return True

    if isinstance(val, (int, float)):
        return False

    val_str = str(val).strip()
    if not val_str:
        return True

    empty_patterns = [
        "", "null", "none", "nan", "undefined",
        "нет", "не указано", "не задано", "не определено",
        "-", "–", "—", "―", "−",
        "n/a", "na", "n.a.", "n.a", "n\\a",
        "пусто", "отсутствует", "не заполнено"
    ]

    val_lower = val_str.lower()
    if val_lower in empty_patterns:
        return True

    special_empty = ["\u200b", "\u00a0", "\u3000", "\u200e", "\u200f", "\u202a", "\u202c"]
    if val_str in special_empty:
        return True

    import re
    if re.fullmatch(r'[\s\-_\.]+', val_str):
        return True

    return False


def format_top_goods(raw_data, top_n):
    """
    Формирует текст с топ-N товаров по количеству предложений.
    Включает единицы измерения и общее количество предложений.
    Возвращает строку для копирования.
    """
    items = raw_data.get('Товары', [])
    if not items:
        return "Нет товаров"

    # Создаем маппинг ID характеристики -> {name, unit}
    char_info = {}
    for char in raw_data.get('ПараметрыТовара', {}).get('Характеристики', []):
        char_id = char['ID']
        char_info[char_id] = {
            'name': char.get('Наименование', ''),
            'unit': char.get('ЕдиницаИзмеренияХарактеристики', '')
        }

    offers_keys = ["9000048005", "9000048006", "Всего предложений", "Предложения", "Количество предложений"]

    # Собираем товары с количеством предложений
    goods_with_offers = []
    for item in items:
        chars = item.get('Характеристики', {})
        offers_count = 0
        for key in offers_keys:
            if key in chars:
                try:
                    offers_count = int(chars[key])
                    break
                except (ValueError, TypeError):
                    pass
        goods_with_offers.append((offers_count, item))

    # Сортируем по убыванию предложений
    goods_with_offers.sort(key=lambda x: x[0], reverse=True)
    top_goods = goods_with_offers[:top_n]

    category_name = raw_data.get('ПараметрыТовара', {}).get('Наименование', 'Категория')
    lines = []
    for offers, item in top_goods:
        parts = [category_name]
        chars = item.get('Характеристики', {})
        for char_id, value in chars.items():
            if char_id in offers_keys:
                continue
            if char_id not in char_info:
                continue
            info = char_info[char_id]
            if is_empty_value(value):
                continue
            # Формируем часть "название значение единица"
            part = info['name']
            if value is not None:
                part += f" {value}"
            if info['unit'] and not is_empty_value(info['unit']):
                part += f" {info['unit']}"
            parts.append(part)
        # Добавляем общее количество предложений
        parts.append(f"Предложений: {offers}")
        line = ", ".join(parts)
        lines.append(line)

    return "\n\n".join(lines)
def process_characteristics(data, black_list):
    params_info = data.get("ПараметрыТовара", {}).get("Характеристики", [])
    items = data.get("Товары", [])

    char_map = {}
    name_to_ids = defaultdict(list)

    for char in params_info:
        char_id = char["ID"]
        char_name = char["Наименование"]
        char_map[char_id] = {
            "name": char_name,
            "original_name": char_name,
            "is_extra": bool(char.get("ДополнительнаяХарактеристика", 0)),
            "unit": char.get("ЕдиницаИзмеренияХарактеристики", ""),
            "priority": char.get("ПриоритетВИмени", 0),
            "values": defaultdict(lambda: {"items": set(), "offers": 0}),
            "items_with_char": set(),
            "values": defaultdict(lambda: {"items": set(), "offers": 0}),
            "had_split": False,
            "split_examples": []
        }
        name_to_ids[char_name].append(char_id)

    total_items = len(items)

    # ────────────────────────────────────────────────────────────────
    # Новый сбор значений с автоматическим разбиением по ", "
    # ────────────────────────────────────────────────────────────────

    for item_idx, item in enumerate(items):
        item_chars = item.get("Характеристики", {})

        offers_count = 0
        offers_keys = ["9000048005", "9000048006", "Всего предложений", "Предложения", "Количество предложений"]
        for key in offers_keys:
            if key in item_chars:
                try:
                    offers_count = int(item_chars[key])
                    break
                except (ValueError, TypeError):
                    offers_count = 0

        for c_id, raw_val in item_chars.items():
            if c_id in offers_keys:
                continue
            if c_id not in char_map:
                continue
            if is_empty_value(raw_val):
                continue

            val_str = str(raw_val).strip()

            # Разбиваем, если есть ", "
            if ", " in val_str:
                parts = [p.strip() for p in val_str.split(", ") if p.strip()]
                if len(parts) > 1:
                    char_map[c_id]["had_split"] = True
                    if len(char_map[c_id]["split_examples"]) < 3:
                        char_map[c_id]["split_examples"].append(val_str)
            else:
                parts = [val_str]

            for part in parts:
                if not part: continue
                char_map[c_id]["values"][part]["items"].add(item_idx)
                char_map[c_id]["items_with_char"].add(item_idx)
                char_map[c_id]["values"][part]["offers"] += offers_count

    result = []
    duplicate_names = {name: ids for name, ids in name_to_ids.items() if len(ids) > 1}

    for c_id, info in char_map.items():
        is_in_black_list = (c_id in black_list) or (info["name"] in black_list) or \
                           any(x in info["name"].lower() for x in ["ед.изм", "едизм", "ед изм"])

        items_with_char_count = len(info["items_with_char"])
        fill_rate = (items_with_char_count / total_items) * 100 if total_items > 0 else 0

        values_data_formatted = {}
        for val, stats in info["values"].items():
            items_count = len(stats["items"])
            values_data_formatted[val] = {
                "count": items_count,
                "offers": stats["offers"]
            }

        is_duplicate = info["name"] in duplicate_names
        had_split = False
        split_examples = []
        original_values = set()
        for val in info["values"]:
            # грубая эвристика — если значение короткое и не содержит запятой — скорее всего оно появилось после разбиения
            if len(val) <= 60 and ", " not in val:
                original_values.add(val)
        result.append({
            "id": c_id,
            "name": info["name"],
            "original_name": info["original_name"],
            "is_extra": info["is_extra"],
            "unit": info["unit"],
            "priority": info["priority"],
            "fill_rate": fill_rate,
            "items_with_char_count": items_with_char_count,
            "total_items": total_items,
            "values_data": values_data_formatted,
            "in_black_list": is_in_black_list,
            "is_duplicate": is_duplicate,
            "duplicate_ids": duplicate_names.get(info["name"], []),
            "had_split": info.get("had_split", False),
            "split_examples": info.get("split_examples", [])
        })

    return result, duplicate_names


# --- Callback-функции ---
def toggle_preview(char_id):
    preview_key = f"preview_{char_id}"
    st.session_state[preview_key] = not st.session_state.get(preview_key, False)


def toggle_json(char_id):
    json_key = f"json_{char_id}"
    st.session_state[json_key] = not st.session_state.get(json_key, False)


def apply_global_settings():
    """Применить глобальные настройки ко всем характеристикам"""
    new_mode = st.session_state.global_mode_selector
    st.session_state.global_mode = new_mode

    # Синхронизируем все индивидуальные режимы
    for key in list(st.session_state.keys()):
        if key.startswith("mode_"):
            st.session_state[key] = new_mode

    # Применяем глобальный Top N ко всем характеристикам в режиме Top N
    for key in list(st.session_state.keys()):
        if key.startswith("topn_"):
            char_id = key.split("_")[1]
            mode_key = f"mode_{char_id}"

            # Обновляем только если характеристика в режиме Top N
            if st.session_state.get(mode_key) == "Top N":
                st.session_state[key] = st.session_state.global_top_n


def update_black_list():
    """Обновить черный список"""
    new_black_list = st.session_state.black_list_textarea
    st.session_state.black_list = [x.strip() for x in new_black_list.split(",") if x.strip()]


def save_edited_name(char_id):
    """Сохранить отредактированное название характеристики"""
    edit_key = f"edit_name_{char_id}"
    if edit_key in st.session_state:
        st.session_state.edited_names[char_id] = st.session_state[edit_key]
        st.session_state[f"json_{char_id}"] = False  # Закрываем JSON панель


def update_global_top_n():
    """Обновить глобальный Top N и применить к характеристикам в режиме Top N"""
    # Обновляем глобальное значение
    st.session_state.global_top_n = st.session_state.global_top_n_input

    # Применяем ко всем характеристикам в режиме Top N
    for key in list(st.session_state.keys()):
        if key.startswith("topn_"):
            char_id = key.split("_")[1]
            mode_key = f"mode_{char_id}"

            # Обновляем только если характеристика в режиме Top N
            if st.session_state.get(mode_key) == "Top N":
                # Проверяем, чтобы новое значение не превышало максимальное
                all_vals_count = st.session_state.get(f"vals_count_{char_id}", 1)
                safe_max_val = max(1, all_vals_count)
                new_value = min(st.session_state.global_top_n, safe_max_val)
                st.session_state[key] = new_value


# --- Приложение ---
def main(app_state=None, settings_mode=False, site_config=None, task_config=None, context=None):
    load_css()

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

        print(f"✅ Phase1 загружен домен из файла: {saved_domain}")

    # ========== ПРОВЕРКА СМЕНЫ ПРОЕКТА ==========
    current_project_id = st.session_state.get('current_project_id')
    last_loaded = st.session_state.get('phase1_last_loaded_project')

    # Если project_id изменился (создан новый проект или переключились)
    if current_project_id and last_loaded != current_project_id:
        # Сбрасываем данные Phase1
        st.session_state.processed_chars = None
        st.session_state.raw_data = None
        st.session_state.uploaded_filename = None
        st.session_state.category_name = ""

        # Обновляем ID последнего загруженного проекта
        st.session_state.phase1_last_loaded_project = current_project_id

    # ========== ПОЛУЧАЕМ КОНТЕКСТ ==========
    ctx_data = _get_context_data(context, st.session_state)

    if ctx_data['has_context']:
        # Используем контекст
        user_id = ctx_data['user_id']
        current_id = ctx_data['project_id']
        site_name = ctx_data['site_name']
        domain_name = ctx_data['domain_name']

        # Имя проекта берем из контекста
        project_name_from_context = ctx_data.get('project_name')
        if project_name_from_context and project_name_from_context != 'None':
            st.session_state.project_name = project_name_from_context
        else:
            if not st.session_state.get('project_name') or st.session_state.project_name == 'None':
                st.session_state.project_name = "Новый проект"

        st.success(f"📁 ТЕКУЩИЙ ПРОЕКТ: **{st.session_state.project_name}** (из контекста)")
    else:
        # Используем st.session_state (старый режим)
        from pathlib import Path
        import json

        current_id = st.session_state.get('current_project_id')
        user_id = st.session_state.get('user_id')

        if 'domain_manager' in st.session_state:
            dm = st.session_state.domain_manager
        else:
            from domain_manager import DomainManager
            dm = DomainManager()

        project_name_from_file = None
        if current_id and user_id:
            project_file = Path(f"sites/{dm.site_name}/domains/{dm.get_current_domain()}/projects/{user_id}/{current_id}.json")

            if project_file.exists():
                try:
                    with open(project_file, 'r', encoding='utf-8') as f:
                        file_data = json.load(f)
                        project_name_from_file = file_data.get('project_name')
                        if not project_name_from_file:
                            project_name_from_file = file_data.get('app_data', {}).get('project_name')
                        if not project_name_from_file:
                            project_name_from_file = file_data.get('app_data', {}).get('category')
                        print(f"📁 Имя проекта из файла: {project_name_from_file}")
                except Exception as e:
                    print(f"Ошибка чтения файла: {e}")

        if project_name_from_file and project_name_from_file != 'None':
            st.session_state.project_name = project_name_from_file
        else:
            if not st.session_state.get('project_name') or st.session_state.project_name == 'None':
                st.session_state.project_name = "Новый проект"

        st.success(f"📁 ТЕКУЩИЙ ПРОЕКТ: **{st.session_state.project_name}**")

    # ========== ИМПОРТ ПАРСЕРОВ ==========
    try:
        from phase1_parsers import get_parser, normalize_string as parser_normalize
        PARSERS_AVAILABLE = True
    except ImportError:
        PARSERS_AVAILABLE = False
        def parser_normalize(s):
            if not isinstance(s, str):
                return s
            return ' '.join(s.split())

    # ========== СОХРАНЯЕМ КОНФИГУРАЦИЮ ==========
    if site_config and task_config:
        st.session_state.current_site_config = site_config
        st.session_state.current_task_config = task_config

        parser_type = task_config.get('phase1_config', {}).get('parser', 'steelborg')

        if PARSERS_AVAILABLE:
            st.session_state.current_parser = get_parser(parser_type)
            print(f"✅ Phase1: Используется парсер '{parser_type}' для задачи '{task_config.get('name', 'unknown')}'")
        else:
            st.warning("⚠️ Модуль парсеров не найден. Используется стандартная логика.")
            st.session_state.current_parser = None

    # ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ЧЁРНЫМ СПИСКОМ ==========
    def update_black_list():
        new_black_list = st.session_state.black_list_textarea
        st.session_state.black_list = [x.strip() for x in new_black_list.split(",") if x.strip()]

    def update_global_top_n():
        st.session_state.global_top_n = st.session_state.global_top_n_input
        for key in list(st.session_state.keys()):
            if key.startswith("topn_"):
                char_id = key.split("_")[1]
                mode_key = f"mode_{char_id}"
                if st.session_state.get(mode_key) == "Top N":
                    all_vals_count = st.session_state.get(f"vals_count_{char_id}", 1)
                    safe_max_val = max(1, all_vals_count)
                    new_value = min(st.session_state.global_top_n, safe_max_val)
                    st.session_state[key] = new_value

    def apply_global_settings():
        new_mode = st.session_state.global_mode_selector
        st.session_state.global_mode = new_mode
        for key in list(st.session_state.keys()):
            if key.startswith("mode_"):
                st.session_state[key] = new_mode
        for key in list(st.session_state.keys()):
            if key.startswith("topn_"):
                char_id = key.split("_")[1]
                mode_key = f"mode_{char_id}"
                if st.session_state.get(mode_key) == "Top N":
                    st.session_state[key] = st.session_state.global_top_n

    def toggle_preview(char_id):
        preview_key = f"preview_{char_id}"
        st.session_state[preview_key] = not st.session_state.get(preview_key, False)

    def toggle_json(char_id):
        json_key = f"json_{char_id}"
        st.session_state[json_key] = not st.session_state.get(json_key, False)

    def save_edited_name(char_id):
        edit_key = f"edit_name_{char_id}"
        if edit_key in st.session_state:
            st.session_state.edited_names[char_id] = st.session_state[edit_key]
            st.session_state[f"json_{char_id}"] = False

    # ========== ИНИЦИАЛИЗАЦИЯ SESSION_STATE ==========
    defaults = {
        'black_list': ["Цена", "Всего предложений", "Единица измерения", "Комментарий"],
        'global_top_n': 5,
        'global_mode': "Top N",
        'edited_names': {},
        'category_name': "",
        'uploaded_filename': None,
        'processed_chars': None,
        'duplicate_names': None,
        'raw_data': None
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # ========== ВОССТАНОВЛЕНИЕ ДАННЫХ ИЗ APP_STATE ==========
    if app_state and 'phase1' in st.session_state.app_data:
        saved_phase1 = st.session_state.app_data['phase1']
        current_project_id = st.session_state.get('current_project_id')
        last_loaded_project = st.session_state.get('phase1_last_loaded_project')

        if saved_phase1 and (last_loaded_project == current_project_id) and not st.session_state.processed_chars:
            st.session_state.category_name = saved_phase1.get('category', '')
            st.session_state.uploaded_filename = saved_phase1.get('metadata', {}).get('source_file', 'Восстановленный проект')

            restored_chars = []
            for char in saved_phase1.get('characteristics', []):
                values_data = {}
                for v in char.get('values', []):
                    values_data[v['value']] = {
                        "count": v.get('items_count', 0),
                        "offers": v.get('offers_sum', 0)
                    }

                restored_chars.append({
                    "id": char.get('char_id', ''),
                    "name": char.get('char_name', ''),
                    "original_name": char.get('original_name', char.get('char_name', '')),
                    "is_extra": False,
                    "unit": char.get('unit', ''),
                    "priority": char.get('priority', 0),
                    "fill_rate": char.get('fill_rate', 0),
                    "items_with_char_count": char.get('items_with_char_count', 0),
                    "total_items": saved_phase1.get('metadata', {}).get('total_items', 0),
                    "values_data": values_data,
                    "in_black_list": False,
                    "is_duplicate": char.get('is_duplicate', False),
                    "duplicate_ids": [],
                    "had_split": char.get('had_split', False),
                    "split_examples": char.get('split_examples', [])
                })

            st.session_state.processed_chars = restored_chars

            from collections import defaultdict
            name_to_ids = defaultdict(list)
            for char in restored_chars:
                name_to_ids[char['name']].append(char['id'])
            duplicate_names = {name: ids for name, ids in name_to_ids.items() if len(ids) > 1}
            st.session_state.duplicate_names = duplicate_names

            st.session_state.raw_data = {
                "Товары": [{}] * saved_phase1.get('metadata', {}).get('total_items', 0),
                "ПараметрыТовара": {
                    "Наименование": saved_phase1.get('category', ''),
                    "Характеристики": []
                }
            }

            for char in saved_phase1.get('characteristics', []):
                if char.get('char_name') != char.get('original_name'):
                    st.session_state.edited_names[char.get('char_id', '')] = char.get('char_name', '')

            st.session_state.data_restored = True
            st.session_state.phase1_last_loaded_project = current_project_id

    # ========== SIDEBAR ==========
    with st.sidebar:
        st.header("Загрузка данных")

        if st.session_state.get('current_task_config'):
            task_name = st.session_state.current_task_config.get('name', 'Неизвестно')
            parser_type = st.session_state.current_task_config.get('phase1_config', {}).get('parser', 'steelborg')
            st.info(f"📋 Активная задача: **{task_name}**\n\n🔧 Парсер: `{parser_type}`")

        with st.expander("Гайд"):
            st.markdown("""
                1. Выберите файл json для обработки (Browse files)
                2. Для характеристик, которые не нужно делать переменной - поставить not var
                3. Установите модель и параметры  
                4. Запустите генерацию  
                """)

        uploaded_file = st.file_uploader(
            "📁 Загрузите JSON файл категории",
            type="json",
            help="Выберите JSON файл с данными о товарах и характеристиках",
            key="phase1_file_uploader"
        )

        st.markdown("---")
        st.header("Настройки")

        with st.expander("🚫 Черный список"):
            st.text_area(
                "Список ID или имен (через запятую)",
                value=", ".join(st.session_state.black_list),
                key="black_list_textarea",
                on_change=update_black_list,
                height=150
            )

        st.number_input(
            "🌐 Top N для всех характеристик",
            min_value=1,
            max_value=100,
            value=st.session_state.global_top_n,
            key="global_top_n_input",
            on_change=update_global_top_n,
            help="Будет применён ко всем характеристикам в режиме 'Top N'"
        )

    # ========== ОБРАБОТКА ЗАГРУЖЕННОГО ФАЙЛА ==========
    if uploaded_file:
        current_project_id = st.session_state.get('current_project_id')

        # Проверяем соответствие проекта
        if (st.session_state.uploaded_filename != uploaded_file.name or
                st.session_state.processed_chars is None or
                st.session_state.get('phase1_last_loaded_project') != current_project_id):

            # Если проект не совпадает - очищаем
            if st.session_state.get('phase1_last_loaded_project') != current_project_id:
                st.session_state.processed_chars = None
                st.session_state.raw_data = None
                st.session_state.uploaded_filename = None
                st.session_state.category_name = ""
                st.session_state.phase1_last_loaded_project = current_project_id


            raw_data = load_data(uploaded_file)
            if raw_data:
                st.session_state.raw_data = raw_data

                if hasattr(st.session_state, 'current_parser') and st.session_state.current_parser:
                    parser = st.session_state.current_parser
                    phase1_config = st.session_state.current_task_config.get('phase1_config', {})

                    try:
                        st.session_state.processed_chars, st.session_state.duplicate_names = parser.parse(
                            raw_data,
                            st.session_state.black_list,
                            phase1_config
                        )
                        print(f"✅ Парсер '{parser.__class__.__name__}' успешно обработал данные")
                        print(f"   Найдено характеристик: {len(st.session_state.processed_chars)}")

                    except Exception as e:
                        st.error(f"❌ Ошибка при парсинге данных: {e}")
                        import traceback
                        st.code(traceback.format_exc())
                        st.warning("⚠️ Использую стандартную логику обработки...")
                        st.session_state.processed_chars, st.session_state.duplicate_names = process_characteristics(
                            raw_data, st.session_state.black_list
                        )
                else:
                    st.session_state.processed_chars, st.session_state.duplicate_names = process_characteristics(
                        raw_data, st.session_state.black_list
                    )

                st.session_state.uploaded_filename = uploaded_file.name

                original_category = raw_data.get('ПараметрыТовара', {}).get('Наименование', '')
                if original_category:
                    st.session_state.category_name = parser_normalize(original_category)
                else:
                    filename = uploaded_file.name
                    base_name = os.path.splitext(filename)[0]
                    st.session_state.category_name = parser_normalize(base_name)

                if not st.session_state.category_name:
                    st.error("❌ category_name не установлен! Использую значение по умолчанию")
                    st.session_state.category_name = "Новая категория"

    # ========== ОТОБРАЖЕНИЕ ИНТЕРФЕЙСА ==========
    selected_configs = {}
    if (uploaded_file and st.session_state.raw_data) or st.session_state.processed_chars:

        if not (uploaded_file and st.session_state.raw_data) and st.session_state.processed_chars:
            raw_data = st.session_state.raw_data or {
                "Товары": [],
                "ПараметрыТовара": {"Наименование": st.session_state.category_name}
            }
            processed_chars = st.session_state.processed_chars
            duplicate_names = st.session_state.duplicate_names or {}
        else:
            raw_data = st.session_state.raw_data
            processed_chars = st.session_state.processed_chars
            duplicate_names = st.session_state.duplicate_names

        col1, col2 = st.columns(2)
        with col1:
            if uploaded_file:
                st.subheader(f"📁 Файл: {uploaded_file.name}")
            else:
                st.subheader(f"📁 Проект: {st.session_state.uploaded_filename}")

            if st.session_state.get('current_task_config'):
                task_name = st.session_state.current_task_config.get('name', '')
                if task_name:
                    st.caption(f"🎯 Тип задачи: {task_name}")

            st.info(f"Категория: {raw_data.get('ПараметрыТовара', {}).get('Наименование', st.session_state.category_name)}")

        if duplicate_names:
            with st.expander("⚠️ Внимание: Обнаружены дублирующиеся названия", expanded=False):
                st.warning("Обнаружены характеристики с одинаковыми названиями!")
                for name, ids in list(duplicate_names.items())[:10]:
                    st.error(f"**'{name}'** встречается у ID: {', '.join(ids)}")

        st.markdown("### Объем данных для всех характеристик")
        col_sync1, col_sync2 = st.columns([3, 1])
        with col_sync1:
            current_mode_idx = ["Все", "Top N", "Вручную"].index(st.session_state.global_mode)
            st.radio(
                "Выберите режим для всех характеристик:",
                ["Все", "Top N", "Вручную"],
                horizontal=True,
                key="global_mode_selector",
                index=current_mode_idx
            )
        with col_sync2:
            if st.button("🔄 Применить ко всем", type="primary", key="apply_global_btn"):
                apply_global_settings()



        for char in processed_chars:
            if char.get("in_black_list", False):
                continue

            char_id = char["id"]
            all_vals_count = len(char['values_data'])

            st.session_state[f"vals_count_{char_id}"] = all_vals_count
            if f"expanded_{char_id}" not in st.session_state:
                st.session_state[f"expanded_{char_id}"] = False

            display_name = st.session_state.edited_names.get(char_id, char['name'])

            container_class = "characteristic-container"
            if char['is_duplicate']:
                container_class += " duplicate-char"
            elif char['is_extra']:
                container_class += " extra-char"
            else:
                container_class += " normal-char"

            with st.container():
                st.markdown(f'<div class="{container_class}">', unsafe_allow_html=True)

                if char.get("had_split", False):
                    with st.expander("⚠️ Значения были разбиты по запятой", expanded=False):
                        st.warning("В исходных данных некоторые значения содержали несколько элементов через запятую. Программа автоматически разбила их.")
                        for ex in char.get("split_examples", [])[:3]:
                            st.code(ex, language=None)

                cols = st.columns([2.2, 1, 0.7, 2.2, 0.6])

                with cols[0]:
                    label_parts = [f"**{display_name}**"]
                    if char['is_duplicate']:
                        label_parts.append("🔄")
                    if char['is_extra']:
                        label_parts.append("➕")
                    label = " ".join(label_parts)

                    is_active = st.checkbox(label, value=not char['is_extra'], key=f"act_{char_id}")

                    info_parts = []
                    if char['id']:
                        info_parts.append(f"ID:{char['id']}")
                    if char['priority']:
                        info_parts.append(f"P:{char['priority']}")
                    if char['unit']:
                        info_parts.append(char['unit'])
                    st.caption(" | ".join(info_parts))

                with cols[1]:
                    total_offers = sum(v['offers'] for v in char['values_data'].values())
                    st.markdown(
                        f"<span style='font-size:0.9rem;'>📊 {char['fill_rate']:.0f}%</span><br>"
                        f"<span style='font-size:0.8rem; color:#64748b;'>📦 {total_offers}</span>",
                        unsafe_allow_html=True
                    )

                with cols[2]:
                    st.checkbox("Not var", key=f"uniq_{char_id}", help="Не делать переменной")

                with cols[3]:
                    mode_key = f"mode_{char_id}"
                    if mode_key not in st.session_state:
                        st.session_state[mode_key] = st.session_state.global_mode

                    mode = st.radio(
                        "Режим",
                        ["Все", "Top N", "Вручную"],
                        index=["Все", "Top N", "Вручную"].index(st.session_state[mode_key]),
                        key=mode_key,
                        horizontal=True,
                        label_visibility="collapsed"
                    )

                    if mode == "Top N":
                        safe_max = max(1, all_vals_count)
                        safe_default = min(st.session_state.global_top_n, safe_max)
                        topn_key = f"topn_{char_id}"
                        if topn_key not in st.session_state:
                            st.session_state[topn_key] = safe_default
                        st.number_input("N", min_value=1, max_value=safe_max, value=st.session_state[topn_key], key=topn_key, label_visibility="collapsed")
                    elif mode == "Вручную" and all_vals_count > 0:
                        available_vals = list(char['values_data'].keys())
                        if len(available_vals) > 50:
                            available_vals = available_vals[:50]
                        st.multiselect("Выберите значения", available_vals, key=f"manual_{char_id}", label_visibility="collapsed")
                    elif mode == "Вручную":
                        st.caption("Нет значений")

                with cols[4]:
                    expand_label = "▼" if st.session_state[f"expanded_{char_id}"] else "▶"
                    if st.button(expand_label, key=f"expand_btn_{char_id}", help="Дополнительные настройки", type="secondary"):
                        st.session_state[f"expanded_{char_id}"] = not st.session_state[f"expanded_{char_id}"]
                        st.rerun()

                if st.session_state.get(f"expanded_{char_id}", False):
                    st.markdown('<div class="compact-details-panel">', unsafe_allow_html=True)

                    sort_by = st.selectbox("Сортировка значений", ["Предложения", "Кол-во товаров"], key=f"sort_{char_id}")

                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("🔍 Предпросмотр", key=f"btn_preview_{char_id}"):
                            st.session_state[f"preview_{char_id}"] = not st.session_state.get(f"preview_{char_id}", False)
                            st.rerun()
                    with col_btn2:
                        if st.button("📋 JSON", key=f"btn_json_{char_id}"):
                            st.session_state[f"json_{char_id}"] = not st.session_state.get(f"json_{char_id}", False)
                            st.rerun()

                    if st.session_state.get(f"preview_{char_id}", False):
                        with st.expander("🔍 Предпросмотр значений", expanded=True):
                            if all_vals_count == 0:
                                st.info("Нет значений")
                            else:
                                sorted_vals = []
                                for val, stats in char['values_data'].items():
                                    sorted_vals.append({
                                        "Значение": val[:100] + ("..." if len(val) > 100 else ""),
                                        "Товары": stats["count"],
                                        "Предложения": stats["offers"],
                                        "%": f"{(stats['count'] / len(raw_data.get('Товары', [])) * 100):.1f}" if raw_data.get('Товары') else "0"
                                    })

                                if sort_by == "Предложения":
                                    sorted_vals.sort(key=lambda x: x['Предложения'], reverse=True)
                                else:
                                    sorted_vals.sort(key=lambda x: x['Товары'], reverse=True)

                                preview_size = min(10, len(sorted_vals))
                                st.write(f"**Топ-{preview_size} значений** (всего: {all_vals_count})")
                                st.dataframe(sorted_vals[:preview_size], use_container_width=True)

                    if st.session_state.get(f"json_{char_id}", False):
                        with st.expander("📝 Редактирование / JSON", expanded=True):
                            col_edit1, col_edit2 = st.columns([3, 1])
                            with col_edit1:
                                st.text_input("Новое название", value=display_name, key=f"edit_name_{char_id}")
                            with col_edit2:
                                if st.button("💾 Сохранить", key=f"save_name_{char_id}"):
                                    st.session_state.edited_names[char_id] = st.session_state[f"edit_name_{char_id}"]
                                    st.session_state[f"json_{char_id}"] = False
                                    st.rerun()
                                if st.button("❌ Отмена", key=f"cancel_edit_{char_id}"):
                                    st.session_state[f"json_{char_id}"] = False
                                    st.rerun()

                            char_data = None
                            params_info = raw_data.get("ПараметрыТовара", {}).get("Характеристики", [])
                            for param in params_info:
                                if param.get("ID") == char_id:
                                    char_data = param
                                    break
                            if char_data:
                                st.json(char_data)

                    st.markdown('</div>', unsafe_allow_html=True)

                if is_active:
                    n_val_selected = (
                        st.session_state.get(f"topn_{char_id}", "all") if mode == "Top N"
                        else (st.session_state.get(f"manual_{char_id}", []) if mode == "Вручную" else "all")
                    )
                    selected_configs[char_id] = {
                        "name": display_name,
                        "original_name": char['original_name'],
                        "unit": char['unit'],
                        "is_unique": st.session_state.get(f"uniq_{char_id}", False),
                        "sort_by": st.session_state.get(f"sort_{char_id}", "Предложения"),
                        "mode": mode,
                        "n_val": n_val_selected,
                        "source_data": char['values_data'],
                        "is_duplicate": char['is_duplicate']
                    }

                st.markdown('</div>', unsafe_allow_html=True)
    # ========== ФОРМИРОВАНИЕ ИТОГОВОГО МАССИВА ==========
    final_output = []

    if selected_configs:
        # Кнопка теперь ВНЕ условия с selected_configs
        if st.button("🚀 Сформировать итоговый массив", type="primary", key="btn_generate_final"):
            items_list = raw_data.get("Товары", []) if "Товары" in raw_data else []

            for c_id, cfg in selected_configs.items():
                raw_vals = []
                for val, stats in cfg['source_data'].items():
                    raw_vals.append({
                        "value": val,
                        "items_count": stats["count"],
                        "offers_sum": stats["offers"],
                        "percent": (stats["count"] / len(items_list) * 100) if items_list else 0
                    })

                if cfg['sort_by'] == "Предложения":
                    raw_vals.sort(key=lambda x: x['offers_sum'], reverse=True)
                else:
                    raw_vals.sort(key=lambda x: x['items_count'], reverse=True)

                if cfg['mode'] == "Top N":
                    processed_vals = raw_vals[:cfg['n_val']]
                elif cfg['mode'] == "Вручную":
                    processed_vals = [v for v in raw_vals if v['value'] in cfg['n_val']]
                else:
                    processed_vals = raw_vals

                final_output.append({
                    "char_id": c_id,
                    "char_name": cfg['name'],
                    "original_name": cfg['original_name'],
                    "unit": cfg['unit'],
                    "is_unique": cfg['is_unique'],
                    "values": processed_vals,
                    "is_duplicate": cfg.get('is_duplicate', False)
                })

            # Нормализуем название категории
            st.session_state.category_name = parser_normalize(st.session_state.category_name)

            if not st.session_state.get('current_project_id'):
                st.error("❌ Нет активного проекта! Сначала создайте или выберите проект.")
                st.stop()

    # ========== СОХРАНЕНИЕ ==========
    # Теперь сохранение ВНЕ условия с кнопкой
    if final_output:  # Проверяем, что массив сформирован
        # Получаем имя проекта
        if ctx_data['has_context']:
            current_project_name = ctx_data.get('project_name',
                                                st.session_state.get('project_name', st.session_state.category_name))
        else:
            current_project_name = st.session_state.get('project_name', st.session_state.category_name)

        if not current_project_name or current_project_name == 'None':
            current_project_name = st.session_state.category_name
            st.warning(f"⚠️ project_name был пуст, установлен как: '{current_project_name}'")
        else:
            st.info(f"✅ Сохраняем project_name: '{current_project_name}'")

        # Формируем данные для сохранения
        phase1_data = {
            "category": st.session_state.category_name,
            "project_name": current_project_name,
            "characteristics": final_output,
            "metadata": {
                "source_file": uploaded_file.name if uploaded_file else st.session_state.uploaded_filename,
                "original_category": raw_data.get("ПараметрыТовара", {}).get("Наименование", "Неизвестно"),
                "total_items": len(items_list),
                "selected_characteristics_count": len(final_output),
                "export_timestamp": datetime.now().isoformat()
            }
        }

        # ========== СОХРАНЯЕМ В КОНТЕКСТ (ЕСЛИ ЕСТЬ) ==========
        if ctx_data['has_context'] and context is not None:
            context.set_phase_data(1, phase1_data)
            context.set('category', st.session_state.category_name)
            context.set('project_name', current_project_name)
            context.save()
            st.success(f"✅ Данные сохранены в контекст!")
            st.success(f"📁 Проект: {current_project_name}")
            st.success(f"🏷️ Категория: {st.session_state.category_name}")
            st.balloons()

        # ========== СОХРАНЯЕМ В APP_STATE И ФАЙЛ ==========
        if 'app_data' not in st.session_state:
            st.session_state.app_data = {}

        st.session_state.app_data['category'] = st.session_state.category_name
        st.session_state.app_data['project_name'] = current_project_name
        st.session_state.app_data['phase1'] = phase1_data

        if app_state is not None:
            try:
                app_state.set_phase_data(1, phase1_data)
                app_state.save_project()
                st.success(f"✅ Данные сохранены через app_state")
            except Exception as e:
                st.warning(f"⚠️ Ошибка при сохранении через app_state: {e}")

        # ========== ПРЯМОЕ СОХРАНЕНИЕ В ФАЙЛ ==========
        try:
            from pathlib import Path
            import json

            if 'domain_manager' not in st.session_state:
                from domain_manager import DomainManager
                st.session_state.domain_manager = DomainManager()

            dm = st.session_state.domain_manager
            user_id = ctx_data.get('user_id') if ctx_data['has_context'] else st.session_state.get('user_id')
            project_id = ctx_data.get('project_id') if ctx_data['has_context'] else st.session_state.get(
                'current_project_id')

            if user_id and project_id:
                if project_id != st.session_state.get('phase1_last_loaded_project'):
                    st.session_state.phase1_last_loaded_project = project_id
                project_file = Path(
                    f"sites/{dm.site_name}/domains/{dm.get_current_domain()}/projects/{user_id}/{project_id}.json")

                if project_file.exists():
                    with open(project_file, 'r', encoding='utf-8') as f:
                        file_data = json.load(f)

                    if 'app_data' not in file_data:
                        file_data['app_data'] = {}

                    file_data['app_data']['phase1'] = phase1_data
                    file_data['app_data']['category'] = st.session_state.category_name
                    file_data['app_data']['project_name'] = current_project_name
                    file_data['category'] = st.session_state.category_name
                    file_data['project_name'] = current_project_name

                    with open(project_file, 'w', encoding='utf-8') as f:
                        json.dump(file_data, f, ensure_ascii=False, indent=2)

                    st.success(f"✅ Данные сохранены в файл: {project_file}")
                    st.success(f"📁 Проект: {current_project_name}")
                    st.success(f"🏷️ Категория: {st.session_state.category_name}")
                    st.balloons()
                else:
                    st.warning(f"⚠️ Файл проекта не найден: {project_file}")
                    st.info("💡 Создайте проект через интерфейс перед сохранением")
            else:
                st.error("❌ Не удалось определить user_id или project_id для сохранения")

        except Exception as e:
            st.error(f"❌ Ошибка при сохранении файла: {e}")
            import traceback
            st.code(traceback.format_exc())

        # Показываем результат
        with st.expander("📊 Просмотр итоговых данных", expanded=False):
            st.json(phase1_data)

        # Кнопка скачивания
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{st.session_state.category_name}_{timestamp}.json"
        st.download_button(
            "💾 Скачать JSON данные",
            data=json.dumps(phase1_data, ensure_ascii=False, indent=4),
            file_name=filename,
            mime="application/json",
            key="btn_download_json"
        )


    elif uploaded_file:
        st.warning("⏳ Обрабатываю файл...")
    else:
        st.info("📤 Пожалуйста, загрузите JSON файл в боковой панели для начала работы.")


if __name__ == "__main__":
    main()