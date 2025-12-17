import os
import json
import uuid
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")
STATE_FILE = "storage.json"

logging.basicConfig(level=logging.INFO)

# ---------------- STORAGE ----------------

def load_storage():
    if not os.path.exists(STATE_FILE):
        return {"user_states": {}, "games": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_storage():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "user_states": user_states,
                "games": games
            },
            f,
            ensure_ascii=False,
            indent=2
        )

storage = load_storage()
user_states = storage["user_states"]
games = storage["games"]

# ---------------- UTILS ----------------

def gen_game_id():
    return str(uuid.uuid4())[:8]

def ensure_user(user_id):
    if str(user_id) not in user_states:
        user_states[str(user_id)] = {"state": "menu"}
        save_storage()

# ---------------- UI ----------------

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎁 Создать игру", callback_data="create_game")]
    ]
    await update.effective_chat.send_message(
        "🎄 Тайный Санта\n\nВыбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_game_menu(update, context, game_id):
    game = games[game_id]

    text = (
        f"🎁 Игра: {game['name']}\n"
        f"💰 Сумма: {game['amount']}\n"
        f"👥 Игроков: {len(game['players'])}"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ Название", callback_data=f"edit_name:{game_id}")],
        [InlineKeyboardButton("💰 Сумма", callback_data=f"edit_amount:{game_id}")],
        [InlineKeyboardButton("👥 Удалить игрока", callback_data=f"manage_players:{game_id}")],
        [InlineKeyboardButton("🗑 Удалить игру", callback_data=f"delete_game:{game_id}")],
        [InlineKeyboardButton("⬅️ В меню", callback_data="back_to_menu")]
    ]

    await update.effective_chat.send_message(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------------- HANDLERS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user.id)
    await show_main_menu(update, context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    data = query.data

    ensure_user(user_id)

    # CREATE GAME
    if data == "create_game":
        game_id = gen_game_id()
        games[game_id] = {
            "id": game_id,
            "name": "Тайный Санта",
            "amount": "—",
            "organizer": user_id,
            "players": [],
        }
        user_states[user_id] = {
            "state": "choose_org_participation",
            "game_id": game_id
        }
        save_storage()

        keyboard = [
            [
                InlineKeyboardButton("🎁 Участвую", callback_data="org_yes"),
                InlineKeyboardButton("🚫 Не участвую", callback_data="org_no")
            ]
        ]
        await query.message.reply_text(
            "Ты будешь участвовать в игре?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ORGANIZER PARTICIPATION
    elif data in ("org_yes", "org_no"):
        game_id = user_states[user_id]["game_id"]
        if data == "org_yes":
            games[game_id]["players"].append(user_id)

        user_states[user_id]["state"] = "menu"
        save_storage()
        await show_game_menu(update, context, game_id)

    # EDIT NAME
    elif data.startswith("edit_name:"):
        game_id = data.split(":")[1]
        user_states[user_id] = {"state": "edit_name", "game_id": game_id}
        save_storage()
        await query.message.reply_text("Введите новое название игры:")

    # EDIT AMOUNT
    elif data.startswith("edit_amount:"):
        game_id = data.split(":")[1]
        user_states[user_id] = {"state": "edit_amount", "game_id": game_id}
        save_storage()
        await query.message.reply_text("Введите новую сумму подарка:")

    # MANAGE PLAYERS
    elif data.startswith("manage_players:"):
        game_id = data.split(":")[1]
        game = games[game_id]

        keyboard = []
        for pid in game["players"]:
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ Удалить {pid}",
                    callback_data=f"remove_player:{game_id}:{pid}"
                )
            ])

        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])

        await query.message.reply_text(
            "Управление игроками:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # REMOVE PLAYER
    elif data.startswith("remove_player:"):
        _, game_id, pid = data.split(":")
        if pid in games[game_id]["players"]:
            games[game_id]["players"].remove(pid)
            save_storage()
        await show_game_menu(update, context, game_id)

    # DELETE GAME
    elif data.startswith("delete_game:"):
        game_id = data.split(":")[1]
        if game_id in games:
            del games[game_id]
            save_storage()
        await show_main_menu(update, context)

    # BACK
    elif data == "back_to_menu":
        user_states[user_id]["state"] = "menu"
        save_storage()
        await show_main_menu(update, context)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    ensure_user(user_id)

    state = user_states[user_id]["state"]
    text = update.message.text

    if state == "edit_name":
        game_id = user_states[user_id]["game_id"]
        games[game_id]["name"] = text
        user_states[user_id]["state"] = "menu"
        save_storage()
        await show_game_menu(update, context, game_id)

    elif state == "edit_amount":
        game_id = user_states[user_id]["game_id"]
        games[game_id]["amount"] = text
        user_states[user_id]["state"] = "menu"
        save_storage()
        await show_game_menu(update, context, game_id)

# ---------------- MAIN ----------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🎄 Бот Тайный Санта запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
