# autopilot.py
import streamlit as st
import time
from typing import Dict
from datetime import datetime
from auto.autopilot_logger import add_autopilot_log


def request_autopilot_for_phase(phase: int):
    """Запрашивает запуск автопилота для фазы (вызывается при переходе)"""
    if 'autopilot_config' not in st.session_state:
        return

    config = st.session_state.autopilot_config

    if not config.get('enabled', False):
        return

    if phase not in config.get('active_phases', []):
        return

    phase_config = config.get('phases', {}).get(phase, {})
    if not phase_config.get('auto_enabled', False):
        return

    config[f'autopilot_requested_for_phase_{phase}'] = True
    st.session_state.autopilot_config = config
    add_autopilot_log(phase, f"Запрошен запуск автопилота при входе в фазу {phase}", 'info')


class AutoPilotManager:
    """Центральный менеджер автопилота"""

    def __init__(self):
        self.init_config()

    def init_config(self):
        if 'autopilot_config' not in st.session_state:
            default_phase3 = st.session_state.get('autopilot_default_phase3', {})

            st.session_state.autopilot_config = {
                'enabled': False,
                'active_phases': [3, 4, 5, 6],
                'stop_on_error': True,
                'max_errors': 5,
                'notification_method': 'toast',
                'phases': {
                    3: {
                        'auto_enabled': True,
                        'auto_proceed': True,
                        'config': {
                            'provider': default_phase3.get('provider', 'agentplatform'),
                            'selection_mode': default_phase3.get('selection_mode', 'all'),
                            'selected_variables': default_phase3.get('selected_variables', []),
                            'retry_on_error': default_phase3.get('retry_on_error', False),
                            'max_retries': default_phase3.get('max_retries', 3),
                            'auto_continue_on_partial': default_phase3.get('auto_continue_on_partial', True),
                            'auto_continue_on_error': default_phase3.get('auto_continue_on_error', True)
                        }
                    },
                    4: {
                        'auto_enabled': True,
                        'auto_proceed': True,
                        'config': {
                            'default_regular_prompts': 3,
                            'default_unique_prompts': 3,
                            'default_other_prompts': 20,
                            'individual_char_settings': {},
                            'other_blocks_settings': {}
                        }
                    },
                    5: {
                        'auto_enabled': True,
                        'auto_proceed': True,
                        'config': {
                            'generation_mode': 'all',
                            'parallel': False,
                            'timeout': 30
                        }
                    },
                    6: {
                        'auto_enabled': True,
                        'auto_proceed': False,
                        'config': {
                            'analysis_type': 'full',
                            'auto_export': True
                        }
                    }
                },
                'errors': [],
                'current_phase_running': False
            }

    def is_enabled_for_phase(self, phase: int) -> bool:
        config = st.session_state.autopilot_config
        return (config['enabled'] and
                phase in config['active_phases'] and
                config['phases'].get(phase, {}).get('auto_enabled', False) and
                not config.get('current_phase_running', False))

    def start_phase(self, phase: int):
        config = st.session_state.autopilot_config
        config['current_phase_running'] = True
        config['current_phase'] = phase
        st.session_state.autopilot_config = config

    def finish_phase(self, phase: int, success: bool):
        config = st.session_state.autopilot_config
        config['current_phase_running'] = False

        if success:
            if config['phases'][phase].get('auto_proceed', True):
                st.session_state.current_phase = phase + 1
        else:
            config['enabled'] = False

        st.session_state.autopilot_config = config

    def add_error(self, phase: int, error_msg: str, context: Dict = None):
        config = st.session_state.autopilot_config
        config['errors'].append({
            'phase': phase,
            'error': error_msg,
            'context': context,
            'timestamp': datetime.now().isoformat()
        })
        add_autopilot_log(phase, f"Ошибка: {error_msg[:100]}", 'error')
        if config['notification_method'] == 'toast':
            st.toast(f"⚠️ Ошибка в фазе {phase}: {error_msg[:50]}...", icon="⚠️")
        elif config['notification_method'] == 'error':
            st.error(f"⚠️ Ошибка в фазе {phase}: {error_msg}")

        phase_errors = [e for e in config['errors'] if e['phase'] == phase]
        if len(phase_errors) >= config['max_errors']:
            st.error(f"❌ Превышен лимит ошибок ({config['max_errors']}) в фазе {phase}. Автопилот остановлен.")
            config['enabled'] = False

        st.session_state.autopilot_config = config

    def get_phase_config(self, phase: int) -> Dict:
        return st.session_state.autopilot_config['phases'].get(phase, {}).get('config', {})


