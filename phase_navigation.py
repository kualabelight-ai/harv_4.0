# phase_navigation.py
"""
Единая система навигации по фазам
"""
import streamlit as st
from datetime import datetime

PHASE_ICONS = ["📦", "🏷️", "📝", "🚀", "📄", "🔄", "📊"]
PHASE_TITLES = ["Сбор", "Маркеры", "Блоки", "Промпты", "Тексты", "Синонимы", "Анализ"]

def render_phase_navigation(app_state, context=None):
    st.markdown("### Навигация")
    phase_cols = st.columns(7)

    for i, col in enumerate(phase_cols, 1):
        with col:
            phase_data = st.session_state.app_data.get(f'phase{i}', {})
            is_completed = bool(phase_data)
            is_active = i == st.session_state.current_phase

            if is_active:
                bg = "#f0e6d2"
                border = "2px solid #b08968"
            elif is_completed:
                bg = "#e6f0da"
                border = "1px solid #7f9f6f"
            else:
                bg = "#f5f0e6"
                border = "1px solid #d4c3a2"

            st.markdown(f"""
            <div style="background-color: {bg}; border: {border}; border-radius: 8px; padding: 8px 4px; text-align: center; margin-bottom: 5px;">
                <div style="font-size: 24px;">{PHASE_ICONS[i-1]}</div>
                <div style="font-size: 12px; font-weight: bold;">{PHASE_TITLES[i-1]}</div>
                <div style="font-size: 10px; color: #5e4b3c;">Фаза {i}</div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("▶", key=f"nav_phase_{i}", use_container_width=True):
                if _can_access_phase(i):
                    st.session_state.current_phase = i
                    app_state.save_project()
                    st.rerun()

    st.markdown("---")
    st.markdown(f"## Фаза {st.session_state.current_phase}: {PHASE_TITLES[st.session_state.current_phase-1]}")

    if not _check_phase_prerequisites():
        return False

    _render_navigation_buttons(app_state, context)
    return True

def render_phase_content(app_state, context=None):
    """Рендерит содержимое текущей фазы"""
    try:
        if st.session_state.current_phase == 1:
            import phases.phase1 as phase1
            phase1.main(app_state=app_state, context=context)  # ← ДОБАВИЛИ context
        elif st.session_state.current_phase == 2:
            import phases.phase2 as phase2
            phase2.main(app_state=app_state, context=context)  # ← ДОБАВИЛИ context
        elif st.session_state.current_phase == 3:
            import phases.phase3 as phase3
            phase3.main(app_state=app_state, context=context)  # ← ДОБАВИЛИ context
        elif st.session_state.current_phase == 4:
            import phases.phase4 as phase4
            phase4.main(app_state=app_state, context=context)  # ← ДОБАВИЛИ context
        elif st.session_state.current_phase == 5:
            import phases.phase5 as phase5
            phase5.main(app_state=app_state, context=context)  # ← ДОБАВИЛИ context
        elif st.session_state.current_phase == 6:
            import phases.phase6 as phase6
            phase6.main(app_state=app_state, context=context)  # ← ДОБАВИЛИ context
        elif st.session_state.current_phase == 7:
            import phases.phase7 as phase7
            phase7.main(app_state=app_state, context=context)  # ← ДОБАВИЛИ context

        app_state.save_project()
    except Exception as e:
        st.error(f"Ошибка загрузки фазы: {e}")
        import traceback
        st.code(traceback.format_exc())

def _can_access_phase(phase_num: int) -> bool:
    """Проверяет, можно ли перейти к указанной фазе"""
    if phase_num >= 2 and not st.session_state.app_data.get('phase1'):
        st.warning("⚠️ Сначала выполните фазу 1")
        return False
    elif phase_num >= 3 and not st.session_state.app_data.get('phase2'):
        st.warning("⚠️ Сначала выполните фазу 2")
        return False
    elif phase_num >= 4:
        phase3_data = st.session_state.app_data.get('phase3', {})
        blocks = phase3_data.get('blocks', {})
        if not blocks:
            st.warning("⚠️ Сначала выполните фазу 3 (создайте хотя бы один блок)")
            return False
    elif phase_num >= 5 and not st.session_state.app_data.get('phase4'):
        st.warning("⚠️ Сначала выполните фазу 4")
        return False
    elif phase_num >= 6 and not st.session_state.app_data.get('phase5'):
        st.warning("⚠️ Сначала выполните фазу 5")
        return False
    elif phase_num >= 7 and not st.session_state.app_data.get('phase6'):
        st.warning("⚠️ Сначала выполните фазу 6")
        return False

    return True

def _check_phase_prerequisites() -> bool:
    """Проверяет предусловия для текущей фазы"""
    current = st.session_state.current_phase

    if current >= 2 and not st.session_state.app_data.get('phase1'):
        st.warning("⚠️ Сначала выполните фазу 1")
        if st.button("← Перейти к фазе 1"):
            st.session_state.current_phase = 1
            st.rerun()
        return False
    elif current >= 3 and not st.session_state.app_data.get('phase2'):
        st.warning("⚠️ Сначала выполните фазу 2")
        if st.button("← Перейти к фазе 2"):
            st.session_state.current_phase = 2
            st.rerun()
        return False
    elif current >= 4 and not st.session_state.app_data.get('phase3'):
        st.warning("⚠️ Сначала выполните фазу 3")
        if st.button("← Перейти к фазе 3"):
            st.session_state.current_phase = 3
            st.rerun()
        return False
    elif current >= 5 and not st.session_state.app_data.get('phase4'):
        st.warning("⚠️ Сначала выполните фазу 4")
        if st.button("← Перейти к фазе 4"):
            st.session_state.current_phase = 4
            st.rerun()
        return False
    elif current >= 6 and not st.session_state.app_data.get('phase5'):
        st.warning("⚠️ Сначала выполните фазу 5")
        if st.button("← Перейти к фазе 5"):
            st.session_state.current_phase = 5
            st.rerun()
        return False
    elif current >= 7 and not st.session_state.app_data.get('phase6'):
        st.warning("⚠️ Сначала выполните фазу 6")
        if st.button("← Перейти к фазе 6"):
            st.session_state.current_phase = 6
            st.rerun()
        return False

    return True

def _render_navigation_buttons(app_state, context=None):

    """Рендерит кнопки навигации"""
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])

    with col_nav1:
        if st.session_state.current_phase > 1:
            if st.button("← Предыдущая фаза", use_container_width=True):
                st.session_state.current_phase -= 1
                app_state.save_project()
                st.rerun()

    current = st.session_state.current_phase
    can_proceed = _can_proceed_to_next_phase()

    with col_nav3:
        if current < 7:
            if can_proceed:
                if st.button("Следующая фаза →", type="primary", use_container_width=True):
                    st.session_state.current_phase += 1
                    app_state.save_project()
                    st.rerun()
            else:
                _show_next_phase_warning(current)

def _can_proceed_to_next_phase() -> bool:
    """Определяет, можно ли перейти к следующей фазе"""
    current = st.session_state.current_phase

    if current == 1:
        return bool(st.session_state.app_data.get('phase1'))
    elif current == 2:
        return bool(st.session_state.app_data.get('phase1') and st.session_state.app_data.get('phase2'))
    elif current == 3:
        phase3_data = st.session_state.app_data.get('phase3', {})
        blocks = phase3_data.get('blocks', {})
        return len(blocks) > 0
    elif current == 4:
        phase4_data = st.session_state.app_data.get('phase4', {})
        prompts = phase4_data.get('prompts', [])
        return len(prompts) > 0 or bool(st.session_state.get('phase4_generated_prompts'))
    elif current == 5:
        phase5_data = st.session_state.app_data.get('phase5', {})
        return bool(phase5_data.get('results'))
    else:
        return True

def _show_next_phase_warning(current_phase: int):
    """Показывает предупреждение"""
    warnings = {
        3: "⚠️ Создайте хотя бы один блок в фазе 3",
        4: "⚠️ Сгенерируйте промпты в фазе 4",
        5: "⚠️ Сгенерируйте тексты в фазе 5",
        6: "⚠️ Выполните синонимизацию в фазе 6",
    }
    if current_phase in warnings:
        st.info(warnings[current_phase])