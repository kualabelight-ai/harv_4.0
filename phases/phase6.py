

# phase6_synonymizer.py
# -*- coding: utf-8 -*-
"""
Фаза 6: Синонимизация текстов
Полноценный синонимайзер с грамматической адаптацией
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def _get_context_data(context, st_session):
    """
    Возвращает данные контекста.
    Приоритет: context > st.session_state
    """
    if context is not None:
        return {
            'user_id': context.user_id,
            'project_id': context.project_id,
            'site_name': context.site_name,
            'domain_name': context.domain_name,
            'project_name': context.data.get('project_name', 'Новый проект'),
            'category': context.data.get('category', ''),
            'app_data': context.data,
            'has_context': True
        }
    else:
        return {
            'user_id': st_session.get('user_id'),
            'project_id': st_session.get('current_project_id'),
            'site_name': st_session.get('current_site', 'steelborg'),
            'domain_name': st_session.get('current_domain', 'default'),
            'project_name': st_session.get('project_name', 'Новый проект'),
            'category': st_session.get('category', ''),
            'app_data': st_session.get('app_data', {}),
            'has_context': False
        }
import json
import re
import random
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import shutil
import streamlit as st
import pandas as pd
from styles import load_css
from domain_manager import DomainManager
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")



# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
def log(msg: str, level: str = "INFO"):
    """Логирование для отладки"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {level} | {msg}"
    print(log_line)

    if "phase6_logs" not in st.session_state:
        st.session_state.phase6_logs = []
    st.session_state.phase6_logs.append(log_line)
    if len(st.session_state.phase6_logs) > 100:
        st.session_state.phase6_logs = st.session_state.phase6_logs[-100:]
# phase6.py — добавить в начало файла после импортов



# ==================== ТИПЫ ДАННЫХ ====================
class ReplacementType(Enum):
    UNIGRAM = "unigram"
    BIGRAM = "bigram"
    TRIGRAM = "trigram"
    NGRAM = "ngram"
    PREPOSITIONAL = "prepositional"


@dataclass
class ReplacementInfo:
    """Информация о замене"""
    original: str
    new: str
    start: int
    end: int
    text_index: int
    type: ReplacementType
    lemma: str = ""
    used_synonym: str = ""
    skipped_reason: str = ""


@dataclass
class NGramInfo:
    """Информация о n-грамме"""
    text: str
    count: int
    length: int
    positions: List[Tuple[int, int, int]]
    replace: bool = True
    synonyms: List[str] = None
    forms: Dict[str, int] = None
    original_forms: List[str] = None
    has_prepositions: bool = False
    is_stopword: bool = False

    def __post_init__(self):
        if self.synonyms is None:
            self.synonyms = []
        if self.forms is None:
            self.forms = {}
        if self.original_forms is None:
            self.original_forms = []

    def to_dict(self) -> dict:
        """Конвертирует объект в JSON-сериализуемый словарь"""
        return {
            'text': self.text,
            'count': self.count,
            'length': self.length,
            'positions': self.positions,
            'replace': self.replace,
            'synonyms': self.synonyms,
            'forms': self.forms,
            'original_forms': self.original_forms,
            'has_prepositions': self.has_prepositions,
            'is_stopword': self.is_stopword
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'NGramInfo':
        """Восстанавливает объект из словаря"""
        return cls(
            text=data['text'],
            count=data['count'],
            length=data['length'],
            positions=data['positions'],
            replace=data.get('replace', True),
            synonyms=data.get('synonyms', []),
            forms=data.get('forms', {}),
            original_forms=data.get('original_forms', []),
            has_prepositions=data.get('has_prepositions', False),
            is_stopword=data.get('is_stopword', False)
        )


# ==================== КЛАСС ДЛЯ СОХРАНЕНИЯ ВЫБОРА (как SessionManager) ====================
class SelectionManager:
    def __init__(self, project_id: str = None, user_id: int = None,
                 site_name: str = None, domain_name: str = None,
                 context=None):
        """
        Выборы хранятся в папке ПРОЕКТА
        """
        # Получаем текущий проект, если не передан
        if project_id is None and context is not None:
            project_id = context.project_id
        elif project_id is None and 'current_project_id' in st.session_state:
            project_id = st.session_state.current_project_id

        if user_id is None and context is not None:
            user_id = context.user_id
        elif user_id is None and 'user_id' in st.session_state:
            user_id = st.session_state.user_id

        # Получаем сайт и домен
        if (site_name is None or domain_name is None) and context is not None:
            site_name = context.site_name
            domain_name = context.domain_name

        if (site_name is None or domain_name is None) and 'domain_manager' in st.session_state:
            dm = st.session_state.domain_manager
            site_name = dm.site_name
            domain_name = dm.get_current_domain()

        # ✅ Сохраняем в папку ПРОЕКТА
        if project_id and user_id and site_name and domain_name:
            selections_dir = Path(f"sites/{site_name}/domains/{domain_name}/projects/{user_id}/{project_id}")
            selections_dir.mkdir(parents=True, exist_ok=True)
            self.selection_file = selections_dir / "selections.json"
        else:
            # Fallback (не должно происходить в нормальной работе)
            self.selection_file = Path(f"temp_selections_{project_id}.json")

        self._load_selections()

    def _load_selections(self):
        """Загрузка выбора из файла проекта"""
        try:
            if self.selection_file.exists():
                with open(self.selection_file, "r", encoding="utf-8") as f:
                    self.selections = json.load(f)
                log(f"Загружен выбор из {self.selection_file}")
            else:
                self.selections = {}
        except Exception as e:
            log(f"Ошибка загрузки выбора: {e}", "ERROR")
            self.selections = {}

    def save_selections(self):
        """Сохранение выбора в файл проекта"""
        try:
            self.selection_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.selection_file, "w", encoding="utf-8") as f:
                json.dump(self.selections, f, ensure_ascii=False, indent=2)
            log(f"Выбор сохранен в {self.selection_file}")
        except Exception as e:
            log(f"Ошибка сохранения выбора: {e}", "ERROR")

    def get_selection(self, ngram_type: str, ngram: str, default: bool = False) -> bool:
        """Получить состояние выбора"""
        key = f"{ngram_type}:{ngram}"
        return self.selections.get(key, default)

    def set_selection(self, ngram_type: str, ngram: str, selected: bool):
        """Установить состояние выбора"""
        key = f"{ngram_type}:{ngram}"
        self.selections[key] = selected
        self.save_selections()

    def set_selections_batch(self, selections: Dict[str, bool]):
        """Массовое обновление выбора"""
        self.selections.update(selections)
        self.save_selections()

    def clear_selections(self):
        """Очистить весь выбор"""
        self.selections.clear()
        self.save_selections()


