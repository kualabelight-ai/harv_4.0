# admin_queues.py
import streamlit as st
from user_queue_manager import GlobalQueueManager
from database_settings.database import get_db
from domain_manager import DomainManager


def render_queues_admin_panel():
    """Панель администратора для просмотра всех очередей"""
    st.subheader("📊 Управление очередями пользователей")

    # ✅ ЗАГРУЖАЕМ ТЕКУЩИЙ ДОМЕН АДМИНИСТРАТОРА
    try:
        if 'domain_manager' not in st.session_state:
            st.session_state.domain_manager = DomainManager()

        dm = st.session_state.domain_manager
        user_id = st.session_state.get('user_id')

        if user_id:
            settings = dm.load_user_settings(user_id)
            saved_domain = settings.get('selected_domain', 'default')
            saved_site = settings.get('selected_site', 'steelborg')

            st.session_state.current_domain = saved_domain
            st.session_state.selected_domain = saved_domain
            st.session_state.current_site = saved_site
            st.session_state.selected_site = saved_site

            print(f"✅ admin_queues загружен домен: {saved_domain}")
    except Exception as e:
        print(f"⚠️ admin_queues: ошибка загрузки домена: {e}")

    queues_info = GlobalQueueManager.get_all_queues_info()

    if not queues_info:
        st.info("Нет активных очередей")
        return

    # Получаем имена пользователей
    with get_db() as conn:
        users = {}
        for user_id in queues_info.keys():
            user = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
            if user:
                users[user_id] = user['username']

    # Таблица со всеми очередями
    data = []
    for user_id, info in queues_info.items():
        data.append({
            "ID": user_id,
            "Пользователь": users.get(user_id, "Неизвестен"),
            "Всего": info['total_projects'],
            "В очереди": info['queued'],
            "Выполняется": info['running'],
            "Завершено": info['completed'],
            "Ошибок": info['failed']
        })

    st.dataframe(data, use_container_width=True)

    # Детальный просмотр
    st.markdown("---")
    st.subheader("🔍 Детальный просмотр")

    if users:
        selected_user_id = st.selectbox(
            "Выберите пользователя",
            options=list(users.keys()),
            format_func=lambda x: f"{users.get(x, 'Неизвестен')} (ID: {x})"
        )

        if selected_user_id:
            queue = GlobalQueueManager.get_queue(selected_user_id)

            if queue.projects:
                for pid, task in queue.projects.items():
                    with st.expander(f"{task.project_name} ({task.status.value})"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**ID:** {pid}")
                            st.write(f"**Категория:** {task.category}")
                            st.write(f"**Фаза:** {task.current_phase}")
                            # ✅ ПОКАЗЫВАЕМ ДОМЕН
                            st.write(f"**Сайт:** {task.site_name}")
                            st.write(f"**Домен:** {task.domain_name}")
                        with col2:
                            st.write(f"**Прогресс:** {task.progress}%")
                            st.write(f"**Сообщение:** {task.message}")
                            if task.error:
                                st.error(f"**Ошибка:** {task.error[:200]}")

                        if task.status.value in ['queued', 'running']:
                            if st.button(f"❌ Отменить", key=f"cancel_{pid}"):
                                queue.remove_project(pid)
                                st.rerun()
            else:
                st.info("Нет проектов в очереди")