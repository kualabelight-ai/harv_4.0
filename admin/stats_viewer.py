# admin/stats_viewer.py - ПОЛНОСТЬЮ ЗАМЕНИТЬ ФАЙЛ

import streamlit as st
from datetime import datetime, timedelta
from database_settings.database import get_db
import pandas as pd
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")

def render_stats_viewer():
    """Детальная статистика использования API"""

    st.subheader("📊 Статистика использования API")
    st.markdown("---")

    # Период
    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox(
            "Период",
            ["Сегодня", "Вчера", "Последние 7 дней", "Последние 30 дней", "За всё время"],
            key="stats_period_select"
        )

    # Определяем дату начала
    if period == "Сегодня":
        date_condition = f"date(l.created_at) = date('now')"
    elif period == "Вчера":
        date_condition = f"date(l.created_at) = date('now', '-1 day')"
    elif period == "Последние 7 дней":
        date_condition = f"l.created_at > date('now', '-7 days')"
    elif period == "Последние 30 дней":
        date_condition = f"l.created_at > date('now', '-30 days')"
    else:
        date_condition = "1=1"

    with get_db() as conn:
        # Общая статистика
        stats = conn.execute(f"""
            SELECT 
                COUNT(*) as total_requests,
                SUM(CASE WHEN l.success = 1 THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN l.success = 0 THEN 1 ELSE 0 END) as failed,
                SUM(l.total_tokens) as total_tokens,
                SUM(l.estimated_cost) as total_cost,
                AVG(l.request_duration_ms) as avg_duration
            FROM api_usage_logs l
            WHERE {date_condition}
        """).fetchone()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего запросов", stats["total_requests"] or 0)
        with col2:
            st.metric("Успешных", stats["successful"] or 0)
        with col3:
            st.metric("Ошибок", stats["failed"] or 0)
        with col4:
            st.metric("Всего токенов", f"{stats['total_tokens'] or 0:,}")

        col5, col6 = st.columns(2)
        with col5:
            st.metric("Примерная стоимость", f"${stats['total_cost'] or 0:.4f}")
        with col6:
            st.metric("Среднее время", f"{stats['avg_duration'] or 0:.0f} мс")

    st.markdown("---")

    # Статистика по провайдерам
    st.subheader("По провайдерам")

    with get_db() as conn:
        provider_stats = conn.execute(f"""
            SELECT 
                l.provider,
                COUNT(*) as requests,
                SUM(l.total_tokens) as tokens,
                SUM(l.estimated_cost) as cost
            FROM api_usage_logs l
            WHERE {date_condition}
            GROUP BY l.provider
            ORDER BY requests DESC
        """).fetchall()

    if provider_stats:
        for stat in provider_stats:
            st.write(f"**{stat['provider']}:** {stat['requests']} запросов, {stat['tokens']:,} токенов, ${stat['cost']:.4f}")
    else:
        st.info("Нет данных")

    st.markdown("---")

    # Статистика по пользователям
    st.subheader("По пользователям")

    with get_db() as conn:
        user_stats = conn.execute(f"""
            SELECT 
                u.username,
                COUNT(l.id) as requests,
                SUM(l.total_tokens) as tokens,
                SUM(l.estimated_cost) as cost
            FROM api_usage_logs l
            JOIN users u ON l.user_id = u.id
            WHERE {date_condition}
            GROUP BY l.user_id
            ORDER BY tokens DESC
            LIMIT 20
        """).fetchall()

    if user_stats:
        user_data = []
        for stat in user_stats:
            user_data.append({
                "Пользователь": stat["username"],
                "Запросов": stat["requests"],
                "Токенов": f"{stat['tokens']:,}",
                "Стоимость": f"${stat['cost']:.4f}"
            })
        st.dataframe(user_data, use_container_width=True)
    else:
        st.info("Нет данных")

    st.markdown("---")

    # Статистика по доменам
    st.subheader("По доменам")

    with get_db() as conn:
        domain_stats = conn.execute(f"""
            SELECT 
                l.site_name,
                l.domain_name,
                COUNT(*) as requests,
                SUM(l.total_tokens) as tokens
            FROM api_usage_logs l
            WHERE {date_condition}
            GROUP BY l.site_name, l.domain_name
            ORDER BY requests DESC
            LIMIT 20
        """).fetchall()

    if domain_stats:
        domain_data = []
        for stat in domain_stats:
            domain_data.append({
                "Сайт": stat["site_name"],
                "Домен": stat["domain_name"],
                "Запросов": stat["requests"],
                "Токенов": f"{stat['tokens']:,}"
            })
        st.dataframe(domain_data, use_container_width=True)
    else:
        st.info("Нет данных")

    st.markdown("---")

    # Статистика по дням (график в табличном виде)
    st.subheader("Статистика по дням")

    with get_db() as conn:
        daily_stats = conn.execute(f"""
            SELECT 
                date(l.created_at) as date,
                COUNT(*) as requests,
                SUM(l.total_tokens) as tokens,
                SUM(CASE WHEN l.success = 1 THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN l.success = 0 THEN 1 ELSE 0 END) as failed
            FROM api_usage_logs l
            WHERE {date_condition}
            GROUP BY date(l.created_at)
            ORDER BY date DESC
            LIMIT 30
        """).fetchall()

    if daily_stats:
        daily_data = []
        for stat in daily_stats:
            daily_data.append({
                "Дата": stat["date"],
                "Запросов": stat["requests"],
                "Токенов": f"{stat['tokens']:,}",
                "Успешно": stat["successful"],
                "Ошибок": stat["failed"]
            })
        st.dataframe(daily_data, use_container_width=True)
    else:
        st.info("Нет данных")

    st.markdown("---")

    # Последние запросы
    st.subheader("Последние 100 запросов")

    with get_db() as conn:
        recent = conn.execute(f"""
            SELECT 
                l.created_at,
                u.username,
                l.provider,
                l.model,
                l.total_tokens,
                l.request_duration_ms,
                l.success,
                l.error_message
            FROM api_usage_logs l
            JOIN users u ON l.user_id = u.id
            WHERE {date_condition}
            ORDER BY l.created_at DESC
            LIMIT 100
        """).fetchall()

    if recent:
        recent_data = []
        for row in recent:
            recent_data.append({
                "Время": row["created_at"][:19] if row["created_at"] else "",
                "Пользователь": row["username"],
                "Провайдер": row["provider"],
                "Модель": row["model"],
                "Токенов": row["total_tokens"],
                "Время (мс)": row["request_duration_ms"],
                "Статус": "✅" if row["success"] else "❌",
                "Ошибка": (row["error_message"][:50] + "...") if row["error_message"] and len(row["error_message"]) > 50 else (row["error_message"] or "")
            })
        st.dataframe(recent_data, use_container_width=True)
    else:
        st.info("Нет данных")