def show_autopilot_panel():
    """Отображает панель управления автопилотом в sidebar"""
    if 'autopilot_config' not in st.session_state:
        AutoPilotManager().init_config()

    config = st.session_state.autopilot_config

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🤖 Автопилот")

    enabled = st.sidebar.toggle(
        "Включить автопилот",
        value=config['enabled'],
        help="Автоматически выполнять действия в выбранных фазах"
    )

    if enabled != config['enabled']:
        config['enabled'] = enabled
        st.session_state.autopilot_config = config
        st.rerun()

    if config['enabled']:
        st.sidebar.markdown("**Активные фазы:**")
        cols = st.sidebar.columns(6)
        for i, col in enumerate(cols, 1):
            with col:
                if i in [1, 2]:
                    st.markdown(f"<small style='color:gray'>⚫{i}</small>", unsafe_allow_html=True)
                else:
                    is_active = i in config['active_phases']
                    color = "🟢" if is_active else "⚪"
                    if st.button(f"{color}{i}", key=f"phase_{i}_toggle", help=f"Фаза {i}"):
                        if is_active:
                            config['active_phases'].remove(i)
                        else:
                            config['active_phases'].append(i)
                        st.session_state.autopilot_config = config
                        st.rerun()

        if config.get('current_phase_running', False):
            st.sidebar.info(f"🔄 Выполняется фаза {config.get('current_phase', '?')}")

        error_count = len(config['errors'])
        if error_count > 0:
            st.sidebar.warning(f"⚠️ Ошибок: {error_count}")

        if st.sidebar.button("🔄 Сбросить автопилот", use_container_width=True):
            config['enabled'] = False
            config['current_phase_running'] = False
            config['errors'] = []
            st.session_state.autopilot_config = config
            st.rerun()


def is_autopilot_active_for_phase(phase: int) -> bool:
    """Проверяет, активен ли автопилот для конкретной фазы"""
    if 'autopilot_config' not in st.session_state:
        return False

    config = st.session_state.autopilot_config

    if not config.get('enabled', False):
        return False

    if phase not in config.get('active_phases', []):
        return False

    phase_config = config.get('phases', {}).get(phase, {})
    if not phase_config.get('auto_enabled', False):
        return False

    if config.get(f'phase_{phase}_completed', False):
        return False

    return True


def reset_autopilot_for_phase(phase: int):
    """Сбрасывает флаги выполнения для фазы (при возврате на фазу)"""
    if 'autopilot_config' in st.session_state:
        config = st.session_state.autopilot_config
        config[f'phase_{phase}_completed'] = False
        config['current_phase_running'] = False
        if config.get('current_phase') == phase:
            config['current_phase'] = None
        st.session_state.autopilot_config = config
        add_autopilot_log(phase, f"Сброс автопилота для фазы {phase}", 'info')


def start_autopilot_for_phase(phase: int):
    """Запускает автопилот для фазы (вызывается при входе)"""
    if 'autopilot_config' not in st.session_state:
        return False

    config = st.session_state.autopilot_config

    if not is_autopilot_active_for_phase(phase):
        return False

    config['current_phase_running'] = True
    config['current_phase'] = phase
    st.session_state.autopilot_config = config

    add_autopilot_log(phase, f"Запуск автопилота для фазы {phase}", 'info')
    return True


def finish_autopilot_for_phase(phase: int, success: bool):
    """Завершает автопилот для фазы (без rerun, только установка флагов)"""
    if 'autopilot_config' not in st.session_state:
        return

    config = st.session_state.autopilot_config

    flag_name = f'autopilot_requested_for_phase_{phase}'
    if flag_name in config:
        config[flag_name] = False

    config['current_phase_running'] = False
    config['current_phase'] = None

    if success:
        config[f'phase_{phase}_completed'] = True
        add_autopilot_log(phase, f"✅ Фаза {phase} успешно завершена", 'success')
    else:
        config[f'phase_{phase}_completed'] = False
        add_autopilot_log(phase, f"❌ Фаза {phase} завершена с ошибками", 'error')
        if config.get('stop_on_error', True):
            config['enabled'] = False
            add_autopilot_log(phase, "⛔ Автопилот остановлен", 'warning')

    st.session_state.autopilot_config = config


def is_autopilot_ready_for_phase(phase: int) -> bool:
    """Проверяет, готов ли автопилот к запуску на фазе"""
    if 'autopilot_config' not in st.session_state:
        return False

    config = st.session_state.autopilot_config

    if not config.get('enabled', False):
        return False

    if phase not in config.get('active_phases', []):
        return False

    phase_config = config.get('phases', {}).get(phase, {})
    if not phase_config.get('auto_enabled', False):
        return False

    if config.get(f'phase_{phase}_completed', False):
        return False

    if config.get('current_phase_running', False):
        return False

    return True


