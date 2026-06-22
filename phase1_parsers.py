# phase1_parsers.py
"""Парсеры для фазы 1 - обработка входных данных разных типов"""

import streamlit as st
from collections import defaultdict
from typing import Dict, List, Any, Tuple

def is_empty_value(val):
    """Проверка на пустое значение"""
    if val is None:
        return True
    if isinstance(val, (int, float)):
        return False
    val_str = str(val).strip()
    if not val_str:
        return True
    empty_patterns = ["", "null", "none", "nan", "undefined", "нет", "не указано", "-", "—", "n/a"]
    return val_str.lower() in empty_patterns

def normalize_string(s):
    """Нормализация строки"""
    if not isinstance(s, str):
        return s
    return ' '.join(s.split())

def get_nested_value(data: Dict, path: List[str]):
    """Получить значение по пути в словаре"""
    current = data
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current

class BaseParser:
    """Базовый класс для парсеров"""

    def parse(self, raw_data: Dict, black_list: List[str], config: Dict) -> Tuple[List[Dict], Dict]:
        """
        Парсит данные и возвращает характеристики и дубликаты

        Returns:
            (processed_chars, duplicate_names)
        """
        raise NotImplementedError


class SteelBorgParser(BaseParser):
    """Парсер для SteelBorg структуры (характеристики товаров)"""

    def parse(self, raw_data: Dict, black_list: List[str], config: Dict) -> Tuple[List[Dict], Dict]:
        # Получаем конфигурацию
        category_field = config.get('category_field', ['ПараметрыТовара', 'Наименование'])
        items_field = config.get('items_field', ['Товары'])
        characteristics_field = config.get('characteristics_field', ['ПараметрыТовара', 'Характеристики'])
        char_id_field = config.get('char_id_field', 'ID')
        char_name_field = config.get('char_name_field', 'Наименование')
        char_unit_field = config.get('char_unit_field', 'ЕдиницаИзмеренияХарактеристики')
        char_priority_field = config.get('char_priority_field', 'ПриоритетВИмени')
        char_extra_field = config.get('char_extra_field', 'ДополнительнаяХарактеристика')
        offers_fields = config.get('offers_fields', ["9000048005", "9000048006", "Всего предложений"])
        value_path = config.get('value_in_items_path', ['Характеристики'])

        # Получаем характеристики из конфигурации
        params_info = get_nested_value(raw_data, characteristics_field) or []
        items = get_nested_value(raw_data, items_field) or []

        char_map = {}
        name_to_ids = defaultdict(list)

        # Инициализация карты характеристик
        for char in params_info:
            char_id = char.get(char_id_field)
            if not char_id:
                continue
            char_name = char.get(char_name_field, '')
            char_map[char_id] = {
                "name": char_name,
                "original_name": char_name,
                "is_extra": bool(char.get(char_extra_field, 0)),
                "unit": char.get(char_unit_field, ""),
                "priority": char.get(char_priority_field, 0),
                "values": defaultdict(lambda: {"items": set(), "offers": 0}),
                "items_with_char": set(),
                "had_split": False,
                "split_examples": []
            }
            name_to_ids[char_name].append(char_id)

        total_items = len(items)

        # Сбор значений
        for item_idx, item in enumerate(items):
            # Получаем характеристики товара по пути
            item_chars = get_nested_value(item, value_path) or {}

            # Подсчет предложений
            offers_count = 0
            for key in offers_fields:
                if key in item_chars:
                    try:
                        offers_count = int(item_chars[key])
                        break
                    except (ValueError, TypeError):
                        pass

            # Обработка каждой характеристики
            for c_id, raw_val in item_chars.items():
                if c_id in offers_fields:
                    continue
                if c_id not in char_map:
                    continue
                if is_empty_value(raw_val):
                    continue

                val_str = str(raw_val).strip()

                # Разбиваем по ", "
                if ", " in val_str:
                    parts = [p.strip() for p in val_str.split(", ") if p.strip()]
                    if len(parts) > 1:
                        char_map[c_id]["had_split"] = True
                        if len(char_map[c_id]["split_examples"]) < 3:
                            char_map[c_id]["split_examples"].append(val_str)
                else:
                    parts = [val_str]

                for part in parts:
                    if not part:
                        continue
                    char_map[c_id]["values"][part]["items"].add(item_idx)
                    char_map[c_id]["items_with_char"].add(item_idx)
                    char_map[c_id]["values"][part]["offers"] += offers_count

        # Формирование результата
        result = []
        duplicate_names = {name: ids for name, ids in name_to_ids.items() if len(ids) > 1}

        for c_id, info in char_map.items():
            is_in_black_list = (c_id in black_list) or (info["name"] in black_list)

            items_with_char_count = len(info["items_with_char"])
            fill_rate = (items_with_char_count / total_items) * 100 if total_items > 0 else 0

            values_data_formatted = {}
            for val, stats in info["values"].items():
                items_count = len(stats["items"])
                values_data_formatted[val] = {
                    "count": items_count,
                    "offers": stats["offers"]
                }

            is_duplicate = info["name"] in duplicate_names

            result.append({
                "id": c_id,
                "name": info["name"],
                "original_name": info["original_name"],
                "is_extra": info["is_extra"],
                "unit": info["unit"],
                "priority": info["priority"],
                "fill_rate": fill_rate,
                "items_with_char_count": items_with_char_count,
                "total_items": total_items,
                "values_data": values_data_formatted,
                "in_black_list": is_in_black_list,
                "is_duplicate": is_duplicate,
                "duplicate_ids": duplicate_names.get(info["name"], []),
                "had_split": info.get("had_split", False),
                "split_examples": info.get("split_examples", [])
            })

        return result, duplicate_names


