# admin/users_manager.py
import streamlit as st
from database_settings.database import get_db
from domain_permissions import DomainPermissionManager
from admin.audit_viewer import log_admin_action
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")

def render_users_manager():
    """Управление пользователями и их правами на домены"""

    st.subheader("👥 Управление пользователями")
    st.markdown("---")

    tab_users, tab_permissions = st.tabs(["👤 Пользователи", "🔐 Права на домены"])

    with tab_users:
        with get_db() as conn:
            users = conn.execute("""
                SELECT id, username, email, status, is_admin, totp_enabled, banned, 
                       failed_attempts, created_at
                FROM users 
                ORDER BY created_at DESC
            """).fetchall()

        if not users:
            st.info("Нет пользователей")
            return

        for user in users:
            with st.expander(f"👤 {user['username']} ({user['email']})"):
                col1, col2 = st.columns(2)

                with col1:
                    st.write(f"**ID:** {user['id']}")
                    st.write(f"**Статус:** {user['status']}")
                    st.write(f"**Админ:** {'✅' if user['is_admin'] else '❌'}")
                    st.write(f"**2FA:** {'✅' if user['totp_enabled'] else '❌'}")
                    st.write(f"**Бан:** {'✅' if user['banned'] else '❌'}")
                    st.write(f"**Попыток входа:** {user['failed_attempts']}")
                    st.write(f"**Зарегистрирован:** {user['created_at']}")

                with col2:
                    # Действия
                    if user["banned"]:
                        if st.button("🔓 Разблокировать", key=f"unban_{user['id']}"):
                            conn.execute("UPDATE users SET banned = 0 WHERE id = ?", (user['id'],))
                            conn.commit()
                            log_admin_action(
                                st.session_state.user_id, "unban_user", "user",
                                str(user['id']), f"Разблокирован пользователь {user['username']}"
                            )
                            st.success(f"✅ Пользователь {user['username']} разблокирован")
                            st.rerun()
                    else:
                        if st.button("🔒 Заблокировать", key=f"ban_{user['id']}"):
                            if user['id'] == st.session_state.user_id:
                                st.error("Нельзя заблокировать самого себя")
                            else:
                                conn.execute("UPDATE users SET banned = 1 WHERE id = ?", (user['id'],))
                                conn.commit()
                                log_admin_action(
                                    st.session_state.user_id, "ban_user", "user",
                                    str(user['id']), f"Заблокирован пользователь {user['username']}"
                                )
                                st.success(f"✅ Пользователь {user['username']} заблокирован")
                                st.rerun()

                    if user["is_admin"]:
                        if st.button("👤 Снять права админа", key=f"deadmin_{user['id']}"):
                            if user['id'] == st.session_state.user_id:
                                st.error("Нельзя снять админа с самого себя")
                            else:
                                conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user['id'],))
                                conn.commit()
                                log_admin_action(
                                    st.session_state.user_id, "remove_admin", "user",
                                    str(user['id']), f"Сняты права админа с {user['username']}"
                                )
                                st.success(f"✅ Пользователь {user['username']} больше не админ")
                                st.rerun()
                    else:
                        if st.button("👑 Назначить админом", key=f"make_admin_{user['id']}"):
                            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user['id'],))
                            conn.commit()
                            log_admin_action(
                                st.session_state.user_id, "make_admin", "user",
                                str(user['id']), f"Назначен админом {user['username']}"
                            )
                            st.success(f"✅ Пользователь {user['username']} теперь администратор")
                            st.rerun()

                    if st.button("❌ Удалить пользователя", key=f"delete_user_{user['id']}"):
                        if user['id'] == st.session_state.user_id:
                            st.error("Нельзя удалить самого себя")
                        else:
                            # Удаляем все связанные данные
                            conn.execute("DELETE FROM user_sessions WHERE user_id = ?", (user['id'],))
                            conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user['id'],))
                            conn.execute("DELETE FROM user_domain_permissions WHERE user_id = ?", (user['id'],))
                            conn.execute("DELETE FROM api_usage_logs WHERE user_id = ?", (user['id'],))
                            conn.execute("DELETE FROM users WHERE id = ?", (user['id'],))
                            conn.commit()

                            # Удаляем проекты пользователя из файловой системы
                            from pathlib import Path
                            sites_dir = Path("sites")
                            if sites_dir.exists():
                                for site_dir in sites_dir.iterdir():
                                    if site_dir.is_dir():
                                        domains_dir = site_dir / "domains"
                                        if domains_dir.exists():
                                            for domain_dir in domains_dir.iterdir():
                                                if domain_dir.is_dir():
                                                    projects_dir = domain_dir / "projects" / str(user['id'])
                                                    if projects_dir.exists():
                                                        import shutil
                                                        shutil.rmtree(projects_dir)

                            log_admin_action(
                                st.session_state.user_id, "delete_user", "user",
                                str(user['id']), f"Удален пользователь {user['username']}"
                            )
                            st.success(f"✅ Пользователь {user['username']} удален")
                            st.rerun()

    with tab_permissions:
        st.subheader("🔐 Выдача прав на домены")

        # Выбор пользователя
        with get_db() as conn:
            users = conn.execute("SELECT id, username FROM users WHERE status = 'approved' ORDER BY username").fetchall()
            user_options = {f"{u['username']} (ID: {u['id']})": u['id'] for u in users}
            selected_user = st.selectbox("Пользователь", list(user_options.keys()))
            user_id = user_options[selected_user]

        # Выбор сайта и домена
        from site_manager import SiteManager
        sm = SiteManager()
        sites = sm.get_available_sites()

        if not sites:
            st.warning("Нет доступных сайтов")
            return

        col1, col2 = st.columns(2)
        with col1:
            site_name = st.selectbox("Сайт", sites)

        from domain_manager import DomainManager
        dm = DomainManager(site_name)
        domains = dm.get_available_domains()

        with col2:
            domain_name = st.selectbox("Домен", domains)

        # Текущие права
        perm_manager = DomainPermissionManager()
        has_access = perm_manager.can_access(user_id, site_name, domain_name)

        if has_access:
            st.info(f"✅ Пользователь уже имеет доступ к {site_name}/{domain_name}")

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("✏️ Изменить права", use_container_width=True):
                    st.session_state.show_permission_edit = True

            with col_b:
                if st.button("🔒 Отозвать доступ", use_container_width=True):
                    if perm_manager.revoke_access(user_id, site_name, domain_name):
                        log_admin_action(
                            st.session_state.user_id, "revoke_access", "domain",
                            f"{site_name}/{domain_name}", f"Отозван доступ у пользователя ID:{user_id}"
                        )
                        st.success("✅ Доступ отозван")
                        st.rerun()

        # Форма выдачи/изменения прав
        if not has_access or st.session_state.get("show_permission_edit", False):
            with st.form("grant_permissions_form"):
                st.write(f"**Выдача прав для:** {site_name}/{domain_name}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    can_read = st.checkbox("Чтение", value=True)
                with col2:
                    can_write = st.checkbox("Запись", value=True)
                with col3:
                    can_delete = st.checkbox("Удаление", value=False)

                if st.form_submit_button("💾 Сохранить права"):
                    if perm_manager.grant_access(
                            st.session_state.user_id, user_id, site_name, domain_name,
                            can_read, can_write, can_delete
                    ):
                        log_admin_action(
                            st.session_state.user_id, "grant_access", "domain",
                            f"{site_name}/{domain_name}",
                            f"Выданы права пользователю ID:{user_id} (read:{can_read}, write:{can_write}, delete:{can_delete})"
                        )
                        st.success("✅ Права сохранены")
                        st.session_state.pop("show_permission_edit", None)
                        st.rerun()

        st.markdown("---")

        # Список пользователей с доступом к домену
        st.subheader("Пользователи с доступом")

        users_with_access = perm_manager.get_users_with_access(site_name, domain_name)

        if users_with_access:
            for u in users_with_access:
                st.write(f"**{u['username']}** - Чтение: {'✅' if u['can_read'] else '❌'}, "
                         f"Запись: {'✅' if u['can_write'] else '❌'}, "
                         f"Удаление: {'✅' if u['can_delete'] else '❌'}")
        else:
            st.info("Нет пользователей с доступом")