def consume_autopilot_request(phase: int) -> bool:
    """Проверяет и снимает флаг запроса на автопилот"""
    if 'autopilot_config' not in st.session_state:
        return False

    config = st.session_state.autopilot_config
    flag_name = f'autopilot_requested_for_phase_{phase}'

    if config.get(flag_name, False):
        config[flag_name] = False
        st.session_state.autopilot_config = config
        add_autopilot_log(phase, f"Потреблён запрос на автопилот для фазы {phase}", 'debug')
        return True

    return False


def disable_autopilot_for_phase(phase: int):
    """Отключает автопилот для конкретной фазы"""
    if 'autopilot_config' in st.session_state:
        config = st.session_state.autopilot_config
        if phase in config.get('active_phases', []):
            config['active_phases'].remove(phase)
        if phase in config.get('phases', {}):
            config['phases'][phase]['auto_enabled'] = False
        st.session_state.autopilot_config = config
        add_autopilot_log(phase, "Автопилот отключен пользователем", 'info')


def get_autopilot_status() -> dict:
    """Возвращает статус автопилота"""
    if 'autopilot_config' not in st.session_state:
        return {'enabled': False, 'active_phases': [], 'running': False}

    config = st.session_state.autopilot_config
    return {
        'enabled': config.get('enabled', False),
        'active_phases': config.get('active_phases', []),
        'running': config.get('current_phase_running', False),
        'current_phase': config.get('current_phase', None)
    }


def run_autopilot_phase3():
    """Автоматическое выполнение фазы 3 – только генерация, возвращает True/False"""
    import traceback
    from phases.phase3 import get_all_ai_variables_with_details, batch_generate_for_characteristic, batch_generate_for_other, BlockManager

    add_autopilot_log(3, "🚀 Запуск автопилота для фазы 3", 'info')
    st.info("🤖 Автопилот: автоматическая генерация AI-инструкций...")

    try:
        ai_vars_details = get_all_ai_variables_with_details()
        if not ai_vars_details:
            add_autopilot_log(3, "Нет AI переменных", 'warning')
            return True

        config = st.session_state.autopilot_config
        phase3_config = config.get('phases', {}).get(3, {}).get('config', {})
        selection_mode = phase3_config.get('selection_mode', 'all')
        selected_vars_keys = phase3_config.get('selected_variables', [])
        provider = phase3_config.get('provider', 'agentplatform')

        filtered_vars = []
        for block_name, var_name, block_id, var_data in ai_vars_details:
            var_key = f"{block_id}|{var_name}"
            if selection_mode == 'all' or var_key in selected_vars_keys:
                filtered_vars.append((block_id, var_name, block_name, var_data))

        if not filtered_vars:
            add_autopilot_log(3, "Нет выбранных переменных", 'warning')
            return True

        if 'block_manager' not in st.session_state:
            st.session_state.block_manager = BlockManager()
        block_manager = st.session_state.block_manager

        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, (block_id, var_name, block_name, var_data) in enumerate(filtered_vars):
            status_text.text(f"Генерация {idx+1}/{len(filtered_vars)}: {block_name} / {var_name}")
            block = block_manager.get_block(block_id)
            if not block:
                continue
            try:
                if block.get('block_type') == 'characteristic':
                    batch_generate_for_characteristic(block_id, var_name, var_data, block, provider=provider)
                else:
                    batch_generate_for_other(block_id, var_name, var_data, block, provider=provider)
            except Exception as e:
                add_autopilot_log(3, f"Ошибка {block_name}/{var_name}: {str(e)}", 'error')
            progress_bar.progress((idx+1)/len(filtered_vars))

        progress_bar.empty()
        status_text.empty()
        st.success("✅ Автопилот завершил генерацию!")

    except Exception as e:
        add_autopilot_log(3, f"Критическая ошибка: {str(e)}", 'error')
        st.error(f"Критическая ошибка: {e}")
        st.code(traceback.format_exc())
        return False
    st.query_params["force_phase"] = "4"
    st.rerun()
    return True


def run_autopilot_for_current_phase():
    """Запускает автопилот для текущей фазы"""
    current = st.session_state.current_phase
    if current == 3:
        return run_autopilot_phase3()
    elif current == 4:
        st.warning("Автопилот для фазы 4 пока не реализован")
        return False
    elif current == 5:
        st.info("Автопилот для фазы 5 пока не реализован")
        return False
    elif current == 6:
        st.info("Автопилот для фазы 6 пока не реализован")
        return False
    return False