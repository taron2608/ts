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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 10000))
STORAGE_FILE = "storage.json"

# ------------------ ЭМОДЗИ ------------------
EMOJI = {
    "santa": "🎅",
    "gift": "🎁",
    "tree": "🎄",
    "snowflake": "❄️",
    "star": "⭐",
    "bell": "🔔",
    "party": "🎉",
    "user": "👤",
    "users": "👥",
    "money": "💰",
    "back": "⬅️",
    "trash": "🗑️",
    "edit": "✏️",
    "join": "🔗",
    "create": "✨",
    "play": "▶️",
    "list": "📋",
    "check": "✅",
    "cross": "❌",
    "info": "ℹ️",
    "link": "🔗",
    "home": "🏠",
    "crown": "👑",
    "mail": "📨",
    "lock": "🔒"
}

def escape_markdown(text):
    """Экранирует спецсимволы Markdown"""
    if not text:
        return ""
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

def get_user_html_mention(user_id, user_info):
    """Возвращает HTML-упоминание пользователя"""
    if not user_info:
        return "Анонимный Санта"
    
    name = ""
    if user_info.first_name:
        name = escape_markdown(user_info.first_name)
        if user_info.last_name:
            name += f" {escape_markdown(user_info.last_name)}"
    elif user_info.username:
        name = f"@{user_info.username}"
    else:
        name = "Анонимный Санта"
    
    return f'<a href="tg://user?id={user_id}">{name}</a>'

# ------------------ ХРАНИЛИЩЕ ------------------
def load_storage():
    if not os.path.exists(STORAGE_FILE):
        return {"games": {}, "users": {}}
    with open(STORAGE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_storage():
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(storage, f, ensure_ascii=False, indent=2)

storage = load_storage()

# ------------------ УТИЛИТЫ ------------------
def gen_game_id():
    return str(uuid.uuid4())[:8]

def get_user(uid):
    return storage["users"].setdefault(str(uid), {
        "state": None,
        "games": []
    })

def cleanup_finished_games():
    """Очищает завершенные игры из хранилища"""
    games_to_remove = []
    for game_id, game in storage["games"].items():
        if game["started"]:
            games_to_remove.append(game_id)
    
    for game_id in games_to_remove:
        # Удаляем игру из списков пользователей
        for uid, user_data in storage["users"].items():
            if "games" in user_data and game_id in user_data["games"]:
                user_data["games"].remove(game_id)
        
        # Удаляем саму игру
        del storage["games"][game_id]
    
    if games_to_remove:
        save_storage()
        print(f"Удалено завершенных игр: {len(games_to_remove)}")

# ------------------ КОМАНДЫ ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    user["state"] = None
    save_storage()

    welcome_text = (
        f"{EMOJI['gift']} <b>Тайный Санта</b>\n\n"
        f"Создай свою игру или присоединись к существующей.\n"
        f"Когда все соберутся — запусти распределение!"
    )

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
        [InlineKeyboardButton(f"{EMOJI['join']} Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")]
    ]

    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /menu для возврата в главное меню"""
    user = get_user(update.effective_user.id)
    user["state"] = None
    save_storage()

    welcome_text = (
        f"{EMOJI['gift']} <b>Главное меню</b>\n\n"
        f"Создай свою игру или присоединись к существующей.\n"
        f"Когда все соберутся — запусти распределение!"
    )

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
        [InlineKeyboardButton(f"{EMOJI['join']} Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")]
    ]

    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /cancel для отмены текущего действия"""
    user = get_user(update.effective_user.id)
    user["state"] = None
    if "tmp_name" in user:
        del user["tmp_name"]
    save_storage()
    
    await update.message.reply_text(
        f"{EMOJI['check']} Действие отменено. Используй /menu для возврата в меню."
    )

