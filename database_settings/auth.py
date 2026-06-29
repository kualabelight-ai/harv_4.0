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
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
# Настройка логирования
logging.basicConfig(
    filename='login_attempts.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
    st.title("👥 Панель администратора")

    tab1, tab2, tab3 = st.tabs(["📋 Заявки на регистрацию", "👤 Все пользователи", "🔐 Права на домены"])

    with tab1:
        st.subheader("Новые заявки")

        with get_db() as conn:
            pending_users = conn.execute(
                "SELECT id, username, email, created_at FROM users WHERE status = 'pending' ORDER BY created_at ASC"
            ).fetchall()

        if not pending_users:
            st.info("✅ Нет новых заявок на регистрацию.")
        else:
            st.warning(f"⚠️ Найдено {len(pending_users)} заявок, ожидающих рассмотрения.")
            st.markdown("---")

            for user in pending_users:
                col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                with col1:
                    st.write(f"**{user['username']}**")
                with col2:
                    st.write(user['email'])
                with col3:
                    created = datetime.fromisoformat(user['created_at']).strftime("%d.%m.%Y %H:%M")
                    st.write(f"📅 {created}")
                with col4:
                    if st.button("✅ Одобрить", key=f"approve_{user['id']}", type="primary"):
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE users SET status = 'approved' WHERE id = ?",
                                (user['id'],)
                            )
                            conn.commit()
                        st.success(f"✅ Пользователь {user['username']} одобрен!")
                        time.sleep(0.5)
                        st.rerun()
                st.divider()

    with tab2:
        st.subheader("Управление пользователями")
        with get_db() as conn:
            users = conn.execute("""
                SELECT id, username, email, status, is_admin, totp_enabled, banned, 
                       failed_attempts, locked_until, created_at
                FROM users 
                ORDER BY 
                    CASE status 
                        WHEN 'pending' THEN 0 
                        ELSE 1 
                    END,
                    created_at DESC
            """).fetchall()

        if users:
            users_list = []
            for u in users:
                status_emoji = {
                    'approved': '✅',
                    'pending': '⏳',
                    'rejected': '❌'
                }.get(u["status"], '❓')

                users_list.append({
                    "ID": u["id"],
                    "Username": u["username"],
                    "Email": u["email"],
                    "Status": f"{status_emoji} {u['status']}",
                    "Admin": "✅" if u["is_admin"] else "❌",
                    "2FA": "✅" if u["totp_enabled"] else "❌",
                    "Banned": "✅" if u["banned"] else "❌",
                    "Created": u["created_at"][:10] if u["created_at"] else "N/A"
                })
            st.dataframe(users_list, use_container_width=True)

        st.markdown("---")
        st.subheader("Действия с пользователем")

        with get_db() as conn:
            users = conn.execute(
                "SELECT id, username, status, is_admin, banned FROM users ORDER BY username"
            ).fetchall()

            if users:
                user_options = {f"{u['username']} (ID: {u['id']})": u['id'] for u in users}
                selected_display = st.selectbox("Выберите пользователя", list(user_options.keys()))
                selected_id = user_options[selected_display]

                user = conn.execute(
                    "SELECT id, username, email, status, is_admin, banned FROM users WHERE id = ?",
                    (selected_id,)
                ).fetchone()

                if user:
                    st.write(f"**Текущий статус:** {user['status']}, Админ: {'да' if user['is_admin'] else 'нет'}, Бан: {'да' if user['banned'] else 'нет'}")

                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        if user["banned"]:
                            if st.button("🔓 Разблокировать", key=f"unban_{user['id']}"):
                                with get_db() as conn:
                                    conn.execute("UPDATE users SET banned = 0 WHERE id = ?", (user['id'],))
                                    conn.commit()
                                st.success(f"Пользователь {user['username']} разблокирован.")
                                st.rerun()
                        else:
                            if st.button("🔒 Заблокировать", key=f"ban_{user['id']}"):
                                if user["id"] == st.session_state["user_id"]:
                                    st.error("Нельзя заблокировать самого себя.")
                                else:
                                    with get_db() as conn:
                                        conn.execute("UPDATE users SET banned = 1 WHERE id = ?", (user['id'],))
                                        conn.commit()
                                    st.success(f"Пользователь {user['username']} заблокирован.")
                                    st.rerun()

                    with col2:
                        if user["is_admin"]:
                            if st.button("👤 Снять админа", key=f"deadmin_{user['id']}"):
                                if user["id"] == st.session_state["user_id"]:
                                    st.error("Нельзя снять админа с самого себя.")
                                else:
                                    with get_db() as conn:
                                        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user['id'],))
                                        conn.commit()
                                    st.success(f"Пользователь {user['username']} больше не администратор.")
                                    st.rerun()
                        else:
                            if st.button("👑 Назначить админом", key=f"admin_{user['id']}"):
                                with get_db() as conn:
                                    conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user['id'],))
                                    conn.commit()
                                st.success(f"Пользователь {user['username']} теперь администратор.")
                                st.rerun()

                    with col3:
                        if st.button("🔄 Сбросить 2FA", key=f"reset2fa_{user['id']}"):
                            with get_db() as conn:
                                conn.execute(
                                    "UPDATE users SET totp_enabled = 0, totp_secret = NULL WHERE id = ?",
                                    (user['id'],)
                                )
                                conn.commit()
                            st.success(f"2FA для {user['username']} сброшена.")
                            st.rerun()

                    with col4:
                        if st.button("❌ Удалить", key=f"delete_{user['id']}"):
                            if user["id"] == st.session_state["user_id"]:
                                st.error("Нельзя удалить самого себя.")
                            else:
                                with get_db() as conn:
                                    conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user['id'],))
                                    conn.execute("DELETE FROM user_sessions WHERE user_id = ?", (user['id'],))
                                    conn.execute("DELETE FROM user_domain_permissions WHERE user_id = ?", (user['id'],))
                                    conn.execute("DELETE FROM users WHERE id = ?", (user['id'],))
                                    conn.commit()
                                st.success(f"Пользователь {user['username']} удален.")
                                st.rerun()

    # ========== НОВАЯ ВКЛАДКА: ПРАВА НА ДОМЕНЫ ==========
    with tab3:
        st.subheader("🔐 Управление правами на домены")

        # Выбор пользователя
        with get_db() as conn:
            users = conn.execute(
                "SELECT id, username, email, status FROM users WHERE status = 'approved' ORDER BY username"
            ).fetchall()

            if not users:
                st.warning("Нет активных пользователей для выдачи прав")
                return

            user_options = {f"{u['username']} ({u['email']})": u['id'] for u in users}
            selected_user_label = st.selectbox("👤 Выберите пользователя", list(user_options.keys()))
            user_id = user_options[selected_user_label]

            # Получаем данные пользователя
            user = conn.execute(
                "SELECT id, username, email FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()

        st.markdown("---")

        # Выбор сайта и домена
        from site_manager import SiteManager
        from domain_manager import DomainManager

        sm = SiteManager()
        sites = sm.get_available_sites()

        if not sites:
            st.warning("Нет доступных сайтов")
            return

        col1, col2 = st.columns(2)
        with col1:
            site_name = st.selectbox("🏢 Сайт", sites)

        dm = DomainManager(site_name)
        domains = dm.get_available_domains()

        with col2:
            domain_name = st.selectbox("🌐 Домен", domains)

        # Проверяем текущие права
        from domain_permissions import DomainPermissionManager
        perm_manager = DomainPermissionManager()

        # Получаем текущие права
        with get_db() as conn:
            current_perms = conn.execute("""
                SELECT can_read, can_write, can_delete
                FROM user_domain_permissions
                WHERE user_id = ? AND site_name = ? AND domain_name = ?
            """, (user_id, site_name, domain_name)).fetchone()

        has_access = current_perms is not None

        st.markdown("---")

        # Отображаем текущие права
        col_status, col_action = st.columns([1, 1])

        with col_status:
            if has_access:
                st.success(f"✅ Пользователь **{user['username']}** уже имеет доступ к **{site_name}/{domain_name}**")

                # Показываем текущие права
                st.write(f"📖 Чтение: {'✅' if current_perms['can_read'] else '❌'}")
                st.write(f"✏️ Запись: {'✅' if current_perms['can_write'] else '❌'}")
                st.write(f"🗑️ Удаление: {'✅' if current_perms['can_delete'] else '❌'}")
            else:
                st.info(f"ℹ️ Пользователь **{user['username']}** не имеет доступа к **{site_name}/{domain_name}**")

        with col_action:
            if has_access:
                if st.button("🔒 Отозвать доступ", type="secondary", use_container_width=True):
                    if perm_manager.revoke_access(user_id, site_name, domain_name):
                        st.success("✅ Доступ отозван")
                        st.rerun()
            else:
                if st.button("📝 Выдать доступ", type="primary", use_container_width=True):
                    st.session_state.show_grant_permissions = True

        # Форма выдачи прав
        if st.session_state.get("show_grant_permissions", False) or not has_access:
            st.markdown("---")
            st.subheader("✏️ Настройка прав доступа")

            with st.form("grant_permissions_form"):
                st.write(f"**Выдача прав для:** {user['username']} → {site_name}/{domain_name}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    can_read = st.checkbox("📖 Чтение", value=True)
                with col2:
                    can_write = st.checkbox("✏️ Запись", value=True)
                with col3:
                    can_delete = st.checkbox("🗑️ Удаление", value=False)

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.form_submit_button("💾 Сохранить права", type="primary", use_container_width=True):
                        if perm_manager.grant_access(
                                st.session_state.user_id,  # admin_user_id
                                user_id,                    # target_user_id
                                site_name,
                                domain_name,
                                can_read,
                                can_write,
                                can_delete
                        ):
                            st.success("✅ Права успешно сохранены!")
                            st.session_state.pop("show_grant_permissions", None)
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("❌ Ошибка сохранения прав")

                with col_btn2:
                    if st.form_submit_button("❌ Отмена", use_container_width=True):
                        st.session_state.pop("show_grant_permissions", None)
                        st.rerun()

        st.markdown("---")

        # Список пользователей с доступом к текущему домену
        st.subheader(f"👥 Пользователи с доступом к {site_name}/{domain_name}")

        users_with_access = perm_manager.get_users_with_access(site_name, domain_name)

        if users_with_access:
            for u in users_with_access:
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.write(f"**{u['username']}**")
                    st.caption(u['email'])
                with col2:
                    st.write(f"📖 {'✅' if u['can_read'] else '❌'}  ✏️ {'✅' if u['can_write'] else '❌'}  🗑️ {'✅' if u['can_delete'] else '❌'}")
                with col3:
                    if st.button("🔒 Отозвать", key=f"revoke_{u['id']}_{site_name}_{domain_name}"):
                        if perm_manager.revoke_access(u['id'], site_name, domain_name):
                            st.success(f"✅ Доступ отозван у {u['username']}")
                            st.rerun()
                st.divider()
        else:
            st.info("Нет пользователей с доступом к этому домену")