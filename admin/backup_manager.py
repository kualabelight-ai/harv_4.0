# admin/backup_manager.py

import streamlit as st
import zipfile
import os
import shutil
from pathlib import Path
import json
from datetime import datetime
import tempfile
import uuid

# -------------------------------------------
# Вспомогательные функции
# -------------------------------------------

def get_available_sites():
    """Возвращает список сайтов (папки в sites/)"""
    sites_dir = Path("sites")
    if not sites_dir.exists():
        return []
    return [d.name for d in sites_dir.iterdir() if d.is_dir()]

def get_available_domains(site_name):
    """Возвращает список доменов для указанного сайта"""
    domains_dir = Path(f"sites/{site_name}/domains")
    if not domains_dir.exists():
        return []
    return [d.name for d in domains_dir.iterdir() if d.is_dir()]

def get_users_for_site_domain(site_name, domain_name):
    """Возвращает список user_id для указанного сайта и домена"""
    projects_dir = Path(f"sites/{site_name}/domains/{domain_name}/projects")
    if not projects_dir.exists():
        return []
    users = []
    for user_dir in projects_dir.iterdir():
        if user_dir.is_dir():
            try:
                user_id = int(user_dir.name)
                users.append(user_id)
            except ValueError:
                continue
    return sorted(users)

def get_user_info(user_id):
    try:
        from database_settings.database import get_db
        with get_db() as conn:
            user = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
            return user["username"] if user else f"user_{user_id}"
    except:
        return f"user_{user_id}"

def get_user_projects(user_id, site_name=None, domain_name=None):
    """
    Возвращает список проектов пользователя.
    Если site_name и domain_name не указаны - ищет по всем сайтам и доменам.
    """
    projects = []
    sites_dir = Path("sites")
    if not sites_dir.exists():
        return projects

    if site_name and domain_name:
        user_dir = Path(f"sites/{site_name}/domains/{domain_name}/projects/{user_id}")
        if user_dir.exists():
            projects.append({
                'site': site_name,
                'domain': domain_name,
                'path': user_dir
            })
        return projects

    for site in sites_dir.iterdir():
        if not site.is_dir():
            continue
        domains_dir = site / "domains"
        if not domains_dir.exists():
            continue
        for domain in domains_dir.iterdir():
            if not domain.is_dir():
                continue
            user_dir = domain / "projects" / str(user_id)
            if user_dir.exists():
                projects.append({
                    'site': site.name,
                    'domain': domain.name,
                    'path': user_dir
                })
    return projects

def create_backup_zip_for_users(site_name, domain_name, selected_users=None, include_all=False, user_id=None):
    """Создаёт ZIP-архив с проектами для указанных пользователей."""
    if user_id:
        user_dir = Path(f"sites/{site_name}/domains/{domain_name}/projects/{user_id}")
        if not user_dir.exists():
            return None
        users = [user_id]
    elif include_all:
        users = get_users_for_site_domain(site_name, domain_name)
    elif selected_users:
        users = selected_users
    else:
        return None

    if not users:
        return None

    base_path = Path(f"sites/{site_name}/domains/{domain_name}/projects")
    if not base_path.exists():
        return None

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        zip_path = tmp.name

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for uid in users:
            user_dir = base_path / str(uid)
            if not user_dir.exists():
                continue
            for item in user_dir.rglob("*"):
                if item.is_file():
                    arcname = str(item.relative_to(Path(".")))
                    zipf.write(item, arcname)

    with open(zip_path, 'rb') as f:
        zip_data = f.read()
    os.unlink(zip_path)
    return zip_data