# ------------------ МОИ ИГРЫ ------------------
async def my_games_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    # Очищаем завершенные игры
    cleanup_finished_games()
    
    # Находим все активные игры пользователя
    user_games = []
    for game_id, game in storage["games"].items():
        if user_id in game["players"] and not game["started"]:
            user_games.append(game)
    
    if not user_games:
        await query.edit_message_text(
            f"{EMOJI['tree']} <b>У тебя пока нет активных игр</b>\n\n"
            f"Создай новую игру или присоединись к существующей!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
            ])
        )
        return
    
    text = f"{EMOJI['list']} <b>Твои игры</b>\n\n"
    buttons = []
    
    for game in user_games[:10]:
        is_owner = f"{EMOJI['crown']} " if game["owner"] == user_id else ""
        game_name = escape_markdown(game["name"])
        
        text += f"{is_owner}<b>{game_name}</b>\n"
        text += f"   {EMOJI['users']} {len(game['players'])} | {EMOJI['money']} {game['amount']} ₽\n\n"
        
        buttons.append([
            InlineKeyboardButton(
                f"{game_name[:15]}...",
                callback_data=f"game_{game['id']}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")
    ])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )

# ------------------ ДЕТАЛИ ИГРЫ ------------------
async def game_details_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = storage["games"].get(game_id)
    
    if not game or game["started"]:
        await query.edit_message_text(
            f"{EMOJI['cross']} Игра не найдена или уже завершена",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
                [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
            ])
        )
        return
    
    user_id = str(query.from_user.id)
    game_name = escape_markdown(game["name"])
    
    text = (
        f"{EMOJI['tree']} <b>{game_name}</b>\n"
        f"{EMOJI['money']} <b>Бюджет:</b> {game['amount']} ₽\n"
        f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}"
    )
    
    keyboard = []
    
    # Кнопки для владельца
    if user_id == game["owner"]:
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['link']} Пригласить", callback_data=f"invite_{game_id}"),
            InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
        ])
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['play']} Запустить распределение", callback_data=f"start_game_{game_id}")
        ])
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['edit']} Изменить сумму", callback_data=f"edit_amount_{game_id}"),
            InlineKeyboardButton(f"{EMOJI['trash']} Удалить игру", callback_data=f"delete_{game_id}")
        ])
    # Кнопки для участника (не владельца)
    elif user_id in game["players"]:
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton(f"{EMOJI['back']} К списку игр", callback_data="my_games"),
        InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")
    ])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# ------------------ ПРИГЛАШЕНИЕ ------------------
