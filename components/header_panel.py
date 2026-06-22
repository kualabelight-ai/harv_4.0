# components/header_panel.py
import streamlit as st
from datetime import datetime

def render_header_panel(app_state=None, mode="full"):
    """
    Рендерит верхнюю панель с кнопками управления

    Args:
        app_state: объект AppState для сохранения проекта
        mode: режим отображения ("full" - полная панель, "simple" - только профиль/выход)
    """

    has_project = st.session_state.get('current_project_id') is not None

    # ========== SIMPLE MODE - только профиль и выход (для главной страницы) ==========
    if mode == "simple":
        col1, col2, col3, col4, col5 = st.columns([4, 1, 1, 1, 1])

        with col1:
            st.markdown("### 📀 Data Harvester Pro")
            st.caption("Система генерации SEO-контента")

        with col3:
            if st.button("👤 Профиль", use_container_width=True, key="simple_profile"):
                st.session_state.show_profile = True
                st.rerun()

        with col4:
            if st.button("🚪 Выйти", use_container_width=True, key="simple_logout"):
                from database_settings import auth
                if app_state and has_project:
                    app_state.save_project()
                st.session_state.app_mode = None
                st.session_state.module_selected = False
                st.session_state.selected_module = None
                st.session_state.selected_site = None
                st.session_state.selected_domain = None
                st.session_state.current_project_id = None
                auth.logout()
                st.rerun()

        st.markdown("---")
        return

    # ========== FULL MODE - полная панель для модуля Тексты ==========
    if mode == "full":
        # 6 колонок для кнопок (без дублирования)
        col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 1])

        with col1:
            if has_project:
                project_name = st.session_state.app_data.get('project_name', 'Новый проект')
                category = st.session_state.app_data.get('category', 'Без категории')
                current_phase = st.session_state.current_phase
                st.markdown(f"### {project_name}")
                st.caption(f"📂 {category} | Фаза {current_phase}/7")
            else:
                st.markdown("### 📁 Нет активного проекта")
                st.caption("Создайте или выберите проект")

        with col2:
            if st.button("📁 Сменить проект", use_container_width=True, key="full_change_project"):
                st.session_state.show_project_selector = True
                if app_state and has_project:
                    app_state.save_project()
                st.rerun()

        with col3:
            if st.button("💾 Сохранить", use_container_width=True, key="full_save"):
                if app_state and has_project:
                    app_state.save_project()
                    st.success("✅ Проект сохранен")
                else:
                    st.warning("Нет активного проекта")

        with col4:
            if st.button("📊 Очереди", use_container_width=True, key="full_queue"):
                st.session_state.show_queue_panel = not st.session_state.show_queue_panel
                st.rerun()

        with col5:
            if st.button("🤖 AI", use_container_width=True, key="full_ai"):
                st.session_state.show_ai_config = True
                st.rerun()

        with col6:
            if st.button("👤 Профиль", use_container_width=True, key="full_profile"):
                st.session_state.show_profile = True
                st.rerun()

        st.markdown("---")
        return


def render_modal_overlays():
    """Рендерит модальные окна (профиль, AI, очередь)"""

    # Профиль
    if st.session_state.get("show_profile", False):
        from database_settings import auth
        auth.profile_page()
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("← Назад", key="profile_back", use_container_width=True):
                st.session_state.show_profile = False
                st.rerun()
        return True

    # AI настройки
    if st.session_state.get("show_ai_config", False):
        st.title("🤖 Настройки AI")
        try:
            from ai_settings.ai_config import show_ai_config_interface
            show_ai_config_interface()
        except Exception as e:
            st.error(f"Ошибка загрузки настроек AI: {e}")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("← Назад", key="ai_back", use_container_width=True):
                st.session_state.show_ai_config = False
                st.rerun()
        return True

    # Панель очередей
    if st.session_state.get("show_queue_panel", False):
        st.markdown("## 📋 Очереди задач")
        st.info("ℹ️ Информация о выполнении проектов в фоне")

        manager = st.session_state.get('project_queue_manager')
        if manager:
            queue_status = manager.get_queue_status() if hasattr(manager, 'get_queue_status') else {}
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Всего проектов", queue_status.get('total_projects', 0))
            with col2:
                st.metric("В очереди", queue_status.get('queue_size', 0))
            with col3:
                st.metric("Активных", queue_status.get('active_workers', 0))
            with col4:
                st.metric("Завершено", queue_status.get('completed_count', 0))

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("← Закрыть", key="queue_close", use_container_width=True):
                st.session_state.show_queue_panel = False
                st.rerun()
        st.markdown("---")
        return True

    return False