class KeywordsParser(BaseParser):
    """Парсер для ключевых слов (MTT)"""

    def parse(self, raw_data: Dict, black_list: List[str], config: Dict) -> Tuple[List[Dict], Dict]:
        category_field = config.get('category_field', ['category', 'name'])
        items_field = config.get('items_field', ['articles'])
        keywords_field = config.get('keywords_field', ['keywords'])

        category = get_nested_value(raw_data, category_field) or "Без категории"
        items = get_nested_value(raw_data, items_field) or []

        # Собираем все ключевые слова
        keyword_counts = defaultdict(int)
        keyword_items = defaultdict(set)

        for item_idx, item in enumerate(items):
            keywords = get_nested_value(item, keywords_field) or []
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',')]

            for keyword in keywords:
                if keyword and keyword not in black_list:
                    keyword_counts[keyword] += 1
                    keyword_items[keyword].add(item_idx)

        total_items = len(items)

        # Формируем результат в формате, совместимом с фазой 1
        result = []
        for idx, (keyword, count) in enumerate(sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)):
            fill_rate = (count / total_items) * 100 if total_items > 0 else 0

            result.append({
                "id": f"kw_{idx}",
                "name": keyword,
                "original_name": keyword,
                "is_extra": False,
                "unit": "",
                "priority": 0,
                "fill_rate": fill_rate,
                "items_with_char_count": count,
                "total_items": total_items,
                "values_data": {keyword: {"count": count, "offers": 0}},
                "in_black_list": keyword in black_list,
                "is_duplicate": False,
                "duplicate_ids": [],
                "had_split": False,
                "split_examples": []
            })

        return result, {}


class NewsParser(BaseParser):
    """Парсер для новостей (MTT)"""

    def parse(self, raw_data: Dict, black_list: List[str], config: Dict) -> Tuple[List[Dict], Dict]:
        category_field = config.get('category_field', ['category'])
        items_field = config.get('items_field', ['news_items'])
        source_field = config.get('source_field', ['source'])

        category = get_nested_value(raw_data, category_field) or "Новости"
        items = get_nested_value(raw_data, items_field) or []

        # Анализируем источники
        source_counts = defaultdict(int)

        for item in items:
            source = get_nested_value(item, source_field) or "Неизвестно"
            if source not in black_list:
                source_counts[source] += 1

        total_items = len(items)

        result = []
        for idx, (source, count) in enumerate(source_counts.items()):
            fill_rate = (count / total_items) * 100 if total_items > 0 else 0

            result.append({
                "id": f"src_{idx}",
                "name": source,
                "original_name": source,
                "is_extra": False,
                "unit": "",
                "priority": 0,
                "fill_rate": fill_rate,
                "items_with_char_count": count,
                "total_items": total_items,
                "values_data": {source: {"count": count, "offers": 0}},
                "in_black_list": source in black_list,
                "is_duplicate": False,
                "duplicate_ids": [],
                "had_split": False,
                "split_examples": []
            })

        return result, {}


def get_parser(parser_type: str):
    """Фабрика парсеров"""
    parsers = {
        "steelborg": SteelBorgParser(),
        "keywords": KeywordsParser(),
        "news": NewsParser()
    }
    return parsers.get(parser_type, SteelBorgParser())