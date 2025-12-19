import json
import os
import uuid
import random
import time
import threading
import requests
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

print("🚀 Начало запуска бота...")

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 10000))
STORAGE_FILE = "storage.json"
FAQ_CHANNEL_LINK = "https://t.me/ssr_faq"

print(f"🔧 Настройки: PORT={PORT}, STORAGE_FILE={STORAGE_FILE}")

# Проверяем наличие токена
if not BOT_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не установлен!")
    print("ℹ️ Установите переменную окружения BOT_TOKEN")
    exit(1)
else:
    print("✅ BOT_TOKEN установлен")

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
    "help": "❓",
    "skip": "⏭️"
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

# ------------------ ПРОСТОЕ ХРАНИЛИЩЕ ------------------
def load_storage():
    """Загружает данные из файла"""
    print(f"📂 Загрузка данных из {STORAGE_FILE}...")
    
    if not os.path.exists(STORAGE_FILE):
        print("📄 Файл не найден, создаем новый...")
        data = {"games": {}, "users": {}}
        save_storage(data)
        return data
    
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Проверяем структуру
        if "games" not in data:
            data["games"] = {}
        if "users" not in data:
            data["users"] = {}
        
        print(f"✅ Данные загружены: {len(data['games'])} игр, {len(data['users'])} пользователей")
        return data
        
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return {"games": {}, "users": {}}

def save_storage(data):
    """Сохраняет данные в файл"""
    try:
        # Проверяем данные
        if not isinstance(data, dict):
            print("❌ Ошибка: данные не являются словарем")
            return False
            
        if "games" not in data:
            data["games"] = {}
        if "users" not in data:
            data["users"] = {}
        
        # Сохраняем во временный файл
        temp_file = STORAGE_FILE + ".tmp"
        
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Заменяем оригинальный файл
        os.replace(temp_file, STORAGE_FILE)
        
        print(f"💾 Данные сохранены: {len(data['games'])} игр, {len(data['users'])} пользователей")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return False

def get_user(data, user_id):
    """Получает или создает пользователя"""
    user_id_str = str(user_id)
    
    if user_id_str not in data["users"]:
        data["users"][user_id_str] = {
            "state": None,
            "games": [],
            "wishes": {},
            "preferences": {},
            "notified_games": [],
            "created_at": time.time()
        }
        print(f"👤 Создан новый пользователь: {user_id_str}")
    
    return data["users"][user_id_str]

def cleanup_old_games(data, days_old=30):
    """Очищает старые игры"""
    current_time = time.time()
    games_to_remove = []
    
    for game_id, game in data["games"].items():
        if game.get("started") and game.get("finished_time"):
            age_days = (current_time - game["finished_time"]) / (24 * 60 * 60)
            if age_days > days_old:
                games_to_remove.append(game_id)
    
    for game_id in games_to_remove:
        # Удаляем игру из списков пользователей
        for user_data in data["users"].values():
            if "games" in user_data and game_id in user_data["games"]:
                user_data["games"].remove(game_id)
            if "wishes" in user_data and game_id in user_data["wishes"]:
                del user_data["wishes"][game_id]
            if "preferences" in user_data and game_id in user_data["preferences"]:
                del user_data["preferences"][game_id]
        
        # Удаляем саму игру
        if game_id in data["games"]:
            del data["games"][game_id]
    
    if games_to_remove:
        print(f"🗑️ Удалено старых игр: {len(games_to_remove)}")
    
    return data

# ------------------ KEEP-ALIVE СИСТЕМА ------------------
def keep_alive_robust():
    """Keep-alive система"""
    print("🔔 Keep-alive система запущена")
    
    # Определяем URL
    base_url = os.getenv("HEALTH_CHECK_URL", f"http://localhost:{PORT}")
    
    if not base_url.endswith('/'):
        base_url += '/'
    
    health_url = base_url
    
    print(f"🔗 Будем пинговать: {health_url}")
    
    while True:
        try:
            current_time = time.strftime("%H:%M:%S")
            response = requests.get(health_url, timeout=30)
            
            if response.status_code == 200:
                print(f"✅ [{current_time}] Бот активен")
            else:
                print(f"⚠️  [{current_time}] Статус: {response.status_code}")
                
        except Exception as e:
            current_time = time.strftime("%H:%M:%S")
            print(f"❌ [{current_time}] Ошибка: {type(e).__name__}")
        
        time.sleep(240)

# ------------------ УТИЛИТЫ ------------------
def gen_game_id():
    return str(uuid.uuid4())[:8]

