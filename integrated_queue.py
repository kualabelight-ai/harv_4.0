# integrated_queue.py
import streamlit as st
from queue_system import CategoryQueueManager, TaskType, TaskStatus
import asyncio
from typing import List, Dict, Any
import threading
import json
# Глобальный менеджер очередей
_queue_manager = None

def get_queue_manager():
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = CategoryQueueManager(max_parallel_categories=3)
        _register_handlers(_queue_manager)
    return _queue_manager

def _register_handlers(manager: CategoryQueueManager):
    """Регистрирует обработчики для разных типов задач"""

    async def handle_data_collection(task):
        """Обработчик сбора данных"""
        # Здесь ваша логика сбора данных
        from phases import phase1
        # Запускаем асинхронно
        result = await asyncio.to_thread(phase1.process_data, task.config)
        return result

    async def handle_prompt_generation(task):
        """Обработчик генерации промптов"""
        from phases import phase4
        result = await asyncio.to_thread(phase4.generate_prompts, task.config)
        return result

    async def handle_text_generation(task):
        """Обработчик генерации текстов"""
        from phases import phase5
        result = await asyncio.to_thread(phase5.generate_texts, task.config)
        return result

    manager.register_handler(TaskType.DATA_COLLECTION, handle_data_collection)
    manager.register_handler(TaskType.PROMPT_GENERATION, handle_prompt_generation)
    manager.register_handler(TaskType.TEXT_GENERATION, handle_text_generation)

def start_background_processing():
    """Запускает фоновую обработку очередей"""
    manager = get_queue_manager()

    async def process_all_categories():
        while True:
            # Обрабатываем все активные категории
            for category in list(manager.categories.keys()):
                if category not in manager.active_categories:
                    asyncio.create_task(manager.process_category(category))
            await asyncio.sleep(1)  # Проверяем каждую секунду

    # Запускаем в фоновом потоке
    def run_async_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_all_categories())

    thread = threading.Thread(target=run_async_loop, daemon=True)
    thread.start()

# UI Компоненты для отображения очередей
def show_queue_status():
    """Отображает статус всех очередей"""
    manager = get_queue_manager()

    st.markdown("## 📋 Очереди задач")

    if not manager.categories:
        st.info("Нет активных очередей")
        return

    # Создаем вкладки для каждой категории
    categories = list(manager.categories.keys())
    tabs = st.tabs([f"📁 {cat}" for cat in categories])

    for tab, category in zip(tabs, categories):
        with tab:
            status = manager.get_category_status(category)
            queue = manager.categories[category]

            # Статус категории
            col1, col2, col3 = st.columns(3)
            with col1:
                mode = "🤖 Авто" if queue.is_auto_mode else "✋ Ручной"
                st.metric("Режим", mode)
            with col2:
                st.metric("В очереди", status['total_tasks'])
            with col3:
                st.metric("Ручных", status['manual_tasks'])

            # Переключатель режима
            if st.button(f"🔄 Переключить режим для {category}"):
                new_mode = not queue.is_auto_mode
                manager.switch_mode(category, new_mode)
                st.rerun()

            # Текущая задача
            if queue.current_task:
                with st.expander("🔄 Текущая задача", expanded=True):
                    task = queue.current_task
                    st.info(f"**{task.task_type.value}** - Фаза {task.phase}")
                    st.progress(0.5)  # Здесь нужен реальный прогресс

            # Очередь задач
            if status['pending_tasks']:
                with st.expander("📋 Очередь задач", expanded=False):
                    for task_info in status['pending_tasks']:
                        st.text(f"• {task_info['type']} (Фаза {task_info['phase']})")

            # Ручные задачи
            if queue.manual_tasks:
                st.warning("⚠️ Задачи требующие ручного вмешательства")
                for task in queue.manual_tasks:
                    with st.expander(f"❌ {task.task_type.value} - {task.task_id[:8]}"):
                        st.error(f"Ошибка: {task.error}")
                        if st.button("✏️ Исправить", key=f"fix_{task.task_id}"):
                            st.session_state.manual_task = task
                            st.rerun()