async def invite_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = storage["games"].get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    invite_link = f"https://t.me/{context.bot.username}?start={game_id}"
    game_name = escape_markdown(game["name"])
    
    text = (
        f"{EMOJI['gift']} <b>Приглашение в игру</b>\n\n"
        f"{EMOJI['tree']} <b>{game_name}</b>\n"
        f"{EMOJI['money']} <b>Сумма подарка:</b> {game['amount']} ₽\n"
        f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}\n\n"
        f"{EMOJI['link']} <b>Ссылка для приглашения:</b>\n"
        f"{invite_link}\n\n"
        f"{EMOJI['snowflake']} Просто отправь эту ссылку друзьям!"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['back']} Назад к игре", callback_data=f"game_{game_id}")],
        [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# ------------------ СОЗДАНИЕ ИГРЫ ------------------
async def create_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)
    user["state"] = "wait_game_name"
    save_storage()

    await query.edit_message_text(
        f"{EMOJI['create']} <b>Создание игры</b>\n\n"
        f"Придумай название для своей игры:\n"
        f"<i>Например:</i> Рождественское чудо\n\n"
        f"Введи название:\n\n"
        f"{EMOJI['info']} <i>Используй /cancel для отмены</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
        ])
    )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    user = get_user(user_id)
    
    print(f"DEBUG: User {user_id} state: {user.get('state')}")

    # ---- НАЗВАНИЕ ИГРЫ ----
    if user.get("state") == "wait_game_name":
        name = update.message.text.strip()
        if len(name) < 2:
            await update.message.reply_text(f"{EMOJI['cross']} Слишком короткое название. Минимум 2 символа:")
            return
            
        user["tmp_name"] = name
        user["state"] = "wait_game_amount"
        save_storage()
        
        # ПРОСТОЕ сообщение без форматирования
        await update.message.reply_text(
            f"{EMOJI['money']} Сумма подарка\n\nВведи сумму в рублях:\n\n"
            f"{EMOJI['info']} Используй /cancel для отмены",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
            ])
        )
        return

    # ---- БЮДЖЕТ ИГРЫ ----
    if user.get("state") == "wait_game_amount":
        if "tmp_name" not in user:
            await update.message.reply_text(
                f"{EMOJI['cross']} Ошибка. Начни заново: /menu",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            user["state"] = None
            save_storage()
            return
            
        try:
            # Чистим ввод
            text = update.message.text.strip().replace(" ", "").replace(",", ".")
            amount = float(text)
            
            if amount <= 0:
                await update.message.reply_text(
                    f"{EMOJI['cross']} Сумма должна быть больше 0. Попробуй снова:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
                    ])
                )
                return
                
            if amount > 1000000:
                await update.message.reply_text(
                    f"{EMOJI['cross']} Максимум 1,000,000 ₽. Попробуй снова:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
                    ])
                )
                return
                
        except ValueError:
            await update.message.reply_text(
                f"{EMOJI['cross']} Это не похоже на число. Пример: 1000 или 1500.50",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
                ])
            )
            return

        # Создаем игру
        game_id = gen_game_id()
        
        # Форматируем сумму
        if amount.is_integer():
            amount_str = str(int(amount))
        else:
            amount_str = f"{amount:.2f}".rstrip('0').rstrip('.')
        
        game_name = escape_markdown(user["tmp_name"])
        
        storage["games"][game_id] = {
            "id": game_id,
            "name": user["tmp_name"],
            "amount": amount_str,
            "owner": user_id,
            "players": [user_id],
            "started": False,
            "pairs": {}
        }

        # Чистим состояние
        del user["tmp_name"]
        user["state"] = None
        user.setdefault("games", []).append(game_id)
        save_storage()

        # Отправляем результат БЕЗ форматирования
        invite_link = f"https://t.me/{context.bot.username}?start={game_id}"
        
        text = (
            f"{EMOJI['tree']}✨ <b>Игра «{game_name}» готова!</b>\n\n"
            f"{EMOJI['money']} <b>Сумма:</b> {amount_str} ₽\n"
            f"{EMOJI['users']} <b>Участников:</b> 1 (включая тебя)\n\n"
            f"{EMOJI['link']} <b>Ссылка для друзей:</b>\n"
            f"{invite_link}\n\n"
            f"{EMOJI['snowflake']} Отправь ссылку друзьям!\n"
            f"{EMOJI['santa']} Когда все соберутся — запусти распределение!"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(f"{EMOJI['link']} Пригласить", callback_data=f"invite_{game_id}"),
                InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
            ],
            [InlineKeyboardButton(f"{EMOJI['play']} Запустить распределение", callback_data=f"start_game_{game_id}")],
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return
        
    # ---- ПРИСОЕДИНЕНИЕ ПО КОДУ ----
    if user.get("state") == "wait_join_code":
        game_id = update.message.text.strip()
        game = storage["games"].get(game_id)
        
        if not game:
            await update.message.reply_text(
                f"{EMOJI['cross']} Игра не найдена! Проверь код.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return

        if game["started"]:
            await update.message.reply_text(
                f"{EMOJI['cross']} Игра уже началась, присоединиться нельзя.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return

        if user_id in game["players"]:
            await update.message.reply_text(
                f"{EMOJI['info']} Ты уже в этой игре!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return

        game["players"].append(user_id)
        user["state"] = None
        user.setdefault("games", []).append(game_id)
        save_storage()
        
        game_name = escape_markdown(game["name"])
        
        await update.message.reply_text(
            f"{EMOJI['check']} <b>Ты присоединился!</b>\n\n"
            f"{EMOJI['tree']} <b>{game_name}</b>\n"
            f"{EMOJI['money']} <b>Сумма:</b> {game['amount']} ₽\n"
            f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}\n\n"
            f"{EMOJI['santa']} Ждем, когда создатель запустит распределение!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
            ])
        )
        return
        
    # ---- ИЗМЕНЕНИЕ СУММЫ ----
    if user.get("state") and user["state"].startswith("wait_new_amount_"):
        game_id = user["state"].split("_")[-1]
        
        if game_id not in storage["games"]:
            await update.message.reply_text(
                f"{EMOJI['cross']} Игра не найдена.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            user["state"] = None
            save_storage()
            return

        game = storage["games"][game_id]
        
        if user_id != game["owner"]:
            await update.message.reply_text(
                f"{EMOJI['cross']} Только создатель игры может менять сумму.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            user["state"] = None
            save_storage()
            return

        try:
            text = update.message.text.strip().replace(" ", "").replace(",", ".")
            amount = float(text)
            
            if amount <= 0:
                await update.message.reply_text(
                    f"{EMOJI['cross']} Сумма должна быть больше 0. Попробуй снова:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
                    ])
                )
                return
                
        except ValueError:
            await update.message.reply_text(
                f"{EMOJI['cross']} Это не похоже на число. Пример: 1000 или 1500.50",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
                ])
            )
            return

        # Форматируем сумму
        if amount.is_integer():
            amount_str = str(int(amount))
        else:
            amount_str = f"{amount:.2f}".rstrip('0').rstrip('.')
            
        game["amount"] = amount_str
        user["state"] = None
        save_storage()
        
        game_name = escape_markdown(game["name"])

        await update.message.reply_text(
            f"{EMOJI['check']} <b>Сумма обновлена!</b>\n\n"
            f"{EMOJI['tree']} <b>{game_name}</b>\n"
            f"{EMOJI['money']} <b>Бюджет:</b> {game['amount']} ₽\n"
            f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['back']} К игре", callback_data=f"game_{game_id}")],
                [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
            ])
        )
        return

