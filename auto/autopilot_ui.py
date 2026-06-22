# autopilot_ui.py
import streamlit as st
from datetime import datetime
from auto.autopilot import AutoPilotManager


def add_autopilot_log(phase: int, message: str, level: str = 'info'):
    """Добавляет запись в лог автопилота"""
    if 'autopilot_log' not in st.session_state:
        st.session_state.autopilot_log = []

    st.session_state.autopilot_log.append({
        'phase': phase,
        'message': message,
        'level': level,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


def show_autopilot_modal():
    """Показывает модальное окно с настройками автопилота"""

    if not st.session_state.get('show_autopilot_modal', False):
        return

    # Инициализируем конфиг, если его нет
    if 'autopilot_config' not in st.session_state:
        AutoPilotManager().init_config()

    with st.expander("🤖 НАСТРОЙКИ АВТОПИЛОТА", expanded=True):
        st.markdown("---")

        config = st.session_state.autopilot_config

        # Основной переключатель
        col1, col2 = st.columns([1, 3])
        with col1:
            enabled = st.toggle(
                "🔛 Включить автопилот",
                value=config.get('enabled', False),
                help="Включить автоматическое выполнение операций"
            )
            if enabled != config.get('enabled'):
                config['enabled'] = enabled
                st.session_state.autopilot_config = config

        with col2:
            if config.get('enabled', False):
                st.success("✅ Автопилот активен")
            else:
                st.info("⏸️ Автопилот отключен. Настройки доступны для конфигурации.")

        st.markdown("---")

        # Вкладки настроек
        tab_main, tab_phases, tab_errors, tab_log = st.tabs([
            "🎛️ Основные", "⚙️ Фазы", "⚠️ Ошибки", "📋 Лог"
        ])

        # === ВКЛАДКА 1: ОСНОВНЫЕ НАСТРОЙКИ ===
        with tab_main:
            st.markdown("### 🌍 Глобальные настройки")

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                config['stop_on_error'] = st.checkbox(
                    "⛔ Останавливать при любой ошибке",
                    value=config.get('stop_on_error', True),
                    help="При возникновении ошибки автопилот остановится и запросит ручное вмешательство"
                )

                config['max_errors'] = st.number_input(
                    "📊 Максимум ошибок до остановки",
                    min_value=1, max_value=20, value=config.get('max_errors', 5),
                    help="При превышении этого лимита автопилот отключится"
                )

            with col_g2:
                config['notification_method'] = st.selectbox(
                    "🔔 Способ уведомлений",
                    ['toast', 'modal', 'sidebar', 'none'],
                    index=['toast', 'modal', 'sidebar', 'none'].index(config.get('notification_method', 'toast')),
                    format_func=lambda x: {
                        'toast': 'Всплывающее уведомление',
                        'modal': 'Модальное окно',
                        'sidebar': 'В боковую панель',
                        'none': 'Без уведомлений'
                    }.get(x, x)
                )

                config['auto_refresh'] = st.checkbox(
                    "🔄 Авто-обновление статуса",
                    value=config.get('auto_refresh', True)
                )

            st.markdown("---")
            st.markdown("### 📊 Текущий статус")

            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                active_phases = config.get('active_phases', [])
                st.metric("Активные фазы", ", ".join(map(str, active_phases)) if active_phases else "нет")

            with col_s2:
                errors_count = len(config.get('errors', []))
                st.metric("Ошибок за сессию", errors_count)

            with col_s3:
                is_running = config.get('current_phase_running', False)
                st.metric("Состояние", "🏃 Работает" if is_running else "💤 Ожидание")

            st.markdown("---")
            st.markdown("### 🔧 Управление")

            col_reset1, col_reset2 = st.columns(2)
            with col_reset1:
                if st.button("🔄 Сбросить флаги выполнения фаз", use_container_width=True):
                    for key in list(config.keys()):
                        if key.startswith('phase_') and key.endswith('_completed'):
                            config[key] = False
                    config['current_phase_running'] = False
                    config['current_phase'] = None
                    st.session_state.autopilot_config = config
                    st.success("✅ Флаги сброшены!")
                    st.rerun()

            with col_reset2:
                if st.button("🗑️ Очистить лог ошибок", use_container_width=True):
                    config['errors'] = []
                    st.session_state.autopilot_config = config
                    st.success("✅ Лог ошибок очищен!")
                    st.rerun()

        # === ВКЛАДКА 2: НАСТРОЙКИ ФАЗ ===
        with tab_phases:
            st.markdown("### ⚙️ Настройка фаз автоматизации")
            st.caption("Фазы 1-2 всегда выполняются вручную. Фазы 3-6 можно автоматизировать.")

            # ФАЗА 3
            with st.expander("📝 ФАЗА 3: Редактирование блоков (AI переменные)", expanded=True):
                phase3_config = config['phases'].get(3, {})
                phase3_config.setdefault('config', {})
                phase3_config.setdefault('auto_enabled', True)
                phase3_config.setdefault('auto_proceed', True)

                col_p3_1, col_p3_2, col_p3_3 = st.columns(3)

                with col_p3_1:
                    phase3_config['auto_enabled'] = st.checkbox(
                        "🤖 Автоматизировать фазу 3",
                        value=phase3_config.get('auto_enabled', True),
                        key="phase3_auto"
                    )

                with col_p3_2:
                    phase3_config['auto_proceed'] = st.checkbox(
                        "➡️ Авто-переход к фазе 4",
                        value=phase3_config.get('auto_proceed', True),
                        key="phase3_auto_proceed"
                    )

                with col_p3_3:
                    if phase3_config.get('auto_enabled'):
                        if 3 not in config['active_phases']:
                            if st.button("➕ Добавить фазу 3 в активные", key="add_phase3"):
                                config['active_phases'].append(3)
                                st.rerun()
                    else:
                        if 3 in config['active_phases']:
                            if st.button("➖ Убрать фазу 3 из активных", key="remove_phase3"):
                                config['active_phases'].remove(3)
                                st.rerun()

                if phase3_config.get('auto_enabled'):
                    st.markdown("**Настройки генерации AI:**")

                    col_p3_a, col_p3_b = st.columns(2)
                    with col_p3_a:
                        phase3_config['config']['provider'] = st.selectbox(
                            "🤖 Провайдер AI",
                            ['agentplatform', 'deepseek'],
                            index=0 if phase3_config['config'].get('provider') == 'agentplatform' else 1,
                            format_func=lambda x: {
                                'agentplatform': 'AgentPlatform (OpenAI/Anthropic/Google/Mistral и др.)',
                                'deepseek': 'DeepSeek (прямой доступ)'
                            }.get(x, x),
                            key="phase3_provider"
                        )

                    with col_p3_b:
                        phase3_config['config']['selection_mode'] = st.radio(
                            "📋 Выбор переменных",
                            ['all', 'selected'],
                            format_func=lambda x: 'Все AI переменные' if x == 'all' else 'Только выбранные',
                            horizontal=True,
                            key="phase3_selection"
                        )

                    st.markdown("**⚙️ Поведение при ошибках:**")
                    col_err1, col_err2 = st.columns(2)
                    with col_err1:
                        phase3_config['config']['auto_continue_on_partial'] = st.checkbox(
                            "✅ Автоматически продолжать при частичных результатах",
                            value=phase3_config['config'].get('auto_continue_on_partial', True)
                        )
                    with col_err2:
                        phase3_config['config']['auto_continue_on_error'] = st.checkbox(
                            "⚠️ Продолжать даже при полных ошибках",
                            value=phase3_config['config'].get('auto_continue_on_error', False)
                        )

                    col_retry1, col_retry2 = st.columns(2)
                    with col_retry1:
                        phase3_config['config']['retry_on_error'] = st.checkbox(
                            "🔄 Повторять при ошибке",
                            value=phase3_config['config'].get('retry_on_error', True)
                        )
                    with col_retry2:
                        if phase3_config['config'].get('retry_on_error'):
                            phase3_config['config']['max_retries'] = st.number_input(
                                "📊 Макс повторов",
                                min_value=1, max_value=5, value=phase3_config['config'].get('max_retries', 3)
                            )

                    if phase3_config['config'].get('selection_mode') == 'selected':
                        st.markdown("**Выберите AI переменные для автоматической генерации:**")

                        if 'block_manager' not in st.session_state:
                            from phases.phase3 import BlockManager
                            st.session_state.block_manager = BlockManager()
                        else:
                            # Перезагружаем блоки на всякий случай
                            st.session_state.block_manager.load_blocks()

                        from phases.phase3 import get_all_ai_variables_with_details
                        ai_vars_list = get_all_ai_variables_with_details()

                        if ai_vars_list:
                            selected_vars = phase3_config['config'].get('selected_variables', [])
                            for block_name, var_name, block_id, var_data in ai_vars_list:
                                var_key = f"{block_id}|{var_name}"
                                is_selected = var_key in selected_vars

                                checked = st.checkbox(
                                    f"**{block_name}** / `{var_name}`",
                                    value=is_selected,
                                    key=f"auto_select_{block_id}_{var_name}"
                                )

                                if checked and var_key not in selected_vars:
                                    selected_vars.append(var_key)
                                elif not checked and var_key in selected_vars:
                                    selected_vars.remove(var_key)

                            phase3_config['config']['selected_variables'] = selected_vars

                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                if st.button("✅ Выбрать все", key="select_all_phase3"):
                                    phase3_config['config']['selected_variables'] = [f"{b_id}|{v_name}" for b_name, v_name, b_id, _ in ai_vars_list]
                                    st.rerun()
                            with col_btn2:
                                if st.button("❌ Снять все", key="deselect_all_phase3"):
                                    phase3_config['config']['selected_variables'] = []
                                    st.rerun()
                        else:
                            st.warning("⚠️ AI переменные не найдены. Сначала создайте AI переменные в блоках (Фаза 3 → вкладка «Редактирование блока» → AI).")


                config['phases'][3] = phase3_config

            # ФАЗА 4
            with st.expander("🚀 ФАЗА 4: Генерация промптов", expanded=True):
                phase4_config = config['phases'].get(4, {})
                phase4_config.setdefault('config', {})
                phase4_config.setdefault('auto_enabled', True)
                phase4_config.setdefault('auto_proceed', True)

                col_p4_1, col_p4_2 = st.columns(2)
                with col_p4_1:
                    auto_enabled = st.checkbox(
                        "🤖 Автоматизировать фазу 4",
                        value=phase4_config.get('auto_enabled', True),
                        key="phase4_auto_enabled"
                    )
                    phase4_config['auto_enabled'] = auto_enabled

                    auto_proceed = st.checkbox(
                        "➡️ Авто-переход к фазе 5",
                        value=phase4_config.get('auto_proceed', True),
                        key="phase4_auto_proceed"
                    )
                    phase4_config['auto_proceed'] = auto_proceed

                with col_p4_2:
                    if auto_enabled:
                        if 4 not in config['active_phases']:
                            if st.button("➕ Добавить фазу 4 в активные", key="add_phase4"):
                                config['active_phases'].append(4)
                                st.rerun()
                        else:
                            st.success("✅ Фаза 4 активна для автопилота")
                    else:
                        if 4 in config['active_phases']:
                            if st.button("➖ Убрать фазу 4 из активных", key="remove_phase4"):
                                config['active_phases'].remove(4)
                                st.rerun()
                        else:
                            st.info("ℹ️ Фаза 4 не активна для автопилота")

                if st.button("🔄 Сбросить статус фазы 4 (разрешить повторный запуск)", use_container_width=True):
                    config['phase_4_completed'] = False
                    config['autopilot_requested_for_phase_4'] = False
                    st.session_state.autopilot_config = config
                    st.success("✅ Статус фазы 4 сброшен")
                    st.rerun()

                config['phases'][4] = phase4_config

            # ФАЗА 5
            with st.expander("📄 ФАЗА 5: Генерация текстов", expanded=False):
                phase5_config = config['phases'].get(5, {})
                phase5_config.setdefault('auto_enabled', True)
                phase5_config.setdefault('auto_proceed', True)

                col_p5_1, col_p5_2 = st.columns(2)
                with col_p5_1:
                    phase5_config['auto_enabled'] = st.checkbox(
                        "🤖 Автоматизировать фазу 5",
                        value=phase5_config.get('auto_enabled', True),
                        key="phase5_auto"
                    )
                with col_p5_2:
                    phase5_config['auto_proceed'] = st.checkbox(
                        "➡️ Авто-переход к фазе 6",
                        value=phase5_config.get('auto_proceed', True),
                        key="phase5_proceed"
                    )

                config['phases'][5] = phase5_config

            # ФАЗА 6
            with st.expander("📊 ФАЗА 6: Анализ и экспорт", expanded=False):
                phase6_config = config['phases'].get(6, {})
                phase6_config.setdefault('auto_enabled', True)
                phase6_config.setdefault('auto_proceed', False)

                col_p6_1, col_p6_2 = st.columns(2)
                with col_p6_1:
                    phase6_config['auto_enabled'] = st.checkbox(
                        "🤖 Автоматизировать фазу 6",
                        value=phase6_config.get('auto_enabled', True),
                        key="phase6_auto"
                    )
                with col_p6_2:
                    phase6_config['auto_proceed'] = st.checkbox(
                        "➡️ Авто-завершение",
                        value=phase6_config.get('auto_proceed', False),
                        key="phase6_proceed"
                    )

                config['phases'][6] = phase6_config

            st.session_state.autopilot_config = config

        # === ВКЛАДКА 3: НАСТРОЙКИ ОШИБОК ===
        with tab_errors:
            st.markdown("### ⚠️ Настройки обработки ошибок")

            col_e1, col_e2 = st.columns(2)
            with col_e1:
                config['stop_on_error'] = st.checkbox(
                    "🛑 Остановить автопилот при ошибке",
                    value=config.get('stop_on_error', True),
                    key="global_stop_on_error"
                )

                config['log_errors'] = st.checkbox(
                    "📝 Сохранять лог ошибок",
                    value=config.get('log_errors', True),
                    key="log_errors"
                )

            with col_e2:
                config['max_errors'] = st.number_input(
                    "⚠️ Лимит ошибок для остановки",
                    min_value=1, max_value=20, value=config.get('max_errors', 5),
                    key="global_max_errors"
                )

                config['retry_strategy'] = st.selectbox(
                    "🔄 Стратегия повторов",
                    ['exponential', 'linear', 'none'],
                    format_func=lambda x: {
                        'exponential': 'Экспоненциальная (2,4,8 сек)',
                        'linear': 'Линейная (2,2,2 сек)',
                        'none': 'Без повторов'
                    }.get(x, x),
                    key="retry_strategy"
                )

            st.markdown("---")
            st.markdown("### 📋 Текущие ошибки")

            errors = config.get('errors', [])
            if errors:
                for err in errors[-10:]:
                    st.error(f"**Фаза {err.get('phase')}**: {err.get('error')[:200]}")
                    st.caption(f"Время: {err.get('timestamp')}")
                    if err.get('context'):
                        with st.expander("Контекст ошибки"):
                            st.json(err.get('context'))
                    st.markdown("---")
            else:
                st.success("✅ Ошибок не зафиксировано")

        # === ВКЛАДКА 4: ЛОГ ДЕЙСТВИЙ ===
        with tab_log:
            st.markdown("### 📋 Лог действий автопилота")

            if 'autopilot_log' not in st.session_state:
                st.session_state.autopilot_log = []

            log = st.session_state.autopilot_log

            if log:
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    level_filter = st.multiselect(
                        "Уровень",
                        ['info', 'success', 'warning', 'error'],
                        default=['info', 'success', 'warning', 'error']
                    )
                with col_f2:
                    phase_filter = st.multiselect(
                        "Фаза",
                        [1, 2, 3, 4, 5, 6],
                        default=[1, 2, 3, 4, 5, 6]
                    )

                filtered_log = [
                    entry for entry in log
                    if entry.get('level') in level_filter and entry.get('phase') in phase_filter
                ]

                for entry in filtered_log[-50:]:
                    if entry.get('level') == 'error':
                        st.error(f"**Фаза {entry.get('phase')}**: {entry.get('message')}")
                    elif entry.get('level') == 'warning':
                        st.warning(f"**Фаза {entry.get('phase')}**: {entry.get('message')}")
                    elif entry.get('level') == 'success':
                        st.success(f"**Фаза {entry.get('phase')}**: {entry.get('message')}")
                    else:
                        st.info(f"**Фаза {entry.get('phase')}**: {entry.get('message')}")

                    st.caption(f"🕐 {entry.get('timestamp', '')}")
                    st.markdown("---")

                if st.button("🗑️ Очистить лог", use_container_width=True):
                    st.session_state.autopilot_log = []
                    st.rerun()
            else:
                st.info("Лог пуст")

        # Кнопки управления
        st.markdown("---")
        col_btn1, col_btn2, col_btn3 = st.columns(3)

        with col_btn1:
            if st.button("💾 Сохранить настройки", type="primary", use_container_width=True):
                st.session_state.autopilot_config = config
                st.success("✅ Настройки сохранены!")
                st.rerun()

        with col_btn2:
            if st.button("🔄 Сбросить все", use_container_width=True):
                AutoPilotManager().init_config()
                st.success("✅ Настройки сброшены!")
                st.rerun()

        with col_btn3:
            if st.button("❌ Закрыть", use_container_width=True):
                st.session_state.show_autopilot_modal = False
                st.rerun()