# ------------------ КОМАНДЫ ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    print(f"📨 Команда /start от {update.effective_user.id}")
    
    data = load_storage()
    user_id = update.effective_user.id
    user = get_user(data, user_id)
    user["state"] = None
    save_storage(data)

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
    """Команда /menu"""
    print(f"📨 Команда /menu от {update.effective_user.id}")
    
    data = load_storage()
    user_id = update.effective_user.id
    user = get_user(data, user_id)
    user["state"] = None
    save_storage(data)

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
    """Команда /cancel"""
    print(f"📨 Команда /cancel от {update.effective_user.id}")
    
    data = load_storage()
    user_id = update.effective_user.id
    user = get_user(data, user_id)
    user["state"] = None
    if "tmp_name" in user:
        del user["tmp_name"]
    if "tmp_game_id" in user:
        del user["tmp_game_id"]
    save_storage(data)
    
    await update.message.reply_text(
        f"{EMOJI['check']} Действие отменено. Используй /menu для возврата в меню."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    print(f"📨 Команда /help от {update.effective_user.id}")
    
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

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /debug - для отладки"""
    print(f"🔍 Команда /debug от {update.effective_user.id}")
    
    data = load_storage()
    file_exists = os.path.exists(STORAGE_FILE)
    file_size = os.path.getsize(STORAGE_FILE) if file_exists else 0
    
    text = (
        f"🔍 <b>Отладка бота</b>\n\n"
        f"📁 <b>Файл хранилища:</b>\n"
        f"• Имя: <code>{STORAGE_FILE}</code>\n"
        f"• Существует: {'✅ Да' if file_exists else '❌ Нет'}\n"
        f"• Размер: {file_size} байт\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего игр: {len(data['games'])}\n"
        f"• Пользователей: {len(data['users'])}\n\n"
        f"⚙️ <b>Настройки:</b>\n"
        f"• Порт: {PORT}\n"
        f"• WEBHOOK_URL: {'✅ Установлен' if WEBHOOK_URL else '❌ Не установлен'}\n"
        f"• BOT_TOKEN: {'✅ Установлен' if BOT_TOKEN else '❌ Не установлен'}"
    )
    
    await update.message.reply_text(text, parse_mode="HTML")

# ------------------ МОИ ИГРЫ ------------------
async def my_games_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    print(f"📨 Запрос 'Мои игры' от {query.from_user.id}")
    
    data = load_storage()
    user_id = str(query.from_user.id)
    
    # Находим игры пользователя
    user_games = []
    for game_id, game in data["games"].items():
        if user_id in game.get("players", []) and not game.get("started", False):
            user_games.append(game)
    
    if not user_games:
        await query.edit_message_text(
            f"{EMOJI['tree']} <b>У тебя пока нет активных игр</b>\n\n"
            f"Создай новую игру или присоединись к существующей!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
                [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
            ])
        )
        return
    
    text = f"{EMOJI['list']} <b>Твои игры</b>\n\n"
    buttons = []
    
    for game in user_games[:10]:
        is_owner = f"{EMOJI['crown']} " if game.get("owner") == user_id else ""
        game_name = escape_markdown(game.get("name", "Без названия"))
        
        text += f"{is_owner}<b>{game_name}</b>\n"
        text += f"   {EMOJI['users']} {len(game.get('players', []))} | {EMOJI['money']} {game.get('amount', '0')} ₽\n\n"
        
        buttons.append([
            InlineKeyboardButton(
                f"{game_name[:15]}...",
                callback_data=f"game_{game.get('id', '')}"
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

# ------------------ СОЗДАНИЕ ИГРЫ ------------------
async def create_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    print(f"📨 Запрос 'Создать игру' от {query.from_user.id}")

    data = load_storage()
    user = get_user(data, query.from_user.id)
    user["state"] = "wait_game_name"
    save_storage(data)

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
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    print(f"📨 Текст от {user_id}: '{text}'")
    
    # Проверяем отладочные команды
    if text.lower() in ["debug", "отладка", "/debug"]:
        await debug_command(update, context)
        return
    
    data = load_storage()
    user = get_user(data, user_id)
    user_state = user.get("state")
    
    print(f"📝 Состояние пользователя {user_id}: {user_state}")
    
    # ---- НАЗВАНИЕ ИГРЫ ----
    if user_state == "wait_game_name":
        name = text
        if len(name) < 2:
            await update.message.reply_text(f"{EMOJI['cross']} Слишком короткое название. Минимум 2 символа:")
            return
            
        user["tmp_name"] = name
        user["state"] = "wait_game_amount"
        save_storage(data)
        
        print(f"✅ Пользователь {user_id} ввел название игры: {name}")
        
        await update.message.reply_text(
            f"{EMOJI['money']} Сумма подарка\n\nВведи сумму в рублях:\n\n"
            f"{EMOJI['info']} Используй /cancel для отмены",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['home']} Отмена", callback_data="main_menu")]
            ])
        )
        return

    # ---- БЮДЖЕТ ИГРЫ ----
    if user_state == "wait_game_amount":
        if "tmp_name" not in user:
            await update.message.reply_text(
                f"{EMOJI['cross']} Ошибка. Начни заново: /menu",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            user["state"] = None
            save_storage(data)
            return
            
        try:
            clean_text = text.replace(" ", "").replace(",", ".")
            amount = float(clean_text)
            
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

        # СОЗДАЕМ ИГРУ
        game_id = gen_game_id()
        
        if amount.is_integer():
            amount_str = str(int(amount))
        else:
            amount_str = f"{amount:.2f}".rstrip('0').rstrip('.')
        
        game_name = user["tmp_name"]
        
        # СОЗДАЕМ ИГРУ В ДАННЫХ
        data["games"][game_id] = {
            "id": game_id,
            "name": game_name,
            "amount": amount_str,
            "owner": str(user_id),
            "players": [str(user_id)],
            "started": False,
            "pairs": {},
            "created_time": time.time(),
            "last_modified": time.time()
        }

        # ОБНОВЛЯЕМ ПОЛЬЗОВАТЕЛЯ
        del user["tmp_name"]
        user["state"] = None
        user.setdefault("games", []).append(game_id)
        
        # СОХРАНЯЕМ
        if save_storage(data):
            print(f"✅ Игра создана: ID={game_id}, название='{game_name}', сумма={amount_str} ₽")
            
            # ПРОВЕРЯЕМ СОХРАНЕНИЕ
            check_data = load_storage()
            if game_id in check_data["games"]:
                print(f"✅ Проверка: игра {game_id} сохранена в файл")
            else:
                print(f"❌ ПРОВЕРКА: игра {game_id} НЕ найдена в файле!")
        else:
            print(f"❌ Ошибка сохранения игры!")
            await update.message.reply_text(
                f"{EMOJI['cross']} Ошибка сохранения игры. Попробуй еще раз.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return

        # ОТПРАВЛЯЕМ ОТВЕТ
        invite_link = f"https://t.me/{context.bot.username}?start={game_id}"
        escaped_game_name = escape_markdown(game_name)
        
        response_text = (
            f"{EMOJI['tree']}✨ <b>Игра «{escaped_game_name}» создана!</b>\n\n"
            f"{EMOJI['money']} <b>Сумма:</b> {amount_str} ₽\n"
            f"{EMOJI['users']} <b>Участников:</b> 1\n\n"
            f"{EMOJI['link']} <b>Ссылка для друзей:</b>\n"
            f"<code>{invite_link}</code>\n\n"
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
            response_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return

    # Если состояние не распознано
    await update.message.reply_text(
        f"{EMOJI['info']} Я не понимаю, что ты хочешь сделать. Используй /menu для возврата в меню.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ])
    )

# ------------------ ОБРАБОТЧИКИ КОЛБЭКОВ ------------------
async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_storage()
    user = get_user(data, query.from_user.id)
    user["state"] = None
    if "tmp_name" in user:
        del user["tmp_name"]
    if "tmp_game_id" in user:
        del user["tmp_game_id"]
    save_storage(data)

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

    await query.edit_message_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def game_details_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_storage()
    game_id = query.data.split("_")[1]
    game = data["games"].get(game_id)
    
    if not game:
        await query.edit_message_text(
            f"{EMOJI['cross']} Игра не найдена",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
                [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
            ])
        )
        return
    
    user_id = str(query.from_user.id)
    game_name = escape_markdown(game.get("name", "Без названия"))
    
    text = (
        f"{EMOJI['tree']} <b>{game_name}</b>\n"
        f"{EMOJI['money']} <b>Бюджет:</b> {game.get('amount', '0')} ₽\n"
        f"{EMOJI['users']} <b>Участников:</b> {len(game.get('players', []))}"
    )
    
    keyboard = []
    
    if user_id == game.get("owner"):
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['link']} Пригласить", callback_data=f"invite_{game_id}"),
            InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
        ])
        keyboard.append([InlineKeyboardButton(f"{EMOJI['play']} Запустить распределение", callback_data=f"start_game_{game_id}")])
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['edit']} Изменить сумму", callback_data=f"edit_amount_{game_id}"),
            InlineKeyboardButton(f"{EMOJI['trash']} Удалить игру", callback_data=f"delete_{game_id}")
        ])
    elif user_id in game.get("players", []):
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
        ])
        keyboard.append([InlineKeyboardButton(f"{EMOJI['wish']} Указать пожелания", callback_data=f"wish_{game_id}")])
    
    keyboard.append([
        InlineKeyboardButton(f"{EMOJI['back']} К списку игр", callback_data="my_games"),
        InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")
    ])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# ------------------ ПРОСТЫЕ ОБРАБОТЧИКИ ДЛЯ ОСТАЛЬНЫХ КНОПОК ------------------
async def join_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
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

async def invite_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_storage()
    game_id = query.data.split("_")[1]
    game = data["games"].get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    invite_link = f"https://t.me/{context.bot.username}?start={game_id}"
    game_name = escape_markdown(game.get("name", "Без названия"))
    
    text = (
        f"{EMOJI['gift']} <b>Приглашение в игру</b>\n\n"
        f"{EMOJI['tree']} <b>{game_name}</b>\n"
        f"{EMOJI['money']} <b>Сумма подарка:</b> {game.get('amount', '0')} ₽\n"
        f"{EMOJI['users']} <b>Участников:</b> {len(game.get('players', []))}\n\n"
        f"{EMOJI['link']} <b>Ссылка для присоединения:</b>\n"
        f"{invite_link}\n\n"
        f"{EMOJI['snowflake']} Нажми на ссылку, чтобы присоединиться к игре!"
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

# ------------------ ОБРАБОТКА ПРИГЛАСИТЕЛЬНОЙ ССЫЛКИ ------------------
async def handle_start_with_param(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка /start с параметром"""
    args = context.args
    if args and len(args[0]) == 8:
        game_id = args[0]
        data = load_storage()
        game = data["games"].get(game_id)
        
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
        
        if game.get("started", False):
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
        
        if user_id in game.get("players", []):
            await update.message.reply_text(
                f"{EMOJI['info']} <b>Ты уже в игре!</b>\n\n"
                f"{EMOJI['tree']} <b>{escape_markdown(game.get('name', 'Без названия'))}</b>\n"
                f"{EMOJI['money']} <b>Сумма:</b> {game.get('amount', '0')} ₽\n"
                f"{EMOJI['users']} <b>Участников:</b> {len(game.get('players', []))}\n\n"
                f"Ждем начала распределения!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return
        
        # Добавляем пользователя в игру
        if "players" not in game:
            game["players"] = []
        game["players"].append(user_id)
        
        user = get_user(data, user_id)
        user.setdefault("games", []).append(game_id)
        save_storage(data)
        
        await update.message.reply_text(
            f"{EMOJI['check']} <b>Ты присоединился к игре!</b>\n\n"
            f"{EMOJI['tree']} <b>{escape_markdown(game.get('name', 'Без названия'))}</b>\n"
            f"{EMOJI['money']} <b>Сумма:</b> {game.get('amount', '0')} ₽\n"
            f"{EMOJI['users']} <b>Участников:</b> {len(game.get('players', []))}\n\n"
            f"{EMOJI['santa']} Ждем, когда создатель запустит распределение!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
            ])
        )
    else:
        await start(update, context)

