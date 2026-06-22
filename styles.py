# styles.py
import streamlit as st

def init_theme():
    """Инициализация темы в session_state"""
    if 'theme' not in st.session_state:
        st.session_state.theme = 'light'

def toggle_theme():
    """Переключение темы"""
    st.session_state.theme = 'dark' if st.session_state.theme == 'light' else 'light'

def get_theme_colors():
    """Возвращает цвета для текущей темы"""
    if st.session_state.theme == 'light':
        return {
            'bg': '#faf7f2',
            'bg_secondary': '#f5f0e6',
            'text': '#3e3a36',
            'text_secondary': '#5e4b3c',
            'border': '#d4c3a2',
            'border_dark': '#b7a99a',
            'hover': '#e6dacd',
            'accent': '#b08968',
            'accent_light': '#d4c3a2',
            'success': '#7f9f6f',
            'warning': '#e6b89c',
            'info': '#8d9f87',
            'error': '#c62828',
            'card_bg': '#f5f0e6',
            'card_hover': '#ede5d9',
            'highlight_bg': '#90EE90',  # Добавлено для подсветки
            'highlight_hover': '#6BCB6B',  # Добавлено для подсветки
        }
    else:
        return {
            'bg': '#1a1a1a',
            'bg_secondary': '#2d2d2d',
            'text': '#e0e0e0',
            'text_secondary': '#b0b0b0',
            'border': '#404040',
            'border_dark': '#505050',
            'hover': '#3d3d3d',
            'accent': '#c49a6c',
            'accent_light': '#8c7a6a',
            'success': '#4caf50',
            'warning': '#ffb74d',
            'info': '#4fc3f7',
            'error': '#ef5350',
            'card_bg': '#2d2d2d',
            'card_hover': '#3d3d3d',
            'highlight_bg': '#2e5c2e',  # Темно-зеленый для темной темы
            'highlight_hover': '#3d7a3d',  # Добавлено для подсветки
        }

