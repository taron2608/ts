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
    "crown": "👑"
}

def escape_markdown(text):
    """Экранирует спецсимволы Markdown"""
    if not text:
        return ""
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

def format_user_name(user_info):
    """Форматирование имени пользователя"""
    if not user_info:
        return "Анонимный Санта"
    
    if user_info.first_name and user_info.last_name:
        name = f"{user_info.first_name} {user_info.last_name}"
    elif user_info.first_name:
        name = user_info.first_name
    elif user_info.username:
        name = f"@{user_info.username}"
    else:
        name = "Анонимный Санта"
    
    return escape_markdown(name)

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

# ------------------ ГЛАВНОЕ МЕНЮ ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    user["state"] = None
    save_storage()

    welcome_text = (
        f"{EMOJI['gift']} *Тайный Санта*\n\n"
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
        parse_mode="Markdown"
    )

# ------------------ МОИ ИГРЫ ------------------
async def my_games_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    # Находим все игры пользователя
    user_games = []
    for game_id, game in storage["games"].items():
        if user_id in game["players"]:
            user_games.append(game)
    
    if not user_games:
        await query.edit_message_text(
            f"{EMOJI['tree']} У тебя пока нет игр\n\nСоздай новую игру или присоединись к существующей!"
        )
        return
    
    text = f"{EMOJI['list']} *Твои игры*\n\n"
    buttons = []
    
    for game in user_games[:10]:
        is_owner = f"{EMOJI['crown']} " if game["owner"] == user_id else ""
        status = "🟢" if not game["started"] else "🟣"
        game_name = escape_markdown(game["name"])
        
        text += f"{status} {is_owner}*{game_name}*\n"
        text += f"   {EMOJI['users']} {len(game['players'])} | {EMOJI['money']} {game['amount']} ₽\n\n"
        
        buttons.append([
            InlineKeyboardButton(
                f"{status} {game_name[:15]}",
                callback_data=f"game_{game['id']}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(f"{EMOJI['home']} Назад", callback_data="main_menu")
    ])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

# ------------------ ДЕТАЛИ ИГРЫ ------------------
async def game_details_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = storage["games"].get(game_id)
    
    if not game:
        await query.edit_message_text(f"{EMOJI['cross']} Игра не найдена")
        return
    
    user_id = str(query.from_user.id)
    game_name = escape_markdown(game["name"])
    
    status = "🟢 Активна" if not game["started"] else "🟣 Распределено"
    text = (
        f"{EMOJI['tree']} *{game_name}*\n"
        f"{EMOJI['money']} *Бюджет:* {game['amount']} ₽\n"
        f"{EMOJI['users']} *Участников:* {len(game['players'])}\n"
        f"{EMOJI['star']} *Статус:* {status}"
    )
    
    keyboard = []
    
    # Кнопки для владельца
    if user_id == game["owner"]:
        if not game["started"]:
            keyboard.append([
                InlineKeyboardButton(f"{EMOJI['link']} Пригласить", callback_data=f"invite_{game_id}"),
                InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
            ])
            keyboard.append([
                InlineKeyboardButton(f"{EMOJI['play']} Запустить распределение", callback_data=f"start_game_{game_id}")
            ])
            keyboard.append([
                InlineKeyboardButton(f"{EMOJI['edit']} Изменить сумму", callback_data=f"edit_amount_{game_id}"),
                InlineKeyboardButton(f"{EMOJI['trash']} Удалить", callback_data=f"delete_{game_id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
            ])
    
    # Кнопки для участника (не владельца)
    elif user_id in game["players"]:
        if game["started"] and user_id in game.get("pairs", {}):
            keyboard.append([
                InlineKeyboardButton(
                    f"{EMOJI['gift']} Мой получатель",
                    callback_data=f"receiver_{game_id}"
                )
            ])
    
    keyboard.append([
        InlineKeyboardButton(f"{EMOJI['back']} К списку игр", callback_data="my_games"),
        InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")
    ])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
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
        f"{EMOJI['gift']} *Приглашение в игру*\n\n"
        f"{EMOJI['tree']} *{game_name}*\n"
        f"{EMOJI['money']} *Сумма подарка:* {game['amount']} ₽\n"
        f"{EMOJI['users']} *Участников:* {len(game['players'])}\n\n"
        f"{EMOJI['link']} *Ссылка для приглашения:*\n"
        f"{invite_link}\n\n"
        f"{EMOJI['snowflake']} Просто отправь эту ссылку друзьям!"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"game_{game_id}")],
        [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ------------------ СОЗДАНИЕ ИГРЫ ------------------
async def create_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)
    user["state"] = "wait_game_name"
    save_storage()

    await query.edit_message_text(
        f"{EMOJI['create']} *Создание игры*\n\n"
        f"Придумай название для своей игры:\n"
        f"_Например:_ Рождественское чудо\n\n"
        f"Введи название:",
        parse_mode="Markdown"
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
        
        # ПРОСТОЕ сообщение без сложного форматирования
        await update.message.reply_text(
            f"{EMOJI['money']} Сумма подарка\n\nВведи сумму в рублях:"
        )
        return

    # ---- БЮДЖЕТ ИГРЫ ----
    if user.get("state") == "wait_game_amount":
        if "tmp_name" not in user:
            await update.message.reply_text(f"{EMOJI['cross']} Ошибка. Начни заново: /start")
            user["state"] = None
            save_storage()
            return
            
        try:
            # Чистим ввод
            text = update.message.text.strip().replace(" ", "").replace(",", ".")
            amount = float(text)
            
            if amount <= 0:
                await update.message.reply_text(f"{EMOJI['cross']} Сумма должна быть больше 0. Попробуй снова:")
                return
                
            if amount > 1000000:
                await update.message.reply_text(f"{EMOJI['cross']} Максимум 1,000,000 ₽. Попробуй снова:")
                return
                
        except ValueError:
            await update.message.reply_text(f"{EMOJI['cross']} Это не похоже на число. Пример: 1000 или 1500.50")
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
            "name": user["tmp_name"],  # Оригинальное имя
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

        # Отправляем результат (ПРОСТОЙ формат без Markdown)
        invite_link = f"https://t.me/{context.bot.username}?start={game_id}"
        
        text = (
            f"{EMOJI['tree']}✨ Игра «{game_name}» готова!\n\n"
            f"{EMOJI['money']} Сумма: {amount_str} ₽\n"
            f"{EMOJI['users']} Участников: 1 (включая тебя)\n\n"
            f"{EMOJI['link']} Ссылка для друзей:\n"
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
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")]
        ]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
        
    # ---- ПРИСОЕДИНЕНИЕ ПО КОДУ ----
    if user.get("state") == "wait_join_code":
        game_id = update.message.text.strip()
        game = storage["games"].get(game_id)
        
        if not game:
            await update.message.reply_text(f"{EMOJI['cross']} Игра не найдена! Проверь код.")
            return

        if game["started"]:
            await update.message.reply_text(f"{EMOJI['cross']} Игра уже началась, присоединиться нельзя.")
            return

        if user_id in game["players"]:
            await update.message.reply_text(f"{EMOJI['info']} Ты уже в этой игре!")
            return

        game["players"].append(user_id)
        user["state"] = None
        user.setdefault("games", []).append(game_id)
        save_storage()
        
        game_name = escape_markdown(game["name"])
        
        await update.message.reply_text(
            f"{EMOJI['check']} Ты присоединился!\n\n"
            f"{EMOJI['tree']} {game_name}\n"
            f"{EMOJI['money']} Сумма: {game['amount']} ₽\n"
            f"{EMOJI['users']} Участников: {len(game['players'])}\n\n"
            f"{EMOJI['santa']} Ждем начала распределения!"
        )
        return
        
    # ---- ИЗМЕНЕНИЕ СУММЫ ----
    if user.get("state") and user["state"].startswith("wait_new_amount_"):
        game_id = user["state"].split("_")[-1]
        
        if game_id not in storage["games"]:
            await update.message.reply_text(f"{EMOJI['cross']} Игра не найдена.")
            user["state"] = None
            save_storage()
            return

        game = storage["games"][game_id]
        
        if user_id != game["owner"]:
            await update.message.reply_text(f"{EMOJI['cross']} Только создатель игры может менять сумму.")
            user["state"] = None
            save_storage()
            return

        try:
            text = update.message.text.strip().replace(" ", "").replace(",", ".")
            amount = float(text)
            
            if amount <= 0:
                await update.message.reply_text(f"{EMOJI['cross']} Сумма должна быть больше 0. Попробуй снова:")
                return
                
        except ValueError:
            await update.message.reply_text(f"{EMOJI['cross']} Это не похоже на число. Пример: 1000 или 1500.50")
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
            f"{EMOJI['check']} Сумма обновлена!\n\n"
            f"{EMOJI['tree']} {game_name}\n"
            f"{EMOJI['money']} Бюджет: {game['amount']} ₽\n"
            f"{EMOJI['users']} Участников: {len(game['players'])}"
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
        f"{EMOJI['join']} *Присоединение по коду*\n\n"
        f"Получи код игры у её создателя и введи его:"
    )

