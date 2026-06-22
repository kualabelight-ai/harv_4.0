# utils/project_utils.py
def regenerate_phase(phase: int):
    """Перегенерировать конкретную фазу проекта"""
    app_state = AppState()

    # Очищаем данные фазы и всех последующих
    for p in range(phase, 7):
        if f'phase{p}' in st.session_state.app_data:
            st.session_state.app_data[f'phase{p}'] = {}

    st.session_state.current_phase = phase
    app_state.save_project()
    st.success(f"🔄 Данные фазы {phase} и последующих очищены. Можно начать заново.")
    st.rerun()

def merge_projects(source_project_id: str, target_project_id: str):
    """Объединяет данные из одного проекта в другой"""
    pm = ProjectManager(st.session_state.user_id)

    source = pm.load_project_data(source_project_id)
    target = pm.load_project_data(target_project_id)

    if source and target:
        # Объединяем данные фаз
        for phase in range(1, 7):
            if source.get(f'phase{phase}') and not target.get(f'phase{phase}'):
                target[f'phase{phase}'] = source[f'phase{phase}']

        # Сохраняем результат
        pm.save_project_data(target_project_id, target)
        return True
    return False