# ------------------ ПРИСОЕДИНЕНИЕ ПО ССЫЛКЕ ------------------
async def join_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)
    user["state"] = "wait_join_code"
    save_storage()

    await query.edit_message_text(
        f"{EMOJI['join']} <b>Присоединение по коду</b>\n\n"
        f"Получи код игры у её создателя и введи его:\n\n"
        f"{EMOJI['info']} <i>Используй /cancel для отмены</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
        ])
    )

# ------------------ УЧАСТНИКИ ИГРЫ ------------------
async def players_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    game = storage["games"].get(game_id)

    if not game:
        await query.edit_message_text(
            f"{EMOJI['cross']} Игра не найдена",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
                [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
            ])
        )
        return

    # Собираем информацию об участниках в HTML
    players_text = f"{EMOJI['users']} <b>Участники ({len(game['players'])}):</b>\n\n"
    
    buttons = []
    
    for i, uid in enumerate(game["players"], 1):
        try:
            user_info = await context.bot.get_chat(int(uid))
            mention = get_user_html_mention(uid, user_info)
            
            if uid == game["owner"]:
                players_text += f"{i}. {EMOJI['crown']} {mention} <i>(создатель)</i>\n"
            else:
                players_text += f"{i}. {EMOJI['user']} {mention}\n"
            
            # Кнопка удаления для владельца (кроме себя)
            if query.from_user.id == int(game["owner"]) and uid != game["owner"]:
                name = escape_markdown(user_info.first_name or user_info.username or f"Игрок {i}")
                buttons.append([
                    InlineKeyboardButton(
                        f"{EMOJI['cross']} Удалить {name[:15]}",
                        callback_data=f"kick_{game_id}_{uid}"
                    )
                ])
                
        except Exception as e:
            print(f"Ошибка получения пользователя {uid}: {e}")
            players_text += f"{i}. Игрок {i}\n"
    
    game_name = escape_markdown(game["name"])
    text = f"{EMOJI['tree']} <b>{game_name}</b>\n\n{players_text}"

    # Кнопка назад
    buttons.append([
        InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"game_{game_id}"),
        InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")
    ])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

