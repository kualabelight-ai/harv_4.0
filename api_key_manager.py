# api_key_manager.py
import streamlit as st
from datetime import datetime
from typing import Optional, Dict, List
from database_settings.database import get_db
from database_settings.models import APIKey


# api_key_manager.py

class APIKeyManager:
    def __init__(self, user_id: int = None, context=None):
        """
        Инициализация менеджера ключей

        Args:
            user_id: ID пользователя (для логирования)
            context: Контекст проекта (приоритет выше user_id)
        """
        self.user_id = user_id
        self.context = context

        # Если есть контекст - берем user_id из него
        if context is not None:
            self.user_id = getattr(context, 'user_id', user_id)

    def _get_user_id(self) -> Optional[int]:
        """Получает user_id с приоритетом: context > параметр > session_state"""
        # 1. Из контекста
        if self.context is not None:
            user_id = getattr(self.context, 'user_id', None)
            if user_id is not None:
                return user_id

        # 2. Из параметра
        if self.user_id is not None:
            return self.user_id

        # 3. Из session_state (только если в основном потоке)
        try:
            if 'user_id' in st.session_state:
                return st.session_state.user_id
        except:
            pass

        return None

    # api_key_manager.py - полный исправленный метод

    def _log_api_usage(self, site_name: str, domain_name: str, provider: str,
                       success: bool, error_message: str = None):
        """Логирует использование API ключа"""
        user_id = self._get_user_id()

        # Если нет user_id - пропускаем логирование (не критично)
        if user_id is None:
            print(f"ℹ️ API usage: {site_name}/{domain_name}/{provider} | success={success}")
            return

        try:
            with get_db() as conn:
                # ✅ ИСПРАВЛЕНО: api_usage_logs (как в auth.py)
                conn.execute("""
                    INSERT INTO api_usage_logs 
                    (user_id, site_name, domain_name, provider, success, error_message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, site_name, domain_name, provider, 1 if success else 0, error_message))
                conn.commit()
        except Exception as e:
            # Логирование не должно ломать основную функцию
            print(f"⚠️ Ошибка логирования API: {e}")

    def get_api_key(self, site_name: str, domain_name: str, provider: str) -> Optional[str]:
        """
        Получает API ключ с приоритетом:
        1. Ключ домена (site_name + domain_name)
        2. Ключ сайта (site_name + NULL domain_name)
        """
        with get_db() as conn:
            # Сначала ищем ключ конкретного домена
            result = conn.execute("""
                SELECT api_key FROM api_keys 
                WHERE site_name = ? AND domain_name = ? AND provider = ? AND is_active = 1
                ORDER BY 
                    CASE WHEN domain_name IS NOT NULL THEN 1 ELSE 2 END,
                    created_at DESC
                LIMIT 1
            """, (site_name, domain_name, provider)).fetchone()

            if result:
                # Обновляем last_used_at
                conn.execute("""
                    UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP
                    WHERE site_name = ? AND domain_name = ? AND provider = ?
                """, (site_name, domain_name, provider))
                conn.commit()

                # Логируем успешное использование
                self._log_api_usage(site_name, domain_name, provider, True)
                return result["api_key"]

            # Если нет - ищем ключ сайта (domain_name = NULL)
            result = conn.execute("""
                SELECT api_key FROM api_keys 
                WHERE site_name = ? AND domain_name IS NULL AND provider = ? AND is_active = 1
                LIMIT 1
            """, (site_name, provider)).fetchone()

            if result:
                conn.execute("""
                    UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP
                    WHERE site_name = ? AND domain_name IS NULL AND provider = ?
                """, (site_name, provider))
                conn.commit()

                # Логируем успешное использование
                self._log_api_usage(site_name, domain_name, provider, True)
                return result["api_key"]

            # Логируем ошибку - ключ не найден
            self._log_api_usage(site_name, domain_name, provider, False, "API key not found")
            return None

    def has_api_key(self, site_name: str, domain_name: str, provider: str) -> bool:
        """Проверяет наличие API ключа"""
        return self.get_api_key(site_name, domain_name, provider) is not None

    def set_api_key(self, site_name: str, domain_name: Optional[str], provider: str,
                    api_key: str, admin_id: int, notes: str = "") -> bool:
        """Устанавливает API ключ для сайта/домена"""
        try:
            with get_db() as conn:
                # Проверяем, существует ли уже такой ключ
                existing = conn.execute("""
                    SELECT id FROM api_keys 
                    WHERE site_name = ? AND (domain_name = ? OR (domain_name IS NULL AND ? IS NULL)) 
                    AND provider = ?
                """, (site_name, domain_name, domain_name, provider)).fetchone()

                if existing:
                    # Обновляем существующий
                    conn.execute("""
                        UPDATE api_keys 
                        SET api_key = ?, is_active = 1, last_used_at = NULL, notes = ?, created_by = ?
                        WHERE id = ?
                    """, (api_key, notes, admin_id, existing["id"]))
                else:
                    # Создаем новый
                    conn.execute("""
                        INSERT INTO api_keys (site_name, domain_name, provider, api_key, created_by, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (site_name, domain_name, provider, api_key, admin_id, notes))

                conn.commit()
                return True
        except Exception as e:
            st.error(f"Ошибка сохранения API ключа: {e}")
            return False

    def delete_api_key(self, key_id: int) -> bool:
        """Удаляет API ключ (мягкое удаление - деактивация)"""
        try:
            with get_db() as conn:
                conn.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))
                conn.commit()
                return True
        except Exception as e:
            st.error(f"Ошибка удаления API ключа: {e}")
            return False

    def get_all_keys(self, site_name: str = None, domain_name: str = None) -> List[Dict]:
        """Получает все API ключи с фильтрацией"""
        with get_db() as conn:
            query = """
                SELECT k.*, u.username as creator_name
                FROM api_keys k
                LEFT JOIN users u ON k.created_by = u.id
                WHERE k.is_active = 1
            """
            params = []

            if site_name:
                query += " AND k.site_name = ?"
                params.append(site_name)

            if domain_name:
                query += " AND k.domain_name = ?"
                params.append(domain_name)

            query += " ORDER BY k.site_name, k.domain_name, k.provider"

            results = conn.execute(query, params).fetchall()

            return [dict(row) for row in results]

    def get_keys_for_domain(self, site_name: str, domain_name: str) -> List[Dict]:
        """Получает ключи для конкретного домена (включая ключи сайта)"""
        with get_db() as conn:
            results = conn.execute("""
                SELECT * FROM api_keys 
                WHERE site_name = ? AND (domain_name = ? OR domain_name IS NULL) AND is_active = 1
                ORDER BY 
                    CASE WHEN domain_name IS NOT NULL THEN 1 ELSE 2 END,
                    provider
            """, (site_name, domain_name)).fetchall()

            return [dict(row) for row in results]


def get_api_key_for_current_domain(provider: str = None, context=None) -> Optional[str]:
    """
    Утилита для получения API ключа для текущего домена

    Args:
        provider: Провайдер (если None - берется из конфига)
        context: Контекст проекта (для получения user_id)
    """
    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    site_name = dm.site_name
    domain_name = dm.get_current_domain()

    if provider is None:
        from ai_settings.ai_module import AIConfigManager
        config_manager = AIConfigManager()
        provider = config_manager.config.get("default_provider", "agentplatform")

    # ✅ Передаем context в APIKeyManager
    key_manager = APIKeyManager(context=context)
    api_key = key_manager.get_api_key(site_name, domain_name, provider)

    if not api_key:
        # Используем print вместо st.warning в фоновых потоках
        print(f"⚠️ Нет API ключа для провайдера {provider} в домене {domain_name}")

        # Только если в основном потоке - показываем warning
        try:
            if st.runtime.scriptrunner.script_run_context.get_current() is not None:
                st.warning(f"⚠️ Нет API ключа для провайдера {provider} в домене {domain_name}. Обратитесь к администратору.")
        except:
            pass

    return api_key