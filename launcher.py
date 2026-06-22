def _migrate_templates_from_project_to_domain(self):
    """Переносит шаблоны из старых проектов в домен (однократно)"""
    # Проверяем, делали ли уже миграцию
    if st.session_state.get('_templates_migrated', False):
        return

    # Загружаем старые проекты
    projects_data = st.session_state.app_data.get('phase7_projects_data', {})

    for project_id, project_data in projects_data.items():
        old_templates = project_data.get('templates', {})
        if old_templates:
            # Определяем категорию из проекта
            category_code = project_data.get('category_code', 'default')

            # Сохраняем в домен (default, так как старые проекты без привязки к домену)
            self.dm.save_templates(old_templates, category_code, domain_name='default')

            # Удаляем шаблоны из проекта
            project_data.pop('templates', None)

    st.session_state._templates_migrated = True
    self.save_data_to_app_state()