# ==================== МЕНЕДЖЕР СТОП-СЛОВ ====================
class StopWordManager:
    """Управление стоп-словами"""

    def __init__(self, syn_manager=None):
        self.syn_manager = syn_manager
        self.stop_words_file = "stop_words.json"
        self.stop_words = set()
        self.stop_word_synonyms = {}
        self._load_stop_words()

        try:
            import pymorphy3
            self.morph = pymorphy3.MorphAnalyzer()
        except ImportError:
            self.morph = None
            log("pymorphy3 не установлен", "WARNING")

    def _load_stop_words(self):
        """Загрузка стоп-слов из файла"""
        try:
            if os.path.exists(self.stop_words_file):
                with open(self.stop_words_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.stop_words = set(data.get("stop_words", []))
                    self.stop_word_synonyms = data.get("stop_word_synonyms", {})
            else:
                self.stop_words = {
                    "идеальный", "высококачественный", "лучший",
                    "превосходный", "отличный", "супер", "мега"
                }
                self._save_stop_words()
        except Exception as e:
            log(f"Ошибка загрузки стоп-слов: {e}", "ERROR")

    def _save_stop_words(self):
        """Сохранение стоп-слов"""
        try:
            data = {
                "stop_words": list(self.stop_words),
                "stop_word_synonyms": self.stop_word_synonyms
            }
            with open(self.stop_words_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(f"Ошибка сохранения стоп-слов: {e}", "ERROR")

    def is_stop_word(self, word: str) -> bool:
        """Проверка, является ли слово стоп-словом"""
        word_lower = word.lower()

        if word_lower in self.stop_words:
            return True

        if self.morph:
            try:
                parsed = self.morph.parse(word_lower)[0]
                lemma = parsed.normal_form.lower()
                if lemma in self.stop_words:
                    return True
            except:
                pass

        return False

    def is_preposition(self, word: str) -> bool:
        """Проверка, является ли слово предлогом"""
        prepositions = {'в', 'на', 'за', 'под', 'над', 'перед', 'при', 'с', 'к', 'у', 'о', 'об', 'по', 'из', 'от',
                        'до', 'без', 'для', 'через', 'между', 'сквозь', 'вокруг', 'около', 'возле'}
        return word.lower() in prepositions


# ==================== МЕНЕДЖЕР СИНОНИМОВ ====================
class FastSynonymManager:
    """Управление синонимами с кешированием"""

    def __init__(self, synonyms_file: str = "synonyms.json"):
        self.synonyms_file = synonyms_file
        self._data = None
        self._cache = {}
        self._load_data()

        self.grouper = SynonymGrouper(self)

    def _load_data(self):
        """Загрузка данных из файла - С ЗАЩИТОЙ ОТ ОШИБОК"""
        try:
            if os.path.exists(self.synonyms_file):
                with open(self.synonyms_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                log(f"Загружены синонимы из {self.synonyms_file}")
            else:
                self._create_default_structure()
                self._save()  # Сохраняем сразу

            # Гарантируем наличие всех секций
            required_sections = [
                "unigram_synonyms", "bigram_synonyms", "trigram_synonyms",
                "ngram_synonyms", "prepositional_synonyms",
                "active_synonyms", "specific_forms"
            ]
            for section in required_sections:
                if section not in self._data:
                    self._data[section] = {}
                    self._save()  # Сохраняем после добавления секции

        except json.JSONDecodeError as e:
            log(f"JSON ошибка в {self.synonyms_file}: {e}", "ERROR")

            # Создаём бэкап повреждённого файла
            backup_name = f"{self.synonyms_file}.corrupted_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                shutil.copy(self.synonyms_file, backup_name)
                log(f"Создан бэкап: {backup_name}")
            except:
                pass

            # СОЗДАЁМ НОВЫЙ ФАЙЛ (100% рабочий)
            log("Создаю новый файл синонимов...", "WARNING")
            self._create_default_structure()
            self._save()  # Сохраняем

            # Проверяем что создалось
            with open(self.synonyms_file, "r", encoding="utf-8") as f:
                self._data = json.load(f)

            log("✅ Новый файл создан успешно")

        except Exception as e:
            log(f"Ошибка загрузки синонимов: {e}", "ERROR")
            self._create_default_structure()
            self._save()

    def _create_default_structure(self):
        """Создание структуры по умолчанию"""
        self._data = {
            "unigram_synonyms": {},
            "bigram_synonyms": {},
            "trigram_synonyms": {},
            "ngram_synonyms": {},
            "prepositional_synonyms": {},
            "active_synonyms": {},
            "specific_forms": {}
        }

    def _save(self):
        """НЕМЕДЛЕННОЕ сохранение данных в файл"""
        try:
            with open(self.synonyms_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            log(f"Синонимы сохранены в {self.synonyms_file}")
        except Exception as e:
            log(f"Ошибка сохранения синонимов: {e}", "ERROR")

    def get_synonyms(self, ngram: str, ngram_type: ReplacementType) -> List[str]:
        """Получение синонимов для n-граммы"""
        cache_key = f"syns:{ngram_type.value}:{ngram.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        section = f"{ngram_type.value}_synonyms"
        synonyms = self._data.get(section, {}).get(ngram.lower(), [ngram])

        # Убеждаемся, что оригинал есть
        if ngram not in synonyms:
            synonyms.insert(0, ngram)

        if len(self._cache) < 10000:
            self._cache[cache_key] = synonyms.copy()

        return synonyms.copy()

    def get_active_synonyms(self, ngram: str, ngram_type: ReplacementType) -> List[str]:
        """Получение активных синонимов для замены"""
        cache_key = f"active:{ngram_type.value}:{ngram.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        all_synonyms = self.get_synonyms(ngram, ngram_type)
        key = f"{ngram_type.value}:{ngram.lower()}"
        active = self._data.get("active_synonyms", {}).get(key, [])

        if active:
            result = [s for s in active if s in all_synonyms]
            # ВСЕГДА добавляем оригинал в начало!
            if ngram not in result:
                result.insert(0, ngram)
            if not result:
                result = all_synonyms[:1]
        else:
            result = all_synonyms
            # Убеждаемся, что оригинал есть
            if ngram not in result:
                result.insert(0, ngram)

        if len(self._cache) < 10000:
            self._cache[cache_key] = result.copy()

        return result.copy()

    def set_active_synonyms(self, ngram: str, ngram_type: ReplacementType, active_synonyms: List[str]):
        """Установка активных синонимов"""
        key = f"{ngram_type.value}:{ngram.lower()}"
        self._data.setdefault("active_synonyms", {})[key] = active_synonyms

        cache_key = f"active:{ngram_type.value}:{ngram.lower()}"
        if cache_key in self._cache:
            del self._cache[cache_key]

        self._save()

    def add_synonyms(self, ngram: str, ngram_type: ReplacementType, synonyms: List[str]):
        """Добавление синонимов"""
        section = f"{ngram_type.value}_synonyms"
        if section not in self._data:
            self._data[section] = {}

        ngram_lower = ngram.lower()
        clean_synonyms = [s.strip() for s in synonyms if s.strip()]

        if ngram not in clean_synonyms:
            clean_synonyms.insert(0, ngram)

        self._data[section][ngram_lower] = clean_synonyms

        cache_keys = [k for k in self._cache if k.startswith(f"syns:{ngram_type.value}:{ngram_lower}") or
                      k.startswith(f"active:{ngram_type.value}:{ngram_lower}")]
        for key in cache_keys:
            del self._cache[key]

        self._save()
        log(f"Сохранены синонимы для {ngram}: {clean_synonyms}")

    def get_specific_form(self, original_phrase: str, synonym: str, ngram_type: ReplacementType) -> Optional[str]:
        """Получение конкретной формы замены"""
        key = f"{ngram_type.value}:{original_phrase.lower()}:{synonym.lower()}"
        return self._data.get("specific_forms", {}).get(key)

    def set_specific_form(self, original_phrase: str, synonym: str, replacement: str, ngram_type: ReplacementType):
        """Установка конкретной формы замены"""
        key = f"{ngram_type.value}:{original_phrase.lower()}:{synonym.lower()}"
        self._data.setdefault("specific_forms", {})[key] = replacement
        self._save()

    def get_all_forms(self) -> Dict:
        """Получить все конкретные формы"""
        return self._data.get("specific_forms", {}).copy()

    def set_all_forms(self, forms: Dict):
        """Установить все конкретные формы"""
        self._data["specific_forms"] = forms.copy()
        self._save()

    def get_unified_synonyms(self, word: str) -> List[str]:
        """Получить унифицированные синонимы из группы"""
        return self.grouper.get_unified_synonyms(word)


class SynonymGrouper:
    """Группировка синонимов"""

    def __init__(self, syn_manager: FastSynonymManager):
        self.syn_manager = syn_manager
        self.groups = {}
        self.group_words = {}
        self._build_groups()

    def _build_groups(self):
        """Построение групп синонимов"""
        all_unigrams = self.syn_manager._data.get("unigram_synonyms", {})
        visited = set()
        group_id = 0

        reverse_index = defaultdict(set)
        for word, synonyms in all_unigrams.items():
            for syn in synonyms:
                if syn != word:
                    reverse_index[syn].add(word)

        for word in all_unigrams.keys():
            if word in visited:
                continue

            group_id += 1
            current_group = set()
            stack = [word]

            while stack:
                current = stack.pop()
                if current in visited:
                    continue

                visited.add(current)
                current_group.add(current)

                current_synonyms = self.syn_manager.get_synonyms(current, ReplacementType.UNIGRAM)
                for syn in current_synonyms:
                    if syn not in visited and syn != current:
                        stack.append(syn)

                for other_word in reverse_index.get(current, []):
                    if other_word not in visited:
                        stack.append(other_word)

            for w in current_group:
                self.groups[w] = group_id
            self.group_words[group_id] = current_group

        log(f"Построено {len(self.group_words)} синонимических групп")

    def get_unified_synonyms(self, word: str) -> List[str]:
        """Получить все синонимы из группы"""
        if word not in self.groups:
            return [word]

        group_id = self.groups[word]
        return sorted(list(self.group_words[group_id]))



# ==================== АНАЛИЗАТОР ТЕКСТА (ПОЛНОСТЬЮ ИСПРАВЛЕННЫЙ) ====================
class FastTextAnalyzer:
    """Анализ текстов с извлечением n-грамм - ТОЧНО КАК В ОРИГИНАЛЕ (не разрывает на стоп-словах)"""

    def __init__(self, texts: List[str], stop_word_manager: StopWordManager):
        self.texts = texts
        self.stop_word_manager = stop_word_manager
        self._word_cache = {}

        try:
            import pymorphy3
            self.morph = pymorphy3.MorphAnalyzer()
        except ImportError:
            self.morph = None
            log("pymorphy3 не установлен", "WARNING")

    def analyze(self, progress_callback=None) -> Tuple[Dict, Dict, Dict, Dict, Dict]:
        """Анализ всех текстов"""
        unigrams = defaultdict(lambda: {
            'count': 0,
            'forms': defaultdict(int),
            'replace': True,
            'positions': [],
            'is_stopword': False
        })
        bigrams = {}
        trigrams = {}
        ngrams = {}
        prepositional = {}

        total = len(self.texts)

        for idx, text in enumerate(self.texts):
            if progress_callback:
                progress_callback(int((idx / total) * 100), f"Анализ текста {idx + 1}/{total}")

            if not text or not text.strip():
                continue

            try:
                self._analyze_text(text, idx, unigrams, bigrams, trigrams, ngrams, prepositional)
            except Exception as e:
                log(f"Ошибка анализа текста {idx}: {e}", "ERROR")

        return dict(unigrams), bigrams, trigrams, ngrams, prepositional

    def _analyze_text(self, text: str, text_index: int, unigrams: Dict, bigrams: Dict,
                      trigrams: Dict, ngrams: Dict, prepositional: Dict):
        # Униграммы (без изменений)
        words = re.findall(r'\b\w+\b', text.lower())
        word_positions = list(re.finditer(r'\b\w+\b', text, re.IGNORECASE))
        for i, (word, match) in enumerate(zip(words, word_positions)):
            if len(word) > 2:
                lemma = self._get_lemma(word)
                is_stopword = self.stop_word_manager.is_stop_word(lemma)
                unigrams[lemma]['count'] += 1
                unigrams[lemma]['forms'][match.group()] += 1
                unigrams[lemma]['positions'].append((text_index, match.start(), match.end()))
                unigrams[lemma]['is_stopword'] = is_stopword

        # Собираем слова с леммами, реальными словами и позициями
        words_with_info = []
        for match in re.finditer(r'\b\w+\b', text):
            word = match.group()
            lemma = self._get_lemma(word)
            words_with_info.append((lemma, word, match.start(), match.end()))

        # Биграммы, триграммы, N-граммы с сохранением реальных форм
        self._extract_ngrams_with_real_forms(text, words_with_info, text_index, 2, bigrams)
        self._extract_ngrams_with_real_forms(text, words_with_info, text_index, 3, trigrams)
        for n in range(4, 7):
            self._extract_ngrams_with_real_forms(text, words_with_info, text_index, n, ngrams)

        self._extract_prepositional_phrases_fixed(text, text_index, prepositional)

    def _extract_ngrams_with_real_forms(self, text: str, words_with_info: List[Tuple[str, str, int, int]],
                                        text_index: int, n: int, target_dict: Dict):
        """Извлечение n-грамм с сохранением реальных форм (подстрок из текста)"""
        for i in range(len(words_with_info) - n + 1):
            lemmas = [w[0] for w in words_with_info[i:i + n]]
            ngram_key = ', '.join(lemmas)
            start_pos = words_with_info[i][2]
            end_pos = words_with_info[i + n - 1][3]
            real_form = text[start_pos:end_pos].strip()  # реальная форма из текста

            if ngram_key not in target_dict:
                target_dict[ngram_key] = NGramInfo(
                    text=ngram_key,
                    count=1,
                    length=n,
                    positions=[(text_index, start_pos, end_pos)],
                    forms={real_form: 1}
                )
            else:
                target_dict[ngram_key].count += 1
                target_dict[ngram_key].positions.append((text_index, start_pos, end_pos))
                target_dict[ngram_key].forms[real_form] = target_dict[ngram_key].forms.get(real_form, 0) + 1

    def _extract_prepositional_phrases_fixed(self, text: str, text_index: int, target_dict: Dict):
        """Извлечение фраз с предлогами с сохранением реальных форм"""
        words_with_info = []
        for match in re.finditer(r'\b\w+\b', text):
            word = match.group()
            lemma = self._get_lemma(word)
            words_with_info.append((lemma, word, match.start(), match.end()))

        for n in range(2, 5):
            for i in range(len(words_with_info) - n + 1):
                lemmas = [w[0] for w in words_with_info[i:i + n]]
                words = [w[1] for w in words_with_info[i:i + n]]
                has_preposition = any(self.stop_word_manager.is_preposition(w) for w in words)
                if has_preposition:
                    phrase_key = ', '.join(lemmas)
                    start_pos = words_with_info[i][2]
                    end_pos = words_with_info[i + n - 1][3]
                    real_form = text[start_pos:end_pos]
                    if phrase_key not in target_dict:
                        target_dict[phrase_key] = NGramInfo(
                            text=phrase_key,
                            count=1,
                            length=n,
                            positions=[(text_index, start_pos, end_pos)],
                            forms={real_form: 1},
                            has_prepositions=True
                        )
                    else:
                        target_dict[phrase_key].count += 1
                        target_dict[phrase_key].positions.append((text_index, start_pos, end_pos))
                        target_dict[phrase_key].forms[real_form] = target_dict[phrase_key].forms.get(real_form, 0) + 1

    def _get_lemma(self, word: str) -> str:
        """Получение леммы слова с кешированием"""
        if not self.morph:
            return word.lower()

        word_lower = word.lower()
        if word_lower not in self._word_cache:
            try:
                parsed = self.morph.parse(word_lower)[0]
                self._word_cache[word_lower] = parsed.normal_form
            except:
                self._word_cache[word_lower] = word_lower

        return self._word_cache[word_lower]


# ==================== ЗАМЕНИТЕЛЬ (ПОЛНОСТЬЮ ИСПРАВЛЕННЫЙ) ====================
# ==================== ЗАМЕНИТЕЛЬ (ПОЛНОСТЬЮ ИСПРАВЛЕННЫЙ) ====================
class FastReplacer:
    """Замена текста синонимами с грамматической адаптацией - ТОЧНО КАК В ОРИГИНАЛЕ"""

    def __init__(self, syn_manager: FastSynonymManager, stop_word_manager: StopWordManager):
        self.syn_manager = syn_manager
        self.stop_word_manager = stop_word_manager

        try:
            import pymorphy3
            self.morph = pymorphy3.MorphAnalyzer()
        except ImportError:
            self.morph = None
            log("pymorphy3 не установлен", "WARNING")

    def clean_spaces(self, text: str) -> str:
        """Очищает текст от лишних пробелов - КАК В ОРИГИНАЛЕ"""
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+([.,;:!?])', r'\1', text)
        text = re.sub(r'([({\["\'])[ \t]+', r'\1', text)
        text = re.sub(r'[ \t]+([)}\]"\'])', r'\1', text)
        return text.strip()

    def get_text_lemmas(self, text: str) -> Set[str]:
        """Получает все леммы из текста - КАК В ОРИГИНАЛЕ"""
        lemmas = set()
        if not self.morph:
            return lemmas

        words = re.findall(r'\b\w+\b', text.lower())
        for word in words:
            try:
                parsed = self.morph.parse(word)[0]
                lemmas.add(parsed.normal_form)
            except:
                continue
        return lemmas

    def get_synonym_lemmas(self, synonym: str) -> Set[str]:
        """Получает все леммы из синонима - КАК В ОРИГИНАЛЕ"""
        lemmas = set()
        if not self.morph:
            return lemmas

        words = re.findall(r'\b\w+\b', synonym.lower())
        for word in words:
            try:
                parsed = self.morph.parse(word)[0]
                lemmas.add(parsed.normal_form)
            except:
                continue
        return lemmas

    def find_best_synonym(self, synonyms: List[str], context_lemmas: Set[str],
                          ngram_key: str, original_form: str, ngram_type: ReplacementType) -> Tuple[Optional[str], str]:
        """Находит лучший синоним для замены - КАК В ОРИГИНАЛЕ"""
        if not synonyms:
            return None, "Нет доступных синонимов"

        if len(synonyms) <= 1:
            return None, "Только один синоним (оригинал)"

        if len(synonyms) > 1 and random.random() < 0.20:
            return None, "Случайно оставили оригинал"

        chosen = random.choice([s for s in synonyms if s != ngram_key])

        # Для униграмм - дополнительная проверка на леммы в контексте
        if ngram_type == ReplacementType.UNIGRAM:
            available_synonyms = []

            for synonym in synonyms:
                synonym_lemmas = self.get_synonym_lemmas(synonym)
                if not synonym_lemmas:
                    available_synonyms.append(synonym)
                    continue

                synonym_in_context = any(lemma in context_lemmas for lemma in synonym_lemmas)
                if not synonym_in_context:
                    available_synonyms.append(synonym)

            if available_synonyms:
                return random.choice(available_synonyms), ""
            else:
                if ngram_key in synonyms:
                    return ngram_key, "Нет новых лемм → оставили оригинал"
                else:
                    chosen = random.choice(synonyms)
                    return chosen, "Нет новых лемм, оригинал отсутствует"

        return random.choice(synonyms), ""

    def collect_all_positions_for_text(self, text_index: int, unigrams: Dict, bigrams: Dict,
                                       trigrams: Dict, ngrams: Dict, prepositional: Dict) -> List[Dict]:
        """Собирает ВСЕ позиции для замен в одном тексте - КАК В ОРИГИНАЛЕ"""
        all_positions = []
        occupied_positions = set()

        def has_overlap(start, end):
            for occ_start, occ_end in occupied_positions:
                if not (end <= occ_start or start >= occ_end):
                    return True
            return False

        def add_positions_with_check(data_dict, ngram_type_obj):
            nonlocal all_positions, occupied_positions

            for ngram_key, ngram_info in data_dict.items():
                should_replace = False
                positions = []

                if isinstance(ngram_info, dict):
                    should_replace = ngram_info.get('replace', False)
                    positions = ngram_info.get('positions', [])
                elif hasattr(ngram_info, 'replace'):
                    should_replace = ngram_info.replace
                    positions = ngram_info.positions
                else:
                    continue

                if not should_replace:
                    continue

                active_synonyms = self.syn_manager.get_active_synonyms(ngram_key, ngram_type_obj)
                if not active_synonyms or len(active_synonyms) <= 1:
                    continue

                for pos in positions:
                    if pos[0] == text_index:
                        start, end = pos[1], pos[2]
                        if has_overlap(start, end):
                            continue
                        all_positions.append({
                            'text_index': text_index,
                            'start': start,
                            'end': end,
                            'ngram_key': ngram_key,
                            'synonyms': active_synonyms,
                            'ngram_type': ngram_type_obj
                        })
                        occupied_positions.add((start, end))
                        break

        # ВАЖНЫЙ ПОРЯДОК - от длинных к коротким (КАК В ОРИГИНАЛЕ)
        add_positions_with_check(ngrams, ReplacementType.NGRAM)
        add_positions_with_check(prepositional, ReplacementType.PREPOSITIONAL)
        add_positions_with_check(trigrams, ReplacementType.TRIGRAM)
        add_positions_with_check(bigrams, ReplacementType.BIGRAM)
        add_positions_with_check(unigrams, ReplacementType.UNIGRAM)

        all_positions.sort(key=lambda x: x['start'])
        return all_positions

    def replace_with_priority(self, texts: List[str], unigrams: Dict, bigrams: Dict,
                              trigrams: Dict, ngrams: Dict, prepositional: Dict) -> Tuple[List[str], List[ReplacementInfo]]:
        """Обработка ВСЕХ замен за один проход - ТОЧНО КАК В ОРИГИНАЛЕ"""
        all_replacements = []
        result_texts = []

        log(f"🔄 Начинаем замену {len(texts)} текстов...")

        for text_index, original_text in enumerate(texts):
            log(f"  Обработка текста {text_index + 1}/{len(texts)}")

            all_positions = self.collect_all_positions_for_text(
                text_index, unigrams, bigrams, trigrams, ngrams, prepositional
            )

            if not all_positions:
                log(f"    Нет позиций для замены")
                result_texts.append(original_text)
                continue

            log(f"    Найдено {len(all_positions)} позиций для замены")
            all_positions.sort(key=lambda x: x['start'])

            processed_text = original_text
            text_replacements = []
            i = 0

            while i < len(all_positions):
                pos_info = all_positions[i]
                start = pos_info['start']
                end = pos_info['end']
                ngram_type = pos_info['ngram_type']
                ngram_key = pos_info['ngram_key']
                synonyms = pos_info['synonyms']

                if start >= len(processed_text) or end > len(processed_text):
                    i += 1
                    continue

                original_phrase = processed_text[start:end]
                valid_synonyms = synonyms[:]

                if not valid_synonyms or len(valid_synonyms) <= 1:
                    i += 1
                    continue

                # Пытаемся найти лучший синоним с учетом контекста
                context_start = max(0, start - 100)
                context_end = min(len(processed_text), end + 100)
                context = processed_text[context_start:context_end]
                context_lemmas = self.get_text_lemmas(context)

                best_synonym, skip_reason = self.find_best_synonym(
                    valid_synonyms, context_lemmas, ngram_key, original_phrase, ngram_type
                )

                if not best_synonym:
                    i += 1
                    continue

                # Адаптируем форму
                new_phrase = self.adapt_synonym_form(ngram_key, best_synonym, original_phrase, ngram_type)

                # Проверяем, что это не та же самая фраза
                orig_clean = ' '.join(original_phrase.strip().split()).lower()
                new_clean = ' '.join(new_phrase.strip().split()).lower()
                if orig_clean == new_clean:
                    i += 1
                    continue

                # Проверяем безопасность замены
                if self.is_safe_replacement(processed_text, start, end, new_phrase):
                    processed_text = processed_text[:start] + new_phrase + processed_text[end:]

                    replacement = ReplacementInfo(
                        original=original_phrase,
                        new=new_phrase,
                        start=start,
                        end=start + len(new_phrase),
                        text_index=text_index,
                        type=ngram_type,
                        used_synonym=best_synonym,
                        lemma=ngram_key
                    )
                    text_replacements.append(replacement)

                    # Корректируем позиции для последующих замен
                    length_diff = len(new_phrase) - len(original_phrase)
                    for j in range(i + 1, len(all_positions)):
                        if all_positions[j]['start'] > start:
                            all_positions[j]['start'] += length_diff
                            all_positions[j]['end'] += length_diff

                    log(f"    ✅ ЗАМЕНА: '{original_phrase[:50]}' → '{new_phrase[:50]}'")

                i += 1

            processed_text = self.clean_spaces(processed_text)
            result_texts.append(processed_text)
            all_replacements.extend(text_replacements)
            log(f"    Выполнено {len(text_replacements)} замен")

        log(f"🎯 Завершено. Всего замен: {len(all_replacements)}")
        return result_texts, all_replacements

    def is_safe_replacement(self, text: str, start: int, end: int, new_phrase: str) -> bool:
        """Проверка безопасности замены - КАК В ОРИГИНАЛЕ"""
        if not new_phrase:
            return False
        if start > 0 and text[start - 1].isalnum():
            return False
        if end < len(text) and text[end].isalnum():
            return False
        return True

    def adapt_synonym_form(self, original_ngram: str, synonym_ngram: str,
                           original_form: str, ngram_type: ReplacementType) -> str:
        """Адаптация формы - КАК В ОРИГИНАЛЕ"""
        try:
            specific_form = self.syn_manager.get_specific_form(original_form, synonym_ngram, ngram_type)
            if specific_form:
                return self.apply_case(original_form, specific_form)

            if not self.morph or ngram_type == ReplacementType.PREPOSITIONAL:
                return self.apply_case(original_form, synonym_ngram)

            if ngram_type == ReplacementType.UNIGRAM:
                result = self.adapt_unigram_form(original_form, synonym_ngram)
            else:
                result = self.adapt_phrase_form(original_form, synonym_ngram, ngram_type)

            return self.apply_case(original_form, result)

        except Exception as e:
            log(f"Ошибка адаптации: {e}", "WARNING")
            return self.apply_case(original_form, synonym_ngram)

    def adapt_unigram_form(self, original_form: str, synonym: str) -> str:
        """Адаптация формы для униграмм - КАК В ОРИГИНАЛЕ"""
        if not self.morph:
            return self.apply_case(original_form, synonym)

        try:
            original_parsed = self.morph.parse(original_form)[0]
            synonym_parsed = self.morph.parse(synonym)[0]
            grammemes = set(original_parsed.tag.grammemes)
            new_form = synonym_parsed.inflect(grammemes)
            return new_form.word if new_form else synonym
        except Exception as e:
            return synonym

    def adapt_phrase_form(self, original_phrase: str, synonym_phrase: str, ngram_type: ReplacementType) -> str:
        """Адаптация формы для фраз - КАК В ОРИГИНАЛЕ"""
        try:
            original_words = re.findall(r'\b\w+\b', original_phrase)
            synonym_words = re.findall(r'\b\w+\b', synonym_phrase)

            if not original_words or not synonym_words:
                return self.apply_case(original_phrase, synonym_phrase)

            if len(original_words) != len(synonym_words):
                adapted = []
                for i, syn_word in enumerate(synonym_words):
                    if i < len(original_words):
                        adapted.append(self.adapt_unigram_form(original_words[i], syn_word))
                    else:
                        adapted.append(syn_word)
                result = ' '.join(adapted)
                return self.apply_case(original_phrase, result)

            adapted_words = []
            for i, syn_word in enumerate(synonym_words):
                try:
                    orig_parsed = self.morph.parse(original_words[i])[0]
                    syn_parsed = self.morph.parse(syn_word)[0]
                    grammemes = set(orig_parsed.tag.grammemes)
                    new_form = syn_parsed.inflect(grammemes)
                    adapted_words.append(new_form.word if new_form else syn_word)
                except:
                    adapted_words.append(syn_word)

            result = ' '.join(adapted_words)
            return self.apply_case(original_phrase, result)

        except Exception as e:
            return self.apply_case(original_phrase, synonym_phrase)

    def apply_case(self, original: str, text: str) -> str:
        """Применяет регистр оригинала к тексту - КАК В ОРИГИНАЛЕ"""
        if not text or not original:
            return text
        if original.isupper():
            return text.upper()
        if original.islower():
            return text.lower()
        if original.istitle():
            return text.title()
        if original and original[0].isupper():
            return text[0].upper() + text[1:].lower() if text else text
        return text


# ==================== ФУНКЦИИ ДЛЯ STREAMLIT UI ====================

def init_phase6_structure(context=None):
    """Инициализация структуры фазы 6 - НЕ ПЕРЕЗАПИСЫВАЕТ существующие данные"""

    # ===== ДОБАВИТЬ ПРОВЕРКУ =====
    current_project_id = st.session_state.get('current_project_id')
    last_loaded = st.session_state.get('phase6_last_loaded_project')

    if current_project_id and last_loaded != current_project_id:
        log(f"🔄 init_phase6_structure: проект изменился, очищаем данные")
        if 'phase6' in st.session_state:
            st.session_state.phase6 = {
                'initialized': True,
                'texts': [],
                'original_texts': [],
                'processed_texts': [],
                'edited_texts': [],
                'replacements': [],
                'unigrams': {},
                'bigrams': {},
                'trigrams': {},
                'ngrams': {},
                'prepositional': {},
                'analysis_completed': False,
                'replacements_applied': False,
                'texts_metadata': [],
                'min_count': 3
            }
        st.session_state.phase6_last_loaded_project = current_project_id
        return
    # ===== КОНЕЦ ПРОВЕРКИ =====

    # ✅ ЕСЛИ НЕТ КОНТЕКСТА - НЕ РАБОТАЕМ
    if context is None:
        log("❌ Нет контекста! Невозможно инициализировать фазу 6", "ERROR")
        return

    # ... остальной код без изменений ...

    # ✅ ЕСЛИ УЖЕ ЕСТЬ ДАННЫЕ - НЕ ТРОГАЕМ!
    if 'phase6' in st.session_state and st.session_state.phase6.get('analysis_completed'):
        log(f"✅ Phase6 уже инициализирована, данные есть: {len(st.session_state.phase6.get('texts', []))} текстов")
        return

    # ✅ ВОССТАНАВЛИВАЕМ ДАННЫЕ ИЗ КОНТЕКСТА (ФАЙЛА)
    phase6_data = context.get_phase_data(6)

    if phase6_data:
        # ✅ НЕ ПЕРЕЗАПИСЫВАЕМ, А ДОПОЛНЯЕМ!
        if 'phase6' not in st.session_state:
            st.session_state.phase6 = {}

        # Сохраняем только то, чего нет
        for key, value in phase6_data.items():
            if key not in st.session_state.phase6 or not st.session_state.phase6[key]:
                st.session_state.phase6[key] = value

        log(f"✅ Загружены данные phase6 из файла")
        return

    # Если нет данных - создаем пустую структуру ТОЛЬКО ЕСЛИ ЕЕ НЕТ
    if 'phase6' not in st.session_state:
        st.session_state.phase6 = {
            'initialized': True,
            'texts': [],
            'original_texts': [],
            'processed_texts': [],
            'edited_texts': [],
            'replacements': [],
            'unigrams': {},
            'bigrams': {},
            'trigrams': {},
            'ngrams': {},
            'prepositional': {},
            'analysis_completed': False,
            'replacements_applied': False,
            'texts_metadata': [],
            'min_count': 3
        }
        log(f"✅ Создана новая структура phase6")

    # ✅ SelectionManager
    if 'selection_manager' not in st.session_state:
        st.session_state.selection_manager = SelectionManager(
            project_id=context.project_id,
            user_id=context.user_id,
            site_name=context.site_name,
            domain_name=context.domain_name,
            context=context
        )


def load_texts_from_phase5(force_reload: bool = False, context=None):
    """Загрузка текстов из фазы 5 - СОХРАНЯЕТ ВСЮ СТРУКТУРУ"""

    # ===== ПРОВЕРКА =====
    current_project_id = st.session_state.get('current_project_id')
    last_loaded = st.session_state.get('phase6_last_loaded_project')

    if current_project_id and last_loaded != current_project_id:
        log(f"⚠️ load_texts_from_phase5: проект изменился! Не загружаем старые данные", "WARNING")
        return [], []

    # ✅ БЕЗ КОНТЕКСТА - НЕ РАБОТАЕМ
    if context is None:
        log("❌ load_texts_from_phase5: Нет контекста!", "ERROR")
        return [], []

    # ✅ БЕРЕМ ДАННЫЕ ТОЛЬКО ИЗ КОНТЕКСТА
    user_id = context.user_id
    project_id = context.project_id
    site = context.site_name
    domain = context.domain_name

    if not user_id or not project_id:
        log(f"❌ Нет данных в контексте: user_id={user_id}, project_id={project_id}", "ERROR")
        return [], []

    # ✅ ЧИТАЕМ ФАЙЛ
    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

    if not project_file.exists():
        log(f"❌ Файл проекта не найден: {project_file}", "ERROR")
        return [], []

    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            file_data = json.load(f)

        app_data = file_data.get('app_data', {})

        # ✅ ПРОВЕРЯЕМ, ЧТО PHASE5 СУЩЕСТВУЕТ И НЕ ПУСТАЯ
        phase5_data = app_data.get('phase5', {})

        # ✅ ЕСЛИ PHASE5 ПУСТАЯ - СОЗДАЕМ ЗАНОВО ИЗ PHASE4
        if not phase5_data or not phase5_data.get('results'):
            log("⚠️ phase5 пустая, пробуем восстановить из phase4", "WARNING")

            phase4_data = app_data.get('phase4', {})
            prompts = phase4_data.get('prompts', [])

            if prompts:
                # Восстанавливаем phase5 из phase4
                results = {}
                for i, prompt in enumerate(prompts):
                    if 'characteristic_id' in prompt:
                        prompt_id = f"char_{prompt['characteristic_id']}_{prompt.get('value', '')}_{prompt.get('prompt_num', i)}"
                    elif 'block_id' in prompt:
                        prompt_id = f"block_{prompt['block_id']}_{prompt.get('prompt_num', i)}"
                    else:
                        prompt_id = f"prompt_{i}"

                    prompt['phase5_id'] = prompt_id
                    results[prompt_id] = {
                        'prompt_id': prompt_id,
                        'prompt': prompt.get('prompt', ''),
                        'ai_response': '',
                        'status': 'pending',
                        'model': '',
                        'provider': '',
                        'tokens_used': 0,
                        'generated_at': None,
                        'error_message': None,
                        'edited_text': '',
                        'characteristic_name': prompt.get('characteristic_name', ''),
                        'characteristic_value': prompt.get('value', ''),
                        'block_name': prompt.get('block_name', ''),
                        'prompt_num': prompt.get('prompt_num', 1),
                        'type': prompt.get('type', prompt.get('block_type', 'unknown'))
                    }

                # ✅ ВОССТАНАВЛИВАЕМ PHASE5 В ФАЙЛЕ
                phase5_data = {
                    'results': results,
                    'statistics': {
                        'total': len(prompts),
                        'success': 0,
                        'error': 0,
                        'completed': 0,
                        'selected': len(prompts),
                        'pending': len(prompts)
                    },
                    'generation_settings': {},
                    'prompts': prompts,
                    'selected_prompt_ids': [p.get('phase5_id') for p in prompts if p.get('phase5_id')],
                    'generation_status': 'idle',
                    'generation_running': False,
                    'generation_queue': [],
                    'current_index': 0,
                    'phase_completed': False,
                    'prompts_count': len(prompts)
                }

                # ✅ СОХРАНЯЕМ ВОССТАНОВЛЕННУЮ PHASE5 В ФАЙЛ
                app_data['phase5'] = phase5_data
                file_data['app_data'] = app_data
                file_data['updated_at'] = datetime.now().isoformat()

                with open(project_file, 'w', encoding='utf-8') as f:
                    json.dump(file_data, f, ensure_ascii=False, indent=2)

                log(f"✅ Восстановлена phase5 из phase4: {len(prompts)} промптов")
            else:
                log("❌ Нет phase4 для восстановления", "ERROR")
                return [], []

        # ✅ ИЗВЛЕКАЕМ ТЕКСТЫ ИЗ PHASE5
        results = phase5_data.get('results', {})
        log(f"📥 Загружено {len(results)} результатов из phase5")

    except Exception as e:
        log(f"❌ Ошибка загрузки: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return [], []

    # Извлекаем тексты
    texts = []
    text_metadata = []

    if isinstance(results, dict):
        for prompt_id, result in results.items():
            if isinstance(result, dict):
                text = result.get('edited_text') or result.get('ai_response', '')
                if text and text.strip():
                    texts.append(text.strip())
                    text_metadata.append({
                        'prompt_id': prompt_id,
                        'characteristic_name': result.get('characteristic_name', ''),
                        'characteristic_value': result.get('characteristic_value', ''),
                        'type': result.get('type', 'other'),
                        'block_name': result.get('block_name', ''),
                        'prompt_num': result.get('prompt_num', 1)
                    })

    if not texts:
        log("⚠️ Нет текстов для синонимизации", "WARNING")
        return [], []

    log(f"✅ Извлечено {len(texts)} текстов")
    return texts, text_metadata


def save_to_phase7(context=None):
    """Сохранение результатов - ТОЛЬКО В ФАЙЛ"""
    log("=" * 60, "INFO")
    log("🔍 save_to_phase7() CALLED", "INFO")
    from pathlib import Path
    import json
    from datetime import datetime
    if context is None:
        log("❌ Нет контекста!", "ERROR")
        return False

    log(f"   context.user_id: {context.user_id}", "INFO")
    log(f"   context.project_id: {context.project_id}", "INFO")
    log(f"   context.site_name: {context.site_name}", "INFO")
    log(f"   context.domain_name: {context.domain_name}", "INFO")



    # ✅ ЛОГИРУЕМ, ЧТО ПРИШЛО
    log(f"🔍 save_to_phase7: context.user_id={context.user_id}")
    log(f"🔍 save_to_phase7: context.project_id={context.project_id}")
    log(f"🔍 save_to_phase7: context.site_name={context.site_name}")
    log(f"🔍 save_to_phase7: context.domain_name={context.domain_name}")

    # Определяем тексты для сохранения
    if 'edited_texts' in st.session_state.phase6 and st.session_state.phase6['edited_texts']:
        processed_texts = st.session_state.phase6['edited_texts']
        was_edited = True
    elif 'processed_texts' in st.session_state.phase6 and st.session_state.phase6['processed_texts']:
        processed_texts = st.session_state.phase6['processed_texts']
        was_edited = False
    else:
        processed_texts = st.session_state.phase6.get('original_texts', [])
        was_edited = False

    if not processed_texts:
        log("⚠️ Нет текстов для сохранения", "WARNING")
        return False

    # ... остальной код без изменений ...

    # Создаем результаты
    original_texts = st.session_state.phase6.get('original_texts', [])
    replacements = st.session_state.phase6.get('replacements', [])
    texts_metadata = st.session_state.phase6.get('texts_metadata', [])

    results_dict = {}
    for idx, processed_text in enumerate(processed_texts):
        metadata = texts_metadata[idx] if idx < len(texts_metadata) else {}
        prompt_id = metadata.get('prompt_id', f"text_{idx}")

        text_replacements = [r for r in replacements if r.get('text_index') == idx]

        results_dict[prompt_id] = {
            'prompt_id': prompt_id,
            'ai_response': processed_text,
            'edited_text': processed_text,
            'original_text': original_texts[idx] if idx < len(original_texts) else '',
            'status': 'success',
            'model': 'synonymizer' if was_edited else 'original',
            'provider': 'synonymizer' if was_edited else 'phase5',
            'tokens_used': 0,
            'generated_at': datetime.now().isoformat(),
            'error_message': None,
            'characteristic_name': metadata.get('characteristic_name', ''),
            'characteristic_value': metadata.get('characteristic_value', ''),
            'block_name': metadata.get('block_name', ''),
            'type': metadata.get('type', 'unknown'),
            'prompt_num': metadata.get('prompt_num', 1),
            'replacements': text_replacements,
            'replacements_count': len(text_replacements),
            'is_synonymized': len(text_replacements) > 0
        }

    log(f"✅ Создано {len(results_dict)} результатов для сохранения")

    # ✅ СОХРАНЯЕМ В ФАЙЛ
    user_id = context.user_id
    project_id = context.project_id
    site = context.site_name
    domain = context.domain_name

    project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

    log(f"🔍 Сохраняем в файл: {project_file}")

    if not project_file.exists():
        log(f"❌ Файл проекта не найден: {project_file}", "ERROR")
        return False

    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            file_data = json.load(f)

        if 'app_data' not in file_data:
            file_data['app_data'] = {}

        phase6_data = {
            'results': results_dict,
            'statistics': {
                'total': len(processed_texts),
                'success': len(processed_texts),
                'error': 0,
                'replacements_applied': len(replacements),
                'total_replacements': len(replacements)
            },
            'phase_completed': True,
            'completed_at': datetime.now().isoformat(),
            'category': file_data.get('app_data', {}).get('category', ''),
            'is_synonymized': len(replacements) > 0
        }

        # В конце функции, при сохранении в файл:
        file_data['app_data']['phase6'] = phase6_data
        file_data['app_data']['phase6_completed'] = True

        # ✅ ТАКЖЕ СОХРАНЯЕМ В phase5 ДЛЯ СОВМЕСТИМОСТИ
        file_data['app_data']['phase5'] = {
            'results': results_dict,
            'statistics': {
                'total': len(processed_texts),
                'success': len(processed_texts),
                'error': 0
            },
            'phase_completed': True
        }
        file_data['app_data']['phase5_completed'] = True

        # ✅ СОХРАНЯЕМ В КОРЕНЬ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ
        file_data['phase5_results'] = results_dict

        # ✅ ОБНОВЛЯЕМ phase6_last_loaded_project
        st.session_state.phase6_last_loaded_project = project_id

        file_data['updated_at'] = datetime.now().isoformat()

        with open(project_file, 'w', encoding='utf-8') as f:
            json.dump(file_data, f, ensure_ascii=False, indent=2)

        log(f"💾 Phase6 и phase5_results сохранены в файл: {project_file}")
        log(f"   - phase6.results: {len(results_dict)}")
        log(f"   - phase5_results: {len(results_dict)}")

        # ✅ ОБНОВЛЯЕМ КОНТЕКСТ
        context.set_phase_data(6, phase6_data)
        context.save()
        log(f"✅ Phase6 сохранена в контекст")

        # ✅ ОБНОВЛЯЕМ session_state ТОЛЬКО ДЛЯ UI
        st.session_state.phase6_completed = True
        st.session_state.phase6_results = results_dict
        st.session_state.phase5_results = results_dict
        st.session_state.phase5_completed = True
        st.session_state.phase6_last_loaded_project = project_id
        # ✅ ПРИНУДИТЕЛЬНО СОХРАНЯЕМ В ФАЙЛ
        try:
            if context is not None and hasattr(context, 'save'):
                context.save()
                log(f"   ✅ Сохранено через context")
            elif 'app_state' in st.session_state:
                st.session_state.app_state.save_project()
                log(f"   ✅ Сохранено через app_state")
            else:
                # Сохраняем через domain_manager
                if 'domain_manager' in st.session_state:
                    dm = st.session_state.domain_manager
                    user_id = context.user_id if context else st.session_state.get('user_id')
                    project_id = context.project_id if context else st.session_state.get('current_project_id')
                    site = context.site_name if context else st.session_state.get('current_site', 'steelborg')
                    domain = context.domain_name if context else st.session_state.get('current_domain', 'default')
                    if user_id and project_id:
                        from pathlib import Path
                        import json
                        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")
                        if project_file.exists():
                            with open(project_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            data['app_data'] = st.session_state.app_data
                            data['updated_at'] = datetime.now().isoformat()
                            with open(project_file, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                            log(f"   ✅ Сохранено через прямой доступ к файлу")
        except Exception as e:
            log(f"   ⚠️ Ошибка сохранения: {e}", "WARNING")
        return True

    except Exception as e:
        log(f"❌ Ошибка сохранения: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return False


def analyze_texts(syn_manager, stop_manager):
    """Анализ текстов и извлечение n-грамм"""
    with st.spinner("Анализ текстов..."):
        texts = st.session_state.phase6.get('texts', [])

        if not texts:
            st.error("Нет текстов для анализа")
            log("❌ analyze_texts: Нет текстов", "ERROR")
            return False

        log(f"🔍 analyze_texts: анализируем {len(texts)} текстов")

        analyzer = FastTextAnalyzer(texts, stop_manager)

        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(progress, message):
            progress_bar.progress(progress)
            status_text.text(message)

        unigrams, bigrams, trigrams, ngrams, prepositional = analyzer.analyze(update_progress)

        # Конвертируем NGramInfo в словари
        def convert_ngram_info_to_dict(data):
            """Рекурсивно конвертирует NGramInfo в словари"""
            result = {}
            for key, value in data.items():
                if hasattr(value, 'to_dict'):
                    result[key] = value.to_dict()
                elif isinstance(value, dict):
                    result[key] = convert_ngram_info_to_dict(value)
                else:
                    result[key] = value
            return result

        # Получаем метаданные
        metadata = st.session_state.phase6.get('texts_metadata', [])

        # ✅ СОХРАНЯЕМ В app_data (потом запишется в файл)
        if 'app_data' not in st.session_state:
            st.session_state.app_data = {}

        if 'phase6' not in st.session_state.app_data:
            st.session_state.app_data['phase6'] = {}

        # Сохраняем анализ
        st.session_state.app_data['phase6']['unigrams'] = convert_ngram_info_to_dict(unigrams)
        st.session_state.app_data['phase6']['bigrams'] = convert_ngram_info_to_dict(bigrams)
        st.session_state.app_data['phase6']['trigrams'] = convert_ngram_info_to_dict(trigrams)
        st.session_state.app_data['phase6']['ngrams'] = convert_ngram_info_to_dict(ngrams)
        st.session_state.app_data['phase6']['prepositional'] = convert_ngram_info_to_dict(prepositional)
        st.session_state.app_data['phase6']['analysis_completed'] = True

        # ✅ КРИТИЧЕСКИ ВАЖНО: СОХРАНЯЕМ ТЕКСТЫ
        st.session_state.app_data['phase6']['texts'] = texts
        st.session_state.app_data['phase6']['original_texts'] = texts.copy()
        st.session_state.app_data['phase6']['processed_texts'] = texts.copy()
        st.session_state.app_data['phase6']['texts_metadata'] = metadata
        st.session_state.app_data['phase6']['replacements'] = []
        st.session_state.app_data['phase6']['replacements_applied'] = False

        # Также сохраняем в session_state для UI
        st.session_state.phase6['unigrams'] = convert_ngram_info_to_dict(unigrams)
        st.session_state.phase6['bigrams'] = convert_ngram_info_to_dict(bigrams)
        st.session_state.phase6['trigrams'] = convert_ngram_info_to_dict(trigrams)
        st.session_state.phase6['ngrams'] = convert_ngram_info_to_dict(ngrams)
        st.session_state.phase6['prepositional'] = convert_ngram_info_to_dict(prepositional)
        st.session_state.phase6['analysis_completed'] = True
        st.session_state.phase6['processed_texts'] = texts.copy()
        st.session_state.phase6['original_texts'] = texts.copy()
        st.session_state.phase6['texts_metadata'] = metadata

        log(f"✅ analysis_completed = True, сохранено {len(texts)} текстов")

        # ✅ ПРИНУДИТЕЛЬНО СОХРАНЯЕМ В ФАЙЛ
        try:
            # Пробуем через app_state
            if 'app_state' in st.session_state:
                st.session_state.app_state.save_project()
                log(f"   ✅ Проект сохранен через app_state")
            # Пробуем через context
            elif '_current_context' in st.session_state:
                st.session_state._current_context.save()
                log(f"   ✅ Проект сохранен через context")
            else:
                # Сохраняем через domain_manager
                if 'domain_manager' in st.session_state:
                    dm = st.session_state.domain_manager
                    user_id = st.session_state.get('user_id')
                    project_id = st.session_state.get('current_project_id')
                    if user_id and project_id:
                        from pathlib import Path
                        import json
                        project_file = Path(f"sites/{dm.site_name}/domains/{dm.get_current_domain()}/projects/{user_id}/{project_id}.json")
                        if project_file.exists():
                            with open(project_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            data['app_data'] = st.session_state.app_data
                            data['updated_at'] = datetime.now().isoformat()
                            with open(project_file, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                            log(f"   ✅ Проект сохранен через прямой доступ к файлу")
        except Exception as e:
            log(f"   ⚠️ Ошибка сохранения: {e}", "WARNING")

        progress_bar.empty()
        status_text.empty()

        st.success(f"✅ Анализ завершен! "
                   f"Униграмм: {len(convert_ngram_info_to_dict(unigrams))}, Биграмм: {len(convert_ngram_info_to_dict(bigrams))}, "
                   f"Триграмм: {len(convert_ngram_info_to_dict(trigrams))}, N-грамм: {len(convert_ngram_info_to_dict(ngrams))}, "
                   f"Фраз с предлогами: {len(convert_ngram_info_to_dict(prepositional))}")

        time.sleep(0.4)
        st.rerun()
        return True

def filter_ngrams_by_count(data: Dict, min_count: int) -> Dict:
    """Фильтрация n-грамм по порогу частоты"""
    if not data:
        return {}

    filtered = {}
    for key, info in data.items():
        if isinstance(info, dict):
            count = info.get('count', 0)
        elif hasattr(info, 'count'):
            count = info.count
        else:
            count = 0

        try:
            count_int = int(count) if count is not None else 0
            if count_int >= min_count:
                filtered[key] = info
        except (TypeError, ValueError):
            continue

    return filtered


def safe_get_count(info) -> int:
    """Безопасное получение count из info"""
    if info is None:
        return 0
    if isinstance(info, dict):
        return info.get('count', 0)
    if hasattr(info, 'count'):
        return info.count
    return 0
def apply_replacements(syn_manager, stop_manager, selection_manager: SelectionManager):
    """Применение замен к текстам - ФИКСИРОВАННАЯ ВЕРСИЯ"""
    with st.spinner("Применение замен..."):
        texts = st.session_state.phase6.get('texts', [])

        if not texts:
            st.error("Нет текстов для обработки")
            return False

        # Получаем ВСЕ данные
        all_unigrams = st.session_state.phase6.get('unigrams', {})
        all_bigrams = st.session_state.phase6.get('bigrams', {})
        all_trigrams = st.session_state.phase6.get('trigrams', {})
        all_ngrams = st.session_state.phase6.get('ngrams', {})
        all_prepositional = st.session_state.phase6.get('prepositional', {})

        # Фильтруем ТОЛЬКО выбранные
        selected_unigrams = {}
        selected_bigrams = {}
        selected_trigrams = {}
        selected_ngrams = {}
        selected_prepositional = {}

        # Для каждого типа - копирование с сохранением структуры
        for key, info in all_unigrams.items():
            if selection_manager.get_selection('unigram', key, False):
                if isinstance(info, dict):
                    selected_unigrams[key] = {
                        'count': info.get('count', 0),
                        'forms': info.get('forms', {}),
                        'positions': info.get('positions', []),
                        'replace': True,
                        'is_stopword': info.get('is_stopword', False)
                    }
                else:
                    selected_unigrams[key] = info
                    if hasattr(selected_unigrams[key], 'replace'):
                        selected_unigrams[key].replace = True

        for key, info in all_bigrams.items():
            if selection_manager.get_selection('bigram', key, False):
                if isinstance(info, dict):
                    selected_bigrams[key] = {
                        'count': info.get('count', 0),
                        'forms': info.get('forms', {}),
                        'positions': info.get('positions', []),
                        'replace': True
                    }
                else:
                    selected_bigrams[key] = info
                    if hasattr(selected_bigrams[key], 'replace'):
                        selected_bigrams[key].replace = True

        for key, info in all_trigrams.items():
            if selection_manager.get_selection('trigram', key, False):
                if isinstance(info, dict):
                    selected_trigrams[key] = {
                        'count': info.get('count', 0),
                        'forms': info.get('forms', {}),
                        'positions': info.get('positions', []),
                        'replace': True
                    }
                else:
                    selected_trigrams[key] = info
                    if hasattr(selected_trigrams[key], 'replace'):
                        selected_trigrams[key].replace = True

        for key, info in all_ngrams.items():
            if selection_manager.get_selection('ngram', key, False):
                if isinstance(info, dict):
                    selected_ngrams[key] = {
                        'count': info.get('count', 0),
                        'forms': info.get('forms', {}),
                        'positions': info.get('positions', []),
                        'replace': True
                    }
                else:
                    selected_ngrams[key] = info
                    if hasattr(selected_ngrams[key], 'replace'):
                        selected_ngrams[key].replace = True

        for key, info in all_prepositional.items():
            if selection_manager.get_selection('prepositional', key, False):
                if isinstance(info, dict):
                    selected_prepositional[key] = {
                        'count': info.get('count', 0),
                        'forms': info.get('forms', {}),
                        'positions': info.get('positions', []),
                        'replace': True,
                        'has_prepositions': info.get('has_prepositions', True)
                    }
                else:
                    selected_prepositional[key] = info
                    if hasattr(selected_prepositional[key], 'replace'):
                        selected_prepositional[key].replace = True

        total_selected = (len(selected_unigrams) + len(selected_bigrams) +
                          len(selected_trigrams) + len(selected_ngrams) +
                          len(selected_prepositional))

        log(f"ВСЕГО выбрано для замены: {total_selected} n-грамм")

        if total_selected == 0:
            st.warning("⚠️ Не выбрано ни одной n-граммы для замены!")
            return False

        st.info(f"📊 Выбрано для замены: {total_selected} n-грамм")

        # Применяем замены
        replacer = FastReplacer(syn_manager, stop_manager)

        processed_texts, replacements = replacer.replace_with_priority(
            texts,
            selected_unigrams,
            selected_bigrams,
            selected_trigrams,
            selected_ngrams,
            selected_prepositional
        )

        # ✅ СОХРАНЯЕМ В app_data
        if 'app_data' not in st.session_state:
            st.session_state.app_data = {}

        if 'phase6' not in st.session_state.app_data:
            st.session_state.app_data['phase6'] = {}

        st.session_state.app_data['phase6']['processed_texts'] = processed_texts
        st.session_state.app_data['phase6']['edited_texts'] = processed_texts.copy()
        st.session_state.app_data['phase6']['replacements'] = [
            {
                'original': r.original,
                'new': r.new,
                'start': r.start,
                'end': r.end,
                'text_index': r.text_index,
                'type': r.type.value,
                'lemma': r.lemma,
                'used_synonym': r.used_synonym
            }
            for r in replacements
        ]
        st.session_state.app_data['phase6']['replacements_applied'] = True

        # Также сохраняем в session_state для UI
        st.session_state.phase6['processed_texts'] = processed_texts
        st.session_state.phase6['replacements'] = [
            {
                'original': r.original,
                'new': r.new,
                'start': r.start,
                'end': r.end,
                'text_index': r.text_index,
                'type': r.type.value,
                'lemma': r.lemma,
                'used_synonym': r.used_synonym
            }
            for r in replacements
        ]
        st.session_state.phase6['replacements_applied'] = True
        st.session_state.phase6['edited_texts'] = processed_texts.copy()

        log(f"   ✅ Сохранено в app_data: processed_texts={len(processed_texts)}, replacements={len(replacements)}")

        # ✅ ПРИНУДИТЕЛЬНО СОХРАНЯЕМ В ФАЙЛ
        try:
            if '_current_context' in st.session_state and st.session_state._current_context is not None:
                st.session_state._current_context.save()
                log(f"   ✅ Сохранено через context")
            elif 'app_state' in st.session_state:
                st.session_state.app_state.save_project()
                log(f"   ✅ Сохранено через app_state")
            else:
                # Сохраняем через domain_manager
                if 'domain_manager' in st.session_state:
                    dm = st.session_state.domain_manager
                    user_id = st.session_state.get('user_id')
                    project_id = st.session_state.get('current_project_id')
                    if user_id and project_id:
                        from pathlib import Path
                        import json
                        project_file = Path(f"sites/{dm.site_name}/domains/{dm.get_current_domain()}/projects/{user_id}/{project_id}.json")
                        if project_file.exists():
                            with open(project_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            data['app_data'] = st.session_state.app_data
                            data['updated_at'] = datetime.now().isoformat()
                            with open(project_file, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                            log(f"   ✅ Сохранено через прямой доступ к файлу")
        except Exception as e:
            log(f"   ⚠️ Ошибка сохранения: {e}", "WARNING")

        st.success(f"✅ Выполнено замен: {len(replacements)} из выбранных {total_selected} n-грамм")
        return True
def reanalyze_with_edited_texts(syn_manager, stop_manager, selection_manager: SelectionManager):
    """Повторный анализ текстов после синонимизации для итеративной доработки"""
    # Берём обработанные тексты (если есть ручные правки, то edited_texts, иначе processed_texts)
    if 'edited_texts' in st.session_state.phase6 and st.session_state.phase6['edited_texts']:
        new_texts = st.session_state.phase6['edited_texts'].copy()
    elif 'processed_texts' in st.session_state.phase6:
        new_texts = st.session_state.phase6['processed_texts'].copy()
    else:
        st.error("Нет обработанных текстов для повторного анализа")
        return False

    if not new_texts:
        st.error("Нет текстов для анализа")
        return False

    # Сохраняем старые метаданные (если были)
    old_metadata = st.session_state.phase6.get('texts_metadata', [])

    # Обновляем тексты в состоянии
    st.session_state.phase6['texts'] = new_texts
    st.session_state.phase6['original_texts'] = new_texts.copy()
    if old_metadata:
        st.session_state.phase6['texts_metadata'] = old_metadata

    # Очищаем старые результаты анализа
    st.session_state.phase6['unigrams'] = {}
    st.session_state.phase6['bigrams'] = {}
    st.session_state.phase6['trigrams'] = {}
    st.session_state.phase6['ngrams'] = {}
    st.session_state.phase6['prepositional'] = {}
    st.session_state.phase6['analysis_completed'] = False
    st.session_state.phase6['replacements_applied'] = False
    st.session_state.phase6['processed_texts'] = []
    st.session_state.phase6['replacements'] = []
    # edited_texts пока не трогаем, пусть остаются старые до следующего применения замен

    # Запускаем анализ
    with st.spinner("Анализ изменённых текстов..."):
        success = analyze_texts(syn_manager, stop_manager)
        if success:
            st.success("✅ Анализ изменённых текстов выполнен. Теперь вы можете выбрать другие n-граммы и снова применить замены.")
            # Не сбрасываем выбранные n-граммы (они остаются в SelectionManager)
            return True
        else:
            st.error("Ошибка при повторном анализе")
def render_ngrams_table(ngrams_data: Dict, ngram_type: ReplacementType, title: str,
                        syn_manager, selection_manager):
    """Заглушка - используйте render_static_ngrams_table вместо этой функции"""
    # Перенаправляем на новую функцию
    render_static_ngrams_table(ngrams_data, ngram_type, title, syn_manager, selection_manager)
def export_simple_results(original_texts, edited_texts, replacements):
    """Простой экспорт результатов"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Создаем DataFrame для экспорта
    export_data = []
    for i, (orig, edited) in enumerate(zip(original_texts, edited_texts)):
        text_replacements = [r for r in replacements if r.get('text_index') == i]
        export_data.append({
            'Номер': i + 1,
            'Оригинал': orig,
            'Результат': edited,
            'Количество замен': len(text_replacements),
            'Список замен': '; '.join([f"{r.get('original')}→{r.get('new')}" for r in text_replacements[:5]])
        })

    df = pd.DataFrame(export_data)

    # Кнопка скачивания
    csv = df.to_csv(index=False, encoding='utf-8-sig')
    st.download_button(
        label="📥 Скачать CSV",
        data=csv,
        file_name=f"phase6_results_{timestamp}.csv",
        mime="text/csv",
        key="download_csv"
    )


def save_without_replacements(context=None):
    """Сохраняет данные из фазы 5 напрямую в phase6/phase7 без каких-либо замен"""

    log("=" * 60)
    log("🔍 save_without_replacements CALLED")

    if context is None:
        log("❌ save_without_replacements: Нет контекста!", "ERROR")
        return False

    # Загружаем тексты
    texts, metadata = load_texts_from_phase5(force_reload=True, context=context)

    if not texts:
        log("❌ Нет текстов из фазы 5", "ERROR")
        return False

    log(f"✅ Загружено {len(texts)} текстов из фазы 5")

    # ✅ СОХРАНЯЕМ В app_data
    if 'app_data' not in st.session_state:
        st.session_state.app_data = {}

    if 'phase6' not in st.session_state.app_data:
        st.session_state.app_data['phase6'] = {}

    st.session_state.app_data['phase6']['texts'] = texts
    st.session_state.app_data['phase6']['original_texts'] = texts.copy()
    st.session_state.app_data['phase6']['processed_texts'] = texts.copy()
    st.session_state.app_data['phase6']['edited_texts'] = texts.copy()
    st.session_state.app_data['phase6']['texts_metadata'] = metadata
    st.session_state.app_data['phase6']['replacements'] = []
    st.session_state.app_data['phase6']['replacements_applied'] = False
    st.session_state.app_data['phase6']['analysis_completed'] = False

    # Очищаем результаты анализа в app_data
    for key in ['unigrams', 'bigrams', 'trigrams', 'ngrams', 'prepositional']:
        st.session_state.app_data['phase6'][key] = {}

    # Также сохраняем в session_state для UI
    st.session_state.phase6['texts'] = texts
    st.session_state.phase6['original_texts'] = texts.copy()
    st.session_state.phase6['processed_texts'] = texts.copy()
    st.session_state.phase6['edited_texts'] = texts.copy()
    st.session_state.phase6['texts_metadata'] = metadata
    st.session_state.phase6['replacements'] = []
    st.session_state.phase6['replacements_applied'] = False
    st.session_state.phase6['analysis_completed'] = False

    for key in ['unigrams', 'bigrams', 'trigrams', 'ngrams', 'prepositional']:
        st.session_state.phase6[key] = {}

    log(f"   ✅ Сохранено в app_data: processed_texts={len(texts)}")

    # ✅ ПРИНУДИТЕЛЬНО СОХРАНЯЕМ В ФАЙЛ
    try:
        if context is not None and hasattr(context, 'save'):
            context.save()
            log(f"   ✅ Сохранено через context")
        elif 'app_state' in st.session_state:
            st.session_state.app_state.save_project()
            log(f"   ✅ Сохранено через app_state")
        else:
            # Сохраняем через domain_manager
            if 'domain_manager' in st.session_state:
                dm = st.session_state.domain_manager
                user_id = st.session_state.get('user_id')
                project_id = st.session_state.get('current_project_id')
                if user_id and project_id:
                    from pathlib import Path
                    import json
                    project_file = Path(f"sites/{dm.site_name}/domains/{dm.get_current_domain()}/projects/{user_id}/{project_id}.json")
                    if project_file.exists():
                        with open(project_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        data['app_data'] = st.session_state.app_data
                        data['updated_at'] = datetime.now().isoformat()
                        with open(project_file, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        log(f"   ✅ Сохранено через прямой доступ к файлу")
    except Exception as e:
        log(f"   ⚠️ Ошибка сохранения: {e}", "WARNING")

    log(f"✅ Сохранено без замен: {len(texts)} текстов")
    st.success(f"✅ Сохранено {len(texts)} текстов без синонимизации!")
    st.balloons()

    log("=" * 60)
    return True
def verify_phase6_data():
    """Проверяет, правильно ли сохранены данные для фазы 7"""

    if 'app_data' not in st.session_state:
        st.error("❌ Нет app_data в session_state")
        return False

    phase6_data = st.session_state.app_data.get('phase6', {})

    if not phase6_data:
        st.error("❌ Нет phase6 данных в app_data")
        return False

    # Проверяем наличие ключей
    required_keys = ['results', 'processed_texts', 'original_texts']
    missing_keys = [key for key in required_keys if key not in phase6_data]

    if missing_keys:
        st.error(f"❌ Отсутствуют ключи в phase6_data: {missing_keys}")
        return False

    results = phase6_data.get('results', {})
    if not results:
        st.error("❌ Нет results в phase6_data")
        return False

    # Показываем статистику
    st.success(f"✅ Данные проверены:")
    st.write(f"- Количество результатов: {len(results)}")
    st.write(f"- Количество обработанных текстов: {len(phase6_data.get('processed_texts', []))}")
    st.write(f"- Количество замен: {phase6_data.get('statistics', {}).get('total_replacements', 0)}")

    return True


'''def render_text_list():
    """Навигация и фильтры (без превью)"""
    processed = st.session_state.phase6.get('processed_texts', [])
    replacements = st.session_state.phase6.get('replacements', [])
    edited = st.session_state.phase6.get('edited_texts', processed.copy())

    if not processed:
        st.info("Нет текстов")
        return 0

    st.subheader(f"📋 Результаты синонимизации ({len(processed)} текстов)")

    col1, col2, col3, col4 = st.columns([2, 3, 2, 2])

    with col1:
        go_to = st.number_input(
            "Перейти к тексту №",
            min_value=1,
            max_value=len(processed),
            value=st.session_state.phase6.get('current_text_index', 0) + 1,
            key="go_to_number"
        )

    with col2:
        search = st.text_input("🔍 Поиск", "", placeholder="слово или фраза...", key="search_results")

    with col3:
        filter_type = st.selectbox(
            "Фильтр",
            ["Все", "С заменами", "Без замен", "Изменены"],
            key="result_filter"
        )

    with col4:
        st.metric("Всего", len(processed))

    # Фильтрация
    filtered_indices = list(range(len(processed)))

    if search:
        s = search.lower()
        filtered_indices = [i for i in filtered_indices if s in edited[i].lower() or s in processed[i].lower()]

    if filter_type == "С заменами":
        filtered_indices = [i for i in filtered_indices if any(r.get('text_index') == i for r in replacements)]
    elif filter_type == "Без замен":
        filtered_indices = [i for i in filtered_indices if not any(r.get('text_index') == i for r in replacements)]
    elif filter_type == "Изменены":
        filtered_indices = [i for i in filtered_indices if edited[i] != processed[i]]

    if not filtered_indices:
        st.warning("Ничего не найдено по фильтрам")
        return 0

    current_idx = go_to - 1
    if current_idx not in filtered_indices:
        current_idx = filtered_indices[0]

    st.session_state.phase6['current_text_index'] = current_idx

    # Навигация
    pos = filtered_indices.index(current_idx)
    c1, c2, c3 = st.columns([1, 4, 1])

    with c1:
        if st.button("← Предыдущий", use_container_width=True, disabled=pos == 0, key="prev_btn"):
            st.session_state.phase6['current_text_index'] = filtered_indices[pos-1]
            st.rerun()

    with c2:
        st.markdown(
            f"<div style='text-align:center; padding:10px;'>"
            f"<b>Текст {current_idx + 1} / {len(processed)}</b> "
            f"({pos + 1} из {len(filtered_indices)})</div>",
            unsafe_allow_html=True
        )

    with c3:
        if st.button("Следующий →", use_container_width=True, disabled=pos == len(filtered_indices)-1, key="next_btn"):
            st.session_state.phase6['current_text_index'] = filtered_indices[pos+1]
            st.rerun()

    return current_idx'''


def render_results():
    """Отображение результатов с подсветкой замен и опциональным редактированием"""
    st.header("✨ Результаты синонимизации")

    processed = st.session_state.phase6.get('processed_texts', [])
    original_texts = st.session_state.phase6.get('original_texts', [])
    replacements = st.session_state.phase6.get('replacements', [])
    edited_texts = st.session_state.phase6.get('edited_texts', processed.copy())

    if not processed:
        st.info("Нет результатов")
        return

    # ====================== ФИЛЬТРЫ ======================
    col1, col2, col3, col4 = st.columns([3, 2, 2, 2])

    with col1:
        search = st.text_input("🔍 Поиск по тексту", "", placeholder="Введите слово...", key="search_all")

    with col2:
        filter_type = st.selectbox(
            "Фильтр",
            ["Все тексты", "С заменами", "Без замен", "Изменены вручную"],
            key="filter_all"
        )

    with col3:
        page_size = st.selectbox("Текстов на странице", [5, 10, 20, 30], index=1, key="page_size")

    with col4:
        total_replacements = len(replacements)
        st.metric("Всего замен", total_replacements)

    # ====================== ФИЛЬТРАЦИЯ ======================
    indices = list(range(len(processed)))

    if search:
        s = search.lower()
        indices = [i for i in indices if s in edited_texts[i].lower() or s in original_texts[i].lower()]

    if filter_type == "С заменами":
        indices = [i for i in indices if any(r.get('text_index') == i for r in replacements)]
    elif filter_type == "Без замен":
        indices = [i for i in indices if not any(r.get('text_index') == i for r in replacements)]
    elif filter_type == "Изменены вручную":
        indices = [i for i in indices if edited_texts[i] != processed[i]]

    if not indices:
        st.warning("Ничего не найдено по заданным фильтрам")
        return

    # ====================== ПАГИНАЦИЯ ======================
    total_pages = (len(indices) - 1) // page_size + 1
    current_page = st.session_state.get('results_current_page', 1)

    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        current_page = st.number_input("Страница", 1, total_pages, current_page, key="results_page", label_visibility="collapsed")

    st.session_state.results_current_page = current_page

    start = (current_page - 1) * page_size
    end = start + page_size
    current_page_indices = indices[start:end]

    st.markdown(f"**Показаны тексты {start+1}–{min(end, len(indices))} из {len(indices)}**")
    st.markdown("---")

    # ====================== ОТОБРАЖЕНИЕ ТЕКСТОВ ======================
    for idx in current_page_indices:
        text_replacements = [r for r in replacements if r.get('text_index') == idx]
        current_edited = edited_texts[idx]
        replacements_count = len(text_replacements)

        # Заголовок с информацией
        with st.container():
            st.markdown(f"### 📄 Текст {idx + 1}")

            # Статистика замен
            if replacements_count > 0:
                st.markdown(f"**🔄 Выполнено замен: {replacements_count}**")

                # Показываем список замен в компактном виде
                replacement_list = []
                for r in text_replacements[:10]:
                    replacement_list.append(f"`{r.get('original', '')}` → `{r.get('new', '')}`")
                if len(text_replacements) > 10:
                    replacement_list.append(f"... и ещё {len(text_replacements) - 10} замен")

                st.markdown("**Что было заменено:**")
                st.markdown(", ".join(replacement_list))
            else:
                st.info("ℹ️ В этом тексте нет замен")

            st.markdown("---")

            # Две колонки: Оригинал и Результат с подсветкой
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**📝 Оригинал**")
                st.text_area(
                    f"original_{idx}",
                    original_texts[idx],
                    height=300,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"orig_view_{idx}"
                )

            with col2:
                st.markdown("**✨ Результат (с подсветкой замен)**")

                # Подсветка замен
                if text_replacements:
                    highlighted = highlight_replacements(current_edited, text_replacements)
                    st.markdown(
                        f'<div class="text-container" style="height:300px; overflow-y:auto; margin-bottom:10px;">{highlighted}</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f'<div class="text-container" style="height:300px; overflow-y:auto; margin-bottom:10px;">{current_edited}</div>',
                        unsafe_allow_html=True
                    )

            # Кнопка редактирования (по желанию пользователя)
            st.markdown("---")
            edit_key = f"edit_toggle_{idx}"

            # Используем expander для опционального редактирования
            with st.expander("✏️ Редактировать этот текст", expanded=False):
                edited = st.text_area(
                    f"Редактируемая версия",
                    current_edited,
                    height=250,
                    key=f"editor_{idx}",
                    label_visibility="collapsed"
                )

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button(f"💾 Сохранить изменения", key=f"save_{idx}", use_container_width=True):
                        if edited != current_edited:
                            st.session_state.phase6['edited_texts'][idx] = edited
                            st.toast(f"✅ Изменения в тексте {idx+1} сохранены", icon="💾")
                            st.rerun()
                with col_cancel:
                    if st.button(f"❌ Отмена", key=f"cancel_{idx}", use_container_width=True):
                        st.rerun()

            st.markdown("---")

    # Кнопки внизу страницы
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🔄 Сбросить все правки", key="reset_all_results", use_container_width=True):
            st.session_state.phase6['edited_texts'] = processed.copy()
            st.rerun()

    with col2:
        if st.button("📊 Показать статистику замен", key="show_stats", use_container_width=True):
            # Статистика по типам замен
            unigram_count = sum(1 for r in replacements if r.get('type') == 'unigram')
            bigram_count = sum(1 for r in replacements if r.get('type') == 'bigram')
            trigram_count = sum(1 for r in replacements if r.get('type') == 'trigram')
            ngram_count = sum(1 for r in replacements if r.get('type') == 'ngram')
            prep_count = sum(1 for r in replacements if r.get('type') == 'prepositional')

            st.info(
                f"📊 **Статистика замен:**\n\n"
                f"• Слова (униграммы): {unigram_count}\n"
                f"• Биграммы: {bigram_count}\n"
                f"• Триграммы: {trigram_count}\n"
                f"• N-граммы: {ngram_count}\n"
                f"• Фразы с предлогами: {prep_count}\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"**Всего: {len(replacements)} замен**"
            )

    with col3:
        if st.button("💾 Сохранить всё в фазу 7", type="primary", key="save_all_to_phase7", use_container_width=True):
            if save_to_phase7():
                st.success("✅ Все изменения сохранены!")
                st.balloons()

    with col4:
        if st.button("📥 Экспорт CSV", key="export_csv_results", use_container_width=True):
            export_simple_results(original_texts, st.session_state.phase6['edited_texts'], replacements)
def render_text_navigator(current_idx: int, total: int, replacements_count: int) -> Tuple[int, bool]:
    """Рендер панели навигации с кнопками предыдущий/следующий"""

    # Индикатор прогресса
    progress = (current_idx + 1) / total if total > 0 else 0

    col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])

    with col1:
        prev_clicked = st.button("◀◀ Предыдущий", key="nav_prev", use_container_width=True)

    with col2:
        # Отображение текущего номера
        st.markdown(f"<div style='text-align: center; padding: 8px;'><b>📄 {current_idx + 1} / {total}</b></div>",
                    unsafe_allow_html=True)

    with col3:
        # Прогресс-бар
        st.progress(progress, text=f"Просмотрено {current_idx + 1} из {total} текстов")

    with col4:
        next_clicked = st.button("Следующий ▶▶", key="nav_next", use_container_width=True)

    with col5:
        # Отображаем количество замен в текущем тексте
        if replacements_count > 0:
            st.markdown(f"<div style='text-align: center; padding: 8px; color: #27ae60;'><b>🔄 {replacements_count} замен</b></div>",
                        unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='text-align: center; padding: 8px; color: #999;'><b>🔄 нет замен</b></div>",
                        unsafe_allow_html=True)

    return prev_clicked, next_clicked
def highlight_replacements(text: str, replacements: List[Dict]) -> str:
    """Подсвечивает замененные фразы в тексте HTML"""
    if not replacements:
        return text

    # Сортируем замены по длине (сначала длинные, чтобы не было конфликтов)
    sorted_replacements = sorted(replacements, key=lambda x: len(x.get('new', '')), reverse=True)

    highlighted = text
    for r in sorted_replacements:
        original = r.get('original', '')
        new_word = r.get('new', '')
        if new_word and new_word in highlighted:
            # Создаем тултип с информацией о замене
            tooltip = f"Было: {original} | Тип: {r.get('type', 'unknown')}"
            if r.get('used_synonym'):
                tooltip += f" | Синоним: {r.get('used_synonym')}"

            # Заменяем на подсвеченную версию
            highlighted = highlighted.replace(
                new_word,
                f'<span class="replacement-highlight" title="{tooltip}">{new_word}</span>'
            )

    return highlighted
# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================

def main(app_state=None, auto_mode=False, settings_mode=False, context=None):
    """Главная функция фазы 6"""
    load_css()

    # ✅ ДОБАВИТЬ СИНХРОНИЗАЦИЮ ДОМЕНА ИЗ ФАЙЛА
    if 'domain_manager' not in st.session_state:
        from domain_manager import DomainManager
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    user_id = st.session_state.get('user_id')

    if user_id:
        settings = dm.load_user_settings(user_id)
        saved_domain = settings.get('selected_domain', 'default')
        saved_site = settings.get('selected_site', 'steelborg')

        # Обновляем session_state
        st.session_state.current_domain = saved_domain
        st.session_state.selected_domain = saved_domain
        st.session_state.current_site = saved_site
        st.session_state.selected_site = saved_site
        st.session_state[f'domain_system_{saved_site}'] = saved_domain

        print(f"✅ Phase6 загружен домен из файла: {saved_domain}")

    # ===== ПРОВЕРКА СМЕНЫ ПРОЕКТА =====
    current_project_id = st.session_state.get('current_project_id')
    last_loaded = st.session_state.get('phase6_last_loaded_project')

    if current_project_id and last_loaded != current_project_id:
        # ... остальной код без изменений ...

        # ... остальной код без изменений ...
        # Проект изменился - очищаем данные Phase 6
        log(f"🔄 Смена проекта: {last_loaded} → {current_project_id}")

        # Очищаем данные в session_state
        if 'phase6' in st.session_state:
            st.session_state.phase6 = {
                'initialized': True,
                'texts': [],
                'original_texts': [],
                'processed_texts': [],
                'edited_texts': [],
                'replacements': [],
                'unigrams': {},
                'bigrams': {},
                'trigrams': {},
                'ngrams': {},
                'prepositional': {},
                'analysis_completed': False,
                'replacements_applied': False,
                'texts_metadata': [],
                'min_count': 3,
                'last_loaded_project_for_selections': current_project_id
            }

        # Очищаем результаты
        for key in ['phase6_results', 'phase6_processed_texts', 'phase6_original_texts']:
            if key in st.session_state:
                del st.session_state[key]

        # Обновляем ID проекта
        st.session_state.phase6_last_loaded_project = current_project_id
        st.session_state.phase6_initialized = False

        log(f"✅ Phase 6 очищена для нового проекта {current_project_id}")
    # ===== КОНЕЦ ПРОВЕРКИ =====

    if context is None:
        log("❌ main() вызвана без context", "ERROR")
        return {
            'success': False,
            'message': 'Нет контекста',
            'error': 'context is None'
        }



    log(f"📌 main() получила context: project_id={context.project_id}, user_id={context.user_id}")

    if auto_mode:
        st.session_state.auto_mode = True

    if 'domain_manager' not in st.session_state:
        st.session_state.domain_manager = DomainManager()

    dm = st.session_state.domain_manager
    st.info(f"🌐 Текущий домен: **{dm.get_domain_display_name()}**")

    # ✅ ИНИЦИАЛИЗИРУЕМ (НЕ ПЕРЕЗАПИСЫВАЕТ СУЩЕСТВУЮЩИЕ ДАННЫЕ)
    init_phase6_structure(context)

    # ✅ ЗАГРУЖАЕМ ТЕКСТЫ ТОЛЬКО ЕСЛИ ИХ НЕТ
    if not st.session_state.phase6.get('texts'):
        texts, metadata = load_texts_from_phase5(force_reload=False, context=context)
        if texts:
            st.session_state.phase6['texts'] = texts
            st.session_state.phase6['original_texts'] = texts.copy()
            st.session_state.phase6['texts_metadata'] = metadata
            st.success(f"✅ Загружено {len(texts)} текстов из фазы 5")
        else:
            st.warning("⚠️ Нет текстов из фазы 5. Сначала выполните фазу 5.")
            return

    # ... остальной код ...

    # ✅ ЗАГРУЖАЕМ ТЕКСТЫ ОДИН РАЗ
    texts, metadata = load_texts_from_phase5(force_reload=False, context=context)

    # ✅ ПОЛУЧАЕМ ctx_data ДЛЯ ПРОВЕРКИ
    ctx_data = _get_context_data(context, st.session_state)

    # СОЗДАЕМ МЕНЕДЖЕРЫ
    try:
        syn_manager = FastSynonymManager("synonyms.json")
        stop_manager = StopWordManager(syn_manager)

        if ctx_data['has_context'] and context is not None:
            selection_manager = SelectionManager(
                project_id=context.project_id,
                user_id=context.user_id,
                site_name=context.site_name,
                domain_name=context.domain_name,
                context=context
            )
        else:
            selection_manager = SelectionManager(
                project_id=st.session_state.get('current_project_id'),
                user_id=st.session_state.get('user_id')
            )

        st.session_state.selection_manager = selection_manager
        log("✅ Менеджеры успешно созданы")
    except Exception as e:
        log(f"❌ Ошибка инициализации менеджеров: {e}", "ERROR")
        st.error(f"❌ Ошибка загрузки синонимов: {e}")
        return

    # Если тексты загружены
    if texts:
        st.session_state.phase6['texts'] = texts
        st.session_state.phase6['original_texts'] = texts.copy()
        st.session_state.phase6['texts_metadata'] = metadata
        st.success(f"✅ Загружено {len(texts)} текстов из фазы 5")
    else:
        st.warning("⚠️ Нет текстов из фазы 5. Сначала выполните фазу 5.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Вернуться к фазе 5"):
                st.session_state.current_phase = 5
                st.rerun()
        return

    # === ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ ВКЛАДОК ===
    if 'phase6_current_tab' not in st.session_state:
        st.session_state.phase6_current_tab = "⚙️ Настройки"

    if 'pending_selections' not in st.session_state:
        st.session_state.pending_selections = {}

    if 'unsaved_changes' not in st.session_state:
        st.session_state.unsaved_changes = False

    # === БОКОВАЯ ПАНЕЛЬ ===
    with st.sidebar:
        st.markdown("### 🎯 Быстрые действия")
        st.divider()
        st.markdown("### 🔄 Обновление данных")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Загрузить из фазы 5", use_container_width=True, type="secondary"):
                with st.spinner("Загружаем свежие тексты из фазы 5..."):
                    texts, metadata = load_texts_from_phase5(force_reload=True, context=context)
                    if texts:
                        st.success(f"✅ Загружено {len(texts)} текстов")
                        st.rerun()
                    else:
                        st.error("Не удалось загрузить тексты")

        with col2:
            if st.button("🗑️ Полный сброс фазы 6", use_container_width=True):
                if 'phase6' in st.session_state:
                    st.session_state.phase6.clear()
                init_phase6_structure(context)
                st.success("Фаза 6 полностью сброшена")
                st.rerun()

        # Подсчёт выбранных фраз
        total_selected = 0
        for ntype in ['unigram', 'bigram', 'trigram', 'ngram', 'prepositional']:
            data = st.session_state.phase6.get(f'{ntype}s', {})
            for key in data.keys():
                if selection_manager.get_selection(ntype, key, False):
                    total_selected += 1

        col1, col2 = st.columns(2)
        with col1:
            st.metric("📊 Выбрано фраз", total_selected)
        with col2:
            replacements_count = len(st.session_state.phase6.get('replacements', []))
            st.metric("🔄 Выполнено замен", replacements_count)

        st.divider()

        # Кнопки быстрых действий
        if st.button("✅ Применить замены", use_container_width=True, type="primary"):
            if st.session_state.phase6.get('analysis_completed'):
                if apply_replacements(syn_manager, stop_manager, selection_manager):
                    st.session_state.phase6_current_tab = "Результаты"
                    st.rerun()
            else:
                st.error("Сначала выполните анализ текстов")

        st.sidebar.divider()
        st.sidebar.markdown("### 💾 Сохранение результата")

        has_results = (
                st.session_state.phase6.get('processed_texts') or
                st.session_state.phase6.get('edited_texts')
        )

        if has_results:
            if st.sidebar.button("💾 **Сохранить в фазу 7**",
                                 type="primary",
                                 use_container_width=True,
                                 key="sidebar_save_to_phase7"):
                if save_to_phase7(context=context):
                    st.sidebar.success("✅ Сохранено в фазу 7!")
                    st.balloons()
                else:
                    st.sidebar.error("❌ Ошибка сохранения")
        else:
            st.sidebar.info("Примените замены, чтобы сохранить результат")

        # Кнопка сохранения без замен
        if not st.session_state.phase6.get('replacements_applied'):
            if st.sidebar.button("⏭️ Сохранить **без** синонимизации",
                                 use_container_width=True,
                                 key="sidebar_save_without"):
                if save_without_replacements(context=context):
                    st.success("✅ Тексты сохранены без замен")
                    st.balloons()

        if st.button("📊 Статистика", use_container_width=True):
            show_quick_statistics(replacements_count, total_selected)

        st.divider()

        # Индикатор несохранённых изменений
        if st.session_state.unsaved_changes:
            st.warning("⚠️ Есть несохранённые изменения")
            if st.button("💾 Сохранить всё", use_container_width=True):
                save_to_phase7(context=context)
                st.session_state.unsaved_changes = False
                st.success("✅ Сохранено!")
                st.rerun()

        # Прогресс
        if total_selected > 0:
            st.progress(min(1.0, replacements_count / max(1, total_selected)))

        st.divider()
        st.caption(f"💡 Совет: редактируйте синонимы в отдельной вкладке")
        st.divider()

        # Индикатор выбранных фраз по типам
        if total_selected > 0:
            st.markdown("### 📋 Выбранные фразы")
            type_counts = {'unigram': 0, 'bigram': 0, 'trigram': 0, 'ngram': 0, 'prepositional': 0}
            for ntype in type_counts.keys():
                data = st.session_state.phase6.get(f'{ntype}s', {})
                for key in data.keys():
                    if selection_manager.get_selection(ntype, key, False):
                        type_counts[ntype] += 1

            st.caption(f"📊 Униграммы: {type_counts['unigram']}")
            st.caption(f"🔤 Биграммы: {type_counts['bigram']}")
            st.caption(f"📚 Триграммы: {type_counts['trigram']}")
            st.caption(f"🔠 N-граммы: {type_counts['ngram'] + type_counts['prepositional']}")

            if st.button("✏️ Перейти к редактору", use_container_width=True):
                st.session_state.phase6_current_tab = "✏️ Редактор синонимов"
                st.rerun()

    # === НАВИГАЦИЯ ПО ВКЛАДКАМ ===
    tab_options = ["⚙️ Настройки", "📊 Выбор n-грамм", "✏️ Редактор синонимов", "✨ Результаты"]
    try:
        current_index = tab_options.index(st.session_state.phase6_current_tab)
    except ValueError:
        current_index = 0
        st.session_state.phase6_current_tab = tab_options[0]

    # ✅ ОДИН РАДИО (НЕ ДВА!)
    current_tab = st.radio(
        "Навигация по вкладкам",
        tab_options,
        index=tab_options.index(st.session_state.phase6_current_tab),
        horizontal=True,
        label_visibility="collapsed",
        key="phase6_tab_radio"
    )

    if current_tab != st.session_state.phase6_current_tab:
        st.session_state.phase6_current_tab = current_tab

    st.divider()

    # ✅ РЕНДЕРИНГ ВЫБРАННОЙ ВКЛАДКИ С ПЕРЕДАЧЕЙ CONTEXT
    if current_tab == "⚙️ Настройки":
        render_settings_tab(syn_manager, stop_manager, selection_manager, context=context)
    elif current_tab == "📊 Выбор n-грамм":
        render_selection_tab(syn_manager, stop_manager, selection_manager, context=context)  # ← ДОБАВЛЕН context
    elif current_tab == "✏️ Редактор синонимов":
        render_synonym_editor_tab(syn_manager, stop_manager, context=context)
    elif current_tab == "✨ Результаты":
        render_results_tab(context=context)

    # === ПРОВЕРКА СМЕНЫ ПРОЕКТА ===
    current_project_id = st.session_state.get('current_project_id')
    last_project_id = st.session_state.phase6.get('last_loaded_project_for_selections')

    if current_project_id != last_project_id:
        st.session_state.selection_manager = SelectionManager(
            project_id=current_project_id,
            user_id=st.session_state.get('user_id')
        )
        st.session_state.phase6['last_loaded_project_for_selections'] = current_project_id
        log(f"🔄 SelectionManager пересоздан для проекта {current_project_id}")

    if auto_mode:
        return {
            'success': True,
            'message': 'Фаза 6 выполнена',
            'replacements_applied': st.session_state.phase6.get('replacements_applied', False)
        }
# ==================== НОВЫЕ ФУНКЦИИ ДЛЯ УЛУЧШЕННОГО UX ====================

def render_settings_tab(syn_manager, stop_manager, selection_manager, context=None):
    """Вкладка настроек — с дополнительной кнопкой в авторежиме"""
    st.subheader("⚙️ Настройки синонимизации")

    col1, col2 = st.columns(2)

    with col1:
        min_count = st.slider(
            "Минимальная частота для отображения:",
            min_value=1, max_value=20,
            value=st.session_state.phase6.get('min_count', 3),
            key="min_count_slider"
        )
        if min_count != st.session_state.phase6.get('min_count', 3):
            st.session_state.phase6['min_count'] = min_count
            st.session_state.phase6['analysis_completed'] = False

    with col2:
        if st.session_state.phase6.get('analysis_completed'):
            st.success("✅ Анализ выполнен")
        else:
            st.warning("⚠️ Анализ не выполнен")

    st.divider()
    st.markdown("### 🛠️ Основные действия")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🔍 Выполнить анализ", type="primary", use_container_width=True):
            if analyze_texts(syn_manager, stop_manager):
                st.success("✅ Анализ завершён!")
                st.rerun()

    with col2:
        if st.button("💾 Сохранить без замен", use_container_width=True):
            if save_without_replacements(context=context):
                st.success("✅ Сохранено без замен")
                st.balloons()

    with col3:
        if st.button("🔄 Сбросить все замены", use_container_width=True):
            reset_all_replacements(selection_manager)
            st.rerun()

    with col4:
        if st.button("🗑️ Очистить выбор", use_container_width=True):
            selection_manager.clear_selections()
            st.success("✅ Выбор очищен")
            st.rerun()

    # ==================== КНОПКА ТОЛЬКО ДЛЯ АВТОРЕЖИМА ====================
    if st.session_state.get('auto_mode', False):   # проверяем, что мы в авторежиме
        st.divider()
        st.markdown("### 🔧 Специальные действия для авторежима")
        if st.button("🔄 Принудительно обновить интерфейс",
                     type="secondary",
                     use_container_width=True,
                     key="force_refresh_auto"):
            if 'app_data' in st.session_state and 'force_sync_all_data' in dir(st.session_state.app_data):
                st.session_state.app_data.force_sync_all_data()
            st.session_state.phase6['analysis_completed'] = True
            st.success("✅ Интерфейс принудительно обновлён")
            st.rerun()

    st.divider()
    # ... остальной код вкладки настроек (итеративная синонимизация и т.д.) оставь как был ...
    st.markdown("### 🔄 Итеративная синонимизация")

    if st.session_state.phase6.get('processed_texts'):
        if st.button("🔄 Продолжить синонимизацию", use_container_width=True,
                     help="Повторный анализ изменённых текстов"):
            if reanalyze_with_edited_texts(syn_manager, stop_manager, selection_manager):
                st.success("✅ Анализ выполнен! Выберите новые фразы.")
                st.rerun()

    # Отображение логов (опционально)
    # Стало (хорошо):
    with st.expander("📋 Логи выполнения", expanded=False):
        logs = st.session_state.get('phase6_logs', [])
        if logs:
            st.text_area(
                "Журнал выполнения",  # ← Добавлен осмысленный label
                value="\n".join(logs[-20:]),
                height=200,
                disabled=True,
                label_visibility="collapsed"  # Скрываем визуально
            )


def render_selection_tab(syn_manager, stop_manager, selection_manager, context=None):
    """Вкладка выбора n-грамм - оптимизированная версия"""
    st.subheader("📊 Выбор n-грамм для замены")

    # ✅ ОТЛАДКА: логируем состояние
    log(f"🔍 render_selection_tab: analysis_completed = {st.session_state.phase6.get('analysis_completed')}")
    log(f"   unigrams count: {len(st.session_state.phase6.get('unigrams', {}))}")
    log(f"   bigrams count: {len(st.session_state.phase6.get('bigrams', {}))}")
    log(f"   trigrams count: {len(st.session_state.phase6.get('trigrams', {}))}")

    # Проверка: выполнен ли анализ
    if not st.session_state.phase6.get('analysis_completed'):
        log(f"⚠️ Анализ не выполнен!")
        st.warning("⚠️ Сначала выполните анализ текстов на вкладке «Настройки»")
        if st.button("🔍 Перейти к анализу"):
            st.session_state.phase6_current_tab = "Настройки"
            st.rerun()
        return

    log(f"✅ Анализ выполнен, отображаем n-граммы")

    # Типы n-грамм для отображения
    ngram_types = [
        (ReplacementType.UNIGRAM, "слова", st.session_state.phase6.get('unigrams', {})),
        (ReplacementType.BIGRAM, "биграммы", st.session_state.phase6.get('bigrams', {})),
        (ReplacementType.TRIGRAM, "триграммы", st.session_state.phase6.get('trigrams', {})),
        (ReplacementType.NGRAM, "n-граммы (4-6 слов)", st.session_state.phase6.get('ngrams', {})),
        (ReplacementType.PREPOSITIONAL, "фразы с предлогами", st.session_state.phase6.get('prepositional', {}))
    ]

    # Проверяем, есть ли данные
    has_data = False
    for ngram_type, title, data in ngram_types:
        if data:
            has_data = True
            log(f"   {title}: {len(data)} шт")

    if not has_data:
        log(f"⚠️ Нет данных для отображения!")
        st.warning("⚠️ Нет данных для отображения. Попробуйте выполнить анализ заново.")
        if st.button("🔄 Повторить анализ"):
            st.session_state.phase6_current_tab = "Настройки"
            st.rerun()
        return

    # Используем expander для каждого типа
    for ngram_type, title, data in ngram_types:
        if data:
            log(f"📖 Отображаем {title}: {len(data)} шт")
            with st.expander(f"📖 {title.capitalize()} ({len(data)} шт.)", expanded=False):
                render_static_ngrams_table(
                    data, ngram_type, title,
                    syn_manager, selection_manager
                )

    # Кнопка применения внизу
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("✅ Применить выбранные замены", type="primary", use_container_width=True):
            if apply_replacements(syn_manager, stop_manager, selection_manager):
                st.success("✅ Замены применены! Перейдите на вкладку «Результаты»")
                st.balloons()
                st.rerun()

def render_static_ngrams_table(ngrams_data: Dict, ngram_type: ReplacementType, title: str,
                               syn_manager, selection_manager):
    """Статическая таблица с чекбоксами"""

    log(f"🔍 render_static_ngrams_table: {title}, data count: {len(ngrams_data)}")

    if not ngrams_data:
        st.info(f"Нет данных для {title.lower()}")
        log(f"   ⚠️ Нет данных для {title}")
        return

    min_count = st.session_state.phase6.get('min_count', 3)
    type_str = ngram_type.value

    # Подготовка данных
    items_list = []
    for key, info in ngrams_data.items():
        count = safe_get_count(info)
        if count >= min_count:
            selected = selection_manager.get_selection(type_str, key, False)
            items_list.append({
                'key': key,
                'count': count,
                'selected': selected
            })

    log(f"   После фильтрации (min_count={min_count}): {len(items_list)}")

    if not items_list:
        st.info(f"Нет {title.lower()} с частотой >= {min_count}")
        return

    items_list.sort(key=lambda x: (-x['count'], x['key']))

    # Панель управления
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        if st.button("✅ Выбрать все", key=f"{type_str}_select_all_static", use_container_width=True):
            for item in items_list:
                selection_manager.set_selection(type_str, item['key'], True)
            st.rerun()
    with col2:
        if st.button("❌ Снять все", key=f"{type_str}_deselect_all_static", use_container_width=True):
            for item in items_list:
                selection_manager.set_selection(type_str, item['key'], False)
            st.rerun()
    with col3:
        selected_count = sum(1 for item in items_list if item['selected'])
        st.metric("Выбрано", f"{selected_count}/{len(items_list)}")
    with col4:
        if st.button("✏️ Редактор", key=f"{type_str}_open_editor", use_container_width=True):
            st.session_state.phase6_current_tab = "✏️ Редактор синонимов"
            st.rerun()
    with col5:
        if st.button("💾 Сохранить выбор", key=f"{type_str}_save_static", use_container_width=True):
            st.success(f"✅ Сохранено {selected_count} фраз!")

    st.markdown("---")

    # Чекбоксы
    for i, item in enumerate(items_list):
        col_cb, col_phrase, col_count, col_edit = st.columns([0.5, 5, 1, 1.5])

        with col_cb:
            label_text = f"Выбрать: {item['key'][:50]}{'...' if len(item['key']) > 50 else ''}"
            new_val = st.checkbox(
                label=label_text,
                value=item['selected'],
                key=f"cb_{type_str}_{hash(item['key'])}_{i}",
                label_visibility="collapsed"
            )
            if new_val != item['selected']:
                selection_manager.set_selection(type_str, item['key'], new_val)
                st.session_state.unsaved_changes = True

        with col_phrase:
            phrase_display = item['key'][:70] + "..." if len(item['key']) > 70 else item['key']
            st.markdown(f"`{phrase_display}`")

        with col_count:
            st.caption(f"📊 {item['count']}")

        with col_edit:
            if st.button("✏️", key=f"quick_edit_{type_str}_{hash(item['key'])}_{i}",
                         help="Редактировать синонимы"):
                st.session_state.edit_ngram_target = item['key']
                st.session_state.edit_ngram_type_target = type_str
                st.session_state.phase6_current_tab = "✏️ Редактор синонимов"
                st.rerun()

    st.caption(f"💡 Всего {len(items_list)} фраз. Нажмите ✏️ чтобы редактировать синонимы.")
def show_quick_statistics(replacements_count, total_selected):
    """Быстрая статистика в модальном окне"""
    with st.expander("📊 Подробная статистика", expanded=True):
        st.markdown(f"**Всего замен:** {replacements_count}")
        st.markdown(f"**Выбрано фраз:** {total_selected}")

        # Статистика по типам
        replacements = st.session_state.phase6.get('replacements', [])
        type_stats = {}
        for r in replacements:
            r_type = r.get('type', 'unknown')
            type_stats[r_type] = type_stats.get(r_type, 0) + 1

        if type_stats:
            st.markdown("**По типам:**")
            for r_type, count in type_stats.items():
                st.markdown(f"- {r_type}: {count}")

        if total_selected > 0:
            completion = (replacements_count / total_selected) * 100
            st.progress(min(1.0, completion / 100))
            st.caption(f"Прогресс: {completion:.1f}%")

def render_synonym_editor_tab(syn_manager, stop_manager, context=None):  # ← ДОБАВЛЯЕМ context
    """Редактор синонимов - отображает только ВЫБРАННЫЕ пользователем фразы"""
    st.subheader("✏️ Редактор синонимов")
    st.caption("Редактируйте синонимы для выбранных фраз. Изменения сохраняются в файл synonyms.json")

    # Получаем все выбранные фразы из SelectionManager
    selection_manager = st.session_state.selection_manager

    # ... остальной код без изменений ...

    # Собираем ВСЕ выбранные фразы
    selected_phrases = []
    phrase_types = {}

    for ntype in ['unigram', 'bigram', 'trigram', 'ngram', 'prepositional']:
        data = st.session_state.phase6.get(f'{ntype}s', {})
        for key in data.keys():
            if selection_manager.get_selection(ntype, key, False):
                selected_phrases.append(key)
                phrase_types[key] = ntype

    if not selected_phrases:
        st.warning("⚠️ Нет выбранных фраз. Перейдите на вкладку «Выбор n-грамм» и отметьте фразы для замены.")

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("📊 Перейти к выбору фраз", use_container_width=True, type="primary"):
                st.session_state.phase6_current_tab = "📊 Выбор n-грамм"
                st.rerun()
        return

    # Сортируем для удобства
    selected_phrases.sort()

    # ✅ НОВОЕ: проверяем, есть ли выбранная фраза для редактирования
    target_phrase = st.session_state.get('edit_ngram_target', '')

    # Статистика выбранных фраз по типам
    st.markdown("### 📊 Выбранные фразы")

    # Подсчёт по типам
    type_counts = {}
    for phrase in selected_phrases:
        t = phrase_types.get(phrase, 'unknown')
        type_counts[t] = type_counts.get(t, 0) + 1

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📝 Всего выбрано", len(selected_phrases))
    with col2:
        st.metric("📊 Униграммы", type_counts.get('unigram', 0))
    with col3:
        st.metric("🔤 Биграммы", type_counts.get('bigram', 0))
    with col4:
        st.metric("📚 Триграммы", type_counts.get('trigram', 0))
    with col5:
        st.metric("🔠 N-граммы", type_counts.get('ngram', 0) + type_counts.get('prepositional', 0))

    st.divider()

    # Поиск ТОЛЬКО среди выбранных фраз
    search = st.text_input("🔍 Поиск среди выбранных фраз",
                           placeholder="Введите слово или фразу...",
                           value=target_phrase if target_phrase else "",
                           key="syn_search_input")

    # Фильтруем выбранные фразы по поиску
    filtered_phrases = [p for p in selected_phrases if search.lower() in p.lower()] if search else selected_phrases

    if not filtered_phrases:
        st.warning(f"Нет выбранных фраз, содержащих '{search}'")
        return

    # ✅ НОВОЕ: устанавливаем индекс на выбранную фразу (если есть)
    default_index = 0
    if target_phrase and target_phrase in filtered_phrases:
        default_index = filtered_phrases.index(target_phrase)
        st.info(f"📌 Редактирование фразы: **{target_phrase}**")

    # Выбор фразы для редактирования
    selected_idx = st.selectbox(
        "Выберите фразу для редактирования синонимов",
        range(len(filtered_phrases)),
        format_func=lambda i: f"{filtered_phrases[i][:80]}..." if len(filtered_phrases[i]) > 80 else filtered_phrases[i],
        index=default_index,
        key="phrase_selector_syn"
    )

    # Кнопки управления
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🔄 Обновить список", use_container_width=True, help="Перезагрузить список выбранных фраз"):
            st.session_state.edit_ngram_target = None
            st.rerun()
    with col2:
        if st.button("📊 К выбору фраз", use_container_width=True, help="Вернуться к выбору n-грамм"):
            st.session_state.edit_ngram_target = None
            st.session_state.phase6_current_tab = "📊 Выбор n-грамм"
            st.rerun()
    with col3:
        if st.button("🗑️ Снять все выборы", use_container_width=True, help="Очистить все выбранные фразы"):
            selection_manager.clear_selections()
            st.success("✅ Все выборы очищены")
            st.rerun()
    with col4:
        if st.button("💾 Сохранить все синонимы", use_container_width=True, type="primary"):
            save_to_phase7()
            st.success("✅ Все изменения сохранены!")

    if selected_idx is not None:
        selected_phrase = filtered_phrases[selected_idx]
        detected_type = ReplacementType(phrase_types.get(selected_phrase, 'unigram'))

        # Очищаем target после выбора
        if target_phrase == selected_phrase:
            st.session_state.edit_ngram_target = None

        st.divider()

        # Информация о фразе
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"**Фраза:** `{selected_phrase}`")
        with col2:
            st.info(f"**Тип:** `{detected_type.value}`")
        with col3:
            # Получаем частоту
            data = st.session_state.phase6.get(f'{detected_type.value}s', {})
            info = data.get(selected_phrase, {})
            count = info.get('count', 0) if isinstance(info, dict) else getattr(info, 'count', 0)
            st.info(f"**Частота:** {count}")

        # Текущие синонимы
        current_synonyms = syn_manager.get_synonyms(selected_phrase, detected_type)

        # Текстовое поле для редактирования
        st.markdown("#### 📝 Синонимы (каждый с новой строки)")
        # Используем динамический ключ, включающий выбранную фразу
        text_area_key = f"syn_edit_area_{selected_phrase}_{detected_type.value}"

        synonyms_text = st.text_area(
            "Редактирование синонимов",  # ← Добавляем осмысленный label
            value="\n".join(current_synonyms),
            height=200,
            key=text_area_key,
            help="Первый синоним - это оригинал. Добавляйте новые синонимы с новой строки.",
            label_visibility="collapsed"  # Скрываем label визуально, но он существует
        )

        # Примеры из текстов
        with st.expander("📖 Примеры использования в текстах", expanded=False):
            forms = info.get('forms', {}) if isinstance(info, dict) else getattr(info, 'forms', {})
            if forms:
                for form, count in list(forms.items())[:5]:
                    st.code(f"«{form}» (встречается {count} раз)", language="text")
            else:
                st.caption("Нет примеров")

        # Кнопки действий
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("💾 Сохранить синонимы", type="primary", use_container_width=True):
                new_synonyms = [line.strip() for line in synonyms_text.split("\n") if line.strip()]
                if selected_phrase not in new_synonyms:
                    new_synonyms.insert(0, selected_phrase)

                syn_manager.add_synonyms(selected_phrase, detected_type, new_synonyms)
                st.success(f"✅ Сохранено {len(new_synonyms)} синонимов")
                st.session_state.unsaved_changes = False
                time.sleep(0.5)
                st.rerun()

        with col2:
            if st.button("🤖 Автозаполнить формы", use_container_width=True):
                with st.spinner("Автозаполнение форм для этой фразы..."):
                    auto_fill_forms_for_phrase(selected_phrase, detected_type, syn_manager, stop_manager)
                st.success("✅ Формы заполнены!")
                st.rerun()

        with col3:
            if st.button("🔄 Сбросить к оригиналу", use_container_width=True):
                syn_manager.add_synonyms(selected_phrase, detected_type, [selected_phrase])
                st.success("✅ Сброшено к оригиналу")
                st.rerun()

        with col4:
            if st.button("📋 Копировать список", use_container_width=True):
                st.toast("Список скопирован в буфер обмена")
                st.session_state[f"syn_edit_area_main"] = synonyms_text

        st.divider()

        # Редактирование конкретных форм
        st.markdown("#### 🔤 Конкретные формы замен")
        st.caption("Настройте, как именно будет выглядеть синоним в конкретном контексте")

        render_forms_editor(selected_phrase, detected_type, syn_manager, stop_manager)

    # Статистика редактирования внизу
    st.divider()
    with st.expander("📊 Статистика выбранных фраз", expanded=False):
        # Показываем все выбранные фразы в компактном виде
        for ntype in ['unigram', 'bigram', 'trigram', 'ngram', 'prepositional']:
            phrases = [p for p in selected_phrases if phrase_types.get(p) == ntype]
            if phrases:
                st.markdown(f"**{ntype.upper()}** ({len(phrases)} шт.)")
                # Показываем только первые 10
                for p in phrases[:10]:
                    st.caption(f"  • {p[:60]}...")
                if len(phrases) > 10:
                    st.caption(f"  ... и ещё {len(phrases) - 10}")
                st.markdown("")

    st.caption("💡 **Совет:** Чтобы добавить фразы в редактор, отметьте их чекбоксами на вкладке «Выбор n-грамм».")


def render_forms_editor(phrase: str, ngram_type: ReplacementType, syn_manager, stop_manager):
    """Редактор конкретных форм"""
    # Получаем формы из текстов
    data = st.session_state.phase6.get(f'{ngram_type.value}s', {})
    info = data.get(phrase, {})
    forms_dict = info.get('forms', {}) if isinstance(info, dict) else getattr(info, 'forms', {})

    if not forms_dict:
        st.info("Нет конкретных форм для этой фразы")
        return

    # Получаем синонимы
    all_synonyms = syn_manager.get_synonyms(phrase, ngram_type)
    available_synonyms = [s for s in all_synonyms if s != phrase]

    if not available_synonyms:
        st.warning("Нет синонимов для заполнения форм")
        return

    # Выбор синонима
    selected_syn = st.selectbox(
        "Выберите синоним для настройки форм:",
        available_synonyms,
        key=f"form_syn_select"
    )

    if selected_syn:
        st.markdown(f"**Настройка форм для синонима:** `{selected_syn}`")

        # Сортируем формы по частоте
        sorted_forms = sorted(forms_dict.items(), key=lambda x: x[1], reverse=True)

        # Показываем формы с возможностью редактирования
        updated_forms = {}

        # Используем columns для компактности
        for i, (form, count) in enumerate(sorted_forms[:15]):
            col1, col2, col3 = st.columns([2, 1, 3])
            with col1:
                st.markdown(f"**{form}**")
            with col2:
                st.caption(f"({count})")
            with col3:
                current_repl = syn_manager.get_specific_form(form, selected_syn, ngram_type)
                new_repl = st.text_input(
                    "Замена:",
                    value=current_repl or "",
                    key=f"form_{phrase}_{selected_syn}_{i}",
                    label_visibility="collapsed",
                    placeholder="Оставьте пустым для автозаполнения"
                )
                if new_repl and new_repl != current_repl:
                    updated_forms[form] = new_repl

        if len(sorted_forms) > 15:
            st.caption(f"... и ещё {len(sorted_forms) - 15} форм")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Сохранить формы", use_container_width=True):
                for form, repl in updated_forms.items():
                    if repl:
                        syn_manager.set_specific_form(form, selected_syn, repl, ngram_type)
                st.success("✅ Формы сохранены")
                st.rerun()

        with col2:
            if st.button("🤖 Автозаполнить эту форму", use_container_width=True):
                with st.spinner("Автозаполнение..."):
                    replacer = FastReplacer(syn_manager, stop_manager)
                    for form, _ in sorted_forms[:20]:
                        try:
                            adapted = replacer.adapt_synonym_form(phrase, selected_syn, form, ngram_type)
                            if adapted and adapted != form:
                                syn_manager.set_specific_form(form, selected_syn, adapted, ngram_type)
                        except Exception as e:
                            log(f"Ошибка: {e}")
                st.success("✅ Формы автозаполнены")
                st.rerun()


def render_results_tab(context=None):
    """Вкладка результатов - улучшенная версия"""
    st.subheader("✨ Результаты синонимизации")

    processed = st.session_state.phase6.get('processed_texts', [])
    original_texts = st.session_state.phase6.get('original_texts', [])
    replacements = st.session_state.phase6.get('replacements', [])
    edited_texts = st.session_state.phase6.get('edited_texts', processed.copy())

    if not processed:
        st.info("Нет результатов. Сначала примените замены.")
        if st.button("🔄 Перейти к выбору фраз"):
            st.session_state.phase6_current_tab = "📊 Выбор n-грамм"
            st.rerun()
        return

    # Статистика
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📄 Всего текстов", len(processed))
    with col2:
        st.metric("🔄 Всего замен", len(replacements))
    with col3:
        texts_with_replacements = len(set(r.get('text_index', -1) for r in replacements))
        st.metric("📝 Текстов с заменами", texts_with_replacements)
    with col4:
        avg_replacements = len(replacements) / max(1, len(processed))
        st.metric("📊 Среднее замен", f"{avg_replacements:.1f}")

    st.divider()

    # Фильтры
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        search = st.text_input("🔍 Поиск по тексту", placeholder="Введите слово...", key="results_search")
    with col2:
        filter_type = st.selectbox(
            "Фильтр",
            ["Все тексты", "С заменами", "Без замен", "Изменены вручную"],
            key="results_filter"
        )
    with col3:
        page_size = st.selectbox("На странице", [3, 5, 10, 100], index=1, key="results_page_size")

    # Фильтрация
    indices = list(range(len(processed)))

    if search:
        s = search.lower()
        indices = [i for i in indices if s in edited_texts[i].lower() or s in original_texts[i].lower()]

    if filter_type == "С заменами":
        indices = [i for i in indices if any(r.get('text_index') == i for r in replacements)]
    elif filter_type == "Без замен":
        indices = [i for i in indices if not any(r.get('text_index') == i for r in replacements)]
    elif filter_type == "Изменены вручную":
        indices = [i for i in indices if edited_texts[i] != processed[i]]

    if not indices:
        st.warning("Ничего не найдено")
        return

    # Пагинация
    total_pages = (len(indices) - 1) // page_size + 1
    page = st.number_input("Страница", 1, total_pages, 1, key="results_page")

    start = (page - 1) * page_size
    end = start + page_size

    # Отображение текстов
    for idx in indices[start:end]:
        with st.container():
            st.markdown(f"### 📄 Текст {idx + 1}")

            text_replacements = [r for r in replacements if r.get('text_index') == idx]

            if text_replacements:
                with st.expander(f"🔄 Показать замены ({len(text_replacements)} шт.)", expanded=False):
                    for r in text_replacements[:10]:
                        st.markdown(f"`{r.get('original', '')}` → `{r.get('new', '')}`")
                    if len(text_replacements) > 10:
                        st.caption(f"... и ещё {len(text_replacements) - 10} замен")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**📝 Оригинал**")
                # Стало:
                st.text_area(
                    f"Оригинальный текст {idx+1}",  # ← Добавлен осмысленный label
                    original_texts[idx],
                    height=250,
                    disabled=True,
                    key=f"orig_display_{idx}",
                    label_visibility="collapsed"
                )

            with col2:
                st.markdown("**✨ Результат**")

                # Подсветка замен
                if text_replacements:
                    highlighted = highlight_replacements(edited_texts[idx], text_replacements)
                    st.markdown(
                        f'<div style="height:250px; overflow-y:auto; border:1px solid #ddd; padding:10px; border-radius:5px;">{highlighted}</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.text_area(
                        f"Результат обработки {idx+1}",  # ← Добавлен осмысленный label
                        edited_texts[idx],
                        height=250,
                        key=f"res_display_{idx}",
                        label_visibility="collapsed"
                    )
            # Ручное редактирование
            with st.expander("✏️ Редактировать этот текст", expanded=False):
                new_text = st.text_area(
                    "Редактируемая версия",
                    edited_texts[idx],
                    height=200,
                    key=f"manual_edit_{idx}"
                )
                if st.button(f"💾 Сохранить изменения для текста {idx+1}", key=f"save_edit_{idx}"):
                    if new_text != edited_texts[idx]:
                        st.session_state.phase6['edited_texts'][idx] = new_text
                        st.session_state.unsaved_changes = True
                        st.success("✅ Изменения сохранены")
                        st.rerun()

            st.divider()

    # Кнопки внизу
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💾 Сохранить всё в фазу 7", type="primary", use_container_width=True):
            if save_to_phase7():
                st.session_state.unsaved_changes = False
                st.success("✅ Данные сохранены!")
                st.balloons()

    with col2:
        if st.button("📥 Экспорт CSV", use_container_width=True):
            export_simple_results(original_texts, st.session_state.phase6['edited_texts'], replacements)

    with col3:
        if st.button("🔄 Сбросить все правки", use_container_width=True):
            st.session_state.phase6['edited_texts'] = processed.copy()
            st.success("✅ Правки сброшены")
            st.rerun()


def show_quick_statistics(replacements_count, total_selected):
    """Быстрая статистика в модальном окне"""
    with st.expander("📊 Подробная статистика", expanded=True):
        st.markdown(f"**Всего замен:** {replacements_count}")
        st.markdown(f"**Выбрано фраз:** {total_selected}")

        if total_selected > 0:
            completion = (replacements_count / total_selected) * 100
            st.progress(min(1.0, completion / 100))
            st.caption(f"Прогресс: {completion:.1f}%")


def reset_all_replacements(selection_manager):
    """Сброс всех замен"""
    original_texts = st.session_state.phase6.get('original_texts', [])
    if original_texts:
        st.session_state.phase6['texts'] = original_texts.copy()
        st.session_state.phase6['processed_texts'] = []
        st.session_state.phase6['edited_texts'] = original_texts.copy()
        st.session_state.phase6['replacements_applied'] = False
        st.session_state.phase6['replacements'] = []
        st.session_state.phase6['analysis_completed'] = False

        # Очищаем результаты анализа
        st.session_state.phase6['unigrams'] = {}
        st.session_state.phase6['bigrams'] = {}
        st.session_state.phase6['trigrams'] = {}
        st.session_state.phase6['ngrams'] = {}
        st.session_state.phase6['prepositional'] = {}

        # Очищаем выбор
        selection_manager.clear_selections()
        st.session_state.pending_selections = {}

        log("Все замены сброшены")


def auto_fill_forms_for_phrase(phrase: str, ngram_type: ReplacementType, syn_manager, stop_manager):
    """Автозаполнение форм для конкретной фразы"""
    replacer = FastReplacer(syn_manager, stop_manager)

    # Получаем формы из текстов
    data = st.session_state.phase6.get(f'{ngram_type.value}s', {})
    info = data.get(phrase, {})
    forms_dict = info.get('forms', {}) if isinstance(info, dict) else getattr(info, 'forms', {})

    # Получаем синонимы
    all_synonyms = syn_manager.get_synonyms(phrase, ngram_type)
    available_synonyms = [s for s in all_synonyms if s != phrase]

    filled = 0
    for syn in available_synonyms[:5]:  # Ограничиваем для скорости
        for form, _ in list(forms_dict.items())[:20]:
            try:
                adapted = replacer.adapt_synonym_form(phrase, syn, form, ngram_type)
                if adapted and adapted != form:
                    syn_manager.set_specific_form(form, syn, adapted, ngram_type)
                    filled += 1
            except Exception:
                continue

    log(f"Автозаполнено {filled} форм для фразы {phrase}")
def render_synonym_edit_dialog(ngram: str, ngram_type: ReplacementType,
                               syn_manager: FastSynonymManager,
                               stop_manager: StopWordManager,
                               forms_dict: Dict[str, int] = None):
    import time, os, json, traceback

    if forms_dict is None:
        forms_dict = {}

    # --- Базовый ключ и счётчик версий (пересоздаёт виджеты при смене синонима) ---
    base_key = f"{ngram_type.value}_{ngram}"
    version_key = f"version_{base_key}"
    if version_key not in st.session_state:
        st.session_state[version_key] = 0

    version = st.session_state[version_key]
    dialog_key = f"syn_dialog_{base_key}_v{version}"
    text_key = f"syn_text_{dialog_key}"

    # --- Выбранный синоним ---
    selected_syn_key = f"selected_syn_{base_key}"
    all_synonyms = syn_manager.get_synonyms(ngram, ngram_type)
    form_synonyms = [s for s in all_synonyms if s != ngram]
    if form_synonyms and selected_syn_key not in st.session_state:
        st.session_state[selected_syn_key] = form_synonyms[0]

    # --- Текст синонимов ---
    if text_key not in st.session_state:
        current = syn_manager.get_synonyms(ngram, ngram_type)
        st.session_state[text_key] = "\n".join(current)

    st.markdown(f"### ✏️ Редактирование синонимов")
    st.markdown(f"**Лемма:** `{ngram}`")
    st.markdown(f"**Тип:** `{ngram_type.value}`")

    synonyms_text = st.text_area(
        "**Все синонимы (каждый с новой строки):**",
        value=st.session_state[text_key],
        height=150,
        key=f"syn_edit_area_{dialog_key}",
        label_visibility="collapsed",
        on_change=lambda: st.session_state.update(
            {text_key: st.session_state[f"syn_edit_area_{dialog_key}"]}
        )
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 СОХРАНИТЬ", type="primary", key=f"save_syn_{dialog_key}", use_container_width=True):
            try:
                new_synonyms = [line.strip() for line in synonyms_text.split("\n") if line.strip()]
                if ngram not in new_synonyms:
                    new_synonyms.insert(0, ngram)

                synonyms_file = "synonyms.json"
                if os.path.exists(synonyms_file):
                    with open(synonyms_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = {
                        "unigram_synonyms": {}, "bigram_synonyms": {}, "trigram_synonyms": {},
                        "ngram_synonyms": {}, "prepositional_synonyms": {},
                        "active_synonyms": {}, "specific_forms": {}
                    }

                section = f"{ngram_type.value}_synonyms"
                if section not in data:
                    data[section] = {}
                data[section][ngram.lower()] = new_synonyms

                active_key = f"{ngram_type.value}:{ngram.lower()}"
                if "active_synonyms" not in data:
                    data["active_synonyms"] = {}
                data["active_synonyms"][active_key] = [s for s in new_synonyms if s != ngram]

                with open(synonyms_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                syn_manager._load_data()
                syn_manager._cache.clear()
                syn_manager.grouper = SynonymGrouper(syn_manager)

                type_str = ngram_type.value
                refresh_name = f'refresh_counter_{type_str}'
                st.session_state[refresh_name] = st.session_state.get(refresh_name, 0) + 1

                st.session_state[text_key] = "\n".join(new_synonyms)

                st.success(f"✅ Сохранено синонимов: {len(new_synonyms)}")
                time.sleep(0.8)
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")
                st.code(traceback.format_exc())

    with col2:
        if st.button("❌ ЗАКРЫТЬ", key=f"close_syn_{dialog_key}", use_container_width=True):
            for k in (text_key, version_key, selected_syn_key):
                if k in st.session_state:
                    del st.session_state[k]
            st.session_state.show_edit_dialog = False
            type_str = ngram_type.value
            st.session_state.pop(f'edit_selector_{type_str}', None)
            st.rerun()

    # --- КОНКРЕТНЫЕ ФОРМЫ ---
    st.markdown("---")
    st.markdown("### 🔤 Конкретные формы")
    if not forms_dict:
        st.info("Нет конкретных форм. Запустите анализ текстов.")
        return

    # Актуальные синонимы после возможного сохранения
    all_synonyms = syn_manager.get_synonyms(ngram, ngram_type)
    form_synonyms = [s for s in all_synonyms if s != ngram]
    if not form_synonyms:
        st.warning("Нет синонимов (кроме оригинала). Добавьте синонимы выше.")
        return

    # --- Выбор синонима с принудительным обновлением версии ---
    current_selected = st.session_state.get(selected_syn_key, form_synonyms[0])
    if current_selected not in form_synonyms:
        current_selected = form_synonyms[0]
        st.session_state[selected_syn_key] = current_selected

    def on_synonym_change():
        new_syn = st.session_state[f"syn_select_{dialog_key}"]
        if new_syn != st.session_state.get(selected_syn_key):
            st.session_state[selected_syn_key] = new_syn
            st.session_state[version_key] += 1   # пересоздаст все виджеты форм
            st.rerun()

    selected_syn = st.selectbox(
        "Выберите синоним:",
        form_synonyms,
        index=form_synonyms.index(current_selected),
        key=f"syn_select_{dialog_key}",
        on_change=on_synonym_change
    )

    # --- ИСПРАВЛЕНИЕ: Добавляем индикатор загрузки для автозаполнения ---
    st.markdown(f"**Формы для синонима:** `{selected_syn}`")

    # --- Отображение форм для выбранного синонима ---
    sorted_forms = sorted(forms_dict.items(), key=lambda x: x[1], reverse=True)
    updated_forms = {}

    # Создаем контейнер для форм
    forms_container = st.container()

    with forms_container:
        for form, count in sorted_forms[:20]:
            current_repl = syn_manager.get_specific_form(form, selected_syn, ngram_type)
            col_a, col_b, col_c = st.columns([2, 1, 3])
            with col_a:
                st.markdown(f"**{form}**")
            with col_b:
                st.caption(f"({count})")
            with col_c:
                new_repl = st.text_input(
                    "Замена:",
                    value=current_repl or "",
                    key=f"form_{dialog_key}_{form}_{selected_syn}",  # Добавляем selected_syn в ключ
                    label_visibility="collapsed",
                    placeholder="Оставьте пустым для автозаполнения"
                )
                if new_repl and new_repl != current_repl:
                    updated_forms[form] = new_repl
        if len(sorted_forms) > 20:
            st.caption(f"... и ещё {len(sorted_forms)-20} форм")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("💾 Сохранить формы", key=f"save_forms_{dialog_key}"):
            for form, repl in updated_forms.items():
                if repl:
                    syn_manager.set_specific_form(form, selected_syn, repl, ngram_type)
            st.success("Формы сохранены")
            st.rerun()

    with col_b:
        # ИСПРАВЛЕНИЕ: Добавляем индикатор процесса для автозаполнения
        if st.button("🤖 Автозаполнить эту форму", key=f"auto_one_{dialog_key}"):
            with st.spinner(f"Автозаполнение форм для синонима '{selected_syn}'..."):
                replacer = FastReplacer(syn_manager, stop_manager)
                filled_count = 0
                progress_bar = st.progress(0)
                for idx, (form, _) in enumerate(sorted_forms[:50]):
                    try:
                        adapted = replacer.adapt_synonym_form(ngram, selected_syn, form, ngram_type)
                        if adapted and adapted != form:
                            syn_manager.set_specific_form(form, selected_syn, adapted, ngram_type)
                            filled_count += 1
                        progress_bar.progress((idx + 1) / min(50, len(sorted_forms)))
                    except Exception as e:
                        log(f"Ошибка автозаполнения для {form}: {e}")
                        continue
                progress_bar.empty()
                st.session_state[version_key] += 1
                st.success(f"✅ Заполнено {filled_count} форм для синонима '{selected_syn}'")
                time.sleep(1)
                st.rerun()

    with col_c:
        if st.button("🤖 Автозаполнить ВСЕ синонимы", key=f"auto_all_{dialog_key}"):
            with st.spinner("Автозаполнение всех синонимов..."):
                replacer = FastReplacer(syn_manager, stop_manager)
                total_filled = 0
                all_syns = form_synonyms[:10]  # Ограничиваем первыми 10 синонимами для скорости

                # Создаем прогресс-бар для всех синонимов
                total_operations = len(all_syns) * min(50, len(sorted_forms))
                current_op = 0
                progress_bar = st.progress(0)

                for syn_idx, syn in enumerate(all_syns):
                    st.write(f"Обработка синонима: {syn}")
                    for form_idx, (form, _) in enumerate(sorted_forms[:50]):
                        try:
                            adapted = replacer.adapt_synonym_form(ngram, syn, form, ngram_type)
                            if adapted and adapted != form:
                                syn_manager.set_specific_form(form, syn, adapted, ngram_type)
                                total_filled += 1
                            current_op += 1
                            progress_bar.progress(current_op / total_operations)
                        except Exception:
                            continue
                    st.write(f"  ✓ Готово")

                progress_bar.empty()
                st.session_state[version_key] += 1
                st.success(f"✅ Заполнено {total_filled} форм для {len(all_syns)} синонимов")
                time.sleep(1.5)
                st.rerun()


def render_forms_edit_dialog(syn_manager: FastSynonymManager):
    """
    Этот диалог больше не нужен – всё объединено в одном месте.
    Оставляем заглушку, чтобы не ломался код.
    """
    st.info("Редактирование форм доступно в диалоге синонимов.")


def handle_edit_dialogs(syn_manager: FastSynonymManager, stop_manager: StopWordManager):
    """Обработчик диалогов - с передачей stop_manager"""
    if st.session_state.get('show_edit_dialog', False):
        ngram = st.session_state.get('edit_ngram', '')
        ngram_type_str = st.session_state.get('edit_ngram_type', 'unigram')
        forms_dict = st.session_state.get('edit_forms', {})

        if ngram:
            try:
                ngram_type = ReplacementType(ngram_type_str)
                # Убеждаемся, что передаем правильные параметры
                render_synonym_edit_dialog(
                    ngram,
                    ngram_type,
                    syn_manager,
                    stop_manager,  # Важно! Передаем stop_manager
                    forms_dict
                )
            except Exception as e:
                st.error(f"Ошибка открытия диалога: {e}")
                st.session_state.show_edit_dialog = False
                st.rerun()

def show_results_in_auto_mode():
    """Показывает результаты синонимизации в авторежиме"""
    processed_texts = st.session_state.phase6.get('processed_texts', [])
    original_texts = st.session_state.phase6.get('original_texts', [])
    replacements = st.session_state.phase6.get('replacements', [])

    if not processed_texts:
        st.info("Нет результатов для отображения")
        return

    st.markdown("### 📊 Результаты синонимизации")
    st.markdown(f"**Обработано текстов:** {len(processed_texts)}")
    st.markdown(f"**Выполнено замен:** {len(replacements)}")

    # Показываем первые 3 текста для примера
    for i in range(min(3, len(processed_texts))):
        with st.expander(f"📄 Текст {i+1}", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Оригинал:**")
                st.text(original_texts[i][:300] + "..." if len(original_texts[i]) > 300 else original_texts[i])
            with col2:
                st.markdown("**Результат:**")
                st.text(processed_texts[i][:300] + "..." if len(processed_texts[i]) > 300 else processed_texts[i])

    if len(processed_texts) > 3:
        st.caption(f"... и ещё {len(processed_texts) - 3} текстов")
def render_edit_synonyms_button(ngram: str, ngram_type: ReplacementType, syn_manager: FastSynonymManager,
                                forms_dict: Dict[str, int] = None):
    """
    Кнопка для открытия диалога редактирования синонимов
    """
    if st.button(f"✏️ Редактировать синонимы", key=f"edit_syn_{ngram_type.value}_{ngram}", use_container_width=True):
        st.session_state.edit_ngram = ngram
        st.session_state.edit_ngram_type = ngram_type.value
        st.session_state.edit_forms = forms_dict or {}
        st.session_state.show_edit_dialog = True
        st.rerun()


def auto_process_synonyms(app_state=None, context=None):
    """Запускаем полный интерфейс фазы 6 как в ручном режиме"""

    # ===== ДОБАВИТЬ ПРОВЕРКУ =====
    current_project_id = st.session_state.get('current_project_id')
    last_loaded = st.session_state.get('phase6_last_loaded_project')

    if current_project_id and last_loaded != current_project_id:
        log(f"🔄 auto_process_synonyms: проект изменился, очищаем данные")
        if 'phase6' in st.session_state:
            st.session_state.phase6 = {
                'initialized': True,
                'texts': [],
                'original_texts': [],
                'processed_texts': [],
                'edited_texts': [],
                'replacements': [],
                'unigrams': {},
                'bigrams': {},
                'trigrams': {},
                'ngrams': {},
                'prepositional': {},
                'analysis_completed': False,
                'replacements_applied': False,
                'texts_metadata': [],
                'min_count': 3
            }
        st.session_state.phase6_last_loaded_project = current_project_id
    # ===== КОНЕЦ ПРОВЕРКИ =====

    log("=" * 60)
    log("🚀 PHASE 6 AUTO MODE — FULL MANUAL INTERFACE")
    log("=" * 60)

    init_phase6_structure()

    return main(
        app_state=app_state,
        auto_mode=True,
        settings_mode=False,
        context=context
    )

def get_data_for_phase7():
    """
    Возвращает данные в формате, ожидаемом фазой 7
    """
    phase6_data = st.session_state.app_data.get('phase6', {})

    if not phase6_data:
        return {
            'success': False,
            'error': 'Нет данных из фазы 6'
        }

    # Проверяем, есть ли результаты в нужном формате
    results = phase6_data.get('results', {})

    if not results:
        # Пытаемся сконвертировать из processed_texts
        processed_texts = phase6_data.get('processed_texts', [])
        original_texts = phase6_data.get('original_texts', [])
        metadata = phase6_data.get('texts_metadata', [])

        if processed_texts:
            results = {}
            for idx, text in enumerate(processed_texts):
                meta = metadata[idx] if idx < len(metadata) else {}
                prompt_id = meta.get('prompt_id', f"synonymized_{idx}")
                results[prompt_id] = {
                    'prompt_id': prompt_id,
                    'original_text': original_texts[idx] if idx < len(original_texts) else '',
                    'edited_text': text,
                    'processed_text': text,
                    'ai_response': text,
                    'status': 'success',
                    'characteristic_name': meta.get('characteristic_name', ''),
                    'characteristic_value': meta.get('characteristic_value', ''),
                    'type': meta.get('type', 'synonymized'),
                    'block_name': meta.get('block_name', ''),
                    'prompt_num': meta.get('prompt_num', 1)
                }

    return {
        'success': True,
        'results': results,
        'statistics': phase6_data.get('statistics', {}),
        'category': phase6_data.get('category', '')
    }
def open_phrase_in_editor(phrase: str, ngram_type: str):
    """Открывает выбранную фразу в редакторе синонимов"""
    st.session_state.edit_ngram_target = phrase
    st.session_state.edit_ngram_type_target = ngram_type
    st.session_state.phase6_current_tab = "✏️ Редактор синонимов"
    st.session_state.pending_phrase_for_editor = phrase
    # Не делаем rerun здесь - он будет после возврата из функции
if __name__ == "__main__":
    main()