# ------------------ FASTAPI ------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan контекст"""
    global application
    
    print("=" * 50)
    print("🎅 Инициализация Тайного Санты...")
    print("=" * 50)
    
    # Проверяем токен
    if not BOT_TOKEN:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не установлен!")
        raise RuntimeError("BOT_TOKEN не установлен")
    
    # Загружаем и чистим данные
    print("📂 Загрузка данных...")
    data = load_storage()
    data = cleanup_old_games(data, days_old=30)
    save_storage(data)
    
    # Создаем приложение
    print("🤖 Создание приложения Telegram...")
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        print("✅ Приложение создано")
    except Exception as e:
        print(f"❌ Ошибка создания приложения: {e}")
        raise
    
    # Регистрируем обработчики
    print("📝 Регистрация обработчиков...")
    try:
        application.add_handler(CommandHandler("start", handle_start_with_param))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("cancel", cancel_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("debug", debug_command))
        
        application.add_handler(CallbackQueryHandler(create_game_cb, pattern="create_game"))
        application.add_handler(CallbackQueryHandler(join_game_cb, pattern="join_game"))
        application.add_handler(CallbackQueryHandler(my_games_cb, pattern="my_games"))
        application.add_handler(CallbackQueryHandler(game_details_cb, pattern="game_"))
        application.add_handler(CallbackQueryHandler(invite_cb, pattern="invite_"))
        application.add_handler(CallbackQueryHandler(main_menu_cb, pattern="main_menu"))
        
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
        
        print("✅ Обработчики зарегистрированы")
    except Exception as e:
        print(f"❌ Ошибка регистрации обработчиков: {e}")
        raise
    
    # Инициализируем приложение
    print("⚙️ Инициализация приложения...")
    try:
        await application.initialize()
        print("✅ Приложение инициализировано")
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        raise
    
    # Настраиваем webhook если есть URL
    if WEBHOOK_URL:
        print(f"🌐 Настройка webhook на {WEBHOOK_URL}")
        try:
            await application.bot.set_webhook(WEBHOOK_URL)
            print("✅ Webhook установлен")
        except Exception as e:
            print(f"❌ Ошибка установки webhook: {e}")
            raise
    else:
        print("ℹ️ Webhook не настроен (используется polling)")
    
    # Статистика
    active_games = len([g for g in data['games'].values() if not g.get('started', False)])
    finished_games = len([g for g in data['games'].values() if g.get('started', False)])
    
    print("=" * 50)
    print(f"📊 Статистика:")
    print(f"   🎮 Активных игр: {active_games}")
    print(f"   📚 Завершенных игр: {finished_games}")
    print(f"   👤 Всего пользователей: {len(data['users'])}")
    print("=" * 50)
    
    # Запускаем keep-alive
    print("🔔 Запуск keep-alive системы...")
    try:
        keep_alive_thread = threading.Thread(target=keep_alive_robust, daemon=True)
        keep_alive_thread.start()
        print("✅ Keep-alive запущен")
    except Exception as e:
        print(f"⚠️  Ошибка запуска keep-alive: {e}")
    
    print("🎅 Тайный Санта готов к работе!")
    print("=" * 50)
    
    yield
    
    print("🎄 Остановка бота...")
    if application:
        await application.shutdown()
    print("✅ Бот остановлен")

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(req: Request):
    """Endpoint для webhook"""
    global application
    
    if not application:
        return {"ok": False, "error": "Application not initialized"}, 500
    
    try:
        data = await req.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        print(f"❌ Ошибка в webhook: {e}")
        return {"ok": False, "error": str(e)}, 500

