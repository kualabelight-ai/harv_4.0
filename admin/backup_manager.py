# admin/backup_manager.py

import streamlit as st
import zipfile
import os
import shutil
from pathlib import Path
import json
from datetime import datetime
import tempfile

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

def create_backup_zip_for_users(site_name, domain_name, selected_users=None, include_all=False):
    """
    Создаёт ZIP-архив с проектами для указанных пользователей в рамках одного сайта/домена.
    """
    if include_all:
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
        for user_id in users:
            user_dir = base_path / str(user_id)
            if not user_dir.exists():
                continue
            # Добавляем все файлы и папки внутри user_dir
            for item in user_dir.rglob("*"):
                if item.is_file():
                    arcname = str(item.relative_to(Path(".")))
                    zipf.write(item, arcname)

    with open(zip_path, 'rb') as f:
        zip_data = f.read()
    os.unlink(zip_path)
    return zip_data

def delete_projects_for_users(site_name, domain_name, selected_users=None, include_all=False, backup_before_delete=True):
    """
    Полностью удаляет папки пользователей для выбранных пользователей в указанном сайте/домене.
    Перед удалением создаёт бэкап (если включено).
    """
    if include_all:
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
        zip_data = create_backup_zip_for_users(site_name, domain_name, selected_users=users, include_all=False)
        if zip_data:
            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"projects_backup_{site_name}_{domain_name}_{timestamp}.zip"
            with open(backup_file, 'wb') as f:
                f.write(zip_data)
            st.info(f"📦 Бэкап сохранён: {backup_file}")

    deleted_count = 0
    for user_id in users:
        user_dir = base_path / str(user_id)
        if user_dir.exists():
            try:
                # Удаляем всю папку пользователя со всем содержимым
                shutil.rmtree(user_dir)
                deleted_count += 1
            except Exception as e:
                st.warning(f"Не удалось удалить папку {user_dir}: {e}")

    return True, f"Удалено {deleted_count} папок пользователей.", deleted_count

# -------------------------------------------
# Основной интерфейс
# -------------------------------------------

def render_backup_manager():
    st.subheader("💾 Бэкапы и очистка проектов")
    st.markdown("---")

    sites = get_available_sites()
    if not sites:
        st.warning("Нет доступных сайтов.")
        return

    # Выбор сайта
    col1, col2 = st.columns(2)
    with col1:
        selected_site = st.selectbox("🏢 Сайт", sites, key="backup_site_select")
    with col2:
        domains = get_available_domains(selected_site)
        if not domains:
            st.warning(f"Нет доменов для сайта {selected_site}")
            return
        selected_domain = st.selectbox("🌐 Домен", domains, key="backup_domain_select")

    # Получаем пользователей для этого сайта/домена
    users = get_users_for_site_domain(selected_site, selected_domain)
    if not users:
        st.info(f"Нет пользователей с проектами в {selected_site}/{selected_domain}.")
        return

    user_map = {uid: get_user_info(uid) for uid in users}
    user_labels = [f"{name} (ID: {uid})" for uid, name in user_map.items()]
    user_options = {label: uid for label, uid in zip(user_labels, users)}

    st.markdown("---")

    # ----- 1. Создание бэкапа (без формы) -----
    st.markdown("### 1️⃣ Создать бэкап проектов")
    backup_choice = st.radio(
        "Выберите пользователей:",
        ["Все пользователи", "Выбрать конкретных"],
        key="backup_choice"
    )
    selected_for_backup = []
    if backup_choice == "Выбрать конкретных":
        selected_labels = st.multiselect("Пользователи для бэкапа:", user_labels, key="backup_select")
        selected_for_backup = [user_options[label] for label in selected_labels]
    else:
        selected_for_backup = users

    if st.button("📥 Создать и скачать ZIP-архив", key="backup_download_btn"):
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
                key="backup_download_final"
            )
        else:
            st.error("Не удалось создать бэкап")

    st.markdown("---")

    # ----- 2. Удаление проектов (форма) -----
    with st.form("delete_form"):
        st.markdown("### 2️⃣ Удалить проекты (с автоматическим бэкапом)")
        st.warning("⚠️ Удаление необратимо! Перед удалением будет создан бэкап в папку `backups/`.")

        delete_choice = st.radio(
            "Выберите пользователей:",
            ["Все пользователи", "Выбрать конкретных"],
            key="delete_choice"
        )
        selected_for_delete = []
        if delete_choice == "Выбрать конкретных":
            selected_labels = st.multiselect("Пользователи для удаления:", user_labels, key="delete_select")
            selected_for_delete = [user_options[label] for label in selected_labels]
        else:
            selected_for_delete = users

        confirm = st.checkbox("✅ Я подтверждаю, что хочу удалить проекты выбранных пользователей", key="confirm_delete")

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