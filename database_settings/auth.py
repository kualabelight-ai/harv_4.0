# database_settings/auth.py
import streamlit as st
import bcrypt
import pyotp
import qrcode
from io import BytesIO
import base64
import sqlite3
import time
from datetime import datetime, timedelta
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets

from database_settings.database import get_db, validate_session, create_session, delete_session, is_admin, hash_password, verify_password
from admin_queues import render_queues_admin_panel
from admin import dashboard, users_manager, api_keys_manager, projects_viewer, stats_viewer, audit_viewer
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
# Настройка логирования
logging.basicConfig(
    filename='login_attempts.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
from admin.backup_manager import render_backup_manager
# Конфигурация email (замените на свои данные или используйте st.secrets)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = st.secrets.get("email", {}).get("user", "your_email@gmail.com")
SMTP_PASSWORD = st.secrets.get("email", {}).get("password", "your_password")
FROM_EMAIL = SMTP_USER

# -------------------- Rate limiting --------------------
MAX_ATTEMPTS = 50
LOCKOUT_MINUTES = 1

def check_rate_limit(username: str) -> bool:
    """Проверяет, не заблокирован ли пользователь из-за множества неудачных попыток."""
    with get_db() as conn:
        user = conn.execute(
            "SELECT failed_attempts, locked_until FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if not user:
            return True

        if user["locked_until"]:
            locked_until = datetime.fromisoformat(user["locked_until"])
            if datetime.now() < locked_until:
                return False
            else:
                conn.execute(
                    "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
                    (username,)
                )
                conn.commit()
        return True

def record_failed_attempt(username: str):
    """Увеличивает счётчик неудач и блокирует при превышении лимита."""
    with get_db() as conn:
        user = conn.execute("SELECT failed_attempts FROM users WHERE username = ?", (username,)).fetchone()
        if user:
            attempts = user["failed_attempts"] + 1
            locked_until = None
            if attempts >= MAX_ATTEMPTS:
                locked_until = (datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
                logging.warning(f"User {username} locked until {locked_until}")
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                (attempts, locked_until, username)
            )
            conn.commit()

def reset_rate_limit(username: str):
    """Сбрасывает счётчик после успешного входа."""
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
            (username,)
        )
        conn.commit()

# -------------------- Логирование --------------------
def log_attempt(username: str, success: bool, ip: str = None):
    """Записывает попытку входа в лог-файл."""
    status = "SUCCESS" if success else "FAILURE"
    logging.info(f"Login attempt - User: {username} - Status: {status} - IP: {ip or 'unknown'}")

# -------------------- Аутентификация с 2FA --------------------
def authenticate_user(username: str, password: str, totp_code: str = None) -> tuple:
    """
    Проверяет логин/пароль и, если включена 2FA, проверяет код.
    Возвращает (success: bool, message: str, user_data: dict or None)
    """
    if not check_rate_limit(username):
        return False, "Слишком много попыток. Попробуйте позже.", None

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, password_hash, totp_secret, totp_enabled, status, banned FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if not user:
            record_failed_attempt(username)
            log_attempt(username, False)
            return False, "Неверное имя пользователя или пароль", None

        if not verify_password(password, user["password_hash"]):
            record_failed_attempt(username)
            log_attempt(username, False)
            return False, "Неверное имя пользователя или пароль", None

        if user["totp_enabled"]:
            if not totp_code:
                return False, "REQUIRE_2FA", dict(user)
            totp = pyotp.TOTP(user["totp_secret"])
            if not totp.verify(totp_code):
                record_failed_attempt(username)
                log_attempt(username, False)
                return False, "Неверный код двухфакторной аутентификации", None

        if user["status"] != "approved":
            log_attempt(username, False)
            return False, "Ваша учётная запись ещё не подтверждена администратором.", None

        if user["banned"]:
            log_attempt(username, False)
            return False, "Ваша учётная запись заблокирована администратором.", None

        reset_rate_limit(username)
        log_attempt(username, True)
        return True, "Успешный вход", dict(user)

# -------------------- 2FA управление --------------------
def generate_totp_secret() -> str:
    return pyotp.random_base32()

def get_totp_uri(username: str, secret: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="Data Harvester")

def generate_qr_base64(uri: str) -> str:
    qr = qrcode.make(uri)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def enable_2fa(user_id: int, secret: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET totp_secret = ?, totp_enabled = 1 WHERE id = ?",
            (secret, user_id)
        )
        conn.commit()

def disable_2fa(user_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET totp_enabled = 0 WHERE id = ?",
            (user_id,)
        )
        conn.commit()

# -------------------- Смена пароля --------------------
def change_password(user_id: int, old_password: str, new_password: str) -> tuple:
    with get_db() as conn:
        user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, "Пользователь не найден"

        if not verify_password(old_password, user["password_hash"]):
            return False, "Неверный текущий пароль"

        new_hash = hash_password(new_password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()
        logging.info(f"Password changed for user {user_id}")
        return True, "Пароль успешно изменён"

# -------------------- Восстановление пароля --------------------
def send_reset_email(email: str, token: str):
    reset_link = f"http://localhost:8501?reset_token={token}"
    subject = "Сброс пароля в Data Harvester"
    body = f"Для сброса пароля перейдите по ссылке: {reset_link}\n\nСсылка действительна 1 час."

    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        return False

def request_password_reset(email: str):
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            return False

        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
        conn.execute(
            "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user["id"], token, expires_at)
        )
        conn.commit()

        return send_reset_email(email, token)

def reset_password_with_token(token: str, new_password: str) -> bool:
    with get_db() as conn:
        reset = conn.execute(
            "SELECT user_id, expires_at FROM password_resets WHERE token = ?",
            (token,)
        ).fetchone()
        if not reset:
            return False

        if datetime.now() > datetime.fromisoformat(reset["expires_at"]):
            return False

        new_hash = hash_password(new_password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, reset["user_id"]))
        conn.execute("DELETE FROM password_resets WHERE token = ?", (token,))
        conn.commit()
        return True

# -------------------- Регистрация --------------------
def register_form():
    st.title("📝 Регистрация")

    with st.form("register_form"):
        new_username = st.text_input("Придумайте логин")
        new_email = st.text_input("Ваш email")
        new_password = st.text_input("Придумайте пароль", type="password")
        confirm_password = st.text_input("Повторите пароль", type="password")
        submitted = st.form_submit_button("Зарегистрироваться")

        if submitted:
            if new_password != confirm_password:
                st.error("Пароли не совпадают")
                return

            if len(new_password) < 6:
                st.error("Пароль должен быть не менее 6 символов")
                return

            pwd_hash = hash_password(new_password)

            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO users (username, email, password_hash, status) VALUES (?, ?, ?, ?)",
                        (new_username, new_email, pwd_hash, 'pending')
                    )
                    conn.commit()
                st.success("Регистрация успешна! Ваша заявка отправлена администратору на подтверждение.")
                st.session_state["show_login"] = True
                st.rerun()
            except Exception as e:
                st.error("Ошибка: возможно, такой логин или email уже заняты.")