def delete_projects_for_users(site_name, domain_name, selected_users=None, include_all=False,
                              backup_before_delete=True, user_id=None):
    """Удаляет папки пользователей с созданием бэкапа."""
    if user_id:
        user_dir = Path(f"sites/{site_name}/domains/{domain_name}/projects/{user_id}")
        if not user_dir.exists():
            return False, "У вас нет проектов в этом домене", 0
        users = [user_id]
    elif include_all:
        users = get_users_for_site_domain(site_name, domain_name)
    elif selected_users:
        users = selected_users
    else:
        return False, "Нет пользователей для удаления", 0

    if not users:
        return False, "Нет пользователей с проектами в этом домене", 0

    base_path = Path(f"sites/{site_name}/domains/{domain_name}/projects")
    if not base_path.exists():
        return False, f"Папка {base_path} не найдена", 0

    # Создаём бэкап перед удалением
    if backup_before_delete:
        try:
            zip_data = create_backup_zip_for_users(
                site_name, domain_name,
                selected_users=users if not user_id else None,
                include_all=False if user_id else include_all,
                user_id=user_id
            )
            if zip_data:
                backup_dir = Path("backups")
                backup_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prefix = f"user_{user_id}" if user_id else "projects"
                backup_file = backup_dir / f"{prefix}_backup_{site_name}_{domain_name}_{timestamp}.zip"
                with open(backup_file, 'wb') as f:
                    f.write(zip_data)
                st.info(f"📦 Бэкап сохранён: {backup_file}")
        except Exception as e:
            st.error(f"Ошибка при создании бэкапа: {e}")
            return False, f"Ошибка при создании бэкапа: {e}", 0

    deleted_count = 0
    for uid in users:
        user_dir = base_path / str(uid)
        if user_dir.exists():
            try:
                shutil.rmtree(user_dir)
                deleted_count += 1
            except Exception as e:
                st.warning(f"Не удалось удалить папку {user_dir}: {e}")

    return True, f"Удалено {deleted_count} папок пользователей.", deleted_count

# -------------------------------------------
# Основной интерфейс
# -------------------------------------------

def render_backup_manager():
    """Рендерит менеджер бэкапов в зависимости от прав пользователя"""
    from database_settings.database import is_admin

    user_id = st.session_state.get("user_id")
    is_admin_user = is_admin(user_id) if user_id else False

    if is_admin_user:
        render_admin_backup_manager()
    else:
        render_user_backup_manager()

def render_admin_backup_manager():
    """Полный интерфейс для администратора"""
    st.subheader("💾 Бэкапы и очистка проектов (Админ-режим)")
    st.markdown("---")

    # Используем фиксированный ID для всей сессии
    if "admin_backup_uid" not in st.session_state:
        st.session_state.admin_backup_uid = uuid.uuid4().hex[:8]
    uid = st.session_state.admin_backup_uid

    # Инициализируем значения для сайта и домена
    if f"{uid}_site" not in st.session_state:
        st.session_state[f"{uid}_site"] = None
    if f"{uid}_domain" not in st.session_state:
        st.session_state[f"{uid}_domain"] = None

    sites = get_available_sites()
    if not sites:
        st.warning("Нет доступных сайтов.")
        return

    # Определяем индекс для selectbox
    site_index = 0
    if st.session_state[f"{uid}_site"] in sites:
        site_index = sites.index(st.session_state[f"{uid}_site"])

    selected_site = st.selectbox(
        "🏢 Сайт",
        sites,
        index=site_index,
        key=f"{uid}_site_select"
    )
    st.session_state[f"{uid}_site"] = selected_site

    domains = get_available_domains(selected_site)
    if not domains:
        st.warning(f"Нет доменов для сайта {selected_site}")
        return

    # Определяем индекс для домена
    domain_index = 0
    if st.session_state[f"{uid}_domain"] in domains:
        domain_index = domains.index(st.session_state[f"{uid}_domain"])
    else:
        # Если сохраненный домен не найден в новом списке, сбрасываем на первый
        st.session_state[f"{uid}_domain"] = domains[0] if domains else None

    selected_domain = st.selectbox(
        "🌐 Домен",
        domains,
        index=domain_index,
        key=f"{uid}_domain_select"
    )
    st.session_state[f"{uid}_domain"] = selected_domain

    users = get_users_for_site_domain(selected_site, selected_domain)
    if not users:
        st.info(f"Нет пользователей с проектами в {selected_site}/{selected_domain}.")
        return

    user_map = {uid: get_user_info(uid) for uid in users}
    user_labels = [f"{name} (ID: {uid})" for uid, name in user_map.items()]
    user_options = {label: uid for label, uid in zip(user_labels, users)}

    st.markdown("---")

    # ----- 1. Создание бэкапа -----
    st.markdown("### 1️⃣ Создать бэкап проектов")
    backup_choice = st.radio(
        "Выберите пользователей:",
        ["Все пользователи", "Выбрать конкретных"],
        key=f"{uid}_backup_choice"
    )
    selected_for_backup = []
    if backup_choice == "Выбрать конкретных":
        selected_labels = st.multiselect(
            "Пользователи для бэкапа:",
            user_labels,
            key=f"{uid}_backup_select"
        )
        selected_for_backup = [user_options[label] for label in selected_labels]
    else:
        selected_for_backup = users

    if st.button("📥 Создать и скачать ZIP-архив", key=f"{uid}_backup_download_btn"):
        zip_data = create_backup_zip_for_users(
            site_name=selected_site,
            domain_name=selected_domain,
            selected_users=selected_for_backup if backup_choice == "Выбрать конкретных" else None,
            include_all=(backup_choice == "Все пользователи")
        )
        if zip_data:
            st.download_button(
                label="💾 Скачать архив",
                data=zip_data,
                file_name=f"projects_backup_{selected_site}_{selected_domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip",
                key=f"{uid}_backup_download_final"
            )
        else:
            st.error("Не удалось создать бэкап")

    st.markdown("---")

    # ----- 2. Удаление проектов -----
    with st.form(key=f"{uid}_delete_form"):
        st.markdown("### 2️⃣ Удалить проекты (с автоматическим бэкапом)")
        st.warning("⚠️ Удаление необратимо! Перед удалением будет создан бэкап в папку `backups/`.")

        delete_choice = st.radio(
            "Выберите пользователей:",
            ["Все пользователи", "Выбрать конкретных"],
            key=f"{uid}_delete_choice"
        )
        selected_for_delete = []
        if delete_choice == "Выбрать конкретных":
            selected_labels = st.multiselect(
                "Пользователи для удаления:",
                user_labels,
                key=f"{uid}_delete_select"
            )
            selected_for_delete = [user_options[label] for label in selected_labels]
        else:
            selected_for_delete = users

        confirm = st.checkbox(
            "✅ Я подтверждаю, что хочу удалить проекты выбранных пользователей",
            key=f"{uid}_confirm_delete"
        )

        if st.form_submit_button("🗑️ Удалить проекты"):
            if not confirm:
                st.error("Необходимо подтвердить удаление")
            else:
                include_all = (delete_choice == "Все пользователи")
                success, msg, count = delete_projects_for_users(
                    site_name=selected_site,
                    domain_name=selected_domain,
                    selected_users=selected_for_delete if not include_all else None,
                    include_all=include_all,
                    backup_before_delete=True
                )
                if success:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

