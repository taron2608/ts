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

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 10000))
STORAGE_FILE = "storage.json"
FAQ_CHANNEL_LINK = "https://t.me/ssr_faq"

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

# ------------------ УЛУЧШЕННОЕ ХРАНИЛИЩЕ ------------------
class StorageManager:
    """Менеджер для работы с хранилищем данных"""
    
    @staticmethod
    def load():
        """Загружает данные из файла с проверкой структуры"""
        print(f"📂 Загрузка данных из {STORAGE_FILE}...")
        
        if not os.path.exists(STORAGE_FILE):
            print("📄 Файл storage.json не найден, создаем новый...")
            data = {"games": {}, "users": {}}
            StorageManager.save(data)
            return data
        
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"✅ Данные загружены успешно")
                
            # Проверяем и исправляем структуру данных
            if "games" not in data:
                print("⚠️  Исправляем структуру: добавляем 'games'")
                data["games"] = {}
            
            if "users" not in data:
                print("⚠️  Исправляем структуру: добавляем 'users'")
                data["users"] = {}
            
            # Проверяем структуру игр
            for game_id, game in list(data["games"].items()):
                if not isinstance(game, dict):
                    print(f"⚠️  Удаляем некорректную игру {game_id}")
                    del data["games"][game_id]
                    continue
                    
                # Обязательные поля для игры
                required_fields = ["id", "name", "amount", "owner", "players"]
                for field in required_fields:
                    if field not in game:
                        print(f"⚠️  Игра {game_id} не имеет поля {field}, удаляем")
                        del data["games"][game_id]
                        break
            
            print(f"📊 Статистика: {len(data['games'])} игр, {len(data['users'])} пользователей")
            return data
            
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка JSON в файле {STORAGE_FILE}: {e}")
            print("🔄 Создаем новый файл с чистыми данными...")
            data = {"games": {}, "users": {}}
            StorageManager.save(data)
            return data
        except Exception as e:
            print(f"❌ Ошибка загрузки {STORAGE_FILE}: {e}")
            return {"games": {}, "users": {}}
    
    @staticmethod
    def save(data):
        """Сохраняет данные в файл с проверкой"""
        try:
            # Проверяем данные перед сохранением
            if not isinstance(data, dict):
                print("❌ Ошибка: данные не являются словарем")
                return False
                
            if "games" not in data:
                data["games"] = {}
            if "users" not in data:
                data["users"] = {}
            
            # Создаем временный файл для безопасной записи
            temp_file = STORAGE_FILE + ".tmp"
            
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Заменяем оригинальный файл
            os.replace(temp_file, STORAGE_FILE)
            
            print(f"💾 Данные сохранены: {len(data['games'])} игр, {len(data['users'])} пользователей")
            
            # Проверяем, что файл действительно записался
            if os.path.exists(STORAGE_FILE):
                file_size = os.path.getsize(STORAGE_FILE)
                print(f"📏 Размер файла: {file_size} байт")
                return True
            else:
                print("❌ Файл не был создан")
                return False
                
        except Exception as e:
            print(f"❌ Критическая ошибка сохранения: {e}")
            return False
    
    @staticmethod
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
        
        return data["users"][user_id_str]
    
    @staticmethod
    def cleanup_old_games(data, days_old=30):
        """Очищает старые игры"""
        current_time = time.time()
        games_to_remove = []
        
        for game_id, game in data["games"].items():
            if game.get("started") and game.get("finished_time"):
                age_days = (current_time - game["finished_time"]) / (24 * 60 * 60)
                if age_days > days_old:
                    games_to_remove.append(game_id)
        
        removed_count = 0
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
                removed_count += 1
        
        if removed_count > 0:
            print(f"🗑️ Удалено старых игр (>{days_old} дней): {removed_count}")
        
        return data

# ------------------ KEEP-ALIVE СИСТЕМА ------------------
def keep_alive_robust():
    """Надежный keep-alive для предотвращения сна бота"""
    print("🔔 Keep-alive система запущена")
    
    # Определяем URL для пинга
    base_url = os.getenv("HEALTH_CHECK_URL")
    
    if not base_url:
        # Пытаемся определить URL автоматически
        if "RAILWAY_STATIC_URL" in os.environ:
            base_url = f"https://{os.environ['RAILWAY_STATIC_URL']}"
        elif "RENDER_EXTERNAL_URL" in os.environ:
            base_url = os.environ['RENDER_EXTERNAL_URL']
        elif "VERCEL_URL" in os.environ:
            base_url = f"https://{os.environ['VERCEL_URL']}"
        else:
            # Локальная разработка - используем localhost
            base_url = f"http://localhost:{PORT}"
    
    # Убедимся, что URL заканчивается на /
    if not base_url.endswith('/'):
        base_url += '/'
    
    health_url = base_url
    wakeup_url = base_url + "wakeup" if base_url.endswith('/') else base_url + "/wakeup"
    
    print(f"🔗 Будем пинговать: {health_url}")
    
    while True:
        try:
            current_time = time.strftime("%H:%M:%S")
            
            # Пробуем основной endpoint
            response = requests.get(health_url, timeout=30)
            if response.status_code == 200:
                print(f"✅ [{current_time}] Бот активен (статус: {response.status_code})")
            else:
                print(f"⚠️  [{current_time}] Неожиданный статус: {response.status_code}")
                
        except requests.exceptions.Timeout:
            current_time = time.strftime("%H:%M:%S")
            print(f"⏰ [{current_time}] Таймаут при ping")
        except requests.exceptions.ConnectionError:
            current_time = time.strftime("%H:%M:%S")
            print(f"🔌 [{current_time}] Ошибка соединения")
        except Exception as e:
            current_time = time.strftime("%H:%M:%S")
            print(f"❌ [{current_time}] Ошибка: {type(e).__name__}")
        
        # Ждем 4 минуты
        time.sleep(240)

