# admin/audit_viewer.py - ИСПРАВИТЬ SQL запросы

import streamlit as st
from database_settings.database import get_db
from datetime import datetime
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")

def log_admin_action(admin_id: int, action: str, target_type: str = None,
                     target_id: str = None, details: str = None, ip: str = None):
    """Логирует действие администратора"""
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO admin_audit_log (admin_id, action, target_type, target_id, details, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (admin_id, action, target_type, target_id, details, ip))
            conn.commit()
    except Exception as e:
        print(f"Ошибка логирования: {e}")


def render_audit_viewer():
    """Просмотр логов действий администраторов"""

    st.subheader("📋 Лог действий администраторов")
    st.markdown("---")

    # Фильтры
    col1, col2, col3 = st.columns(3)

    with col1:
        # Получаем список админов
        with get_db() as conn:
            admins = conn.execute("SELECT id, username FROM users WHERE is_admin = 1").fetchall()
            admin_options = {f"{a['username']} (ID: {a['id']})": a['id'] for a in admins}
            filter_admin = st.selectbox("Администратор", ["Все"] + list(admin_options.keys()), key="audit_filter_admin")

    with col2:
        actions = ["Все", "create_api_key", "delete_api_key", "grant_access", "revoke_access",
                   "ban_user", "unban_user", "make_admin", "remove_admin", "delete_user"]
        filter_action = st.selectbox("Действие", actions, key="audit_filter_action")

    with col3:
        days = st.selectbox("За последние N дней", [1, 7, 30, 90, "Все"], key="audit_filter_days")

    # Формируем запрос
    query = """
        SELECT a.*, u.username as admin_name
        FROM admin_audit_log a
        JOIN users u ON a.admin_id = u.id
        WHERE 1=1
    """
    params = []

    if filter_admin != "Все":
        admin_id = admin_options[filter_admin]
        query += " AND a.admin_id = ?"
        params.append(admin_id)

    if filter_action != "Все":
        query += " AND a.action = ?"
        params.append(filter_action)

    if days != "Все":
        query += " AND a.created_at > datetime('now', ?)"
        params.append(f"-{days} days")

    query += " ORDER BY a.created_at DESC LIMIT 500"

    with get_db() as conn:
        logs = conn.execute(query, params).fetchall()

    if not logs:
        st.info("Нет записей в логе")
        return

    # Отображаем логи
    for idx, log in enumerate(logs):
        unique_key = f"audit_log_{log['id']}_{idx}"
        with st.expander(f"📝 {log['created_at'][:19]} - {log['admin_name']} - {log['action']}", expanded=False):
            st.write(f"**Действие:** {log['action']}")
            if log['target_type']:
                st.write(f"**Тип цели:** {log['target_type']}")
            if log['target_id']:
                st.write(f"**ID цели:** {log['target_id']}")
            if log['details']:
                st.write(f"**Детали:** {log['details']}")
            if log['ip_address']:
                st.write(f"**IP:** {log['ip_address']}")
            st.write(f"**Время:** {log['created_at']}")