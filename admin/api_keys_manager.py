# admin/api_keys_manager.py
import streamlit as st
from database_settings.database import get_db
from api_key_manager import APIKeyManager
from admin.audit_viewer import log_admin_action
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")

def render_api_keys_manager():
    """Управление API ключами для сайтов и доменов"""

    st.subheader("🔑 Управление API ключами")
    st.markdown("---")

    key_manager = APIKeyManager()

    # Вкладки
    tab_list, tab_add = st.tabs(["📋 Список ключей", "➕ Добавить ключ"])

    with tab_list:
        # Фильтры
        col1, col2 = st.columns(2)
        with col1:
            sites = []
            from pathlib import Path
            sites_dir = Path("sites")
            if sites_dir.exists():
                sites = [d.name for d in sites_dir.iterdir() if d.is_dir()]

            if sites:
                filter_site = st.selectbox("Фильтр по сайту", ["Все"] + sites)
            else:
                filter_site = "Все"

        with col2:
            filter_provider = st.selectbox("Фильтр по провайдеру", ["Все", "agentplatform", "deepseek"])

        # Получаем ключи
        all_keys = key_manager.get_all_keys()

        # Фильтруем
        filtered_keys = all_keys
        if filter_site != "Все":
            filtered_keys = [k for k in filtered_keys if k["site_name"] == filter_site]
        if filter_provider != "Все":
            filtered_keys = [k for k in filtered_keys if k["provider"] == filter_provider]

        if not filtered_keys:
            st.info("Нет API ключей")
        else:
            for key in filtered_keys:
                with st.expander(f"🔑 {key['site_name']}/{key['domain_name'] or 'весь сайт'} - {key['provider']}"):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.write(f"**Ключ:** `{key['api_key'][:20]}...{key['api_key'][-10:] if len(key['api_key']) > 30 else ''}`")
                        st.write(f"**Создан:** {key['created_by']} ({key.get('creator_name', 'unknown')})")
                        st.write(f"**Дата:** {key['created_at']}")
                        if key['last_used_at']:
                            st.write(f"**Последнее использование:** {key['last_used_at']}")
                        if key['notes']:
                            st.write(f"**Примечания:** {key['notes']}")

                    with col2:
                        if st.button("🗑️ Удалить", key=f"del_key_{key['id']}"):
                            if key_manager.delete_api_key(key['id']):
                                log_admin_action(
                                    st.session_state.user_id,
                                    "delete_api_key",
                                    "api_key",
                                    str(key['id']),
                                    f"Удален ключ {key['provider']} для {key['site_name']}/{key['domain_name'] or 'весь сайт'}"
                                )
                                st.success("✅ Ключ удален")
                                st.rerun()
                            else:
                                st.error("❌ Ошибка удаления")

    with tab_add:
        st.subheader("Добавить новый API ключ")

        with st.form("add_api_key_form"):
            # Выбор сайта
            from pathlib import Path
            sites = []
            sites_dir = Path("sites")
            if sites_dir.exists():
                sites = [d.name for d in sites_dir.iterdir() if d.is_dir()]

            if not sites:
                st.error("Нет доступных сайтов")
                return

            col1, col2 = st.columns(2)
            with col1:
                site_name = st.selectbox("Сайт", sites)

                # Выбор домена
                from domain_manager import DomainManager
                dm = DomainManager(site_name)
                domains = dm.get_available_domains()
                domain_options = ["(весь сайт)"] + domains
                domain_choice = st.selectbox("Домен", domain_options)
                domain_name = None if domain_choice == "(весь сайт)" else domain_choice

            with col2:
                provider = st.selectbox("Провайдер", ["agentplatform", "deepseek"])
                api_key = st.text_input("API ключ", type="password")
                notes = st.text_area("Примечания (необязательно)", height=100)

            if st.form_submit_button("💾 Сохранить ключ"):
                if api_key and api_key.strip():
                    if key_manager.set_api_key(
                            site_name=site_name,
                            domain_name=domain_name,
                            provider=provider,
                            api_key=api_key.strip(),
                            admin_id=st.session_state.user_id,
                            notes=notes
                    ):
                        log_admin_action(
                            st.session_state.user_id,
                            "create_api_key",
                            "api_key",
                            f"{site_name}/{domain_name or 'site'}",
                            f"Создан ключ {provider} для {site_name}/{domain_name or 'весь сайт'}"
                        )
                        st.success("✅ API ключ сохранен")
                        st.rerun()
                    else:
                        st.error("❌ Ошибка сохранения ключа")
                else:
                    st.error("❌ Введите API ключ")

    # Информация о приоритете
    with st.expander("ℹ️ Как работают API ключи?"):
        st.markdown("""
        **Приоритет использования API ключей:**
        1. **Ключ домена** - если есть ключ для конкретного домена, используется он
        2. **Ключ сайта** - если нет ключа домена, используется ключ для всего сайта
        
        **Пример:**
        - Сайт `steelborg`, домен `europe`
        - Если есть ключ для `steelborg/europe` - используется он
        - Если нет - используется ключ для `steelborg` (весь сайт)
        
        **Рекомендации:**
        - Для разных регионов можно использовать разные API ключи
        - Если у домена нет своего ключа, будет использован ключ сайта
        """)