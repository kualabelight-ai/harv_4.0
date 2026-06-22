# domain_utils.py
"""
Утилиты для работы с доменами - ЕДИНЫЙ ИСТОЧНИК ПРАВДЫ
"""

import streamlit as st
from pathlib import Path
from typing import Optional, Tuple

def get_current_domain_from_file(site_name: str = None) -> Tuple[str, str]:
    """
    Возвращает (site_name, domain_name) ИЗ ФАЙЛА конфигурации
    НЕ ТРОГАЕТ session_state!
    """
    if site_name is None:
        site_name = st.session_state.get('current_site', 'steelborg')

    config_file = Path(f"sites/{site_name}/current_domain.txt")
    domain = 'default'

    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                saved = f.read().strip()
                if saved:
                    # Проверяем, существует ли такой домен
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
    - Если нет проекта - берем домен из файла конфигурации сайта
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

    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager(site)
    else:
        dm = st.session_state.domain_manager
        if dm.site_name != site:
            st.session_state.domain_manager = DomainManager(site)

    dm = st.session_state.domain_manager
    dm.set_current_domain(domain)

    st.session_state.current_site = site
    st.session_state.current_domain = domain

    print(f"✅ Домен синхронизирован с конфигом: {site}/{domain}")
    return True