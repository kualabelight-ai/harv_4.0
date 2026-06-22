# migrate_blocks.py - запустить отдельно
import shutil
from pathlib import Path

def migrate_existing_blocks():
    """Переносит существующие блоки в новую структуру"""

    old_blocks_dir = Path("blocks")
    new_blocks_dir = Path("project_configs/default/blocks")

    if old_blocks_dir.exists():
        print(f"📁 Найдена старая папка blocks: {old_blocks_dir}")

        # Создаем целевую папку
        new_blocks_dir.mkdir(parents=True, exist_ok=True)

        # Копируем все блоки
        for item in old_blocks_dir.iterdir():
            if item.is_dir():
                target = new_blocks_dir / item.name
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
                print(f"✅ Скопирован блок: {item.name}")

        print(f"✅ Миграция блоков завершена в {new_blocks_dir}")
    else:
        print("❌ Старая папка blocks не найдена")

    # Также переносим AI инструкции, если есть
    old_ai_dir = Path("data/ai_instructions.json")
    new_ai_dir = Path("project_configs/default/ai_instructions")

    if old_ai_dir.exists():
        new_ai_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_ai_dir, new_ai_dir / "instructions.json")
        print(f"✅ Скопированы AI инструкции")
    else:
        print("⚠️ Старые AI инструкции не найдены")

if __name__ == "__main__":
    migrate_existing_blocks()