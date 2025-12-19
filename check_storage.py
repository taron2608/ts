import json
import os

STORAGE_FILE = "storage.json"

print("🔍 Проверка хранилища данных...")
print(f"Файл: {STORAGE_FILE}")

if os.path.exists(STORAGE_FILE):
    print("✅ Файл существует")
    
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        print(f"📊 Игр: {len(data.get('games', {}))}")
        print(f"👤 Пользователей: {len(data.get('users', {}))}")
        
        # Показываем все игры
        print("\n🎮 Список игр:")
        for game_id, game in data.get('games', {}).items():
            print(f"  • {game_id}: {game.get('name', 'Без названия')} ({len(game.get('players', []))} игроков)")
            
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        
else:
    print("❌ Файл не существует")

# Проверка прав на запись
print(f"\n📝 Проверка прав на запись...")
try:
    with open("test_write.txt", "w") as f:
        f.write("test")
    os.remove("test_write.txt")
    print("✅ Права на запись в порядке")
except Exception as e:
    print(f"❌ Нет прав на запись: {e}")
