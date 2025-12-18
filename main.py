import json
import uuid
import random
import os
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
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

def gen_code():
    return str(uuid.uuid4())[:8]

def game_card(game):
    return (
        f"🎄 <b>{game['name']}</b>\n"
        f"💰 Сумма: {game['amount']} ₽\n"
        f"👥 Игроков: {len(game['players'])}"
    )

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎁 Организатор", callback_data="role_org")],
        [InlineKeyboardButton("👤 Участник", callback_data="role_user")],
    ]
    await update.message.reply_text(
        "Выбери роль:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ---------------- ROLE ----------------

async def role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    storage["users"][user_id] = {"state": query.data}
    save_storage()

    if query.data == "role_org":
        await organizer_menu(query)
    else:
        await join_game_prompt(query)

# ---------------- ORGANIZER MENU ----------------

async def organizer_menu(query):
    keyboard = [
        [InlineKeyboardButton("🎮 Создать игру", callback_data="create_game")],
        [InlineKeyboardButton("📋 Мои игры", callback_data="my_games")],
        [InlineKeyboardButton("💰 Изменить сумму", callback_data="edit_amount")],
    ]
    await query.edit_message_text(
        "Панель организатора:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ---------------- CREATE GAME ----------------

async def create_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    context.user_data["creating"] = True
    await query.edit_message_text("Введите название игры:")

async def game_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("creating"):
        return

    context.user_data["game_name"] = update.message.text
    await update.message.reply_text("Введите сумму подарка:")

async def game_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "game_name" not in context.user_data:
        return

    user_id = str(update.message.from_user.id)
    game_id = gen_code()

    storage["games"][game_id] = {
        "id": game_id,
        "name": context.user_data["game_name"],
        "amount": update.message.text,
        "owner": user_id,
        "players": [user_id],
        "started": False,
    }

    context.user_data.clear()
    save_storage()

    await update.message.reply_text(
        game_card(storage["games"][game_id]),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("👥 Участники", callback_data=f"players_{game_id}")],
                [InlineKeyboardButton("🗑 Удалить игру", callback_data=f"delete_{game_id}")],
            ]
        ),
    )

# ---------------- PLAYERS ----------------

async def players_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    game = storage["games"][game_id]

    buttons = []
    for uid in game["players"]:
        buttons.append(
            [InlineKeyboardButton(f"❌ {uid}", callback_data=f"kick_{game_id}_{uid}")]
        )

    buttons.append([InlineKeyboardButton("⬅ Назад", callback_data="my_games")])

    await query.edit_message_text(
        game_card(game),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def kick_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, game_id, uid = query.data.split("_")
    game = storage["games"][game_id]

    if uid in game["players"]:
        game["players"].remove(uid)
        save_storage()

    await players_menu(update, context)

# ---------------- DELETE GAME ----------------

async def delete_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    storage["games"].pop(game_id, None)
    save_storage()

    await organizer_menu(query)

# ---------------- JOIN GAME ----------------

async def join_game_prompt(query):
    await query.edit_message_text("Отправь код игры:")

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text
    user_id = str(update.message.from_user.id)

    game = storage["games"].get(code)
    if not game:
        await update.message.reply_text("Игра не найдена")
        return

    if user_id in game["players"]:
        await update.message.reply_text("Ты уже в игре")
        return

    game["players"].append(user_id)
    save_storage()

    await update.message.reply_text(
        f"Ты присоединился!\n\n{game_card(game)}",
        parse_mode="HTML",
    )

# ---------------- ROUTER ----------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(role_handler, pattern="role_"))
    app.add_handler(CallbackQueryHandler(create_game, pattern="create_game"))
    app.add_handler(CallbackQueryHandler(players_menu, pattern="players_"))
    app.add_handler(CallbackQueryHandler(kick_player, pattern="kick_"))
    app.add_handler(CallbackQueryHandler(delete_game, pattern="delete_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, game_name))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, game_amount))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, join_game))

    app.run_polling()

if __name__ == "__main__":
    main()
