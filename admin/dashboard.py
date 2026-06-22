# admin/dashboard.py
import streamlit as st
from datetime import datetime, timedelta
from database_settings.database import get_db
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")

def render_admin_dashboard():
    """Главная страница админ-панели со статистикой"""

    st.title("👑 Панель администратора")
    st.markdown("---")

    # Статистика в карточках
    col1, col2, col3, col4 = st.columns(4)

    with get_db() as conn:
        # Всего пользователей
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        col1.metric("👥 Всего пользователей", total_users)

        # Активных пользователей (заходили за последние 7 дней)
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        active_users = conn.execute("""
            SELECT COUNT(DISTINCT user_id) FROM user_sessions 
            WHERE created_at > ?
        """, (week_ago,)).fetchone()[0]
        col2.metric("🟢 Активных за неделю", active_users)

        # Всего проектов
        # Нужно посчитать все JSON файлы в папках projects
        import json
        from pathlib import Path

        total_projects = 0
        sites_dir = Path("sites")
        if sites_dir.exists():
            for project_file in sites_dir.rglob("projects/*/*.json"):
                if project_file.name != "queue_state.json":
                    total_projects += 1
        col3.metric("📁 Всего проектов", total_projects)

        # Запросов API за сегодня
        today = datetime.now().date().isoformat()
        api_today = conn.execute("""
            SELECT COUNT(*) FROM api_usage_logs 
            WHERE date(created_at) = date('now')
        """).fetchone()[0]
        col4.metric("📡 API запросов сегодня", api_today)

    st.markdown("---")

    # Графики
    tab1, tab2, tab3 = st.tabs(["📊 Статистика API", "👥 Пользователи", "📁 Проекты"])

    with tab1:
        st.subheader("Использование API по дням")

        with get_db() as conn:
            # Последние 30 дней
            daily_stats = conn.execute("""
                SELECT 
                    date(l.created_at) as date,
                    COUNT(*) as requests,
                    SUM(l.total_tokens) as tokens,
                    SUM(CASE WHEN l.success = 1 THEN 1 ELSE 0 END) as successful,
                    l.provider
                FROM api_usage_logs l
                WHERE l.created_at > date('now', '-30 days')
                GROUP BY date(l.created_at), l.provider
                ORDER BY date DESC
            """).fetchall()
        if daily_stats:
            # Простая таблица с данными
            stats_data = []
            for row in daily_stats:
                stats_data.append({
                    "Дата": row["date"],
                    "Провайдер": row["provider"],
                    "Запросов": row["requests"],
                    "Токенов": row["tokens"],
                    "Успешных": row["successful"]
                })
            st.dataframe(stats_data, use_container_width=True)
        else:
            st.info("Нет данных об использовании API")

        st.markdown("---")

        # Топ пользователей по использованию
        st.subheader("Топ пользователей по токенам")
        with get_db() as conn:
            top_users = conn.execute("""
                SELECT 
                    u.username,
                    COUNT(l.id) as requests,
                    SUM(l.total_tokens) as total_tokens,
                    SUM(l.estimated_cost) as total_cost
                FROM api_usage_logs l
                JOIN users u ON l.user_id = u.id
                GROUP BY l.user_id
                ORDER BY total_tokens DESC
                LIMIT 10
            """).fetchall()

        if top_users:
            for i, user in enumerate(top_users, 1):
                st.write(f"{i}. **{user['username']}** - {user['requests']} запросов, {user['total_tokens']:,} токенов")
        else:
            st.info("Нет данных")

    with tab2:
        st.subheader("Новые пользователи по дням")
        with get_db() as conn:
            new_users = conn.execute("""
                SELECT date(created_at) as date, COUNT(*) as count
                FROM users 
                WHERE created_at > date('now', '-30 days')
                GROUP BY date(created_at)
                ORDER BY date DESC
            """).fetchall()

        if new_users:
            st.dataframe(new_users, use_container_width=True)
        else:
            st.info("Нет данных")

    with tab3:
        st.subheader("Проекты по доменам")

        from pathlib import Path

        sites_dir = Path("sites")
        domain_stats = []

        if sites_dir.exists():
            for site_dir in sites_dir.iterdir():
                if not site_dir.is_dir():
                    continue

                domains_dir = site_dir / "domains"
                if not domains_dir.exists():
                    continue

                for domain_dir in domains_dir.iterdir():
                    if not domain_dir.is_dir():
                        continue

                    projects_dir = domain_dir / "projects"
                    project_count = 0

                    if projects_dir.exists():
                        for user_dir in projects_dir.iterdir():
                            if user_dir.is_dir():
                                project_count += len(list(user_dir.glob("*.json")))

                    domain_stats.append({
                        "Сайт": site_dir.name,
                        "Домен": domain_dir.name,
                        "Проектов": project_count
                    })

        if domain_stats:
            st.dataframe(domain_stats, use_container_width=True)
        else:
            st.info("Нет данных")

    st.markdown("---")

    # Быстрые действия
    '''st.subheader("⚡ Быстрые действия")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("👥 Управление пользователями", use_container_width=True):
            st.session_state.admin_tab = "users"
            st.rerun()

    with col2:
        if st.button("🔑 Управление API ключами", use_container_width=True):
            st.session_state.admin_tab = "api_keys"
            st.rerun()

    with col3:
        if st.button("📁 Все проекты", use_container_width=True):
            st.session_state.admin_tab = "projects"
            st.rerun()

    with col4:
        if st.button("📊 Статистика API", use_container_width=True):
            st.session_state.admin_tab = "stats"
            st.rerun()'''