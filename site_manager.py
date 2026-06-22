# site_manager.py
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import streamlit as st
from domain_manager import DomainManager


class SiteManager:
    """Управление сайтами"""

    def __init__(self):
        self.sites_dir = Path("sites")
        self.sites_dir.mkdir(parents=True, exist_ok=True)

        # ✅ ДОБАВИТЬ СИНХРОНИЗАЦИЮ ДОМЕНА ИЗ ФАЙЛА
        try:
            user_id = st.session_state.get('user_id')
            if user_id:
                from domain_manager import DomainManager
                if 'domain_manager' not in st.session_state:
                    st.session_state.domain_manager = DomainManager()

                dm = st.session_state.domain_manager
                settings = dm.load_user_settings(user_id)
                saved_domain = settings.get('selected_domain', 'default')
                saved_site = settings.get('selected_site', 'steelborg')

                # Обновляем session_state
                st.session_state.current_domain = saved_domain
                st.session_state.selected_domain = saved_domain
                st.session_state.current_site = saved_site
                st.session_state.selected_site = saved_site
                st.session_state[f'domain_system_{saved_site}'] = saved_domain

                print(f"✅ SiteManager загружен домен из файла: {saved_domain}")
        except Exception as e:
            print(f"⚠️ SiteManager: ошибка загрузки домена: {e}")

    def get_available_sites(self) -> List[str]:
        """Возвращает список доступных сайтов"""
        if not self.sites_dir.exists():
            return []

        sites = []
        for site_dir in self.sites_dir.iterdir():
            if site_dir.is_dir() and (site_dir / "config.json").exists():
                sites.append(site_dir.name)

        return sorted(sites)

    def get_current_site(self) -> str:
        """Возвращает текущий сайт из session_state"""
        return st.session_state.get('current_site', 'steelborg')

    def set_current_site(self, site_name: str):
        """Устанавливает текущий сайт"""
        st.session_state['current_site'] = site_name
        # Сбрасываем загруженный домен при смене сайта
        st.session_state.pop('domain_data_loaded', None)

    def get_site_config(self, site_name: str = None) -> Dict:
        """Получает конфигурацию сайта"""
        if site_name is None:
            site_name = self.get_current_site()

        config_path = self.sites_dir / site_name / "config.json"

        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        # Если нет - создаем дефолтный сайт
        return self._create_default_site(site_name)

    def _create_default_site(self, site_name: str) -> Dict:
        """Создает дефолтный сайт с базовой структурой"""
        site_dir = self.sites_dir / site_name
        site_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "site_name": site_name,
            "display_name": site_name.capitalize(),
            "description": f"Сайт {site_name}",
            "created_at": datetime.now().isoformat(),
            "modules": ["texts", "faq", "reviews"],
            "default_module": "texts",
            "ai_config": {
                "default_provider": "deepseek",
                "default_model": "deepseek-chat",
                "temperature": 0.7,
                "max_tokens": 2000
            }
        }

        with open(site_dir / "config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # Создаем структуру доменов для сайта
        domains_dir = site_dir / "domains"
        domains_dir.mkdir(exist_ok=True)

        # Создаем дефолтный домен через DomainManager
        dm = DomainManager(site_name)
        dm._create_default_domain()

        return config

    def create_new_site(self, site_name: str, display_name: str = None, description: str = "") -> bool:
        """Создает новый сайт"""
        if not site_name or site_name in self.get_available_sites():
            return False

        site_dir = self.sites_dir / site_name
        site_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "site_name": site_name,
            "display_name": display_name or site_name.capitalize(),
            "description": description or f"Сайт {site_name}",
            "created_at": datetime.now().isoformat(),
            "modules": ["texts", "faq", "reviews"],
            "default_module": "texts",
            "ai_config": {
                "default_provider": "deepseek",
                "default_model": "deepseek-chat",
                "temperature": 0.7,
                "max_tokens": 2000
            }
        }

        with open(site_dir / "config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # Создаем структуру доменов
        domains_dir = site_dir / "domains"
        domains_dir.mkdir(exist_ok=True)

        # Создаем дефолтный домен
        dm = DomainManager(site_name)
        dm._create_default_domain()

        return True

    def delete_site(self, site_name: str) -> bool:
        """Удаляет сайт (нельзя удалить steelborg)"""
        if site_name == 'steelborg':
            return False

        site_dir = self.sites_dir / site_name
        if site_dir.exists():
            shutil.rmtree(site_dir)
            return True
        return False

    def update_site_config(self, site_name: str, config_data: Dict) -> bool:
        """Обновляет конфигурацию сайта"""
        config_path = self.sites_dir / site_name / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            config.update(config_data)
            config['updated_at'] = datetime.now().isoformat()

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        return False

    def get_site_domains(self, site_name: str = None) -> List[str]:
        """Возвращает список доменов для сайта"""
        if site_name is None:
            site_name = self.get_current_site()

        dm = DomainManager(site_name)
        return dm.get_available_domains()

    def create_domain_for_site(self, site_name: str, domain_name: str) -> bool:
        """Создает новый домен для сайта"""
        dm = DomainManager(site_name)
        if dm.domain_exists(domain_name):
            return False

        dm._create_domain_from_default(domain_name)
        return True

    def delete_domain_for_site(self, site_name: str, domain_name: str) -> bool:
        """Удаляет домен сайта"""
        if domain_name == 'default':
            return False

        dm = DomainManager(site_name)
        return dm.delete_domain(domain_name)


def render_site_selector() -> str:
    """Рендерит селектор сайтов в интерфейсе"""

    if 'site_manager' not in st.session_state:
        st.session_state.site_manager = SiteManager()

    sm = st.session_state.site_manager
    sites = sm.get_available_sites()

    if not sites:
        st.warning("⚠️ Нет доступных сайтов. Создайте хотя бы один.")
        return 'steelborg'

    current_site = sm.get_current_site()

    # Проверяем, что текущий сайт существует
    if current_site not in sites:
        current_site = sites[0]
        sm.set_current_site(current_site)

    # Создаем словарь для selectbox
    site_options = {}
    for site in sites:
        config = sm.get_site_config(site)
        display_name = config.get('display_name', site.capitalize())
        site_options[display_name] = site

    col1, col2 = st.columns([3, 1])

    with col1:
        selected_display = st.selectbox(
            "🏢 Выберите сайт",
            options=list(site_options.keys()),
            index=list(site_options.values()).index(current_site) if current_site in site_options.values() else 0,
            key="site_selector_main",
            help="Выбор сайта определяет, с каким проектом вы работаете"
        )
        selected_site = site_options[selected_display]

    with col2:
        if st.button("⚙️ Управление сайтами", key="manage_sites_btn", use_container_width=True):
            st.session_state.show_site_manager = True
            st.rerun()

    # Если сайт изменился, обновляем
    if selected_site != current_site:
        sm.set_current_site(selected_site)
        # Обновляем DomainManager для нового сайта
        st.session_state.domain_manager = DomainManager(selected_site)

        # ✅ ЗАГРУЖАЕМ ДОМЕН ПОЛЬЗОВАТЕЛЯ ДЛЯ НОВОГО САЙТА
        user_id = st.session_state.get('user_id')
        if user_id:
            dm = st.session_state.domain_manager
            settings = dm.load_user_settings(user_id)
            saved_domain = settings.get('selected_domain', 'default')
            dm.set_current_domain(saved_domain)
            st.session_state.current_domain = saved_domain
            st.session_state.selected_domain = saved_domain
            st.session_state[f'domain_system_{selected_site}'] = saved_domain
            print(f"✅ Загружен домен для сайта {selected_site}: {saved_domain}")

        st.success(f"✅ Переключено на сайт: {selected_display}")
        st.rerun()

    return selected_site


def render_site_admin_panel():
    """Панель администратора для управления сайтами и доменами"""

    st.markdown("## 🏢 Управление сайтами и доменами")
    st.markdown("---")

    if 'site_manager' not in st.session_state:
        st.session_state.site_manager = SiteManager()

    sm = st.session_state.site_manager
    sites = sm.get_available_sites()

    # Только для администраторов
    try:
        from database_settings.auth import is_admin
        if not is_admin(st.session_state.get('user_id')):
            st.error("❌ Доступ только для администраторов")
            if st.button("← Назад"):
                st.session_state.show_site_manager = False
                st.rerun()
            return
    except:
        # Если не можем проверить - показываем предупреждение
        st.warning("⚠️ Проверка прав администратора недоступна")

    # Вкладки
    tab_sites, tab_domains = st.tabs(["🏢 Управление сайтами", "🌐 Управление доменами"])

    with tab_sites:
        st.subheader("📋 Список сайтов")

        if not sites:
            st.info("Нет доступных сайтов")
        else:
            for site in sites:
                config = sm.get_site_config(site)
                display_name = config.get('display_name', site.capitalize())
                description = config.get('description', '')
                created_at = config.get('created_at', '')
                modules = config.get('modules', [])

                with st.expander(f"🏢 {display_name} ({site})", expanded=False):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.write(f"**Описание:** {description}")
                        st.write(f"**Создан:** {created_at[:19] if created_at else 'Неизвестно'}")
                        st.write(f"**Модули:** {', '.join(modules)}")

                        if site != 'steelborg':
                            new_display_name = st.text_input(
                                "Отображаемое имя",
                                value=display_name,
                                key=f"site_display_{site}"
                            )
                            new_description = st.text_input(
                                "Описание",
                                value=description,
                                key=f"site_desc_{site}"
                            )

                            if st.button("💾 Сохранить изменения", key=f"save_site_{site}"):
                                sm.update_site_config(site, {
                                    'display_name': new_display_name,
                                    'description': new_description
                                })
                                st.success("✅ Изменения сохранены")
                                st.rerun()

                    with col2:
                        if site != 'steelborg':
                            if st.button("🗑️ Удалить сайт", key=f"delete_site_{site}", type="secondary"):
                                if sm.delete_site(site):
                                    st.success(f"✅ Сайт '{display_name}' удален")
                                    st.rerun()
                                else:
                                    st.error("❌ Ошибка удаления")
                        else:
                            st.caption("🔒 Защищенный сайт (нельзя удалить)")

        st.markdown("---")
        st.subheader("➕ Создать новый сайт")

        with st.form("create_site_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_site_name = st.text_input("Имя сайта (латиницей)", placeholder="например: new_site")
            with col2:
                new_site_display = st.text_input("Отображаемое имя", placeholder="например: Новый сайт")

            new_site_desc = st.text_area("Описание", placeholder="Краткое описание сайта")

            if st.form_submit_button("🚀 Создать сайт", use_container_width=True):
                if new_site_name and new_site_name.isalnum():
                    if sm.create_new_site(new_site_name, new_site_display, new_site_desc):
                        st.success(f"✅ Сайт '{new_site_name}' создан!")
                        st.rerun()
                    else:
                        st.error("❌ Сайт с таким именем уже существует")
                else:
                    st.error("❌ Введите корректное имя сайта (только латиница и цифры)")

    with tab_domains:
        st.subheader("🌐 Управление доменами")

        current_site = sm.get_current_site()
        site_config = sm.get_site_config(current_site)
        site_display = site_config.get('display_name', current_site.capitalize())

        st.info(f"Текущий сайт: **{site_display}**")

        dm = DomainManager(current_site)
        domains = dm.get_available_domains()

        if not domains:
            st.info("Нет доступных доменов")
        else:
            for domain in domains:
                config = dm.get_domain_config(domain)
                display_name = config.get('display_name', domain.capitalize())
                description = config.get('description', '')
                created_at = config.get('created_at', '')
                based_on = config.get('based_on', '')

                with st.expander(f"🌐 {display_name} ({domain})", expanded=False):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.write(f"**Описание:** {description}")
                        st.write(f"**Создан:** {created_at[:19] if created_at else 'Неизвестно'}")
                        if based_on:
                            st.write(f"**Основан на:** {based_on}")

                        if domain != 'default':
                            new_display_name = st.text_input(
                                "Отображаемое имя",
                                value=display_name,
                                key=f"domain_display_{current_site}_{domain}"
                            )
                            new_description = st.text_input(
                                "Описание",
                                value=description,
                                key=f"domain_desc_{current_site}_{domain}"
                            )

                            if st.button("💾 Сохранить изменения", key=f"save_domain_{current_site}_{domain}"):
                                config['display_name'] = new_display_name
                                config['description'] = new_description
                                config['updated_at'] = datetime.now().isoformat()
                                dm.save_phase_data(0, config)
                                st.success("✅ Изменения сохранены")
                                st.rerun()

                    with col2:
                        if domain != 'default':
                            if st.button("🗑️ Удалить домен", key=f"delete_domain_{current_site}_{domain}", type="secondary"):
                                if dm.delete_domain(domain):
                                    st.success(f"✅ Домен '{display_name}' удален")
                                    st.rerun()
                                else:
                                    st.error("❌ Ошибка удаления")
                        else:
                            st.caption("🔒 Защищенный домен (нельзя удалить)")

        st.markdown("---")
        st.subheader("➕ Создать новый домен")

        col1, col2 = st.columns(2)
        with col1:
            new_domain_name = st.text_input(
                "Имя домена (латиницей)",
                placeholder="например: europe, usa, asia",
                key="new_domain_name_input"
            )
        with col2:
            new_domain_display = st.text_input(
                "Отображаемое имя",
                placeholder="например: Европа, США, Азия",
                key="new_domain_display_input"
            )

        new_domain_desc = st.text_area(
            "Описание",
            placeholder="Краткое описание домена",
            key="new_domain_desc_input"
        )

        st.markdown("### 📦 Настройка блоков (фаза 3)")
        copy_blocks_choice = st.radio(
            "Что делать с блоками?",
            options=[
                "📋 Скопировать блоки из домена default",
                "🆕 Создать пустые блоки (с нуля)"
            ],
            key="copy_blocks_choice",
            help="Если выберете 'Скопировать' - будут использованы существующие блоки из default. Если 'Создать пустые' - начнёте с чистого листа."
        )

        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            if st.button("➕ Создать домен", key="create_domain_btn", use_container_width=True):
                if new_domain_name and new_domain_name.strip():
                    system_name = new_domain_name.strip().lower()
                    system_name = system_name.replace(' ', '_')
                    import re
                    system_name = re.sub(r'[^a-z0-9_]', '', system_name)

                    if not system_name:
                        st.error("❌ Некорректное имя домена")
                    elif not dm.domain_exists(system_name):
                        copy_blocks = copy_blocks_choice.startswith("📋")

                        dm._create_domain_from_default(system_name, copy_blocks=copy_blocks)

                        if copy_blocks:
                            import shutil
                            source_blocks = Path(f"sites/{current_site}/domains/default/blocks")
                            target_blocks = Path(f"sites/{current_site}/domains/{system_name}/blocks")

                            if source_blocks.exists():
                                if target_blocks.exists():
                                    shutil.rmtree(target_blocks)
                                shutil.copytree(source_blocks, target_blocks)
                                st.success(f"✅ Папка blocks скопирована из default")
                            else:
                                st.warning(f"⚠️ Папка blocks не найдена в default")

                        config = dm.get_domain_config(system_name)
                        config['display_name'] = new_domain_display or new_domain_name.capitalize()
                        config['description'] = new_domain_desc or f"Домен {new_domain_name}"
                        config['blocks_copied'] = copy_blocks

                        config_path = dm.domains_dir / system_name / "config.json"
                        with open(config_path, 'w', encoding='utf-8') as f:
                            json.dump(config, f, ensure_ascii=False, indent=2)

                        dm.set_current_domain(system_name)
                        st.success(f"✅ Домен '{new_domain_name}' создан")
                        st.rerun()
                    else:
                        st.error(f"❌ Домен '{system_name}' уже существует")
                else:
                    st.error("❌ Введите имя домена")

        with col_btn2:
            # ИСПРАВЛЕНО: переменная system_name определена здесь
            if st.button("🔄 Сделать активным", key="activate_domain_btn", use_container_width=True):
                if new_domain_name and new_domain_name.strip():
                    system_name = new_domain_name.strip().lower()
                    system_name = system_name.replace(' ', '_')
                    import re
                    system_name = re.sub(r'[^a-z0-9_]', '', system_name)

                    if dm.domain_exists(system_name):
                        dm.set_current_domain(system_name)
                        st.success(f"✅ Домен '{new_domain_display or system_name}' активирован")
                        st.rerun()
                    else:
                        st.error(f"❌ Домен '{system_name}' не существует")
                else:
                    st.error("❌ Введите имя домена для активации")

        st.markdown("---")

        current_domain = dm.get_current_domain()
        current_domain_display = dm.get_domain_display_name(current_domain)
        st.success(f"🔆 **Активный домен:** {current_domain_display} ({current_domain})")

        if st.button("← Назад к работе", use_container_width=True):
            st.session_state.show_site_manager = False
            st.rerun()