import json
import os
import re
import time
from typing import Dict, List, Optional, Any
import httpx
from openai import OpenAI
import streamlit as st
import requests
import re
import threading
from pathlib import Path
import time
from datetime import datetime
from database_settings.database import get_db
from api_key_manager import APIKeyManager, get_api_key_for_current_domain
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")

# ДОБАВИТЬ В КЛАСС AIGenerator:



def _estimate_cost(self, provider: str, model: str, tokens: Dict) -> float:
    """Примерная оценка стоимости (можно настроить под свои тарифы)"""
    total_tokens = tokens.get('total_tokens', 0)

    # Цены за 1K токенов (примерные)
    pricing = {
        'agentplatform': {
            'gpt-4o': 0.01,
            'gpt-4-turbo': 0.01,
            'gpt-3.5-turbo': 0.002,
            'default': 0.005
        },
        'deepseek': {
            'deepseek-chat': 0.001,
            'deepseek-coder': 0.001,
            'default': 0.001
        }
    }

    price_per_1k = pricing.get(provider, {}).get(model, pricing.get(provider, {}).get('default', 0.001))
    return (total_tokens / 1000) * price_per_1k

class AIConfigManager:
    """Менеджер настроек AI"""
    _lock = threading.Lock()  # ✅ ДОЛЖЕН БЫТЬ НА УРОВНЕ КЛАССА

    def __init__(self, config_file="config/ai_config.json", user_id: int = None, context=None):
        """
        Инициализация менеджера конфигурации AI
        """
        self.config_file = config_file
        self.user_id = user_id
        self.context = context

        # ✅ ДОБАВИТЬ СИНХРОНИЗАЦИЮ ДОМЕНА ИЗ ФАЙЛА
        try:
            import streamlit as st
            if 'domain_manager' not in st.session_state:
                from domain_manager import DomainManager
                st.session_state.domain_manager = DomainManager()

            dm = st.session_state.domain_manager
            user_id_from_session = st.session_state.get('user_id')

            if user_id_from_session:
                settings = dm.load_user_settings(user_id_from_session)
                saved_domain = settings.get('selected_domain', 'default')
                saved_site = settings.get('selected_site', 'steelborg')

                st.session_state.current_domain = saved_domain
                st.session_state.selected_domain = saved_domain
                st.session_state.current_site = saved_site
                st.session_state.selected_site = saved_site
                st.session_state[f'domain_system_{saved_site}'] = saved_domain

                print(f"✅ AIConfigManager загружен домен из файла: {saved_domain}")
        except:
            pass

        # Если есть контекст - берем user_id из него
        if context is not None:
            self.user_id = getattr(context, 'user_id', user_id)

        self.config = self.load_config()
        print(f"✅ AIConfigManager инициализирован, user_id={self.user_id}")
    def set_user_id(self, user_id: int):
        """Устанавливает user_id для логирования"""
        self.user_id = user_id

    def _get_user_id(self):
        """Получает user_id с приоритетом: context > параметр > session_state"""
        if self.context is not None:
            user_id = getattr(self.context, 'user_id', None)
            if user_id is not None:
                return user_id

        if self.user_id is not None:
            return self.user_id

        try:
            if 'user_id' in st.session_state:
                return st.session_state.user_id
        except:
            pass

        return None

    def load_config(self) -> Dict:
        with self.__class__._lock:  # ✅ Используем lock класса
            default_config = {
                "providers": {
                    "agentplatform": {
                        "model": "openai/gpt-4o",
                        "system_prompt": "Ты - опытный технический копирайтер и SEO-специалист.",
                        "temperature": 0.7,
                        "max_tokens": 2000,
                        "top_p": 0.9,
                        "frequency_penalty": 0.0,
                        "presence_penalty": 0.0
                    },
                    "deepseek": {
                        "model": "deepseek-chat",
                        "system_prompt": "Ты - опытный технический копирайтер и SEO-специалист.",
                        "temperature": 0.7,
                        "max_tokens": 2000,
                        "top_p": 0.9,
                        "frequency_penalty": 0.0,
                        "presence_penalty": 0.0
                    }
                },
                "default_provider": "agentplatform",
                "rate_limit": {
                    "requests_per_minute": 30,
                    "delay_between_requests": 2.0
                },
                "custom_models": []
            }

            try:
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)

                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        loaded_config = json.load(f)
                        merged_config = self._deep_merge(default_config, loaded_config)
                        return merged_config
                else:
                    with open(self.config_file, 'w', encoding='utf-8') as f:
                        json.dump(default_config, f, ensure_ascii=False, indent=2)
                    return default_config

            except Exception as e:
                st.error(f"Ошибка загрузки конфига AI: {e}")
                return default_config

    # ... остальные методы AIConfigManager ...

    def get_custom_models(self) -> List[str]:
        """Возвращает список пользовательских моделей."""
        return self.config.get("custom_models", [])

    def add_custom_model(self, model_name: str) -> bool:
        """Добавляет новую пользовательскую модель, если её ещё нет."""
        if model_name and model_name not in self.config["custom_models"]:
            self.config["custom_models"].append(model_name)
            return self.save_config()
        return False
    def get_system_prompt(self, provider: str = None) -> str:
        """Возвращает системный промпт для указанного провайдера"""
        if provider is None:
            provider = self.config.get("default_provider", "agentplatform")

        provider_config = self.get_provider_config(provider)
        return provider_config.get("system_prompt", "Ты - опытный технический копирайтер и SEO-специалист.")

    def update_system_prompt(self, provider: str, prompt: str) -> bool:
        """Обновляет системный промпт для провайдера"""
        if provider in self.config["providers"]:
            self.config["providers"][provider]["system_prompt"] = prompt
            return self.save_config()
        return False
    def update_custom_model(self, old_name: str, new_name: str) -> bool:
        """Обновляет название существующей пользовательской модели."""
        if old_name in self.config["custom_models"] and new_name and new_name != old_name:
            idx = self.config["custom_models"].index(old_name)
            self.config["custom_models"][idx] = new_name
            return self.save_config()
        return False

    def delete_custom_model(self, model_name: str) -> bool:
        """Удаляет пользовательскую модель."""
        if model_name in self.config["custom_models"]:
            self.config["custom_models"].remove(model_name)
            return self.save_config()
        return False
    def _deep_merge(self, default: Dict, loaded: Dict) -> Dict:
        """
        Рекурсивно объединяет загруженную конфигурацию с дефолтной.
        Гарантирует, что все ключи из default присутствуют в результате.
        """
        result = default.copy()

        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Рекурсивно объединяем вложенные словари
                result[key] = self._deep_merge(result[key], value)
            else:
                # Для остальных типов просто обновляем значение
                result[key] = value

        return result
    def merge_configs(self, default: Dict, loaded: Dict) -> None:
        """Рекурсивно объединяет конфиги"""
        for key, value in loaded.items():
            if key in default:
                if isinstance(value, dict) and isinstance(default[key], dict):
                    self.merge_configs(default[key], value)
                else:
                    default[key] = value

    def save_config(self) -> bool:
        with self.__class__._lock:
            """Сохраняет конфигурацию в файл"""
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                st.error(f"Ошибка сохранения конфига AI: {e}")
                return False

    def get_provider_config(self, provider: str) -> Dict:
        """Возвращает конфигурацию для провайдера"""
        return self.config["providers"].get(provider, {})

    def update_provider_config(self, provider: str, config: Dict) -> bool:
        """Обновляет конфигурацию провайдера"""
        self.config["providers"][provider] = config
        return self.save_config()

    def set_default_provider(self, provider: str) -> bool:
        """Устанавливает провайдера по умолчанию"""
        self.config["default_provider"] = provider
        return self.save_config()


