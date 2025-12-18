import json
import os
import uuid
import random
from contextlib import asynccontextmanager
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from fastapi import FastAPI, Request
import uvicorn

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://xxx.onrender.com/webhook
PORT = int(os.environ.get("PORT", 10000))

STORAGE_FILE = "storage.json"

# ---------------- STORAGE ----------------

def load_storage():
    if not os.path.exists(STORAGE_FILE):
        return {"games": {}, "users": {}}
    with open(STORAGE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_storage():
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(storage, f, ensure_ascii=False, indent=2)

storage = load_storage()

# ---------------- UTILS ----------------

def gen_game_id():
    return str(uuid.uuid4())[:8]

def get_user(uid):
    return storage["users"].setdefault(str(uid), {"state": None})

def game_card(game):
    return (
        f"🎄 Тайный Санта\n\n"
        f"🎁 Игра: {game['name']}\n"
        f"💰 Сумма: {game['amount']}\n"
        f"👥 Игроков: {len(game['players'])}"
    )

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    user["state"] = None
    save_storage()

    keyboard = [
        [InlineKeyboardButton("🎁 Создать игру", callback_data="create_game")],
        [InlineKeyboardButton("🔗 Войти в игру", callback_data="join_game")],
    ]

    await update.message.reply_text(
        "🎄 Тайный Санта\n\nВыбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ---------------- CREATE GAME ----------------

async def create_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)
    user["state"] = "wait_game_name"
    save_storage()

    await query.edit_message_text("Введите название игры:")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    user = get_user(user_id)

    # ---- GAME NAME ----
    if user["state"] == "wait_game_name":
        user["tmp_name"] = update.message.text
        user["state"] = "wait_game_amount"
        save_storage()

        await update.message.reply_text("Введите сумму подарка:")
        return

    # ---- GAME AMOUNT ----
    if user["state"] == "wait_game_amount":
        try:
            amount = float(update.message.text.replace(",", "."))
            if amount <= 0:
                await update.message.reply_text("Сумма должна быть положительной. Попробуйте снова:")
                return
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректную сумму (например: 1000 или 1000.50):")
            return

        game_id = gen_game_id()

        storage["games"][game_id] = {
            "id": game_id,
            "name": user["tmp_name"],
            "amount": update.message.text,
            "owner": user_id,
            "players": [user_id],
            "started": False,
            "pairs": {}
        }

        user["state"] = None
        user.pop("tmp_name", None)
        save_storage()

        game = storage["games"][game_id]

        keyboard = [
            [InlineKeyboardButton("👥 Участники", callback_data=f"players_{game_id}")],
            [InlineKeyboardButton("▶️ Начать жеребьёвку", callback_data=f"start_game_{game_id}")],
            [InlineKeyboardButton("💰 Изменить сумму", callback_data=f"edit_amount_{game_id}")],
            [InlineKeyboardButton("🗑 Удалить игру", callback_data=f"delete_{game_id}")],
        ]

        await update.message.reply_text(
            f"🎄 Игра создана!\n\n"
            f"🎁 Название: {game['name']}\n"
            f"💰 Сумма: {game['amount']}\n"
            f"🆔 Код игры: `{game_id}`\n\n"
            f"Отправьте этот код друзьям, чтобы они присоединились!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # ---- JOIN GAME ----
    if user["state"] == "wait_join_code":
        game = storage["games"].get(update.message.text)
        if not game:
            await update.message.reply_text("Игра не найдена. Проверьте код и попробуйте снова.")
            return

        if game["started"]:
            await update.message.reply_text("Игра уже началась, присоединиться нельзя.")
            return

        if user_id in game["players"]:
            await update.message.reply_text("Ты уже в этой игре!")
            return

        game["players"].append(user_id)
        user["state"] = None
        save_storage()

        await update.message.reply_text(
            f"✅ Ты успешно присоединился к игре!\n"
            f"🎁 Название: {game['name']}\n"
            f"💰 Сумма: {game['amount']}\n"
            f"👥 Участников: {len(game['players'])}"
        )
        return

    # ---- EDIT AMOUNT ----
    if user["state"] and user["state"].startswith("wait_new_amount_"):
        game_id = user["state"].split("_")[-1]
        
        if game_id not in storage["games"]:
            await update.message.reply_text("Игра не найдена.")
            user["state"] = None
            save_storage()
            return

        game = storage["games"][game_id]
        
        if user_id != game["owner"]:
            await update.message.reply_text("Только создатель игры может менять сумму.")
            user["state"] = None
            save_storage()
            return

        try:
            amount = float(update.message.text.replace(",", "."))
            if amount <= 0:
                await update.message.reply_text("Сумма должна быть положительной. Попробуйте снова:")
                return
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректную сумму (например: 1000 или 1000.50):")
            return

        game["amount"] = update.message.text
        user["state"] = None
        save_storage()

        await update_message_with_game_menu(update.message, game_id)
        return

# ---------------- JOIN ----------------

async def join_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)
    user["state"] = "wait_join_code"
    save_storage()

    await query.edit_message_text("Введите код игры:")

# ---------------- PLAYERS ----------------

async def players_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    game = storage["games"][game_id]

    # Собираем имена игроков
    players_text = "👥 Участники:\n"
    for i, uid in enumerate(game["players"], 1):
        try:
            user_info = await context.bot.get_chat(uid)
            name = user_info.first_name or user_info.username or f"Игрок {i}"
        except:
            name = f"Игрок {i}"
        players_text += f"{i}. {name}\n"

    buttons = []
    if query.from_user.id == int(game["owner"]):
        for uid in game["players"]:
            if uid != game["owner"]:  # Не показываем кнопку удаления для владельца
                try:
                    user_info = await context.bot.get_chat(uid)
                    name = user_info.first_name or user_info.username or uid
                except:
                    name = uid
                buttons.append(
                    [InlineKeyboardButton(f"❌ Удалить {name[:15]}", callback_data=f"kick_{game_id}_{uid}")]
                )

    buttons.append([InlineKeyboardButton("⬅ Назад", callback_data=f"back_{game_id}")])

    await query.edit_message_text(
        f"{game_card(game)}\n\n{players_text}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def kick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, game_id, uid = query.data.split("_")
    game = storage["games"][game_id]

    if uid in game["players"]:
        game["players"].remove(uid)
        save_storage()
        try:
            await context.bot.send_message(
                uid, 
                f"Вы были удалены из игры '{game['name']}' создателем игры."
            )
        except:
            pass

    await players_cb(update, context)

# ---------------- DELETE ----------------

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    game = storage["games"][game_id]
    
    if query.from_user.id != int(game["owner"]):
        await query.answer("Только создатель игры может её удалить!", show_alert=True)
        return

    # Уведомляем участников
    for uid in game["players"]:
        if uid != str(query.from_user.id):
            try:
                await context.bot.send_message(uid, f"Игра '{game['name']}' была удалена создателем.")
            except:
                pass
    
    storage["games"].pop(game_id, None)
    save_storage()

    await query.edit_message_text("🎄 Игра удалена.")

# ---------------- EDIT AMOUNT ----------------

async def edit_amount_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[2]
    game = storage["games"][game_id]
    
    if query.from_user.id != int(game["owner"]):
        await query.answer("Только создатель игры может менять сумму!", show_alert=True)
        return

    user = get_user(query.from_user.id)
    user["state"] = f"wait_new_amount_{game_id}"
    save_storage()

    await query.edit_message_text(f"Текущая сумма: {game['amount']}\n\nВведите новую сумму:")

# ---------------- START GAME ----------------

async def start_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[2]
    game = storage["games"][game_id]
    
    if query.from_user.id != int(game["owner"]):
        await query.answer("Только создатель игры может начать жеребьёвку!", show_alert=True)
        return

    if len(game["players"]) < 2:
        await query.answer("Нужно минимум 2 участника!", show_alert=True)
        return

    if game["started"]:
        await query.answer("Жеребьёвка уже проведена!", show_alert=True)
        return

    # Проводим жеребьёвку
    players = game["players"][:]
    random.shuffle(players)
    
    pairs = {}
    for i in range(len(players)):
        giver = players[i]
        receiver = players[(i + 1) % len(players)]
        pairs[giver] = receiver

    game["pairs"] = pairs
    game["started"] = True
    save_storage()

    # Отправляем сообщения участникам
    for giver, receiver in pairs.items():
        try:
            receiver_info = await context.bot.get_chat(receiver)
            receiver_name = receiver_info.first_name or receiver_info.username or "ваш получатель"
            
            await context.bot.send_message(
                giver,
                f"🎅 Жеребьёвка проведена!\n\n"
                f"🎁 Вы дарите подарок: {receiver_name}\n"
                f"💰 Сумма подарка: {game['amount']}\n"
                f"🎄 Игра: {game['name']}\n\n"
                f"Удачи в выборе подарка! 🎄"
            )
        except Exception as e:
            print(f"Ошибка отправки сообщения {giver}: {e}")

    await query.edit_message_text(
        f"✅ Жеребьёвка проведена!\n\n"
        f"Все участники получили свои задания.\n"
        f"🎁 Игра: {game['name']}\n"
        f"👥 Участников: {len(game['players'])}\n\n"
        f"Счастливого Рождества! 🎅"
    )

# ---------------- BACK ----------------

async def back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await update_message_with_game_menu(query, query.data.split("_")[1])

async def update_message_with_game_menu(message_obj, game_id):
    """Обновляет сообщение с меню игры"""
    game = storage["games"][game_id]
    
    keyboard = []
    if not game["started"]:
        keyboard.append([InlineKeyboardButton("👥 Участники", callback_data=f"players_{game_id}")])
        if message_obj.from_user.id == int(game["owner"]):
            keyboard.append([InlineKeyboardButton("▶️ Начать жеребьёвку", callback_data=f"start_game_{game_id}")])
            keyboard.append([InlineKeyboardButton("💰 Изменить сумму", callback_data=f"edit_amount_{game_id}")])
            keyboard.append([InlineKeyboardButton("🗑 Удалить игру", callback_data=f"delete_{game_id}")])
    else:
        keyboard.append([InlineKeyboardButton("👥 Участники", callback_data=f"players_{game_id}")])
        keyboard.append([InlineKeyboardButton("📊 Статус игры", callback_data=f"status_{game_id}")])

    text = f"{game_card(game)}\n"
    if game["started"]:
        text += f"\n✅ Жеребьёвка проведена"
    else:
        text += f"\n🆔 Код для входа: `{game_id}`"

    if hasattr(message_obj, 'edit_message_text'):
        await message_obj.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await message_obj.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# ---------------- WEBHOOK & FASTAPI ----------------

# Глобальная переменная для Application
application = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan контекст для FastAPI"""
    global application
    
    # При запуске приложения
    print("🚀 Инициализация бота...")
    
    # Создаем и инициализируем Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(create_game_cb, pattern="create_game"))
    application.add_handler(CallbackQueryHandler(join_game_cb, pattern="join_game"))
    application.add_handler(CallbackQueryHandler(players_cb, pattern="players_"))
    application.add_handler(CallbackQueryHandler(kick_cb, pattern="kick_"))
    application.add_handler(CallbackQueryHandler(delete_cb, pattern="delete_"))
    application.add_handler(CallbackQueryHandler(edit_amount_cb, pattern="edit_amount_"))
    application.add_handler(CallbackQueryHandler(start_game_cb, pattern="start_game_"))
    application.add_handler(CallbackQueryHandler(back_cb, pattern="back_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    # Инициализируем Application
    await application.initialize()
    
    # Устанавливаем webhook
    if WEBHOOK_URL:
        await application.bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook установлен на {WEBHOOK_URL}")
    else:
        print("⚠️ WEBHOOK_URL не установлен. Бот может не работать.")
    
    print("✅ Бот инициализирован и готов к работе!")
    
    yield
    
    # При остановке приложения
    print("🛑 Остановка бота...")
    if application:
        await application.shutdown()
    print("✅ Бот остановлен")

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(req: Request):
    """Endpoint для получения обновлений от Telegram"""
    global application
    
    if not application:
        return {"ok": False, "error": "Application not initialized"}, 500
    
    try:
        data = await req.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        print(f"Ошибка в webhook: {e}")
        return {"ok": False, "error": str(e)}, 500

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok", 
        "message": "Бот Тайный Санта работает",
        "service": "secret-santa-bot",
        "games_count": len(storage["games"])
    }

@app.get("/status")
async def status():
    """Детальный статус"""
    return {
        "status": "running",
        "webhook_set": bool(WEBHOOK_URL),
        "games": len(storage["games"]),
        "users": len(storage["users"])
    }

# ---------------- MAIN ----------------

def main():
    """Запуск FastAPI приложения"""
    print(f"🚀 Запуск FastAPI сервера на порту {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