# -------------------- Форма входа --------------------
def login_form():
    st.title("🔐 Вход в систему")

    if st.session_state.get("show_register", False):
        register_form()
        if st.button("← Вернуться ко входу"):
            st.session_state["show_register"] = False
            st.rerun()
        return

    if "2fa_user" in st.session_state:
        with st.form("2fa_form"):
            st.write(f"Введите код двухфакторной аутентификации для {st.session_state['2fa_user']['username']}")
            totp_code = st.text_input("Код из приложения", max_chars=6)
            submitted = st.form_submit_button("Подтвердить")
            if submitted:
                success, msg, user = authenticate_user(
                    st.session_state['2fa_user']['username'],
                    st.session_state['2fa_password'],
                    totp_code
                )
                if success:
                    session_token = create_session(user["id"])
                    st.session_state["authenticated"] = True
                    st.session_state["user_id"] = user["id"]
                    st.session_state["username"] = user["username"]
                    st.session_state["session_token"] = session_token
                    st.query_params["token"] = session_token
                    st.session_state.pop("2fa_user", None)
                    st.session_state.pop("2fa_password", None)
                    st.success("Вход выполнен успешно!")
                    st.rerun()
                else:
                    st.error(msg)
        if st.button("← Назад"):
            st.session_state.pop("2fa_user", None)
            st.session_state.pop("2fa_password", None)
            st.rerun()
        return

    with st.form("login_form"):
        username = st.text_input("Имя пользователя")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти")

        if submitted:
            success, msg, user = authenticate_user(username, password)
            if success:
                session_token = create_session(user["id"])
                st.session_state["authenticated"] = True
                st.session_state["user_id"] = user["id"]
                st.session_state["username"] = user["username"]
                st.session_state["session_token"] = session_token
                st.query_params["token"] = session_token
                st.success("Вход выполнен успешно!")
                st.rerun()
            elif msg == "REQUIRE_2FA":
                st.session_state["2fa_user"] = user
                st.session_state["2fa_password"] = password
                st.rerun()
            else:
                st.error(msg)

    if st.button("Нет аккаунта? Зарегистрироваться"):
        st.session_state["show_register"] = True
        st.rerun()

    with st.expander("Забыли пароль?"):
        email = st.text_input("Ваш email")
        if st.button("Отправить ссылку для сброса"):
            if request_password_reset(email):
                st.success("Если email зарегистрирован, ссылка отправлена.")
            else:
                st.error("Ошибка отправки. Проверьте email и попробуйте снова.")