# ------------------ УТИЛИТЫ ------------------
def gen_game_id():
    return str(uuid.uuid4())[:8]

# ------------------ КОМАНДЫ ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    data = StorageManager.load()
    user_id = update.effective_user.id
    user = StorageManager.get_user(data, user_id)
    user["state"] = None
    
    if StorageManager.save(data):
        print(f"✅ Состояние пользователя {user_id} сброшено")
    else:
        print(f"❌ Ошибка сохранения состояния пользователя {user_id}")

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
    data = StorageManager.load()
    user_id = update.effective_user.id
    user = StorageManager.get_user(data, user_id)
    user["state"] = None
    StorageManager.save(data)

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
    data = StorageManager.load()
    user_id = update.effective_user.id
    user = StorageManager.get_user(data, user_id)
    user["state"] = None
    if "tmp_name" in user:
        del user["tmp_name"]
    if "tmp_game_id" in user:
        del user["tmp_game_id"]
    StorageManager.save(data)
    
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
    
    data = StorageManager.load()
    user_id = str(query.from_user.id)
    
    # Находим все активные игры пользователя
    user_games = []
    for game_id, game in data["games"].items():
        if user_id in game.get("players", []) and not game.get("started", False):
            user_games.append(game)
    
    if not user_games:
        # Показываем завершенные игры отдельно
        finished_games = []
        for game_id, game in data["games"].items():
            if user_id in game.get("players", []) and game.get("started", False):
                finished_games.append(game)
        
        if finished_games:
            text = f"{EMOJI['check']} <b>Завершенные игры</b>\n\n"
            for game in finished_games[:5]:
                game_name = escape_markdown(game.get("name", "Без названия"))
                text += f"🎄 <b>{game_name}</b>\n"
                text += f"   {EMOJI['money']} {game.get('amount', '0')} ₽ | {EMOJI['users']} {len(game.get('players', []))}\n\n"
            
            text += f"{EMOJI['info']} Активных игр нет. Создайте новую!"
            
            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
                    [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
                ])
            )
        else:
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

    data = StorageManager.load()
    user = StorageManager.get_user(data, query.from_user.id)
    user["state"] = "wait_game_name"
    
    if StorageManager.save(data):
        print(f"✅ Пользователь {query.from_user.id} начал создание игры")
    else:
        print(f"❌ Ошибка сохранения состояния создания игры")

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