def render_user_backup_manager():
    """Упрощённый интерфейс для обычного пользователя"""
    st.subheader("💾 Мои проекты - бэкап и управление")
    st.markdown("---")

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("Пользователь не авторизован")
        return

    # Проверяем, что пользователь не админ
    from database_settings.database import is_admin
    if is_admin(user_id):
        st.warning("Вы администратор. Используйте админ-панель для управления всеми проектами.")
        return

    projects = get_user_projects(user_id)

    if not projects:
        st.info("У вас пока нет проектов.")
        return

    st.write(f"Найдено проектов: {len(projects)}")

    for idx, project in enumerate(projects):
        project_id = f"{project['site']}_{project['domain']}_{user_id}_{idx}"

        st.markdown(f"**Сайт:** {project['site']} | **Домен:** {project['domain']}")

        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                    f"📥 Скачать бэкап ({project['site']}/{project['domain']})",
                    key=f"backup_btn_{project_id}"
            ):
                zip_data = create_backup_zip_for_users(
                    site_name=project['site'],
                    domain_name=project['domain'],
                    user_id=user_id
                )
                if zip_data:
                    st.download_button(
                        label="💾 Скачать архив",
                        data=zip_data,
                        file_name=f"my_project_backup_{project['site']}_{project['domain']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        key=f"download_{project_id}"
                    )
                else:
                    st.error("Не удалось создать бэкап")

        # Альтернативный вариант для пользовательской панели (без формы)
        with col2:
            # Используем отдельные элементы, а не форму
            st.warning(f"⚠️ Удаление проекта {project['site']}/{project['domain']}")
            confirm_delete = st.checkbox(
                f"Я подтверждаю удаление проекта",
                key=f"confirm_{project_id}"
            )

            if st.button(f"🗑️ Удалить проект", key=f"delete_btn_{project_id}"):
                if not confirm_delete:
                    st.error("Необходимо подтвердить удаление")
                else:
                    try:
                        success, msg, count = delete_projects_for_users(
                            site_name=project['site'],
                            domain_name=project['domain'],
                            user_id=user_id,
                            backup_before_delete=True
                        )
                        if success:
                            st.success(f"✅ Проект удалён. Бэкап сохранён в папку backups/")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
                    except Exception as e:
                        st.error(f"Ошибка при удалении: {e}")

        st.markdown("---")