# -------------------- Выход --------------------
def logout():
    if 'user_data_cache' in st.session_state:
        st.session_state.user_data_cache = {}
    if 'phase5_results' in st.session_state:
        st.session_state.phase5_results = {}
    if 'phase5_completed' in st.session_state:
        st.session_state.phase5_completed = False
    # ... остальная логика выхода
    if st.session_state.get("session_token"):
        delete_session(st.session_state.get("session_token"))

    keys_to_clear = ["authenticated", "user_id", "username", "session_token",
                     "show_change_password", "show_2fa_settings", "show_admin_panel"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    #st.query_params.clear()
    st.rerun()

# -------------------- Профиль --------------------
def profile_page():
    """Страница профиля - без sidebar, полноэкранный режим"""

    # Заголовок и кнопка назад
    col_back, col_title = st.columns([1, 5])
    with col_back:
        if st.button("← Назад", key="back_from_profile"):
            st.session_state.show_profile = False
            st.rerun()
    with col_title:
        st.title(f"👤 Профиль: {st.session_state['username']}")

    st.markdown("---")

    # Создаем вкладки для разных разделов
    tabs = st.tabs(["🔐 Основное", "🛡️ Безопасность", "⚙️ Действия"])

    # ========== ВКЛАДКА ОСНОВНОЕ ==========
    with tabs[0]:
        st.subheader("Информация о пользователе")

        with get_db() as conn:
            user = conn.execute(
                "SELECT username, email, status, is_admin, created_at FROM users WHERE id = ?",
                (st.session_state["user_id"],)
            ).fetchone()

        if user:
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Логин:**")
                st.write(user["username"])
                st.write("**Статус:**")
                st.write("✅ Администратор" if user["is_admin"] else "👤 Пользователь")
            with col2:
                st.write("**Email:**")
                st.write(user["email"])
                st.write("**Дата регистрации:**")
                st.write(user["created_at"][:10] if user["created_at"] else "Неизвестно")

    # ========== ВКЛАДКА БЕЗОПАСНОСТЬ ==========
    with tabs[1]:
        st.subheader("Настройки безопасности")

        # Смена пароля
        with st.expander("🔑 Сменить пароль", expanded=False):
            with st.form("change_password_form"):
                old_pwd = st.text_input("Текущий пароль", type="password")
                new_pwd = st.text_input("Новый пароль", type="password")
                confirm_pwd = st.text_input("Подтвердите новый пароль", type="password")

                if st.form_submit_button("Изменить пароль", type="primary"):
                    if new_pwd != confirm_pwd:
                        st.error("Пароли не совпадают")
                    elif len(new_pwd) < 6:
                        st.error("Пароль должен быть не менее 6 символов")
                    else:
                        success, msg = change_password(st.session_state["user_id"], old_pwd, new_pwd)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        # 2FA настройки
        with st.expander("🛡️ Двухфакторная аутентификация", expanded=False):
            with get_db() as conn:
                user = conn.execute(
                    "SELECT totp_enabled, totp_secret FROM users WHERE id = ?",
                    (st.session_state["user_id"],)
                ).fetchone()

            if user["totp_enabled"]:
                st.success("✅ 2FA включена")
                if st.button("Отключить 2FA", type="secondary"):
                    disable_2fa(st.session_state["user_id"])
                    st.success("2FA отключена")
                    st.rerun()
            else:
                st.info("2FA не включена. Для дополнительной защиты рекомендуем настроить.")

                if "temp_totp_secret" not in st.session_state:
                    st.session_state["temp_totp_secret"] = generate_totp_secret()

                secret = st.session_state["temp_totp_secret"]
                uri = get_totp_uri(st.session_state["username"], secret)
                qr_base64 = generate_qr_base64(uri)

                col_qr, col_key = st.columns([1, 1])
                with col_qr:
                    st.image(f"data:image/png;base64, {qr_base64}", caption="Отсканируйте QR-код")
                with col_key:
                    st.code(f"Секретный ключ: {secret}")
                    st.caption("Или введите этот ключ в приложение-аутентификатор")

                with st.form("verify_2fa_form"):
                    verify_code = st.text_input("Введите код из приложения", max_chars=6)
                    if st.form_submit_button("Активировать 2FA", type="primary"):
                        totp = pyotp.TOTP(secret)
                        if totp.verify(verify_code):
                            enable_2fa(st.session_state["user_id"], secret)
                            st.success("2FA успешно включена!")
                            st.session_state.pop("temp_totp_secret", None)
                            st.rerun()
                        else:
                            st.error("Неверный код. Попробуйте снова.")

    # ========== ВКЛАДКА ДЕЙСТВИЯ ==========
    with tabs[2]:
        st.subheader("Действия с аккаунтом")

        # Админ-панель (только для админов)
        if is_admin(st.session_state["user_id"]):
            st.markdown("### 👑 Администрирование")

            # Кнопка входа в админ-панель
            if st.button("Перейти в панель администратора", type="primary", use_container_width=True):
                st.session_state["show_admin_panel"] = True
                st.rerun()

            # Отображение админ-панели
            if st.session_state.get("show_admin_panel", False):
                st.markdown("---")
                # ✅ ВЫЗЫВАЕМ admin_panel() ИЗ ЭТОГО ЖЕ ФАЙЛА
                admin_panel()

                st.markdown("---")
                if st.button("← Закрыть админ-панель", use_container_width=True):
                    st.session_state["show_admin_panel"] = False
                    st.rerun()

            st.markdown("---")

        # Выход
        st.markdown("### 🚪 Выход из системы")
        if st.button("Выйти из аккаунта", type="secondary", use_container_width=True):
            logout()
            st.rerun()

# -------------------- Админ панель --------------------
def admin_panel():
    """Полноценная панель администратора с использованием всех модулей"""
    st.title("👑 Панель администратора")

    # Импортируем все необходимые функции из модулей admin/
    from admin.dashboard import render_admin_dashboard
    from admin.users_manager import render_users_manager
    from admin.api_keys_manager import render_api_keys_manager
    from admin.projects_viewer import render_projects_viewer
    from admin.stats_viewer import render_stats_viewer
    from admin.audit_viewer import render_audit_viewer

    # Создаём вкладки
    tabs = st.tabs([
        "📊 Дашборд",
        "👥 Пользователи и права",
        "🔑 API ключи",
        "📁 Все проекты",
        "📊 Статистика API",
        "📋 Аудит",
        "💾 Бэкапы и очистка"   # Новая вкладка
    ])

    with tabs[0]:
        render_admin_dashboard()
    with tabs[1]:
        render_users_manager()
    with tabs[2]:
        render_api_keys_manager()
    with tabs[3]:
        render_projects_viewer()
    with tabs[4]:
        render_stats_viewer()
    with tabs[5]:
        render_audit_viewer()
    with tabs[6]:
        render_backup_manager()