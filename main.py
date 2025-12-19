import os
import uuid
import time
import threading
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

print("🚀 Запуск простого бота...")

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Хранилище в памяти
games = {}
users = {}

# Активный пинг
def keep_alive():
    """Пингуем себя чтобы не заснуть"""
    print("🔔 Активный пинг запущен")
    
    # URL для пинга (нужно указать свой)
    ping_url = "https://ваш-бот.railway.app/"  # ЗАМЕНИ НА СВОЙ URL!
    
    while True:
        try:
            requests.get(ping_url, timeout=10)
            print(f"✅ [{time.strftime('%H:%M:%S')}] Пинг отправлен")
        except:
            print(f"⚠️  [{time.strftime('%H:%M:%S')}] Пинг не удался")
        
        time.sleep(120)  # Каждые 2 минуты

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if user_id not in users:
        users[user_id] = {"games": []}
    
    text = "🎅 <b>Тайный Санта</b>\n\nСоздай игру или присоединяйся!"
    
    keyboard = [
        [InlineKeyboardButton("✨ Создать игру", callback_data="create")],
        [InlineKeyboardButton("📋 Мои игры", callback_data="list")],
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def create_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    users[user_id]["state"] = "wait_name"
    
    await query.edit_message_text("🎄 Введи название игры:")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    
    if user_id not in users:
        users[user_id] = {"games": [], "state": None}
    
    state = users[user_id].get("state")
    
    if state == "wait_name":
        # Создаем игру
        game_id = str(uuid.uuid4())[:8]
        
        games[game_id] = {
            "id": game_id,
            "name": text,
            "owner": user_id,
            "players": [user_id],
            "amount": "1000",  # Фиксированная сумма для простоты
            "created": time.time()
        }
        
        users[user_id]["games"].append(game_id)
        users[user_id]["state"] = None
        
        await update.message.reply_text(
            f"✅ Игра создана!\n\n"
            f"🎄 <b>{text}</b>\n"
            f"👥 Участников: 1\n\n"
            f"ID игры: <code>{game_id}</code>",
            parse_mode="HTML"
        )
        
        print(f"✅ Игра создана: {game_id}, всего игр: {len(games)}")

async def list_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    user_games = []
    
    for game_id, game in games.items():
        if user_id in game["players"]:
            user_games.append(game)
    
    if user_games:
        text = "🎮 <b>Твои игры:</b>\n\n"
        for game in user_games[:5]:
            text += f"🎄 {game['name']}\n👥 {len(game['players'])} игроков\n\n"
    else:
        text = "🎄 У тебя пока нет игр\n\nСоздай первую!"
    
    keyboard = [[InlineKeyboardButton("✨ Создать игру", callback_data="create")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

def main():
    print("🎅 Запуск простого бота...")
    
    # Запускаем активный пинг в отдельном потоке
    ping_thread = threading.Thread(target=keep_alive, daemon=True)
    ping_thread.start()
    print("✅ Активный пинг запущен")
    
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(create_game, pattern="create"))
    app.add_handler(CallbackQueryHandler(list_games, pattern="list"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🤖 Бот запущен и готов к работе!")
    print("🔥 Активный пинг предотвращает сон")
    print(f"📊 В памяти: {len(games)} игр, {len(users)} пользователей")
    
    # Запускаем бота
    app.run_polling()

if __name__ == "__main__":
    main()