def show_manual_task_editor():
    """Отображает редактор для ручного исправления задачи"""
    if 'manual_task' not in st.session_state:
        return

    task = st.session_state.manual_task

    st.markdown("## 🔧 Ручное исправление задачи")
    st.info(f"**Тип:** {task.task_type.value}\n**Фаза:** {task.phase}\n**Ошибка:** {task.error}")

    # Здесь показываем конфиг для редактирования
    st.markdown("### Конфигурация задачи")

    # Пример для разных типов задач
    corrected_config = {}

    if task.task_type == TaskType.DATA_COLLECTION:
        corrected_config['file_path'] = st.text_input(
            "Путь к файлу",
            value=task.config.get('file_path', '')
        )
        corrected_config['settings'] = st.text_area(
            "Настройки",
            value=json.dumps(task.config.get('settings', {}), indent=2)
        )

    elif task.task_type == TaskType.PROMPT_GENERATION:
        corrected_config['prompt_template'] = st.text_area(
            "Шаблон промпта",
            value=task.config.get('prompt_template', '')
        )
        corrected_config['parameters'] = st.multiselect(
            "Параметры",
            options=task.config.get('parameters', []),
            default=task.config.get('parameters', [])
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Отправить на обработку", type="primary"):
            manager = get_queue_manager()
            manager.resolve_manual_task(
                task.config.get('category', 'default'),
                task.task_id,
                corrected_config
            )
            del st.session_state.manual_task
            st.success("Задача отправлена на повторную обработку")
            st.rerun()

    with col2:
        if st.button("❌ Отмена"):
            del st.session_state.manual_task
            st.rerun()

def add_batch_tasks(category: str, user_id: int, project_id: str, tasks_config: List[Dict[str, Any]]):
    """Добавляет несколько задач в очередь"""
    manager = get_queue_manager()

    for config in tasks_config:
        task_id = manager.add_task(
            category=category,
            user_id=user_id,
            project_id=project_id,
            task_type=config['type'],
            phase=config['phase'],
            config=config['data'],
            priority=config.get('priority', 0)
        )

        # Сохраняем связь task_id с проектом
        if 'batch_tasks' not in st.session_state:
            st.session_state.batch_tasks = {}
        st.session_state.batch_tasks[task_id] = {
            'project_id': project_id,
            'category': category,
            'status': 'pending'
        }

    st.success(f"✅ Добавлено {len(tasks_config)} задач в очередь для категории {category}")

def add_background_task(category: str, user_id: int, project_id: str, task_type, phase: int, config: dict) -> str:
    """Добавляет фоновую задачу"""
    manager = get_queue_manager()

    task_id = manager.add_task(
        category=category,
        user_id=user_id,
        project_id=project_id,
        task_type=task_type,
        phase=phase,
        config=config
    )

    from project_manager import ProjectManager
    pm = ProjectManager(user_id)
    pm.update_project_task_status(project_id, task_id, 'pending', 0)

    return task_id

def get_active_tasks_for_user(user_id: int) -> list:
    """Возвращает все активные задачи пользователя"""
    manager = get_queue_manager()
    active_tasks = []

    for category, queue in manager.categories.items():
        if queue.user_id != user_id:
            continue

        if queue.current_task:
            active_tasks.append({
                'category': category,
                'project_id': queue.project_id,
                'task_id': queue.current_task.task_id,
                'task_type': queue.current_task.task_type.value,
                'phase': queue.current_task.phase,
                'status': 'processing',
                'progress': getattr(queue.current_task, 'progress', 0),
                'message': getattr(queue.current_task, 'status_message', 'Обработка...')
            })

        for task in queue.tasks[:5]:
            active_tasks.append({
                'category': category,
                'project_id': queue.project_id,
                'task_id': task.task_id,
                'task_type': task.task_type.value,
                'phase': task.phase,
                'status': 'pending',
                'progress': 0,
                'message': 'В очереди'
            })

        for task in queue.manual_tasks:
            active_tasks.append({
                'category': category,
                'project_id': queue.project_id,
                'task_id': task.task_id,
                'task_type': task.task_type.value,
                'phase': task.phase,
                'status': 'manual_required',
                'progress': 0,
                'message': f'Ошибка: {task.error[:50] if task.error else "Неизвестная ошибка"}...'
            })

    return active_tasks