def render_project_selector_embedded(app_state):
    """Встроенный селектор проектов (для отображения внутри вкладки)"""
    st.markdown("### 📁 Мои проекты")

    from project_manager import ProjectManager

    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    current_site = dm.site_name
    current_domain = dm.get_current_domain()

    pm = ProjectManager(
        user_id=st.session_state.user_id,
        site_name=current_site,
        domain_name=current_domain
    )
    projects = pm.get_all_projects()

    # Кнопка создания нового проекта
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("#### Доступные проекты")
    with col2:
        if st.button("➕ Новый проект", use_container_width=True, type="primary", key="new_project_embedded"):
            st.session_state.show_new_project_form = True

    # Форма создания нового проекта
    if st.session_state.get('show_new_project_form', False):
        with st.form(key="new_project_form_embedded"):
            new_category = st.text_input("Название категории / проекта", key="new_category_embedded")
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("Создать", key="create_embedded_btn"):
                    if new_category and new_category.strip():
                        app_state.create_new_project(new_category.strip())
                        st.session_state.show_new_project_form = False
                        st.rerun()
            with col2:
                if st.form_submit_button("Отмена", key="cancel_embedded_btn"):
                    st.session_state.show_new_project_form = False
                    st.rerun()

    st.markdown("---")

    if not projects:
        st.info(f"📭 У вас пока нет сохраненных проектов для сайта '{current_site}' и домена '{current_domain}'")
        return

    # Фильтры
    col1, col2, col3 = st.columns(3)
    with col1:
        search_query = st.text_input("🔍 Поиск", placeholder="Название или категория...", key="search_embedded")
    with col2:
        filter_phase = st.selectbox("Фильтр по фазе",
                                    ["Все", "Фаза 1", "Фаза 2", "Фаза 3", "Фаза 4", "Фаза 5", "Фаза 6", "Фаза 7", "Завершены"],
                                    key="filter_embedded")
    with col3:
        sort_by = st.selectbox("Сортировка", ["По дате изменения", "По названию", "По категории"], key="sort_embedded")

    # Фильтрация
    filtered_projects = projects.copy()
    if search_query:
        filtered_projects = [p for p in filtered_projects
                             if search_query.lower() in p['project_name'].lower()
                             or search_query.lower() in p['category'].lower()]

    if filter_phase != "Все":
        if filter_phase == "Завершены":
            filtered_projects = [p for p in filtered_projects if p['current_phase'] == 7]
        else:
            phase_num = int(filter_phase.split()[1])
            filtered_projects = [p for p in filtered_projects if p['current_phase'] == phase_num]

    # Сортировка
    if sort_by == "По названию":
        filtered_projects.sort(key=lambda x: x['project_name'])
    elif sort_by == "По категории":
        filtered_projects.sort(key=lambda x: x['category'])
    else:
        filtered_projects.sort(key=lambda x: x.get('updated_at', ''), reverse=True)

    # Отображение проектов
    for project in filtered_projects:
        with st.container():
            col1, col2, col3, col4 = st.columns([4, 2, 1.5, 1.5])
            with col1:
                phase_icons = {1: "📦", 2: "🏷️", 3: "📝", 4: "🚀", 5: "📄", 6: "🔄", 7: "📊"}
                icon = phase_icons.get(project['current_phase'], "📁")
                st.markdown(f"**{icon} {project['project_name']}**")
                st.caption(f"📂 {project['category']}")
            with col2:
                progress = project['current_phase'] / 7
                st.progress(progress, text=f"Фаза {project['current_phase']}/7")
            with col3:
                if project.get('updated_at'):
                    updated = datetime.fromisoformat(project['updated_at']).strftime("%d.%m.%Y")
                    st.caption(f"📅 {updated}")
            with col4:
                if st.button("Открыть", key=f"open_emb_{project['project_id']}", type="primary"):
                    if app_state.load_project(project['project_id']):
                        if 'domain_manager' in st.session_state:
                            dm = st.session_state.domain_manager
                            proj_domain = project.get('domain_name', 'default')
                            dm.set_current_domain(proj_domain)
                        st.session_state.show_project_selector = False
                        st.success(f"✅ Проект '{project['project_name']}' загружен")
                        st.rerun()
            st.divider()

    # Статистика
    with st.expander("📊 Статистика", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего проектов", len(projects))
        with col2:
            completed = len([p for p in projects if p['current_phase'] == 7])
            st.metric("Завершенных", completed)
        with col3:
            active = len([p for p in projects if 1 <= p['current_phase'] < 7])
            st.metric("В работе", active)
        with col4:
            total_phases = sum(p['current_phase'] for p in projects)
            avg_phase = total_phases / len(projects) if projects else 0
            st.metric("Средняя фаза", f"{avg_phase:.1f}")


def reset_to_main_menu():
    """Сброс к выбору модуля"""
    st.session_state.app_mode = None
    st.session_state.module_selected = False
    st.session_state.selected_module = None
    st.session_state.selected_site = None
    st.session_state.selected_domain = None
    st.session_state.current_project_id = None
    st.session_state.show_project_selector = False
    st.session_state.show_project_settings = False
    st.session_state.view_mode = 'settings'
    st.session_state.show_queue_panel = False
    st.session_state.show_profile = False
    st.session_state.show_ai_config = False
    st.session_state.show_new_project_form = False

    # Очищаем кэшированные данные
    for key in ['auto_domain_loaded', 'domain_data_loaded', 'phase7_data_loaded']:
        if key in st.session_state:
            del st.session_state[key]