class AIGenerator:
    """Генератор инструкций через AI API"""

    def __init__(self, config_manager: AIConfigManager):
        self.config_manager = config_manager
        self.rate_limit_delay = config_manager.config["rate_limit"]["delay_between_requests"]
        self.last_request_time = 0

    def _rate_limit(self):
        """Ограничение частоты запросов"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _prepare_prompt(self, prompt_template: str, context: Dict) -> str:
        """Подготавливает промпт с подстановкой контекста"""
        prompt = prompt_template

        # Заменяем плейсхолдеры из контекста
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))

        return prompt

    def get_available_models(self, provider: str = "agentplatform") -> Dict[str, str]:
        """Возвращает словарь доступных моделей для выпадающего списка"""
        if provider == "agentplatform":
            return {
                "openai/gpt-4o": "OpenAI GPT-4o",
                "openai/gpt-4-turbo": "OpenAI GPT-4 Turbo",
                "openai/gpt-3.5-turbo": "OpenAI GPT-3.5 Turbo"            }
        elif provider == "deepseek":
            return {
                "deepseek-chat": "DeepSeek Chat",
                "deepseek-coder": "DeepSeek Coder"
            }
        return {}

    # ai_settings/ai_module.py - ЗАМЕНИТЬ МЕТОД _call_agentplatform
    # ai_settings/ai_module.py - исправленный метод

    def _log_api_usage(self, user_id: int, project_id: str, site_name: str, domain_name: str,
                       provider: str, model: str, request_type: str, tokens: Dict,
                       success: bool, duration_ms: int, error_message: str = None):
        """Логирует использование API в БД"""
        try:
            if user_id is None or user_id == 0:
                print("⚠️ Пропуск логирования API: user_id = None")
                return

            # ✅ ЗАЩИТА ОТ None
            if not model:
                model = "unknown"

            with get_db() as conn:
                conn.execute("""
                    INSERT INTO api_usage_logs 
                    (user_id, project_id, site_name, domain_name, provider, model, request_type,
                     prompt_tokens, completion_tokens, total_tokens, estimated_cost,
                     request_duration_ms, success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, project_id, site_name, domain_name, provider, model, request_type,
                    tokens.get('prompt_tokens', 0),
                    tokens.get('completion_tokens', 0),
                    tokens.get('total_tokens', 0),
                    self._estimate_cost(provider, model, tokens),
                    duration_ms,
                    1 if success else 0,
                    error_message
                ))
                conn.commit()
        except Exception as e:
            print(f"⚠️ Ошибка логирования API: {e}")
    def _estimate_cost(self, provider: str, model: str, tokens: Dict) -> float:
        """Примерная оценка стоимости (можно настроить под свои тарифы)"""
        total_tokens = tokens.get('total_tokens', 0)

        # Цены за 1K токенов (примерные)
        pricing = {
            'agentplatform': {
                'gpt-4o': 0.01,
                'gpt-4-turbo': 0.01,
                'gpt-3.5-turbo': 0.002,
                'default': 0.005
            },
            'deepseek': {
                'deepseek-chat': 0.001,
                'deepseek-coder': 0.001,
                'default': 0.001
            }
        }

        price_per_1k = pricing.get(provider, {}).get(model, pricing.get(provider, {}).get('default', 0.001))
        return (total_tokens / 1000) * price_per_1k

    def _prepare_prompt(self, prompt_template: str, context: Dict) -> str:
        """Подготавливает промпт с подстановкой контекста"""
        prompt = prompt_template

        # Заменяем плейсхолдеры из контекста
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))

        return prompt

    def _call_agentplatform(self, prompt: str, config: Dict, num_variants: int,
                            model_override: str = None, return_full_response: bool = False,
                            user_id: int = None, project_id: str = None) -> List[Dict]:
        """Вызов через agentplatform.ru (OpenAI-совместимый API)"""
        results = []

        # ✅ Используем переданные параметры
        # user_id и project_id уже переданы в функцию

        # Получаем сайт и домен
        site_name = "unknown"
        domain_name = "unknown"

        # ПРИОРИТЕТ 1: Пытаемся получить из domain_manager
        try:
            if 'domain_manager' in st.session_state:
                dm = st.session_state.domain_manager
                site_name = dm.site_name
                domain_name = dm.get_current_domain()
        except:
            pass

        # ПРИОРИТЕТ 2: Если domain_manager не помог, пробуем из контекста (если есть)
        if site_name == "unknown" or domain_name == "unknown":
            try:
                # Пытаемся получить context из параметров функции или из других источников
                # В текущей версии context не передается в этот метод
                # Используем session_state как fallback
                if 'current_site' in st.session_state:
                    site_name = st.session_state.get('current_site', 'steelborg')
                if 'current_domain' in st.session_state:
                    domain_name = st.session_state.get('current_domain', 'default')
            except:
                pass

        # ✅ ПОЛУЧАЕМ API КЛЮЧ (БЕЗ ДУБЛИРОВАНИЯ)
        key_manager = APIKeyManager()
        api_key = key_manager.get_api_key(site_name, domain_name, "agentplatform")

        if not api_key:
            error_msg = f"Нет API ключа для AgentPlatform в домене {domain_name}. Обратитесь к администратору."
            return [{
                "success": False,
                "error": error_msg,
                "text": "",
                "variant": 1
            }]

        start_time = time.time()

        try:
            # Определяем модель: приоритет у model_override
            model = model_override if model_override else config.get("model", "openai/gpt-4o")

            client = OpenAI(
                api_key=api_key,
                base_url="https://api.agentplatform.ru/v1"
            )

            system_prompt = self.config_manager.get_system_prompt("agentplatform")

            completion_kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": config.get("temperature", 0.7),
                "max_tokens": config.get("max_tokens", 2000),
                "top_p": config.get("top_p", 0.9),
                "frequency_penalty": config.get("frequency_penalty", 0.0),
                "presence_penalty": config.get("presence_penalty", 0.0),
                "n": num_variants
            }

            response = client.chat.completions.create(**completion_kwargs)
            duration_ms = int((time.time() - start_time) * 1000)

            for i, choice in enumerate(response.choices):
                text = choice.message.content.strip()
                result_item = {
                    "success": True,
                    "text": text,
                    "variant": i + 1,
                    "model": model,
                    "provider": "agentplatform",
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                        "completion_tokens": response.usage.completion_tokens if response.usage else None,
                        "total_tokens": response.usage.total_tokens if response.usage else None
                    }
                }
                if return_full_response:
                    result_item["full_response"] = {
                        "id": response.id,
                        "model": response.model,
                        "choices": [
                            {
                                "index": c.index,
                                "message": {"role": c.message.role, "content": c.message.content},
                                "finish_reason": c.finish_reason
                            } for c in response.choices
                        ],
                        "usage": {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens
                        } if response.usage else None,
                        "created": response.created
                    }

                results.append(result_item)

                # Логируем использование API
                self._log_api_usage(
                    user_id=user_id,
                    project_id=project_id,
                    site_name=site_name,
                    domain_name=domain_name,
                    provider="agentplatform",
                    model=model,
                    request_type="generation",
                    tokens=result_item.get("usage", {}),
                    success=True,
                    duration_ms=duration_ms
                )

            return results

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Ошибка AgentPlatform: {str(e)}"

            self._log_api_usage(
                user_id=user_id,
                project_id=project_id,
                site_name=site_name,
                domain_name=domain_name,
                provider="agentplatform",
                model=model_override or config.get("model", "unknown"),
                request_type="generation",
                tokens={},
                success=False,
                duration_ms=duration_ms,
                error_message=error_msg
            )

            return [{
                "success": False,
                "error": error_msg,
                "text": "",
                "variant": 1
            }]


    # ИЗМЕНИТЬ МЕТОД _call_deepseek:

    # ai_settings/ai_module.py - ЗАМЕНИТЬ МЕТОД _call_deepseek

    def _call_deepseek(self, prompt: str, config: Dict, num_variants: int,
                       return_full_response: bool = False,
                       user_id: int = None, project_id: str = None) -> List[Dict]:
        """Вызов DeepSeek с получением ключа из БД"""
        results = []

        # ✅ user_id и project_id уже переданы в функцию

        # Получаем сайт и домен
        site_name = "unknown"
        domain_name = "unknown"

        try:
            if 'domain_manager' in st.session_state:
                dm = st.session_state.domain_manager
                site_name = dm.site_name
                domain_name = dm.get_current_domain()
        except:
            pass

        # Fallback из session_state
        if site_name == "unknown" or domain_name == "unknown":
            try:
                if 'current_site' in st.session_state:
                    site_name = st.session_state.get('current_site', 'steelborg')
                if 'current_domain' in st.session_state:
                    domain_name = st.session_state.get('current_domain', 'default')
            except:
                pass

        # Получаем API ключ через APIKeyManager из БД
        key_manager = APIKeyManager()
        api_key = key_manager.get_api_key(site_name, domain_name, "deepseek")

        if not api_key:
            error_msg = f"Нет API ключа для DeepSeek в домене {domain_name}. Обратитесь к администратору."
            return [{
                "success": False,
                "error": error_msg,
                "text": "",
                "variant": 1
            }]

        start_time = time.time()

        # ✅ ПОЛУЧАЕМ СИСТЕМНЫЙ ПРОМПТ ОДИН РАЗ ДО ЦИКЛА
        system_prompt = self.config_manager.get_system_prompt("deepseek")

        try:
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com/v1"
            )

            for i in range(num_variants):
                response = client.chat.completions.create(
                    model=config.get("model", "deepseek-chat"),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=config.get("temperature", 0.7),
                    max_tokens=config.get("max_tokens", 1000),
                    top_p=config.get("top_p", 0.9),
                    frequency_penalty=config.get("frequency_penalty", 0.0),
                    presence_penalty=config.get("presence_penalty", 0.0)
                )

                text = response.choices[0].message.content.strip()
                duration_ms = int((time.time() - start_time) * 1000)

                result = {
                    "success": True,
                    "text": text,
                    "variant": i + 1,
                    "model": config.get("model", "deepseek-chat"),
                    "provider": "deepseek",
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    } if response.usage else None
                }

                if return_full_response:
                    result["full_response"] = {
                        "id": response.id,
                        "model": response.model,
                        "choices": [
                            {
                                "index": c.index,
                                "message": {"role": c.message.role, "content": c.message.content},
                                "finish_reason": c.finish_reason
                            } for c in response.choices
                        ],
                        "usage": {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens
                        } if response.usage else None,
                        "created": response.created
                    }

                results.append(result)

                self._log_api_usage(
                    user_id=user_id,
                    project_id=project_id,
                    site_name=site_name,
                    domain_name=domain_name,
                    provider="deepseek",
                    model=config.get("model", "deepseek-chat"),
                    request_type="generation",
                    tokens=result.get("usage", {}),
                    success=True,
                    duration_ms=duration_ms
                )

            return results

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Ошибка DeepSeek: {str(e)}"

            self._log_api_usage(
                user_id=user_id,
                project_id=project_id,
                site_name=site_name,
                domain_name=domain_name,
                provider="deepseek",
                model=config.get("model", "unknown"),
                request_type="generation",
                tokens={},
                success=False,
                duration_ms=duration_ms,
                error_message=error_msg
            )

            return [{
                "success": False,
                "error": error_msg,
                "text": "",
                "variant": 1
            }]

    def generate_instruction(self, prompt_template: str, context: Dict,
                             provider: str = None, num_variants: int = 1,
                             return_full_response: bool = False,
                             model_override: str = None,
                             user_id: int = None, project_id: str = None) -> List[Dict]:
        """Генерация инструкции через AI"""

        # ✅ ПОЛУЧАЕМ USER_ID ЕСЛИ НЕ ПЕРЕДАН
        if user_id is None:
            user_id = self.config_manager._get_user_id() if hasattr(self.config_manager, '_get_user_id') else None

        if provider is None:
            provider = self.config_manager.config.get("default_provider", "agentplatform")

        config = self.config_manager.get_provider_config(provider)

        # Подстановка контекста в шаблон
        prompt = self._prepare_prompt(prompt_template, context)

        if provider == "deepseek":
            return self._call_deepseek(prompt, config, num_variants,
                                       return_full_response, user_id, project_id)
        else:
            return self._call_agentplatform(prompt, config, num_variants,
                                            model_override, return_full_response,
                                            user_id, project_id)

    def batch_generate_for_characteristics(self, prompt_template: str,
                                           characteristics: List[Dict],
                                           category: str,
                                           provider: str = None) -> Dict[str, List[Dict]]:
        """
        Пакетная генерация инструкций для списка характеристик

        Args:
            prompt_template: Шаблон промпта
            characteristics: Список характеристик
            category: Категория товара
            provider: Провайдер AI

        Returns:
            Словарь {characteristic_id: [результаты]}
        """
        results = {}

        for char in characteristics:
            char_id = char.get("char_id", "")
            char_name = char.get("char_name", "")
            is_unique = char.get("is_unique", False)
            values = char.get("values", [])

            char_results = []

            if is_unique:
                # Для unique характеристик генерируем для каждого значения
                for value_item in values:
                    value = value_item.get("value", "")

                    context = {
                        "категория": category,
                        "характеристика": char_name,
                        "значение": value,
                        "тип": "unique"
                    }

                    variants = self.generate_instruction(
                        prompt_template, context, provider, num_variants=1
                    )

                    if variants:
                        char_results.append({
                            "value": value,
                            "results": variants
                        })
            else:
                # Для regular характеристик генерируем общую инструкцию
                context = {
                    "категория": category,
                    "характеристика": char_name,
                    "тип": "regular"
                }

                variants = self.generate_instruction(
                    prompt_template, context, provider, num_variants=3
                )

                char_results = variants

            results[char_id] = char_results

        return results

