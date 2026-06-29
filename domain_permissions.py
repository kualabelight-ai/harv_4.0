# domain_permissions.py
"""
Утилиты для работы с доменами - ЕДИНЫЙ ИСТОЧНИК ПРАВДЫ
"""

import streamlit as st
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import json
from datetime import datetime


# ==================== КЛАСС ДЛЯ РАБОТЫ С ПРАВАМИ ЧЕРЕЗ БД ====================
class DomainPermissionManager:
    """
    Менеджер разрешений для доменов
    Использует таблицу user_domain_permissions в БД
    """

    def __init__(self, site_name: str = None):
        self.site_name = site_name or st.session_state.get('current_site', 'steelborg')

    def _get_db(self):
        """Получает соединение с БД"""
        from database_settings.database import get_db
        return get_db()

    def can_access(self, user_id: int, site_name: str = None, domain_name: str = None) -> bool:
        """
        Проверяет, может ли пользователь получить доступ к сайту/домену.
        """
        # Если site_name не указан, используем текущий
        if site_name is None:
            site_name = self.site_name

        # Если domain_name не указан, используем текущий домен
        if domain_name is None:
            domain_name = st.session_state.get('current_domain', 'default')

        # Проверяем права администратора (админы имеют доступ ко всему)
        try:
            from database_settings.database import get_db
            with get_db() as conn:
                user = conn.execute(
                    "SELECT is_admin FROM users WHERE id = ?",
                    (user_id,)
                ).fetchone()
                if user and user["is_admin"] == 1:
                    return True
        except:
            pass

        # Проверяем права в таблице user_domain_permissions
        try:
            with self._get_db() as conn:
                perm = conn.execute("""
                    SELECT 1 FROM user_domain_permissions 
                    WHERE user_id = ? AND site_name = ? AND domain_name = ?
                    AND can_read = 1
                """, (user_id, site_name, domain_name)).fetchone()

                return perm is not None
        except Exception as e:
            print(f"⚠️ Ошибка проверки прав: {e}")
            return False

    def grant_access(self, admin_user_id: int, target_user_id: int, site_name: str,
                     domain_name: str, can_read: bool = True, can_write: bool = False,
                     can_delete: bool = False) -> bool:
        """
        Выдает пользователю доступ к домену с определенными правами
        """
        try:
            from database_settings.database import get_db
            with get_db() as conn:
                # Проверяем, есть ли уже запись
                existing = conn.execute("""
                    SELECT id FROM user_domain_permissions 
                    WHERE user_id = ? AND site_name = ? AND domain_name = ?
                """, (target_user_id, site_name, domain_name)).fetchone()

                if existing:
                    # Обновляем существующую запись
                    conn.execute("""
                        UPDATE user_domain_permissions 
                        SET can_read = ?, can_write = ?, can_delete = ?, 
                            granted_by = ?, granted_at = CURRENT_TIMESTAMP
                        WHERE user_id = ? AND site_name = ? AND domain_name = ?
                    """, (can_read, can_write, can_delete, admin_user_id,
                          target_user_id, site_name, domain_name))
                else:
                    # Вставляем новую запись
                    conn.execute("""
                        INSERT INTO user_domain_permissions 
                        (user_id, site_name, domain_name, can_read, can_write, can_delete, granted_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (target_user_id, site_name, domain_name, can_read, can_write, can_delete, admin_user_id))

                conn.commit()
                print(f"✅ Выданы права пользователю {target_user_id} на {site_name}/{domain_name}")
                return True

        except Exception as e:
            print(f"❌ Ошибка выдачи прав: {e}")
            return False

    def revoke_access(self, user_id: int, site_name: str = None, domain_name: str = None) -> bool:
        """
        Отзывает у пользователя доступ к домену
        """
        try:
            from database_settings.database import get_db
            with get_db() as conn:
                # Если site_name не указан, используем текущий
                if site_name is None:
                    site_name = self.site_name

                # Если domain_name не указан, используем текущий домен
                if domain_name is None:
                    domain_name = st.session_state.get('current_domain', 'default')

                conn.execute("""
                    DELETE FROM user_domain_permissions 
                    WHERE user_id = ? AND site_name = ? AND domain_name = ?
                """, (user_id, site_name, domain_name))
                conn.commit()

                print(f"✅ Отозваны права у пользователя {user_id} на {site_name}/{domain_name}")
                return True

        except Exception as e:
            print(f"❌ Ошибка отзыва прав: {e}")
            return False

    def get_users_with_access(self, site_name: str = None, domain_name: str = None) -> List[Dict]:
        """
        Возвращает список пользователей с доступом к домену
        """
        try:
            from database_settings.database import get_db

            # Если site_name не указан, используем текущий
            if site_name is None:
                site_name = self.site_name

            # Если domain_name не указан, используем текущий домен
            if domain_name is None:
                domain_name = st.session_state.get('current_domain', 'default')

            with get_db() as conn:
                users = conn.execute("""
                    SELECT u.id, u.username, u.email, 
                           p.can_read, p.can_write, p.can_delete,
                           p.granted_at, p.granted_by
                    FROM user_domain_permissions p
                    JOIN users u ON u.id = p.user_id
                    WHERE p.site_name = ? AND p.domain_name = ?
                    ORDER BY u.username
                """, (site_name, domain_name)).fetchall()

                result = []
                for u in users:
                    result.append({
                        'id': u['id'],
                        'username': u['username'],
                        'email': u['email'],
                        'can_read': bool(u['can_read']),
                        'can_write': bool(u['can_write']),
                        'can_delete': bool(u['can_delete']),
                        'granted_at': u['granted_at'],
                        'granted_by': u['granted_by']
                    })

                return result

        except Exception as e:
            print(f"❌ Ошибка получения списка пользователей: {e}")
            return []

    def get_user_permissions(self, user_id: int) -> Dict:
        """
        Возвращает все права пользователя
        """
        try:
            from database_settings.database import get_db
            with get_db() as conn:
                perms = conn.execute("""
                    SELECT site_name, domain_name, can_read, can_write, can_delete
                    FROM user_domain_permissions 
                    WHERE user_id = ?
                """, (user_id,)).fetchall()

                result = {}
                for p in perms:
                    key = f"{p['site_name']}/{p['domain_name']}"
                    result[key] = {
                        'can_read': bool(p['can_read']),
                        'can_write': bool(p['can_write']),
                        'can_delete': bool(p['can_delete'])
                    }

                return result

        except Exception as e:
            print(f"❌ Ошибка получения прав пользователя: {e}")
            return {}

    def get_user_domains(self, user_id: int) -> List[str]:
        """
        Возвращает список доменов, доступных пользователю
        """
        try:
            from database_settings.database import get_db
            with get_db() as conn:
                perms = conn.execute("""
                    SELECT site_name, domain_name 
                    FROM user_domain_permissions 
                    WHERE user_id = ? AND can_read = 1
                """, (user_id,)).fetchall()

                return [f"{p['site_name']}/{p['domain_name']}" for p in perms]

        except Exception as e:
            print(f"❌ Ошибка получения доменов пользователя: {e}")
            return []

    def has_any_permission(self, user_id: int) -> bool:
        """
        Проверяет, есть ли у пользователя хоть какие-то разрешения
        """
        try:
            from database_settings.database import get_db
            with get_db() as conn:
                perm = conn.execute("""
                    SELECT 1 FROM user_domain_permissions 
                    WHERE user_id = ?
                    LIMIT 1
                """, (user_id,)).fetchone()

                return perm is not None

        except Exception as e:
            print(f"❌ Ошибка проверки прав: {e}")
            return False


# ==================== ОСТАЛЬНЫЕ ФУНКЦИИ ====================

def get_current_domain_from_file(site_name: str = None) -> Tuple[str, str]:
    """
    Возвращает (site_name, domain_name) ИЗ ФАЙЛА НАСТРОЕК ПОЛЬЗОВАТЕЛЯ
    НЕ ТРОГАЕТ session_state!
    """
    if site_name is None:
        site_name = st.session_state.get('current_site', 'steelborg')

    user_id = st.session_state.get('user_id')

    # ✅ ПРОВЕРЯЕМ ФАЙЛ НАСТРОЕК ПОЛЬЗОВАТЕЛЯ
    if user_id:
        settings_file = Path(f"sites/users/{user_id}/settings.json")
        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    saved_domain = data.get('selected_domain', 'default')
                    saved_site = data.get('selected_site', site_name)

                    # Проверяем, существует ли такой домен
                    domain_path = Path(f"sites/{saved_site}/domains/{saved_domain}")
                    if domain_path.exists() and (domain_path / "config.json").exists():
                        return saved_site, saved_domain
            except Exception as e:
                print(f"⚠️ Ошибка загрузки настроек пользователя: {e}")

    # Fallback - старый способ через current_domain.txt
    config_file = Path(f"sites/{site_name}/current_domain.txt")
    domain = 'default'

    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                saved = f.read().strip()
                if saved:
                    domain_path = Path(f"sites/{site_name}/domains/{saved}")
                    if domain_path.exists() and (domain_path / "config.json").exists():
                        domain = saved
        except:
            pass

    return site_name, domain


def get_project_domain(project_id: str, user_id: int) -> Optional[Tuple[str, str]]:
    """
    Возвращает (site_name, domain_name) проекта ИЗ ЕГО ФАЙЛА
    Ищет проект ВО ВСЕХ ДОМЕНАХ (только для поиска!)
    """
    sites_base = Path("sites")

    for site_dir in sites_base.iterdir():
        if not site_dir.is_dir():
            continue

        domains_dir = site_dir / "domains"
        if not domains_dir.exists():
            continue

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            project_file = domain_dir / "projects" / str(user_id) / f"{project_id}.json"
            if project_file.exists():
                try:
                    with open(project_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return data.get('site_name', site_dir.name), data.get('domain_name', domain_dir.name)
                except:
                    return site_dir.name, domain_dir.name

    return None, None


def ensure_domain_consistency(project_id: str = None):
    """
    ГАРАНТИРУЕТ, что session_state содержит правильный домен
    - Если есть проект - берем домен из файла проекта
    - Если нет проекта - берем домен из файла настроек пользователя
    """
    user_id = st.session_state.get('user_id')

    # 1. Если есть проект - используем его домен
    if project_id and user_id:
        site, domain = get_project_domain(project_id, user_id)
        if site and domain:
            # Обновляем DomainManager
            if 'domain_manager' not in st.session_state:
                from domain_manager import DomainManager
                st.session_state.domain_manager = DomainManager(site)
            else:
                dm = st.session_state.domain_manager
                if dm.site_name != site:
                    st.session_state.domain_manager = DomainManager(site)

            dm = st.session_state.domain_manager
            dm.set_current_domain(domain)

            # Обновляем session_state для отображения
            st.session_state.current_site = site
            st.session_state.current_domain = domain
            st.session_state.selected_site = site
            st.session_state.selected_domain = domain

            print(f"✅ Домен синхронизирован с проектом: {site}/{domain}")
            return True

    # 2. Если нет проекта - используем сохраненный домен
    site, domain = get_current_domain_from_file()

    # ✅ ОБНОВЛЯЕМ session_state
    st.session_state.current_site = site
    st.session_state.current_domain = domain
    st.session_state.selected_site = site
    st.session_state.selected_domain = domain

    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager(site)
    else:
        dm = st.session_state.domain_manager
        if dm.site_name != site:
            st.session_state.domain_manager = DomainManager(site)

    dm = st.session_state.domain_manager
    dm.set_current_domain(domain)

    print(f"✅ Домен синхронизирован с конфигом: {site}/{domain}")
    return True


def get_user_domain_from_settings(user_id: int = None) -> Tuple[str, str]:
    """
    Возвращает (site_name, domain_name) ИЗ ФАЙЛА НАСТРОЕК ПОЛЬЗОВАТЕЛЯ
    """
    if user_id is None:
        user_id = st.session_state.get('user_id')

    if not user_id:
        return 'steelborg', 'default'

    settings_file = Path(f"sites/users/{user_id}/settings.json")

    if settings_file.exists():
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('selected_site', 'steelborg'), data.get('selected_domain', 'default')
        except Exception as e:
            print(f"⚠️ Ошибка загрузки настроек: {e}")

    return 'steelborg', 'default'