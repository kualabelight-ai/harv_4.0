
import sys
import os
import json
import random
import pandas as pd
import re
import logging
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Any, Optional
from dataclasses import dataclass
from enum import Enum
import itertools
import time
import threading
import traceback
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTableWidget, QTextEdit, QTabWidget, QPushButton, QTableWidgetItem,
    QHeaderView, QSplitter, QProgressBar, QLabel, QTreeWidget, QTreeWidgetItem,
    QDialog, QDialogButtonBox, QLineEdit, QCheckBox, QRadioButton, QButtonGroup,
    QGroupBox, QScrollArea, QFileDialog, QMessageBox, QToolBar, QStatusBar,
    QToolButton, QMenu, QSizePolicy, QStyledItemDelegate, QInputDialog,
    QTextBrowser, QListWidget, QListWidgetItem, QComboBox, QProgressDialog,
    QMenuBar, QFrame, QDockWidget, QTextBrowser, QCompleter
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QModelIndex, QRegularExpression, QPoint, QSize
from PySide6.QtGui import (
    QAction, QFont, QTextCursor, QColor, QTextCharFormat, QPalette, QSyntaxHighlighter,
    QTextDocument, QGuiApplication, QKeySequence, QIcon, QDesktopServices, QShortcut, QClipboard, QCursor
)
from typing import Dict, List, Set, Tuple, Any, Optional
from dataclasses import dataclass
from enum import Enum


# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
class ErrorLogger:
    """Логирование ошибок в отдельный файл"""

    def __init__(self):
        self.log_file = "error_log.txt"
        self.setup_logging()

    def setup_logging(self):
        """Настройка логирования"""
        # Основной логгер для приложения
        self.logger = logging.getLogger('Synonymizer')
        self.logger.setLevel(logging.INFO)

        # Форматтер для логов
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Хендлер для файла ошибок
        error_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)

        # Хендлер для консоли
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        # Добавляем хендлеры
        self.logger.addHandler(error_handler)
        self.logger.addHandler(console_handler)

        # Логируем старт
        self.logger.info("=" * 80)
        self.logger.info("Приложение запущено")
        self.logger.info(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 80)

    def log_error(self, error_msg: str, exc_info=None):
        """Логирование ошибки с трассировкой"""
        if exc_info:
            self.logger.error(error_msg, exc_info=exc_info)
        else:
            self.logger.error(error_msg)

    def log_warning(self, warning_msg: str):
        """Логирование предупреждения"""
        self.logger.warning(warning_msg)

    def log_info(self, info_msg: str):
        """Логирование информации"""
        self.logger.info(info_msg)

    def show_error_log(self):
        """Показать файл с логами ошибок"""
        try:
            if os.path.exists(self.log_file):
                os.startfile(self.log_file) if sys.platform == 'win32' else QDesktopServices.openUrl(
                    f"file://{os.path.abspath(self.log_file)}")
            else:
                QMessageBox.information(None, "Информация", "Файл логов ошибок не найден.")
        except Exception as e:
            self.logger.error(f"Не удалось открыть файл логов: {e}")


# Создаем глобальный логгер
error_logger = ErrorLogger()
logger = error_logger.logger


# ==================== ТИПЫ ДАННЫХ ====================
class WordStatus(Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    PENDING = "pending"


class ReplacementType(Enum):
    UNIGRAM = "unigram"
    BIGRAM = "bigram"
    TRIGRAM = "trigram"
    NGRAM = "ngram"
    PREPOSITIONAL = "prepositional"
    MANUAL = "manual"
    STOPWORD = "stopword"


@dataclass
class ReplacementInfo:
    original: str
    new: str
    start: int
    end: int
    text_index: int
    type: ReplacementType
    lemma: str = ""
    is_manual: bool = False
    used_synonym: str = ""
    context: str = ""
    skipped_reason: str = ""


@dataclass
class NGramInfo:
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


# ==================== БЫСТРАЯ СИСТЕМА ПОДСВЕТКИ ====================
class FastHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument, replacements: List[ReplacementInfo]):
        super().__init__(document)
        self.replacements = replacements

    def highlightBlock(self, text):
        for replacement in self.replacements:
            start_idx = 0
            while True:
                idx = text.find(replacement.new, start_idx)
                if idx == -1:
                    break

                if self.is_exact_match(text, idx, len(replacement.new)):
                    format = QTextCharFormat()

                    # Разные цвета для разных типов замен
                    if replacement.type == ReplacementType.STOPWORD:
                        format.setBackground(QColor(255, 200, 200))  # Красный для стоп-слов
                    else:
                        format.setBackground(QColor(200, 255, 200))  # Зеленый для обычных замен

                    format.setForeground(QColor(0, 0, 0))
                    format.setFontWeight(QFont.Bold)

                    tooltip_text = (f"🔄 ЗАМЕНЕНО:\n"
                                    f"📝 Было: '{replacement.original}'\n"
                                    f"✨ Стало: '{replacement.new}'\n"
                                    f"🔧 Тип: {replacement.type.value}")

                    if replacement.used_synonym and replacement.used_synonym != replacement.new:
                        tooltip_text += f"\n🎯 Синоним: {replacement.used_synonym}"

                    if replacement.skipped_reason:
                        tooltip_text += f"\n⚠️ Пропущено: {replacement.skipped_reason}"

                    format.setToolTip(tooltip_text)

                    self.setFormat(idx, len(replacement.new), format)

                start_idx = idx + 1

    def is_exact_match(self, text: str, start: int, length: int) -> bool:
        if start > 0 and text[start - 1].isalnum():
            return False
        end_pos = start + length
        if end_pos < len(text) and text[end_pos].isalnum():
            return False
        return True


# ==================== СИСТЕМА ПОИСКА И ЗАМЕНЫ ====================
class FindReplaceDialog(QDialog):
    """Диалог для поиска и замены текста"""

    def __init__(self, text_edit: QTextEdit, parent=None):
        super().__init__(parent)
        self.text_edit = text_edit
        self.setWindowTitle("Поиск и замена")
        self.setModal(False)
        self.setup_ui()
        self.center_on_parent()  # Центрируем на родительском окне

    def center_on_parent(self):
        """Центрирует окно относительно родительского окна"""
        parent_widget = self.parent()
        if parent_widget:
            # Получаем геометрию родительского окна
            parent_geometry = self.parent().frameGeometry()
            # Получаем геометрию экрана, на котором находится родительское окно
            screen = QGuiApplication.screenAt(parent_geometry.center())
            if screen:
                screen_geometry = screen.availableGeometry()

                # Вычисляем позицию для центрирования на том же экране
                x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2

                # Устанавливаем положение окна
                self.move(x, y)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Поиск
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("Найти:"))
        self.find_edit = QLineEdit()
        self.find_edit.textChanged.connect(self.find_text)
        find_layout.addWidget(self.find_edit)

        self.find_next_btn = QPushButton("Следующий")
        self.find_next_btn.clicked.connect(self.find_next)
        find_layout.addWidget(self.find_next_btn)

        self.find_prev_btn = QPushButton("Предыдущий")
        self.find_prev_btn.clicked.connect(self.find_previous)
        find_layout.addWidget(self.find_prev_btn)

        layout.addLayout(find_layout)

        # Замена
        replace_layout = QHBoxLayout()
        replace_layout.addWidget(QLabel("Заменить на:"))
        self.replace_edit = QLineEdit()
        replace_layout.addWidget(self.replace_edit)

        self.replace_btn = QPushButton("Заменить")
        self.replace_btn.clicked.connect(self.replace_current)
        replace_layout.addWidget(self.replace_btn)

        self.replace_all_btn = QPushButton("Заменить все")
        self.replace_all_btn.clicked.connect(self.replace_all)
        replace_layout.addWidget(self.replace_all_btn)

        layout.addLayout(replace_layout)

        # Настройки
        options_layout = QHBoxLayout()
        self.case_sensitive = QCheckBox("С учетом регистра")
        self.whole_words = QCheckBox("Целые слова")
        options_layout.addWidget(self.case_sensitive)
        options_layout.addWidget(self.whole_words)
        options_layout.addStretch()

        layout.addLayout(options_layout)

        # Статус
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Кнопки
        button_layout = QHBoxLayout()
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Устанавливаем размер
        self.setFixedSize(500, 200)

    def find_text(self, text: str = None):
        """Поиск текста с выделением и прокруткой к найденному"""
        if not text:
            text = self.find_edit.text()

        if not text:
            return

        # Сбрасываем предыдущее выделение
        cursor = self.text_edit.textCursor()
        format = QTextCharFormat()
        format.setBackground(QColor(45, 45, 45))  # Черный фон (сбрасываем)
        cursor.select(QTextCursor.Document)
        cursor.mergeCharFormat(format)

        # Начинаем поиск с текущей позиции курсора
        cursor.clearSelection()

        # Устанавливаем флаги поиска
        flags = QTextDocument.FindFlags()
        if self.case_sensitive.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        if self.whole_words.isChecked():
            flags |= QTextDocument.FindWholeWords

        # Ищем с текущей позиции
        found = self.text_edit.find(text, flags)

        if not found:
            # Если не нашли, начинаем с начала
            cursor = self.text_edit.textCursor()
            cursor.setPosition(0)
            self.text_edit.setTextCursor(cursor)
            found = self.text_edit.find(text, flags)

        if found:
            # Создаем формат для выделения
            format = QTextCharFormat()
            format.setBackground(QColor(255, 255, 0))  # Желтый цвет
            format.setForeground(QColor(0, 0, 0))  # Черный текст

            # Выделяем найденный текст
            cursor = self.text_edit.textCursor()
            cursor.mergeCharFormat(format)

            # ПРОКРУЧИВАЕМ К НАЙДЕННОМУ МЕСТУ
            self.text_edit.ensureCursorVisible()

            # Перемещаем фокус на найденный текст
            self.text_edit.setFocus()

            self.status_label.setText("Текст найден")
            self.status_label.setStyleSheet("color: green")
        else:
            self.status_label.setText("Текст не найден")
            self.status_label.setStyleSheet("color: red")

    def find_next(self):
        """Найти следующий с правильным позиционированием"""
        text = self.find_edit.text()

        if not text:
            self.find_text("")
            return

        flags = QTextDocument.FindFlags()
        if self.case_sensitive.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        if self.whole_words.isChecked():
            flags |= QTextDocument.FindWholeWords

        found = self.text_edit.find(text, flags)

        if found:
            # Выделяем найденный текст
            format = QTextCharFormat()
            format.setBackground(QColor(255, 255, 0))
            format.setForeground(QColor(0, 0, 0))

            cursor = self.text_edit.textCursor()
            cursor.mergeCharFormat(format)

            # ПРОКРУЧИВАЕМ
            self.text_edit.ensureCursorVisible()
            self.text_edit.setFocus()

            self.status_label.setText("Текст найден")
            self.status_label.setStyleSheet("color: green")
        else:
            # Если не нашли, начинаем с начала
            cursor = self.text_edit.textCursor()
            cursor.setPosition(0)
            self.text_edit.setTextCursor(cursor)
            found = self.text_edit.find(text, flags)

            if found:
                format = QTextCharFormat()
                format.setBackground(QColor(255, 255, 0))
                format.setForeground(QColor(0, 0, 0))

                cursor = self.text_edit.textCursor()
                cursor.mergeCharFormat(format)

                # ПРОКРУЧИВАЕМ
                self.text_edit.ensureCursorVisible()
                self.text_edit.setFocus()

                self.status_label.setText("Текст найден (с начала документа)")
                self.status_label.setStyleSheet("color: green")
            else:
                self.status_label.setText("Текст не найден")
                self.status_label.setStyleSheet("color: red")

    def find_previous(self):
        """Найти предыдущий"""
        text = self.find_edit.text()

        if not text:
            return

        flags = QTextDocument.FindBackward
        if self.case_sensitive.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        if self.whole_words.isChecked():
            flags |= QTextDocument.FindWholeWords

        found = self.text_edit.find(text, flags)

        if found:
            # Выделяем найденный текст
            format = QTextCharFormat()
            format.setBackground(QColor(255, 255, 0))
            format.setForeground(QColor(0, 0, 0))

            cursor = self.text_edit.textCursor()
            cursor.mergeCharFormat(format)

            self.status_label.setText("Текст найден")
            self.status_label.setStyleSheet("color: green")
        else:
            # Если не нашли, начинаем с конца
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.text_edit.setTextCursor(cursor)
            found = self.text_edit.find(text, flags)

            if found:
                format = QTextCharFormat()
                format.setBackground(QColor(255, 255, 0))
                format.setForeground(QColor(0, 0, 0))

                cursor = self.text_edit.textCursor()
                cursor.mergeCharFormat(format)

                self.status_label.setText("Текст найден (с конца документа)")
                self.status_label.setStyleSheet("color: green")
            else:
                self.status_label.setText("Текст не найден")
                self.status_label.setStyleSheet("color: red")

    def replace_current(self):
        """Заменить текущее вхождение"""
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_edit.text())
            self.find_next()

    def replace_all(self):
        """Заменить все вхождения"""
        text = self.text_edit.toPlainText()
        find_text = self.find_edit.text()
        replace_text = self.replace_edit.text()

        if not find_text:
            return

        # Заменяем
        if self.case_sensitive.isChecked():
            new_text = text.replace(find_text, replace_text)
        else:
            import re
            new_text = re.sub(re.escape(find_text), replace_text, text, flags=re.IGNORECASE)

        self.text_edit.setPlainText(new_text)
        self.status_label.setText(f"Заменено {text.count(find_text)} вхождений")
        self.status_label.setStyleSheet("color: blue")