async def kick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, game_id, uid = query.data.split("_")
    game = storage["games"][game_id]

    if uid in game["players"]:
        try:
            user_info = await context.bot.get_chat(int(uid))
            user_name = escape_markdown(user_info.first_name or user_info.username or "Игрок")
            game["players"].remove(uid)
            save_storage()
            
            # Уведомляем удаленного участника
            try:
                await context.bot.send_message(
                    uid,
                    f"{EMOJI['cross']} <b>Тебя удалили из игры</b>\n\n"
                    f"{EMOJI['tree']} Игра: {escape_markdown(game['name'])}\n"
                    f"{EMOJI['info']} Создатель игры принял решение об твоем удалении.",
                    parse_mode="HTML"
                )
            except:
                pass
                
            await query.answer(f"✅ {user_name} удален", show_alert=True)
        except:
            game["players"].remove(uid)
            save_storage()
            await query.answer("✅ Игрок удален", show_alert=True)

    await players_cb(update, context)

# ------------------ ЗАПУСК РАСПРЕДЕЛЕНИЯ ------------------
async def start_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[2]
    game = storage["games"].get(game_id)
    
    if not game:
        await query.answer(f"{EMOJI['cross']} Игра не найдена!", show_alert=True)
        return
    
    if query.from_user.id != int(game["owner"]):
        await query.answer(f"{EMOJI['cross']} Только создатель игры может запустить распределение!", show_alert=True)
        return

    if len(game["players"]) < 2:
        await query.answer(f"{EMOJI['cross']} Нужно минимум 2 участника!", show_alert=True)
        return

    if game["started"]:
        await query.answer(f"{EMOJI['info']} Распределение уже проведено!", show_alert=True)
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
    success_count = 0
    for giver, receiver in pairs.items():
        try:
            receiver_info = await context.bot.get_chat(receiver)
            receiver_mention = get_user_html_mention(receiver, receiver_info)
            
            await context.bot.send_message(
                giver,
                f"{EMOJI['gift']} <b>Твой Тайный Санта!</b>\n\n"
                f"{EMOJI['star']} <b>Твой получатель:</b> {receiver_mention}\n"
                f"{EMOJI['money']} <b>Сумма подарка:</b> {game['amount']} ₽\n"
                f"{EMOJI['tree']} <b>Игра:</b> {escape_markdown(game['name'])}\n\n"
                f"{EMOJI['santa']} <b>Совет Санты:</b>\n"
                f"Узнай интересы получателя и прояви креативность!\n\n"
                f"Счастливого Рождества! 🎄",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            success_count += 1
        except Exception as e:
            print(f"Ошибка отправки сообщения {giver}: {e}")

    # Отправляем организатору полный список пар под спойлером
    try:
        pairs_list = f"{EMOJI['mail']} <b>Полный список пар (только для тебя):</b>\n\n"
        
        # Формируем спойлер с парами
        spoiler_content = ""
        for giver, receiver in pairs.items():
            try:
                giver_info = await context.bot.get_chat(giver)
                receiver_info = await context.bot.get_chat(receiver)
                giver_name = escape_markdown(giver_info.first_name or giver_info.username or f"Игрок {giver[:4]}")
                receiver_name = escape_markdown(receiver_info.first_name or receiver_info.username or f"Игрок {receiver[:4]}")
                
                spoiler_content += f"• {giver_name} → {receiver_name}\n"
            except:
                spoiler_content += f"• Игрок {giver[:4]}... → Игрок {receiver[:4]}...\n"
        
        # Добавляем спойлер (используем тег <tg-spoiler>)
        pairs_list += f"<tg-spoiler>{spoiler_content}</tg-spoiler>\n\n"
        pairs_list += f"{EMOJI['lock']} <i>Нажми, чтобы увидеть список</i>"
        
        await context.bot.send_message(
            game["owner"],
            pairs_list,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Ошибка отправки списка пар организатору: {e}")
        # Альтернатива без спойлера, если не поддерживается
        try:
            pairs_list_simple = f"{EMOJI['mail']} <b>Полный список пар (только для тебя):</b>\n\n"
            for giver, receiver in pairs.items():
                try:
                    giver_info = await context.bot.get_chat(giver)
                    receiver_info = await context.bot.get_chat(receiver)
                    giver_mention = get_user_html_mention(giver, giver_info)
                    receiver_mention = get_user_html_mention(receiver, receiver_info)
                    
                    pairs_list_simple += f"• {giver_mention} → {receiver_mention}\n"
                except:
                    pairs_list_simple += f"• Игрок {giver[:4]}... → Игрок {receiver[:4]}...\n"
            
            await context.bot.send_message(
                game["owner"],
                pairs_list_simple,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e2:
            print(f"Ошибка отправки альтернативного списка: {e2}")

    # Удаляем игру из общего списка
    await query.edit_message_text(
        f"{EMOJI['check']} <b>Распределение проведено!</b>\n\n"
        f"Участникам отправлены сообщения с их получателями.\n"
        f"Тебе отправлен полный список пар под спойлером.\n\n"
        f"{EMOJI['lock']} <b>Игра завершена и удалена из списка активных.</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ])
    )

# ------------------ УДАЛЕНИЕ ИГРЫ ------------------
async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    game = storage["games"].get(game_id)
    
    if not game:
        await query.answer(f"{EMOJI['cross']} Игра не найдена!", show_alert=True)
        return
    
    if query.from_user.id != int(game["owner"]):
        await query.answer(f"{EMOJI['cross']} Только создатель игры может её удалить!", show_alert=True)
        return

    # Уведомляем участников
    for uid in game["players"]:
        if uid != str(query.from_user.id):
            try:
                await context.bot.send_message(
                    uid,
                    f"{EMOJI['info']} <b>Игра удалена</b>\n\n"
                    f"{EMOJI['tree']} Игра '{escape_markdown(game['name'])}' была удалена создателем.",
                    parse_mode="HTML"
                )
            except:
                pass
    
    storage["games"].pop(game_id, None)
    save_storage()

    await query.edit_message_text(
        f"{EMOJI['check']} <b>Игра удалена</b>\n\n"
        f"Игра '{escape_markdown(game['name'])}' успешно удалена.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ])
    )

# ------------------ ИЗМЕНЕНИЕ СУММЫ ------------------
async def edit_amount_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[2]
    game = storage["games"][game_id]
    
    if query.from_user.id != int(game["owner"]):
        await query.answer(f"{EMOJI['cross']} Только создатель игры может менять сумму!", show_alert=True)
        return

    user = get_user(query.from_user.id)
    user["state"] = f"wait_new_amount_{game_id}"
    save_storage()

    await query.edit_message_text(
        f"{EMOJI['edit']} <b>Изменение суммы</b>\n\n"
        f"{EMOJI['tree']} Игра: {escape_markdown(game['name'])}\n"
        f"{EMOJI['money']} Текущая сумма: {game['amount']} ₽\n\n"
        f"Введи новую сумму:\n\n"
        f"{EMOJI['info']} <i>Используй /cancel для отмены</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
        ])
    )

# ------------------ ГЛАВНОЕ МЕНЮ (колбэк) ------------------
async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    user["state"] = None
    if "tmp_name" in user:
        del user["tmp_name"]
    save_storage()

    welcome_text = (
        f"{EMOJI['gift']} <b>Тайный Санта</b>\n\n"
        f"Создай свою игру или присоединись к существующей.\n"
        f"Когда все соберутся — запусти распределение!"
    )

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
        [InlineKeyboardButton(f"{EMOJI['join']} Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")]
    ]

    await query.edit_message_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# ------------------ ОБРАБОТКА ПРИГЛАСИТЕЛЬНОЙ ССЫЛКИ ------------------
