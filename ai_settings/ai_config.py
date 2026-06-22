import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
from ai_settings.ai_module import AIConfigManager, AIGenerator


def show_ai_config_interface():
    """Интерфейс для настройки параметров AI (agentplatform + deepseek)"""

    if 'ai_config_manager' not in st.session_state:
        st.session_state.ai_config_manager = AIConfigManager()

    config_manager = st.session_state.ai_config_manager

    # Создаём экземпляр генератора, чтобы использовать get_available_models
    if 'ai_generator' not in st.session_state:
        st.session_state.ai_generator = AIGenerator(config_manager)
    ai_gen = st.session_state.ai_generator


    st.markdown("---")

    # Выбор провайдера по умолчанию — теперь только два
    available_providers = ["agentplatform", "deepseek"]
    current_default = config_manager.config.get("default_provider", "agentplatform")

    default_provider = st.selectbox(
        "Провайдер по умолчанию:",
        available_providers,
        index=available_providers.index(current_default) if current_default in available_providers else 0
    )

    if default_provider != config_manager.config.get("default_provider"):
        config_manager.set_default_provider(default_provider)
        st.success(f"Провайдер по умолчанию изменен на {default_provider}")

    # Вкладки для двух провайдеров
    tabs = st.tabs(["AgentPlatform", "DeepSeek", "📚 Пользовательские модели"])

    # --- Вкладка AgentPlatform ---
    with tabs[0]:
        provider = "agentplatform"
        provider_config = config_manager.get_provider_config(provider) or {}

        st.subheader("Настройки AgentPlatform")
        st.caption("Единый сервис для OpenAI, Anthropic, Google Gemini, Mistral и др. через https://api.agentplatform.ru/v1")

        # API ключ
        api_key = st.text_input(
            "API ключ AgentPlatform:",
            value=provider_config.get("api_key", ""),
            type="password",
            key="agentplatform_api_key"
        )

        # Получаем список стандартных моделей
        default_models_dict = ai_gen.get_available_models(provider)  # {"openai/gpt-4o": "OpenAI GPT-4o", ...}
        standard_ids = list(default_models_dict.keys())
        custom_ids = config_manager.get_custom_models()

        # Объединяем: сначала стандартные, потом пользовательские
        all_model_ids = standard_ids + custom_ids

        # Формируем отображаемые названия
        model_display = []
        for mid in all_model_ids:
            if mid in default_models_dict:
                model_display.append(default_models_dict[mid])
            else:
                model_display.append(f"📌 {mid} (пользовательская)")

        # Добавляем опцию ручного ввода
        custom_option = "__custom__"
        all_model_ids.append(custom_option)
        model_display.append("🔧 Другая (ввести название модели)")

        # Текущая модель из конфига
        current_model = provider_config.get("model", "openai/gpt-4o")
        if current_model in all_model_ids:
            default_index = all_model_ids.index(current_model)
        else:
            # Если текущей модели нет в списке, выбираем ручной ввод
            default_index = len(all_model_ids) - 1

        selected_display = st.selectbox(
            "Модель:",
            model_display,
            index=default_index,
            key="agentplatform_model_select"
        )
        selected_index = model_display.index(selected_display)
        selected_model_key = all_model_ids[selected_index]

        # Обработка выбора
        if selected_model_key == custom_option:
            col_input, col_add = st.columns([4, 1])
            with col_input:
                model = st.text_input(
                    "Введите название модели (например, anthropic/claude-3-haiku):",
                    value=current_model if current_model not in all_model_ids else "",
                    key="agentplatform_custom_model"
                )
            with col_add:
                if st.button("➕ Добавить в список", key=f"add_custom_from_input_{provider}"):
                    if model and config_manager.add_custom_model(model):
                        st.success(f"Модель '{model}' добавлена в пользовательские!")
                        st.rerun()
            if not model:
                model = current_model
        else:
            model = selected_model_key
        st.markdown("---")
        st.subheader("🧠 Системный промпт (роль AI)")

        current_system_prompt = provider_config.get("system_prompt", "Ты - опытный технический копирайтер и SEO-специалист.")

        system_prompt = st.text_area(
            "Инструкция для AI:",
            value=current_system_prompt,
            height=150,
            key="agentplatform_system_prompt",
            help="Этот промпт определяет роль и поведение AI. Будет отправляться в каждом запросе как system message."
        )

        col_reset, col_empty = st.columns([1, 5])
        with col_reset:
            if st.button("↺ Сбросить к стандартному", key="reset_agentplatform_prompt"):
                default_prompt = "Ты - опытный технический копирайтер и SEO-специалист."
                st.session_state.agentplatform_system_prompt = default_prompt
                st.rerun()

        st.markdown("---")

        # Параметры генерации (общие для всех)
        col1, col2 = st.columns(2)
        with col1:
            temperature = st.slider(
                "Temperature:",
                min_value=0.0, max_value=2.0,
                value=float(provider_config.get("temperature", 0.7)),
                step=0.1,
                key="agentplatform_temp"
            )
            max_tokens = st.number_input(
                "Max Tokens:",
                min_value=100, max_value=16384,
                value=int(provider_config.get("max_tokens", 2000)),
                key="agentplatform_tokens"
            )
        with col2:
            top_p = st.slider(
                "Top P:",
                min_value=0.0, max_value=1.0,
                value=float(provider_config.get("top_p", 0.9)),
                step=0.01,
                key="agentplatform_top_p"
            )
            frequency_penalty = st.slider(
                "Frequency Penalty:",
                min_value=-2.0, max_value=2.0,
                value=float(provider_config.get("frequency_penalty", 0.0)),
                step=0.1,
                key="agentplatform_freq"
            )
            presence_penalty = st.slider(
                "Presence Penalty:",
                min_value=-2.0, max_value=2.0,
                value=float(provider_config.get("presence_penalty", 0.0)),
                step=0.1,
                key="agentplatform_pres"
            )

        # Кнопка сохранения
        if st.button("💾 Сохранить настройки AgentPlatform", key="save_agentplatform"):
            new_config = {
                "api_key": api_key.strip(),
                "model": model,
                "system_prompt": system_prompt,  # <-- ДОБАВЛЕНО
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty
            }
            if config_manager.update_provider_config(provider, new_config):
                st.success("Настройки AgentPlatform сохранены!")
            else:
                st.error("Ошибка при сохранении настроек AgentPlatform")

    # --- Вкладка DeepSeek ---
    with tabs[1]:
        provider = "deepseek"
        provider_config = config_manager.get_provider_config(provider) or {}

        st.subheader("Настройки DeepSeek")
        st.caption("Прямое API DeepSeek (https://api.deepseek.com)")

        # API ключ
        api_key = st.text_input(
            "API ключ DeepSeek:",
            value=provider_config.get("api_key", ""),
            type="password",
            key="deepseek_api_key"
        )

        # Модели DeepSeek (фиксированный список)
        models = ["deepseek-chat", "deepseek-coder"]
        current_model = provider_config.get("model", "deepseek-chat")
        if current_model not in models:
            models.append(current_model)  # добавляем нестандартную, если была
        model = st.selectbox(
            "Модель:",
            models,
            index=models.index(current_model) if current_model in models else 0,
            key="deepseek_model"
        )

        # ===== СИСТЕМНЫЙ ПРОМПТ =====
        st.markdown("---")
        st.subheader("🧠 Системный промпт (роль AI)")

        current_system_prompt = provider_config.get("system_prompt", "Ты - опытный технический копирайтер и SEO-специалист.")

        system_prompt = st.text_area(
            "Инструкция для AI:",
            value=current_system_prompt,
            height=150,
            key="deepseek_system_prompt",
            help="Этот промпт определяет роль и поведение AI. Будет отправляться в каждом запросе как system message."
        )

        col_reset, col_empty = st.columns([1, 5])
        with col_reset:
            if st.button("↺ Сбросить к стандартному", key="reset_deepseek_prompt"):
                default_prompt = "Ты - опытный технический копирайтер и SEO-специалист."
                st.session_state.deepseek_system_prompt = default_prompt
                st.rerun()

        st.markdown("---")


        # Параметры генерации
        col1, col2 = st.columns(2)
        with col1:
            temperature = st.slider(
                "Temperature:",
                min_value=0.0, max_value=2.0,
                value=float(provider_config.get("temperature", 0.7)),
                step=0.1,
                key="deepseek_temp"
            )
            max_tokens = st.number_input(
                "Max Tokens:",
                min_value=100, max_value=8192,
                value=int(provider_config.get("max_tokens", 2000)),
                key="deepseek_tokens"
            )
        with col2:
            top_p = st.slider(
                "Top P:",
                min_value=0.0, max_value=1.0,
                value=float(provider_config.get("top_p", 0.9)),
                step=0.01,
                key="deepseek_top_p"
            )
            frequency_penalty = st.slider(
                "Frequency Penalty:",
                min_value=-2.0, max_value=2.0,
                value=float(provider_config.get("frequency_penalty", 0.0)),
                step=0.1,
                key="deepseek_freq"
            )
            presence_penalty = st.slider(
                "Presence Penalty:",
                min_value=-2.0, max_value=2.0,
                value=float(provider_config.get("presence_penalty", 0.0)),
                step=0.1,
                key="deepseek_pres"
            )

        # Кнопка сохранения
        if st.button("💾 Сохранить настройки DeepSeek", key="save_deepseek"):
            new_config = {
                "api_key": api_key.strip(),
                "model": model,
                "system_prompt": system_prompt,  # <-- ДОБАВЛЕНО
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty
            }
            if config_manager.update_provider_config(provider, new_config):
                st.success("Настройки DeepSeek сохранены!")
            else:
                st.error("Ошибка при сохранении настроек DeepSeek")
    with tabs[2]:
        st.subheader("Управление пользовательскими моделями для AgentPlatform")
        st.caption("Добавьте свои модели, которые будут доступны в выпадающем списке при выборе провайдера AgentPlatform.")

        custom_models = config_manager.get_custom_models()

        # Форма добавления новой модели
        with st.form(key="add_custom_model_form"):
            new_model = st.text_input("Название новой модели (например, 'openai/gpt-4-turbo')")
            if st.form_submit_button("➕ Добавить модель"):
                if new_model.strip():
                    if config_manager.add_custom_model(new_model.strip()):
                        st.success(f"Модель '{new_model}' добавлена!")
                        st.rerun()
                    else:
                        st.error("Модель уже существует или не удалось сохранить.")
                else:
                    st.warning("Введите название модели.")

        st.divider()

        # Список существующих моделей с редактированием и удалением
        if custom_models:
            st.write("**Сохранённые модели:**")
            for i, model in enumerate(custom_models):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"`{model}`")
                with col2:
                    if st.button("✏️", key=f"edit_custom_{i}", help="Редактировать"):
                        st.session_state[f"editing_custom_{i}"] = model
                with col3:
                    if st.button("🗑️", key=f"del_custom_{i}", help="Удалить"):
                        if config_manager.delete_custom_model(model):
                            st.success(f"Модель '{model}' удалена")
                            st.rerun()

                # Редактирование модели
                if st.session_state.get(f"editing_custom_{i}") == model:
                    with st.form(key=f"edit_form_{i}"):
                        new_name = st.text_input("Новое название", value=model)
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.form_submit_button("💾 Сохранить"):
                                if config_manager.update_custom_model(model, new_name.strip()):
                                    st.success("Обновлено!")
                                    del st.session_state[f"editing_custom_{i}"]
                                    st.rerun()
                        with col_cancel:
                            if st.form_submit_button("Отмена"):
                                del st.session_state[f"editing_custom_{i}"]
                                st.rerun()
        else:
            st.info("Пока нет пользовательских моделей. Добавьте первую с помощью формы выше.")

    # --- Общие ограничения запросов ---
    st.markdown("---")
    st.subheader("⏱️ Ограничения запросов (общие для всех провайдеров)")
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        delay = st.number_input(
            "Задержка между запросами (сек):",
            min_value=0.5, max_value=10.0,
            value=float(config_manager.config["rate_limit"]["delay_between_requests"]),
            step=0.5,
            key="global_delay"
        )
    with col_r2:
        requests_per_minute = st.number_input(
            "Запросов в минуту:",
            min_value=1, max_value=60,
            value=int(config_manager.config["rate_limit"]["requests_per_minute"]),
            key="global_rpm"
        )
    if st.button("💾 Сохранить общие ограничения"):
        config_manager.config["rate_limit"]["delay_between_requests"] = delay
        config_manager.config["rate_limit"]["requests_per_minute"] = requests_per_minute
        config_manager.save_config()
        st.success("Ограничения сохранены")

    # --- Тестовый вызов API ---
    with st.expander("🧪 Тестовый вызов API"):
        test_prompt = st.text_area(
            "Тестовый промпт:",
            value="Привет! Ответь одним предложением.",
            height=100,
            key="test_prompt"
        )

        # Выбор провайдера для теста (из двух)
        test_provider = st.selectbox(
            "Провайдер для теста:",
            available_providers,
            index=available_providers.index(default_provider),
            key="test_provider"
        )

        if st.button("Отправить тестовый запрос"):
            # Используем сохранённый ai_generator (уже есть в session_state)
            with st.spinner("Отправка запроса..."):
                # Для теста используем стандартный вызов без model_override — будет взята модель из конфига
                result = ai_gen.generate_instruction(
                    test_prompt,
                    {},
                    provider=test_provider,
                    num_variants=1
                )[0]

                if result["success"]:
                    st.success("✅ Запрос успешен!")
                    st.text_area("Ответ AI:", value=result["text"], height=150, key="test_response")
                    if "usage" in result and result["usage"]:
                        usage = result["usage"]
                        st.caption(
                            f"Токены: {usage.get('total_tokens', 0)} "
                            f"(prompt: {usage.get('prompt_tokens', 0)}, "
                            f"completion: {usage.get('completion_tokens', 0)})"
                        )
                else:
                    st.error(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")


if __name__ == "__main__":
    show_ai_config_interface()