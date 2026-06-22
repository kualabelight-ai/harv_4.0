# site_configs.py
"""Конфигурации сайтов и типов задач"""

SITE_CONFIGS = {
    "steelborg": {
        "name": "SteelBorg",
        "description": "Генерация контента для SteelBorg",
        "task_types": {
            "texts": {
                "name": "Описания товаров",
                "description": "Генерация описаний на основе характеристик",
                "pipeline": "steelborg_texts",
                "phases_enabled": [1, 2, 3, 4, 5, 6, 7],
                "phase1_config": {
                    "parser": "steelborg",
                    "input_type": "json",
                    "category_field": ["ПараметрыТовара", "Наименование"],
                    "items_field": ["Товары"],
                    "characteristics_field": ["ПараметрыТовара", "Характеристики"],
                    "char_id_field": "ID",
                    "char_name_field": "Наименование",
                    "char_unit_field": "ЕдиницаИзмеренияХарактеристики",
                    "char_priority_field": "ПриоритетВИмени",
                    "char_extra_field": "ДополнительнаяХарактеристика",
                    "offers_fields": ["9000048005", "9000048006", "Всего предложений", "Предложения", "Количество предложений"],
                    "value_in_items_path": ["Характеристики"]  # путь к значениям в товаре
                },
                "phase2_config": {
                    "enabled": True,
                    "default_markers": ["Важно", "Внимание", "Рекомендуем"]
                }
            },
            "faq": {
                "name": "FAQ",
                "description": "Генерация FAQ на основе характеристик",
                "pipeline": "steelborg_faq",
                "phases_enabled": [1, 3, 4, 5, 6, 7],
                "phase1_config": {
                    "parser": "steelborg",
                    "input_type": "json",
                    "category_field": ["ПараметрыТовара", "Наименование"],
                    "items_field": ["Товары"],
                    "characteristics_field": ["ПараметрыТовара", "Характеристики"],
                    "char_id_field": "ID",
                    "char_name_field": "Наименование"
                }
            }
        }
    },
    "mtt": {
        "name": "MTT",
        "description": "Генерация контента для MTT",
        "task_types": {
            "articles": {
                "name": "Статьи",
                "description": "Генерация статей по ключевым словам",
                "pipeline": "mtt_articles",
                "phases_enabled": [1, 3, 4, 5, 6, 7],
                "phase1_config": {
                    "parser": "keywords",
                    "input_type": "json",
                    "category_field": ["category", "name"],
                    "items_field": ["articles"],
                    "keywords_field": ["keywords"],
                    "title_field": ["title"]
                }
            },
            "news": {
                "name": "Новости",
                "description": "Генерация новостных заметок",
                "pipeline": "mtt_news",
                "phases_enabled": [1, 3, 4, 5, 6, 7],
                "phase1_config": {
                    "parser": "news",
                    "input_type": "json",
                    "category_field": ["category"],
                    "items_field": ["news_items"],
                    "source_field": ["source"]
                }
            }
        }
    }
}

def get_site_config(site_id: str):
    """Получить конфигурацию сайта"""
    return SITE_CONFIGS.get(site_id)

def get_task_config(site_id: str, task_type: str):
    """Получить конфигурацию задачи"""
    site = SITE_CONFIGS.get(site_id)
    if site:
        return site.get("task_types", {}).get(task_type)
    return None

def get_available_sites():
    """Получить список доступных сайтов"""
    return [(site_id, config["name"]) for site_id, config in SITE_CONFIGS.items()]

def get_available_tasks(site_id: str):
    """Получить список доступных задач для сайта"""
    site = SITE_CONFIGS.get(site_id)
    if site:
        return [(task_id, config["name"]) for task_id, config in site["task_types"].items()]
    return []