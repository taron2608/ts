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
FAQ_CHANNEL_LINK = "https://t.me/ssr_faq"  # Ссылка на ваш канал

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
"lock": "🔒",
"wish": "🎯",
"not_wish": "🙅",
    "preferences": "📝",
    "help": "❓"
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
uid_str = str(uid)
if uid_str not in storage["users"]:
storage["users"][uid_str] = {
"state": None,
"games": [],
            "wishes": {},  # Хранит пожелания по играм: {game_id: {"wish": "", "not_wish": ""}}
            "preferences": {}  # Хранит предпочтения по играм
}
return storage["users"][uid_str]

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
            
            # Удаляем пожелания для этой игры
if "wishes" in user_data and game_id in user_data["wishes"]:
del user_data["wishes"][game_id]
            
if "preferences" in user_data and game_id in user_data["preferences"]:
del user_data["preferences"][game_id]

        # Удаляем саму игру
del storage["games"][game_id]

if games_to_remove:
save_storage()
print(f"Удалено завершенных игр: {len(games_to_remove)}")

# ------------------ КОМАНДЫ ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
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
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
        [InlineKeyboardButton(f"{EMOJI['help']} FAQ и инструкции", url=FAQ_CHANNEL_LINK)],
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
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
        [InlineKeyboardButton(f"{EMOJI['help']} FAQ и инструкции", url=FAQ_CHANNEL_LINK)],
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
if "tmp_game_id" in user:
del user["tmp_game_id"]
save_storage()