# ==================== МЕНЕДЖЕР СТОП-СЛОВ ====================
class StopWordManager:
    """Менеджер стоп-слов"""

    def __init__(self, syn_manager):
        self.syn_manager = syn_manager
        self.stop_words_file = "stop_words.json"
        self._load_stop_words()

    def _load_stop_words(self):
        """Загрузка стоп-слов из файла"""
        try:
            if os.path.exists(self.stop_words_file):
                with open(self.stop_words_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.stop_words = set(data.get("stop_words", []))
                    self.stop_word_synonyms = data.get("stop_word_synonyms", {})
            else:
                self.stop_words = {"идеальный", "высококачественный", "лучший", "превосходный", "отличный"}
                self.stop_word_synonyms = {}
                self._save_stop_words()

        except Exception as e:
            error_logger.log_error(f"Ошибка загрузки стоп-слов: {e}")
            self.stop_words = {"идеальный", "высококачественный", "лучший", "превосходный", "отличный"}
            self.stop_word_synonyms = {}

    def _save_stop_words(self):
        """Сохранение стоп-слов в файл"""
        try:
            data = {
                "stop_words": list(self.stop_words),
                "stop_word_synonyms": self.stop_word_synonyms
            }
            with open(self.stop_words_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            error_logger.log_error(f"Ошибка сохранения стоп-слов: {e}")

    def add_stop_word(self, word: str):
        """Добавить стоп-слово"""
        self.stop_words.add(word.lower())
        self._save_stop_words()

    def remove_stop_word(self, word: str):
        """Удалить стоп-слово"""
        word_lower = word.lower()
        if word_lower in self.stop_words:
            self.stop_words.remove(word_lower)
            self._save_stop_words()

    def get_stop_words(self) -> Set[str]:
        """Получить список стоп-слов"""
        return self.stop_words.copy()

    def is_stop_word(self, word: str) -> bool:
        """Проверяет, является ли слово стоп-словом"""
        # Базовая проверка
        if word.lower() in self.stop_words:
            return True

        # Дополнительная проверка через морфологию
        try:
            if hasattr(self.syn_manager, 'morph') and self.syn_manager.morph:
                parsed = self.syn_manager.morph.parse(word)[0]
                lemma = parsed.normal_form.lower()
                return lemma in self.stop_words
        except:
            pass

        return False

    def get_stop_word_synonyms(self, word: str) -> List[str]:
        """Получить синонимы для стоп-слова"""
        return self.stop_word_synonyms.get(word.lower(), [])

    def set_stop_word_synonyms(self, word: str, synonyms: List[str]):
        """Установить синонимы для стоп-слова"""
        self.stop_word_synonyms[word.lower()] = synonyms
        self._save_stop_words()

    def get_all_stop_word_synonyms(self) -> Dict[str, List[str]]:
        """Получить все синонимы стоп-слов"""
        return self.stop_word_synonyms.copy()


# ==================== БЫСТРЫЙ АНАЛИЗАТОР ТЕКСТА С ПРЕДЛОГАМИ ====================
class FastTextAnalyzer(QThread):
    progress_updated = Signal(int, str)
    analysis_finished = Signal(dict, dict, dict, dict, dict)
    error_occurred = Signal(str)

    def __init__(self, texts: List[str], stop_word_manager: StopWordManager):
        super().__init__()
        self.texts = texts
        self.stop_word_manager = stop_word_manager
        self._word_cache = {}  # Кеш для слов

        try:
            import pymorphy3
            self.morph = pymorphy3.MorphAnalyzer()
        except ImportError:
            self.morph = None

    def run(self):
        try:
            unigrams = defaultdict(lambda: {'count': 0, 'forms': defaultdict(int), 'replace': True, 'positions': []})
            bigrams = {}
            trigrams = {}
            ngrams = {}
            prepositional_phrases = {}

            total_texts = len(self.texts)

            for text_index, text in enumerate(self.texts):
                self.progress_updated.emit(int((text_index / total_texts) * 100),
                                           f"Анализ текста {text_index + 1}/{total_texts}")

                if not text or not text.strip():
                    continue

                try:
                    # Униграммы (слова) - включая все слова
                    words = re.findall(r'\b\w+\b', text.lower())
                    word_positions = list(re.finditer(r'\b\w+\b', text, re.IGNORECASE))

                    for i, (word, match) in enumerate(zip(words, word_positions)):
                        if len(word) > 2:  # Игнорируем короткие слова
                            lemma = word
                            if self.morph:
                                parsed = self.morph.parse(word)[0]
                                lemma = parsed.normal_form

                            # ПРОВЕРЯЕМ, ЯВЛЯЕТСЯ ЛИ СТОП-СЛОВОМ (по лемме)
                            is_stopword = self.is_stop_word(lemma)

                            unigrams[lemma]['count'] += 1
                            unigrams[lemma]['forms'][match.group()] += 1
                            unigrams[lemma]['positions'].append((text_index, match.start(), match.end()))
                            unigrams[lemma]['is_stopword'] = is_stopword  # ДОБАВЛЯЕМ ФЛАГ

                    # Биграммы (без стоп-слов)
                    bigram_data = self.extract_clean_ngrams(text, text_index, 2)
                    for lemma, info in bigram_data.items():
                        if lemma not in bigrams:
                            bigrams[lemma] = info
                        else:
                            bigrams[lemma].count += info.count
                            bigrams[lemma].positions.extend(info.positions)
                            for form, count in info.forms.items():
                                bigrams[lemma].forms[form] = bigrams[lemma].forms.get(form, 0) + count

                    # Триграммы (без стоп-слов)
                    trigram_data = self.extract_clean_ngrams(text, text_index, 3)
                    for lemma, info in trigram_data.items():
                        if lemma not in trigrams:
                            trigrams[lemma] = info
                        else:
                            trigrams[lemma].count += info.count
                            trigrams[lemma].positions.extend(info.positions)
                            for form, count in info.forms.items():
                                trigrams[lemma].forms[form] = trigrams[lemma].forms.get(form, 0) + count

                    # N-граммы (4-6 слов без стоп-слов)
                    for n in range(4, 7):
                        ngram_data = self.extract_clean_ngrams(text, text_index, n)
                        for lemma, info in ngram_data.items():
                            if lemma not in ngrams:
                                ngrams[lemma] = info
                            else:
                                ngrams[lemma].count += info.count
                                ngrams[lemma].positions.extend(info.positions)
                                for form, count in info.forms.items():
                                    ngrams[lemma].forms[form] = ngrams[lemma].forms.get(form, 0) + count

                    # Фразы с предлогами (2-4 слова)
                    prepositional_data = self.extract_prepositional_phrases(text, text_index)
                    for phrase, info in prepositional_data.items():
                        if phrase not in prepositional_phrases:
                            prepositional_phrases[phrase] = info
                        else:
                            prepositional_phrases[phrase].count += info.count
                            prepositional_phrases[phrase].positions.extend(info.positions)
                            for form, count in info.forms.items():
                                prepositional_phrases[phrase].forms[form] = \
                                    prepositional_phrases[phrase].forms.get(form, 0) + count

                    # --- ВСТАВЬТЕ КОД ЗДЕСЬ ---
                    # Очищаем кеш каждые 50 текстов для предотвращения утечек памяти
                    if text_index % 50 == 0 and text_index > 0:
                        self._word_cache.clear()
                        import gc
                        gc.collect()
                        logger.debug(f"🧹 Очищен кеш после обработки текста {text_index + 1}")
                    # --- КОНЕЦ ВСТАВКИ ---

                except Exception as e:
                    error_logger.log_error(f"Ошибка анализа текста {text_index}: {e}")
                    continue

            # Очищаем кеш после обработки всех текстов
            self._word_cache.clear()
            import gc
            gc.collect()

            self.progress_updated.emit(100, "Анализ завершен")
            self.analysis_finished.emit(dict(unigrams), bigrams, trigrams, ngrams, prepositional_phrases)

        except Exception as e:
            error_logger.log_error(f"Ошибка анализа: {str(e)}", exc_info=True)
            self.error_occurred.emit(f"Ошибка анализа: {str(e)}")
    def cached_parse(self, word: str):
        """Кешированный разбор слова"""
        if word not in self._word_cache:
            if self.morph:
                self._word_cache[word] = self.morph.parse(word)[0]
            else:
                self._word_cache[word] = None
        return self._word_cache[word]

    def is_stop_word(self, word: str) -> bool:
        """Проверяет, является ли слово стоп-словом (по лемме или точному совпадению)"""
        # 1. Используем публичный метод для проверки
        if self.stop_word_manager.is_stop_word(word):
            return True

        # 2. Проверяем грамматические стоп-слова
        parsed = self.cached_parse(word)
        if parsed:
            stop_pos = {'PREP', 'CONJ', 'PRCL', 'INTJ'}
            if any(tag in parsed.tag for tag in stop_pos):
                return True

            # 3. Проверяем по лемме через менеджер
            lemma = parsed.normal_form
            # Нужно дать менеджеру доступ к лемме
            # Либо создаем метод в менеджере, либо делаем так:
            stop_words_set = self.stop_word_manager.get_stop_words()
            if lemma.lower() in stop_words_set:
                return True

        return False

    def is_preposition(self, word: str) -> bool:
        """Проверяет, является ли слово предлогом (с кешированием)"""
        parsed = self.cached_parse(word)
        if not parsed:
            return False
        return 'PREP' in parsed.tag

    def extract_prepositional_phrases(self, text: str, text_index: int) -> Dict[str, NGramInfo]:
        """Извлекает 2-4 словные фразы с предлогами"""
        phrases_dict = {}

        # Разбиваем текст на слова с сохранением позиций
        words_with_positions = []
        for match in re.finditer(r'\b\w+\b', text):
            word = match.group()
            words_with_positions.append((word, match.start(), match.end()))

        # Ищем фразы длиной 2-4 слова
        for n in range(2, 5):
            for i in range(len(words_with_positions) - n + 1):
                # Проверяем, содержит ли фраза предлог
                phrase_words = [w[0] for w in words_with_positions[i:i + n]]
                has_preposition = any(self.is_preposition(w) for w in phrase_words)

                if has_preposition:
                    phrase_text = ' '.join(phrase_words)

                    # Находим все вхождения этой фразы
                    pattern = re.compile(re.escape(phrase_text), re.IGNORECASE)
                    positions = []

                    for match in pattern.finditer(text):
                        positions.append((text_index, match.start(), match.end()))

                    if phrase_text.lower() not in phrases_dict:
                        phrases_dict[phrase_text.lower()] = NGramInfo(
                            text=phrase_text,
                            count=len(positions),
                            length=n,
                            positions=positions,
                            forms={phrase_text: len(positions)},
                            original_forms=[phrase_text],
                            has_prepositions=True
                        )
                    else:
                        phrases_dict[phrase_text.lower()].count += len(positions)
                        phrases_dict[phrase_text.lower()].positions.extend(positions)
                        phrases_dict[phrase_text.lower()].forms[phrase_text] = \
                            phrases_dict[phrase_text.lower()].forms.get(phrase_text, 0) + len(positions)

        return phrases_dict

    def lemmatize_phrase(self, phrase: str) -> str:
        """Лемматизирует фразу пословно, исключая стоп-слова"""
        if not self.morph:
            return phrase

        words = re.findall(r'\b\w+\b', phrase)
        lemmas = []
        for word in words:
            if not self.is_stop_word(word):  # Исключаем стоп-слова
                parsed = self.cached_parse(word)
                if parsed:
                    lemmas.append(parsed.normal_form)
        return ', '.join(lemmas)

    def extract_clean_ngrams(self, text: str, text_index: int, n: int) -> Dict[str, NGramInfo]:
        """Извлекает n-граммы без стоп-слов с лемматизацией"""
        ngrams_dict = {}

        # Разбиваем текст на слова с сохранением позиций
        words_with_positions = []
        for match in re.finditer(r'\b\w+\b', text):
            word = match.group()
            if not self.is_stop_word(word):  # Исключаем стоп-слово
                words_with_positions.append((word, match.start(), match.end()))

        # Извлекаем n-граммы
        for i in range(len(words_with_positions) - n + 1):
            ngram_words = [w[0] for w in words_with_positions[i:i + n]]
            ngram_text = ' '.join(ngram_words)

            # Лемматизируем n-грамму
            ngram_lemma = self.lemmatize_phrase(ngram_text)

            # Находим все оригинальные формы этой n-граммы в тексте
            original_forms = self.find_original_forms(text, ngram_words)

            if original_forms:
                positions = []
                forms_count = {}

                for form in original_forms:
                    # Ищем все вхождения этой формы
                    pattern = re.compile(re.escape(form), re.IGNORECASE)
                    matches = list(pattern.finditer(text))

                    for match in matches:
                        positions.append((text_index, match.start(), match.end()))
                        forms_count[form] = forms_count.get(form, 0) + 1

                if ngram_lemma not in ngrams_dict:
                    ngrams_dict[ngram_lemma] = NGramInfo(
                        text=ngram_lemma,
                        count=len(positions),
                        length=n,
                        positions=positions,
                        forms=forms_count,
                        original_forms=original_forms
                    )
                else:
                    # Объединяем формы и позиции
                    for form, count in forms_count.items():
                        ngrams_dict[ngram_lemma].forms[form] = ngrams_dict[ngram_lemma].forms.get(form, 0) + count
                    ngrams_dict[ngram_lemma].positions.extend(positions)
                    ngrams_dict[ngram_lemma].count = len(ngrams_dict[ngram_lemma].positions)

        return ngrams_dict

    def find_original_forms(self, text: str, target_words: List[str]) -> List[str]:
        """Находит оригинальные формы n-граммы в тексте"""
        forms = []
        words_pattern = r'\b\w+\b'
        all_words = list(re.finditer(words_pattern, text))

        for i in range(len(all_words) - len(target_words) + 1):
            # Проверяем, соответствуют ли слова целевым (игнорируя стоп-слова)
            match_words = []
            current_idx = i

            for target_word in target_words:
                while current_idx < len(all_words) and self.is_stop_word(all_words[current_idx].group()):
                    current_idx += 1

                if current_idx >= len(all_words):
                    break

                current_word = all_words[current_idx].group().lower()
                if current_word == target_word.lower():
                    match_words.append(all_words[current_idx])
                    current_idx += 1
                else:
                    break
            else:
                # Все слова совпали - извлекаем оригинальную фразу
                if len(match_words) == len(target_words):
                    start_pos = match_words[0].start()
                    end_pos = match_words[-1].end()
                    original_form = text[start_pos:end_pos]
                    if original_form not in forms:
                        forms.append(original_form)

        return forms

    def clear_cache(self):
        """Очищает кеш для освобождения памяти"""
        self._word_cache.clear()
        import gc
        gc.collect()




# ==================== МЕНЕДЖЕР СЕССИИ ====================
class SessionManager:
    """Управляет временными данными сессии, сохраняет только при выходе"""

    def __init__(self):
        self.session_file = "session_state.json"
        self.data = {
            "checkboxes": {},  # { "unigram:слово": true/false }
            "table_sort": {},  # Состояния сортировки таблиц
            "window_geometry": {},  # Размеры и положение окон
            "last_files": [],  # Последние открытые файлы
            "ui_settings": {  # Настройки UI
                "splitter_sizes": [400, 500, 500],
                "current_tab": 0
            }
        }
        self._load_session()

    def _load_session(self):
        """Загружаем сессию при старте"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Безопасное обновление данных
                    for key in self.data:
                        if key in loaded:
                            self.data[key] = loaded[key]
                logger.info("✅ Сессия загружена")
        except Exception as e:
            error_logger.log_error(f"❌ Ошибка загрузки сессии: {e}")

    def save_session(self):
        """Сохраняем сессию при выходе"""
        try:
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            logger.info("💾 Сессия сохранена")
        except Exception as e:
            error_logger.log_error(f"❌ Ошибка сохранения сессии: {e}")

    def set_current_file(self, filepath):
        """Устанавливает текущий файл"""
        self.data["current_file"] = filepath

    def set_checkbox_state(self, ngram_type: str, ngram: str, state: bool):
        """Сохраняем состояние чекбокса"""
        key = f"{ngram_type}:{ngram}"
        self.data["checkboxes"][key] = state

    def get_checkbox_state(self, ngram_type: str, ngram: str, default: bool = False) -> bool:
        """Получаем состояние чекбокса"""
        key = f"{ngram_type}:{ngram}"
        return self.data["checkboxes"].get(key, default)


# ==================== ДИАЛОГ ВЫБОРА КАСКАДНЫХ СИНОНИМОВ ====================

# ==================== ОПТИМИЗИРОВАННЫЙ МЕНЕДЖЕР СИНОНИМОВ ====================
class FastSynonymManager:
    def __init__(self):
        self.synonyms_file = "synonyms.json"
        self._ensure_file_exists()
        self._data = None
        self._dirty_sections = set()  # Какие секции изменились
        self._cache = {}  # Кеш для быстрого доступа
        self._cache_limit = 10000
        self._save_pending = False  # Флаг отложенного сохранения
        self._save_immediate = False  # Флаг немедленного сохранения
        self._last_save_time = 0
        self._save_timer = None

        self._load_once()
        self.grouper = SynonymGrouper(self)  # Создаем группер после загрузки данных

    def _schedule_save(self, section: str):
        """Отмечаем секцию как изменённую, но не сохраняем сразу"""
        self._dirty_sections.add(section)
        self._save_pending = True

    def unify_synonym_sets(self):
        """Объединить все синонимические множества и обновить файл"""
        try:
            logger.info("🔄 Объединение синонимических множеств...")

            # Перестраиваем группы
            self.grouper._build_groups()

            # Обновляем синонимы согласно группам
            self.grouper.update_synonym_groups()

            # Помечаем раздел как измененный
            self._schedule_save("unigram_synonyms")

            # Сохраняем сразу
            self.save_all_changes()

            logger.info(f"✅ Объединено {len(self.grouper.group_words)} синонимических групп")
            return True

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка объединения синонимов: {e}")
            return False

    def get_unified_synonyms(self, word: str) -> List[str]:
        """Получить все синонимы из группы для слова"""
        return self.grouper.get_unified_synonyms(word)

    def cascade_all_ngrams(self, progress_callback=None) -> Dict[str, Dict[str, List[str]]]:
        """Каскадное обновление всех n-грамм (новая логика)"""
        results = {}

        ngram_types = [
            ReplacementType.BIGRAM,
            ReplacementType.TRIGRAM,
            ReplacementType.NGRAM,
            ReplacementType.PREPOSITIONAL
        ]

        total_processed = 0

        for ngram_type in ngram_types:
            section = f"{ngram_type.value}_synonyms"
            ngram_synonyms = self._data.get(section, {})

            for ngram_lemma, existing_syns in ngram_synonyms.items():
                total_processed += 1

        if progress_callback:
            progress_callback(100, f"Готово к каскадной обработке {total_processed} n-грамм")

        # Теперь этот метод только возвращает информацию
        # Фактическая обработка будет в диалоге для каждой n-граммы отдельно
        return results

    def save_all_changes(self, parent=None) -> bool:
        """Быстрое сохранение всех изменений на диск"""
        if not self._dirty_sections:
            return True

        try:
            # Читаем текущий файл
            if os.path.exists(self.synonyms_file):
                with open(self.synonyms_file, "r", encoding="utf-8") as f:
                    current_data = json.load(f)
            else:
                current_data = self._data.copy()

            # Обновляем только изменённые секции
            for section in self._dirty_sections:
                if section in current_data and section in self._data:
                    current_data[section] = self._data[section]

            # Быстрая запись
            temp_file = self.synonyms_file + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)

            # Атомарная замена
            os.replace(temp_file, self.synonyms_file)

            self._dirty_sections.clear()
            self._save_pending = False

            logger.info(f"💾 Быстрое сохранение завершено: {len(self._dirty_sections)} разделов")
            return True

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка быстрого сохранения: {e}")
            return False

    def get_ngram_components_info(self, ngram_lemma: str, ngram_type: ReplacementType) -> Dict:
        """Получить информацию о составных словах n-граммы"""
        if ngram_type == ReplacementType.UNIGRAM:
            return {"words": [ngram_lemma], "can_cascade": False}

        words = ngram_lemma.split(', ')
        components = []

        for word in words:
            synonyms = self.get_unified_synonyms(word)
            components.append({
                'word': word,
                'synonyms': synonyms,
                'has_other_synonyms': len(synonyms) > 1
            })

        can_cascade = any(comp['has_other_synonyms'] for comp in components) and len(components) > 1

        return {
            'words': words,
            'components': components,
            'can_cascade': can_cascade,
            'word_count': len(words)
        }

    def get_all_forms(self) -> Dict[str, Dict]:
        """Получить все конкретные формы"""
        return self._data.get("specific_forms", {}).copy()

    def set_all_forms(self, forms: Dict[str, Dict]):
        """Установить все конкретные формы"""
        self._data["specific_forms"] = forms.copy()
        self._schedule_save("specific_forms")
        # Очищаем кеш форм
        cache_keys = [k for k in self._cache.keys() if k.startswith("form:")]
        for key in cache_keys:
            del self._cache[key]

    def batch_update_synonyms(self, updates: Dict[str, Dict]):
        """Пакетное обновление синонимов"""
        for ngram_type_str, ngram_updates in updates.items():
            section = f"{ngram_type_str}_synonyms"
            if section not in self._data:
                self._data[section] = {}

            for ngram, synonyms in ngram_updates.items():
                self._data[section][ngram] = synonyms

                # Очищаем кеш
                cache_key = f"syns:{ngram_type_str}:{ngram.lower()}"
                if cache_key in self._cache:
                    del self._cache[cache_key]

            self._schedule_save(section)

    def _ensure_file_exists(self):
        if not os.path.exists(self.synonyms_file):
            self._create_default_structure()
        else:
            # Проверяем структуру существующего файла
            self._validate_file_structure()

    def _create_default_structure(self):
        """Создает файл с полной структурой данных"""
        empty_data = {
            "unigram_synonyms": {},
            "bigram_synonyms": {},
            "trigram_synonyms": {},
            "ngram_synonyms": {},
            "prepositional_synonyms": {},
            "active_synonyms": {},
            "specific_forms": {}
        }
        with open(self.synonyms_file, "w", encoding="utf-8") as f:
            json.dump(empty_data, f, ensure_ascii=False, indent=2)

    def _validate_file_structure(self):
        """Проверяет и исправляет структуру файла синонимов"""
        try:
            with open(self.synonyms_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Определяем обязательные поля
            required_fields = [
                "unigram_synonyms",
                "bigram_synonyms",
                "trigram_synonyms",
                "ngram_synonyms",
                "prepositional_synonyms",
                "active_synonyms",
                "specific_forms"
            ]

            needs_update = False
            for field in required_fields:
                if field not in data:
                    data[field] = {}
                    needs_update = True

            if needs_update:
                logger.info("🔄 Обновление структуры файла синонимов...")
                temp_file = self.synonyms_file + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(temp_file, self.synonyms_file)
                logger.info("✅ Структура файла обновлена")

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка проверки структуры файла: {e}")
            # Если файл поврежден, создаем новый
            self._create_default_structure()

    def _load_once(self):
        """Загружаем данные один раз при старте приложения"""
        try:
            self._validate_file_structure()  # Сначала проверяем структуру

            with open(self.synonyms_file, "r", encoding="utf-8") as f:
                self._data = json.load(f)

            # Гарантируем, что все поля существуют
            required_fields = [
                "unigram_synonyms",
                "bigram_synonyms",
                "trigram_synonyms",
                "ngram_synonyms",
                "prepositional_synonyms",
                "active_synonyms",
                "specific_forms"
            ]

            for field in required_fields:
                if field not in self._data:
                    self._data[field] = {}

            total_entries = sum(len(v) for v in self._data.values())
            logger.info(f"✅ Загружено {total_entries} записей")

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка загрузки кеша: {e}")
            self._data = {
                "unigram_synonyms": {},
                "bigram_synonyms": {},
                "trigram_synonyms": {},
                "ngram_synonyms": {},
                "prepositional_synonyms": {},
                "active_synonyms": {},
                "specific_forms": {}
            }

    def get_specific_form(self, original_phrase: str, synonym: str, ngram_type: ReplacementType) -> Optional[str]:
        # Используем кеш
        cache_key = f"form:{ngram_type.value}:{original_phrase.lower()}:{synonym.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        key = f"{ngram_type.value}:{original_phrase.lower()}:{synonym.lower()}"
        result = self._data["specific_forms"].get(key)

        # Кешируем
        if len(self._cache) < self._cache_limit:
            self._cache[cache_key] = result

        return result

    def set_specific_form(self, original_phrase: str, synonym: str, replacement: str, ngram_type: ReplacementType):
        key = f"{ngram_type.value}:{original_phrase.lower()}:{synonym.lower()}"
        old_value = self._data["specific_forms"].get(key)

        # Проверяем, действительно ли изменилось значение
        if old_value != replacement:
            self._data["specific_forms"][key] = replacement

            # Обновляем кеш
            cache_key = f"form:{ngram_type.value}:{original_phrase.lower()}:{synonym.lower()}"
            self._cache[cache_key] = replacement

            # Планируем сохранение
            self._schedule_save("specific_forms")

    def get_synonyms(self, ngram: str, ngram_type: ReplacementType) -> List[str]:
        # Кеширование запросов
        cache_key = f"syns:{ngram_type.value}:{ngram.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        key = ngram.lower()

        # Безопасный доступ к данным
        synonyms_dict = self._data.get(f"{ngram_type.value}_synonyms", {})
        synonyms = synonyms_dict.get(key, [ngram])

        # Кешируем
        if len(self._cache) < self._cache_limit:
            self._cache[cache_key] = synonyms.copy()

        return synonyms

    def get_active_synonyms(self, ngram: str, ngram_type: ReplacementType) -> List[str]:
        # Кеширование активных синонимов
        cache_key = f"active:{ngram_type.value}:{ngram.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        all_synonyms = self.get_synonyms(ngram, ngram_type)
        key = f"{ngram_type.value}:{ngram.lower()}"

        active_synonyms = self._data["active_synonyms"].get(key, [])

        if active_synonyms:
            # Фильтруем только активные синонимы, которые есть в общем списке
            active = [s for s in active_synonyms if s in all_synonyms]
            result = active if active else all_synonyms[:1]
            logger.info(f"get_active_synonyms({ngram!r}, {ngram_type}) → {result}")
        else:
            # Если активные синонимы не заданы, используем все синонимы
            result = all_synonyms

        # Кешируем
        if len(self._cache) < self._cache_limit:
            self._cache[cache_key] = result.copy()

        return result

    def set_active_synonyms(self, ngram: str, ngram_type: ReplacementType, active_synonyms: List[str]):
        key = f"{ngram_type.value}:{ngram.lower()}"
        old_value = self._data["active_synonyms"].get(key, [])

        # Проверяем, действительно ли изменилось значение
        if old_value != active_synonyms:
            self._data["active_synonyms"][key] = active_synonyms

            # Очищаем кеш для этой записи
            cache_key = f"active:{ngram_type.value}:{ngram.lower()}"
            if cache_key in self._cache:
                del self._cache[cache_key]

            # Планируем сохранение
            self._schedule_save("active_synonyms")

    def add_synonyms(self, ngram: str, ngram_type: ReplacementType, synonyms: List[str]):
        key = ngram.lower()
        clean_synonyms = [s.strip() for s in synonyms if s.strip()]

        # Всегда включаем оригинал в список синонимов
        if ngram not in clean_synonyms:
            clean_synonyms.insert(0, ngram)

        # Получаем старое значение
        old_value = []
        section = ""

        # Определяем секцию в зависимости от типа n-граммы
        section_map = {
            ReplacementType.UNIGRAM: "unigram_synonyms",
            ReplacementType.BIGRAM: "bigram_synonyms",
            ReplacementType.TRIGRAM: "trigram_synonyms",
            ReplacementType.NGRAM: "ngram_synonyms",
            ReplacementType.PREPOSITIONAL: "prepositional_synonyms"
        }

        section = section_map.get(ngram_type)
        if not section:
            logger.error(f"❌ Неизвестный тип n-граммы: {ngram_type}")
            return

        old_value = self._data[section].get(key, [])
        self._data[section][key] = clean_synonyms

        # Проверяем изменение
        if old_value != clean_synonyms:
            # Очищаем кеш
            cache_keys_to_delete = []
            for cache_key in self._cache:
                if cache_key.startswith(f"syns:{ngram_type.value}:{ngram.lower()}") or \
                        cache_key.startswith(f"active:{ngram_type.value}:{ngram.lower()}"):
                    cache_keys_to_delete.append(cache_key)

            for cache_key in cache_keys_to_delete:
                del self._cache[cache_key]

            # Планируем сохранение
            self._schedule_save(section)

    def cascade_synonyms(self, word: str, synonyms: List[str]):
        """Каскадное добавление синонимов ко всем n-граммам с этим словом"""
        try:
            logger.info(f"🔄 Каскад для слова '{word}' - теперь используйте ручной выбор в диалогах n-грамм")
            # Логируем, но не делаем автоматических действий
            # Пользователь будет выбирать в диалогах для каждой n-граммы

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка каскадного добавления синонимов: {e}")


# ==================== ДИАЛОГ ВЫБОРА КАСКАДНЫХ СИНОНИМОВ (ОБНОВЛЕННЫЙ) ====================
class CascadeSynonymsDialog(QDialog):
    """Диалог для выбора синонимов каждого слова в n-грамме"""

    def __init__(self, ngram_lemma: str, ngram_type: ReplacementType,
                 syn_manager: FastSynonymManager, parent=None):
        super().__init__(parent)
        self.ngram_lemma = ngram_lemma
        self.ngram_type = ngram_type
        self.syn_manager = syn_manager
        self.parent_widget = parent
        self.word_widgets = []  # Храним виджеты для каждого слова

        self.setWindowTitle(f"Каскадные синонимы: {ngram_lemma}")
        self.setGeometry(400, 300, 800, 600)
        self.existing_synonyms = []  # Добавляем для хранения существующих синонимов
        self.setup_ui()
        self.load_word_synonyms()
        self.load_existing_synonyms()  # Загружаем существующие синонимы
        self.center_on_parent()
        self.update_preview()  # Сразу показываем превью

    def center_on_parent(self):
        parent_widget = self.parent()
        if parent_widget:
            parent_geometry = parent_widget.frameGeometry()
            screen = QGuiApplication.screenAt(parent_geometry.center())
            if screen:
                screen_geometry = screen.availableGeometry()
                x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
                self.move(x, y)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Заголовок
        title_label = QLabel(f"🔗 Каскадные синонимы для:\n<b>{self.ngram_lemma}</b>")
        title_label.setStyleSheet("font-size: 12pt; margin: 10px;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Инструкция
        instruction = QLabel("Выберите синонимы для каждого слова в фразе:")
        instruction.setStyleSheet("color: #666; margin: 5px;")
        layout.addWidget(instruction)

        # Scroll area для слов
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.words_layout = QVBoxLayout(scroll_content)

        # Здесь будут добавляться виджеты для каждого слова
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Предпросмотр результата
        layout.addWidget(QLabel("<b>Будут созданы синонимы:</b>"))
        self.preview_text = QTextEdit()
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("""
                    QTextEdit {
                        background-color: #f8f9fa;
                        font-family: 'Courier New', monospace;
                        font-size: 10pt;
                        color: #2c3e50;  /* Тёмный текст */
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        padding: 8px;
                    }
                """)
        layout.addWidget(self.preview_text)
        existing_label = QLabel("<b>Существующие синонимы (можно удалить):</b>")
        existing_label.setStyleSheet("margin-top: 10px; margin-bottom: 5px;")
        layout.addWidget(existing_label)

        self.existing_synonyms_list = QListWidget()
        self.existing_synonyms_list.setMaximumHeight(150)
        self.existing_synonyms_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.existing_synonyms_list)

        # Кнопки для управления существующими синонимами
        existing_buttons_layout = QHBoxLayout()

        self.delete_selected_btn = QPushButton("🗑️ Удалить выбранные")
        self.delete_selected_btn.clicked.connect(self.delete_selected_synonyms)
        self.delete_selected_btn.setToolTip("Удалить выбранные существующие синонимы")

        self.select_all_existing_btn = QPushButton("✅ Выбрать все")
        self.select_all_existing_btn.clicked.connect(lambda: self.select_all_existing(True))

        self.deselect_all_existing_btn = QPushButton("❌ Снять все")
        self.deselect_all_existing_btn.clicked.connect(lambda: self.select_all_existing(False))

        existing_buttons_layout.addWidget(self.delete_selected_btn)
        existing_buttons_layout.addWidget(self.select_all_existing_btn)
        existing_buttons_layout.addWidget(self.deselect_all_existing_btn)
        existing_buttons_layout.addStretch()

        layout.addLayout(existing_buttons_layout)
        # Кнопки
        button_layout = QHBoxLayout()

        # Кнопки массового выбора
        select_all_btn = QPushButton("✅ Выбрать все слова")
        select_all_btn.clicked.connect(lambda: self.set_all_words_state(True))

        deselect_all_btn = QPushButton("❌ Снять все слова")
        deselect_all_btn.clicked.connect(lambda: self.set_all_words_state(False))

        # Основные кнопки
        save_btn = QPushButton("💾 Сохранить синонимы")
        save_btn.clicked.connect(self.save_selected)
        save_btn.setStyleSheet("font-weight: bold; padding: 8px;")

        cancel_btn = QPushButton("❌ Отмена")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(deselect_all_btn)
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def load_existing_synonyms(self):
        """Загружает существующие синонимы из менеджера"""
        self.existing_synonyms_list.clear()
        self.existing_synonyms = []

        # Получаем ВСЕ текущие синонимы из менеджера
        all_synonyms = self.syn_manager.get_synonyms(self.ngram_lemma, self.ngram_type)

        # Фильтруем: оставляем только те, которые не являются оригинальной фразой
        for synonym in all_synonyms:
            if synonym != self.ngram_lemma and synonym.strip():
                self.existing_synonyms.append(synonym)

        # Заполняем список
        for synonym in self.existing_synonyms:
            item = QListWidgetItem(synonym)
            item.setCheckState(Qt.Unchecked)
            self.existing_synonyms_list.addItem(item)

        # Обновляем статистику
        self.update_existing_stats()

        # Логируем
        logger.debug(f"📋 Загружено {len(self.existing_synonyms)} существующих синонимов")

    def update_existing_stats(self):
        """Обновляет статистику по существующим синонимам"""
        count = self.existing_synonyms_list.count()
        selected = sum(1 for i in range(count)
                       if self.existing_synonyms_list.item(i).checkState() == Qt.Checked)

        self.delete_selected_btn.setText(f"🗑️ Удалить выбранные ({selected})")
        self.delete_selected_btn.setEnabled(selected > 0)

    def select_all_existing(self, state: bool):
        """Выбирает или снимает выбор со всех существующих синонимов"""
        for i in range(self.existing_synonyms_list.count()):
            item = self.existing_synonyms_list.item(i)
            item.setCheckState(Qt.Checked if state else Qt.Unchecked)
        self.update_existing_stats()

    def delete_selected_synonyms(self):
        """Удаляет выбранные существующие синонимы и сразу обновляет менеджер"""
        selected_items = []
        for i in range(self.existing_synonyms_list.count()):
            item = self.existing_synonyms_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_items.append(item.text())

        if not selected_items:
            return

        reply = QMessageBox.question(
            self,
            "Удаление синонимов",
            f"Удалить {len(selected_items)} выбранных синонимов?\n\n"
            f"Примеры удаляемых:\n" + "\n".join([f"• {s}" for s in selected_items[:5]]),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # НЕМЕДЛЕННО обновляем в менеджере синонимов
            current_synonyms = self.syn_manager.get_synonyms(self.ngram_lemma, self.ngram_type)

            # Создаем новый список: оригинал + оставшиеся синонимы
            new_synonyms = [self.ngram_lemma]  # всегда первый - оригинал

            for synonym in current_synonyms:
                # Пропускаем оригинал (он уже добавлен) и выбранные для удаления
                if synonym != self.ngram_lemma and synonym not in selected_items:
                    new_synonyms.append(synonym)

            # НЕМЕДЛЕННО обновляем в менеджере
            self.syn_manager.add_synonyms(self.ngram_lemma, self.ngram_type, new_synonyms)

            # Обновляем активные синонимы
            active_synonyms = [s for s in new_synonyms if s != self.ngram_lemma]
            self.syn_manager.set_active_synonyms(self.ngram_lemma, self.ngram_type, active_synonyms)

            # Очищаем конкретные формы для удаленных синонимов
            self.clean_specific_forms_for_synonyms(selected_items)

            # Обновляем UI
            self.load_existing_synonyms()

            # Сообщаем об успехе
            QMessageBox.information(self, "Успех",
                                    f"✅ Удалено {len(selected_items)} синонимов!\n\n"
                                    f"Изменения сохранены в менеджере синонимов.")

    def clean_specific_forms_for_synonyms(self, deleted_synonyms: List[str]):
        """Очищает конкретные формы для удаленных синонимов"""
        try:
            # Получаем все формы
            all_forms = self.syn_manager.get_all_forms()

            # Собираем ключи для удаления
            keys_to_delete = []

            for key in all_forms.keys():
                # Ключ имеет формат: "ngram_type:original_phrase:synonym"
                parts = key.split(":", 2)
                if len(parts) == 3:
                    key_ngram_type, key_original, key_synonym = parts

                    # Проверяем совпадение по типу, оригинальной фразе и синониму
                    if (key_ngram_type == self.ngram_type.value and
                            key_original.lower() == self.ngram_lemma.lower() and
                            key_synonym in deleted_synonyms):
                        keys_to_delete.append(key)

            # Удаляем найденные ключи
            for key in keys_to_delete:
                del all_forms[key]
                logger.debug(f"🗑️ Удалена конкретная форма: {key}")

            # Сохраняем обратно
            if keys_to_delete:
                self.syn_manager.set_all_forms(all_forms)
                logger.info(f"🗑️ Удалено {len(keys_to_delete)} конкретных форм")

        except Exception as e:
            error_logger.log_error(f"Ошибка очистки конкретных форм: {e}")
    def create_word_widget(self, word: str, synonyms: List[str]) -> QWidget:
        """Создает виджет для выбора синонимов одного слова"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 5, 10, 5)

        # Заголовок слова
        word_label = QLabel(f"<b>Слово:</b> '{word}'")
        word_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addWidget(word_label)

        # Чекбоксы для синонимов
        checkboxes = []
        for synonym in synonyms:
            if synonym == word:
                # Основной синоним (само слово) - всегда отмечен
                cb = QCheckBox(f"✓ {synonym} <i>(основной)</i>")
                cb.setChecked(True)
                cb.setEnabled(False)  # Нельзя снять основной синоним
                cb.setStyleSheet("color: #27ae60; font-weight: bold;")
            else:
                cb = QCheckBox(synonym)
                cb.setChecked(True)  # По умолчанию все синонимы выбраны

            checkboxes.append(cb)
            cb.toggled.connect(self.update_preview)  # При изменении обновляем превью
            layout.addWidget(cb)

        return widget, checkboxes

    def load_word_synonyms(self):
        """Загружаем синонимы для каждого слова в n-грамме"""
        # Очищаем layout
        while self.words_layout.count():
            item = self.words_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.word_widgets.clear()

        # Разбираем n-грамму на слова
        ngram_words = self.ngram_lemma.split(', ')

        # Для каждого слова создаем виджет
        for word in ngram_words:
            # Получаем ВСЕ синонимы из группы (без ограничений)
            synonyms = self.syn_manager.get_unified_synonyms(word)

            # Создаем виджет для этого слова
            widget, checkboxes = self.create_word_widget(word, synonyms)  # ВСЕ синонимы

            self.words_layout.addWidget(widget)
            self.word_widgets.append({
                'word': word,
                'widget': widget,
                'checkboxes': checkboxes,
                'all_synonyms': synonyms
            })

        # Добавляем растягивающий элемент
        self.words_layout.addStretch()

    def get_selected_synonyms_per_word(self) -> List[List[str]]:
        """Получаем выбранные синонимы для каждого слова"""
        result = []

        for word_data in self.word_widgets:
            selected = []
            for cb in word_data['checkboxes']:
                if cb.isChecked():
                    # Извлекаем текст синонима (убираем маркеры)
                    text = cb.text()
                    if "✓" in text:
                        text = text.split("✓ ")[1]
                    if "<i>" in text:
                        text = text.split("<i>")[0].strip()
                    selected.append(text.strip())

            # Всегда добавляем само слово, даже если не выбрано
            if word_data['word'] not in selected:
                selected.insert(0, word_data['word'])

            result.append(selected)

        return result

    def generate_combinations(self, word_synonym_lists: List[List[str]]) -> List[str]:
        """Генерирует все комбинации из выбранных синонимов"""
        if not word_synonym_lists:
            return []

        # Начинаем с первого списка
        result = word_synonym_lists[0].copy()

        # Последовательно добавляем остальные слова
        for i in range(1, len(word_synonym_lists)):
            new_result = []
            for combo in result:
                for synonym in word_synonym_lists[i]:
                    new_result.append(f"{combo}, {synonym}")
            result = new_result

        return result

    def check_combinations_limit(self, selected_per_word: List[List[str]]) -> bool:
        """Проверяет, не слишком ли много комбинаций получится"""
        total = 1
        for syns in selected_per_word:
            total *= len(syns)

        if total > 1000:  # Если больше 1000 комбинаций
            reply = QMessageBox.warning(
                self,
                "Много комбинаций",
                f"Выбрано слишком много синонимов!\n\n"
                f"Будет создано: {total} комбинаций\n"
                f"Это может замедлить работу программы.\n\n"
                f"Продолжить?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            return reply == QMessageBox.Yes

        return True

    def update_preview(self):
        """Обновляет предпросмотр создаваемых синонимов"""
        selected_per_word = self.get_selected_synonyms_per_word()
        combinations = self.generate_combinations(selected_per_word)

        # Фильтруем оригинальную фразу
        combinations = [c for c in combinations if c != self.ngram_lemma]

        # Форматируем для отображения
        if not combinations:
            self.preview_text.setPlainText("Нет выбранных синонимов.")
            return

        # Считаем статистику
        selected_counts = [len(syns) for syns in selected_per_word]
        total_possible = 1
        for count in selected_counts:
            total_possible *= count

        preview_text = f"📊 Статистика:\n"
        preview_text += f"• Слов в фразе: {len(selected_per_word)}\n"
        for i, (word_data, syns) in enumerate(zip(self.word_widgets, selected_per_word), 1):
            preview_text += f"• Слово {i} ('{word_data['word']}'): {len(syns)} синонимов\n"
        preview_text += f"• Всего возможных комбинаций: {total_possible}\n"
        preview_text += f"• Будет создано синонимов: {len(combinations)}\n\n"
        preview_text += f"📝 Примеры создаваемых синонимов:\n"

        # Показываем первые 15 комбинаций
        for i, combo in enumerate(combinations[:15], 1):
            preview_text += f"{i}. {combo}\n"

        if len(combinations) > 15:
            preview_text += f"\n... и ещё {len(combinations) - 15} вариантов"

        self.preview_text.setPlainText(preview_text)

    def set_all_words_state(self, state: bool):
        """Установить состояние всех чекбоксов"""
        for word_data in self.word_widgets:
            for cb in word_data['checkboxes']:
                if cb.isEnabled():  # Не трогаем disabled чекбоксы
                    cb.setChecked(state)

        self.update_preview()

    def save_selected(self):
        """Сохранить выбранные синонимы (теперь только добавляет новые)"""
        # Получаем выбранные синонимы для каждого слова
        selected_per_word = self.get_selected_synonyms_per_word()

        # Проверяем лимит комбинаций
        if not self.check_combinations_limit(selected_per_word):
            return

        # Генерируем новые комбинации
        new_combinations = self.generate_combinations(selected_per_word)

        # Фильтруем оригинальную фразу
        new_combinations = [c for c in new_combinations if c != self.ngram_lemma]

        if not new_combinations:
            QMessageBox.information(self, "Без изменений",
                                    "Нет новых синонимов для добавления.\n"
                                    "Существующие синонимы можно удалять кнопкой '🗑️ Удалить выбранные'.")
            return

        # Получаем текущие синонимы (уже с учетом удалений)
        current_synonyms = self.syn_manager.get_synonyms(self.ngram_lemma, self.ngram_type)

        # Создаем итоговый список
        final_synonyms = current_synonyms.copy()  # берем уже существующие

        # Добавляем новые комбинации (исключая дубликаты)
        added_count = 0
        for combo in new_combinations:
            if combo not in final_synonyms:
                final_synonyms.append(combo)
                added_count += 1

        if added_count == 0:
            QMessageBox.information(self, "Без изменений",
                                    "Все новые комбинации уже существуют.")
            return

        # Показываем предварительный просмотр
        preview_text = f"📋 Будет добавлено {added_count} новых синонимов:\n\n"
        for i, combo in enumerate(new_combinations[:10], 1):
            preview_text += f"{i}. {combo}\n"

        if len(new_combinations) > 10:
            preview_text += f"\n... и ещё {len(new_combinations) - 10}"

        reply = QMessageBox.question(
            self,
            "Добавление новых синонимов",
            f"{preview_text}\n\n"
            f"Всего синонимов станет: {len(final_synonyms)}\n\n"
            f"Добавить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            # Сохраняем
            self.syn_manager.add_synonyms(self.ngram_lemma, self.ngram_type, final_synonyms)

            # Обновляем активные синонимы (добавляем новые к активным)
            current_active = self.syn_manager.get_active_synonyms(self.ngram_lemma, self.ngram_type)
            new_active = list(set(current_active + new_combinations))  # объединяем
            self.syn_manager.set_active_synonyms(self.ngram_lemma, self.ngram_type, new_active)

            # Показываем результат
            QMessageBox.information(self, "Успех",
                                    f"✅ Добавлено {added_count} новых синонимов!\n\n"
                                    f"Теперь всего синонимов: {len(final_synonyms)}\n"
                                    f"Активных синонимов: {len(new_active)}")

            self.accept()


# ==================== КЛАСС ДЛЯ ОБЪЕДИНЕНИЯ СИНОНИМИЧЕСКИХ ГРУПП ====================
class SynonymGrouper:
    """Объединяет синонимы в группы для согласованного использования"""

    def __init__(self, syn_manager: FastSynonymManager):
        self.syn_manager = syn_manager
        self.groups = {}  # word -> group_id
        self.group_words = {}  # group_id -> set of words
        self._build_groups()

    def _build_groups(self):
        """Построение групп синонимов из всех униграмм (итеративная версия)"""
        all_unigrams = self.syn_manager._data.get("unigram_synonyms", {})
        visited = set()
        group_id = 0

        # Создаем обратный индекс: слово -> все слова, у которых оно является синонимом
        reverse_index = defaultdict(set)
        for word, synonyms in all_unigrams.items():
            for syn in synonyms:
                if syn != word:
                    reverse_index[syn].add(word)

        for word in all_unigrams.keys():
            if word in visited:
                continue

            # Начинаем новую группу
            group_id += 1
            current_group = set()

            # Используем стек вместо рекурсии
            stack = [word]

            while stack:
                current = stack.pop()
                if current in visited:
                    continue

                visited.add(current)
                current_group.add(current)

                # Добавляем все синонимы этого слова
                current_synonyms = self.syn_manager.get_synonyms(current, ReplacementType.UNIGRAM)
                for syn in current_synonyms:
                    if syn not in visited and syn != current:
                        stack.append(syn)

                # Добавляем слова, у которых current является синонимом (через обратный индекс)
                for other_word in reverse_index.get(current, []):
                    if other_word not in visited:
                        stack.append(other_word)

            # Сохраняем группу
            for w in current_group:
                self.groups[w] = group_id
            self.group_words[group_id] = current_group

        logger.info(f"✅ Построено {len(self.group_words)} синонимических групп")

    def get_unified_synonyms(self, word: str) -> List[str]:
        """Получить все синонимы из группы для слова"""
        if word not in self.groups:
            return [word]

        group_id = self.groups[word]
        return sorted(list(self.group_words[group_id]))

    def update_synonym_groups(self):
        """Обновить все синонимы в файле согласно группам"""
        all_unigrams = self.syn_manager._data.get("unigram_synonyms", {})

        for group_id, words in self.group_words.items():
            unified_set = set(words)

            # Для каждого слова в группе устанавливаем все синонимы группы
            for word in words:
                if word in all_unigrams:
                    # Фильтруем самоссылки и сохраняем оригинал первым
                    other_synonyms = sorted([w for w in unified_set if w != word])
                    all_unigrams[word] = [word] + other_synonyms
                    logger.info(f"🔄 Обновлены синонимы для '{word}': {len(other_synonyms)} синонимов")


# ==================== ИСПРАВЛЕННЫЙ ЗАМЕНИТЕЛЬ ====================
class FastReplacer:
    def __init__(self, syn_manager: FastSynonymManager, stop_word_manager: StopWordManager):
        self.syn_manager = syn_manager
        self.stop_word_manager = stop_word_manager
        try:
            import pymorphy3
            self.morph = pymorphy3.MorphAnalyzer()
        except ImportError:
            self.morph = None

    def clean_spaces(self, text: str) -> str:
        """Очищает текст от лишних пробелов, но сохраняет новые строки."""
        # Заменяем множественные горизонтальные пробелы/табы на один пробел
        text = re.sub(r'[ \t]+', ' ', text)

        # Опционально: сжимаем множественные новые строки (например, >2 \n на 2), чтобы убрать лишние пустые строки
        text = re.sub(r'\n{3,}', '\n\n', text)  # Если не нужно, удалите эту строку

        # Убираем пробелы перед знаками препинания (но не трогаем \n)
        text = re.sub(r'[ \t]+([.,;:!?])', r'\1', text)

        # Убираем пробелы после открывающих скобок/кавычек
        text = re.sub(r'([({\["\'])[ \t]+', r'\1', text)

        # Убираем пробелы перед закрывающими скобками/кавычками
        text = re.sub(r'[ \t]+([)}\]"\'])', r'\1', text)

        return text.strip()

    def get_text_lemmas(self, text: str) -> Set[str]:
        """Получает все леммы из текста"""
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
        """Получает все леммы из синонима (может быть фразой)"""
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
        """Находит лучший синоним для замены"""
        if not synonyms:
            return None, "Нет доступных синонимов"

        # ЗАЩИТА ОТ ПУСТОГО СПИСКА
        if len(synonyms) <= 1:
            return None, "Только один синоним (оригинал)"

        if len(synonyms) > 1 and random.random() < 0.20:  # 20% шанс оставить оригинал
            return None, "Случайно оставили оригинал"  # или return original, ""

        # иначе обычная логика
        chosen = random.choice([s for s in synonyms if s != ngram_key])

        # Для униграмм - дополнительная проверка на леммы в контексте
        if ngram_type == ReplacementType.UNIGRAM:
            # Сначала пытаемся найти синонимы с леммами, которых еще нет в контексте
            available_synonyms = []

            for synonym in synonyms:
                synonym_lemmas = self.get_synonym_lemmas(synonym)
                if not synonym_lemmas:
                    available_synonyms.append(synonym)
                    continue

                # Проверяем, есть ли леммы синонима в контексте
                synonym_in_context = any(lemma in context_lemmas for lemma in synonym_lemmas)
                if not synonym_in_context:
                    available_synonyms.append(synonym)

            # Если нашли синонимы с новыми леммами - выбираем из них
            if available_synonyms:
                return random.choice(available_synonyms), ""
            else:
                # Нет новых лемм → стараемся вернуть именно оригинал без адаптации
                if ngram_key in synonyms:
                    logger.info(f"Оставляем оригинал без адаптации: '{ngram_key}'")
                    return ngram_key, "Нет новых лемм → оставили оригинал"
                else:
                    # Если оригинала нет в списке — берём случайный (редкий случай)
                    chosen = random.choice(synonyms)
                    logger.warning(f"Оригинал отсутствует в synonyms → выбрано '{chosen}'")
                    return chosen, "Нет новых лемм, оригинал отсутствует"

        # Для ВСЕХ остальных типов (биграмм, триграмм, n-грамм, с предлогами, стоп-слов)
        # - просто рандом между всеми синонимами
        return random.choice(synonyms), ""

    def replace_ngrams(self, texts: List[str], ngrams_data: Dict, ngram_type: ReplacementType) -> Tuple[
        List[str], List[ReplacementInfo]]:
        replacements = []
        result_texts = texts.copy()

        # ЗАЩИТА ОТ ПУСТЫХ ДАННЫХ
        if not ngrams_data:
            logger.info(f"🔄 Нет данных для замены {ngram_type.value}")
            return result_texts, replacements  # Всегда возвращаем кортеж

        logger.info(f"🔄 Начинаем замену {ngram_type.value}, ngrams: {len(ngrams_data)}")

        # Собираем ВСЕ позиции для замены
        all_positions = []
        total_positions = 0

        for ngram_key, ngram_info in ngrams_data.items():
            # УНИВЕРСАЛЬНАЯ ПРОВЕРКА replace
            should_replace = False
            positions = []

            # ДЛЯ УНИГРАММ - новая структура
            if ngram_type == ReplacementType.UNIGRAM:
                # Теперь ngram_info - словарь с полями
                should_replace = ngram_info.get('replace', True)
                positions = ngram_info.get('positions', [])
            else:
                # Для остальных типов
                if hasattr(ngram_info, 'replace'):
                    should_replace = ngram_info.replace
                    positions = ngram_info.positions
                else:
                    should_replace = ngram_info.get('replace', True)
                    positions = ngram_info.get('positions', [])

            if not should_replace:
                continue

            # Получаем активные синонимы
            active_synonyms = self.syn_manager.get_active_synonyms(ngram_key, ngram_type)

            # ПРОВЕРКА: если нет активных синонимов, пропускаем
            if not active_synonyms or len(active_synonyms) == 0:
                logger.debug(f"  Пропуск {ngram_key}: нет активных синонимов")
                continue

            total_positions += len(positions)

            # Добавляем позиции
            for pos in positions:
                all_positions.append({
                    'text_index': pos[0],
                    'start': pos[1],
                    'end': pos[2],
                    'ngram_key': ngram_key,
                    'synonyms': active_synonyms,
                    'ngram_type': ngram_type
                })

        logger.info(f"📊 Всего позиций для обработки: {total_positions}")

        # ЕСЛИ НЕТ ПОЗИЦИЙ ДЛЯ ОБРАБОТКИ - ВОЗВРАЩАЕМ ПУСТОЙ РЕЗУЛЬТАТ
        if total_positions == 0:
            logger.info(f"🎯 Нет позиций для замены {ngram_type.value}")
            return result_texts, replacements  # Всегда возвращаем кортеж

        # Сортируем позиции
        all_positions.sort(key=lambda x: (x['text_index'], -x['start']))

        # Выполняем замены
        replaced_count = 0
        skipped_count = 0

        for pos_info in all_positions:
            text_index = pos_info['text_index']
            start = pos_info['start']
            end = pos_info['end']
            ngram_key = pos_info['ngram_key']
            synonyms = pos_info['synonyms']
            ngram_type = pos_info['ngram_type']

            if text_index >= len(result_texts):
                continue

            current_text = result_texts[text_index]
            if start >= len(current_text) or end > len(current_text):
                continue

            original_phrase = current_text[start:end]

            # Получаем контекст вокруг замены
            context_start = max(0, start - 100)  # Увеличиваем контекст для лучшей проверки
            context_end = min(len(current_text), end + 100)
            context = current_text[context_start:context_end]

            # Получаем ВСЕ леммы из контекста для проверки
            context_lemmas = self.get_text_lemmas(context)

            # Находим лучший синоним с учетом уже имеющихся лемм
            best_synonym, skip_reason = self.find_best_synonym(
                synonyms, context_lemmas, ngram_key, original_phrase, ngram_type
            )

            if not best_synonym:
                # Не нашли подходящий синоним, пропускаем замену
                replacement = ReplacementInfo(
                    original=original_phrase,
                    new=original_phrase,  # Оставляем без изменений
                    start=start,
                    end=end,
                    text_index=text_index,
                    type=ngram_type,
                    used_synonym="",
                    lemma=ngram_key,
                    skipped_reason=skip_reason
                )
                replacements.append(replacement)
                skipped_count += 1
                continue

            valid_synonyms = synonyms[:]
            if not valid_synonyms:
                # Нет подходящих синонимов

                continue
            # БЕРЁМ СЛУЧАЙНЫЙ, НО ПРОВЕРЯЕМ НА ОРИГИНАЛ
            best_synonym = random.choice(valid_synonyms)

            # СРАЗУ ПРОВЕРЯЕМ СОВПАДЕНИЕ — НЕ ДАЁМ АДАПТИРОВАТЬ ОРИГИНАЛ
            orig_clean = ' '.join(original_phrase.strip().split()).lower()
            best_clean = ' '.join(best_synonym.strip().split()).lower()

            if orig_clean == best_clean:
                new_phrase = original_phrase
                logger.info(f"ЗАЩИТА: оригинал выбран → '{new_phrase}' (без адаптации)")
                # Пропускаем адаптацию полностью
            else:
                new_phrase = self.adapt_synonym_form(ngram_key, best_synonym, original_phrase, ngram_type)

            # Проверяем безопасность замены
            if self.is_safe_replacement(current_text, start, end, new_phrase):
                # Выполняем замену
                before = current_text[:start]
                after = current_text[end:]
                new_text = before + new_phrase + after

                # ОЧИЩАЕМ ПРОБЕЛЫ после замены
                new_text = self.clean_spaces(new_text)

                result_texts[text_index] = new_text
                replaced_count += 1

                # Пересчитываем позиции для следующих замен в этом тексте
                length_diff = len(new_text) - len(current_text)
                for other_pos in all_positions:
                    if other_pos['text_index'] == text_index and other_pos['start'] > start:
                        other_pos['start'] += length_diff
                        other_pos['end'] += length_diff

                replacement = ReplacementInfo(
                    original=original_phrase,
                    new=new_phrase,
                    start=start,
                    end=end,
                    text_index=text_index,
                    type=ngram_type,
                    used_synonym=best_synonym,
                    lemma=ngram_key
                )
                replacements.append(replacement)

        logger.info(
            f"🎯 Завершена замена {ngram_type.value}: {replaced_count}/{total_positions} замен, пропущено: {skipped_count}")

        # Дополнительная очистка всех текстов в конце
        result_texts = [self.clean_spaces(text) for text in result_texts]

        return result_texts, replacements

    def check_synonym_in_context(self, context: str, synonym: str, original_phrase: str) -> bool:
        """Проверяет, есть ли лемма синонима в контексте"""
        try:
            if not self.morph:
                return False

            # Получаем лемму синонима
            syn_parsed = self.morph.parse(synonym)[0]
            syn_lemma = syn_parsed.normal_form

            # Ищем все слова в контексте
            words = re.findall(r'\b\w+\b', context.lower())

            for word in words:
                if word == original_phrase.lower():
                    continue

                word_parsed = self.morph.parse(word)[0]
                word_lemma = word_parsed.normal_form

                if word_lemma == syn_lemma:
                    return True

            return False

        except Exception as e:
            error_logger.log_error(f"Ошибка проверки синонима в контексте: {e}")
            return False

    def adapt_synonym_form_simple(self, original_phrase: str, synonym: str, ngram_type: ReplacementType) -> str:
        """Упрощенная адаптация формы - только регистр"""
        try:
            # Простая адаптация - только регистр
            if original_phrase.istitle():
                return synonym.title()
            elif original_phrase.isupper():
                return synonym.upper()
            else:
                return synonym
        except:
            return synonym

    def is_safe_replacement(self, text: str, start: int, end: int, new_phrase: str) -> bool:
        """Проверка безопасности замены"""
        if not new_phrase:
            return False

        # Проверяем границы слов
        if start > 0 and text[start - 1].isalnum():
            return False
        if end < len(text) and text[end].isalnum():
            return False

        return True

    def collect_all_positions_for_text(self, text_index: int, unigrams: Dict, bigrams: Dict,
                                       trigrams: Dict, ngrams: Dict, prepositional: Dict) -> List[Dict]:
        """Собирает ВСЕ позиции для замен в одном тексте, учитывая состояние чекбоксов"""
        all_positions = []
        occupied_positions = set()

        def has_overlap(start, end):
            for occupied in occupied_positions:
                occ_start, occ_end = occupied
                if not (end <= occ_start or start >= occ_end):
                    return True
            return False

        # Функция-помощник с проверкой состояния replace
        def add_positions_with_check(data_dict, ngram_type):
            nonlocal all_positions, occupied_positions

            for ngram_key, ngram_info in data_dict.items():
                # КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: проверяем состояние replace
                should_replace = False
                positions = []

                if ngram_type == ReplacementType.UNIGRAM:
                    # Для униграмм: проверяем поле replace
                    should_replace = ngram_info.get('replace', False)  # По умолчанию False!
                    positions = ngram_info.get('positions', [])
                else:
                    # Для остальных типов
                    if hasattr(ngram_info, 'replace'):
                        should_replace = ngram_info.replace
                        positions = ngram_info.positions
                    else:
                        should_replace = ngram_info.get('replace', False)  # По умолчанию False!
                        positions = ngram_info.get('positions', [])

                # Пропускаем если НЕ выбрано для замены
                if not should_replace:
                    continue

                # Получаем активные синонимы
                active_synonyms = self.syn_manager.get_active_synonyms(ngram_key, ngram_type)
                if not active_synonyms or len(active_synonyms) <= 1:
                    continue

                # Добавляем только первую непересекающуюся позицию
                for pos in positions:
                    if pos[0] == text_index:
                        start, end = pos[1], pos[2]

                        # Пропускаем если пересекается
                        if has_overlap(start, end):
                            continue

                        all_positions.append({
                            'text_index': text_index,
                            'start': start,
                            'end': end,
                            'ngram_key': ngram_key,
                            'synonyms': active_synonyms,
                            'ngram_type': ngram_type
                        })

                        occupied_positions.add((start, end))
                        break  # только первое вхождение

        # Собираем в порядке от длинных к коротким
        add_positions_with_check(ngrams, ReplacementType.NGRAM)
        add_positions_with_check(prepositional, ReplacementType.PREPOSITIONAL)
        add_positions_with_check(trigrams, ReplacementType.TRIGRAM)
        add_positions_with_check(bigrams, ReplacementType.BIGRAM)
        add_positions_with_check(unigrams, ReplacementType.UNIGRAM)

        # Сортируем по начальной позиции
        all_positions.sort(key=lambda x: x['start'])

        return all_positions

    def replace_with_priority(self, texts: List[str], unigrams: Dict, bigrams: Dict, trigrams: Dict,
                              ngrams: Dict, prepositional: Dict) -> Tuple[List[str], List[ReplacementInfo]]:
        """Обработка ВСЕХ замен за один проход по тексту - УПРОЩЕННЫЙ ВАРИАНТ"""
        all_replacements = []
        result_texts = []

        logger.info(f"🔄 Начинаем замену {len(texts)} текстов одним проходом...")

        for text_index, original_text in enumerate(texts):
            logger.debug(f"  Обработка текста {text_index + 1}/{len(texts)}")

            # Собираем все позиции для этого текста
            all_positions = self.collect_all_positions_for_text(
                text_index, unigrams, bigrams, trigrams, ngrams, prepositional
            )

            if not all_positions:
                logger.debug(f"    Нет позиций для замены")
                result_texts.append(original_text)
                continue

            logger.debug(f"    Найдено {len(all_positions)} позиций для замены")

            # Сортируем по позиции (от начала к концу)
            all_positions.sort(key=lambda x: x['start'])

            # Обрабатываем текст
            processed_text = original_text
            text_replacements = []
            last_position = 0  # последняя обработанная позиция
            i = 0  # индекс в all_positions

            while i < len(all_positions):
                pos_info = all_positions[i]
                start = pos_info['start']
                end = pos_info['end']
                ngram_type = pos_info['ngram_type']
                ngram_key = pos_info['ngram_key']
                synonyms = pos_info['synonyms']

                # Проверяем, что позиция актуальна
                if start >= len(processed_text) or end > len(processed_text):
                    i += 1
                    continue

                # Получаем оригинальную фразу
                original_phrase = processed_text[start:end]

                # Выбираем синоним (случайный, но не оригинал)
                valid_synonyms = synonyms[:]
                if not valid_synonyms:
                    # Нет подходящих синонимов
                    i += 1
                    continue

                # Случайный выбор синонима
                # БЕРЁМ СЛУЧАЙНЫЙ, НО ПРОВЕРЯЕМ НА ОРИГИНАЛ
                best_synonym = random.choice(valid_synonyms)

                # СРАЗУ ПРОВЕРЯЕМ СОВПАДЕНИЕ — НЕ ДАЁМ АДАПТИРОВАТЬ ОРИГИНАЛ
                orig_clean = ' '.join(original_phrase.strip().split()).lower()
                best_clean = ' '.join(best_synonym.strip().split()).lower()

                if orig_clean == best_clean:
                    new_phrase = original_phrase
                    logger.info(f"ЗАЩИТА: оригинал выбран → '{new_phrase}' (без адаптации)")
                    # Пропускаем адаптацию полностью
                else:
                    new_phrase = self.adapt_synonym_form(ngram_key, best_synonym, original_phrase, ngram_type)
                logger.debug(f"new_phrase после адаптации: '{new_phrase}' | original: '{original_phrase}'")
                # Пропускаем если замена бессмысленна
                if new_phrase == original_phrase:
                    i += 1
                    continue

                # Проверяем безопасность замены
                if self.is_safe_replacement(processed_text, start, end, new_phrase):
                    # Выполняем замену
                    before = processed_text[:start]
                    after = processed_text[end:]
                    processed_text = before + new_phrase + after

                    # Добавляем информацию о замене
                    replacement = ReplacementInfo(
                        original=original_phrase,
                        new=new_phrase,
                        start=start,
                        end=end,
                        text_index=text_index,
                        type=ngram_type,
                        used_synonym=best_synonym,
                        lemma=ngram_key
                    )
                    text_replacements.append(replacement)

                    # Сдвигаем все последующие позиции
                    length_diff = len(new_phrase) - len(original_phrase)
                    for j in range(i + 1, len(all_positions)):
                        if all_positions[j]['start'] > start:
                            all_positions[j]['start'] += length_diff
                            all_positions[j]['end'] += length_diff

                i += 1

            # Очищаем текст
            processed_text = self.clean_spaces(processed_text)
            result_texts.append(processed_text)
            all_replacements.extend(text_replacements)

            logger.debug(f"    Выполнено {len(text_replacements)} замен")

        logger.info(f"🎯 Завершено. Всего замен: {len(all_replacements)}")
        return result_texts, all_replacements

    def adapt_synonym_form(self, original_ngram: str, synonym_ngram: str, original_form: str,
                           ngram_type: ReplacementType) -> str:
        # Если синоним — это именно ключ-лемма (без предлога и формы), а не полная фраза из текста — возвращаем оригинал как есть
        if ngram_type in (
                ReplacementType.PREPOSITIONAL, ReplacementType.BIGRAM, ReplacementType.TRIGRAM, ReplacementType.NGRAM):
            # Сравниваем очищенную лемму синонима с ключом ngram_key
            syn_clean = ' '.join(synonym_ngram.strip().split()).lower()
            key_clean = ' '.join(original_ngram.strip().split()).lower()

            if syn_clean == key_clean:
                logger.info(
                    f"ЗАЩИТА ДЛЯ ФРАЗ: синоним = ngram_key (лемма) → возвращаем оригинальную форму из текста '{original_form}'")
                return original_form  # ← возвращаем то, что стояло в тексте!

        # Всё остальное — как было раньше
        try:
            specific_form = self.syn_manager.get_specific_form(
                original_phrase=original_form,
                synonym=synonym_ngram,
                ngram_type=ngram_type
            )
            if specific_form:
                return self.apply_case(original_form, specific_form)

            if not self.morph or ngram_type == ReplacementType.PREPOSITIONAL:
                return self.apply_case(original_form, synonym_ngram)

            result = synonym_ngram  # значение по умолчанию

            if ngram_type == ReplacementType.UNIGRAM:
                # Для униграмм - простое склонение
                result = self.adapt_unigram_form(original_form, synonym_ngram)

            elif ngram_type in [ReplacementType.BIGRAM, ReplacementType.TRIGRAM, ReplacementType.NGRAM]:
                # Для биграмм, триграмм и n-грамм - адаптация всех слова
                result = self.adapt_phrase_form(original_form, synonym_ngram, ngram_type)

            # Применяем регистр оригинала
            return self.apply_case(original_form, result)

        except Exception as e:
            error_logger.log_error(f"Ошибка адаптации формы '{original_form}' -> '{synonym_ngram}': {e}")
            # В случае ошибки пытаемся сохранить регистр
            return self.apply_case(original_form, synonym_ngram)

    def adapt_unigram_form(self, original_form: str, synonym: str) -> str:
        """Адаптация формы для униграмм"""
        try:
            original_parsed = self.morph.parse(original_form)[0]
            synonym_parsed = self.morph.parse(synonym)[0]

            # Получаем грамматические характеристики оригинала
            grammemes = set(original_parsed.tag.grammemes)

            # Пытаемся просклонять синоним
            new_form = synonym_parsed.inflect(grammemes)

            if new_form:
                return new_form.word
            else:
                # Если склонение не удалось, возвращаем исходный синоним
                return synonym

        except Exception as e:
            error_logger.log_warning(f"Не удалось адаптировать униграмму '{original_form}' -> '{synonym}': {e}")
            return synonym

    def adapt_phrase_form(self, original_phrase: str, synonym_phrase: str, ngram_type: ReplacementType) -> str:
        """Адаптация формы для фраз (биграмм, триграмм, n-грамм)"""
        try:
            # ПРОВЕРЯЕМ ЕСТЬ ЛИ КОНКРЕТНАЯ ФОРМА ДЛЯ ЭТОЙ ФРАЗЫ
            specific_form = self.syn_manager.get_specific_form(
                original_phrase=original_phrase,
                synonym=synonym_phrase,
                ngram_type=ngram_type
            )

            if specific_form:
                # Используем сохранённую конкретную форму фразы
                # ВАЖНО: Применяем регистр оригинала
                return self.apply_case(original_phrase, specific_form)

            # Разбиваем на слова, сохраняя разделители
            original_parts = self.split_phrase_preserving_delimiters(original_phrase)
            synonym_parts = self.split_phrase_preserving_delimiters(synonym_phrase)

            # Получаем списки слов (без разделителей)
            original_words = [p for p in original_parts if p['type'] == 'word']
            synonym_words = [p for p in synonym_parts if p['type'] == 'word']

            # Если количество слов разное - адаптируем то, что можем
            if len(original_words) != len(synonym_words):
                # Адаптируем слова попарно, насколько возможно
                adapted_words = []
                min_len = min(len(original_words), len(synonym_words))

                for i in range(min_len):
                    adapted_word = self.adapt_single_word_in_context(
                        original_words[i]['text'],
                        synonym_words[i]['text'],
                        original_phrase
                    )
                    adapted_words.append(adapted_word)

                # Остальные слова берем как есть из синонима
                for i in range(min_len, len(synonym_words)):
                    adapted_words.append(synonym_words[i]['text'])

                return self.reconstruct_phrase_with_delimiters(original_parts, synonym_parts, adapted_words)

            # Если количество слов совпадает - адаптируем каждое слово
            adapted_words = []
            for orig_word, syn_word in zip(original_words, synonym_words):
                adapted_word = self.adapt_single_word_in_context(
                    orig_word['text'], syn_word['text'], original_phrase
                )
                adapted_words.append(adapted_word)

            # Восстанавливаем фразу с оригинальными разделителями
            return self.reconstruct_phrase_with_delimiters(original_parts, synonym_parts, adapted_words)

        except Exception as e:
            error_logger.log_error(f"Ошибка адаптации фразы '{original_phrase}' -> '{synonym_phrase}': {e}")
            return self.apply_case(original_phrase, synonym_phrase)

    def adapt_single_word_in_context(self, original_word: str, synonym_word: str, context_phrase: str) -> str:
        """Адаптация одного слова в контексте фразы"""
        try:
            original_parsed = self.morph.parse(original_word)[0]
            synonym_parsed = self.morph.parse(synonym_word)[0]

            # Получаем грамматические характеристики оригинала
            grammemes = set(original_parsed.tag.grammemes)

            # Пытаемся просклонять синоним
            new_form = synonym_parsed.inflect(grammemes)

            if new_form:
                return new_form.word
            else:
                # Если склонение не удалось, проверяем возможность приведения к тому же роду/числу
                if self.should_preserve_gender_number(original_parsed, synonym_parsed):
                    preserved_form = self.preserve_gender_number(original_parsed, synonym_parsed)
                    if preserved_form:
                        return preserved_form

            return synonym_word

        except Exception as e:
            error_logger.log_warning(f"Не удалось адаптировать слово '{original_word}' -> '{synonym_word}': {e}")
            return synonym_word

    def should_preserve_gender_number(self, original_parsed, synonym_parsed) -> bool:
        """Определяет, нужно ли сохранять род и число"""
        original_pos = original_parsed.tag.POS
        synonym_pos = synonym_parsed.tag.POS

        # Сохраняем для существительных, прилагательных, причастий
        preserve_pos = {'NOUN', 'ADJF', 'ADJS', 'PRTF', 'PRTS'}

        return (original_pos in preserve_pos and
                synonym_pos in preserve_pos)

    def preserve_gender_number(self, original_parsed, synonym_parsed) -> str:
        """Сохраняет род и число при невозможности полного склонения"""
        try:
            target_grammemes = set()

            # Сохраняем число
            if 'sing' in original_parsed.tag:
                target_grammemes.add('sing')
            elif 'plur' in original_parsed.tag:
                target_grammemes.add('plur')

            # Сохраняем род для единственного числа
            if 'sing' in target_grammemes:
                if 'masc' in original_parsed.tag:
                    target_grammemes.add('masc')
                elif 'femn' in original_parsed.tag:
                    target_grammemes.add('femn')
                elif 'neut' in original_parsed.tag:
                    target_grammemes.add('neut')

            # Сохраняем падеж, если возможно
            cases = {'nomn', 'gent', 'datv', 'accs', 'ablt', 'loct'}
            for case in cases:
                if case in original_parsed.tag:
                    target_grammemes.add(case)
                    break

            if target_grammemes:
                new_form = synonym_parsed.inflect(target_grammemes)
                if new_form:
                    return new_form.word

            return None

        except Exception:
            return None

    def split_phrase_preserving_delimiters(self, phrase: str) -> List[Dict]:
        """Разбивает фразу на слова и разделители с сохранением позиционной информации"""
        parts = []

        # Регулярное выражение для поиска слов и не-слов
        pattern = r'(\b\w+\b|[^\w\s]+|\s+)'
        matches = re.finditer(pattern, phrase)

        for match in matches:
            text = match.group()
            if re.match(r'\b\w+\b', text):
                parts.append({'type': 'word', 'text': text})
            else:
                parts.append({'type': 'delimiter', 'text': text})

        return parts

    def reconstruct_phrase_with_delimiters(self, original_parts: List[Dict],
                                           synonym_parts: List[Dict],
                                           adapted_words: List[str]) -> str:
        """Восстанавливает фразу с адаптированными словами и оригинальными разделителями"""
        result_parts = []
        word_index = 0

        for part in original_parts:
            if part['type'] == 'word':
                if word_index < len(adapted_words):
                    result_parts.append(adapted_words[word_index])
                    word_index += 1
                else:
                    # Если что-то пошло не так, используем оригинальное слово из синонима
                    if word_index < len(synonym_parts):
                        syn_part = synonym_parts[word_index]
                        if syn_part['type'] == 'word':
                            result_parts.append(syn_part['text'])
                            word_index += 1
            else:
                result_parts.append(part['text'])

        return ''.join(result_parts)

    def apply_case(self, original: str, text: str) -> str:
        """Применяет регистр оригинала к тексту"""
        if not text or not original:
            return text

        # Если оригинал полностью в верхнем регистре
        if original.isupper():
            return text.upper()

        # Если оригинал полностью в нижнем регистре
        if original.islower():
            return text.lower()

        # Если оригинал с заглавной буквы (только первая буква заглавная)
        if original.istitle():
            return text.title()

        # Если оригинал с заглавной буквы в начале предложения
        if len(original) > 0 and original[0].isupper() and original[1:].islower():
            return text[0].upper() + text[1:].lower() if text else text

        # Смешанный регистр - оставляем как есть
        return text


# ==================== УЛУЧШЕННЫЙ РЕДАКТОР ФОРМ ====================
class FastFormEditDialog(QDialog):
    def __init__(self, ngram_lemma: str, ngram_type: ReplacementType, syn_manager: FastSynonymManager,
                 forms_dict: Dict[str, int], parent=None):
        super().__init__(parent)
        self.ngram_lemma = ngram_lemma  # ← БЫЛО: self.ngram, СТАЛО: self.ngram_lemma
        self.ngram_type = ngram_type
        self.syn_manager = syn_manager
        self.forms_dict = forms_dict  # Словарь форм: {форма: количество}
        self.current_synonym = ""
        self.parent_widget = parent

        self.setWindowTitle(f"Конкретные формы: {ngram_lemma}")
        self.setGeometry(400, 300, 1200, 800)
        self.setup_ui()
        self.load_data()
        self.center_on_parent()

    def center_on_parent(self):
        """Центрирует окно относительно родительского окна"""
        parent_widget = self.parent()
        if parent_widget:
            parent_geometry = parent_widget.frameGeometry()
            screen = QGuiApplication.screenAt(parent_geometry.center())
            if screen:
                screen_geometry = screen.availableGeometry()
                x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
                self.move(x, y)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Заголовок
        title_label = QLabel(f"🔤 Редактирование конкретных форм замен для:\nЛемма: {self.ngram_lemma}")
        title_label.setStyleSheet("font-weight: bold; font-size: 12pt; margin: 10px;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Инструкция
        instruction = QLabel("Для каждой конкретной формы употребления можно задать свою замену синонимом")
        instruction.setStyleSheet("color: #666; margin: 5px;")
        layout.addWidget(instruction)

        # Выбор синонима
        synonym_layout = QHBoxLayout()
        synonym_layout.addWidget(QLabel("Синоним для замены:"))

        self.synonym_combo = QComboBox()
        self.synonym_combo.currentTextChanged.connect(self.on_synonym_changed)
        synonym_layout.addWidget(self.synonym_combo)

        # Кнопка автозаполнить все
        self.auto_fill_all_btn = QPushButton("🤖 Автозаполнить ВСЕ формы")
        self.auto_fill_all_btn.clicked.connect(self.auto_fill_all_forms)
        self.auto_fill_all_btn.setToolTip("Автоматически заполнить формы для всех синонимов")
        synonym_layout.addWidget(self.auto_fill_all_btn)

        synonym_layout.addStretch()
        layout.addLayout(synonym_layout)

        # Таблица форм
        self.forms_table = QTableWidget()
        self.forms_table.setColumnCount(3)
        self.forms_table.setHorizontalHeaderLabels(["Исходная форма", "Количество", "Замена синонимом"])
        self.forms_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.forms_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.forms_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        # Устанавливаем подсказки для столбцов
        self.forms_table.horizontalHeaderItem(0).setToolTip("Конкретная форма как встречается в тексте")
        self.forms_table.horizontalHeaderItem(1).setToolTip("Количество вхождений в тексте")
        self.forms_table.horizontalHeaderItem(2).setToolTip("Конкретная замена для этой формы")

        layout.addWidget(self.forms_table)

        # Кнопки
        button_layout = QHBoxLayout()

        save_btn = QPushButton("💾 Сохранить все формы")
        save_btn.clicked.connect(self.save_forms)

        auto_btn = QPushButton("🤖 Автозаполнить формы")
        auto_btn.clicked.connect(self.auto_fill_forms)
        auto_btn.setToolTip("Автоматически заполнить формы на основе выбранного синонима")

        cancel_btn = QPushButton("❌ Закрыть")
        cancel_btn.clicked.connect(self.accept)

        button_layout.addWidget(save_btn)
        button_layout.addWidget(auto_btn)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def load_data(self):
        """Быстрая загрузка данных"""
        # Загружаем синонимы
        synonyms = self.syn_manager.get_synonyms(self.ngram_lemma, self.ngram_type)
        self.synonym_combo.clear()
        for synonym in synonyms:
            if synonym != self.ngram_lemma:  # Не показываем оригинальную лемму
                self.synonym_combo.addItem(synonym)

        if self.synonym_combo.count() > 0:
            self.synonym_combo.setCurrentIndex(0)

    def on_synonym_changed(self, synonym):
        """При смене синонима загружаем его формы"""
        self.current_synonym = synonym
        self.load_forms_table()

    def load_forms_table(self):
        """Загрузка таблицы форм для выбранного синонима"""
        if not self.current_synonym:
            return

        print(f"Загрузка форм для {self.ngram_lemma}, синоним: {self.current_synonym}")  # ← ИСПРАВЛЕНО: self.ngram_lemma
        print(f"forms_dict: {self.forms_dict}")

        if not self.forms_dict:
            print("НЕТ ФОРМ! Таблица будет пустой.")
            self.forms_table.setRowCount(0)
            return

        # Показываем все формы из текста, отсортированные по количеству
        sorted_forms = sorted(self.forms_dict.items(), key=lambda x: x[1], reverse=True)
        self.forms_table.setRowCount(len(sorted_forms))

        for row, (form, count) in enumerate(sorted_forms):
            # Исходная форма
            form_item = QTableWidgetItem(form)
            form_item.setFlags(form_item.flags() & ~Qt.ItemIsEditable)
            form_item.setToolTip(f"Форма употребления: {form}")
            self.forms_table.setItem(row, 0, form_item)

            # Количество
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            self.forms_table.setItem(row, 1, count_item)

            # Замена для этого синонима
            current_replacement = self.syn_manager.get_specific_form(form, self.current_synonym, self.ngram_type)
            replacement_item = QTableWidgetItem(current_replacement or "")
            replacement_item.setToolTip(f"Замена для '{form}' синонимом '{self.current_synonym}'")
            self.forms_table.setItem(row, 2, replacement_item)

    # ... остальные методы (auto_fill_forms, auto_fill_all_forms, adapt_with_gender_number, save_forms) остаются без изменений

    def auto_fill_forms(self):
        """Улучшенное автозаполнение форм с правильной адаптацией"""
        if not self.current_synonym:
            QMessageBox.warning(self, "Ошибка", "Выберите синоним для автозаполнения")
            return

        try:
            # Получаем экземпляр replacer
            replacer = None

            # ИСПРАВЛЕНИЕ: используем self.parent_widget
            parent = self.parent_widget

            # Ищем родителя с replacer
            while parent and not hasattr(parent, 'replacer'):
                parent = parent.parent_widget if hasattr(parent, 'parent_widget') else None

            if parent and hasattr(parent, 'replacer'):
                replacer = parent.replacer
            else:
                # Если replacer не найден, создаем новый
                replacer = FastReplacer(self.syn_manager,
                                        parent.stop_word_manager if hasattr(parent, 'stop_word_manager') else None)

            for row in range(self.forms_table.rowCount()):
                form_item = self.forms_table.item(row, 0)
                replacement_item = self.forms_table.item(row, 2)

                if form_item and replacement_item:
                    original_form = form_item.text()
                    current_value = replacement_item.text().strip()

                    # Заполняем только если поле пустое ИЛИ содержит только базовый синоним без адаптации
                    should_fill = (not current_value or
                                   current_value == self.current_synonym or
                                   current_value.lower() == self.current_synonym.lower())

                    if should_fill:
                        # Для униграмм используем правильную адаптацию
                        if self.ngram_type == ReplacementType.UNIGRAM:
                            if hasattr(replacer, 'adapt_unigram_form') and replacer.morph:
                                try:
                                    # Парсим оригинальную форму
                                    parsed = replacer.morph.parse(original_form)[0]

                                    # Парсим синоним
                                    syn_parsed = replacer.morph.parse(self.current_synonym)[0]

                                    # Получаем грамматические характеристики оригинала
                                    grammemes = set(parsed.tag.grammemes)

                                    # Пытаемся просклонять синоним
                                    new_form = syn_parsed.inflect(grammemes)

                                    if new_form:
                                        adapted_form = new_form.word
                                    else:
                                        # Если склонение не удалось, проверяем род/число
                                        adapted_form = self.adapt_with_gender_number(parsed, syn_parsed)

                                    # Применяем регистр оригинала
                                    adapted_form = replacer.apply_case(original_form, adapted_form)
                                    replacement_item.setText(adapted_form)

                                except Exception as e:
                                    error_logger.log_warning(
                                        f"Не удалось адаптировать '{original_form}' -> '{self.current_synonym}': {e}")
                                    # В случае ошибки - простая адаптация регистра
                                    adapted_form = replacer.apply_case(original_form, self.current_synonym)
                                    replacement_item.setText(adapted_form)
                            else:
                                # Простая адаптация регистра
                                adapted_form = replacer.apply_case(original_form, self.current_synonym)
                                replacement_item.setText(adapted_form)
                        else:
                            # Для фраз используем адаптацию формы
                            adapted_form = replacer.adapt_synonym_form(
                                self.ngram_lemma,
                                self.current_synonym,
                                original_form,
                                self.ngram_type
                            )
                            replacement_item.setText(adapted_form)

            QMessageBox.information(self, "Автозаполнение",
                                    "✅ Формы автоматически заполнены с правильной адаптацией!")

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка автозаполнения: {e}")
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка автозаполнения: {str(e)}")

    def auto_fill_all_forms(self):
        """Автозаполнение форм для всех синонимов"""
        try:
            # Сохраняем текущий выбранный синоним
            current_synonym = self.current_synonym

            # Получаем все синонимы
            all_synonyms = self.syn_manager.get_synonyms(self.ngram_lemma, self.ngram_type)

            if not all_synonyms:
                QMessageBox.warning(self, "Внимание", "Нет синонимов для автозаполнения")
                return

            # Получаем экземпляр replacer
            replacer = None
            parent = self.parent_widget

            # Ищем родителя с replacer
            while parent and not hasattr(parent, 'replacer'):
                parent = parent.parent_widget if hasattr(parent, 'parent_widget') else parent.parent()

            if parent and hasattr(parent, 'replacer'):
                replacer = parent.replacer
            else:
                replacer = FastReplacer(self.syn_manager,
                                        parent.stop_word_manager if hasattr(parent, 'stop_word_manager') else None)

            # Прогресс-диалог
            progress = QProgressDialog("Автозаполнение всех форм...", "Отмена", 0, len(all_synonyms), self)
            progress.setWindowTitle("Автозаполнение")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()

            # Для каждого синонима
            for i, synonym in enumerate(all_synonyms):
                if synonym == self.ngram_lemma:
                    continue

                progress.setValue(i)
                progress.setLabelText(f"Обработка синонима: {synonym}")
                QApplication.processEvents()

                if progress.wasCanceled():
                    break

                # Устанавливаем текущий синоним в комбобоксе
                index = self.synonym_combo.findText(synonym)
                if index >= 0:
                    self.synonym_combo.setCurrentIndex(index)
                    self.current_synonym = synonym

                    # Даем время на обновление UI
                    QApplication.processEvents()

                    # Для каждой формы
                    for row in range(self.forms_table.rowCount()):
                        form_item = self.forms_table.item(row, 0)
                        if form_item:
                            original_form = form_item.text()

                            # Получаем адаптированную форму
                            if self.ngram_type == ReplacementType.UNIGRAM:
                                if hasattr(replacer, 'adapt_unigram_form') and replacer.morph:
                                    try:
                                        parsed = replacer.morph.parse(original_form)[0]
                                        syn_parsed = replacer.morph.parse(synonym)[0]
                                        grammemes = set(parsed.tag.grammemes)
                                        new_form = syn_parsed.inflect(grammemes)

                                        if new_form:
                                            adapted_form = new_form.word
                                        else:
                                            adapted_form = self.adapt_with_gender_number(parsed, syn_parsed)

                                        adapted_form = replacer.apply_case(original_form, adapted_form)
                                    except:
                                        adapted_form = replacer.apply_case(original_form, synonym)
                                else:
                                    adapted_form = replacer.apply_case(original_form, synonym)
                            else:
                                adapted_form = replacer.adapt_synonym_form(
                                    self.ngram_lemma,
                                    synonym,
                                    original_form,
                                    self.ngram_type
                                )

                            # Сохраняем форму
                            self.syn_manager.set_specific_form(original_form, synonym, adapted_form, self.ngram_type)

                            # Обновляем отображение в таблице если это текущий синоним
                            if synonym == self.current_synonym:
                                replacement_item = self.forms_table.item(row, 2)
                                if replacement_item:
                                    replacement_item.setText(adapted_form)

            progress.close()

            # Восстанавливаем оригинальный выбранный синоним
            if current_synonym:
                index = self.synonym_combo.findText(current_synonym)
                if index >= 0:
                    self.synonym_combo.setCurrentIndex(index)
                    self.current_synonym = current_synonym

            # Перезагружаем таблицу для отображения всех изменений
            self.load_forms_table()

            QMessageBox.information(self, "Успех",
                                    f"✅ Автозаполнение выполнено для {len(all_synonyms) - 1} синонимов!")

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка автозаполнения всех форм: {e}")
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка: {str(e)}")

    def adapt_with_gender_number(self, original_parsed, synonym_parsed):
        """Адаптация с сохранением рода и числа"""
        try:
            target_grammemes = set()

            # Сохраняем число
            if 'sing' in original_parsed.tag:
                target_grammemes.add('sing')
            elif 'plur' in original_parsed.tag:
                target_grammemes.add('plur')

            # Сохраняем род для единственного числа
            if 'sing' in target_grammemes:
                if 'masc' in original_parsed.tag:
                    target_grammemes.add('masc')
                elif 'femn' in original_parsed.tag:
                    target_grammemes.add('femn')
                elif 'neut' in original_parsed.tag:
                    target_grammemes.add('neut')

            # Сохраняем падеж
            cases = {'nomn', 'gent', 'datv', 'accs', 'ablt', 'loct'}
            for case in cases:
                if case in original_parsed.tag:
                    target_grammemes.add(case)
                    break

            if target_grammemes:
                new_form = synonym_parsed.inflect(target_grammemes)
                if new_form:
                    return new_form.word

        except Exception:
            pass

        # Возвращаем исходный синоним, если адаптация не удалась
        return synonym_parsed.word

    def save_forms(self):
        """Сохранение форм БЕЗ прогресса и записи на диск"""
        if not self.current_synonym:
            QMessageBox.warning(self, "Ошибка", "Выберите синоним")
            return

        try:
            saved_count = 0
            for row in range(self.forms_table.rowCount()):
                form_item = self.forms_table.item(row, 0)
                replacement_item = self.forms_table.item(row, 2)

                if form_item and replacement_item:
                    original_form = form_item.text()
                    replacement = replacement_item.text().strip()

                    if original_form and replacement:
                        self.syn_manager.set_specific_form(original_form, self.current_synonym,
                                                           replacement, self.ngram_type)
                        saved_count += 1

            QMessageBox.information(self, "Успех",
                                    f"✅ Сохранено {saved_count} форм в памяти.\n\n"
                                    "Чтобы записать на диск, нажмите кнопку '💾 Сохранить синонимы' в главном окне.")

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка сохранения форм: {e}")
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка: {str(e)}")


# ==================== ОБНОВЛЕННЫЙ ДИАЛОГ РЕДАКТИРОВАНИЯ СИНОНИМОВ ====================
class FastSynonymEditDialog(QDialog):
    def __init__(self, ngram: str, ngram_type: ReplacementType, syn_manager: FastSynonymManager,
                 forms_dict: Dict[str, int] = None, parent=None):
        super().__init__(parent)
        self.ngram = ngram  # Теперь это лемма
        self.ngram_type = ngram_type
        self.syn_manager = syn_manager
        self.forms_dict = forms_dict or {}
        self.parent_widget = parent

        self.setWindowTitle(f"Синонимы: {ngram}")
        self.setGeometry(300, 300, 900, 700)
        self.setup_ui()
        self.load_data()
        self.center_on_parent()  # Центрируем на родительском окне

    def center_on_parent(self):
        """Центрирует окно относительно родительского окна"""
        parent_widget = self.parent()
        if parent_widget:
            parent_geometry = parent_widget.frameGeometry()
            screen = QGuiApplication.screenAt(parent_geometry.center())
            if screen:
                screen_geometry = screen.availableGeometry()
                x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
                self.move(x, y)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Заголовок с примером формы
        example_form = list(self.forms_dict.keys())[0] if self.forms_dict else "нет примеров"
        title_text = f"✏️ Редактирование синонимов для:\nЛемма: {self.ngram}\nПример формы: '{example_form}'"
        title_label = QLabel(title_text)
        title_label.setStyleSheet("font-weight: bold; margin: 10px;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        cascade_btn = QPushButton("🔗 Каскадные синонимы")
        cascade_btn.clicked.connect(self.open_cascade_dialog)
        cascade_btn.setToolTip("Сгенерировать каскадные синонимы из составных слов")
        # Синонимы
        synonyms_label = QLabel("Синонимы (каждый с новой строки, в виде фраз):")
        layout.addWidget(synonyms_label)

        self.synonyms_edit = QTextEdit()
        self.synonyms_edit.setMaximumHeight(150)
        self.synonyms_edit.setPlaceholderText(
            "Введите синонимичные фразы...\nнапример: надежность и стабильность\nпрочность и долговечность")
        layout.addWidget(self.synonyms_edit)

        # Активные синонимы
        active_label = QLabel("Активные синонимы для замены:")
        layout.addWidget(active_label)

        # Кнопки для выделения всех/снятия всех
        active_buttons_layout = QHBoxLayout()
        select_all_btn = QPushButton("✅ Выбрать все")
        select_all_btn.clicked.connect(self.select_all_active)
        deselect_all_btn = QPushButton("❌ Снять все")
        deselect_all_btn.clicked.connect(self.deselect_all_active)
        active_buttons_layout.addWidget(select_all_btn)
        active_buttons_layout.addWidget(deselect_all_btn)
        active_buttons_layout.addStretch()
        layout.addLayout(active_buttons_layout)

        self.active_synonyms_list = QListWidget()
        layout.addWidget(self.active_synonyms_list)

        # Кнопки
        button_layout = QHBoxLayout()

        forms_btn = QPushButton("🔤 Редактировать конкретные формы")
        forms_btn.clicked.connect(self.open_forms_dialog)
        forms_btn.setToolTip("Настройка замен для конкретных форм употребления")
        cascade_btn = QPushButton("🔗 Каскадные синонимы")
        cascade_btn.clicked.connect(self.open_cascade_dialog)

        # ДОБАВЛЯЕМ НОВУЮ КНОПКУ УДАЛЕНИЯ
        delete_all_btn = QPushButton("🗑️ Удалить все синонимы")
        delete_all_btn.clicked.connect(self.delete_all_synonyms)
        delete_all_btn.setToolTip("Удалить все синонимы, кроме оригинальной фразы")
        delete_all_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #dc3545;
                        color: white;
                        font-weight: bold;
                        padding: 8px;
                    }
                    QPushButton:hover {
                        background-color: #c82333;
                    }
                """)

        save_btn = QPushButton("💾 Сохранить")
        save_btn.clicked.connect(self.save_all)

        cancel_btn = QPushButton("❌ Отмена")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(forms_btn)
        button_layout.addWidget(cascade_btn)
        button_layout.addWidget(delete_all_btn)  # Добавляем кнопку
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def delete_all_synonyms(self):
        """Удалить все синонимы, кроме оригинальной фразы"""
        reply = QMessageBox.warning(
            self,
            "Удаление всех синонимов",
            f"Удалить ВСЕ синонимы для:\n\n'{self.ngram}'\n\n"
            f"Останется только оригинальная фраза. Это действие нельзя отменить!",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Устанавливаем только оригинальную фразу
            self.syn_manager.add_synonyms(self.ngram, self.ngram_type, [self.ngram])

            # Очищаем активные синонимы
            self.syn_manager.set_active_synonyms(self.ngram, self.ngram_type, [])

            # Очищаем конкретные формы для этой n-граммы
            self.clean_specific_forms()

            # Обновляем UI
            self.load_data()

            QMessageBox.information(self, "Успех",
                                    f"✅ Все синонимы удалены!\n\n"
                                    f"Для '{self.ngram}' остался только оригинал.")

    def clean_specific_forms(self):
        """Очищает конкретные формы для этой n-граммы"""
        try:
            # Получаем все формы
            all_forms = self.syn_manager.get_all_forms()

            # Фильтруем: удаляем формы для этой n-граммы
            keys_to_delete = []
            for key in all_forms.keys():
                if key.startswith(f"{self.ngram_type.value}:{self.ngram.lower()}:"):
                    keys_to_delete.append(key)

            # Удаляем
            for key in keys_to_delete:
                del all_forms[key]

            # Сохраняем обратно
            self.syn_manager.set_all_forms(all_forms)

        except Exception as e:
            error_logger.log_error(f"Ошибка очистки конкретных форм: {e}")
    def open_cascade_dialog(self):
        """Открыть диалог каскадных синонимов"""
        # Проверяем, можно ли применять каскад
        info = self.syn_manager.get_ngram_components_info(self.ngram, self.ngram_type)

        # ДОБАВЛЯЕМ ПРОВЕРКУ НАЛИЧИЯ КЛЮЧЕЙ
        word_count = info.get('word_count', 1)

        if not info.get('can_cascade', False):
            if word_count == 1:
                msg = "Для униграмм используйте объединение синонимических множеств"
            else:
                msg = (f"Недостаточно синонимов для составных слов.\n"
                       f"Добавьте синонимы для слов в фразе, чтобы использовать каскад.")

            QMessageBox.information(self, "Информация", msg)
            return

        # Показываем информацию о том, что будет
        word_info = "\n".join([
            f"- '{comp['word']}' → {len(comp['synonyms'])} синонимов"
            for comp in info.get('components', [])
        ])

        reply = QMessageBox.question(
            self,
            "Каскадные синонимы",
            f"Создать каскадные синонимы для:\n\n{self.ngram}\n\n"
            f"Составные слова:\n{word_info}\n\n"
            f"Будут созданы все комбинации выбранных синонимов.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            dialog = CascadeSynonymsDialog(self.ngram, self.ngram_type, self.syn_manager, self)
            if dialog.exec() == QDialog.Accepted:
                # Обновляем отображение синонимов
                self.load_data()
    def select_all_active(self):
        """Выбрать все активные синонимы"""
        for i in range(self.active_synonyms_list.count()):
            item = self.active_synonyms_list.item(i)
            item.setCheckState(Qt.Checked)

    def deselect_all_active(self):
        """Снять все активные синонимы"""
        for i in range(self.active_synonyms_list.count()):
            item = self.active_synonyms_list.item(i)
            item.setCheckState(Qt.Unchecked)

    def load_data(self):
        """Быстрая загрузка данных - ТОЛЬКО обычные синонимы"""
        synonyms = self.syn_manager.get_synonyms(self.ngram, self.ngram_type)
        self.synonyms_edit.setPlainText("\n".join(synonyms))

        # Загружаем активные синонимы
        active_synonyms = self.syn_manager.get_active_synonyms(self.ngram, self.ngram_type)
        self.active_synonyms_list.clear()

        all_synonyms = self.syn_manager.get_synonyms(self.ngram, self.ngram_type)
        for synonym in all_synonyms:
            item = QListWidgetItem(synonym)
            item.setCheckState(Qt.Checked if synonym in active_synonyms else Qt.Unchecked)
            self.active_synonyms_list.addItem(item)

    def open_forms_dialog(self):
        """Открытие диалога редактирования конкретных форм"""
        if not self.forms_dict:
            QMessageBox.information(self, "Информация", "Нет данных о формах для редактирования")
            return

        dialog = FastFormEditDialog(self.ngram, self.ngram_type, self.syn_manager, self.forms_dict, self)
        dialog.exec()

    def save_all(self):
        """Сохранение всех изменений"""
        try:
            synonyms_text = self.synonyms_edit.toPlainText()
            new_synonyms = [s.strip() for s in synonyms_text.split("\n") if s.strip()]

            if new_synonyms:
                # ТОЛЬКО обычные синонимы, без отдельной логики для стоп-слов
                self.syn_manager.add_synonyms(self.ngram, self.ngram_type, new_synonyms)

                # Каскадное добавление синонимов для униграмм
                if self.ngram_type == ReplacementType.UNIGRAM:
                    # Фильтруем оригинал из списка синонимов для каскадного добавления
                    cascade_synonyms = [s for s in new_synonyms if s.lower() != self.ngram.lower()]
                    if cascade_synonyms:
                        self.syn_manager.cascade_synonyms(self.ngram, cascade_synonyms)

            # Активные синонимы
            active_synonyms = []
            for i in range(self.active_synonyms_list.count()):
                item = self.active_synonyms_list.item(i)
                if item.checkState() == Qt.Checked:
                    active_synonyms.append(item.text())

            self.syn_manager.set_active_synonyms(self.ngram, self.ngram_type, active_synonyms)

            # ЗАКРЫВАЕМ диалог БЕЗ сохранения на диск
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка: {str(e)}")


# ==================== ДИАЛОГ РЕДАКТИРОВАНИЯ СТОП-СЛОВ ====================
class StopWordEditDialog(QDialog):
    def __init__(self, stop_word_manager: StopWordManager, parent=None):
        super().__init__(parent)
        self.stop_word_manager = stop_word_manager
        self.setWindowTitle("Редактирование стоп-слов")
        self.setGeometry(400, 300, 800, 600)
        self.setup_ui()
        self.load_data()
        self.center_on_parent()  # Центрируем на родительском окне

    def center_on_parent(self):
        """Центрирует окно относительно родительского окна"""
        parent_widget = self.parent()
        if parent_widget:
            parent_geometry = parent_widget.frameGeometry()
            screen = QGuiApplication.screenAt(parent_geometry.center())
            if screen:
                screen_geometry = screen.availableGeometry()
                x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
                self.move(x, y)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Заголовок
        title_label = QLabel("🚫 Редактирование стоп-слов")
        title_label.setStyleSheet("font-weight: bold; font-size: 12pt; margin: 10px;")
        layout.addWidget(title_label)

        # Добавление нового стоп-слова
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("Новое стоп-слово:"))
        self.new_word_edit = QLineEdit()
        self.new_word_edit.setPlaceholderText("Введите стоп-слово...")
        add_layout.addWidget(self.new_word_edit)

        add_btn = QPushButton("➕ Добавить")
        add_btn.clicked.connect(self.add_stop_word)
        add_layout.addWidget(add_btn)

        layout.addLayout(add_layout)

        # Список стоп-слов
        self.stop_words_list = QListWidget()
        layout.addWidget(self.stop_words_list)

        # Кнопки управления
        buttons_layout = QHBoxLayout()

        remove_btn = QPushButton("🗑️ Удалить выбранное")
        remove_btn.clicked.connect(self.remove_stop_word)
        buttons_layout.addWidget(remove_btn)


        buttons_layout.addStretch()

        save_btn = QPushButton("💾 Сохранить")
        save_btn.clicked.connect(self.save_all)
        buttons_layout.addWidget(save_btn)

        cancel_btn = QPushButton("❌ Закрыть")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

    def load_data(self):
        """Загрузка данных"""
        self.stop_words_list.clear()
        stop_words = sorted(self.stop_word_manager.get_stop_words())
        for word in stop_words:
            item = QListWidgetItem(word)
            self.stop_words_list.addItem(item)

    def add_stop_word(self):
        """Добавление нового стоп-слова"""
        new_word = self.new_word_edit.text().strip()
        if new_word:
            self.stop_word_manager.add_stop_word(new_word)
            self.load_data()
            self.new_word_edit.clear()

    def remove_stop_word(self):
        """Удаление выбранного стоп-слова"""
        current_item = self.stop_words_list.currentItem()
        if current_item:
            word = current_item.text()
            self.stop_word_manager.remove_stop_word(word)
            self.load_data()



    def save_all(self):
        """Сохранение всех изменений"""
        self.stop_word_manager._save_stop_words()
        self.accept()


# ==================== ДИАЛОГ РЕДАКТИРОВАНИЯ СИНОНИМОВ СТОП-СЛОВ ====================



# ==================== УЛУЧШЕННЫЙ РЕДАКТОР ТЕКСТОВ ====================
class SideBySideTextEditDialog(QDialog):
    def __init__(self, original_texts: List[str], processed_texts: List[str], replacements: List[ReplacementInfo],
                 parent=None):
        super().__init__(parent)
        self.original_texts = original_texts
        self.processed_texts = processed_texts
        self.replacements = replacements
        self.current_index = -1
        self.parent_widget = parent

        self.setWindowTitle("Редактирование текстов")
        self.setGeometry(100, 100, 1600, 900)  # Увеличим ширину
        self.setup_ui()
        self.update_display()
        self.center_on_parent()

    def center_on_parent(self):
        """Центрирует окно относительно родительского окна"""
        parent_widget = self.parent()
        if parent_widget:
            parent_geometry = parent_widget.frameGeometry()
            screen = QGuiApplication.screenAt(parent_geometry.center())
            if screen:
                screen_geometry = screen.availableGeometry()
                x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
                self.move(x, y)
    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Панель навигации с превью
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)

        # Панель выбора текста с превью
        left_nav = QVBoxLayout()
        left_nav.addWidget(QLabel("📄 Выбор текста:"))

        # Список текстов с превью
        self.text_list_widget = QListWidget()
        self.text_list_widget.setMaximumWidth(400)
        self.text_list_widget.setAlternatingRowColors(False)

        # Добавить стили для лучшей видимости
        self.text_list_widget.setStyleSheet("""
            QListWidget {
                border: 2px solid #3498db;
                border-radius: 5px;
                padding: 5px;
                background-color: #f8f9fa;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eac2f2;
            }
            QListWidget::item:selected {
                background-color: #e07af5;
                color: white;
                font-weight: bold;
            }
            QListWidget::item:hover {
                background-color: #eec3f7;
            }
        """)

        self.populate_text_list()
        self.text_list_widget.currentRowChanged.connect(self.on_text_list_changed)
        left_nav.addWidget(self.text_list_widget)

        nav_layout.addLayout(left_nav)

        # Правая часть навигации с кнопками
        right_nav = QVBoxLayout()

        # Статистика текста
        self.text_stats_label = QLabel("")
        self.text_stats_label.setStyleSheet("font-size: 10pt; color: #666;")
        right_nav.addWidget(self.text_stats_label)

        # Навигационные кнопки
        nav_buttons = QHBoxLayout()

        self.prev_btn = QPushButton("◀ Предыдущий текст")
        self.prev_btn.clicked.connect(self.previous_text)

        self.next_btn = QPushButton("Следующий текст ▶")
        self.next_btn.clicked.connect(self.next_text)

        nav_buttons.addWidget(self.prev_btn)
        nav_buttons.addWidget(self.next_btn)

        right_nav.addLayout(nav_buttons)

        # Информация о заменах
        self.replacements_info = QLabel("")
        self.replacements_info.setStyleSheet("""
            QLabel {
                padding: 10px;
                background-color: #666;
                border: 1px solid #dee2e6;
                border-radius: 5px;
            }
        """)
        self.replacements_info.setWordWrap(True)
        right_nav.addWidget(self.replacements_info)

        right_nav.addStretch()
        nav_layout.addLayout(right_nav)

        layout.addWidget(nav_widget)

        # Splitter для одновременного отображения
        splitter = QSplitter(Qt.Horizontal)

        # Оригинал
        original_widget = QWidget()
        original_layout = QVBoxLayout(original_widget)
        original_header = QHBoxLayout()
        original_header.addWidget(QLabel("📄 ОРИГИНАЛ:"))

        # Добавляем статистику оригинального текста
        self.original_stats = QLabel("")
        self.original_stats.setStyleSheet("color: #666; font-size: 10pt;")
        original_header.addWidget(self.original_stats)
        original_header.addStretch()

        original_layout.addLayout(original_header)
        self.original_edit = QTextEdit()
        self.original_edit.setReadOnly(True)  # Сделаем только для чтения
        self.original_edit.setStyleSheet("""
            QTextEdit {
                background-color: #666;
                border: 1px solid #dee2e6;
            }
        """)
        original_layout.addWidget(self.original_edit)

        # Результат
        result_widget = QWidget()
        result_layout = QVBoxLayout(result_widget)
        result_header = QHBoxLayout()
        result_header.addWidget(QLabel("✨ РЕЗУЛЬТАТ (редактируемый):"))

        # Добавляем статистику результата
        self.result_stats = QLabel("")
        self.result_stats.setStyleSheet("color: #27ae60; font-size: 10pt; font-weight: bold;")
        result_header.addWidget(self.result_stats)
        result_header.addStretch()

        # Кнопка "Показать отличия"
        #self.show_diff_btn = QPushButton("🔍 Показать отличия")
        #self.show_diff_btn.clicked.connect(self.toggle_differences)
        #self.show_diff_btn.setCheckable(True)
        #result_header.addWidget(self.show_diff_btn)

        result_layout.addLayout(result_header)
        self.result_edit = QTextEdit()
        result_layout.addWidget(self.result_edit)

        splitter.addWidget(original_widget)
        splitter.addWidget(result_widget)
        splitter.setSizes([700, 700])  # Равные размеры

        layout.addWidget(splitter)

        # Кнопки
        button_layout = QHBoxLayout()

        # Кнопка "Применить ко всем"
        self.apply_to_all_btn = QPushButton("🔄 Применить изменения ко всем")
        self.apply_to_all_btn.clicked.connect(self.apply_to_all_texts)
        self.apply_to_all_btn.setToolTip("Применить текущие изменения ко всем остальным текстам")

        save_btn = QPushButton("💾 Сохранить все")
        save_btn.clicked.connect(self.save_all)

        close_btn = QPushButton("❌ Закрыть")
        close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.apply_to_all_btn)
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Устанавливаем фокус на первый текст
        self.text_list_widget.setCurrentRow(0)

    def populate_text_list(self):
        """Заполняет список текстов с превью"""
        self.text_list_widget.clear()

        for i, (original, processed) in enumerate(zip(self.original_texts, self.processed_texts)):
            # Создаем превью текста (первые 100 символов)
            preview = original[:100].replace('\n', ' ') + ("..." if len(original) > 100 else "")

            # Считаем количество замен в этом тексте
            text_replacements = len([r for r in self.replacements if r.text_index == i])

            # Создаем элемент списка
            item = QListWidgetItem()

            # Создаем виджет для элемента
            widget = QWidget()
            layout = QVBoxLayout(widget)

            # Заголовок с номером
            header = QLabel(f"📝 Текст {i + 1} (изменений: {text_replacements})")
            header.setStyleSheet("font-weight: bold; color: #2c3e50;")
            layout.addWidget(header)

            # Превью
            preview_label = QLabel(preview)
            preview_label.setStyleSheet("color: #666; font-size: 10pt;")
            preview_label.setWordWrap(True)
            layout.addWidget(preview_label)

            # Статистика
            stats = QLabel(f"📊 Символов: {len(original)} | Слов: {len(original.split())}")
            stats.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
            layout.addWidget(stats)

            widget.setLayout(layout)
            item.setSizeHint(widget.sizeHint())
            self.text_list_widget.addItem(item)
            self.text_list_widget.setItemWidget(item, widget)

    def on_text_list_changed(self, row):
        """Обработчик выбора текста из списка"""
        # Добавь эту проверку:
        if not hasattr(self, 'current_index'):
            self.current_index = 0
            return

        if row >= 0 and row < len(self.original_texts):
            # СОХРАНЯЕМ ТОЛЬКО ЕСЛИ ЭТО НЕ ПЕРВЫЙ ВЫЗОВ
            if self.current_index != -1:  # Если текущий индекс уже установлен
                self.save_current_text()

            self.current_index = row
            self.update_display()

    def update_display(self):
        """Обновляет отображение"""
        # Устанавливаем текст
        self.original_edit.setPlainText(self.original_texts[self.current_index])
        self.result_edit.setPlainText(self.processed_texts[self.current_index])

        # Обновляем статистику
        original_text = self.original_texts[self.current_index]
        processed_text = self.processed_texts[self.current_index]

        self.original_stats.setText(
            f"📊 Символов: {len(original_text)} | Слов: {len(original_text.split())} | "
            f"Строк: {original_text.count(chr(10)) + 1}"
        )

        self.result_stats.setText(
            f"📊 Символов: {len(processed_text)} | Слов: {len(processed_text.split())} | "
            f"Строк: {processed_text.count(chr(10)) + 1} | "
            f"🔧 Изменений: {len(self.get_current_replacements())}"
        )

        # Обновляем информацию о заменах
        replacements = self.get_current_replacements()
        if replacements:
            unique_changes = set()
            for r in replacements[:10]:  # Показываем первые 10 уникальных замен
                if r.original != r.new:
                    unique_changes.add(f"• '{r.original}' → '{r.new}'")

            info_text = f"🔄 <b>Выполнено замен:</b> {len(replacements)}\n"
            info_text += "\n".join(list(unique_changes)[:5])
            if len(unique_changes) > 5:
                info_text += f"\n... и ещё {len(unique_changes) - 5} замен"
        else:
            info_text = "🔄 <b>Замены:</b> нет изменений"

        self.replacements_info.setText(info_text)

        # Подсветка в результате
        doc = self.result_edit.document()
        highlighter = FastHighlighter(doc, self.get_current_replacements())

        # Подсвечиваем выбранный элемент в списке
        self.text_list_widget.setCurrentRow(self.current_index)
        self.update_navigation()

    def toggle_differences(self):
        """Переключение режима показа отличий"""
        if self.show_diff_btn.isChecked():
            self.highlight_differences()
        else:
            self.update_display()

    def highlight_differences(self):
        """Подсвечивает различия между оригиналом и результатом"""
        original = self.original_texts[self.current_index]
        processed = self.processed_texts[self.current_index]

        # Создаем текст с подсветкой отличий
        # Здесь можно реализовать алгоритм сравнения текстов
        # Например, использовать diff-match-patch или простую визуализацию

        # Временная заглушка - просто показываем текст
        self.result_edit.setPlainText(processed)

        # Можно добавить подсветку измененных участков
        cursor = self.result_edit.textCursor()
        format = QTextCharFormat()
        format.setBackground(QColor(255, 255, 200))  # Светло-желтый

        # Ищем изменения по позициям замен
        for replacement in self.get_current_replacements():
            if replacement.original != replacement.new:
                cursor.setPosition(replacement.start)
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor,
                                    len(replacement.new))
                cursor.mergeCharFormat(format)

    def apply_to_all_texts(self):
        """Применить текущие изменения ко всем текстам"""
        if not self.result_edit.toPlainText():
            return

        reply = QMessageBox.question(
            self,
            "Применить ко всем",
            "Вы уверены, что хотите применить изменения текущего текста ко всем остальным текстам?\n\n"
            "Это действие нельзя отменить!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            current_text = self.result_edit.toPlainText()
            for i in range(len(self.processed_texts)):
                if i != self.current_index:
                    self.processed_texts[i] = current_text

            QMessageBox.information(self, "Успех",
                                    f"✅ Изменения применены к {len(self.processed_texts) - 1} текстам")
            self.populate_text_list()

    def get_current_replacements(self) -> List[ReplacementInfo]:
        return [r for r in self.replacements if r.text_index == self.current_index]

    def previous_text(self):
        if self.current_index > 0:
            self.save_current_text()
            self.current_index -= 1
            self.update_display()

    def next_text(self):
        if self.current_index < len(self.processed_texts) - 1:
            self.save_current_text()
            self.current_index += 1
            self.update_display()

    def save_current_text(self):
        """Сохранить текущий отредактированный текст"""
        self.processed_texts[self.current_index] = self.result_edit.toPlainText()

    def update_navigation(self):
        """Обновить навигацию"""
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.original_texts) - 1)

        # Обновляем выделение в списке
        self.text_list_widget.blockSignals(True)
        self.text_list_widget.setCurrentRow(self.current_index)
        self.text_list_widget.blockSignals(False)

    def save_all(self):
        """Сохранить все изменения"""
        self.save_current_text()
        self.accept()

# ==================== ФУНКЦИЯ ДЛЯ ПАРАЛЛЕЛЬНОЙ ЛЕММАТИЗАЦИИ ====================
def process_chunk_parallel(chunk_words):
    """Обрабатывает чанк слов в отдельном процессе"""
    import pymorphy3
    morph = pymorphy3.MorphAnalyzer()
    results = []
    for word in chunk_words:
        try:
            parsed = morph.parse(word)[0]
            results.append((word, parsed.normal_form))
        except:
            results.append((word, word))
    return results
# ==================== ГЛАВНОЕ ОКНО ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎯 СинонимайZZZер")

        # Устанавливаем минимальный размер
        self.setMinimumSize(1200, 700)

        # Получаем экран и устанавливаем размер
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            self.resize(int(screen_geometry.width() * 0.9),
                        int(screen_geometry.height() * 0.85))
            self.center_window()

        # Центрируем окно на экране где запущено приложение
        self.center_window()

        # Устанавливаем максимальный размер окна

        self.original_texts = []
        self.processed_texts = []
        self.current_replacements = []
        self.unigram_data = {}
        self.bigram_data = {}
        self.trigram_data = {}
        self.ngram_data = {}
        self.prepositional_data = {}

        self.result_highlighter = None
        self.syn_manager = FastSynonymManager()
        self.stop_word_manager = StopWordManager(self.syn_manager)
        self.replacer = FastReplacer(self.syn_manager, self.stop_word_manager)
        self.session_manager = SessionManager()  # Менеджер сессии
        self.checkbox_states = {}  # Кеш состояний чекбоксов в памяти
        self.current_analyzer = None
        self.find_replace_dialog = None

        # Настраиваем полноэкранный режим

        self.setup_ui()
        self.setup_connections()
        self.setup_menu_bar()
        self.center_window()
        self.load_window_geometry()

        self.unigrams_filter_combo = None
        self.bigrams_filter_combo = None
        self.trigrams_filter_combo = None
        self.ngrams_filter_combo = None
        self.prepositional_filter_combo = None

        # Если нет сохранённой - максимизируем
        if not self.session_manager.data.get("window_geometry"):
            self.showMaximized()
    def replace_and_export_all(self):
        """Замена ВСЕХ выбранных n-грамм (униграммы, биграммы, триграммы, n-граммы, предложные) + автоэкспорт"""
        if not self.original_texts:
            QMessageBox.warning(self, "Ошибка", "Нет текстов для замены")
            return

        if not any([self.unigram_data, self.bigram_data, self.trigram_data, self.ngram_data, self.prepositional_data]):
            QMessageBox.warning(self, "Ошибка", "Сначала выполните анализ текстов")
            return

        # Собираем выбранные униграммы
        selected_unigrams = self.get_selected_ngrams(self.unigrams_table, self.unigram_data, ReplacementType.UNIGRAM)
        # Биграммы
        selected_bigrams = self.get_selected_ngrams(self.bigrams_table, self.bigram_data, ReplacementType.BIGRAM)
        # Триграммы
        selected_trigrams = self.get_selected_ngrams(self.trigrams_table, self.trigram_data, ReplacementType.TRIGRAM)
        # N-граммы
        selected_ngrams = self.get_selected_ngrams(self.ngrams_table, self.ngram_data, ReplacementType.NGRAM)
        # Предложные фразы
        selected_prepositional = self.get_selected_ngrams(self.prepositional_table, self.prepositional_data,
                                                          ReplacementType.PREPOSITIONAL)

        total_selected = (len(selected_unigrams) + len(selected_bigrams) + len(selected_trigrams) +
                          len(selected_ngrams) + len(selected_prepositional))

        if total_selected == 0:
            QMessageBox.warning(self, "Внимание",
                                "⚠️ Не выбрано ни одной n-граммы для замены!\n\n"
                                "Отметьте чекбоксы в таблицах 'Управление заменой'")
            return

        self.show_processing(f"🔄 Замена всех выбранных n-грамм ({total_selected} типов)...")
        QApplication.processEvents()

        try:
            # Выполняем замену ТОЧНО ТАК ЖЕ, как в apply_replacements
            processed_texts, replacements = self.replacer.replace_with_priority(
                self.original_texts,
                selected_unigrams,
                selected_bigrams,
                selected_trigrams,
                selected_ngrams,
                selected_prepositional
            )

            # Сразу экспорт
            from datetime import datetime
            t = datetime.now().strftime("%Y%m%d_%H%M%S")

            self.show_processing("💾 Сохранение Excel...")
            QApplication.processEvents()

            # Сохраняем Excel
            df = pd.DataFrame({
                'Оригинал': self.original_texts,
                'Результат': processed_texts
            })
            excel_file = f'replace_all_{t}.xlsx'
            df.to_excel(excel_file, index=False)

            # Сохраняем отчёт о заменах
            replacements_data = [{
                'текст': r.text_index,
                'было': r.original,
                'стало': r.new,
                'тип': r.type.value,
                'лемма': r.lemma
            } for r in replacements]

            json_file = f'replacements_all_{t}.json'
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(replacements_data, f, ensure_ascii=False, indent=2)

            self.hide_processing(f"✅ Готово! {len(replacements)} замен, {total_selected} выбранных n-грамм")
            QMessageBox.information(self, "Успех",
                                    f"✅ Замен выполнено: {len(replacements)}\n"
                                    f"✅ Выбрано n-грамм: {total_selected}\n\n"
                                    f"📁 Excel: {excel_file}\n"
                                    f"📄 Отчёт: {json_file}")

        except Exception as e:
            self.hide_processing("❌ Ошибка")
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка замены: {str(e)}")
    def populate_unigrams_table_fast(self):
        """Быстрое заполнение таблицы с ограничением по памяти"""
        try:
            self.unigrams_table.setUpdatesEnabled(False)
            self.unigrams_table.blockSignals(True)

            # Ограничиваем количество отображаемых строк (топ 10000)
            MAX_ROWS = 10000
            sorted_data = sorted(self.unigram_data.items(), key=lambda x: x[1]['count'], reverse=True)[:MAX_ROWS]

            self.unigrams_table.setRowCount(len(sorted_data))

            for row, (lemma, data) in enumerate(sorted_data):
                # Чекбокс
                replace_item = QTableWidgetItem()
                replace_item.setCheckState(Qt.Checked)
                self.unigrams_table.setItem(row, 0, replace_item)

                # Лемма
                self.unigrams_table.setItem(row, 1, QTableWidgetItem(lemma))

                # Количество
                count_item = QTableWidgetItem(str(data['count']))
                count_item.setTextAlignment(Qt.AlignCenter)
                self.unigrams_table.setItem(row, 2, count_item)

                # Формы (первые 3)
                forms_preview = list(data['forms'].keys())[:3]
                self.unigrams_table.setItem(row, 3, QTableWidgetItem(", ".join(forms_preview)))

                # Синонимы
                synonyms = self.syn_manager.get_active_synonyms(lemma, ReplacementType.UNIGRAM)
                syn_text = ", ".join([s for s in synonyms if s != lemma][:3]) if len(synonyms) > 1 else "нет"
                self.unigrams_table.setItem(row, 4, QTableWidgetItem(syn_text))

                # Стоп-слово
                stop_item = QTableWidgetItem()
                if data.get('is_stopword', False):
                    stop_item.setText("🚫")
                self.unigrams_table.setItem(row, 5, stop_item)

            self.unigrams_table.blockSignals(False)
            self.unigrams_table.setUpdatesEnabled(True)

            # Показываем сообщение, если не все слова отображены
            if len(self.unigram_data) > MAX_ROWS:
                self.status_label.setText(f"⚠️ Показаны только топ {MAX_ROWS} из {len(self.unigram_data)} слов")

        except Exception as e:
            self.unigrams_table.blockSignals(False)
            self.unigrams_table.setUpdatesEnabled(True)
            print(f"Ошибка: {e}")
    def analyze_streaming(self):
        """Потоковый анализ ВСЕХ типов с лемматизацией и записью на диск"""

        if not self.original_texts:
            QMessageBox.warning(self, "Внимание", "⚠️ Нет текстов для анализа")
            return

        self.show_processing("🚀 ПОТОКОВЫЙ АНАЛИЗ ВСЕХ ТИПОВ (леммы, экономия памяти)...")
        QApplication.processEvents()

        try:
            from collections import defaultdict
            import re
            import gc
            import pymorphy3

            MIN_COUNT = 1000
            morph = pymorphy3.MorphAnalyzer()

            # ВРЕМЕННЫЕ ФАЙЛЫ
            temp_unigrams = "temp_unigrams_lemmas.txt"
            temp_bigrams = "temp_bigrams_lemmas.txt"
            temp_trigrams = "temp_trigrams_lemmas.txt"

            self.show_processing("Первый проход - сбор лемм...")
            QApplication.processEvents()

            # ПЕРВЫЙ ПРОХОД - пишем леммы во временные файлы
            with open(temp_unigrams, 'w', encoding='utf-8') as f_uni, \
                    open(temp_bigrams, 'w', encoding='utf-8') as f_bi, \
                    open(temp_trigrams, 'w', encoding='utf-8') as f_tri:

                for idx, text in enumerate(self.original_texts):
                    if idx % 1000 == 0:
                        self.show_processing(f"Проход 1: {idx+1}/{len(self.original_texts)}...")
                        QApplication.processEvents()

                    # Находим слова и их леммы
                    words = re.findall(r'\b[а-яА-ЯёЁ]{3,}\b', text.lower())
                    lemmas = []
                    for word in words:
                        try:
                            lemma = morph.parse(word)[0].normal_form
                            lemmas.append(lemma)
                            f_uni.write(lemma + "\n")
                        except:
                            lemmas.append(word)
                            f_uni.write(word + "\n")

                    # Биграммы (по леммам)
                    for i in range(len(lemmas) - 1):
                        bigram_lemma = f"{lemmas[i]}, {lemmas[i+1]}"
                        f_bi.write(bigram_lemma + "\n")

                    # Триграммы (по леммам)
                    for i in range(len(lemmas) - 2):
                        trigram_lemma = f"{lemmas[i]}, {lemmas[i+1]}, {lemmas[i+2]}"
                        f_tri.write(trigram_lemma + "\n")

                    # Очищаем память каждые 1000 текстов
                    if idx % 1000 == 0:
                        gc.collect()

            self.show_processing("Подсчёт частоты лемм...")
            QApplication.processEvents()

            # Считаем частоту
            unigram_counts = defaultdict(int)
            bigram_counts = defaultdict(int)
            trigram_counts = defaultdict(int)

            with open(temp_unigrams, 'r', encoding='utf-8') as f:
                for line in f:
                    unigram_counts[line.strip()] += 1

            with open(temp_bigrams, 'r', encoding='utf-8') as f:
                for line in f:
                    bigram_counts[line.strip()] += 1

            with open(temp_trigrams, 'r', encoding='utf-8') as f:
                for line in f:
                    trigram_counts[line.strip()] += 1

            # Оставляем только частые
            freq_unigrams = {lemma: c for lemma, c in unigram_counts.items() if c >= MIN_COUNT}
            freq_bigrams = {bigram: c for bigram, c in bigram_counts.items() if c >= MIN_COUNT}
            freq_trigrams = {trigram: c for trigram, c in trigram_counts.items() if c >= MIN_COUNT}

            # Очищаем память
            unigram_counts.clear()
            bigram_counts.clear()
            trigram_counts.clear()
            gc.collect()

            self.show_processing(f"Найдено: униграмм={len(freq_unigrams)}, биграмм={len(freq_bigrams)}, триграмм={len(freq_trigrams)}")
            QApplication.processEvents()

            # ВТОРОЙ ПРОХОД - собираем данные для отображения
            self.unigram_data = {}
            self.bigram_data = {}
            self.trigram_data = {}

            uni_set = set(freq_unigrams.keys())
            bi_set = set(freq_bigrams.keys())
            tri_set = set(freq_trigrams.keys())

            self.show_processing("Второй проход - сбор данных...")
            QApplication.processEvents()

            for idx, text in enumerate(self.original_texts):
                if idx % 1000 == 0:
                    self.show_processing(f"Проход 2: {idx+1}/{len(self.original_texts)}...")
                    QApplication.processEvents()
                    gc.collect()

                words = re.findall(r'\b[а-яА-ЯёЁ]{3,}\b', text.lower())
                word_positions = list(re.finditer(r'\b[а-яА-ЯёЁ]{3,}\b', text, re.IGNORECASE))

                # Получаем леммы
                lemmas = []
                for word in words:
                    try:
                        lemmas.append(morph.parse(word)[0].normal_form)
                    except:
                        lemmas.append(word)

                # Униграммы
                for i, (lemma, match) in enumerate(zip(lemmas, word_positions)):
                    if lemma in uni_set:
                        if lemma not in self.unigram_data:
                            self.unigram_data[lemma] = {
                                'count': 0, 'forms': defaultdict(int), 'positions': [],
                                'replace': True, 'is_stopword': self.stop_word_manager.is_stop_word(lemma)
                            }
                        self.unigram_data[lemma]['count'] += 1
                        self.unigram_data[lemma]['forms'][match.group()] += 1
                        self.unigram_data[lemma]['positions'].append((idx, match.start(), match.end()))

                # Биграммы
                for i in range(len(lemmas) - 1):
                    bigram_key = f"{lemmas[i]}, {lemmas[i+1]}"
                    if bigram_key in bi_set:
                        if bigram_key not in self.bigram_data:
                            self.bigram_data[bigram_key] = {'count': 0, 'forms': defaultdict(int), 'positions': [], 'replace': True}
                        self.bigram_data[bigram_key]['count'] += 1
                        form = f"{word_positions[i].group()} {word_positions[i+1].group()}"
                        self.bigram_data[bigram_key]['forms'][form] += 1
                        self.bigram_data[bigram_key]['positions'].append((idx, word_positions[i].start(), word_positions[i+1].end()))

                # Триграммы
                for i in range(len(lemmas) - 2):
                    trigram_key = f"{lemmas[i]}, {lemmas[i+1]}, {lemmas[i+2]}"
                    if trigram_key in tri_set:
                        if trigram_key not in self.trigram_data:
                            self.trigram_data[trigram_key] = {'count': 0, 'forms': defaultdict(int), 'positions': [], 'replace': True}
                        self.trigram_data[trigram_key]['count'] += 1
                        form = f"{word_positions[i].group()} {word_positions[i+1].group()} {word_positions[i+2].group()}"
                        self.trigram_data[trigram_key]['forms'][form] += 1
                        self.trigram_data[trigram_key]['positions'].append((idx, word_positions[i].start(), word_positions[i+2].end()))

            # Очищаем временные файлы
            for f in [temp_unigrams, temp_bigrams, temp_trigrams]:
                if os.path.exists(f):
                    os.remove(f)

            # Очищаем остальные данные
            self.ngram_data = {}
            self.prepositional_data = {}

            # Заполняем таблицы
            self.populate_unigrams_table_fast()
            self.populate_bigrams_table()
            self.populate_trigrams_table()

            self.hide_processing(f"✅ Анализ завершен!")
            QMessageBox.information(self, "Успех",
                                    f"✅ Анализ завершен!\n"
                                    f"📝 Униграмм (лемм): {len(self.unigram_data)}\n"
                                    f"🔤 Биграмм (лемм): {len(self.bigram_data)}\n"
                                    f"📚 Триграмм (лемм): {len(self.trigram_data)}")

        except Exception as e:
            self.hide_processing("❌ Ошибка")
            QMessageBox.critical(self, "Ошибка", str(e))
    def replace_and_export_glued(self):
        """Быстрая замена и автоэкспорт БЕЗ отображения"""

        if not self.original_texts:
            QMessageBox.warning(self, "Ошибка", "Нет текстов")
            return

        if not self.unigram_data:
            QMessageBox.warning(self, "Ошибка", "Сначала выполните анализ")
            return

        # Собираем выбранные слова
        selected = {}
        for row in range(self.unigrams_table.rowCount()):
            item = self.unigrams_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                lemma = self.unigrams_table.item(row, 1).text()
                if lemma in self.unigram_data:
                    selected[lemma] = self.unigram_data[lemma].copy()
                    selected[lemma]['replace'] = True

        if not selected:
            QMessageBox.warning(self, "Ошибка", "Не выбраны слова для замены")
            return

        self.show_processing(f"🔄 Замена в {len(self.original_texts)} текстах...")
        QApplication.processEvents()

        try:
            # Замены (только униграммы, так как другие типы не анализировали)
            self.processed_texts, replacements = self.replacer.replace_with_priority(
                self.original_texts, selected, {}, {}, {}, {}
            )

            # Сразу экспорт
            from datetime import datetime
            t = datetime.now().strftime("%Y%m%d_%H%M%S")

            self.show_processing("💾 Сохранение Excel...")
            QApplication.processEvents()

            # Сохраняем Excel
            df = pd.DataFrame({
                'Оригинал': self.original_texts,
                'Результат': self.processed_texts
            })
            df.to_excel(f'result_glued_{t}.xlsx', index=False)

            # Сохраняем замены
            replacements_data = [{
                'текст': r.text_index,
                'было': r.original,
                'стало': r.new,
                'тип': r.type.value,
                'лемма': r.lemma
            } for r in replacements]

            with open(f'replacements_glued_{t}.json', 'w', encoding='utf-8') as f:
                json.dump(replacements_data, f, ensure_ascii=False, indent=2)

            self.hide_processing(f"✅ Готово! {len(self.processed_texts)} текстов, {len(replacements)} замен")
            QMessageBox.information(self, "Успех",
                                    f"✅ Обработано {len(self.processed_texts)} текстов\n"
                                    f"✅ Выполнено {len(replacements)} замен\n"
                                    f"✅ Файл: result_glued_{t}.xlsx")

        except Exception as e:
            self.hide_processing("❌ Ошибка")
            QMessageBox.critical(self, "Ошибка", str(e))
    def analyze_all_fast_parallel(self):
        """Параллельный анализ всех типов n-грамм с лемматизацией (только частые >1000)"""
        import re
        if not self.original_texts and self.original_text_edit.toPlainText().strip():
            raw_text = self.original_text_edit.toPlainText().strip()
            self.original_texts = [text.strip() for text in re.split(r'\n\s*\n', raw_text) if text.strip()]
            if len(self.original_texts) == 1:
                self.original_texts = [text.strip() for text in raw_text.split('\n') if text.strip()]

        if not self.original_texts:
            QMessageBox.warning(self, "Внимание", "⚠️ Нет текстов для анализа")
            return

        self.show_processing("🚀 ПАРАЛЛЕЛЬНЫЙ АНАЛИЗ ВСЕХ ТИПОВ (лемматизация)...")
        QApplication.processEvents()

        try:
            from collections import defaultdict
            import re
            from multiprocessing import Pool, cpu_count

            MIN_COUNT = 1000
            SEPARATOR = "\n★★★★★SPLIT★★★★★\n"

            self.show_processing("Склеивание текстов...")
            QApplication.processEvents()

            glued_text = SEPARATOR.join(self.original_texts)

            # Находим позиции разделителей
            separator_positions = []
            pos = 0
            while True:
                pos = glued_text.find(SEPARATOR, pos)
                if pos == -1:
                    break
                separator_positions.append(pos)
                pos += len(SEPARATOR)

            # Находим все слова и их позиции
            word_matches = list(re.finditer(r'\b[а-яА-ЯёЁ]{3,}\b', glued_text))
            words = [m.group().lower() for m in word_matches]

            self.show_processing(f"Параллельная лемматизация {len(words)} слов на {cpu_count()} ядрах...")
            QApplication.processEvents()

            # Разбиваем на чанки
            chunk_size = max(1, len(words) // cpu_count())
            chunks = [words[i:i+chunk_size] for i in range(0, len(words), chunk_size)]

            # Параллельная обработка
            with Pool(cpu_count()) as pool:
                chunk_results = pool.map(process_chunk_parallel, chunks)

            # Собираем результаты
            word_to_lemma = {}
            for chunk in chunk_results:
                for word, lemma in chunk:
                    word_to_lemma[word] = lemma

            # Считаем частоту лемм
            lemma_counts = defaultdict(int)
            for word in words:
                lemma = word_to_lemma[word]
                lemma_counts[lemma] += 1

            # Оставляем только частые
            freq_lemmas = {lemma: count for lemma, count in lemma_counts.items() if count >= MIN_COUNT}

            self.show_processing(f"Найдено {len(freq_lemmas)} частых лемм, собираем данные...")
            QApplication.processEvents()

            # Собираем униграммы
            self.unigram_data = {}
            self.bigram_data = {}
            self.trigram_data = {}
            self.ngram_data = {}
            self.prepositional_data = {}

            for i, (word, match) in enumerate(zip(words, word_matches)):
                if i % 100000 == 0 and i > 0:
                    self.show_processing(f"Сбор данных {i}/{len(words)}...")
                    QApplication.processEvents()

                lemma = word_to_lemma[word]

                if lemma in freq_lemmas:
                    if lemma not in self.unigram_data:
                        self.unigram_data[lemma] = {
                            'count': 0, 'forms': defaultdict(int), 'positions': [],
                            'replace': True, 'is_stopword': self.stop_word_manager.is_stop_word(lemma)
                        }
                    self.unigram_data[lemma]['count'] += 1
                    self.unigram_data[lemma]['forms'][match.group()] += 1

                    # Находим индекс текста
                    text_index = 0
                    for sep_pos in separator_positions:
                        if match.start() > sep_pos:
                            text_index += 1
                        else:
                            break
                    self.unigram_data[lemma]['positions'].append((text_index, match.start(), match.end()))

            self.show_processing("Сбор биграмм и триграмм...")
            QApplication.processEvents()

            # Собираем биграммы
            for i in range(len(words) - 1):
                lemma1 = word_to_lemma[words[i]]
                lemma2 = word_to_lemma[words[i+1]]

                if lemma1 in freq_lemmas and lemma2 in freq_lemmas:
                    bigram_key = f"{lemma1}, {lemma2}"
                    if bigram_key not in self.bigram_data:
                        self.bigram_data[bigram_key] = {'count': 0, 'forms': defaultdict(int), 'positions': [], 'replace': True}
                    self.bigram_data[bigram_key]['count'] += 1

                    form = f"{word_matches[i].group()} {word_matches[i+1].group()}"
                    self.bigram_data[bigram_key]['forms'][form] += 1

                    text_index = 0
                    for sep_pos in separator_positions:
                        if word_matches[i].start() > sep_pos:
                            text_index += 1
                        else:
                            break
                    self.bigram_data[bigram_key]['positions'].append((text_index, word_matches[i].start(), word_matches[i+1].end()))

            # Собираем триграммы
            for i in range(len(words) - 2):
                lemma1 = word_to_lemma[words[i]]
                lemma2 = word_to_lemma[words[i+1]]
                lemma3 = word_to_lemma[words[i+2]]

                if lemma1 in freq_lemmas and lemma2 in freq_lemmas and lemma3 in freq_lemmas:
                    trigram_key = f"{lemma1}, {lemma2}, {lemma3}"
                    if trigram_key not in self.trigram_data:
                        self.trigram_data[trigram_key] = {'count': 0, 'forms': defaultdict(int), 'positions': [], 'replace': True}
                    self.trigram_data[trigram_key]['count'] += 1

                    form = f"{word_matches[i].group()} {word_matches[i+1].group()} {word_matches[i+2].group()}"
                    self.trigram_data[trigram_key]['forms'][form] += 1

                    text_index = 0
                    for sep_pos in separator_positions:
                        if word_matches[i].start() > sep_pos:
                            text_index += 1
                        else:
                            break
                    self.trigram_data[trigram_key]['positions'].append((text_index, word_matches[i].start(), word_matches[i+2].end()))

            # Заполняем таблицы
            self.populate_unigrams_table_fast()
            self.populate_bigrams_table()
            self.populate_trigrams_table()

            self.hide_processing(f"✅ Анализ завершен!")
            QMessageBox.information(self, "Успех",
                                    f"✅ Анализ завершен!\n"
                                    f"📝 Униграмм: {len(self.unigram_data)}\n"
                                    f"🔤 Биграмм: {len(self.bigram_data)}\n"
                                    f"📚 Триграмм: {len(self.trigram_data)}")

        except Exception as e:
            self.hide_processing("❌ Ошибка")
            QMessageBox.critical(self, "Ошибка", str(e))
    def analyze_fast_glued(self):
        """Супер-быстрый анализ через склеивание всех текстов"""
        import re
        if not self.original_texts and self.original_text_edit.toPlainText().strip():
            raw_text = self.original_text_edit.toPlainText().strip()
            self.original_texts = [text.strip() for text in re.split(r'\n\s*\n', raw_text) if text.strip()]
            if len(self.original_texts) == 1:
                self.original_texts = [text.strip() for text in raw_text.split('\n') if text.strip()]

        if not self.original_texts:
            QMessageBox.warning(self, "Внимание", "⚠️ Нет текстов для анализа")
            return

        self.show_processing("🚀 СУПЕР-БЫСТРЫЙ АНАЛИЗ (склеивание текстов)...")
        QApplication.processEvents()

        try:
            from collections import defaultdict
            import re

            # УНИКАЛЬНЫЙ РАЗДЕЛИТЕЛЬ (которого точно нет в текстах)
            SEPARATOR = "\n★★★★★SPLIT★★★★★\n"

            self.show_processing("Склеивание текстов...")
            QApplication.processEvents()

            # Склеиваем все тексты
            glued_text = SEPARATOR.join(self.original_texts)

            # Сохраняем позиции разделителей для обратной разбивки
            separator_positions = []
            pos = 0
            while True:
                pos = glued_text.find(SEPARATOR, pos)
                if pos == -1:
                    break
                separator_positions.append(pos)
                pos += len(SEPARATOR)

            self.show_processing("Лемматизация ОДНОГО текста (это быстро)...")
            QApplication.processEvents()

            # Анализируем как один текст
            import pymorphy3
            morph = pymorphy3.MorphAnalyzer()

            # Находим все слова в склеенном тексте
            words = re.findall(r'\b[а-яА-ЯёЁ]{3,}\b', glued_text.lower())

            self.show_processing(f"Лемматизация {len(words)} слов...")
            QApplication.processEvents()

            # Считаем частоту лемм
            lemma_counts = defaultdict(int)
            lemma_to_words = defaultdict(list)

            for i, word in enumerate(words):
                if i % 100000 == 0 and i > 0:
                    self.show_processing(f"Лемматизация {i}/{len(words)}...")
                    QApplication.processEvents()

                parsed = morph.parse(word)[0]
                lemma = parsed.normal_form
                lemma_counts[lemma] += 1
                lemma_to_words[lemma].append(word)

            # Оставляем только частые леммы
            MIN_COUNT = 1000
            freq_lemmas = {lemma: count for lemma, count in lemma_counts.items() if count >= MIN_COUNT}

            self.show_processing(f"Найдено {len(freq_lemmas)} частых лемм, собираем данные...")
            QApplication.processEvents()

            # Собираем данные для униграмм
            self.unigram_data = {}

            # Второй проход по склеенному тексту
            word_matches = list(re.finditer(r'\b[а-яА-ЯёЁ]{3,}\b', glued_text))

            for i, (word, match) in enumerate(zip(words, word_matches)):
                if i % 100000 == 0 and i > 0:
                    self.show_processing(f"Сбор данных {i}/{len(words)}...")
                    QApplication.processEvents()

                # Получаем лемму (можно из кеша, но для простоты заново)
                lemma = morph.parse(word)[0].normal_form

                if lemma in freq_lemmas:
                    if lemma not in self.unigram_data:
                        self.unigram_data[lemma] = {
                            'count': 0, 'forms': defaultdict(int), 'positions': [],
                            'replace': True, 'is_stopword': self.stop_word_manager.is_stop_word(lemma)
                        }
                    self.unigram_data[lemma]['count'] += 1
                    self.unigram_data[lemma]['forms'][match.group()] += 1

                    # Находим индекс текста по позиции разделителя
                    text_index = 0
                    for sep_pos in separator_positions:
                        if match.start() > sep_pos:
                            text_index += 1
                        else:
                            break

                    self.unigram_data[lemma]['positions'].append((text_index, match.start(), match.end()))

            # Очищаем остальные данные (если не нужны)
            self.bigram_data = {}
            self.trigram_data = {}
            self.ngram_data = {}
            self.prepositional_data = {}

            # Заполняем таблицу
            self.populate_unigrams_table_fast()

            self.hide_processing(f"✅ Готово! {len(self.unigram_data)} частых лемм")
            QMessageBox.information(self, "Успех",
                                    f"✅ Анализ завершен!\n"
                                    f"📝 Найдено {len(self.unigram_data)} лемм с частотой >{MIN_COUNT}\n"
                                    f"🔤 Всего слов в склеенном тексте: {len(words)}\n"
                                    f"📄 Текстов: {len(self.original_texts)}")

        except Exception as e:
            self.hide_processing("❌ Ошибка")
            QMessageBox.critical(self, "Ошибка", str(e))
    def center_window(self):
        """Центрирование окна на экране с активным окном"""
        # Получаем экран, на котором находится указатель мыши
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos)
        if not screen:
            # Если не удалось определить экран, используем основной
            screen = QGuiApplication.primaryScreen()

        screen_geometry = screen.availableGeometry()

        # Вычисляем позицию для центрирования
        x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
        y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2

        # Устанавливаем положение окна
        self.move(x, y)

    def setup_menu_bar(self):
        """Настройка меню"""
        menubar = self.menuBar()

        # Меню Файл
        file_menu = menubar.addMenu("Файл")

        open_action = QAction("📂 Открыть Excel", self)
        open_action.triggered.connect(self.load_excel)
        file_menu.addAction(open_action)

        export_action = QAction("💾 Экспорт результатов", self)
        export_action.triggered.connect(self.export_results)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("🚪 Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню Сервис
        service_menu = menubar.addMenu("Сервис")

        # ДОБАВЛЯЕМ НОВЫЕ ПУНКТЫ:
        unify_action = QAction("🔄 Объединить синонимические множества", self)
        unify_action.triggered.connect(self.unify_synonym_sets)
        service_menu.addAction(unify_action)

        cascade_action = QAction("🔗 Каскадные синонимы для всех n-грамм", self)
        cascade_action.triggered.connect(self.cascade_all_ngrams)
        service_menu.addAction(cascade_action)

        service_menu.addSeparator()

        show_logs_action = QAction("📋 Показать логи ошибок", self)
        show_logs_action.triggered.connect(lambda: error_logger.show_error_log())
        service_menu.addAction(show_logs_action)

        # Меню Помощь
        help_menu = menubar.addMenu("Помощь")

        about_action = QAction("ℹ️ О программе", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def unify_synonym_sets(self):
        """Объединить синонимические множества"""
        reply = QMessageBox.question(
            self,
            "Объединение синонимов",
            "Объединить все синонимические множества?\n\n"
            "Это приведёт все синонимы в согласованное состояние, "
            "где слова из одной синонимической группы будут иметь одинаковые наборы синонимов.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            self.show_processing("🔄 Объединение синонимических множеств...")

            if self.syn_manager.unify_synonym_sets():
                self.hide_processing("✅ Синонимические множества объединены!")
                QMessageBox.information(self, "Успех",
                                        "✅ Все синонимические множества успешно объединены.\n"
                                        "Теперь каскадные синонимы будут использовать полные группы.")
            else:
                self.hide_processing("❌ Ошибка объединения")
                QMessageBox.warning(self, "Ошибка", "Не удалось объединить синонимические множества")
    def export_analysis_data(self):
        """Экспорт данных анализа (униграммы, биграммы, триграммы, n-граммы)"""
        if not any([self.unigram_data, self.bigram_data, self.trigram_data,
                    self.ngram_data, self.prepositional_data]):
            QMessageBox.warning(self, "Внимание", "⚠️ Нет данных для экспорта. Сначала выполните анализ.")
            return

        # Диалог выбора типа экспорта
        export_type, ok = QInputDialog.getItem(
            self,
            "Экспорт данных анализа",
            "Выберите тип данных для экспорта:",
            ["Все данные", "Униграммы", "Биграммы", "Триграммы", "N-граммы", "Фразы с предлогами"],
            0,
            False
        )

        if not ok:
            return

        # Диалог выбора формата
        file_format, ok = QInputDialog.getItem(
            self,
            "Выберите формат файла",
            "Формат экспорта:",
            ["Excel (.xlsx)", "CSV (.csv)", "JSON (.json)"],
            0,
            False
        )

        if not ok:
            return

        # Выбор файла для сохранения
        if file_format == "Excel (.xlsx)":
            file_filter = "Excel files (*.xlsx)"
            default_ext = ".xlsx"
        elif file_format == "CSV (.csv)":
            file_filter = "CSV files (*.csv)"
            default_ext = ".csv"
        else:
            file_filter = "JSON files (*.json)"
            default_ext = ".json"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить данные анализа",
            f"analysis_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}{default_ext}",
            file_filter
        )

        if not file_path:
            return

        try:
            self.show_processing("💾 Экспорт данных анализа...")

            if export_type == "Все данные":
                self._export_all_data(file_path, file_format)
            elif export_type == "Униграммы":
                self._export_unigrams(file_path, file_format)
            elif export_type == "Биграммы":
                self._export_ngrams(self.bigram_data, "Биграммы", file_path, file_format)
            elif export_type == "Триграммы":
                self._export_ngrams(self.trigram_data, "Триграммы", file_path, file_format)
            elif export_type == "N-граммы":
                self._export_ngrams(self.ngram_data, "N-граммы", file_path, file_format)
            elif export_type == "Фразы с предлогами":
                self._export_ngrams(self.prepositional_data, "Фразы_с_предлогами", file_path, file_format)

            self.hide_processing("✅ Экспорт завершен")
            QMessageBox.information(self, "Успех", f"✅ Данные успешно экспортированы в:\n{file_path}")

        except Exception as e:
            self.hide_processing("❌ Ошибка экспорта")
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка при экспорте:\n{str(e)}")

    def _export_all_data(self, file_path: str, file_format: str):
        """Экспорт всех данных в один файл"""
        data = {
            "униграммы": self._prepare_unigrams_data(),
            "биграммы": self._prepare_ngrams_data(self.bigram_data),
            "триграммы": self._prepare_ngrams_data(self.trigram_data),
            "n-граммы": self._prepare_ngrams_data(self.ngram_data),
            "фразы_с_предлогами": self._prepare_ngrams_data(self.prepositional_data),
            "статистика": {
                "всего_текстов": len(self.original_texts),
                "всего_униграмм": len(self.unigram_data),
                "всего_биграмм": len(self.bigram_data),
                "всего_триграмм": len(self.trigram_data),
                "всего_n_грамм": len(self.ngram_data),
                "всего_фраз_с_предлогами": len(self.prepositional_data),
                "дата_экспорта": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }

        if file_format == "Excel (.xlsx)":
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # Сохраняем каждый тип данных на отдельный лист
                pd.DataFrame(data["униграммы"]).to_excel(writer, sheet_name="Униграммы", index=False)
                pd.DataFrame(data["биграммы"]).to_excel(writer, sheet_name="Биграммы", index=False)
                pd.DataFrame(data["триграммы"]).to_excel(writer, sheet_name="Триграммы", index=False)
                pd.DataFrame(data["n-граммы"]).to_excel(writer, sheet_name="N-граммы", index=False)
                pd.DataFrame(data["фразы_с_предлогами"]).to_excel(writer, sheet_name="Фразы_с_предлогами", index=False)
                pd.DataFrame([data["статистика"]]).to_excel(writer, sheet_name="Статистика", index=False)

        elif file_format == "CSV (.csv)":
            # Для CSV создаем отдельные файлы или один файл с метками
            base_path = file_path.replace('.csv', '')
            pd.DataFrame(data["униграммы"]).to_csv(f"{base_path}_униграммы.csv", index=False, encoding='utf-8-sig')
            pd.DataFrame(data["биграммы"]).to_csv(f"{base_path}_биграммы.csv", index=False, encoding='utf-8-sig')
            pd.DataFrame(data["триграммы"]).to_csv(f"{base_path}_триграммы.csv", index=False, encoding='utf-8-sig')
            pd.DataFrame(data["n-граммы"]).to_csv(f"{base_path}_n_граммы.csv", index=False, encoding='utf-8-sig')
            pd.DataFrame(data["фразы_с_предлогами"]).to_csv(f"{base_path}_фразы_с_предлогами.csv", index=False, encoding='utf-8-sig')
            QMessageBox.information(self, "Информация", f"Создано 5 CSV файлов с префиксом:\n{base_path}")

        else:  # JSON
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def _prepare_unigrams_data(self) -> List[Dict]:
        """Подготовка данных униграмм для экспорта"""
        data = []
        for lemma, info in sorted(self.unigram_data.items(), key=lambda x: x[1]['count'], reverse=True):
            # Получаем синонимы
            synonyms = self.syn_manager.get_active_synonyms(lemma, ReplacementType.UNIGRAM)
            synonyms_str = ", ".join([s for s in synonyms if s != lemma][:10])
            if len(synonyms) > 11:
                synonyms_str += f" ... (+{len(synonyms) - 10})"

            # Получаем формы
            forms_str = ", ".join([f"{form}({count})" for form, count in
                                   sorted(info['forms'].items(), key=lambda x: x[1], reverse=True)[:5]])

            data.append({
                "лемма": lemma,
                "количество_вхождений": info['count'],
                "количество_уникальных_форм": len(info['forms']),
                "формы": forms_str,
                "синонимы": synonyms_str if synonyms_str else "нет синонимов",
                "стоп_слово": "да" if info.get('is_stopword', False) else "нет",
                "выбрано_для_замены": "да" if info.get('replace', False) else "нет"
            })
        return data

    def _prepare_ngrams_data(self, ngrams_data: Dict) -> List[Dict]:
        """Подготовка данных для n-грамм (биграммы, триграммы и т.д.)"""
        data = []
        for ngram, info in sorted(ngrams_data.items(), key=lambda x: x[1].count if hasattr(x[1], 'count') else x[1].get('count', 0), reverse=True):
            # Получаем синонимы
            ngram_type = self._get_ngram_type_by_data(ngrams_data)
            synonyms = self.syn_manager.get_active_synonyms(ngram, ngram_type)
            synonyms_str = ", ".join([s for s in synonyms if s != ngram][:10])

            # Получаем формы
            if hasattr(info, 'forms'):
                forms_dict = info.forms
                replace_state = info.replace if hasattr(info, 'replace') else False
                count = info.count
            else:
                forms_dict = info.get('forms', {})
                replace_state = info.get('replace', False)
                count = info.get('count', 0)

            forms_str = ", ".join([f"{form}({cnt})" for form, cnt in
                                   sorted(forms_dict.items(), key=lambda x: x[1], reverse=True)[:5]])

            data.append({
                "фраза_лемма": ngram,
                "количество_вхождений": count,
                "количество_уникальных_форм": len(forms_dict),
                "формы_употребления": forms_str,
                "синонимы": synonyms_str if synonyms_str else "нет синонимов",
                "выбрано_для_замены": "да" if replace_state else "нет"
            })
        return data

    def _export_unigrams(self, file_path: str, file_format: str):
        """Экспорт только униграмм"""
        data = self._prepare_unigrams_data()
        self._save_dataframe(data, file_path, file_format, "Униграммы")

    def _export_ngrams(self, ngrams_data: Dict, sheet_name: str, file_path: str, file_format: str):
        """Экспорт n-грамм"""
        data = self._prepare_ngrams_data(ngrams_data)
        self._save_dataframe(data, file_path, file_format, sheet_name)

    def _save_dataframe(self, data: List[Dict], file_path: str, file_format: str, sheet_name: str):
        """Сохраняет DataFrame в файл"""
        df = pd.DataFrame(data)

        if file_format == "Excel (.xlsx)":
            df.to_excel(file_path, sheet_name=sheet_name, index=False)
        elif file_format == "CSV (.csv)":
            df.to_csv(file_path, index=False, encoding='utf-8-sig')
        else:  # JSON
            df.to_json(file_path, orient='records', force_ascii=False, indent=2)

    def _get_ngram_type_by_data(self, data: Dict) -> ReplacementType:
        """Определяет тип n-граммы по данным"""
        if data is self.bigram_data:
            return ReplacementType.BIGRAM
        elif data is self.trigram_data:
            return ReplacementType.TRIGRAM
        elif data is self.ngram_data:
            return ReplacementType.NGRAM
        elif data is self.prepositional_data:
            return ReplacementType.PREPOSITIONAL
        return ReplacementType.UNIGRAM
    def cascade_all_ngrams(self):
        """Каскадная обработка всех n-грамм (упрощенная версия)"""
        QMessageBox.information(
            self,
            "Каскадные синонимы",
            "Для массовой каскадной обработки:\n\n"
            "1. Используйте кнопку '🔗 Каскадные синонимы' в диалоге редактирования "
            "каждой конкретной n-граммы\n"
            "2. Или объедините синонимические множества через меню Сервис → "
            "'🔄 Объединить синонимические множества'\n\n"
            "Автоматическая массовая обработка заменена на ручной выбор "
            "для каждой n-граммы, чтобы дать больше контроля."
        )

    def show_about(self):
        """Показать информацию о программе"""
        QMessageBox.about(self, "О программе",
                          "🎯 СинонимайZZZер\n\n"
                          "Версия 2.0\n"
                          "Приложение для синонимизации текстов\n\n"
                          "© 2024 Все права защищены")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        self.setup_filter_widgets()

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)

        center_panel = self.create_center_panel()
        splitter.addWidget(center_panel)

        right_panel = self.create_right_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([400, 500, 500])

        self.setup_status_bar()
        self.setup_toolbar()

    def setup_filter_widgets(self):
        """Настройка виджетов фильтрации для всех вкладок"""
        # Фильтрация будет добавлена через обновление create_ngram_tab
        pass
    def save_all_synonyms(self):
        """Сохранить все синонимы и формы с улучшенным прогрессом"""
        try:
            # Проверяем, есть ли что сохранять
            if not hasattr(self.syn_manager, '_dirty_sections') or not self.syn_manager._dirty_sections:
                QMessageBox.information(self, "Информация", "Нет изменений для сохранения")
                return

            dirty_count = len(self.syn_manager._dirty_sections)
            reply = QMessageBox.question(
                self,
                "Сохранение синонимов",
                f"Сохранить {dirty_count} разделов синонимов и форм на диск?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                # Показываем улучшенный прогресс
                progress = QProgressDialog("Сохранение всех изменений...", "Отмена", 0, 100, self)
                progress.setWindowTitle("Сохранение")
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(0)
                progress.show()

                progress.setValue(10)
                progress.setLabelText("Подготовка данных...")
                QApplication.processEvents()

                # Быстрое сохранение
                success = self.syn_manager.save_all_changes(progress)

                if success:
                    progress.setValue(100)
                    progress.close()
                    QMessageBox.information(self, "Успех",
                                            f"✅ Все изменения успешно сохранены!\n\n"
                                            f"Сохранено разделов: {dirty_count}")
                else:
                    progress.close()
                    QMessageBox.warning(self, "Ошибка",
                                        "❌ Не удалось сохранить данные.\n"
                                        "Проверьте права доступа к файлу synonyms.json")

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка сохранения: {e}")
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка сохранения: {str(e)}")

    def open_batch_forms_edit(self):
        """Открыть диалог массового редактирования форм"""
        # Получаем все формы
        all_forms = self.syn_manager.get_all_forms()

        if not all_forms:
            QMessageBox.information(self, "Информация", "Нет данных о конкретных формах")
            return

        dialog = BatchFormsEditDialog(all_forms, self.syn_manager, self)
        dialog.exec()

    def edit_stop_words(self):
        """Открыть диалог редактирования стоп-слов"""
        dialog = StopWordEditDialog(self.stop_word_manager, self)
        dialog.exec()

    def open_find_replace(self):
        """Открыть диалог поиска и замены с правильным позиционированием"""
        if not self.find_replace_dialog:
            self.find_replace_dialog = FindReplaceDialog(self.result_text_edit, self)
            self.find_replace_dialog.setWindowFlags(Qt.Window)

        # Убедимся, что окно открывается на правильном экране
        self.find_replace_dialog.show()
        self.find_replace_dialog.raise_()
        self.find_replace_dialog.activateWindow()

        # Принудительно обновляем геометрию окна
        QTimer.singleShot(50, self.find_replace_dialog.center_on_parent)

    def setup_toolbar(self):
        toolbar = QToolBar("Инструменты")
        self.addToolBar(toolbar)

        # Оставляем только эти кнопки:
        save_action = QAction("💾 Сохранить синонимы", self)
        save_action.triggered.connect(self.save_all_synonyms)
        toolbar.addAction(save_action)
        export_analysis_action = QAction("📊 Экспорт данных анализа", self)
        export_analysis_action.setToolTip("Экспортировать результаты анализа (униграммы, биграммы и т.д.)")
        export_analysis_action.triggered.connect(self.export_analysis_data)
        toolbar.addAction(export_analysis_action)
        # Кнопка массового редактирования форм
        batch_forms_action = QAction("🔤 Массовое редактирование форм", self)
        batch_forms_action.setToolTip("Редактировать все конкретные формы")
        batch_forms_action.triggered.connect(self.open_batch_forms_edit)
        toolbar.addAction(batch_forms_action)

        # Кнопка редактирования стоп-слов (только список лемм)
        stop_words_action = QAction("🚫 Редактировать стоп-слова", self)
        stop_words_action.triggered.connect(self.edit_stop_words)
        toolbar.addAction(stop_words_action)

        find_replace_action = QAction("🔍 Поиск и замена", self)
        find_replace_action.triggered.connect(self.open_find_replace)
        toolbar.addAction(find_replace_action)

    def closeEvent(self, event):
        """Срабатывает при закрытии окна"""
        try:
            # Проверяем, есть ли несохранённые изменения
            if hasattr(self.syn_manager, '_save_pending') and self.syn_manager._save_pending:
                reply = QMessageBox.question(
                    self,
                    "Несохранённые изменения",
                    "Есть несохранённые изменения синонимов и форм. Сохранить перед выходом?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes:
                    if not self.syn_manager.save_all_changes(self):
                        QMessageBox.warning(self, "Ошибка",
                                            "Не удалось сохранить изменения. Проверьте права доступа к файлу synonyms.json")
                        event.ignore()
                        return
                elif reply == QMessageBox.Cancel:
                    event.ignore()
                    return

            # Сохраняем сессию
            self.session_manager.save_session()

            # Сохраняем геометрию окна
            self.save_window_geometry()

            logger.info("💾 Приложение закрыто")

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка при выходе: {e}")

        event.accept()

    def load_window_geometry(self):
        """Восстанавливаем размер и положение окна"""
        geometry = self.session_manager.data.get("window_geometry")
        if geometry:
            if geometry.get("is_maximized", False):
                self.showMaximized()
            else:
                self.setGeometry(
                    geometry.get("x", 100),
                    geometry.get("y", 100),
                    geometry.get("width", 1600),
                    geometry.get("height", 900)
                )
        else:
            # По умолчанию - максимизировано
            self.showMaximized()

    def save_window_geometry(self):
        """Сохраняем размер и положение окна"""
        self.session_manager.data["window_geometry"] = {
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height(),
            "is_maximized": self.isMaximized()  # Добавляем флаг максимизации
        }

    def create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title_label = QLabel("📄 Исходные тексты")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        button_layout = QHBoxLayout()

        load_btn = QPushButton("📂 Загрузить Excel")
        load_btn.setStyleSheet("QPushButton { padding: 8px; font-weight: bold; }")
        load_btn.clicked.connect(self.load_excel)

        analyze_btn = QPushButton("🔍 Анализировать")
        analyze_btn.setStyleSheet(
            "QPushButton { padding: 8px; font-weight: bold; background-color: #3498db; color: white; }")
        analyze_btn.clicked.connect(self.analyze_texts)

        button_layout.addWidget(load_btn)
        button_layout.addWidget(analyze_btn)
        layout.addLayout(button_layout)

        self.original_text_edit = QTextEdit()
        self.original_text_edit.setPlaceholderText("Загрузите Excel файл или введите тексты для анализа...")
        self.original_text_edit.setStyleSheet("QTextEdit { font-family: 'Arial'; font-size: 11pt; }")
        layout.addWidget(self.original_text_edit)

        return panel

    def create_center_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title_label = QLabel("🔄 Управление заменой")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        # Строка поиска
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Поиск:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по всем вкладкам...")
        self.search_edit.textChanged.connect(self.filter_tables)
        search_layout.addWidget(self.search_edit)

        clear_search_btn = QPushButton("❌")
        clear_search_btn.setToolTip("Очистить поиск")
        clear_search_btn.clicked.connect(lambda: self.search_edit.clear())
        search_layout.addWidget(clear_search_btn)

        layout.addLayout(search_layout)

        self.stats_label = QLabel("Загрузите текст для анализа")
        self.stats_label.setStyleSheet("color: #666; margin: 5px;")
        layout.addWidget(self.stats_label)

        self.tabs = QTabWidget()

        self.unigrams_tab = self.create_ngram_tab("Униграммы", ReplacementType.UNIGRAM)
        self.tabs.addTab(self.unigrams_tab, "📝 Слова")

        self.bigrams_tab = self.create_ngram_tab("Биграммы", ReplacementType.BIGRAM)
        self.tabs.addTab(self.bigrams_tab, "🔤 Биграммы")

        self.trigrams_tab = self.create_ngram_tab("Триграммы", ReplacementType.TRIGRAM)
        self.tabs.addTab(self.trigrams_tab, "📚 Триграммы")

        self.ngrams_tab = self.create_ngram_tab("N-граммы", ReplacementType.NGRAM)
        self.tabs.addTab(self.ngrams_tab, "🔠 N-граммы")

        self.prepositional_tab = self.create_ngram_tab("Формы с предлогами", ReplacementType.PREPOSITIONAL)
        self.tabs.addTab(self.prepositional_tab, "📋 С предлогами")



        layout.addWidget(self.tabs)

        return panel

    def create_ngram_tab(self, title: str, ngram_type: ReplacementType):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # =========== ПАНЕЛЬ ФИЛЬТРАЦИИ ===========
        filter_panel = QWidget()
        filter_layout = QHBoxLayout(filter_panel)

        # Комбобокс для выбора типа фильтра
        filter_layout.addWidget(QLabel("Фильтр:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "Все",
            "Только с синонимами",
            "Только выбранные",
            "Только без синонимов",
            "Только стоп-слова" if ngram_type == ReplacementType.UNIGRAM else "Только с предлогами"
        ])
        self.filter_combo.currentTextChanged.connect(
            lambda text: self.apply_filter(ngram_type, text)
        )

        # Кнопка применения фильтра
        apply_filter_btn = QPushButton("Применить фильтр")
        apply_filter_btn.clicked.connect(
            lambda: self.apply_filter(ngram_type, self.filter_combo.currentText())
        )

        # Кнопка сброса фильтра
        reset_filter_btn = QPushButton("Сбросить фильтр")
        reset_filter_btn.clicked.connect(
            lambda: self.reset_filter(ngram_type)
        )

        filter_layout.addWidget(self.filter_combo)
        filter_layout.addWidget(apply_filter_btn)
        filter_layout.addWidget(reset_filter_btn)
        filter_layout.addStretch()

        # Сохраняем ссылку на комбобокс по типу n-граммы
        if ngram_type == ReplacementType.UNIGRAM:
            self.unigrams_filter_combo = self.filter_combo
        elif ngram_type == ReplacementType.BIGRAM:
            self.bigrams_filter_combo = self.filter_combo
        elif ngram_type == ReplacementType.TRIGRAM:
            self.trigrams_filter_combo = self.filter_combo
        elif ngram_type == ReplacementType.NGRAM:
            self.ngrams_filter_combo = self.filter_combo
        elif ngram_type == ReplacementType.PREPOSITIONAL:
            self.prepositional_filter_combo = self.filter_combo

        layout.addWidget(filter_panel)
        # ==========================================

        # Существующий код с кнопками управления
        control_layout = QHBoxLayout()

        select_all_btn = QPushButton("✅ Выбрать все")
        select_all_btn.clicked.connect(lambda: self.toggle_all_ngrams(ngram_type, True))

        deselect_all_btn = QPushButton("❌ Снять все")
        deselect_all_btn.clicked.connect(lambda: self.toggle_all_ngrams(ngram_type, False))

        edit_synonyms_btn = QPushButton("✏️ Редактировать синонимы")
        edit_synonyms_btn.clicked.connect(lambda: self.edit_ngram_synonyms(ngram_type))

        control_layout.addWidget(select_all_btn)
        control_layout.addWidget(deselect_all_btn)
        control_layout.addWidget(edit_synonyms_btn)
        control_layout.addStretch()

        layout.addLayout(control_layout)

        # Таблица
        table = QTableWidget()

        if ngram_type == ReplacementType.UNIGRAM:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["✓", "Лемма", "Вхожд.", "Формы", "Синонимы", "🚫"])
            self.unigrams_table = table
        elif ngram_type == ReplacementType.BIGRAM:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["✓", "Лемма", "Формы употребления", "Вхожд.", "Синонимы", "Пример формы"])
            self.bigrams_table = table
        elif ngram_type == ReplacementType.TRIGRAM:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["✓", "Лемма", "Формы употребления", "Вхожд.", "Синонимы", "Пример формы"])
            self.trigrams_table = table
        elif ngram_type == ReplacementType.NGRAM:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["✓", "Лемма", "Формы употребления", "Вхожд.", "Синонимы", "Пример формы"])
            self.ngrams_table = table
        elif ngram_type == ReplacementType.PREPOSITIONAL:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["✓", "Фраза", "Формы употребления", "Вхожд.", "Синонимы", "Пример формы"])
            self.prepositional_table = table

        # Настраиваем поведение заголовков для возможности изменения размеров
        header = table.horizontalHeader()
        header.setSectionsMovable(True)  # Разрешаем перемещение столбцов
        header.setSectionResizeMode(QHeaderView.Interactive)  # Интерактивное изменение размера

        # Устанавливаем начальные размеры столбцов (опционально)
        if ngram_type == ReplacementType.UNIGRAM:
            header.setSectionResizeMode(0, QHeaderView.Fixed)  # Чекбокс - фиксированный
            header.resizeSection(0, 40)
            header.setSectionResizeMode(1, QHeaderView.Interactive)  # Лемма
            header.setSectionResizeMode(2, QHeaderView.Fixed)  # Вхождений - фиксированный
            header.resizeSection(2, 80)
            header.setSectionResizeMode(3, QHeaderView.Interactive)  # Формы
            header.setSectionResizeMode(4, QHeaderView.Interactive)  # Синонимы
            header.setSectionResizeMode(5, QHeaderView.Fixed)  # Стоп-слово - фиксированный
            header.resizeSection(5, 40)
        else:
            header.setSectionResizeMode(0, QHeaderView.Fixed)  # Чекбокс - фиксированный
            header.resizeSection(0, 40)
            header.setSectionResizeMode(1, QHeaderView.Interactive)  # Лемма/Фраза
            header.setSectionResizeMode(2, QHeaderView.Interactive)  # Формы употребления
            header.setSectionResizeMode(3, QHeaderView.Fixed)  # Вхождений - фиксированный
            header.resizeSection(3, 80)
            header.setSectionResizeMode(4, QHeaderView.Interactive)  # Синонимы
            header.setSectionResizeMode(5, QHeaderView.Interactive)  # Пример формы

        # Разрешаем изменение размера строк
        table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)

        layout.addWidget(table)

        return widget

    def apply_filter(self, ngram_type: ReplacementType, filter_text: str):
        """Применить фильтр к таблице"""
        table = self.get_table_by_type(ngram_type)

        if not table or table.rowCount() == 0:
            return

        for row in range(table.rowCount()):
            show_row = True

            # Получаем данные строки
            ngram_item = table.item(row, 1)  # Лемма/фраза
            synonyms_item = table.item(row, 4) if table.columnCount() > 4 else None  # Синонимы
            checkbox_item = table.item(row, 0)  # Чекбокс
            stopword_item = table.item(row,
                                       5) if ngram_type == ReplacementType.UNIGRAM and table.columnCount() > 5 else None  # Стоп-слово

            # Применяем фильтр
            if filter_text == "Только с синонимами":
                if synonyms_item:
                    # Проверяем, есть ли синонимы (не считая оригинала)
                    synonyms_text = synonyms_item.text().lower()
                    if synonyms_text == "нет синонимов" or not synonyms_text.strip():
                        show_row = False
                else:
                    show_row = False

            elif filter_text == "Только выбранные":
                if checkbox_item and checkbox_item.checkState() != Qt.Checked:
                    show_row = False

            elif filter_text == "Только без синонимов":
                if synonyms_item:
                    synonyms_text = synonyms_item.text().lower()
                    if synonyms_text != "нет синонимов" and synonyms_text.strip():
                        show_row = False

            elif filter_text == "Только стоп-слова" and ngram_type == ReplacementType.UNIGRAM:
                if stopword_item and stopword_item.text() != "🚫":
                    show_row = False

            elif filter_text == "Только с предлогами" and ngram_type == ReplacementType.PREPOSITIONAL:
                # Все строки в этой таблице уже с предлогами
                pass

            # Применяем видимость строки
            table.setRowHidden(row, not show_row)

        # Обновляем статистику
        visible_count = sum(1 for row in range(table.rowCount()) if not table.isRowHidden(row))
        total_count = table.rowCount()

        # Обновляем заголовок вкладки
        tab_index = -1
        if ngram_type == ReplacementType.UNIGRAM:
            tab_index = 0
        elif ngram_type == ReplacementType.BIGRAM:
            tab_index = 1
        elif ngram_type == ReplacementType.TRIGRAM:
            tab_index = 2
        elif ngram_type == ReplacementType.NGRAM:
            tab_index = 3
        elif ngram_type == ReplacementType.PREPOSITIONAL:
            tab_index = 4

        if tab_index >= 0:
            original_text = self.tabs.tabText(tab_index)
            base_text = original_text.split(" (")[0]
            if filter_text != "Все":
                self.tabs.setTabText(tab_index, f"{base_text} ({visible_count}/{total_count})")
            else:
                self.tabs.setTabText(tab_index, base_text)

    def reset_filter(self, ngram_type: ReplacementType):
        """Сбросить фильтр"""
        table = self.get_table_by_type(ngram_type)

        if not table:
            return

        # Показываем все строки
        for row in range(table.rowCount()):
            table.setRowHidden(row, False)

        # Сбрасываем комбобокс фильтра
        filter_combo = None
        if ngram_type == ReplacementType.UNIGRAM:
            filter_combo = getattr(self, 'unigrams_filter_combo', None)
        elif ngram_type == ReplacementType.BIGRAM:
            filter_combo = getattr(self, 'bigrams_filter_combo', None)
        elif ngram_type == ReplacementType.TRIGRAM:
            filter_combo = getattr(self, 'trigrams_filter_combo', None)
        elif ngram_type == ReplacementType.NGRAM:
            filter_combo = getattr(self, 'ngrams_filter_combo', None)
        elif ngram_type == ReplacementType.PREPOSITIONAL:
            filter_combo = getattr(self, 'prepositional_filter_combo', None)

        if filter_combo:
            filter_combo.setCurrentText("Все")

        # Обновляем заголовок вкладки
        tab_index = -1
        if ngram_type == ReplacementType.UNIGRAM:
            tab_index = 0
        elif ngram_type == ReplacementType.BIGRAM:
            tab_index = 1
        elif ngram_type == ReplacementType.TRIGRAM:
            tab_index = 2
        elif ngram_type == ReplacementType.NGRAM:
            tab_index = 3
        elif ngram_type == ReplacementType.PREPOSITIONAL:
            tab_index = 4

        if tab_index >= 0:
            original_text = self.tabs.tabText(tab_index)
            base_text = original_text.split(" (")[0]
            self.tabs.setTabText(tab_index, base_text)

    def get_filtered_ngrams(self, ngram_type: ReplacementType):
        """Получить отфильтрованные n-граммы"""
        table = self.get_table_by_type(ngram_type)
        filtered = []

        if not table:
            return filtered

        for row in range(table.rowCount()):
            if not table.isRowHidden(row):
                ngram_item = table.item(row, 1)
                if ngram_item:
                    filtered.append(ngram_item.text())

        return filtered
    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title_label = QLabel("✨ Результат")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        button_layout = QHBoxLayout()

        # ПОТОКОВЫЙ АНАЛИЗ (без зависаний)
        streaming_analyze_btn = QPushButton("💾 ПОТОКОВЫЙ АНАЛИЗ (без зависаний)")
        streaming_analyze_btn.setStyleSheet("background-color: #00bcd4; color: white; font-weight: bold;")
        streaming_analyze_btn.clicked.connect(self.analyze_streaming)
        button_layout.addWidget(streaming_analyze_btn)

        # ПАРАЛЛЕЛЬНЫЙ АНАЛИЗ
        parallel_analyze_btn = QPushButton("⚡ ПАРАЛЛЕЛЬНЫЙ АНАЛИЗ (все типы)")
        parallel_analyze_btn.setStyleSheet("background-color: #673ab7; color: white; font-weight: bold;")
        parallel_analyze_btn.clicked.connect(self.analyze_all_fast_parallel)
        button_layout.addWidget(parallel_analyze_btn)

        # СКЛЕЕННЫЙ АНАЛИЗ
        glued_analyze_btn = QPushButton("⚡ СКЛЕЕННЫЙ АНАЛИЗ")
        glued_analyze_btn.setStyleSheet("background-color: #9b59b6; color: white; font-weight: bold;")
        glued_analyze_btn.clicked.connect(self.analyze_fast_glued)
        button_layout.addWidget(glued_analyze_btn)

        # ЗАМЕНА + ЭКСПОРТ
        # ЗАМЕНА + ЭКСПОРТ (все типы)
        self.replace_all_btn = QPushButton("⚡ ЗАМЕНА + ЭКСПОРТ (все n-граммы)")
        self.replace_all_btn.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold;")
        self.replace_all_btn.clicked.connect(self.replace_and_export_all)
        button_layout.addWidget(self.replace_all_btn)

        # Обычные кнопки
        apply_btn = QPushButton("🔄 Применить замены")
        apply_btn.setStyleSheet("QPushButton { padding: 8px; font-weight: bold; background-color: #27ae60; color: white; }")
        apply_btn.clicked.connect(self.apply_replacements)

        edit_btn = QPushButton("✏️ Редактировать тексты")
        edit_btn.clicked.connect(self.edit_all_texts)

        export_btn = QPushButton("💾 Экспорт")
        export_btn.clicked.connect(self.export_results)

        clear_btn = QPushButton("🧹 Очистить")
        clear_btn.clicked.connect(self.clear_results)

        find_replace_btn = QPushButton("🔍 Поиск/Замена")
        find_replace_btn.clicked.connect(self.open_find_replace)

        button_layout.addWidget(apply_btn)
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(export_btn)
        button_layout.addWidget(clear_btn)
        button_layout.addWidget(find_replace_btn)

        layout.addLayout(button_layout)

        self.result_text_edit = QTextEdit()
        self.result_text_edit.setStyleSheet("QTextEdit { font-family: 'Arial'; font-size: 11pt; }")
        layout.addWidget(self.result_text_edit)

        return panel

    def setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("✅ Готов к работе")
        self.status_bar.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addWidget(self.progress_bar)

    def setup_connections(self):
        self.unigrams_table.cellDoubleClicked.connect(
            lambda row, col: self.on_ngram_double_click(row, col, ReplacementType.UNIGRAM))
        self.bigrams_table.cellDoubleClicked.connect(
            lambda row, col: self.on_ngram_double_click(row, col, ReplacementType.BIGRAM))
        self.trigrams_table.cellDoubleClicked.connect(
            lambda row, col: self.on_ngram_double_click(row, col, ReplacementType.TRIGRAM))
        self.ngrams_table.cellDoubleClicked.connect(
            lambda row, col: self.on_ngram_double_click(row, col, ReplacementType.NGRAM))
        self.prepositional_table.cellDoubleClicked.connect(
            lambda row, col: self.on_ngram_double_click(row, col, ReplacementType.PREPOSITIONAL))

        # ДОБАВЛЯЕМ обработчики изменений чекбоксов
        self.unigrams_table.cellChanged.connect(
            lambda row, col: self.on_ngram_checkbox_changed(row, col, ReplacementType.UNIGRAM))
        self.bigrams_table.cellChanged.connect(
            lambda row, col: self.on_ngram_checkbox_changed(row, col, ReplacementType.BIGRAM))
        self.trigrams_table.cellChanged.connect(
            lambda row, col: self.on_ngram_checkbox_changed(row, col, ReplacementType.TRIGRAM))
        self.ngrams_table.cellChanged.connect(
            lambda row, col: self.on_ngram_checkbox_changed(row, col, ReplacementType.NGRAM))
        self.prepositional_table.cellChanged.connect(
            lambda row, col: self.on_ngram_checkbox_changed(row, col, ReplacementType.PREPOSITIONAL))


        # Горячие клавиши
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.open_find_replace)
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self.open_find_replace)

    def on_ngram_checkbox_changed(self, row, column, ngram_type: ReplacementType):
        """Обработчик изменения чекбокса"""
        if column != 0:  # Только для колонки с чекбоксами
            return

        table = self.get_table_by_type(ngram_type)
        data = self.get_data_by_type(ngram_type)

        item = table.item(row, 0)
        ngram_item = table.item(row, 1)

        if item and ngram_item:
            ngram = ngram_item.text()
            state = item.checkState() == Qt.Checked

            # Обновляем данные в памяти
            if ngram in data:
                if ngram_type == ReplacementType.UNIGRAM:
                    data[ngram]['replace'] = state
                else:
                    if hasattr(data[ngram], 'replace'):
                        data[ngram].replace = state
                    elif isinstance(data[ngram], dict):
                        data[ngram]['replace'] = state

            logger.debug(f"🔧 Изменен {ngram_type.value} '{ngram}': replace={state}")

    def filter_tables(self):
        """Фильтрация таблиц с учетом фильтров"""
        search_text = self.search_edit.text().lower()

        if not search_text:
            # Если поиск пустой, применяем текущие фильтры
            self.apply_filter(ReplacementType.UNIGRAM,
                              self.unigrams_filter_combo.currentText() if self.unigrams_filter_combo else "Все")
            self.apply_filter(ReplacementType.BIGRAM,
                              self.bigrams_filter_combo.currentText() if self.bigrams_filter_combo else "Все")
            self.apply_filter(ReplacementType.TRIGRAM,
                              self.trigrams_filter_combo.currentText() if self.trigrams_filter_combo else "Все")
            self.apply_filter(ReplacementType.NGRAM,
                              self.ngrams_filter_combo.currentText() if self.ngrams_filter_combo else "Все")
            self.apply_filter(ReplacementType.PREPOSITIONAL,
                              self.prepositional_filter_combo.currentText() if self.prepositional_filter_combo else "Все")
            return

        # Фильтруем каждую таблицу с учетом поиска
        self.apply_search_filter(ReplacementType.UNIGRAM, search_text)
        self.apply_search_filter(ReplacementType.BIGRAM, search_text)
        self.apply_search_filter(ReplacementType.TRIGRAM, search_text)
        self.apply_search_filter(ReplacementType.NGRAM, search_text)
        self.apply_search_filter(ReplacementType.PREPOSITIONAL, search_text)

    def apply_search_filter(self, ngram_type: ReplacementType, search_text: str):
        """Применить поиск с учетом текущего фильтра"""
        table = self.get_table_by_type(ngram_type)

        if not table:
            return

        current_filter = "Все"
        if ngram_type == ReplacementType.UNIGRAM and self.unigrams_filter_combo:
            current_filter = self.unigrams_filter_combo.currentText()
        elif ngram_type == ReplacementType.BIGRAM and self.bigrams_filter_combo:
            current_filter = self.bigrams_filter_combo.currentText()
        elif ngram_type == ReplacementType.TRIGRAM and self.trigrams_filter_combo:
            current_filter = self.trigrams_filter_combo.currentText()
        elif ngram_type == ReplacementType.NGRAM and self.ngrams_filter_combo:
            current_filter = self.ngrams_filter_combo.currentText()
        elif ngram_type == ReplacementType.PREPOSITIONAL and self.prepositional_filter_combo:
            current_filter = self.prepositional_filter_combo.currentText()

        for row in range(table.rowCount()):
            # Сначала проверяем основной фильтр
            show_row = self.check_filter_condition(table, row, ngram_type, current_filter)

            # Затем проверяем поиск
            if show_row and search_text:
                found = False
                if ngram_type == ReplacementType.UNIGRAM:
                    columns_to_search = [1, 3, 4]  # Лемма, Формы, Синонимы
                else:
                    columns_to_search = [1, 2, 4, 5]  # Лемма, Формы, Синонимы, Пример

                for col in columns_to_search:
                    item = table.item(row, col)
                    if item and search_text in item.text().lower():
                        found = True
                        break

                show_row = found

            table.setRowHidden(row, not show_row)

    def check_filter_condition(self, table, row, ngram_type, filter_text):
        """Проверить условие фильтра для строки"""
        if filter_text == "Все":
            return True

        ngram_item = table.item(row, 1)
        synonyms_item = table.item(row, 4) if table.columnCount() > 4 else None
        checkbox_item = table.item(row, 0)
        stopword_item = table.item(row,
                                   5) if ngram_type == ReplacementType.UNIGRAM and table.columnCount() > 5 else None

        if filter_text == "Только с синонимами":
            if synonyms_item:
                synonyms_text = synonyms_item.text().lower()
                return synonyms_text != "нет синонимов" and synonyms_text.strip() != ""
            return False

        elif filter_text == "Только выбранные":
            if checkbox_item:
                return checkbox_item.checkState() == Qt.Checked
            return False

        elif filter_text == "Только без синонимов":
            if synonyms_item:
                synonyms_text = synonyms_item.text().lower()
                return synonyms_text == "нет синонимов" or synonyms_text.strip() == ""
            return True

        elif filter_text == "Только стоп-слова" and ngram_type == ReplacementType.UNIGRAM:
            if stopword_item:
                return stopword_item.text() == "🚫"
            return False

        elif filter_text == "Только с предлогами" and ngram_type == ReplacementType.PREPOSITIONAL:
            return True  # Все строки в этой таблице уже с предлогами

        return True

    def get_data_by_type(self, ngram_type: ReplacementType):
        """Возвращает данные по типу n-граммы"""
        if ngram_type == ReplacementType.UNIGRAM:
            return self.unigram_data
        elif ngram_type == ReplacementType.BIGRAM:
            return self.bigram_data
        elif ngram_type == ReplacementType.TRIGRAM:
            return self.trigram_data
        elif ngram_type == ReplacementType.NGRAM:
            return self.ngram_data
        elif ngram_type == ReplacementType.PREPOSITIONAL:
            return self.prepositional_data

        else:
            return {}

    def load_excel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите Excel файл", "", "Excel files (*.xlsx *.xls);;All files (*.*)")

        if not file_path:
            return

        try:
            self.show_processing("📂 Загрузка Excel файла...")

            df = pd.read_excel(file_path)

            # ОЧИСТКА СЕССИИ ДЛЯ НОВОГО ФАЙЛА
            self.checkbox_states.clear()  # Очищаем кеш чекбоксов

            # ВОССТАНАВЛИВАЕМ ВЫБОР КОЛОНКИ
            columns = df.columns.tolist()
            column_name, ok = QInputDialog.getItem(
                self, "Выбор колонки", "Выберите колонку с текстами:", columns, 0, False
            )
            if not ok or not column_name:
                self.hide_processing("Загрузка отменена")
                return
            texts = df[column_name].dropna().astype(str).tolist()

            self.original_texts = texts
            self.original_text_edit.setPlainText("\n".join(texts))
            self.hide_processing(f"✅ Загружено {len(texts)} текстов из колонки '{column_name}'")
            QMessageBox.information(self, "Успех", f"✅ Загружено {len(texts)} текстов из колонки '{column_name}'")

        except Exception as e:
            self.hide_processing("❌ Ошибка загрузки")
            QMessageBox.critical(self, "Ошибка", f"❌ Не удалось загрузить файл:\n{str(e)}")

    def analyze_texts(self):
        # Очищаем кеш чекбоксов при новом анализе
        self.checkbox_states.clear()

        if not self.original_texts and self.original_text_edit.toPlainText().strip():
            raw_text = self.original_text_edit.toPlainText().strip()
            # Разбиваем на тексты по пустым строкам или абзацам
            self.original_texts = [text.strip() for text in re.split(r'\n\s*\n', raw_text) if text.strip()]
            # Если нет разделения по абзацам, разбиваем по строкам
            if len(self.original_texts) == 1:
                self.original_texts = [text.strip() for text in raw_text.split('\n') if text.strip()]

        if not self.original_texts:
            QMessageBox.warning(self, "Внимание", "⚠️ Нет текстов для анализа")
            return

        # Очищаем таблицы
        self.unigrams_table.setRowCount(0)
        self.bigrams_table.setRowCount(0)
        self.trigrams_table.setRowCount(0)
        self.ngrams_table.setRowCount(0)
        self.prepositional_table.setRowCount(0)

        # Очищаем данные
        self.unigram_data.clear()
        self.bigram_data.clear()
        self.trigram_data.clear()
        self.ngram_data.clear()
        self.prepositional_data.clear()

        logger.info(f"📊 Начинаем анализ {len(self.original_texts)} текстов")

        # Выбираем анализатор в зависимости от объема
        if len(self.original_texts) > 100:
            # Для большого количества текстов используем порционный анализатор
            logger.info("🔢 Используем порционный анализатор (более 100 текстов)")
            batch_size = min(100, max(20, len(self.original_texts) // 10))  # Динамический batch_size
            self.current_analyzer = BatchTextAnalyzer(self.original_texts, self.stop_word_manager, batch_size)
        else:
            # Для малого количества текстов используем обычный анализатор
            logger.info("🔍 Используем обычный анализатор")
            self.current_analyzer = FastTextAnalyzer(self.original_texts, self.stop_word_manager)

        self.current_analyzer.progress_updated.connect(self.on_analysis_progress)
        self.current_analyzer.analysis_finished.connect(self.on_analysis_finished)
        self.current_analyzer.error_occurred.connect(self.on_analysis_error)
        self.current_analyzer.start()

    def on_analysis_progress(self, progress, message):
        self.show_processing(message)
        self.progress_bar.setValue(progress)

    def on_analysis_finished(self, unigrams, bigrams, trigrams, ngrams, prepositional):
        try:
            print(f"DEBUG: Анализ завершен - получены данные:")
            print(f"  Униграмм: {len(unigrams)}")
            print(f"  Биграмм: {len(bigrams)}")
            print(f"  Триграмм: {len(trigrams)}")
            print(f"  N-грамм: {len(ngrams)}")
            print(f"  Фразы с предлогами: {len(prepositional)}")

            self.hide_processing("✅ Анализ завершен")

            # Сохраняем данные
            self.unigram_data = unigrams
            self.bigram_data = bigrams
            self.trigram_data = trigrams
            self.ngram_data = ngrams
            self.prepositional_data = prepositional

            # Проверяем что данные не пустые
            if not unigrams and not bigrams and not trigrams and not ngrams and not prepositional:
                print("WARNING: Все данные пустые!")
                QMessageBox.warning(self, "Внимание", "Анализ завершен, но не найдено n-грамм. Проверьте текст.")
                return

            # Заполняем таблицы
            print("DEBUG: Заполняем таблицы...")
            self.populate_unigrams_table()
            self.populate_bigrams_table()
            self.populate_trigrams_table()
            self.populate_ngrams_table()
            self.populate_prepositional_table()
            print("DEBUG: Все таблицы заполнены")

            # Обновляем статистику
            total_words = sum(len(text.split()) for text in self.original_texts)
            self.update_stats(
                len(unigrams),
                len(bigrams),
                len(trigrams),
                len(ngrams),
                len(prepositional),
                total_words  # НЕ ЗАБЫВАЕМ total_words
            )

            # Показываем сообщение
            QMessageBox.information(self, "Успех",
                                    f"✅ Проанализировано {len(self.original_texts)} текстов\n"
                                    f"📝 Униграмм: {len(unigrams)}\n"
                                    f"🔤 Биграмм: {len(bigrams)}\n"
                                    f"📚 Триграммы: {len(trigrams)}\n"
                                    f"🔠 N-грамм: {len(ngrams)}\n"
                                    f"📋 Фраз с предлогами: {len(prepositional)}")
            self.reset_filter(ReplacementType.UNIGRAM)
            self.reset_filter(ReplacementType.BIGRAM)
            self.reset_filter(ReplacementType.TRIGRAM)
            self.reset_filter(ReplacementType.NGRAM)
            self.reset_filter(ReplacementType.PREPOSITIONAL)

        except Exception as e:
            print(f"ERROR в on_analysis_finished: {e}")
            import traceback
            traceback.print_exc()
            self.hide_processing("❌ Ошибка анализа")
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка при отображении результатов:\n{str(e)}")

    def on_analysis_error(self, error_message):
        self.hide_processing("❌ Ошибка анализа")
        QMessageBox.critical(self, "Ошибка", f"❌ Ошибка при анализе:\n{error_message}")

    def populate_unigrams_table(self):
        """Быстрое заполнение таблицы униграмм"""
        try:
            print(f"DEBUG: Быстрое заполнение униграмм, данных: {len(self.unigram_data)}")

            # ВАЖНО: Блокируем сигналы ДО начала операций
            self.unigrams_table.setUpdatesEnabled(False)
            self.unigrams_table.blockSignals(True)

            self.unigrams_table.setRowCount(len(self.unigram_data))

            # Оптимизация: создаем все элементы за раз
            sorted_unigrams = sorted(self.unigram_data.items(), key=lambda x: x[1]['count'], reverse=True)

            for row, (lemma, data) in enumerate(sorted_unigrams):
                # Чекбокс
                replace_item = QTableWidgetItem()
                key = f"{ReplacementType.UNIGRAM.value}:{lemma}"
                saved_state = self.checkbox_states.get(key, False)
                replace_item.setCheckState(Qt.Checked if saved_state else Qt.Unchecked)
                self.unigrams_table.setItem(row, 0, replace_item)

                # Лемма
                self.unigrams_table.setItem(row, 1, QTableWidgetItem(lemma))

                # Количество
                count_item = QTableWidgetItem(str(data['count']))
                count_item.setTextAlignment(Qt.AlignCenter)
                self.unigrams_table.setItem(row, 2, count_item)

                # Формы (сокращаем отображение)
                forms_text = self.get_forms_preview(data['forms'], 3)  # показываем только 3 формы
                self.unigrams_table.setItem(row, 3, QTableWidgetItem(forms_text))

                # Синонимы (только первые 3)
                synonyms = self.syn_manager.get_active_synonyms(lemma, ReplacementType.UNIGRAM)
                syns_text = self.get_synonyms_preview(synonyms, lemma, 3)
                self.unigrams_table.setItem(row, 4, QTableWidgetItem(syns_text))

                # 6. СТОП-СЛОВО (новая колонка)
                stop_item = QTableWidgetItem()
                if data.get('is_stopword', False):
                    stop_item.setText("🚫")
                    stop_item.setToolTip("Стоп-слово")
                    # Можно добавить цвет для наглядности
                    stop_item.setForeground(QColor(220, 53, 69))  # Красный
                self.unigrams_table.setItem(row, 5, stop_item)
            # ВАЖНО: Разрешаем обновления только ПОСЛЕ заполнения
            self.unigrams_table.blockSignals(False)
            self.unigrams_table.setUpdatesEnabled(True)

            # Однократное обновление отображения
            self.unigrams_table.viewport().update()

            print(f"DEBUG: Униграммы заполнены (оптимизировано), строк: {self.unigrams_table.rowCount()}")

        except Exception as e:
            self.unigrams_table.blockSignals(False)
            self.unigrams_table.setUpdatesEnabled(True)
            print(f"ERROR в populate_unigrams_table: {e}")
            import traceback
            traceback.print_exc()

    def filter_stopwords_in_table(self, checked: bool):
        """Фильтрует таблицу униграмм: показывать только стоп-слова или все"""
        if not hasattr(self, 'unigrams_table'):
            return

        for row in range(self.unigrams_table.rowCount()):
            stop_item = self.unigrams_table.item(row, 5)  # Колонка "🚫"
            if stop_item and stop_item.text() == "🚫":
                # Это стоп-слово - показываем если checked, иначе скрываем
                self.unigrams_table.setRowHidden(row, not checked)
            else:
                # Не стоп-слово - скрываем если checked, иначе показываем
                self.unigrams_table.setRowHidden(row, checked)
    def populate_bigrams_table(self):
        """Заполнение таблицы биграмм (поддержка словарей)"""
        self.bigrams_table.setRowCount(len(self.bigram_data))

        sorted_bigrams = sorted(self.bigram_data.items(), key=lambda x: x[1]['count'] if isinstance(x[1], dict) else x[1].count, reverse=True)

        for row, (bigram_lemma, data) in enumerate(sorted_bigrams):
            # Чекбокс
            replace_item = QTableWidgetItem()
            key = f"{ReplacementType.BIGRAM.value}:{bigram_lemma}"
            saved_state = self.checkbox_states.get(key, False)
            replace_item.setCheckState(Qt.Checked if saved_state else Qt.Unchecked)
            self.bigrams_table.setItem(row, 0, replace_item)

            # Лемма
            self.bigrams_table.setItem(row, 1, QTableWidgetItem(bigram_lemma))

            # Формы употребления
            if isinstance(data, dict):
                forms_dict = data.get('forms', {})
                count = data.get('count', 0)
            else:
                forms_dict = data.forms
                count = data.count

            forms_text = ", ".join([f"{form}({cnt})" for form, cnt in list(forms_dict.items())[:5]])
            if len(forms_dict) > 5:
                forms_text += f" ... (+{len(forms_dict) - 5})"
            self.bigrams_table.setItem(row, 2, QTableWidgetItem(forms_text))

            # Количество
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.bigrams_table.setItem(row, 3, count_item)

            # Синонимы
            syns = self.syn_manager.get_active_synonyms(bigram_lemma, ReplacementType.BIGRAM)
            syn_text = ", ".join([s for s in syns if s != bigram_lemma][:5])
            self.bigrams_table.setItem(row, 4, QTableWidgetItem(syn_text))

            # Пример формы
            example_form = list(forms_dict.keys())[0] if forms_dict else ""
            self.bigrams_table.setItem(row, 5, QTableWidgetItem(example_form))

    def populate_trigrams_table(self):
        """Заполнение таблицы триграмм (поддержка словарей)"""
        self.trigrams_table.setRowCount(len(self.trigram_data))

        sorted_trigrams = sorted(self.trigram_data.items(), key=lambda x: x[1]['count'] if isinstance(x[1], dict) else x[1].count, reverse=True)

        for row, (trigram_lemma, data) in enumerate(sorted_trigrams):
            # Чекбокс
            replace_item = QTableWidgetItem()
            key = f"{ReplacementType.TRIGRAM.value}:{trigram_lemma}"
            saved_state = self.checkbox_states.get(key, False)
            replace_item.setCheckState(Qt.Checked if saved_state else Qt.Unchecked)
            self.trigrams_table.setItem(row, 0, replace_item)

            # Лемма
            self.trigrams_table.setItem(row, 1, QTableWidgetItem(trigram_lemma))

            # Формы употребления
            if isinstance(data, dict):
                forms_dict = data.get('forms', {})
                count = data.get('count', 0)
            else:
                forms_dict = data.forms
                count = data.count

            forms_text = ", ".join([f"{form}({cnt})" for form, cnt in list(forms_dict.items())[:5]])
            if len(forms_dict) > 5:
                forms_text += f" ... (+{len(forms_dict) - 5})"
            self.trigrams_table.setItem(row, 2, QTableWidgetItem(forms_text))

            # Количество
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.trigrams_table.setItem(row, 3, count_item)

            # Синонимы
            syns = self.syn_manager.get_active_synonyms(trigram_lemma, ReplacementType.TRIGRAM)
            syn_text = ", ".join([s for s in syns if s != trigram_lemma][:5])
            self.trigrams_table.setItem(row, 4, QTableWidgetItem(syn_text))

            # Пример формы
            example_form = list(forms_dict.keys())[0] if forms_dict else ""
            self.trigrams_table.setItem(row, 5, QTableWidgetItem(example_form))

    def populate_ngrams_table(self):
        """Заполнение таблицы n-грамм (поддержка словарей)"""
        self.ngrams_table.setRowCount(len(self.ngram_data))

        sorted_ngrams = sorted(self.ngram_data.items(), key=lambda x: x[1]['count'] if isinstance(x[1], dict) else x[1].count, reverse=True)

        for row, (ngram_lemma, data) in enumerate(sorted_ngrams):
            # Чекбокс
            replace_item = QTableWidgetItem()
            key = f"{ReplacementType.NGRAM.value}:{ngram_lemma}"
            saved_state = self.checkbox_states.get(key, False)
            replace_item.setCheckState(Qt.Checked if saved_state else Qt.Unchecked)
            self.ngrams_table.setItem(row, 0, replace_item)

            # Лемма
            self.ngrams_table.setItem(row, 1, QTableWidgetItem(ngram_lemma))

            # Формы употребления
            if isinstance(data, dict):
                forms_dict = data.get('forms', {})
                count = data.get('count', 0)
            else:
                forms_dict = data.forms
                count = data.count

            forms_text = ", ".join([f"{form}({cnt})" for form, cnt in list(forms_dict.items())[:5]])
            if len(forms_dict) > 5:
                forms_text += f" ... (+{len(forms_dict) - 5})"
            self.ngrams_table.setItem(row, 2, QTableWidgetItem(forms_text))

            # Количество
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.ngrams_table.setItem(row, 3, count_item)

            # Синонимы
            syns = self.syn_manager.get_active_synonyms(ngram_lemma, ReplacementType.NGRAM)
            syn_text = ", ".join([s for s in syns if s != ngram_lemma][:5])
            self.ngrams_table.setItem(row, 4, QTableWidgetItem(syn_text))

            # Пример формы
            example_form = list(forms_dict.keys())[0] if forms_dict else ""
            self.ngrams_table.setItem(row, 5, QTableWidgetItem(example_form))

    def populate_prepositional_table(self):
        """Заполнение таблицы фраз с предлогами (поддержка словарей)"""
        self.prepositional_table.setRowCount(len(self.prepositional_data))

        sorted_prepositional = sorted(self.prepositional_data.items(), key=lambda x: x[1]['count'] if isinstance(x[1], dict) else x[1].count, reverse=True)

        for row, (phrase, data) in enumerate(sorted_prepositional):
            # Чекбокс
            replace_item = QTableWidgetItem()
            key = f"{ReplacementType.PREPOSITIONAL.value}:{phrase}"
            saved_state = self.checkbox_states.get(key, False)
            replace_item.setCheckState(Qt.Checked if saved_state else Qt.Unchecked)
            self.prepositional_table.setItem(row, 0, replace_item)

            # Фраза
            self.prepositional_table.setItem(row, 1, QTableWidgetItem(phrase))

            # Формы употребления
            if isinstance(data, dict):
                forms_dict = data.get('forms', {})
                count = data.get('count', 0)
            else:
                forms_dict = data.forms
                count = data.count

            forms_text = ", ".join([f"{form}({cnt})" for form, cnt in list(forms_dict.items())[:5]])
            if len(forms_dict) > 5:
                forms_text += f" ... (+{len(forms_dict) - 5})"
            self.prepositional_table.setItem(row, 2, QTableWidgetItem(forms_text))

            # Количество вхождений
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.prepositional_table.setItem(row, 3, count_item)

            # Синонимы
            syns = self.syn_manager.get_active_synonyms(phrase, ReplacementType.PREPOSITIONAL)
            syn_text = ", ".join([s for s in syns if s != phrase][:5])
            self.prepositional_table.setItem(row, 4, QTableWidgetItem(syn_text))

            # Пример формы
            example_form = list(forms_dict.keys())[0] if forms_dict else ""
            self.prepositional_table.setItem(row, 5, QTableWidgetItem(example_form))

    def apply_replacements(self):
        if not any([self.unigram_data, self.bigram_data, self.trigram_data, self.ngram_data,
                    self.prepositional_data]):
            QMessageBox.warning(self, "Внимание", "⚠️ Сначала проанализируйте текст")
            return

        # Считаем ВЫБРАННЫЕ n-граммы (с отмеченными чекбоксами)
        selected_unigrams = self.get_selected_ngrams(self.unigrams_table, self.unigram_data, ReplacementType.UNIGRAM)
        selected_bigrams = self.get_selected_ngrams(self.bigrams_table, self.bigram_data, ReplacementType.BIGRAM)
        selected_trigrams = self.get_selected_ngrams(self.trigrams_table, self.trigram_data, ReplacementType.TRIGRAM)
        selected_ngrams = self.get_selected_ngrams(self.ngrams_table, self.ngram_data, ReplacementType.NGRAM)
        selected_prepositional = self.get_selected_ngrams(self.prepositional_table, self.prepositional_data,
                                                          ReplacementType.PREPOSITIONAL)

        total_selected = (len(selected_unigrams) + len(selected_bigrams) +
                          len(selected_trigrams) + len(selected_ngrams) + len(selected_prepositional))


        if total_selected == 0:
            QMessageBox.warning(self, "Внимание",
                                "⚠️ Не выбрано ни одной n-граммы для замены!\n\n"
                                "Отметьте чекбоксы в таблицах 'Управление заменой'")
            return

        try:
            self.show_processing("🔄 Применение замен...")

            # Передаем ТОЛЬКО выбранные n-граммы
            self.processed_texts, all_replacements = self.replacer.replace_with_priority(
                self.original_texts,
                selected_unigrams,  # Только выбранные!
                selected_bigrams,  # Только выбранные!
                selected_trigrams,  # Только выбранные!
                selected_ngrams,  # Только выбранные!
                selected_prepositional  # Только выбранные!
            )

            self.current_replacements = all_replacements
            self.display_result_with_highlights()

            self.hide_processing(f"✅ Выполнено {len(all_replacements)} замен")

            if len(all_replacements) > 0:
                QMessageBox.information(self, "Успех",
                                        f"✅ Выполнено {len(all_replacements)} замен\n\n"
                                        f"Из выбранных {total_selected} n-грамм")
            else:
                QMessageBox.warning(self, "Внимание",
                                    f"⚠️ Замены не выполнены при выбранных {total_selected} n-граммах\n\n"
                                    "Возможные причины:\n"
                                    "• Все синонимы совпадают с оригиналом\n"
                                    "• Нет активных синонимов\n"
                                    "• Позиции замены пересекаются")

        except Exception as e:
            self.hide_processing("❌ Ошибка замен")
            logger.error(f"Критическая ошибка замены: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка при применении замен:\n{str(e)}")

    def get_selected_ngrams(self, table, data, ngram_type):
        """Возвращает ВЫБРАННЫЕ (с отмеченными чекбоксами) n-граммы из таблицы"""
        selected = {}
        if not table or not data:
            return selected

        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if not item:
                continue

            # ПРОВЕРЯЕМ ЧЕКБОКС - только если отмечен!
            if item.checkState() != Qt.Checked:
                continue  # Пропускаем если не отмечен

            ngram_item = table.item(row, 1)
            if not ngram_item:
                continue

            ngram = ngram_item.text()
            if ngram in data:
                logger.debug(f"✅ ВЫБРАНА {ngram_type.value}: {ngram}")

                # Обязательно устанавливаем replace=True для выбранных
                if ngram_type == ReplacementType.UNIGRAM:
                    selected[ngram] = {
                        'count': data[ngram].get('count', 0),
                        'forms': data[ngram].get('forms', {}),
                        'positions': data[ngram].get('positions', []),
                        'replace': True,  # Обязательно True!
                        'is_stopword': data[ngram].get('is_stopword', False)
                    }
                else:
                    if hasattr(data[ngram], 'replace'):
                        # Создаем копию с replace=True
                        selected[ngram] = {
                            'count': data[ngram].count,
                            'forms': data[ngram].forms,
                            'positions': data[ngram].positions,
                            'replace': True  # Обязательно True!
                        }
                    else:
                        selected[ngram] = {
                            'count': data[ngram].get('count', 0),
                            'forms': data[ngram].get('forms', {}),
                            'positions': data[ngram].get('positions', []),
                            'replace': True  # Обязательно True!
                        }

        logger.info(f"📋 Для {ngram_type.value} выбрано: {len(selected)} из {len(data)}")
        return selected

    def display_result_with_highlights(self):
        if not self.processed_texts:
            return

        # Создаем новый документ
        document = QTextDocument()

        full_text = ""
        adjusted_replacements = []
        current_position = 0

        for i, (original, processed) in enumerate(zip(self.original_texts, self.processed_texts)):
            # Формируем заголовок и текст до результата
            header = f"=== Текст {i + 1} ===\n"
            original_header = "ОРИГИНАЛ:\n"
            result_header = "РЕЗУЛЬТАТ:\n"
            separator = "=" * 80 + "\n\n"

            # Собираем текст до результата
            text_before_result = header + original_header + original + "\n\n" + result_header
            full_text += text_before_result

            # Позиция начала результата в общем тексте
            result_start_in_full = len(full_text)

            # Добавляем результат
            full_text += processed + "\n" + separator

            # Находим замены для этого текста
            text_replacements = [r for r in self.current_replacements if r.text_index == i]

            # Корректируем позиции замен для общего текста
            for replacement in text_replacements:
                # Проверяем, что позиции в пределах обработанного текста
                if (replacement.start >= 0 and replacement.end <= len(processed) and
                        replacement.start < replacement.end):
                    adjusted_replacement = ReplacementInfo(
                        original=replacement.original,
                        new=replacement.new,
                        start=result_start_in_full + replacement.start,
                        end=result_start_in_full + replacement.end,
                        text_index=i,
                        type=replacement.type,
                        used_synonym=replacement.used_synonym,
                        lemma=replacement.lemma,
                        context=replacement.context,
                        skipped_reason=replacement.skipped_reason
                    )
                    adjusted_replacements.append(adjusted_replacement)

        document.setPlainText(full_text)

        # Создаем подсветку с скорректированными позициями
        highlighter = FastHighlighter(document, adjusted_replacements)

        # Устанавливаем документ для QTextEdit
        self.result_text_edit.setDocument(document)
        self.result_text_edit.moveCursor(QTextCursor.Start)  # Прокручиваем к началу

        # Сохраняем ссылку на highlighter
        self.result_highlighter = highlighter

        # Логирование для отладки
        logger.info(
            f"📄 Отображено {len(self.processed_texts)} текстов, {len(adjusted_replacements)} подсвеченных замен")

    def edit_all_texts(self):
        if not self.processed_texts:
            QMessageBox.warning(self, "Внимание", "⚠️ Сначала примените замены")
            return

        dialog = SideBySideTextEditDialog(self.original_texts, self.processed_texts, self.current_replacements, self)

        if dialog.exec() == QDialog.Accepted:
            self.processed_texts = dialog.processed_texts
            self.display_result_with_highlights()
            QMessageBox.information(self, "Успех", "✅ Все изменения сохранены!")

    def export_results(self):
        if not self.processed_texts:
            QMessageBox.warning(self, "Внимание", "⚠️ Нет данных для экспорта")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Экспорт результатов", "", "Excel files (*.xlsx);;Text files (*.txt)")

        if not file_path:
            return

        try:
            self.show_processing("💾 Экспорт результатов...")

            if file_path.endswith('.xlsx'):
                data = {
                    'Оригинальный текст': self.original_texts,
                    'Обработанный текст': self.processed_texts
                }
                df = pd.DataFrame(data)
                df.to_excel(file_path, index=False)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for i, text in enumerate(self.processed_texts):
                        f.write(f"=== Текст {i + 1} ===\n")
                        f.write(text + "\n\n")

            self.hide_processing("✅ Экспорт завершен")
            QMessageBox.information(self, "Успех", f"✅ Результаты экспортированы в:\n{file_path}")

        except Exception as e:
            self.hide_processing("❌ Ошибка экспорта")
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка экспорта:\n{str(e)}")

    def clear_results(self):
        self.result_text_edit.clear()
        self.processed_texts.clear()
        self.current_replacements.clear()
        QMessageBox.information(self, "Успех", "✅ Результаты очищены")

    def toggle_all_ngrams(self, ngram_type: ReplacementType, state: bool):
        """Устанавливает все чекбоксы в указанное состояние"""
        table = self.get_table_by_type(ngram_type)
        data = self.get_data_by_type(ngram_type)

        # Блокируем сигналы чтобы не вызывать on_ngram_checkbox_changed для каждой строки
        table.blockSignals(True)

        try:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item:
                    item.setCheckState(Qt.Checked if state else Qt.Unchecked)

                    # Обновляем данные в памяти
                    ngram = table.item(row, 1).text()
                    if ngram in data:
                        if ngram_type == ReplacementType.UNIGRAM:
                            data[ngram]['replace'] = state
                        else:
                            if hasattr(data[ngram], 'replace'):
                                data[ngram].replace = state
                            elif isinstance(data[ngram], dict):
                                data[ngram]['replace'] = state
        finally:
            table.blockSignals(False)

        logger.info(f"🔧 {'Включены' if state else 'Отключены'} все {ngram_type.value} ({table.rowCount()})")

    def edit_ngram_synonyms(self, ngram_type: ReplacementType):
        table = self.get_table_by_type(ngram_type)
        current_row = table.currentRow()
        if current_row == -1:
            QMessageBox.warning(self, "Внимание", f"⚠️ Выберите {ngram_type.value} для редактирования синонимов")
            return

        ngram = table.item(current_row, 1).text()

        # ОТЛАДКА
        print(f"\n=== Редактирование {ngram_type.value}: {ngram} ===")

        # Получаем формы для этой n-граммы
        forms_dict = {}

        if ngram_type == ReplacementType.UNIGRAM:
            if ngram in self.unigram_data:
                forms_dict = self.unigram_data[ngram].get('forms', {})
                print(f"Униграмма: найдено {len(forms_dict)} форм")
            else:
                print(f"УНИГРАММА НЕ НАЙДЕНА: {ngram}")

        elif ngram_type == ReplacementType.BIGRAM:
            if ngram in self.bigram_data:
                data = self.bigram_data[ngram]
                if isinstance(data, dict):
                    forms_dict = data.get('forms', {})
                else:
                    forms_dict = data.forms if hasattr(data, 'forms') else {}
                print(f"Биграмма: найдено {len(forms_dict)} форм")
            else:
                print(f"БИГРАММА НЕ НАЙДЕНА: {ngram}")

        elif ngram_type == ReplacementType.TRIGRAM:
            if ngram in self.trigram_data:
                data = self.trigram_data[ngram]
                if isinstance(data, dict):
                    forms_dict = data.get('forms', {})
                else:
                    forms_dict = data.forms if hasattr(data, 'forms') else {}
                print(f"Триграмма: найдено {len(forms_dict)} форм")
            else:
                print(f"ТРИГРАММА НЕ НАЙДЕНА: {ngram}")

        elif ngram_type == ReplacementType.NGRAM:
            if ngram in self.ngram_data:
                data = self.ngram_data[ngram]
                if isinstance(data, dict):
                    forms_dict = data.get('forms', {})
                else:
                    forms_dict = data.forms if hasattr(data, 'forms') else {}
                print(f"N-грамма: найдено {len(forms_dict)} форм")
            else:
                print(f"N-ГРАММА НЕ НАЙДЕНА: {ngram}")

        elif ngram_type == ReplacementType.PREPOSITIONAL:
            if ngram in self.prepositional_data:
                data = self.prepositional_data[ngram]
                if isinstance(data, dict):
                    forms_dict = data.get('forms', {})
                else:
                    forms_dict = data.forms if hasattr(data, 'forms') else {}
                print(f"Предложная: найдено {len(forms_dict)} форм")
            else:
                print(f"ПРЕДЛОЖНАЯ НЕ НАЙДЕНА: {ngram}")

        print(f"Итоговый forms_dict: {list(forms_dict.keys())[:5]}...")

        # Открываем диалог
        dialog = FastSynonymEditDialog(ngram, ngram_type, self.syn_manager, forms_dict, self)

        if dialog.exec() == QDialog.Accepted:
            # Обновляем только нужную строку
            self.update_single_ngram_row(ngram_type, current_row, ngram)
            QMessageBox.information(self, "Успех", "✅ Синонимы успешно обновлены!")

    def update_single_ngram_row(self, ngram_type: ReplacementType, row: int, ngram: str):
        """Обновляет только одну строку в таблице вместо всей таблицы"""
        table = self.get_table_by_type(ngram_type)
        data = self.get_data_by_type(ngram_type)

        if ngram not in data:
            return

        # Обновляем колонку с синонимами
        if ngram_type == ReplacementType.UNIGRAM:
            # Для униграмм - 4-я колонка
            syns_item = table.item(row, 4)
            if syns_item:
                synonyms = self.syn_manager.get_active_synonyms(ngram, ngram_type)
                has_synonyms = len(synonyms) > 1
                if has_synonyms:
                    syns_text = ", ".join([s for s in synonyms if s != ngram][:5])
                    if len(synonyms) > 6:
                        syns_text += f"... (+{len(synonyms) - 5})"
                else:
                    syns_text = "нет синонимов"
                syns_item.setText(syns_text)

        else:
            # Для остальных - 4-я колонка (синонимы) и 5-я (пример формы)
            syns_item = table.item(row, 4)
            example_item = table.item(row, 5) if table.columnCount() > 5 else None

            if syns_item:
                synonyms = self.syn_manager.get_active_synonyms(ngram, ngram_type)
                syn_text = ", ".join([s for s in synonyms if s != ngram][:5])
                syns_item.setText(syn_text)

            if example_item:
                # Обновляем пример формы если нужно
                ngram_info = data.get(ngram)
                if ngram_info and hasattr(ngram_info, 'forms'):
                    forms_dict = ngram_info.forms
                    if forms_dict:
                        example_form = list(forms_dict.keys())[0]
                        example_item.setText(example_form)

    def get_forms_preview(self, forms_dict: Dict[str, int], max_forms: int = 3) -> str:
        """Создает сокращенный просмотр форм"""
        if not forms_dict:
            return ""

        sorted_forms = sorted(forms_dict.items(), key=lambda x: x[1], reverse=True)
        preview = []

        for i, (form, count) in enumerate(sorted_forms[:max_forms]):
            preview.append(f"{form}({count})")

        result = ", ".join(preview)
        if len(sorted_forms) > max_forms:
            result += f" (+{len(sorted_forms) - max_forms})"

        return result

    def get_synonyms_preview(self, synonyms: List[str], original: str, max_syns: int = 3) -> str:
        """Создает сокращенный просмотр синонимов"""
        if not synonyms or len(synonyms) <= 1:
            return "нет синонимов"

        # Фильтруем оригинал
        filtered = [s for s in synonyms if s.lower() != original.lower()]

        if not filtered:
            return "нет синонимов"

        preview = filtered[:max_syns]
        result = ", ".join(preview)

        if len(filtered) > max_syns:
            result += f" (+{len(filtered) - max_syns})"

        return result

    def get_table_by_type(self, ngram_type: ReplacementType):
        if ngram_type == ReplacementType.UNIGRAM:
            return self.unigrams_table
        elif ngram_type == ReplacementType.BIGRAM:
            return self.bigrams_table
        elif ngram_type == ReplacementType.TRIGRAM:
            return self.trigrams_table
        elif ngram_type == ReplacementType.NGRAM:
            return self.ngrams_table
        elif ngram_type == ReplacementType.PREPOSITIONAL:
            return self.prepositional_table

        else:
            return None

    def on_ngram_double_click(self, row, column, ngram_type: ReplacementType):
        self.edit_ngram_synonyms(ngram_type)

    def update_stats(self, unigram_count, bigram_count, trigram_count, ngram_count, prepositional_count, total_words):
        stats_text = (f"📊 Униграмм: {unigram_count} | "
                      f"🔤 Биграмм: {bigram_count} | "
                      f"📚 Триграммы: {trigram_count} | "
                      f"🔠 N-грамм: {ngram_count} | "
                      f"📋 С предлогами: {prepositional_count} | "
                      f"📝 Всего слов: {total_words}")
        self.stats_label.setText(stats_text)

    def show_processing(self, message="Обработка..."):
        self.status_label.setText(message)
        self.progress_bar.setVisible(True)
        QApplication.processEvents()

    def hide_processing(self, message="✅ Готово"):
        self.status_label.setText(message)
        self.progress_bar.setVisible(False)
        QApplication.processEvents()


# ==================== ПОРЦИОННЫЙ АНАЛИЗАТОР ====================
class BatchTextAnalyzer(QThread):
    """Анализатор с порционной обработкой для больших объемов текста"""

    progress_updated = Signal(int, str)
    analysis_finished = Signal(dict, dict, dict, dict, dict)
    error_occurred = Signal(str)

    def __init__(self, texts: List[str], stop_word_manager: StopWordManager, batch_size: int = 50):
        super().__init__()
        self.texts = texts
        self.stop_word_manager = stop_word_manager
        self.batch_size = batch_size  # Обрабатывать по N текстов за раз
        self._intermediate_results = []  # Для накопления промежуточных результатов
        self._word_cache = {}

        try:
            import pymorphy3
            self.morph = pymorphy3.MorphAnalyzer()
        except ImportError:
            self.morph = None

    def merge_results(self, results_list: List[tuple]) -> tuple:
        """Объединяет промежуточные результаты"""
        if not results_list:
            return {}, {}, {}, {}, {}

        # Инициализируем финальные структуры из первого результата
        final_unigrams, final_bigrams, final_trigrams, final_ngrams, final_prepositional = results_list[0]

        # Объединяем с остальными результатами
        for unigrams, bigrams, trigrams, ngrams, prepositional in results_list[1:]:
            # Униграммы
            for lemma, data in unigrams.items():
                if lemma in final_unigrams:
                    final_unigrams[lemma]['count'] += data['count']
                    final_unigrams[lemma]['positions'].extend(data['positions'])
                    for form, count in data['forms'].items():
                        final_unigrams[lemma]['forms'][form] = final_unigrams[lemma]['forms'].get(form, 0) + count
                else:
                    final_unigrams[lemma] = data.copy()

            # Биграммы
            for lemma, info in bigrams.items():
                if lemma in final_bigrams:
                    final_bigrams[lemma].count += info.count
                    final_bigrams[lemma].positions.extend(info.positions)
                    for form, count in info.forms.items():
                        final_bigrams[lemma].forms[form] = final_bigrams[lemma].forms.get(form, 0) + count
                else:
                    final_bigrams[lemma] = info

            # Триграммы
            for lemma, info in trigrams.items():
                if lemma in final_trigrams:
                    final_trigrams[lemma].count += info.count
                    final_trigrams[lemma].positions.extend(info.positions)
                    for form, count in info.forms.items():
                        final_trigrams[lemma].forms[form] = final_trigrams[lemma].forms.get(form, 0) + count
                else:
                    final_trigrams[lemma] = info

            # N-граммы
            for lemma, info in ngrams.items():
                if lemma in final_ngrams:
                    final_ngrams[lemma].count += info.count
                    final_ngrams[lemma].positions.extend(info.positions)
                    for form, count in info.forms.items():
                        final_ngrams[lemma].forms[form] = final_ngrams[lemma].forms.get(form, 0) + count
                else:
                    final_ngrams[lemma] = info

            # Фразы с предлогами
            for phrase, info in prepositional.items():
                if phrase in final_prepositional:
                    final_prepositional[phrase].count += info.count
                    final_prepositional[phrase].positions.extend(info.positions)
                    for form, count in info.forms.items():
                        final_prepositional[phrase].forms[form] = final_prepositional[phrase].forms.get(form, 0) + count
                else:
                    final_prepositional[phrase] = info

        return final_unigrams, final_bigrams, final_trigrams, final_ngrams, final_prepositional

    def process_batch(self, batch_texts: List[str], start_index: int) -> tuple:
        """Обрабатывает одну порцию текстов"""
        # Используем существующий анализатор, но с ограниченным набором текстов
        analyzer = FastTextAnalyzer(batch_texts, self.stop_word_manager)

        # Временные структуры для этой порции
        unigrams = defaultdict(lambda: {'count': 0, 'forms': defaultdict(int), 'replace': True, 'positions': []})
        bigrams = {}
        trigrams = {}
        ngrams = {}
        prepositional_phrases = {}

        # Проходим по каждому тексту в порции
        for local_idx, text in enumerate(batch_texts):
            text_index = start_index + local_idx  # Глобальный индекс текста

            if not text or not text.strip():
                continue

            try:
                # Униграммы
                words = re.findall(r'\b\w+\b', text.lower())
                word_positions = list(re.finditer(r'\b\w+\b', text, re.IGNORECASE))

                for i, (word, match) in enumerate(zip(words, word_positions)):
                    if len(word) > 2:
                        lemma = word
                        if self.morph:
                            parsed = self.morph.parse(word)[0]
                            lemma = parsed.normal_form

                        is_stopword = analyzer.is_stop_word(lemma)
                        unigrams[lemma]['count'] += 1
                        unigrams[lemma]['forms'][match.group()] += 1
                        unigrams[lemma]['positions'].append((text_index, match.start(), match.end()))
                        unigrams[lemma]['is_stopword'] = is_stopword

                # Биграммы
                bigram_data = analyzer.extract_clean_ngrams(text, text_index, 2)
                for lemma, info in bigram_data.items():
                    if lemma not in bigrams:
                        bigrams[lemma] = info
                    else:
                        bigrams[lemma].count += info.count
                        bigrams[lemma].positions.extend(info.positions)
                        for form, count in info.forms.items():
                            bigrams[lemma].forms[form] = bigrams[lemma].forms.get(form, 0) + count

                # Триграммы
                trigram_data = analyzer.extract_clean_ngrams(text, text_index, 3)
                for lemma, info in trigram_data.items():
                    if lemma not in trigrams:
                        trigrams[lemma] = info
                    else:
                        trigrams[lemma].count += info.count
                        trigrams[lemma].positions.extend(info.positions)
                        for form, count in info.forms.items():
                            trigrams[lemma].forms[form] = trigrams[lemma].forms.get(form, 0) + count

                # N-граммы (4-6 слов)
                for n in range(4, 7):
                    ngram_data = analyzer.extract_clean_ngrams(text, text_index, n)
                    for lemma, info in ngram_data.items():
                        if lemma not in ngrams:
                            ngrams[lemma] = info
                        else:
                            ngrams[lemma].count += info.count
                            ngrams[lemma].positions.extend(info.positions)
                            for form, count in info.forms.items():
                                ngrams[lemma].forms[form] = ngrams[lemma].forms.get(form, 0) + count

                # Фразы с предлогами
                prepositional_data = analyzer.extract_prepositional_phrases(text, text_index)
                for phrase, info in prepositional_data.items():
                    if phrase not in prepositional_phrases:
                        prepositional_phrases[phrase] = info
                    else:
                        prepositional_phrases[phrase].count += info.count
                        prepositional_phrases[phrase].positions.extend(info.positions)
                        for form, count in info.forms.items():
                            prepositional_phrases[phrase].forms[form] = prepositional_phrases[phrase].forms.get(form,
                                                                                                                0) + count

            except Exception as e:
                error_logger.log_error(f"Ошибка анализа текста {text_index}: {e}")
                continue

        return dict(unigrams), bigrams, trigrams, ngrams, prepositional_phrases

    def run(self):
        """Основной метод с порционной обработкой"""
        try:
            total_texts = len(self.texts)
            num_batches = (total_texts + self.batch_size - 1) // self.batch_size

            logger.info(
                f"🔢 Начинаем порционный анализ: {total_texts} текстов, {num_batches} порций по {self.batch_size} текстов")

            # Очищаем промежуточные результаты
            self._intermediate_results = []

            for batch_num in range(num_batches):
                start_idx = batch_num * self.batch_size
                end_idx = min(start_idx + self.batch_size, total_texts)
                batch_texts = self.texts[start_idx:end_idx]

                # Прогресс
                progress = int((batch_num / num_batches) * 100)
                self.progress_updated.emit(progress,
                                           f"Порция {batch_num + 1}/{num_batches} ({len(batch_texts)} текстов)")

                # Обрабатываем порцию
                batch_result = self.process_batch(batch_texts, start_idx)
                self._intermediate_results.append(batch_result)

                # Очищаем кеш и вызываем сборщик мусора
                self._word_cache.clear()
                import gc
                gc.collect()

                logger.info(f"✅ Обработана порция {batch_num + 1}/{num_batches}")

            # Объединяем все результаты
            self.progress_updated.emit(95, "Объединение результатов...")
            final_result = self.merge_results(self._intermediate_results)

            # Очищаем промежуточные результаты
            self._intermediate_results.clear()
            import gc
            gc.collect()

            self.progress_updated.emit(100, "Анализ завершен")
            self.analysis_finished.emit(*final_result)

        except Exception as e:
            error_logger.log_error(f"❌ Ошибка порционного анализа: {str(e)}", exc_info=True)
            self.error_occurred.emit(f"Ошибка анализа: {str(e)}")
# ==================== ДИАЛОГ МАССОВОГО РЕДАКТИРОВАНИЯ ФОРМ ====================
class BatchFormsEditDialog(QDialog):
    def __init__(self, forms_data: Dict[str, Dict], syn_manager: FastSynonymManager, parent=None):
        super().__init__(parent)
        self.forms_data = forms_data
        self.syn_manager = syn_manager
        self.parent_widget = parent

        self.setWindowTitle("Массовое редактирование конкретных форм")
        self.setGeometry(400, 300, 1200, 800)
        self.setup_ui()
        self.center_on_parent()  # Центрируем на родительском окне

    def center_on_parent(self):
        """Центрирует окно относительно родительского окна"""
        parent_widget = self.parent()
        if parent_widget:
            parent_geometry = parent_widget.frameGeometry()
            screen = QGuiApplication.screenAt(parent_geometry.center())
            if screen:
                screen_geometry = screen.availableGeometry()
                x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
                self.move(x, y)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Заголовок
        title_label = QLabel("🔤 Массовое редактирование конкретных форм")
        title_label.setStyleSheet("font-weight: bold; font-size: 12pt; margin: 10px;")
        layout.addWidget(title_label)

        # Информация
        info_label = QLabel(f"Загружено {len(self.forms_data)} записей форм")
        layout.addWidget(info_label)

        # Таблица
        self.forms_table = QTableWidget()
        self.forms_table.setColumnCount(4)
        self.forms_table.setHorizontalHeaderLabels(["Тип", "Оригинальная фраза", "Синоним", "Конкретная форма"])
        self.forms_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.forms_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.forms_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.forms_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

        layout.addWidget(self.forms_table)

        # Кнопки
        button_layout = QHBoxLayout()

        load_btn = QPushButton("📂 Загрузить из файла")
        load_btn.clicked.connect(self.load_from_file)
        load_btn.setToolTip("Загрузить формы из CSV или JSON файла")

        export_btn = QPushButton("💾 Экспорт в файл")
        export_btn.clicked.connect(self.export_to_file)
        export_btn.setToolTip("Экспортировать формы в CSV файл")

        save_btn = QPushButton("💾 Сохранить все формы")
        save_btn.clicked.connect(self.save_all_forms)
        save_btn.setToolTip("Сохранить все изменения форм")

        cancel_btn = QPushButton("❌ Закрыть")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(load_btn)
        button_layout.addWidget(export_btn)
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        self.populate_table()

    def populate_table(self):
        """Заполняем таблицу данными форм"""
        self.forms_table.setRowCount(len(self.forms_data))

        for i, (key, value) in enumerate(self.forms_data.items()):
            # Разбираем ключ: "unigram:слово:синоним"
            parts = key.split(":")
            if len(parts) == 3:
                ngram_type, original, synonym = parts

                # Тип
                type_item = QTableWidgetItem(ngram_type)
                self.forms_table.setItem(i, 0, type_item)

                # Оригинальная фраза
                orig_item = QTableWidgetItem(original)
                self.forms_table.setItem(i, 1, orig_item)

                # Синоним
                syn_item = QTableWidgetItem(synonym)
                self.forms_table.setItem(i, 2, syn_item)

                # Конкретная форма
                form_item = QTableWidgetItem(value)
                self.forms_table.setItem(i, 3, form_item)

    def load_from_file(self):
        """Загрузить формы из файла"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить формы", "", "CSV файлы (*.csv);;JSON файлы (*.json);;Все файлы (*.*)")

        if not file_path:
            return

        try:
            if file_path.endswith('.csv'):
                import pandas as pd
                df = pd.read_csv(file_path, encoding='utf-8')

                # Проверяем необходимые колонки
                required_columns = ['Тип', 'Оригинальная фраза', 'Синоним', 'Конкретная форма']
                for col in required_columns:
                    if col not in df.columns:
                        QMessageBox.critical(self, "Ошибка", f"В файле отсутствует колонка: {col}")
                        return

                # Обновляем данные
                for _, row in df.iterrows():
                    key = f"{row['Тип']}:{row['Оригинальная фраза']}:{row['Синоним']}"
                    self.forms_data[key] = row['Конкретная форма']

                self.populate_table()
                QMessageBox.information(self, "Успех", f"Загружено {len(df)} форм из CSV файла")

            elif file_path.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)

                self.forms_data.update(loaded_data)
                self.populate_table()
                QMessageBox.information(self, "Успех", f"Загружено {len(loaded_data)} форм из JSON файла")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл:\n{str(e)}")

    def export_to_file(self):
        """Экспортировать формы в файл"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт форм", "", "CSV файлы (*.csv);;JSON файлы (*.json)")

        if not file_path:
            return

        try:
            if file_path.endswith('.csv'):
                import pandas as pd

                # Подготавливаем данные для CSV
                rows = []
                for key, value in self.forms_data.items():
                    parts = key.split(":")
                    if len(parts) == 3:
                        rows.append({
                            'Тип': parts[0],
                            'Оригинальная фраза': parts[1],
                            'Синоним': parts[2],
                            'Конкретная форма': value
                        })

                df = pd.DataFrame(rows)
                df.to_csv(file_path, index=False, encoding='utf-8')
                QMessageBox.information(self, "Успех", f"Экспортировано {len(rows)} форм в CSV файл")

            elif file_path.endswith('.json'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.forms_data, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, "Успех", f"Экспортировано {len(self.forms_data)} форм в JSON файл")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать файл:\n{str(e)}")

    def save_all_forms(self):
        """Сохранить все формы"""
        try:
            progress = QProgressDialog("Сохранение всех форм...", "Отмена", 0, 100, self)
            progress.setWindowTitle("Сохранение")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()

            progress.setValue(10)
            progress.setLabelText("Подготовка данных...")
            QApplication.processEvents()

            # Обновляем формы в менеджере синонимов
            self.syn_manager.set_all_forms(self.forms_data)

            progress.setValue(50)
            progress.setLabelText("Сохранение на диск...")
            QApplication.processEvents()

            # Сохраняем все изменения
            if self.syn_manager.save_all_changes(self):
                progress.setValue(100)
                progress.close()
                QMessageBox.information(self, "Успех", "✅ Все формы успешно сохранены!")
                self.accept()
            else:
                progress.close()
                QMessageBox.warning(self, "Ошибка", "Не удалось сохранить формы")

        except Exception as e:
            if 'progress' in locals():
                progress.close()
            QMessageBox.critical(self, "Ошибка", f"❌ Ошибка сохранения: {str(e)}")


# ==================== ЗАПУСК ПРИЛОЖЕНИЯ ====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())