@app.get("/")
async def health_check():
    """Health check endpoint"""
    data = load_storage()
    active_games = len([g for g in data["games"].values() if not g.get("started", False)])
    finished_games = len([g for g in data["games"].values() if g.get("started", False)])
    
    return {
        "status": "ok", 
        "message": "🎅 Тайный Санта работает",
        "games_count": len(data["games"]),
        "active_games": active_games,
        "finished_games": finished_games,
        "users_count": len(data["users"]),
        "timestamp": time.time()
    }

@app.get("/debug")
async def debug_api():
    """API endpoint для отладки"""
    data = load_storage()
    file_exists = os.path.exists(STORAGE_FILE)
    file_size = os.path.getsize(STORAGE_FILE) if file_exists else 0
    
    return {
        "status": "ok",
        "storage": {
            "file": STORAGE_FILE,
            "exists": file_exists,
            "size": file_size,
            "games_count": len(data["games"]),
            "users_count": len(data["users"])
        },
        "system": {
            "port": PORT,
            "webhook_url": WEBHOOK_URL is not None,
            "bot_token": BOT_TOKEN is not None
        },
        "timestamp": time.time()
    }

@app.get("/wakeup")
async def wakeup():
    """Endpoint для пробуждения"""
    return {
        "status": "awake",
        "message": "🎅 Тайный Санта бодрствует",
        "timestamp": time.time()
    }

# ------------------ MAIN ------------------
def main():
    """Главная функция"""
    print("🚀 Запуск Тайного Санты...")
    print(f"⚙️ Порт: {PORT}")
    print(f"📁 Файл хранилища: {STORAGE_FILE}")
    print(f"🌐 FAQ канал: {FAQ_CHANNEL_LINK}")
    print("=" * 50)
    
    try:
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=PORT,
            log_level="info"
        )
    except Exception as e:
        print(f"❌ Ошибка запуска сервера: {e}")
        raise

if __name__ == "__main__":
    main()
