# auto/autopilot_logger.py
import streamlit as st
from datetime import datetime

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