def load_css():
    """Загрузка CSS с поддержкой темы"""
    init_theme()
    colors = get_theme_colors()

    st.markdown(f"""
    <style>
        /* ========== БАЗОВЫЙ СТИЛЬ С ПОДДЕРЖКОЙ ТЕМЫ ========== */
        .stApp {{
            background-color: {colors['bg']} !important;
            color: {colors['text']} !important;
        }}

        /* Типографика */
        h1, h2, h3, h4, h5, h6, .stMarkdown, .stText, label, span, p, div {{
            color: {colors['text']} !important;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
            line-height: 1.5;
        }}
        
        h1, h2, h3, h4, h5, h6 {{
            color: {colors['text_secondary']} !important;
            font-family: 'Courier New', monospace;
        }}

        h1 {{ font-size: 2rem; font-weight: 500; margin-bottom: 1rem; }}
        h2 {{ font-size: 1.5rem; font-weight: 500; margin-bottom: 0.75rem; }}
        h3 {{ font-size: 1.25rem; font-weight: 500; margin-bottom: 0.5rem; }}

        /* ========== ПОДСВЕТКА ЗАМЕН (ДОБАВЛЕНО ИЗ PHASE6) ========== */
        .replacement-highlight {{
            background-color: {colors['highlight_bg']} !important;
            padding: 2px 4px !important;
            border-radius: 4px !important;
            font-weight: bold !important;
            cursor: help !important;
            transition: all 0.2s !important;
            display: inline-block !important;
            color: {colors['text']} !important;
        }}
        .replacement-highlight:hover {{
            background-color: {colors['highlight_hover']} !important;
            transform: scale(1.02) !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        }}
        
        /* ========== КОНТЕЙНЕРЫ ДЛЯ ТЕКСТОВ (ДОБАВЛЕНО ИЗ PHASE6) ========== */
        .text-container {{
            background-color: {colors['bg_secondary']} !important;
            padding: 15px !important;
            border-radius: 8px !important;
            border: 1px solid {colors['border']} !important;
            max-height: 300px !important;
            overflow-y: auto !important;
            font-family: 'Courier New', monospace !important;
            font-size: 14px !important;
            line-height: 1.6 !important;
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            color: {colors['text']} !important;
        }}

        /* ========== КНОПКА ПЕРЕКЛЮЧЕНИЯ ТЕМЫ ========== */
        .theme-toggle {{
            position: fixed !important;
            top: 1rem !important;
            right: 1rem !important;
            z-index: 9999 !important;
            background: {colors['bg_secondary']} !important;
            border: 1px solid {colors['border']} !important;
            border-radius: 50% !important;
            width: 40px !important;
            height: 40px !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
            font-size: 20px !important;
            background-color: {colors['bg_secondary']} !important;
        }}
        .theme-toggle:hover {{
            transform: scale(1.05) !important;
            background: {colors['hover']} !important;
            border-color: {colors['accent']} !important;
        }}
        .theme-toggle:active {{
            transform: scale(0.95) !important;
        }}

        /* ========== КНОПКИ ========== */
        .stButton > button {{
            background-color: {colors['bg_secondary']} !important;
            color: {colors['text']} !important;
            border: 1px solid {colors['border']} !important;
            border-radius: 6px !important;
            font-size: 14px !important;
            padding: 6px 16px !important;
            font-family: inherit !important;
            font-weight: 400 !important;
            transition: all 0.15s ease !important;
            box-shadow: none !important;
        }}
        .stButton > button:hover {{
            background-color: {colors['hover']} !important;
            border-color: {colors['border_dark']} !important;
            color: {colors['text']} !important;
        }}

        /* ========== ПОЛЯ ВВОДА ========== */
        .stTextInput > div > div > input,
        .stNumberInput > div > div > input,
        .stTextArea > div > textarea,
        .stSelectbox > div > div > div,
        .stMultiselect > div > div,
        .stDateInput > div > div > input,
        .stTimeInput > div > div > input {{
            background-color: {colors['bg']} !important;
            border: 1px solid {colors['border']} !important;
            border-radius: 4px !important;
            color: {colors['text']} !important;
            font-family: inherit !important;
            padding: 0.5rem 0.75rem !important;
            box-shadow: none !important;
        }}
        
        .stTextInput > div > div > input:focus,
        .stNumberInput > div > div > input:focus,
        .stTextArea > div > textarea:focus {{
            border-color: {colors['accent']} !important;
            box-shadow: 0 0 0 2px rgba(176, 137, 104, 0.2) !important;
            outline: none !important;
        }}

        /* ========== ЧЕКБОКСЫ / РАДИО ========== */
        .stCheckbox > label,
        .stRadio > label {{
            color: {colors['text_secondary']} !important;
            font-family: 'Courier New', monospace !important;
        }}

        /* ========== СЛАЙДЕРЫ ========== */
        .stSlider > div > div > div {{
            background-color: {colors['accent']} !important;
        }}
        .stSlider > div > div > div > div {{
            background-color: {colors['accent']} !important;
        }}

        /* ========== ТАБЛИЦЫ ========== */
        .stDataFrame th {{
            background-color: {colors['bg_secondary']} !important;
            color: {colors['text']} !important;
            border-bottom: 2px solid {colors['border']} !important;
        }}
        .stDataFrame td {{
            background-color: {colors['bg']} !important;
            border-bottom: 1px solid {colors['border']} !important;
            color: {colors['text']} !important;
        }}

        /* ========== АЛЕРТЫ ========== */
        div.stAlert, div.stSuccess, div.stWarning, div.stInfo, div.stError {{
            background-color: {colors['bg_secondary']} !important;
            border-left: 4px solid {colors['accent']} !important;
            color: {colors['text']} !important;
        }}
        div.stSuccess {{ border-left-color: {colors['success']} !important; }}
        div.stWarning {{ border-left-color: {colors['warning']} !important; }}
        div.stInfo {{ border-left-color: {colors['info']} !important; }}
        div.stError {{ border-left-color: {colors['error']} !important; }}

        /* ========== КАРТОЧКИ ========== */
        .mode-card {{
            background-color: {colors['card_bg']} !important;
            border-radius: 12px;
            padding: 30px;
            text-align: center;
            transition: all 0.3s ease;
            border: 2px solid {colors['border']};
        }}
        .mode-card:hover {{
            border-color: {colors['accent']};
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
            background-color: {colors['card_hover']} !important;
        }}

        /* ========== СТАТУСЫ ========== */
        .status-running {{ color: #3b82f6; font-weight: bold; }}
        .status-completed {{ color: {colors['success']}; font-weight: bold; }}
        .status-failed {{ color: {colors['error']}; font-weight: bold; }}
        .status-queued {{ color: #f59e0b; font-weight: bold; }}

        /* ========== ОСТАЛЬНЫЕ СТИЛИ ========== */
        hr {{
            border: none !important;
            border-top: 1px solid {colors['border']} !important;
            margin: 1.5rem 0 !important;
        }}

        .block-container {{
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
        }}
        
        /* Скрываем лишние элементы */
        span[data-testid="stIconMaterial"] {{
            display: none !important;
        }}
        
        header[data-testid="stHeader"] {{
            display: none !important;
        }}
    </style>
    """, unsafe_allow_html=True)

def render_theme_toggle():
    """Рендер фиксированной кнопки переключения темы"""
    init_theme()

    theme_icon = "🌙" if st.session_state.theme == 'light' else "☀️"

    # Используем компонент button с правильным ключом
    # Добавляем отступ сверху, чтобы кнопка не перекрывала контент
    st.markdown('<div style="height: 60px;"></div>', unsafe_allow_html=True)

    # Создаем колонки для позиционирования
    col1, col2, col3 = st.columns([10, 1, 0.5])

    with col3:
        if st.button(
                theme_icon,
                key="theme_toggle_global",
                help="Переключить тему",
                use_container_width=True
        ):
            toggle_theme()
            st.rerun()