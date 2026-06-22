# migrate_db.py (放在项目根目录)
import sqlite3
import os

# Указываем правильный путь к БД
DB_PATH = "users.db"

def get_absolute_path():
    """Получает абсолютный путь к БД"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, DB_PATH)

def add_session_table():
    """Добавляет таблицу user_sessions в существующую базу данных"""
    db_path = get_absolute_path()

    # Проверяем, существует ли файл БД
    if not os.path.exists(db_path):
        print(f"❌ База данных не найдена по пути: {db_path}")
        print("Сначала запустите приложение, чтобы создать БД")
        return False

    print(f"Подключение к БД: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Проверяем, существует ли таблица
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_sessions'")
        if not cursor.fetchone():
            print("📝 Создаём таблицу user_sessions...")

            # Создаём таблицу
            cursor.execute("""
                CREATE TABLE user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)

            # Создаём индексы
            cursor.execute("CREATE INDEX idx_session_token ON user_sessions(session_token)")
            cursor.execute("CREATE INDEX idx_session_user ON user_sessions(user_id)")

            conn.commit()
            print("✅ Таблица user_sessions успешно создана!")
            return True
        else:
            print("✅ Таблица user_sessions уже существует")
            return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def check_database_structure():
    """Проверяет структуру базы данных"""
    db_path = get_absolute_path()

    if not os.path.exists(db_path):
        print(f"❌ База данных не найдена: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n📊 Структура базы данных:")

    # Получаем список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()

    for table in tables:
        table_name = table[0]
        print(f"\n📋 Таблица: {table_name}")
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")

    conn.close()
    return True

if __name__ == "__main__":
    print("Начинаем миграцию базы данных...")
    print("=" * 50)

    # Проверяем существование БД
    db_path = get_absolute_path()
    if os.path.exists(db_path):
        print(f"✅ База данных найдена: {db_path}")

        # Добавляем таблицу сессий
        if add_session_table():
            print("\n✅ Миграция успешно завершена!")
        else:
            print("\n❌ Миграция не удалась")

        # Показываем структуру БД
        check_database_structure()
    else:
        print(f"❌ База данных не найдена по пути: {db_path}")
        print("\nСоздайте БД, запустив приложение хотя бы один раз:")
        print("streamlit run main_app.py")