async def handle_start_with_param(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start с параметром (пригласительная ссылка)"""
    args = context.args
    if args and len(args[0]) == 8:  # Длина game_id
        game_id = args[0]
        game = storage["games"].get(game_id)
        
        if not game:
            await update.message.reply_text(
                f"{EMOJI['cross']} <b>Игра не найдена!</b>\n\n"
                f"Ссылка устарела или игра была удалена.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return
        
        if game["started"]:
            await update.message.reply_text(
                f"{EMOJI['cross']} <b>Игра уже началась!</b>\n\n"
                f"Распределение уже проведено, присоединиться нельзя.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return
        
        user_id = str(update.effective_user.id)
        
        if user_id in game["players"]:
            await update.message.reply_text(
                f"{EMOJI['info']} <b>Ты уже в игре!</b>\n\n"
                f"{EMOJI['tree']} <b>{escape_markdown(game['name'])}</b>\n"
                f"{EMOJI['money']} <b>Сумма:</b> {game['amount']} ₽\n"
                f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}\n\n"
                f"Ждем начала распределения!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return
        
        # Добавляем в игру
        game["players"].append(user_id)
        user = get_user(user_id)
        user.setdefault("games", []).append(game_id)
        save_storage()
        
        # Уведомляем создателя
        try:
            await context.bot.send_message(
                game["owner"],
                f"{EMOJI['bell']} <b>Новый участник!</b>\n\n"
                f"К игре '{escape_markdown(game['name'])}' присоединился новый участник.\n"
                f"{EMOJI['users']} Теперь участников: {len(game['players'])}",
                parse_mode="HTML"
            )
        except:
            pass
        
        await update.message.reply_text(
            f"{EMOJI['check']} <b>Ты присоединился к игре!</b>\n\n"
            f"{EMOJI['tree']} <b>{escape_markdown(game['name'])}</b>\n"
            f"{EMOJI['money']} <b>Сумма:</b> {game['amount']} ₽\n"
            f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}\n\n"
            f"{EMOJI['santa']} Ждем, когда создатель запустит распределение!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
            ])
        )
    else:
        await start(update, context)

# ------------------ WEBHOOK & FASTAPI ------------------
application = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan контекст для FastAPI"""
    global application
    
    print("🎅 Инициализация Тайного Санты...")
    
    # Очищаем завершенные игры при старте
    cleanup_finished_games()
    
    # Создаем и инициализируем Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", handle_start_with_param))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(create_game_cb, pattern="create_game"))
    application.add_handler(CallbackQueryHandler(join_game_cb, pattern="join_game"))
    application.add_handler(CallbackQueryHandler(my_games_cb, pattern="my_games"))
    application.add_handler(CallbackQueryHandler(game_details_cb, pattern="game_"))
    application.add_handler(CallbackQueryHandler(invite_cb, pattern="invite_"))
    application.add_handler(CallbackQueryHandler(players_cb, pattern="players_"))
    application.add_handler(CallbackQueryHandler(kick_cb, pattern="kick_"))
    application.add_handler(CallbackQueryHandler(delete_cb, pattern="delete_"))
    application.add_handler(CallbackQueryHandler(edit_amount_cb, pattern="edit_amount_"))
    application.add_handler(CallbackQueryHandler(start_game_cb, pattern="start_game_"))
    application.add_handler(CallbackQueryHandler(main_menu_cb, pattern="main_menu"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    # Инициализируем Application
    await application.initialize()
    
    # Устанавливаем webhook
    if WEBHOOK_URL:
        await application.bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook установлен на {WEBHOOK_URL}")
    
    print("✅ Тайный Санта готов!")
    
    yield
    
    print("🎄 Остановка бота...")
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
        "message": "🎅 Тайный Санта работает",
        "games_count": len(storage["games"])
    }

# ------------------ MAIN ------------------
def main():
    """Запуск FastAPI приложения"""
    print(f"🎄 Запуск на порту {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
