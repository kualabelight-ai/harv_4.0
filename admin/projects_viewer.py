import streamlit as st
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")

def get_all_projects() -> List[Dict]:
    """Получает все проекты всех пользователей"""
    projects = []
    sites_dir = Path("sites")

    if not sites_dir.exists():
        return projects

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
            if not projects_dir.exists():
                continue

            for user_dir in projects_dir.iterdir():
                if not user_dir.is_dir():
                    continue

                # ✅ Преобразуем в int
                try:
                    user_id = int(user_dir.name)
                except ValueError:
                    print(f"⚠️ Неверный формат user_id: {user_dir.name}")
                    continue

                # Получаем имя пользователя
                from database_settings.database import get_db
                username = f"user_{user_id}"
                try:
                    with get_db() as conn:
                        user = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
                        if user:
                            username = user["username"]
                except Exception as e:
                    print(f"⚠️ Ошибка получения имени пользователя {user_id}: {e}")

                for project_file in user_dir.glob("*.json"):
                    if project_file.name == "queue_state.json":
                        continue

                    try:
                        with open(project_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        project_info = {
                            "project_id": project_file.stem,
                            "project_name": data.get("project_name", "Без названия"),
                            "category": data.get("category", "Без категории"),
                            "current_phase": data.get("current_phase", 1),
                            "created_at": data.get("created_at", ""),
                            "updated_at": data.get("updated_at", ""),
                            "site_name": site_dir.name,
                            "domain_name": domain_dir.name,
                            "user_id": user_id,
                            "username": username,
                            "file_path": str(project_file),
                            "has_phase5": bool(data.get("app_data", {}).get("phase5", {})),
                            "has_phase6": bool(data.get("app_data", {}).get("phase6", {})),
                            "has_phase7": bool(data.get("app_data", {}).get("phase7", {}))
                        }
                        projects.append(project_info)
                    except Exception as e:
                        print(f"Ошибка чтения {project_file}: {e}")

    projects.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return projects


def render_projects_viewer():
    """Просмотр всех проектов пользователей"""

    st.subheader("📁 Все проекты пользователей")
    st.markdown("---")

    if 'selected_project_for_view' not in st.session_state:
        st.session_state.selected_project_for_view = None
    if 'selected_project_for_download' not in st.session_state:
        st.session_state.selected_project_for_download = None
    if 'selected_project_for_delete' not in st.session_state:
        st.session_state.selected_project_for_delete = None

    col1, col2, col3, col4 = st.columns(4)

    all_projects = get_all_projects()

    if not all_projects:
        st.info("Нет проектов")
        return

    sites = sorted(list(set(p["site_name"] for p in all_projects)))
    domains = sorted(list(set(p["domain_name"] for p in all_projects)))

    # ✅ Исправлено: обрабатываем случай, когда username может быть None
    users = sorted(list(set((p["user_id"], p["username"] or f"user_{p['user_id']}") for p in all_projects)))

    with col1:
        filter_site = st.selectbox("Сайт", ["Все"] + sites, key="filter_site_projects")
    with col2:
        filter_domain = st.selectbox("Домен", ["Все"] + domains, key="filter_domain_projects")
    with col3:
        user_options = {f"{username} (ID: {uid})": uid for uid, username in users}
        filter_user = st.selectbox("Пользователь", ["Все"] + list(user_options.keys()), key="filter_user_projects")
    with col4:
        filter_phase = st.selectbox("Фаза", ["Все", "1", "2", "3", "4", "5", "6", "7"], key="filter_phase_projects")

    filtered = all_projects.copy()

    if filter_site != "Все":
        filtered = [p for p in filtered if p["site_name"] == filter_site]
    if filter_domain != "Все":
        filtered = [p for p in filtered if p["domain_name"] == filter_domain]
    if filter_user != "Все":
        selected_user_id = user_options[filter_user]
        filtered = [p for p in filtered if p["user_id"] == selected_user_id]
    if filter_phase != "Все":
        filtered = [p for p in filtered if p["current_phase"] == int(filter_phase)]

    st.info(f"📊 Найдено проектов: {len(filtered)} из {len(all_projects)}")

    col_export1, col_export2, col_export3 = st.columns(3)
    with col_export2:
        if st.button("📥 Экспортировать в CSV", use_container_width=True, key="export_all_projects_csv"):
            export_data = []
            for p in filtered:
                export_data.append({
                    "ID проекта": p["project_id"],
                    "Название": p["project_name"],
                    "Категория": p["category"],
                    "Пользователь": p["username"],
                    "User ID": p["user_id"],
                    "Сайт": p["site_name"],
                    "Домен": p["domain_name"],
                    "Фаза": p["current_phase"],
                    "Создан": p["created_at"],
                    "Обновлен": p["updated_at"],
                    "Phase5": "✅" if p["has_phase5"] else "❌",
                    "Phase6": "✅" if p["has_phase6"] else "❌",
                    "Phase7": "✅" if p["has_phase7"] else "❌"
                })

            df = pd.DataFrame(export_data)
            csv = df.to_csv(index=False).encode('utf-8')

            st.download_button(
                label="📥 Скачать CSV",
                data=csv,
                file_name=f"projects_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="download_csv_btn"
            )

    st.markdown("---")

    for idx, project in enumerate(filtered):
        unique_key = f"{project['project_id']}_{idx}_{project['user_id']}"

        with st.expander(f"📁 {project['project_name']} - {project['username']} ({project['site_name']}/{project['domain_name']})"):
            col1, col2 = st.columns(2)

            with col1:
                st.write(f"**ID:** `{project['project_id']}`")
                st.write(f"**Категория:** {project['category']}")
                st.write(f"**Текущая фаза:** {project['current_phase']}/7")
                st.write(f"**Создан:** {project['created_at']}")
                st.write(f"**Обновлен:** {project['updated_at']}")

            with col2:
                st.write(f"**Сайт:** {project['site_name']}")
                st.write(f"**Домен:** {project['domain_name']}")
                st.write(f"**Пользователь:** {project['username']} (ID: {project['user_id']})")
                st.write(f"**Путь:** `{project['file_path']}`")

            col_btn1, col_btn2, col_btn3 = st.columns(3)

            with col_btn1:
                view_key = f"view_{unique_key}"
                if st.button("📄 Просмотреть содержимое", key=view_key):
                    st.session_state.selected_project_for_view = project
                    st.rerun()

            with col_btn2:
                download_key = f"download_{unique_key}"
                if st.button("📥 Скачать JSON", key=download_key):
                    st.session_state.selected_project_for_download = project
                    st.rerun()

            with col_btn3:
                delete_key = f"delete_{unique_key}"
                if st.button("🗑️ Удалить", key=delete_key):
                    st.session_state.selected_project_for_delete = project

    if st.session_state.selected_project_for_view:
        project = st.session_state.selected_project_for_view
        st.divider()
        st.subheader(f"📄 Содержимое проекта: {project['project_name']}")

        try:
            with open(project['file_path'], 'r', encoding='utf-8') as f:
                content = json.load(f)
            st.json(content)
        except Exception as e:
            st.error(f"Ошибка чтения: {e}")

        if st.button("Закрыть", key="close_view_content"):
            st.session_state.selected_project_for_view = None
            st.rerun()

    if st.session_state.selected_project_for_download:
        project = st.session_state.selected_project_for_download
        try:
            with open(project['file_path'], 'r', encoding='utf-8') as f:
                content = f.read()

            st.download_button(
                label="📥 Скачать JSON",
                data=content,
                file_name=f"{project['project_id']}.json",
                mime="application/json",
                key=f"download_final_{project['project_id']}"
            )

            if st.button("Закрыть", key="close_download"):
                st.session_state.selected_project_for_download = None
                st.rerun()
        except Exception as e:
            st.error(f"Ошибка: {e}")
            if st.button("Закрыть", key="close_download_error"):
                st.session_state.selected_project_for_download = None
                st.rerun()

    if st.session_state.selected_project_for_delete:
        project = st.session_state.selected_project_for_delete

        st.warning(f"⚠️ Вы действительно хотите удалить проект '{project['project_name']}'?")

        col_confirm1, col_confirm2 = st.columns(2)
        with col_confirm1:
            if st.button("✅ Да, удалить", key=f"confirm_delete_{project['project_id']}"):
                try:
                    Path(project['file_path']).unlink()
                    st.success("✅ Проект удален")
                    st.session_state.selected_project_for_delete = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка удаления: {e}")

        with col_confirm2:
            if st.button("❌ Отмена", key=f"cancel_delete_{project['project_id']}"):
                st.session_state.selected_project_for_delete = None
                st.rerun()