# ------------------ ТЕКСТОВЫЙ ОБРАБОТЧИК (ОСНОВНОЙ) ------------------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ЗАГРУЖАЕМ ДАННЫЕ ПЕРЕД ЛЮБОЙ ОПЕРАЦИЕЙ
    data = StorageManager.load()
    user_id = update.message.from_user.id
    user = StorageManager.get_user(data, user_id)
    user_state = user.get("state")
    
    print(f"📝 Обработка сообщения от {user_id}, состояние: {user_state}")
    
    # ---- НАЗВАНИЕ ИГРЫ ----
    if user_state == "wait_game_name":
        name = update.message.text.strip()
        if len(name) < 2:
            await update.message.reply_text(f"{EMOJI['cross']} Слишком короткое название. Минимум 2 символа:")
            return
            
        user["tmp_name"] = name
        user["state"] = "wait_game_amount"
        
        if StorageManager.save(data):
            print(f"✅ Пользователь {user_id} ввел название игры: {name}")
        else:
            print(f"❌ Ошибка сохранения названия игры")
            await update.message.reply_text(
                f"{EMOJI['cross']} Ошибка сохранения. Попробуй еще раз: /menu",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return
        
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
        # ПЕРЕЗАГРУЖАЕМ ДАННЫЕ НА СЛУЧАЙ ПАРАЛЛЕЛЬНЫХ ИЗМЕНЕНИЙ
        data = StorageManager.load()
        user = StorageManager.get_user(data, user_id)
        
        if "tmp_name" not in user:
            await update.message.reply_text(
                f"{EMOJI['cross']} Ошибка. Начни заново: /menu",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            user["state"] = None
            StorageManager.save(data)
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

        # ГЕНЕРИРУЕМ ID И СОЗДАЕМ ИГРУ
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
        
        # СОХРАНЯЕМ ВСЕ ИЗМЕНЕНИЯ
        if StorageManager.save(data):
            print(f"✅ Игра создана: ID={game_id}, название='{game_name}', сумма={amount_str} ₽")
        else:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: игра не сохранена!")
            await update.message.reply_text(
                f"{EMOJI['cross']} Критическая ошибка сохранения игры. Попробуй еще раз.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
                ])
            )
            return

        # ОТПРАВЛЯЕМ ОТВЕТ ПОЛЬЗОВАТЕЛЮ
        invite_link = f"https://t.me/{context.bot.username}?start={game_id}"
        escaped_game_name = escape_markdown(game_name)
        
        text = (
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
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: снова загружаем данные и проверяем, что игра сохранена
        verification_data = StorageManager.load()
        if game_id in verification_data["games"]:
            print(f"✅ Проверка: игра {game_id} найдена в хранилище")
        else:
            print(f"❌ ПРОВЕРКА НЕ ПРОЙДЕНА: игра {game_id} НЕ найдена в хранилище!")
            
        return

    # ---- ДРУГИЕ СОСТОЯНИЯ ----
    # ... (остальной код обработки состояний остается таким же, но с использованием StorageManager)
    
    # Если состояние не распознано
    await update.message.reply_text(
        f"{EMOJI['info']} Я не понимаю, что ты хочешь сделать. Используй /menu для возврата в меню.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ])
    )

# ... (остальные функции остаются такими же, но ВСЕГДА используют StorageManager.load() в начале и StorageManager.save() после изменений)

# ------------------ ДЕТАЛИ ИГРЫ ------------------
async def game_details_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = StorageManager.load()
    game_id = query.data.split("_")[1]
    game = data["games"].get(game_id)
    
    if not game or game.get("started", False):
        await query.edit_message_text(
            f"{EMOJI['cross']} Игра не найдена или уже завершена",
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
    
    user = StorageManager.get_user(data, user_id)
    has_wishes = False
    if "wishes" in user and game_id in user["wishes"]:
        wishes = user["wishes"][game_id]
        if wishes.get("wish") or wishes.get("not_wish"):
            has_wishes = True
    
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
    
    if user_id in game.get("players", []):
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

# ... (все остальные функции аналогично переписать с использованием StorageManager)

# В конце файла в lifespan добавьте проверку файла:
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan контекст для FastAPI"""
    global application
    
    print("🎅 Инициализация Тайного Санты...")
    print("=" * 50)
    
    # Проверяем и загружаем данные
    print("📂 Проверка хранилища данных...")
    data = StorageManager.load()
    
    # Проверяем права на запись
    try:
        test_save = StorageManager.save(data)
        if test_save:
            print("✅ Права на запись в порядке")
        else:
            print("❌ Проблемы с правами на запись!")
    except Exception as e:
        print(f"❌ Ошибка проверки прав: {e}")
    
    # Чистим старые игры
    data = StorageManager.cleanup_old_games(data, days_old=30)
    StorageManager.save(data)
    
    print("=" * 50)
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков (остается такой же)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(create_game_cb, pattern="create_game"))
    application.add_handler(CallbackQueryHandler(my_games_cb, pattern="my_games"))
    application.add_handler(CallbackQueryHandler(game_details_cb, pattern="game_"))
    # ... остальные обработчики
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    await application.initialize()
    
    if WEBHOOK_URL:
        await application.bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook установлен на {WEBHOOK_URL}")
    
    active_games = len([g for g in data['games'].values() if not g.get('started', False)])
    finished_games = len([g for g in data['games'].values() if g.get('started', False)])
    
    print(f"🎮 Активных игр: {active_games}")
    print(f"📚 Завершенных игр: {finished_games}")
    print(f"👤 Всего пользователей: {len(data['users'])}")
    print(f"📖 FAQ канал: {FAQ_CHANNEL_LINK}")
    print("=" * 50)
    
    # Запускаем keep-alive систему
    if "localhost" not in os.getenv("HEALTH_CHECK_URL", ""):
        print("🔔 Запускаем keep-alive систему...")
        keep_alive_thread = threading.Thread(target=keep_alive_robust, daemon=True)
        keep_alive_thread.start()
        print("✅ Keep-alive система запущена")
    
    print("🎅 Тайный Санта готов к работе!")
    print("=" * 50)
    
    yield
    
    print("🎄 Остановка бота...")
    if application:
        await application.shutdown()
    print("✅ Бот остановлен")

# Остальной код FastAPI остается таким же...