await update.message.reply_text(
f"{EMOJI['check']} Действие отменено. Используй /menu для возврата в меню."
)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help с ссылкой на канал"""
    help_text = (
        f"{EMOJI['help']} <b>Помощь и инструкции</b>\n\n"
        f"📚 <b>Полные инструкции здесь:</b>\n"
        f"{FAQ_CHANNEL_LINK}\n\n"
        f"🎯 <b>Быстрый старт:</b>\n"
        f"1. Создай игру или присоединись\n"
        f"2. Укажи пожелания для Санты\n"
        f"3. Жди распределения\n\n"
        f"🤖 <b>Основные команды:</b>\n"
        f"/start - Начать работу\n"
        f"/menu - Главное меню\n"
        f"/cancel - Отменить действие\n"
        f"/help - Эта справка"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['link']} Перейти в FAQ канал", url=FAQ_CHANNEL_LINK)],
        [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
    ]
    
    await update.message.reply_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
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
        
        buttons.append([InlineKeyboardButton(f"{game_name[:15]}...", callback_data=f"game_{game['id']}")])

    buttons.append([InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")])

await query.edit_message_text(
text,
reply_markup=InlineKeyboardMarkup(buttons),
parse_mode="HTML"
)

# ==================== ВОССТАНОВЛЕННЫЕ ОБРАБОТЧИКИ КНОПОК ====================

# ------------------ ПРИСОЕДИНЕНИЕ ------------------
async def join_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Присоединиться' из главного меню"""
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    user["state"] = "wait_join_code"
    save_storage()
    
    await query.edit_message_text(
        f"{EMOJI['info']} <b>Для присоединения к игре нужна ссылка от организатора</b>\n\n"
        f"{EMOJI['santa']} Попроси у организатора игры ссылку-приглашение и просто перейди по ней!\n\n"
        f"Если ты организатор — создай новую игру или зайди в свои существующие игры.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ])
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

    # Проверяем, есть ли у пользователя пожелания для этой игры
user = get_user(user_id)
has_wishes = False
if "wishes" in user and game_id in user["wishes"]:
wishes = user["wishes"][game_id]
if wishes.get("wish") or wishes.get("not_wish"):
has_wishes = True

keyboard = []

    # Кнопки для владельца
if user_id == game["owner"]:
keyboard.append([
InlineKeyboardButton(f"{EMOJI['link']} Пригласить", callback_data=f"invite_{game_id}"),
InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
])
        keyboard.append([InlineKeyboardButton(f"{EMOJI['play']} Запустить распределение", callback_data=f"start_game_{game_id}")])
keyboard.append([
InlineKeyboardButton(f"{EMOJI['edit']} Изменить сумму", callback_data=f"edit_amount_{game_id}"),
InlineKeyboardButton(f"{EMOJI['trash']} Удалить игру", callback_data=f"delete_{game_id}")
])
    # Кнопки для участника (не владельца)
elif user_id in game["players"]:
keyboard.append([
InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
])

    # Кнопка пожеланий для ВСЕХ участников (включая организатора)
if user_id in game["players"]:
wish_button_text = f"{EMOJI['preferences']} Мои пожелания" if has_wishes else f"{EMOJI['wish']} Указать пожелания"
        keyboard.append([InlineKeyboardButton(wish_button_text, callback_data=f"wish_{game_id}")])

keyboard.append([
InlineKeyboardButton(f"{EMOJI['back']} К списку игр", callback_data="my_games"),
InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")
])

await query.edit_message_text(
text,
reply_markup=InlineKeyboardMarkup(keyboard),
parse_mode="HTML"
)

# ------------------ УЧАСТНИКИ ИГРЫ ------------------
async def players_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Участники'"""
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
    
    players_text = f"{EMOJI['users']} <b>Участники ({len(game['players'])}):</b>\n\n"
    buttons = []
    
    for i, uid in enumerate(game["players"], 1):
        try:
            user_info = await context.bot.get_chat(int(uid))
            mention = get_user_html_mention(uid, user_info)
            
            # Проверяем, есть ли пожелания у пользователя
            user = get_user(uid)
            has_wishes = False
            if "wishes" in user and game_id in user["wishes"]:
                wishes = user["wishes"][game_id]
                if wishes.get("wish") or wishes.get("not_wish"):
                    has_wishes = True
            
            if uid == game["owner"]:
                players_text += f"{i}. {EMOJI['crown']} {mention}"
                if has_wishes:
                    players_text += f" {EMOJI['wish']}"
            else:
                players_text += f"{i}. {EMOJI['user']} {mention}"
                if has_wishes:
                    players_text += f" {EMOJI['wish']}"
            
            players_text += "\n"
            
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
    
    if query.from_user.id == int(game["owner"]):
        text += f"\n{EMOJI['wish']} - участник указал пожелания"
    
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
    """Обработчик удаления участника"""
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

# ------------------ ИЗМЕНЕНИЕ СУММЫ ------------------
async def edit_amount_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Изменить сумму'"""
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

# ------------------ ЗАПУСК РАСПРЕДЕЛЕНИЯ ------------------
async def start_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Запустить распределение'"""
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
            
            # Получаем пожелания получателя
            receiver_wishes = ""
            receiver_user = get_user(receiver)
            if "wishes" in receiver_user and game_id in receiver_user["wishes"]:
                wishes = receiver_user["wishes"][game_id]
                if wishes.get("wish"):
                    receiver_wishes += f"\n{EMOJI['wish']} <b>Хочет получить:</b>\n{wishes['wish']}\n"
                if wishes.get("not_wish"):
                    receiver_wishes += f"\n{EMOJI['not_wish']} <b>Не хочет получать:</b>\n{wishes['not_wish']}\n"
            
            message_text = (
                f"{EMOJI['gift']} <b>Твой Тайный Санта!</b>\n\n"
                f"{EMOJI['star']} <b>Твой получатель:</b> {receiver_mention}\n"
                f"{EMOJI['money']} <b>Сумма подарка:</b> {game['amount']} ₽\n"
                f"{EMOJI['tree']} <b>Игра:</b> {escape_markdown(game['name'])}"
            )
            
            if receiver_wishes:
                message_text += f"\n\n{EMOJI['info']} <b>Пожелания получателя:</b>{receiver_wishes}"
            
            message_text += (
                f"\n\n{EMOJI['santa']} <b>Совет Санты:</b>\n"
                f"Узнай интересы получателя и прояви креативность!\n\n"
                f"Счастливого Рождества! 🎄"
            )
            
            await context.bot.send_message(
                giver,
                message_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            success_count += 1
        except Exception as e:
            print(f"Ошибка отправки сообщения {giver}: {e}")
    
    # Отправляем организатору полный список пар
    try:
        pairs_list = f"{EMOJI['mail']} <b>Полный список пар (только для тебя):</b>\n\n"
        for giver, receiver in pairs.items():
            try:
                giver_info = await context.bot.get_chat(giver)
                receiver_info = await context.bot.get_chat(receiver)
                giver_mention = get_user_html_mention(giver, giver_info)
                receiver_mention = get_user_html_mention(receiver, receiver_info)
                
                pairs_list += f"• {giver_mention} → {receiver_mention}\n"
            except:
                pairs_list += f"• Игрок {giver[:4]}... → Игрок {receiver[:4]}...\n"
        
        await context.bot.send_message(
            game["owner"],
            pairs_list,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Ошибка отправки списка пар организатору: {e}")
    
    # Уведомляем участников, которые не указали пожелания
    for uid in game["players"]:
        user = get_user(uid)
        if "wishes" not in user or game_id not in user["wishes"] or not user["wishes"][game_id].get("wish"):
            try:
                await context.bot.send_message(
                    uid,
                    f"{EMOJI['info']} <b>Напоминание о пожеланиях</b>\n\n"
                    f"{EMOJI['tree']} Игра '{escape_markdown(game['name'])}' началась!\n\n"
                    f"{EMOJI['santa']} К сожалению, ты не указал(а) свои пожелания для подарка.\n"
                    f"Твой Тайный Санта не будет знать, что тебе подарить.\n\n"
                    f"{EMOJI['wish']} <b>Что можно сделать:</b>\n"
                    f"• Напиши своему Санте в личные сообщения\n"
                    f"• Расскажи о своих интересах и предпочтениях\n"
                    f"• Предложи идеи для подарка\n\n"
                    f"Удачного обмена подарками! 🎁",
                    parse_mode="HTML"
                )
            except:
                pass
    
    # Удаляем игру из общего списка
    await query.edit_message_text(
        f"{EMOJI['check']} <b>Распределение проведено!</b>\n\n"
        f"Участникам отправлены сообщения с их получателями.\n"
        f"Тебе отправлен полный список пар.\n\n"
        f"{EMOJI['lock']} <b>Игра завершена и удалена из списка активных.</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ])
    )

# ------------------ УДАЛЕНИЕ ИГРЫ ------------------
async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Удалить игру'"""
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

# ------------------ УПРАВЛЕНИЕ ПОЖЕЛАНИЯМИ ------------------
async def wish_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Указать пожелания'"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = storage["games"].get(game_id)
    
    if not game:
        await query.answer(f"{EMOJI['cross']} Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    
    if user_id not in game["players"]:
        await query.answer(f"{EMOJI['cross']} Ты не участник этой игры!", show_alert=True)
        return
    
    user = get_user(user_id)
    
    # Проверяем текущие пожелания
    current_wishes = user.get("wishes", {}).get(game_id, {})
    wish_text = current_wishes.get("wish", "")
    not_wish_text = current_wishes.get("not_wish", "")
    
    if wish_text or not_wish_text:
        # Показываем текущие пожелания
        game_name = escape_markdown(game["name"])
        text = f"{EMOJI['preferences']} <b>Твои пожелания для игры:</b>\n\n"
        text += f"{EMOJI['tree']} <b>{game_name}</b>\n\n"
        
        if wish_text:
            text += f"{EMOJI['wish']} <b>Хочу получить:</b>\n{wish_text}\n\n"
        else:
            text += f"{EMOJI['wish']} <b>Хочу получить:</b>\nНе указано\n\n"
        
        if not_wish_text:
            text += f"{EMOJI['not_wish']} <b>Не хочу получать:</b>\n{not_wish_text}\n"
        else:
            text += f"{EMOJI['not_wish']} <b>Не хочу получать:</b>\nНе указано\n"
        
        text += f"\n{EMOJI['info']} Эти пожелания увидит твой Тайный Санта после распределения."
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['edit']} Изменить пожелания", callback_data=f"edit_wish_{game_id}")],
            [InlineKeyboardButton(f"{EMOJI['check']} Оставить как есть", callback_data=f"game_{game_id}")],
            [InlineKeyboardButton(f"{EMOJI['trash']} Удалить пожелания", callback_data=f"delete_wish_{game_id}")],
            [InlineKeyboardButton(f"{EMOJI['back']} Назад к игре", callback_data=f"game_{game_id}")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    else:
        # Нет пожеланий, начинаем процесс их создания
        user["state"] = f"wait_wish_want_{game_id}"
        save_storage()
        
        await query.edit_message_text(
            f"{EMOJI['wish']} <b>Укажи свои пожелания для подарка</b>\n\n"
            f"{EMOJI['tree']} Игра: {escape_markdown(game['name'])}\n"
            f"{EMOJI['money']} Бюджет: {game['amount']} ₽\n\n"
            f"Напиши, что бы ты хотел(а) получить:\n\n"
            f"{EMOJI['info']} Примеры:\n"
            f"• Книга по программированию\n"
            f"• Тёплый шарф\n"
            f"• Набор для рисования\n"
            f"• Сюрприз\n\n"
            f"Можно написать несколько пунктов.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
            ])
        )

async def edit_wish_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Изменить пожелания'"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[2]
    game = storage["games"].get(game_id)
    
    if not game:
        await query.answer(f"{EMOJI['cross']} Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    user = get_user(user_id)
    user["state"] = f"wait_wish_want_{game_id}"
    save_storage()
    
    await query.edit_message_text(
        f"{EMOJI['edit']} <b>Изменение пожеланий</b>\n\n"
        f"{EMOJI['tree']} Игра: {escape_markdown(game['name'])}\n\n"
        f"Напиши, что бы ты хотел(а) получить:\n\n"
        f"{EMOJI['info']} Примеры:\n"
        f"• Книга по программированию\n"
        f"• Тёплый шарф\n"
        f"• Набор для рисования\n"
        f"• Сюрприз\n\n"
        f"Можно написать несколько пунктов.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
        ])
    )

async def delete_wish_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Удалить пожелания'"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[2]
    game = storage["games"].get(game_id)
    
    if not game:
        await query.answer(f"{EMOJI['cross']} Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    user = get_user(user_id)
    
    if "wishes" in user and game_id in user["wishes"]:
        del user["wishes"][game_id]
        save_storage()
    
    await query.answer("✅ Пожелания удалены", show_alert=True)
    await wish_cb(update, context)

async def skip_not_wish_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Пропустить' (не хочу получать)"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[3]
    game = storage["games"].get(game_id)
    
    if not game:
        await query.answer(f"{EMOJI['cross']} Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    user = get_user(user_id)
    
    user.setdefault("wishes", {}).setdefault(game_id, {})["not_wish"] = ""
    user["state"] = None
    save_storage()
    
    game_name = escape_markdown(game["name"])
    
    await query.edit_message_text(
        f"{EMOJI['check']} <b>Пожелания сохранены!</b>\n\n"
        f"{EMOJI['tree']} <b>{game_name}</b>\n\n"
        f"Теперь твой Тайный Санта будет знать, что ты хочешь получить в подарок! 🎁",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['back']} К игре", callback_data=f"game_{game_id}")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ])
    )

# ==================== КОНЕЦ ВОССТАНОВЛЕННЫХ ОБРАБОТЧИКОВ ====================

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

# ------------------ ТЕКСТОВЫЙ ОБРАБОТЧИК ------------------
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

del user["tmp_name"]
user["state"] = None
user.setdefault("games", []).append(game_id)
save_storage()

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
[InlineKeyboardButton(f"{EMOJI['wish']} Указать пожелания", callback_data=f"wish_{game_id}")],
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
await update.message.reply_text(
f"{EMOJI['info']} <b>Для присоединения к игре нужна ссылка от организатора</b>\n\n"
f"{EMOJI['santa']} Попроси у организатора игры ссылку-приглашение и просто перейди по ней!\n\n"
f"Если ты организатор — создай новую игру или зайди в свои существующие игры.",
parse_mode="HTML",
reply_markup=InlineKeyboardMarkup([
[InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
[InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
[InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
])
)
user["state"] = None
save_storage()
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

# ---- ПОЖЕЛАНИЯ: ХОЧУ ----
if user.get("state") and user["state"].startswith("wait_wish_want_"):
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

wish_text = update.message.text.strip()
if len(wish_text) > 500:
await update.message.reply_text(
f"{EMOJI['cross']} Слишком длинный текст. Максимум 500 символов.",
reply_markup=InlineKeyboardMarkup([
[InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
])
)
return

user.setdefault("wishes", {}).setdefault(game_id, {})["wish"] = wish_text
user["state"] = f"wait_wish_not_{game_id}"
save_storage()

await update.message.reply_text(
f"{EMOJI['check']} <b>Отлично!</b> А теперь напиши, что бы ты НЕ хотел(а) получить:\n\n"
f"{EMOJI['info']} Примеры:\n"
f"• Не нужно дарить сладости\n"
f"• Не люблю красный цвет\n"
f"• Не дарите носки, пожалуйста\n\n"
f"Можно написать несколько пунктов или оставить поле пустым.",
parse_mode="HTML",
reply_markup=InlineKeyboardMarkup([
[InlineKeyboardButton(f"{EMOJI['check']} Пропустить", callback_data=f"skip_not_wish_{game_id}")],
[InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
])
)
return

# ---- ПОЖЕЛАНИЯ: НЕ ХОЧУ ----
if user.get("state") and user["state"].startswith("wait_wish_not_"):
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

not_wish_text = update.message.text.strip()
if len(not_wish_text) > 500:
await update.message.reply_text(
f"{EMOJI['cross']} Слишком длинный текст. Максимум 500 символов.",
reply_markup=InlineKeyboardMarkup([
[InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
])
)
return

user.setdefault("wishes", {}).setdefault(game_id, {})["not_wish"] = not_wish_text
user["state"] = None
save_storage()

game = storage["games"][game_id]
game_name = escape_markdown(game["name"])

await update.message.reply_text(
f"{EMOJI['check']} <b>Пожелания сохранены!</b>\n\n"
f"{EMOJI['tree']} <b>{game_name}</b>\n\n"
f"Теперь твой Тайный Санта будет знать, что ты хочешь и чего не хочешь получить в подарок! 🎁",
parse_mode="HTML",
reply_markup=InlineKeyboardMarkup([
[InlineKeyboardButton(f"{EMOJI['back']} К игре", callback_data=f"game_{game_id}")],
[InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
])
)
return

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

# ------------------ ГЛАВНОЕ МЕНЮ (колбэк) ------------------
async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
await query.answer()

user = get_user(query.from_user.id)
user["state"] = None
if "tmp_name" in user:
del user["tmp_name"]
if "tmp_game_id" in user:
del user["tmp_game_id"]
save_storage()

welcome_text = (
f"{EMOJI['gift']} <b>Тайный Санта</b>\n\n"
f"Создай свою игру или присоединись к существующей.\n"
f"Когда все соберутся — запусти распределение!"
)

keyboard = [
[InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
[InlineKeyboardButton(f"{EMOJI['join']} Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
        [InlineKeyboardButton(f"{EMOJI['help']} FAQ и инструкции", url=FAQ_CHANNEL_LINK)],
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
    if args and len(args[0]) == 8:
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

        # Отправляем стандартное сообщение о вступлении
await update.message.reply_text(
f"{EMOJI['check']} <b>Ты присоединился к игре!</b>\n\n"
f"{EMOJI['tree']} <b>{escape_markdown(game['name'])}</b>\n"
f"{EMOJI['money']} <b>Сумма:</b> {game['amount']} ₽\n"
f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}\n\n"
f"{EMOJI['santa']} Ждем, когда создатель запустит распределение!",
parse_mode="HTML",
reply_markup=InlineKeyboardMarkup([
[InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
])
)

        # ОТДЕЛЬНО отправляем информационное сообщение о пожеланиях (через 1 секунду)
        async def send_info_message():
            try:
                await context.bot.send_message(
                    user_id,
                    f"{EMOJI['info']} <b>Важная информация!</b>\n\n"
                    f"🎯 <b>Укажи свои пожелания для подарка!</b>\n\n"
                    f"Чтобы твой Тайный Санта знал, что тебе дарить, ты можешь указать свои пожелания:\n\n"
                    f"🎁 <b>Что бы ты хотел(а) получить</b>\n"
                    f"🙅 <b>Что бы ты НЕ хотел(а) получать</b>\n\n"
                    f"Эти пожелания увидит только твой Тайный Санта после распределения.\n\n"
                    f"<i>Зайди в свои игры и нажми кнопку \"Указать пожелания\" для игры:</i>\n"
                    f"<b>{escape_markdown(game['name'])}</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{EMOJI['wish']} Указать пожелания", callback_data=f"wish_{game_id}")],
                        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")]
                    ])
                )
            except Exception as e:
                print(f"Ошибка отправки информационного сообщения: {e}")
        
        # Запускаем отправку с небольшой задержкой
        import asyncio
        asyncio.create_task(send_info_message())
        
        try:
            await context.bot.send_message(
                user_id,
                f"{EMOJI['info']} <b>🎯 Укажи свои пожелания для подарка!</b>\n\n"
                f"Чтобы твой Тайный Санта знал, что тебе дарить:\n\n"
                f"✅ <b>Что бы ты хотел(а) получить</b>\n"
                f"❌ <b>Что бы ты НЕ хотел(а) получать</b>\n\n"
                f"<i>Эти пожелания увидит только твой Тайный Санта.</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['wish']} Указать пожелания", callback_data=f"wish_{game_id}")],
                    [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")]
                ])
            )
        except Exception as e:
            print(f"Ошибка отправки информационного сообщения: {e}")
            
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
    application.add_handler(CommandHandler("help", help_command))
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
application.add_handler(CallbackQueryHandler(wish_cb, pattern="wish_"))
application.add_handler(CallbackQueryHandler(edit_wish_cb, pattern="edit_wish_"))
application.add_handler(CallbackQueryHandler(delete_wish_cb, pattern="delete_wish_"))
application.add_handler(CallbackQueryHandler(skip_not_wish_cb, pattern="skip_not_wish_"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Инициализируем Application
await application.initialize()

    # Устанавливаем webhook
if WEBHOOK_URL:
await application.bot.set_webhook(WEBHOOK_URL)
print(f"✅ Webhook установлен на {WEBHOOK_URL}")

print(f"✅ Тайный Санта готов! Всего пользователей: {len(storage['users'])}")
    print(f"📚 FAQ канал: {FAQ_CHANNEL_LINK}")

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
"games_count": len(storage["games"]),
"users_count": len(storage["users"]),
        "active_games": len([g for g in storage["games"].values() if not g["started"]]),
        "faq_channel": FAQ_CHANNEL_LINK
}

# ------------------ MAIN ------------------
def main():
"""Запуск FastAPI приложения"""
print(f"🎄 Запуск на порту {PORT}")
    print(f"📊 Всего пользователей в системе: {len(storage['users'])}")
    print(f"🎮 Всего игр в системе: {len(storage['games'])}")
    print(f"📚 FAQ канал: {FAQ_CHANNEL_LINK}")
uvicorn.run(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
main()