class AIInstructionManager:
    """Менеджер для работы с AI-инструкциями - ПРИВЯЗАН К ПРОЕКТУ"""
    _lock = threading.Lock()

    def __init__(self, project_id: str = None, user_id: int = None,
                 site_name: str = None, domain_name: str = None,
                 context=None):
        self.context = context
        self.project_id = project_id
        self.user_id = user_id
        self.site_name = site_name
        self.domain_name = domain_name

        # ✅ ВАЖНО: ИНИЦИАЛИЗИРУЕМ АТРИБУТ СРАЗУ
        self.instructions = {}
        self.storage_dir = None
        self.storage_file = None

        # ✅ ДОБАВИТЬ СИНХРОНИЗАЦИЮ ДОМЕНА ИЗ ФАЙЛА
        try:
            import streamlit as st
            if 'domain_manager' not in st.session_state:
                from domain_manager import DomainManager
                st.session_state.domain_manager = DomainManager()

            dm = st.session_state.domain_manager
            user_id_from_session = st.session_state.get('user_id')

            if user_id_from_session:
                settings = dm.load_user_settings(user_id_from_session)
                saved_domain = settings.get('selected_domain', 'default')
                saved_site = settings.get('selected_site', 'steelborg')

                # Обновляем session_state
                st.session_state.current_domain = saved_domain
                st.session_state.selected_domain = saved_domain
                st.session_state.current_site = saved_site
                st.session_state.selected_site = saved_site
                st.session_state[f'domain_system_{saved_site}'] = saved_domain

                print(f"✅ AIInstructionManager загружен домен из файла: {saved_domain}")
        except:
            pass

        # Получаем site_name и domain_name из контекста (приоритет)
        if (site_name is None or domain_name is None) and context is not None:
            site_name = context.site_name
            domain_name = context.domain_name
            project_id = context.project_id
            user_id = context.user_id

        # Если нет в контексте - пробуем из session_state
        if site_name is None or domain_name is None:
            try:
                import streamlit as st
                if 'domain_manager' in st.session_state:
                    dm = st.session_state.domain_manager
                    site_name = site_name or dm.site_name
                    domain_name = domain_name or dm.get_current_domain()
            except:
                pass

        # Если нет project_id - пробуем взять из session_state
        if project_id is None:
            try:
                import streamlit as st
                if 'current_project_id' in st.session_state:
                    project_id = st.session_state.current_project_id
            except:
                pass

        if user_id is None:
            try:
                import streamlit as st
                if 'user_id' in st.session_state:
                    user_id = st.session_state.user_id
            except:
                pass

        # ✅ УБЕДИТЕСЬ, ЧТО storage_dir СОЗДАЁТСЯ ВСЕГДА
        if project_id and user_id and site_name and domain_name:
            self.storage_dir = Path(
                f"sites/{site_name}/domains/{domain_name}/projects/{user_id}/{project_id}/ai_instructions")
        else:
            # Fallback для случая, когда не хватает данных
            self.storage_dir = Path("temp/ai_instructions")
            print(f"⚠️ AIInstructionManager: нет параметров, использую {self.storage_dir}")

            # Пытаемся восстановить из session_state
            try:
                import streamlit as st
                if 'current_project_id' in st.session_state and 'user_id' in st.session_state:
                    project_id = st.session_state.current_project_id
                    user_id = st.session_state.user_id
                    if 'domain_manager' in st.session_state:
                        dm = st.session_state.domain_manager
                        site_name = dm.site_name
                        domain_name = dm.get_current_domain()
                        if project_id and user_id and site_name and domain_name:
                            self.storage_dir = Path(
                                f"sites/{site_name}/domains/{domain_name}/projects/{user_id}/{project_id}/ai_instructions")
                            print(f"🔄 Восстановлен путь: {self.storage_dir}")
            except:
                pass

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = self.storage_dir / "instructions.json"

        # ✅ ЗАГРУЖАЕМ ИНСТРУКЦИИ (ЭТО СОЗДАЕТ self.instructions)
        self.instructions = self.load_instructions()
        print(f"✅ AIInstructionManager загружен: {len(self.instructions)} блоков")
    def switch_project(self, project_id: str, user_id: int, site_name: str = None, domain_name: str = None):
        # Если нет site_name/domain_name, пробуем из контекста
        if (site_name is None or domain_name is None) and self.context is not None:
            site_name = site_name or self.context.site_name
            domain_name = domain_name or self.context.domain_name

        # Если нет в контексте - пробуем из session_state
        if site_name is None or domain_name is None:
            try:
                import streamlit as st
                if 'domain_manager' in st.session_state:
                    dm = st.session_state.domain_manager
                    site_name = site_name or dm.site_name
                    domain_name = domain_name or dm.get_current_domain()
            except:
                pass

        self.storage_dir = Path(f"sites/{site_name}/domains/{domain_name}/projects/{user_id}/{project_id}/ai_instructions")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = self.storage_dir / "instructions.json"
        self.instructions = self.load_instructions()
        print(f"🔄 AIInstructionManager переключен на проект {project_id}")
    @staticmethod
    def normalize_string(s):
        """Удаляет лишние пробелы и приводит к нижнему регистру"""
        if not isinstance(s, str):
            return ""
        return re.sub(r'\s+', ' ', s.strip()).lower()

    def load_instructions(self) -> Dict:
        with self.__class__._lock:
            try:
                if self.storage_file.exists():
                    with open(self.storage_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception as e:
                print(f"Ошибка загрузки AI инструкций: {e}")
            return {}

    def reload(self):
        """Перезагружает инструкции из файла (сбрасывает кэш в памяти)"""
        self.instructions = self.load_instructions()
        return True

    def clear_all_instructions(self):
        """Полностью очищает все инструкции текущего домена (память и файл)"""
        self.instructions = {}
        return self.save_instructions()

    def save_instructions(self) -> bool:
        """Сохраняет инструкции в файл домена"""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.instructions, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            st.error(f"Ошибка сохранения AI инструкций: {e}")
            return False

    def find_matching_context_hash(self, block_id: str, var_name: str,
                                   expected_context: Dict) -> Optional[str]:
        """
        Находит хэш контекста, который соответствует ожидаемому контексту
        """
        if block_id not in self.instructions:
            return None

        if var_name not in self.instructions[block_id]:
            return None

        # Нормализуем ожидаемый контекст
        exp_norm = {
            "категория": self.normalize_string(expected_context.get("категория", "")),
            "характеристика": self.normalize_string(expected_context.get("характеристика", "")),
            "тип": self.normalize_string(expected_context.get("тип", "regular")),
            "значение": self.normalize_string(expected_context.get("значение", "")),
            "block_id": self.normalize_string(expected_context.get("block_id", ""))
        }

        for context_hash, data in self.instructions[block_id][var_name].items():
            stored_context = data.get("context", {})
            stored_norm = {
                "категория": self.normalize_string(stored_context.get("категория", "")),
                "характеристика": self.normalize_string(stored_context.get("характеристика", "")),
                "тип": self.normalize_string(stored_context.get("тип", "regular")),
                "значение": self.normalize_string(stored_context.get("значение", "")),
                "block_id": self.normalize_string(stored_context.get("block_id", ""))
            }

            expected_type = exp_norm["тип"]
            stored_type = stored_norm["тип"]

            # Для разных типов - разные правила сравнения
            if expected_type != stored_type:
                continue

            # 1. Для OTHER блоков: сравниваем категорию, block_id и тип
            if expected_type == "other":
                if (stored_norm["категория"] == exp_norm["категория"] and
                        stored_norm["block_id"] == exp_norm["block_id"]):
                    return context_hash

            # 2. Для REGULAR характеристик: сравниваем категорию и характеристику
            elif expected_type == "regular":
                if (stored_norm["категория"] == exp_norm["категория"] and
                        stored_norm["характеристика"] == exp_norm["характеристика"]):
                    return context_hash

            # 3. Для UNIQUE характеристик: сравниваем категорию, характеристику и значение
            elif expected_type == "unique":
                if (stored_norm["категория"] == exp_norm["категория"] and
                        stored_norm["характеристика"] == exp_norm["характеристика"] and
                        stored_norm["значение"] == exp_norm["значение"]):
                    return context_hash

            # 4. Для других типов (старая логика для совместимости)
            else:
                match = True
                for key in ["категория", "характеристика", "тип", "block_id"]:
                    if exp_norm.get(key) and stored_norm.get(key) != exp_norm[key]:
                        match = False
                        break
                if match and exp_norm["тип"] == "unique" and exp_norm.get("значение"):
                    if stored_norm.get("значение") != exp_norm["значение"]:
                        match = False
                if match:
                    return context_hash

        return None

    def get_all_contexts_for_variable(self, block_id: str, var_name: str) -> List[Dict]:
        with self.__class__._lock:
            if block_id not in self.instructions:
                return []

            if var_name not in self.instructions[block_id]:
                return []

            contexts = []
            for context_hash, data in self.instructions[block_id][var_name].items():
                context_info = {
                    "hash": context_hash,
                    "context": data.get("context", {}),
                    "values_count": len(data.get("values", [])),
                    "original_count": len(data.get("original_values", [])),
                    "updated_at": data.get("updated_at", 0)
                }
                contexts.append(context_info)

            return contexts

    def get_instruction(self, block_id: str, var_name: str,
                        expected_context: Dict = None) -> Optional[List[str]]:
        with self.__class__._lock:
            if block_id not in self.instructions:
                return None

            if var_name not in self.instructions[block_id]:
                return None

            if expected_context is None:
                # Если контекст не указан, возвращаем первую найденную инструкцию
                for context_hash, data in self.instructions[block_id][var_name].items():
                    return data.get("values", [])
                return None

            # Нормализуем ожидаемый контекст
            exp_norm = {
                "категория": self.normalize_string(expected_context.get("категория", "")),
                "характеристика": self.normalize_string(expected_context.get("характеристика", "")),
                "тип": self.normalize_string(expected_context.get("тип", "regular")),
                "значение": self.normalize_string(expected_context.get("значение", "")),
                "block_id": self.normalize_string(expected_context.get("block_id", ""))
            }

            for context_hash, data in self.instructions[block_id][var_name].items():
                stored_context = data.get("context", {})
                stored_norm = {
                    "категория": self.normalize_string(stored_context.get("категория", "")),
                    "характеристика": self.normalize_string(stored_context.get("характеристика", "")),
                    "тип": self.normalize_string(stored_context.get("тип", "regular")),
                    "значение": self.normalize_string(stored_context.get("значение", "")),
                    "block_id": self.normalize_string(stored_context.get("block_id", ""))
                }

                expected_type = exp_norm["тип"]
                stored_type = stored_norm["тип"]

                if expected_type != stored_type:
                    continue

                # 1. Для OTHER блоков
                if expected_type == "other":
                    if (stored_norm["категория"] == exp_norm["категория"] and
                            stored_norm["block_id"] == exp_norm["block_id"]):
                        return data.get("values", [])

                # 2. Для REGULAR характеристик
                elif expected_type == "regular":
                    if (stored_norm["категория"] == exp_norm["категория"] and
                            stored_norm["характеристика"] == exp_norm["характеристика"]):
                        return data.get("values", [])

                # 3. Для UNIQUE характеристик
                elif expected_type == "unique":
                    if (stored_norm["категория"] == exp_norm["категория"] and
                            stored_norm["характеристика"] == exp_norm["характеристика"] and
                            stored_norm["значение"] == exp_norm["значение"]):
                        return data.get("values", [])

            return None

    def save_instruction(self, block_id: str, var_name: str,
                         values: List[str], context: Dict = None,
                         metadata: Dict = None) -> bool:
        with self.__class__._lock:
            if block_id not in self.instructions:
                self.instructions[block_id] = {}

            if var_name not in self.instructions[block_id]:
                self.instructions[block_id][var_name] = {}

            # Нормализуем контекст
            if context:
                normalized_context = {
                    "категория": self.normalize_string(context.get("категория", "")),
                    "характеристика": self.normalize_string(context.get("характеристика", "")),
                    "тип": self.normalize_string(context.get("тип", "regular")),
                    "значение": self.normalize_string(context.get("значение", "")),
                    "block_id": self.normalize_string(context.get("block_id", ""))
                }
            else:
                normalized_context = {
                    "категория": "",
                    "характеристика": "",
                    "тип": "regular",
                    "значение": "",
                    "block_id": ""
                }

            # Создаем хэш контекста для уникального ключа
            import hashlib
            context_str = json.dumps(normalized_context, sort_keys=True)
            context_hash = hashlib.md5(context_str.encode()).hexdigest()

            # Разбиваем инструкции на пункты
            split_values = []
            for value in values:
                if isinstance(value, str):
                    items = [item.strip() for item in value.split(';') if item.strip()]
                    split_values.extend(items)
                else:
                    split_values.append(str(value))

            # Сохраняем
            self.instructions[block_id][var_name][context_hash] = {
                "values": split_values,
                "original_values": values,
                "context": normalized_context,
                "metadata": metadata or {},
                "updated_at": time.time()
            }

            return self.save_instructions()

    def update_instruction_value(self, block_id: str, var_name: str,
                                 context_hash: str, index: int, new_value: str) -> bool:
        """Обновляет конкретное значение инструкции"""
        try:
            if (block_id in self.instructions and
                    var_name in self.instructions[block_id] and
                    context_hash in self.instructions[block_id][var_name]):

                values = self.instructions[block_id][var_name][context_hash]["values"]
                if 0 <= index < len(values):
                    values[index] = new_value
                    return self.save_instructions()
        except:
            pass
        return False

    def update_full_instruction(self, block_id: str, var_name: str,
                                context_hash: str, index: int, new_full_value: str) -> bool:
        """Обновляет полную инструкцию и переразбивает ее на пункты"""
        try:
            if (block_id in self.instructions and
                    var_name in self.instructions[block_id] and
                    context_hash in self.instructions[block_id][var_name]):

                # Обновляем оригинальное значение
                original_values = self.instructions[block_id][var_name][context_hash]["original_values"]
                if 0 <= index < len(original_values):
                    original_values[index] = new_full_value

                # Переразбиваем на пункты
                split_values = []
                for value in original_values:
                    if isinstance(value, str):
                        items = [item.strip() for item in value.split(';') if item.strip()]
                        split_values.extend(items)
                    else:
                        split_values.append(str(value))

                # Обновляем разбитые значения
                self.instructions[block_id][var_name][context_hash]["values"] = split_values

                return self.save_instructions()
        except:
            pass
        return False

    def delete_instruction(self, block_id: str, var_name: str,
                           context_hash: str = None) -> bool:
        """Удаляет инструкции"""
        try:
            if block_id in self.instructions:
                if var_name in self.instructions[block_id]:
                    if context_hash:
                        if context_hash in self.instructions[block_id][var_name]:
                            del self.instructions[block_id][var_name][context_hash]
                    else:
                        del self.instructions[block_id][var_name]

                    # Удаляем пустые структуры
                    if not self.instructions[block_id][var_name]:
                        del self.instructions[block_id][var_name]
                    if not self.instructions[block_id]:
                        del self.instructions[block_id]

                    return self.save_instructions()
        except:
            pass
        return False