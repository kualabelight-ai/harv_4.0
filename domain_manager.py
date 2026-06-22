import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import streamlit as st


class DomainManager:
    def __init__(self, site_name: str = None):
        self.site_name = site_name or st.session_state.get('current_site', 'steelborg')
        self.sites_dir = Path("sites")
        self.site_dir = self.sites_dir / self.site_name
        self.domains_dir = self.site_dir / "domains"
        self.domains_dir.mkdir(parents=True, exist_ok=True)

        # ✅ НЕ СТАВИМ DEFAULT! Пусть читает из файла через get_current_domain
        # if 'selected_domain' not in st.session_state:
        #     st.session_state.selected_domain = 'default'  ← УДАЛИТЬ!

    def _get_user_settings_path(self, user_id: int) -> Path:
        """Путь к файлу настроек пользователя - В КОРНЕ sites/users"""
        return self.sites_dir / "users" / str(user_id) / "settings.json"

    def save_user_settings(self, user_id: int, data: Dict) -> bool:
        """Сохраняет настройки пользователя"""
        settings_file = self._get_user_settings_path(user_id)
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        print(f"   📝 СОХРАНЯЕМ В: {settings_file}")

        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"   ✅ Настройки сохранены: {settings_file}")
            return True
        except Exception as e:
            print(f"   ❌ Ошибка сохранения: {e}")
            return False
    def load_user_settings(self, user_id: int) -> Dict:
        """Загружает настройки пользователя"""
        settings_file = self._get_user_settings_path(user_id)

        print(f"   📂 ЗАГРУЖАЕМ ИЗ: {settings_file}")

        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"   ✅ Загружено: {data}")
                    return data
            except Exception as e:
                print(f"   ⚠️ Ошибка загрузки: {e}")

        return {
            'selected_domain': 'default',
            'selected_site': 'steelborg',
            'updated_at': datetime.now().isoformat()
        }

    def set_current_domain(self, system_name: str):
        print(f"🔄 set_current_domain: site={self.site_name}, new_domain={system_name}")

        if not self.domain_exists(system_name):
            print(f"⚠️ Домен {system_name} не существует, создаем...")
            self._create_domain_from_default(system_name, copy_blocks=True)

        st.session_state.selected_domain = system_name
        st.session_state.current_domain = system_name
        st.session_state[f'domain_system_{self.site_name}'] = system_name

        user_id = st.session_state.get('user_id')
        if user_id:
            self.save_user_settings(user_id, {
                'selected_domain': system_name,
                'selected_site': self.site_name,
                'updated_at': datetime.now().isoformat()
            })
            print(f"💾 Домен {system_name} сохранен для пользователя {user_id}")

    # domain_manager.py - ЗАМЕНИТЬ МЕТОД get_current_domain

    def get_current_domain(self) -> str:
        """Возвращает домен - СНАЧАЛА ИЗ ФАЙЛА ПОЛЬЗОВАТЕЛЯ, ПОТОМ ИЗ session_state"""
        user_id = st.session_state.get('user_id')

        # ✅ СНАЧАЛА ПРОВЕРЯЕМ ФАЙЛ
        if user_id:
            settings = self.load_user_settings(user_id)
            domain = settings.get('selected_domain')
            if domain and self.domain_exists(domain):
                print(f"🔍 get_current_domain: site={self.site_name}, domain={domain} (из файла users)")
                return domain

        # ✅ ПОТОМ session_state
        domain = st.session_state.get('selected_domain')
        if domain:
            print(f"🔍 get_current_domain: site={self.site_name}, domain={domain} (из selected_domain)")
            return domain

        domain = st.session_state.get('current_domain')
        if domain:
            print(f"🔍 get_current_domain: site={self.site_name}, domain={domain} (из current_domain)")
            return domain

        domain = st.session_state.get(f'domain_system_{self.site_name}')
        if domain:
            print(f"🔍 get_current_domain: site={self.site_name}, domain={domain} (из domain_system)")
            return domain

        print(f"🔍 get_current_domain: site={self.site_name}, domain=default (default)")
        return 'default'

    def get_available_domains(self) -> List[str]:
        if not self.domains_dir.exists():
            return []
        domains = []
        for domain_dir in self.domains_dir.iterdir():
            if domain_dir.is_dir() and (domain_dir / "config.json").exists():
                domains.append(domain_dir.name)
        return sorted(domains)

    def domain_exists(self, domain_name: str) -> bool:
        return (self.domains_dir / domain_name / "config.json").exists()

    def get_domain_display_name(self, domain_name: str = None) -> str:
        if domain_name is None:
            domain_name = self.get_current_domain()
        config = self.get_domain_config(domain_name)
        return config.get("display_name", domain_name.capitalize())

    def get_domain_config(self, domain_name: str = None) -> Dict:
        if domain_name is None:
            domain_name = self.get_current_domain()
        config_path = self.domains_dir / domain_name / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        if domain_name != 'default':
            return self._create_domain_from_default(domain_name)
        return self._create_default_domain()

    def _create_default_domain(self) -> Dict:
        default_dir = self.domains_dir / "default"
        default_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "domain_name": "default",
            "display_name": "СНГ (дефолтный)",
            "system_name": "default",
            "description": "Дефолтный домен для СНГ",
            "created_at": datetime.now().isoformat(),
            "based_on": None,
            "phases": {
                "phase1": {"data_file": "phase1_data.json"},
                "phase2": {"data_file": "phase2_data.json"},
                "phase3": {"blocks_file": "phase3_blocks.json", "custom_blocks_allowed": True},
                "phase4": {"prompts_file": "phase4_prompts.json"},
                "phase5": {"texts_file": "phase5_texts.json"},
                "phase6": {"synonyms_file": "phase6_synonyms.json"},
                "phase7": {"final_file": "phase7_final.json"}
            }
        }
        phases_dir = default_dir / "phases"
        phases_dir.mkdir(exist_ok=True)
        for phase_config in config["phases"].values():
            for file_key in ["data_file", "blocks_file", "prompts_file", "texts_file", "synonyms_file", "final_file"]:
                if file_key in phase_config:
                    file_path = phases_dir / phase_config[file_key]
                    if not file_path.exists():
                        if "blocks" in phase_config[file_key]:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                json.dump({}, f)
                        elif "prompts" in phase_config[file_key]:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                json.dump([], f)
                        else:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                json.dump({}, f)
        with open(default_dir / "config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return config

    def _create_domain_from_default(self, domain_name: str, copy_blocks: bool = False) -> Dict:
        import re
        system_name = domain_name.lower().strip()
        system_name = system_name.replace(' ', '_')
        system_name = re.sub(r'[^a-z0-9_]', '', system_name)
        if not system_name:
            system_name = "new_domain"
        new_domain_dir = self.domains_dir / system_name
        if new_domain_dir.exists():
            shutil.rmtree(new_domain_dir)
        new_domain_dir.mkdir(parents=True, exist_ok=True)
        phases_dir = new_domain_dir / "phases"
        phases_dir.mkdir(exist_ok=True)
        if copy_blocks:
            source_blocks = self.domains_dir / "default" / "blocks"
            target_blocks = new_domain_dir / "blocks"
            if source_blocks.exists():
                if target_blocks.exists():
                    shutil.rmtree(target_blocks)
                shutil.copytree(source_blocks, target_blocks)
            else:
                target_blocks.mkdir(parents=True, exist_ok=True)
        else:
            blocks_dir = new_domain_dir / "blocks"
            blocks_dir.mkdir(parents=True, exist_ok=True)
        for phase_file in ["phase1_data.json", "phase2_data.json", "phase3_blocks.json",
                           "phase4_prompts.json", "phase5_texts.json", "phase6_synonyms.json",
                           "phase7_final.json"]:
            with open(phases_dir / phase_file, 'w', encoding='utf-8') as f:
                json.dump({} if phase_file != "phase4_prompts.json" else [], f)
        config = {
            "domain_name": system_name,
            "system_name": system_name,
            "display_name": domain_name,
            "description": f"Домен {domain_name}",
            "created_at": datetime.now().isoformat(),
            "blocks_copied": copy_blocks,
            "phases": {
                "phase1": {"data_file": "phase1_data.json"},
                "phase2": {"data_file": "phase2_data.json"},
                "phase3": {"blocks_file": "phase3_blocks.json"},
                "phase4": {"prompts_file": "phase4_prompts.json"},
                "phase5": {"texts_file": "phase5_texts.json"},
                "phase6": {"synonyms_file": "phase6_synonyms.json"},
                "phase7": {"final_file": "phase7_final.json"}
            }
        }
        with open(new_domain_dir / "config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return config

    def get_domain_config_file(self, domain_name: str = None) -> Path:
        if domain_name is None:
            domain_name = self.get_current_domain()
        return self.domains_dir / domain_name / "domain_config.json"

    def load_domain_config(self, domain_name: str = None) -> Dict:
        if domain_name is None:
            domain_name = self.get_current_domain()
        config_path = self.get_domain_config_file(domain_name)
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self._get_default_domain_config()

    def _get_default_domain_config(self) -> Dict:
        return {
            "phase7": {
                "non_characteristic_blocks": [
                    "заголовок", "описание", "заключение_текст", "заключение_список",
                    "применение_текст", "применение_список", "производство", "технология"
                ],
                "template_patterns": [
                    ["заголовок", "описание", "характеристики", "заключение_текст"]
                ],
                "postprocessing_rules": {
                    "remove_units": True,
                    "punctuation_fix": True,
                    "city_variable_fix": True
                }
            }
        }

    def get_phase_config(self, phase: int, domain_name: str = None) -> Dict:
        config = self.load_domain_config(domain_name)
        return config.get(f"phase{phase}", {})

    def get_phase_file_path(self, phase: int, domain_name: str = None) -> Path:
        if domain_name is None:
            domain_name = self.get_current_domain()
        config = self.get_domain_config(domain_name)
        phase_key = f"phase{phase}"
        phase_config = config.get("phases", {}).get(phase_key, {})
        phase_files = {
            1: phase_config.get("data_file", "phase1_data.json"),
            2: phase_config.get("data_file", "phase2_data.json"),
            3: phase_config.get("blocks_file", "phase3_blocks.json"),
            4: phase_config.get("prompts_file", "phase4_prompts.json"),
            5: phase_config.get("texts_file", "phase5_texts.json"),
            6: phase_config.get("synonyms_file", "phase6_synonyms.json"),
            7: phase_config.get("final_file", "phase7_final.json")
        }
        filename = phase_files.get(phase, f"phase{phase}_data.json")
        return self.domains_dir / domain_name / "phases" / filename

    def save_phase_data(self, phase: int, data: any, domain_name: str = None):
        if domain_name is None:
            domain_name = self.get_current_domain()
        file_path = self.get_phase_file_path(phase, domain_name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return True

    def load_phase_data(self, phase: int, domain_name: str = None):
        if domain_name is None:
            domain_name = self.get_current_domain()
        file_path = self.get_phase_file_path(phase, domain_name)
        if not file_path.exists():
            return [] if phase == 4 else {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return [] if phase == 4 else {}

    def get_templates(self, category_code: str = None, domain_name: str = None) -> Dict:
        """Возвращает шаблоны для указанной категории из domain_config.json"""
        if domain_name is None:
            domain_name = self.get_current_domain()

        # ✅ ПРАВИЛЬНЫЙ ПУТЬ: sites/{site}/domains/{domain}/domain_config.json
        config_file = self.domains_dir / domain_name / "domain_config.json"

        if not config_file.exists():
            return {} if category_code else {}

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Шаблоны хранятся в секции "templates" или "phase7_templates"
            templates = config.get("templates", {}) or config.get("phase7_templates", {})

            if category_code:
                return templates.get(category_code, {})
            return templates
        except Exception as e:
            print(f"❌ Ошибка загрузки шаблонов: {e}")
            return {} if category_code else {}

    def save_templates(self, templates: Dict, category_code: str = None, domain_name: str = None):
        """Сохраняет шаблоны в domain_config.json"""
        if domain_name is None:
            domain_name = self.get_current_domain()

        config_file = self.domains_dir / domain_name / "domain_config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Загружаем существующий конфиг
        config = {}
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                pass

        # Обновляем шаблоны
        if "templates" not in config:
            config["templates"] = {}

        if category_code:
            config["templates"][category_code] = templates
        else:
            config["templates"] = templates

        # Сохраняем
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        print(f"✅ Сохранено {len(templates)} шаблонов в domain_config.json для категории {category_code}")

    def add_template(self, category_code: str, template_name: str, template_order: List[str],
                     description: str = "", is_default: bool = False, domain_name: str = None):
        templates = self.get_templates(category_code, domain_name)
        templates[template_name] = {
            "name": template_name,
            "order": template_order,
            "description": description,
            "is_default": is_default
        }
        if is_default:
            for name, tpl in templates.items():
                if name != template_name:
                    tpl["is_default"] = False
        self.save_templates(templates, category_code, domain_name)

    def delete_template(self, category_code: str, template_name: str, domain_name: str = None):
        templates = self.get_templates(category_code, domain_name)
        if template_name in templates:
            was_default = templates[template_name].get("is_default", False)
            del templates[template_name]
            if was_default and templates:
                first_name = next(iter(templates.keys()))
                templates[first_name]["is_default"] = True
            self.save_templates(templates, category_code, domain_name)

    def get_default_template(self, category_code: str, domain_name: str = None) -> Optional[Dict]:
        templates = self.get_templates(category_code, domain_name)
        for name, tpl in templates.items():
            if tpl.get("is_default", False):
                return {"name": name, **tpl}
        if templates:
            first_name = next(iter(templates.keys()))
            return {"name": first_name, **templates[first_name]}
        return None

    def get_currency_settings(self, domain_name: str = None) -> Dict:
        if domain_name is None:
            domain_name = self.get_current_domain()
        config = self.get_domain_config(domain_name)
        if "currency" in config:
            return config["currency"]
        default_currency = {
            "symbol": "₽",
            "code": "RUB",
            "name": "руб.",
            "position": "after",
            "decimal_separator": ",",
            "thousands_separator": " "
        }
        if domain_name == "kz":
            default_currency = {
                "symbol": "₸",
                "code": "KZT",
                "name": "тенге",
                "position": "after",
                "decimal_separator": ",",
                "thousands_separator": " "
            }
        elif domain_name == "by":
            default_currency = {
                "symbol": "Br",
                "code": "BYN",
                "name": "бел. руб.",
                "position": "after",
                "decimal_separator": ",",
                "thousands_separator": " "
            }
        elif domain_name in ["eu", "europe"]:
            default_currency = {
                "symbol": "€",
                "code": "EUR",
                "name": "евро",
                "position": "before",
                "decimal_separator": ",",
                "thousands_separator": " "
            }
        return default_currency

    def update_currency_settings(self, currency_settings: Dict, domain_name: str = None):
        if domain_name is None:
            domain_name = self.get_current_domain()
        config = self.get_domain_config(domain_name)
        config["currency"] = currency_settings
        config_path = self.domains_dir / domain_name / "config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def get_price_variable(self, domain_name: str = None) -> str:
        currency = self.get_currency_settings(domain_name)
        symbol = currency["symbol"]
        position = currency.get("position", "after")
        if position == "before":
            return f"{symbol}{{system цена_товара}}"
        else:
            return f"{{system цена_товара}} {symbol}"

    def get_current_domain_display(self) -> str:
        current_system = self.get_current_domain()
        config = self.get_domain_config(current_system)
        return config.get('display_name', current_system.capitalize())

    def delete_domain(self, domain_name: str) -> bool:
        if domain_name == 'default':
            return False
        domain_dir = self.domains_dir / domain_name
        if domain_dir.exists():
            shutil.rmtree(domain_dir)
            return True
        return False


def render_domain_selector(phase: int = None, key_suffix: str = "") -> str:
    import time
    from datetime import datetime

    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    all_domains = dm.get_available_domains()

    current_site = st.session_state.get('current_site', 'steelborg')
    current_domain = st.session_state.get('current_domain', 'default')
    user_id = st.session_state.get('user_id')

    domain_options = {}
    for d in all_domains:
        display_name = dm.get_domain_display_name(d)
        domain_options[display_name] = d

    current_display = dm.get_domain_display_name(current_domain)

    selector_key = f"domain_selector_{phase}_{key_suffix}"

    state_key = f"domain_selector_selected_{phase}_{key_suffix}"
    if state_key not in st.session_state:
        st.session_state[state_key] = current_display

    options_list = list(domain_options.keys())

    if st.session_state[state_key] not in options_list:
        st.session_state[state_key] = current_display

    default_index = options_list.index(st.session_state[state_key]) if st.session_state[
                                                                           state_key] in options_list else 0

    selected_display = st.selectbox(
        "🌐 Выберите домен/регион",
        options=options_list,
        index=default_index,
        key=selector_key
    )

    st.session_state[state_key] = selected_display
    selected_domain = domain_options[selected_display]

    if selected_domain != current_domain:
        st.info(f"📌 Выбран домен: **{selected_display}**. Нажмите 'Подтвердить' для переключения.")
    else:
        st.success(f"✅ Текущий домен: **{current_display}**")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("✅ Подтвердить выбор домена", use_container_width=True, type="primary",
                     key=f"confirm_domain_{phase}_{key_suffix}"):

            if selected_domain != current_domain:
                if not user_id:
                    st.error("❌ Нет user_id")
                    return selected_domain

                settings_data = {
                    'selected_domain': selected_domain,
                    'selected_site': current_site,
                    'updated_at': datetime.now().isoformat()
                }

                if dm.save_user_settings(user_id, settings_data):
                    print(f"   ✅ Настройки сохранены")

                # ✅ ОБНОВЛЯЕМ session_state
                st.session_state.current_domain = selected_domain
                st.session_state.selected_domain = selected_domain
                st.session_state.current_site = current_site
                st.session_state.selected_site = current_site
                st.session_state[f'domain_system_{current_site}'] = selected_domain

                st.success(f"✅ Переключено на домен: {selected_display}")
                time.sleep(0.5)
                st.rerun()
            else:
                st.warning("⚠️ Вы уже на этом домене")

    return selected_domain