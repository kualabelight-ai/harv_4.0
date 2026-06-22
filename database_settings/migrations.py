# database_settings/migrations.py
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from database_settings.database import get_db, DB_PATH


def migrate_existing_api_keys():
    """Переносит существующие API ключи из ai_config.json в БД"""
    config_file = Path("config/ai_config.json")

    if not config_file.exists():
        print("❌ Файл ai_config.json не найден, миграция ключей пропущена")
        return 0

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения ai_config.json: {e}")
        return 0

    providers = config.get("providers", {})
    migrated_count = 0

    with get_db() as conn:
        # Проверяем, есть ли уже ключи в БД
        existing = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        if existing > 0:
            print(f"ℹ️ В БД уже есть {existing} ключей, миграция пропущена")
            return 0

        # Переносим ключи для каждого провайдера
        for provider, provider_config in providers.items():
            api_key = provider_config.get("api_key", "")
            if not api_key:
                print(f"⚠️ Нет API ключа для провайдера {provider}, пропуск")
                continue

            # Добавляем ключ для домена default сайта steelborg
            conn.execute("""
                INSERT INTO api_keys (site_name, domain_name, provider, api_key, created_by, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                "steelborg",
                "default",
                provider,
                api_key,
                1,  # admin1
                f"Мигрировано из ai_config.json {datetime.now().isoformat()}"
            ))
            migrated_count += 1
            print(f"✅ Мигрирован ключ для {provider} (steelborg/default)")

        conn.commit()

    print(f"✅ Миграция завершена: добавлено {migrated_count} ключей")
    return migrated_count


def grant_default_permissions():
    """Выдает права на домен default всем существующим пользователям"""
    with get_db() as conn:
        # Получаем всех пользователей
        users = conn.execute("SELECT id FROM users WHERE status = 'approved'").fetchall()

        if not users:
            print("ℹ️ Нет пользователей для выдачи прав")
            return 0

        granted_count = 0
        for user in users:
            # Проверяем, есть ли уже права
            existing = conn.execute("""
                SELECT id FROM user_domain_permissions 
                WHERE user_id = ? AND site_name = 'steelborg' AND domain_name = 'default'
            """, (user["id"],)).fetchone()

            if not existing:
                conn.execute("""
                    INSERT INTO user_domain_permissions (user_id, site_name, domain_name, can_read, can_write, can_delete, granted_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user["id"], "steelborg", "default", 1, 1, 0, 1))
                granted_count += 1

        conn.commit()

    print(f"✅ Выданы права на default домен {granted_count} пользователям")
    return granted_count


def run_all_migrations():
    """Запускает все миграции"""
    print("=" * 50)
    print("🚀 Запуск миграций...")
    print("=" * 50)

    # 1. Миграция API ключей
    keys_migrated = migrate_existing_api_keys()
    print(f"📊 API ключи: {keys_migrated} мигрировано")

    # 2. Выдача прав на default домен
    permissions_granted = grant_default_permissions()
    print(f"📊 Права доступа: {permissions_granted} выдано")

    print("=" * 50)
    print("✅ Миграции завершены!")
    print("=" * 50)


if __name__ == "__main__":
    from database_settings.database import init_db
    init_db()
    run_all_migrations()