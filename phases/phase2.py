import streamlit as st
import json
import os
import re
from difflib import get_close_matches
from styles import load_css
from domain_manager import DomainManager
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
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
# --- CSS стили ---
def local_css():
    st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .markers-table-container {
        max-height: 500px;
        overflow-y: auto;
        border: 1px solid #e0e0e0;
        border-radius: 5px;
        padding: 10px;
        background-color: white;
        margin-bottom: 20px;
    }
    .marker-row {
        display: flex;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid #f0f0f0;
    }
    .marker-row:last-child {
        border-bottom: none;
    }
    .marker-name {
        flex: 1;
        padding-left: 10px;
    }
    .marker-type-badge {
        font-size: 0.7em;
        padding: 2px 6px;
        border-radius: 3px;
        margin-left: 8px;
        background-color: #e8f4fd;
        color: #0066cc;
    }
    .category-match {
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
        cursor: pointer;
    }
    .category-match:hover {
        background-color: #e8f4fd;
    }
    .exact-match {
        border-left: 4px solid #28a745;
    }
    .close-match {
        border-left: 4px solid #ffc107;
    }
    .no-match {
        border-left: 4px solid #dc3545;
    }
    .markers-container {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin-bottom: 20px;
    }
    .info-box {
        background-color: #e8f4fd;
        border: 1px solid #b6d4fe;
        border-radius: 5px;
        padding: 15px;
        margin-bottom: 20px;
    }
    .section-header {
        background-color: #f8f9fa;
        padding: 10px;
        border-radius: 5px;
        margin: 15px 0 10px 0;
        font-weight: bold;
        color: #495057;
    }
    </style>
    """, unsafe_allow_html=True)


def load_markers(markers_file="markers.json"):
    """Загружает глобальную базу маркеров"""
    try:
        if os.path.exists(markers_file):
            with open(markers_file, 'r', encoding='utf-8') as f:
                markers_data = json.load(f)
        else:
            markers_data = {
                "Абразивные материалы": [
                    {"name": "абразивные материалы", "priority": 1},
                    {"name": "шлифовальные материалы", "priority": 3}
                ],
                "Адаптер котла": [{"name": "адаптер котла", "priority": 2}],
                "Алюмель": [{"name": "алюмель", "priority": None}]
            }
            save_markers(markers_data, markers_file)
        return markers_data
    except Exception as e:
        st.error(f"Ошибка загрузки маркеров: {e}")
        return {}


def save_markers(markers_data, markers_file="markers.json"):
    try:
        with open(markers_file, 'w', encoding='utf-8') as f:
            json.dump(markers_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"Ошибка сохранения маркеров: {e}")
        return False


def normalize_category_name(name):
    if not name:
        return ""
    normalized = name.lower().strip()
    normalized = re.sub(r'[^\w\s-]', '', normalized)
    words = sorted(normalized.split())
    return ' '.join(words)


def find_category_matches(category_name, markers_data):
    if not category_name or not markers_data:
        return []

    normalized_input = normalize_category_name(category_name)
    matches = []

    for stored_category, markers in markers_data.items():
        normalized_stored = normalize_category_name(stored_category)

        if normalized_input == normalized_stored:
            matches.append({
                'category': stored_category,
                'match_type': 'exact',
                'markers': markers,
                'score': 100
            })
        elif normalized_input in normalized_stored or normalized_stored in normalized_input:
            set_input = set(normalized_input.split())
            set_stored = set(normalized_stored.split())
            if set_input and set_stored:
                match_score = len(set_input & set_stored) / len(set_input | set_stored) * 100
            else:
                match_score = 0
            matches.append({
                'category': stored_category,
                'match_type': 'partial',
                'markers': markers,
                'score': match_score
            })

    if not matches:
        category_names = list(markers_data.keys())
        fuzzy_matches = get_close_matches(category_name, category_names, n=3, cutoff=0.6)
        for match in fuzzy_matches:
            matches.append({
                'category': match,
                'match_type': 'fuzzy',
                'markers': markers_data[match],
                'score': 70
            })

    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches


def get_default_markers():
    if 'default_markers' in st.session_state:
        return st.session_state.default_markers.copy()
    else:
        return ["продукция", "изделие"]


def save_to_session_state(app_state=None, context=None):
    """Сохраняет данные фазы 2 в проект и файл"""

    if 'app_data' not in st.session_state:
        st.session_state.app_data = {}

    original_category = st.session_state.get('original_category_from_phase1', '')
    if not original_category and st.session_state.get('loaded_data'):
        original_category = st.session_state.loaded_data.get('category', '')

    phase2_data = {
        'category': st.session_state.get('selected_category', ''),
        'original_category': original_category,
        'markers': st.session_state.get('phase2_markers', []).copy(),
        'source_category': st.session_state.get('loaded_data', {}).get('category', ''),
        'custom_category_mode': st.session_state.get('custom_category_mode', False)
    }

    # ========== СОХРАНЯЕМ ВО ВСЕ ИСТОЧНИКИ ==========
    success = False

    # 1. Сохраняем в st.session_state (всегда)
    st.session_state.app_data['phase2'] = phase2_data
    success = True

    # 2. Сохраняем в context (если есть)
    if context is not None:
        try:
            context.set_phase_data(2, phase2_data)
            context.save()
            print(f"✅ Phase2 сохранена в контекст")
        except Exception as e:
            print(f"❌ Ошибка сохранения в контекст: {e}")

    # 3. Сохраняем в app_state и ФАЙЛ (ВСЕГДА, если есть app_state)
    if app_state:
        try:
            app_state.set_phase_data(2, phase2_data)
            app_state.save_project()  # <-- Это сохраняет в файл!
            print(f"✅ Phase2 сохранена в файл через app_state")
            success = True
        except Exception as e:
            print(f"❌ Ошибка сохранения через app_state: {e}")

    # 4. Дополнительная проверка: сохраняем напрямую в файл, если знаем путь
    try:
        project_file = st.session_state.get('current_project_file')
        if project_file and os.path.exists(project_file):
            with open(project_file, 'r', encoding='utf-8') as f:
                project_data = json.load(f)

            # Обновляем данные
            if 'phases' not in project_data:
                project_data['phases'] = {}
            project_data['phases']['2'] = phase2_data

            # Сохраняем в файл
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)
            print(f"✅ Phase2 сохранена напрямую в файл: {project_file}")
            success = True
    except Exception as e:
        print(f"⚠️ Не удалось сохранить напрямую в файл: {e}")

    return success


def main(app_state=None, settings_mode=False, site_config=None, task_config=None, context=None):
    # --- ОСНОВНОЕ ПРИЛОЖЕНИЕ ---
    load_css()
    local_css()

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

        print(f"✅ Phase2 загружен домен из файла: {saved_domain}")

    # === ИНИЦИАЛИЗАЦИЯ DOMAIN MANAGER ===
    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()
    dm = st.session_state.domain_manager

    st.info(f"🌐 Текущий домен: **{dm.get_domain_display_name()}**")
    # === ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ ===
    defaults = {
        'phase2_markers': [],
        'selected_category': "",
        'custom_category_mode': False,
        'search_query': "",
        'new_marker_input': "",
        'loaded_data': None,
        'markers_data': load_markers(),
        'default_markers': get_default_markers(),
        'show_default_markers_editor': False,
        'show_marker_editor': False,
        'new_markers_priority': {},
        'phase2_auto_loaded': False  # Флаг для предотвращения двойной загрузки
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # === ЗАГРУЗКА КАТЕГОРИИ ИЗ ФАЗЫ 1 (ГЛАВНЫЙ ПРИОРИТЕТ) ===
    # === ЗАГРУЗКА КАТЕГОРИИ ИЗ ФАЗЫ 1 ===
    # === ЗАГРУЗКА КАТЕГОРИИ ИЗ ФАЗЫ 1 ===
    category_from_phase1 = ""

    # ========== ПОЛУЧАЕМ КОНТЕКСТ ==========
    ctx_data = _get_context_data(context, st.session_state)

    # ========== ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА ==========
    if ctx_data['has_context'] and context is not None:
        phase1_data = context.get_phase_data(1)
        if phase1_data and isinstance(phase1_data, dict):
            category_from_phase1 = phase1_data.get('category', '')
            if not category_from_phase1 and 'metadata' in phase1_data:
                category_from_phase1 = phase1_data['metadata'].get('original_category', '')
            if category_from_phase1:
                print(f"📌 Категория из контекста (фаза 1): {category_from_phase1}")

    # ========== ПРИОРИТЕТ 2: ИЗ APP_STATE ==========
    if not category_from_phase1 and app_state:
        phase1_data = app_state.get_phase_data(1)
        if phase1_data and isinstance(phase1_data, dict):
            category_from_phase1 = phase1_data.get('category', '')
            if not category_from_phase1 and 'metadata' in phase1_data:
                category_from_phase1 = phase1_data['metadata'].get('original_category', '')
            if category_from_phase1:
                print(f"📌 Категория из app_state (фаза 1): {category_from_phase1}")

    # ========== ПРИОРИТЕТ 3: ИЗ ST.SESSION_STATE ==========
    if not category_from_phase1 and 'app_data' in st.session_state:
        phase1_data = st.session_state.app_data.get('phase1', {})
        if phase1_data and isinstance(phase1_data, dict):
            category_from_phase1 = phase1_data.get('category', '')
            if not category_from_phase1 and 'metadata' in phase1_data:
                category_from_phase1 = phase1_data['metadata'].get('original_category', '')
            if category_from_phase1:
                print(f"📌 Категория из st.session_state (фаза 1): {category_from_phase1}")

    # Устанавливаем search_query ТОЛЬКО если есть категория
    if category_from_phase1:
        st.session_state.original_category_from_phase1 = category_from_phase1
        st.session_state.search_query = category_from_phase1  # <-- Теперь тут будет правильная категория
        print(f"✅ Установлен search_query: {category_from_phase1}")

    # 3. Сохраняем оригинальную категорию
    if category_from_phase1:
        st.session_state.original_category_from_phase1 = category_from_phase1
        st.session_state.search_query = category_from_phase1

        # Загружаем данные фазы 1 если нужно
        if not st.session_state.loaded_data:
            if app_state and 'phase1' in st.session_state.app_data:
                st.session_state.loaded_data = st.session_state.app_data['phase1']
            elif 'app_data' in st.session_state:
                st.session_state.loaded_data = st.session_state.app_data.get('phase1')

        # АВТОМАТИЧЕСКИЙ ВЫБОР КАТЕГОРИИ (ЕСЛИ НЕТ СОХРАНЕННЫХ ДАННЫХ)
        if not st.session_state.get('phase2_auto_loaded'):
            if st.session_state.markers_data:
                matches = find_category_matches(category_from_phase1, st.session_state.markers_data)
                if matches and not st.session_state.selected_category:
                    best_match = matches[0]
                    st.session_state.selected_category = best_match['category']
                    category_objects = st.session_state.markers_data.get(best_match['category'], [])
                    st.session_state.phase2_markers = [obj['name'] for obj in category_objects if obj.get('priority') is not None]
                    st.session_state.custom_category_mode = False
                    print(f"✅ Автоматически выбрана категория: {best_match['category']}")
                elif not matches and not st.session_state.selected_category:
                    st.session_state.selected_category = category_from_phase1
                    st.session_state.custom_category_mode = True
                    print(f"📝 Создана новая категория: {category_from_phase1}")

            st.session_state.phase2_auto_loaded = True

    # === ЗАГРУЗКА СОХРАНЕННЫХ ДАННЫХ ФАЗЫ 2 ИЗ ДОМЕНА (ТОЛЬКО ЕСЛИ НЕТ ДАННЫХ ИЗ ФАЗЫ 1) ===


    # === ЗАГРУЗКА СОХРАНЕННЫХ ДАННЫХ ИЗ APP_STATE ===
    # === ЗАГРУЗКА СОХРАНЕННЫХ ДАННЫХ ФАЗЫ 2 ===
    phase2_loaded = False

    # ========== ПРИОРИТЕТ 1: ИЗ КОНТЕКСТА ==========
    if ctx_data['has_context'] and context is not None:
        saved_phase2 = context.get_phase_data(2)
        if saved_phase2 and isinstance(saved_phase2, dict) and not category_from_phase1:
            if saved_phase2.get('category'):
                st.session_state.selected_category = saved_phase2.get('category', '')
                st.session_state.phase2_markers = saved_phase2.get('markers', [])
                st.session_state.custom_category_mode = saved_phase2.get('custom_category_mode', False)
                if saved_phase2.get('source_category'):
                    st.session_state.search_query = saved_phase2.get('source_category')
                phase2_loaded = True
                print(f"✅ Загружены данные фазы 2 из контекста")

    # ========== ПРИОРИТЕТ 2: ИЗ APP_STATE ==========
    if not phase2_loaded and app_state and 'phase2' in st.session_state.app_data:
        saved_phase2 = st.session_state.app_data['phase2']
        if saved_phase2 and isinstance(saved_phase2, dict) and not category_from_phase1:
            if saved_phase2.get('category'):
                st.session_state.selected_category = saved_phase2.get('category', '')
                st.session_state.phase2_markers = saved_phase2.get('markers', [])
                st.session_state.custom_category_mode = saved_phase2.get('custom_category_mode', False)
                if saved_phase2.get('source_category'):
                    st.session_state.search_query = saved_phase2.get('source_category')
                phase2_loaded = True
                print(f"✅ Загружены данные фазы 2 из app_state")

    # --- БОКОВАЯ ПАНЕЛЬ ---
    with st.sidebar:
        st.header("⚙️ Настройки")

        with st.expander("🔧 Маркеры по умолчанию", expanded=False):
            if st.button("✏️ Редактировать"):
                st.session_state.show_default_markers_editor = not st.session_state.show_default_markers_editor

            if st.session_state.show_default_markers_editor:
                default_markers_text = st.text_area(
                    "Маркеры по умолчанию (каждый с новой строки):",
                    value="\n".join(st.session_state.default_markers),
                    height=150
                )

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾 Сохранить", use_container_width=True):
                        new_default_markers = [m.strip() for m in default_markers_text.split('\n') if m.strip()]
                        st.session_state.default_markers = new_default_markers
                        st.success("Маркеры по умолчанию обновлены!")
                        st.rerun()
                with col2:
                    if st.button("🔄 Сбросить", use_container_width=True):
                        st.session_state.default_markers = ["продукция", "изделие"]
                        st.rerun()

        st.divider()
        st.header("📊 Информация")

        if st.session_state.loaded_data:
            category = st.session_state.loaded_data.get('category', 'Не указана')
            characteristics_count = len(st.session_state.loaded_data.get('characteristics', []))
            st.success(f"✅ Данные из фазы 1 загружены")
            st.write(f"**Категория:** {category}")
            st.write(f"**Характеристик:** {characteristics_count}")
        else:
            st.warning("⚠️ Данные из фазы 1 не загружены")
            st.info("Запустите фазу 1 для автоматической передачи данных")

        st.divider()

        if st.button("🔄 Сбросить выбор категории", use_container_width=True):
            st.session_state.selected_category = ""
            st.session_state.phase2_markers = []
            st.session_state.custom_category_mode = False
            if category_from_phase1:
                st.session_state.search_query = category_from_phase1
            st.rerun()

    # --- ОСНОВНОЙ КОНТЕНТ ---

    # Показываем текущую категорию из фазы 1
    if category_from_phase1:
        st.info(f"📂 **Категория из фазы 1:** {category_from_phase1}")

    # --- ПОИСК КАТЕГОРИИ ---
    if st.session_state.search_query:
        st.subheader(f"🔍 Поиск маркеров для категории: **{st.session_state.search_query}**")

        matches = find_category_matches(st.session_state.search_query, st.session_state.markers_data)

        if matches:
            with st.expander(f"Найдено {len(matches)} совпадение(ий)", expanded=True):
                for i, match in enumerate(matches):
                    match_icon = '✅' if match['match_type'] == 'exact' else '🔍'

                    col1, col2, col3 = st.columns([1, 3, 1])
                    with col1:
                        st.markdown(f"**{match_icon}**")
                    with col2:
                        st.markdown(f"**{match['category']}**")
                        st.caption(f"Маркеров: {len(match['markers'])}")
                    with col3:
                        if st.button("Выбрать", key=f"select_{i}"):
                            st.session_state.selected_category = match['category']
                            st.session_state.custom_category_mode = False
                            category_objects = st.session_state.markers_data.get(match['category'], [])
                            st.session_state.phase2_markers = [obj['name'] for obj in category_objects if obj.get('priority') is not None]
                            st.rerun()

                    if match['markers']:
                        sample_names = [m['name'] for m in match['markers'][:3]]
                        st.markdown(f"*Примеры:* {', '.join(sample_names)}")
                    st.divider()

            st.markdown("<div class='info-box'>", unsafe_allow_html=True)
            st.write("**Не нашли подходящую категорию?**")

            col_new1, col_new2 = st.columns([3, 1])
            with col_new1:
                default_category = st.session_state.search_query if not st.session_state.selected_category else ""
                new_category_name = st.text_input(
                    "Создать новую категорию:",
                    value=default_category,
                    key="new_category_input"
                )
            with col_new2:
                if st.button("Создать", use_container_width=True):
                    if new_category_name:
                        st.session_state.selected_category = new_category_name
                        st.session_state.phase2_markers = []
                        st.session_state.custom_category_mode = True
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        else:
            st.warning("Совпадений не найдено. Создайте новую категорию или попробуйте другой поиск.")

            col_new1, col_new2 = st.columns([3, 1])
            with col_new1:
                default_category = st.session_state.search_query if not st.session_state.selected_category else ""
                new_category_name = st.text_input(
                    "Название новой категории:",
                    value=default_category,
                    key="new_category_input_empty"
                )
            with col_new2:
                if st.button("Создать", use_container_width=True):
                    if new_category_name:
                        st.session_state.selected_category = new_category_name
                        st.session_state.phase2_markers = []
                        st.session_state.custom_category_mode = True
                        st.rerun()

    # --- РЕДАКТИРОВАНИЕ МАРКЕРОВ ДЛЯ ВЫБРАННОЙ КАТЕГОРИИ ---
    if st.session_state.selected_category:
        st.markdown("<div class='markers-container'>", unsafe_allow_html=True)

        col_info1, col_info2, col_info3 = st.columns(3)
        with col_info1:
            original_cat = st.session_state.get('original_category_from_phase1', '')
            if not original_cat and st.session_state.loaded_data:
                original_cat = st.session_state.loaded_data.get('category', '')
            st.info(f"📌 Исходная категория (фаза 1): **{original_cat}**")
        with col_info2:
            st.info(f"🏷️ Категория маркеров: **{st.session_state.selected_category}**")
        with col_info3:
            if st.session_state.custom_category_mode:
                st.warning("⚠️ Новая категория (ещё не сохранена в базу)")
            else:
                st.success("✅ Категория найдена в базе")

        st.markdown("### 📝 Управление маркерами")

        # Получаем объекты текущей категории из базы
        category_objects = st.session_state.markers_data.get(st.session_state.selected_category, [])
        priority_map = {obj['name']: obj.get('priority') for obj in category_objects}

        # Маркеры по умолчанию
        default_markers = get_default_markers()
        default_markers_lower = [m.lower() for m in default_markers]

        # Все имена для отображения
        all_display_names = sorted(
            set(priority_map.keys()) |
            set(st.session_state.phase2_markers) |
            set(default_markers)
        )

        # Разделяем на маркеры по умолчанию и остальные
        default_display = []
        other_display = []
        for name in all_display_names:
            if name.lower() in default_markers_lower:
                default_display.append(name)
            else:
                other_display.append(name)

        def get_priority_sort_key(marker_name):
            priority = priority_map.get(marker_name)
            if priority is None and marker_name in st.session_state.new_markers_priority:
                priority = st.session_state.new_markers_priority[marker_name]

            if priority is not None:
                return (0, -priority if priority else 0, marker_name)
            else:
                return (1, 0, marker_name)

        other_display.sort(key=get_priority_sort_key)

        # Таблица маркеров
        st.markdown("<div class='markers-table-container'>", unsafe_allow_html=True)

        # Маркеры по умолчанию
        if default_display:
            st.markdown("<div class='section-header'>📌 Маркеры по умолчанию</div>", unsafe_allow_html=True)
            for marker_name in sorted(default_display):
                col1, col2 = st.columns([1, 20])
                with col1:
                    is_checked = marker_name in st.session_state.phase2_markers
                    if st.checkbox(" ", value=is_checked, key=f"cb_default_{marker_name}", label_visibility="collapsed"):
                        if marker_name not in st.session_state.phase2_markers:
                            st.session_state.phase2_markers.append(marker_name)
                    else:
                        if marker_name in st.session_state.phase2_markers:
                            st.session_state.phase2_markers.remove(marker_name)
                with col2:
                    st.markdown(
                        f"<div class='marker-name'>{marker_name} <span class='marker-type-badge'>по умолчанию</span></div>",
                        unsafe_allow_html=True
                    )

        # Остальные маркеры
        if other_display:
            st.markdown("<div class='section-header'>🎯 Маркеры категории</div>", unsafe_allow_html=True)

            has_priority_shown = False
            for marker_name in other_display:
                priority = priority_map.get(marker_name)
                if priority is None and marker_name in st.session_state.new_markers_priority:
                    priority = st.session_state.new_markers_priority[marker_name]

                if priority is not None and not has_priority_shown:
                    st.markdown("<div style='margin-top: 10px; font-size: 0.9em; color: #666;'>⭐ С приоритетом:</div>", unsafe_allow_html=True)
                    has_priority_shown = True
                elif priority is None and has_priority_shown:
                    st.markdown("<div style='margin-top: 15px; font-size: 0.9em; color: #666;'>📋 Без приоритета:</div>", unsafe_allow_html=True)
                    has_priority_shown = False

                col1, col2 = st.columns([1, 20])
                with col1:
                    is_checked = marker_name in st.session_state.phase2_markers
                    if st.checkbox(" ", value=is_checked, key=f"cb_other_{marker_name}", label_visibility="collapsed"):
                        if marker_name not in st.session_state.phase2_markers:
                            st.session_state.phase2_markers.append(marker_name)
                    else:
                        if marker_name in st.session_state.phase2_markers:
                            st.session_state.phase2_markers.remove(marker_name)
                with col2:
                    if priority is not None:
                        st.markdown(
                            f"<div class='marker-name'>{marker_name} <span class='marker-type-badge'>приоритет: {priority}</span></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"<div class='marker-name'>{marker_name}</div>",
                            unsafe_allow_html=True
                        )

        if not default_display and not other_display:
            st.info("Нет доступных маркеров. Добавьте новые маркеры.")

        st.markdown("</div>", unsafe_allow_html=True)

        # Статистика
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("Всего маркеров в базе", len(category_objects))
        with col_stat2:
            st.metric("Выбрано", len(st.session_state.phase2_markers))
        with col_stat3:
            new_count = len(set(st.session_state.phase2_markers) - set(priority_map.keys()) - set(default_markers))
            st.metric("Новых (не сохранено)", new_count)

        # Добавление нового маркера
        st.markdown("### ➕ Добавить новый маркер")
        col_name, col_priority, col_no_priority, col_button = st.columns([3, 1, 1, 1])
        with col_name:
            new_marker = st.text_input("Название", key="new_marker_name", placeholder="Введите маркер")
        with col_priority:
            priority_val = st.number_input("Приоритет", min_value=1, step=1, key="new_marker_priority", value=1)
        with col_no_priority:
            no_priority = st.checkbox("Нет приоритета", value=False, key="new_marker_no_priority")
        with col_button:
            if st.button("➕ Добавить", use_container_width=True):
                if new_marker and new_marker not in st.session_state.phase2_markers:
                    st.session_state.phase2_markers.append(new_marker)
                    if not no_priority:
                        st.session_state.new_markers_priority[new_marker] = priority_val
                    st.rerun()

        # Редактор маркеров
        col_edit1, col_edit2 = st.columns([1, 5])
        with col_edit1:
            if st.button("✏️ Редактировать маркеры", type="secondary", use_container_width=True):
                st.session_state.show_marker_editor = not st.session_state.get('show_marker_editor', False)
                st.rerun()

        if st.session_state.get('show_marker_editor', False):
            st.markdown("---")
            st.markdown("### ✏️ Расширенный редактор маркеров")
            st.info("Здесь вы можете редактировать существующие маркеры и их приоритеты")

            existing_markers = st.session_state.markers_data.get(st.session_state.selected_category, [])

            if existing_markers:
                st.markdown("#### Существующие маркеры:")

                for idx, marker in enumerate(existing_markers):
                    col1, col2, col3, col4 = st.columns([3, 2, 1, 1])

                    with col1:
                        new_name = st.text_input(
                            "Название",
                            value=marker['name'],
                            key=f"edit_name_{idx}",
                            label_visibility="collapsed"
                        )

                    with col2:
                        current_priority = marker.get('priority', 0)
                        priority_val = current_priority if current_priority else 0
                        new_priority = st.number_input(
                            "Приоритет",
                            min_value=0,
                            value=priority_val,
                            key=f"edit_priority_{idx}",
                            label_visibility="collapsed"
                        )

                    with col3:
                        if st.button("💾", key=f"save_{idx}", help="Сохранить изменения"):
                            if new_name and new_name != marker['name']:
                                marker['name'] = new_name
                            marker['priority'] = new_priority if new_priority > 0 else None
                            save_markers(st.session_state.markers_data)
                            st.success(f"✓ Маркер обновлен")
                            st.rerun()

                    with col4:
                        if st.button("🗑️", key=f"delete_{idx}", help="Удалить маркер"):
                            st.session_state.markers_data[st.session_state.selected_category] = [
                                m for m in existing_markers if m['name'] != marker['name']
                            ]
                            save_markers(st.session_state.markers_data)
                            st.session_state.phase2_markers = [
                                m for m in st.session_state.phase2_markers if m != marker['name']
                            ]
                            st.success(f"✓ Маркер удален")
                            st.rerun()
            else:
                st.info("Нет маркеров для редактирования")

        st.markdown("</div>", unsafe_allow_html=True)

        # Кнопки сохранения
        st.divider()
        st.markdown("### 💾 Сохранение и переход")

        col_save1, col_save2, col_save3 = st.columns([1, 1, 1])

        with col_save1:
            if st.button("💾 Сохранить маркеры в базу", type="primary", use_container_width=True):
                if st.session_state.selected_category and st.session_state.phase2_markers:
                    existing_objects = st.session_state.markers_data.get(st.session_state.selected_category, [])
                    existing_names = {obj['name'] for obj in existing_objects}
                    new_objects = []
                    new_objects.extend(existing_objects)

                    for marker_name in st.session_state.phase2_markers:
                        if marker_name not in existing_names:
                            priority = st.session_state.new_markers_priority.get(marker_name, None)
                            new_objects.append({"name": marker_name, "priority": priority})

                    st.session_state.markers_data[st.session_state.selected_category] = new_objects
                    if save_markers(st.session_state.markers_data):
                        st.success(f"✅ Маркеры для категории '{st.session_state.selected_category}' сохранены!")
                        st.session_state.new_markers_priority = {}
                        save_to_session_state(app_state, context)
                        st.rerun()
                    else:
                        st.error("❌ Ошибка сохранения маркеров")

        with col_save2:
            if st.button("💾 Сохранить в проект", use_container_width=True):
                if save_to_session_state(app_state, context):
                    st.success("✅ Данные сохранены в проект!")
                    st.rerun()
                else:
                    st.error("❌ Ошибка сохранения")

        # ========== КНОПКА ПЕРЕХОДА К ФАЗЕ 3 ==========
        with col_save3:
            # Проверяем, сохранены ли данные
            phase2_saved = False
            if 'app_data' in st.session_state and 'phase2' in st.session_state.app_data:
                phase2_data = st.session_state.app_data['phase2']
                if phase2_data and phase2_data.get('markers'):
                    phase2_saved = True

            if not phase2_saved and ctx_data['has_context'] and context is not None:
                phase2_data = context.get_phase_data(2)
                if phase2_data and phase2_data.get('markers'):
                    phase2_saved = True

            if phase2_saved:
                if st.button("➡️ Фаза 3", type="primary", use_container_width=True, help="Перейти к фазе 3"):
                    st.session_state.current_phase = 3
                    if app_state:
                        app_state.current_phase = 3
                    st.rerun()
            else:
                st.button("➡️ Фаза 3", disabled=True, use_container_width=True, help="Сначала сохраните данные")

        # Предпросмотр
        with st.expander("👁️ Предпросмотр данных для фазы 3"):
            original_category = st.session_state.get('original_category_from_phase1', '')
            if not original_category and st.session_state.loaded_data:
                original_category = st.session_state.loaded_data.get('category', '')

            phase3_data = {
                "category": original_category,
                "selected_marker_category": st.session_state.selected_category,
                "markers": st.session_state.phase2_markers,
                "characteristics": st.session_state.loaded_data.get('characteristics', []) if st.session_state.loaded_data else []
            }
            st.json(phase3_data)

    else:
        if not st.session_state.loaded_data:
            st.info("""
            ## 👋 Добро пожаловать в фазу 2!
            
            Чтобы начать работу:
            
            1. **Запустите фазу 1** и обработайте данные
            2. **Категория автоматически передастся** в фазу 2
            3. **Найдите или создайте** категорию для работы с маркерами
            """)

            manual_search = st.text_input(
                "Введите название категории для поиска:",
                placeholder="Например: Абразивные материалы",
                key="manual_search_input"
            )

            if manual_search:
                st.session_state.search_query = manual_search
                st.rerun()
        else:
            st.info("🔍 Введите название категории в поле поиска выше или используйте категорию из фазы 1")


if __name__ == "__main__":
    main()