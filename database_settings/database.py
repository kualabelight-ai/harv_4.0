import sqlite3
import bcrypt
import pyotp
import secrets
import os  # <-- ДОБАВИТЬ ЭТОТ ИМПОРТ
from contextlib import contextmanager
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")
# ТЕПЕРЬ ТАК:
DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                totp_secret TEXT,
                totp_enabled INTEGER DEFAULT 0,
                failed_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                banned INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            )
        """)
        # Таблица для сброса пароля
        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        # НОВАЯ ТАБЛИЦА ДЛЯ СЕССИЙ
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_name TEXT NOT NULL,
                domain_name TEXT,
                provider TEXT NOT NULL,
                api_key TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                notes TEXT,
                UNIQUE(site_name, domain_name, provider),
                FOREIGN KEY(created_by) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id TEXT,
                site_name TEXT NOT NULL,
                domain_name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                request_type TEXT NOT NULL,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                estimated_cost DECIMAL(10,6),
                request_duration_ms INTEGER,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_domain_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                site_name TEXT NOT NULL,
                domain_name TEXT NOT NULL,
                can_read INTEGER DEFAULT 1,
                can_write INTEGER DEFAULT 1,
                can_delete INTEGER DEFAULT 0,
                granted_by INTEGER NOT NULL,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, site_name, domain_name),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(granted_by) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(admin_id) REFERENCES users(id)
            )
        """)

        # ИНДЕКСЫ ДЛЯ БЫСТРОГО ПОИСКА
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_site_domain ON api_keys(site_name, domain_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_user ON api_usage_logs(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_created ON api_usage_logs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_permissions_user ON user_domain_permissions(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_admin ON admin_audit_log(admin_id)")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_session_token ON user_sessions(session_token)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session_user ON user_sessions(user_id)")

        conn.commit()

# Хеширование пароля
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())
def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    with get_db() as conn:
        result = conn.execute(
            "SELECT is_admin FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        return result and result["is_admin"] == 1
# ============ НОВЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С СЕССИЯМИ ============

def create_session(user_id: int) -> str:
    """Создаёт новую сессию и возвращает токен"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=7)

    with get_db() as conn:
        # Удаляем старые сессии этого пользователя
        conn.execute(
            "DELETE FROM user_sessions WHERE user_id = ? AND expires_at < datetime('now')",
            (user_id,)
        )
        # Создаём новую сессию
        conn.execute(
            "INSERT INTO user_sessions (user_id, session_token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires_at)
        )
        conn.commit()

    return token

def validate_session(token: str):
    """Проверяет валидность токена, возвращает данные пользователя или None"""
    if not token:
        return None

    try:
        with get_db() as conn:
            user = conn.execute(
                """SELECT u.id, u.username, u.status, u.banned
                FROM users u 
                JOIN user_sessions s ON u.id = s.user_id 
                WHERE s.session_token = ? AND s.expires_at > datetime('now')""",
                (token,)
            ).fetchone()

            if user and user["status"] == "approved" and not user["banned"]:
                return {
                    "user_id": user["id"],
                    "username": user["username"]
                }
    except Exception as e:
        print(f"Session validation error: {e}")

    return None

def delete_session(token: str):
    """Удаляет сессию при выходе"""
    if not token:
        return

    try:
        with get_db() as conn:
            conn.execute(
                "DELETE FROM user_sessions WHERE session_token = ?",
                (token,)
            )
            conn.commit()
    except Exception:
        pass

def cleanup_expired_sessions():
    """Очищает просроченные сессии (можно вызывать периодически)"""
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM user_sessions WHERE expires_at <= datetime('now')")
            conn.commit()
    except Exception:
        pass

# Создание первого администратора
def create_admin(username, email, password):
    with get_db() as conn:
        pwd_hash = hash_password(password)
        try:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, status, is_admin) VALUES (?, ?, ?, 'approved', 1)",
                (username, email, pwd_hash)
            )
            conn.commit()
            print(f"Admin {username} created")
        except sqlite3.IntegrityError:
            print("User already exists")

if __name__ == "__main__":
    init_db()
    create_admin("admin1", "111@example.com", "1111")