# ------------------ УЧАСТНИКИ ИГРЫ ------------------
async def players_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    game = storage["games"][game_id]

    # Собираем информацию об участниках
    players_text = f"{EMOJI['users']} *Участники ({len(game['players'])}):*\n\n"
    
    buttons = []
    
    for i, uid in enumerate(game["players"], 1):
        try:
            user_info = await context.bot.get_chat(int(uid))
            name = format_user_name(user_info)
            
            if uid == game["owner"]:
                players_text += f"{i}. {EMOJI['crown']} *{name}* (создатель)\n"
            else:
                players_text += f"{i}. {name}\n"
            
            # Кнопка удаления для владельца (кроме себя)
            if query.from_user.id == int(game["owner"]) and uid != game["owner"]:
                buttons.append([
                    InlineKeyboardButton(
                        f"{EMOJI['cross']} Удалить {name[:15]}",
                        callback_data=f"kick_{game_id}_{uid}"
                    )
                ])
                
        except:
            players_text += f"{i}. Игрок {i}\n"
    
    game_name = escape_markdown(game["name"])
    text = f"{EMOJI['tree']} *{game_name}*\n\n{players_text}"

    # Кнопка назад
    buttons.append([
        InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"game_{game_id}"),
        InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")
    ])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

async def kick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, game_id, uid = query.data.split("_")
    game = storage["games"][game_id]

    if uid in game["players"]:
        try:
            user_info = await context.bot.get_chat(int(uid))
            user_name = format_user_name(user_info)
            game["players"].remove(uid)
            save_storage()
            
            # Уведомляем удаленного участника
            try:
                await context.bot.send_message(
                    uid,
                    f"{EMOJI['cross']} *Тебя удалили из игры*\n\n"
                    f"{EMOJI['tree']} Игра: {escape_markdown(game['name'])}\n"
                    f"{EMOJI['info']} Создатель игры принял решение об твоем удалении."
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
    game = storage["games"][game_id]
    
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
            receiver_name = format_user_name(receiver_info)
            
            await context.bot.send_message(
                giver,
                f"{EMOJI['gift']} *Твой Тайный Санта!*\n\n"
                f"{EMOJI['star']} *Твой получатель:* {receiver_name}\n"
                f"{EMOJI['money']} *Сумма подарка:* {game['amount']} ₽\n"
                f"{EMOJI['tree']} *Игра:* {escape_markdown(game['name'])}\n\n"
                f"{EMOJI['santa']} *Совет Санты:*\n"
                f"Узнай интересы получателя и прояви креативность!\n\n"
                f"Счастливого Рождества! 🎄"
            )
            success_count += 1
        except Exception as e:
            print(f"Ошибка отправки сообщения {giver}: {e}")

    await query.edit_message_text(
        f"{EMOJI['check']} *Распределение проведено!*\n\n"
        f"Участникам отправлены сообщения с их получателями.\n\n"
        f"{EMOJI['tree']} *Игра:* {escape_markdown(game['name'])}\n"
        f"{EMOJI['users']} *Участников:* {len(game['players'])}\n"
        f"{EMOJI['money']} *Сумма:* {game['amount']} ₽"
    )

# ------------------ УДАЛЕНИЕ ИГРЫ ------------------
async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[1]
    game = storage["games"][game_id]
    
    if query.from_user.id != int(game["owner"]):
        await query.answer(f"{EMOJI['cross']} Только создатель игры может её удалить!", show_alert=True)
        return

    # Уведомляем участников
    for uid in game["players"]:
        if uid != str(query.from_user.id):
            try:
                await context.bot.send_message(
                    uid,
                    f"{EMOJI['info']} *Игра удалена*\n\n"
                    f"{EMOJI['tree']} Игра '{escape_markdown(game['name'])}' была удалена создателем."
                )
            except:
                pass
    
    storage["games"].pop(game_id, None)
    save_storage()

    await query.edit_message_text(
        f"{EMOJI['check']} *Игра удалена*\n\n"
        f"Игра '{escape_markdown(game['name'])}' успешно удалена."
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
        f"{EMOJI['edit']} *Изменение суммы*\n\n"
        f"{EMOJI['tree']} Игра: {escape_markdown(game['name'])}\n"
        f"{EMOJI['money']} Текущая сумма: {game['amount']} ₽\n\n"
        f"Введи новую сумму:"
    )

# ------------------ ГЛАВНОЕ МЕНЮ (колбэк) ------------------
async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    user["state"] = None
    save_storage()

    welcome_text = (
        f"{EMOJI['gift']} *Тайный Санта*\n\n"
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
        parse_mode="Markdown"
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
                f"{EMOJI['cross']} *Игра не найдена!*\n\n"
                f"Ссылка устарела или игра была удалена.",
                parse_mode="Markdown"
            )
            return
        
        if game["started"]:
            await update.message.reply_text(
                f"{EMOJI['cross']} *Игра уже началась!*\n\n"
                f"Распределение уже проведено, присоединиться нельзя.",
                parse_mode="Markdown"
            )
            return
        
        user_id = str(update.effective_user.id)
        
        if user_id in game["players"]:
            await update.message.reply_text(
                f"{EMOJI['info']} *Ты уже в игре!*\n\n"
                f"{EMOJI['tree']} *{escape_markdown(game['name'])}*\n"
                f"{EMOJI['money']} *Сумма:* {game['amount']} ₽\n"
                f"{EMOJI['users']} *Участников:* {len(game['players'])}\n\n"
                f"Ждем начала распределения!",
                parse_mode="Markdown"
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
                f"{EMOJI['bell']} *Новый участник!*\n\n"
                f"К игре '{escape_markdown(game['name'])}' присоединился новый участник.\n"
                f"{EMOJI['users']} Теперь участников: {len(game['players'])}"
            )
        except:
            pass
        
        await update.message.reply_text(
            f"{EMOJI['check']} *Ты присоединился к игре!*\n\n"
            f"{EMOJI['tree']} *{escape_markdown(game['name'])}*\n"
            f"{EMOJI['money']} *Сумма:* {game['amount']} ₽\n"
            f"{EMOJI['users']} *Участников:* {len(game['players'])}\n\n"
            f"{EMOJI['santa']} Ждем, когда создатель запустит распределение!",
            parse_mode="Markdown"
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
    
    # Создаем и инициализируем Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", handle_start_with_param))
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
