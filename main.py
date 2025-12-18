import json
import os
import uuid
import random
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
        game_id = gen_game_id()

        storage["games"][game_id] = {
            "id": game_id,
            "name": user["tmp_name"],
            "amount": update.message.text,
            "owner": user_id,
            "players": [user_id],
            "started": False,
        }

        user["state"] = None
        user.pop("tmp_name", None)
        save_storage()

        game = storage["games"][game_id]

        keyboard = [
            [InlineKeyboardButton("👥 Посмотреть участников", callback_data=f"players_{game_id}")],
            [InlineKeyboardButton("💰 Изменить сумму", callback_data=f"edit_amount_{game_id}")],
            [InlineKeyboardButton("🗑 Удалить игру", callback_data=f"delete_{game_id}")],
        ]

        await update.message.reply_text(
            game_card(game),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # ---- JOIN GAME ----
    if user["state"] == "wait_join_code":
        game = storage["games"].get(update.message.text)
        if not game:
            await update.message.reply_text("Игра не найдена.")
            return

        if user_id in game["players"]:
            await update.message.reply_text("Ты уже в игре.")
            return

        game["players"].append(user_id)
        user["state"] = None
        save_storage()

        await update.message.reply_text("Ты успешно присоединился к игре!")
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

    buttons = []
    for uid in game["players"]:
        buttons.append(
            [InlineKeyboardButton(f"❌ Удалить {uid}", callback_data=f"kick_{game_id}_{uid}")]
        )

    buttons.append([InlineKeyboardButton("⬅ Назад", callback_data=f"back_{game_id}")])

    await query.edit_message_text(
        game_card(game),
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

    await players_cb(update, context)

# ---------------- DELETE ----------------

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    storage["games"].pop(game_id, None)
    save_storage()

    await query.edit_message_text("Игра удалена.")

# ---------------- WEBHOOK ----------------

app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

async def on_startup():
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)

# ---------------- MAIN ----------------

def main():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(create_game_cb, pattern="create_game"))
    application.add_handler(CallbackQueryHandler(join_game_cb, pattern="join_game"))
    application.add_handler(CallbackQueryHandler(players_cb, pattern="players_"))
    application.add_handler(CallbackQueryHandler(kick_cb, pattern="kick_"))
    application.add_handler(CallbackQueryHandler(delete_cb, pattern="delete_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    uvicorn.run(app, host="0.0.0.0", port=PORT, lifespan="on")

if __name__ == "__main__":
    import asyncio
    asyncio.run(on_startup())
    main()
