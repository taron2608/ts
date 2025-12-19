import json
import os
import uuid
import random
import time
import threading
import requests
from contextlib import asynccontextmanager
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, ContextTypes, filters
from fastapi import FastAPI, Request
import uvicorn

print("🚀 Запуск Тайного Санты...")

# ------------------ НАСТРОЙКИ ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    print("ℹ️ Установите переменную окружения BOT_TOKEN")
    exit(1)

print(f"✅ Токен есть")
print(f"🌐 Порт: {PORT}")

# ------------------ ПОСТОЯННОЕ ХРАНИЛИЩЕ ------------------
STORAGE_FILE = "data.json"

def load_storage():
    """Загружает данные из файла"""
    try:
        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"📂 Загружено из хранилища: {len(data.get('games', {}))} игр, {len(data.get('users', {}))} пользователей")
                return data
        else:
            print("📂 Файл хранилища не найден, начинаем с пустого")
            return {"games": {}, "users": {}}
    except Exception as e:
        print(f"⚠️ Ошибка загрузки хранилища: {e}")
        return {"games": {}, "users": {}}

def save_storage():
    """Сохраняет данные в файл"""
    try:
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(storage, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения хранилища: {e}")

# Загружаем данные при старте
storage = load_storage()
games_db = storage["games"]
users_db = storage["users"]

# ------------------ ЭМОДЗИ ------------------
EMOJI = {
    "santa": "🎅", "gift": "🎁", "tree": "🎄", "money": "💰",
    "users": "👥", "create": "✨", "list": "📋", "home": "🏠",
    "cross": "❌", "check": "✅", "info": "ℹ️", "link": "🔗",
    "help": "❓", "crown": "👑", "play": "▶️", "wish": "🎯",
    "bell": "🔔", "star": "⭐", "back": "⬅️", "mail": "📨",
    "lock": "🔒", "edit": "✏️", "trash": "🗑️", "join": "🔗"
}

# ------------------ АКТИВНЫЙ ПИНГ ------------------
def active_ping():
    """Активный пинг каждые 2 минуты чтобы бот не спал"""
    print("🔔 Запускаю активный пинг...")
    
    # Определяем URL автоматически
    base_url = None
    
    # Проверяем разные хостинги
    if "RENDER_EXTERNAL_URL" in os.environ:
        base_url = os.environ['RENDER_EXTERNAL_URL']
        print(f"🎨 Определен Render: {base_url}")
    elif "RAILWAY_STATIC_URL" in os.environ:
        base_url = f"https://{os.environ['RAILWAY_STATIC_URL']}"
        print(f"🚂 Определен Railway: {base_url}")
    elif "HEROKU_APP_NAME" in os.environ:
        base_url = f"https://{os.environ['HEROKU_APP_NAME']}.herokuapp.com"
        print(f"⚡ Определен Heroku: {base_url}")
    else:
        # Если не на хостинге, пинг не нужен
        print("💻 Локальный режим, пинг не требуется")
        return
    
    if not base_url.endswith('/'):
        base_url += '/'
    
    print(f"🔗 Буду пинговать: {base_url}")
    
    while True:
        try:
            current_time = time.strftime("%H:%M:%S")
            
            # Пингуем основной endpoint
            response = requests.get(base_url, timeout=10)
            
            if response.status_code == 200:
                print(f"✅ [{current_time}] Пинг успешен")
            else:
                print(f"⚠️  [{current_time}] Статус: {response.status_code}")
            
            # Также пингуем другие endpoints для надежности
            try:
                requests.get(base_url + "ping", timeout=5)
                requests.get(base_url + "wakeup", timeout=5)
            except:
                pass
            
        except Exception as e:
            current_time = time.strftime("%H:%M:%S")
            print(f"❌ [{current_time}] Ошибка пинга: {type(e).__name__}")
        
        # Ждем 2 минуты (меньше чем 15-минутный таймаут сна на хостингах)
        time.sleep(120)

# ------------------ КОМАНДЫ ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = str(update.effective_user.id)
    
    # Создаем пользователя если его нет
    if user_id not in users_db:
        users_db[user_id] = {"games": [], "state": None}
        save_storage()
        print(f"👤 Новый пользователь: {user_id}")
    
    text = (
        f"{EMOJI['gift']} <b>Тайный Санта</b>\n\n"
        f"Создай свою игру и пригласи друзей!\n"
        f"Когда все соберутся — запусти распределение подарков."
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
        [InlineKeyboardButton(f"{EMOJI['help']} Помощь", callback_data="help")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /menu"""
    user_id = str(update.effective_user.id)
    
    if user_id in users_db:
        users_db[user_id]["state"] = None
        save_storage()
    
    text = f"{EMOJI['gift']} <b>Главное меню</b>"
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
        [InlineKeyboardButton(f"{EMOJI['help']} Помощь", callback_data="help")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    text = (
        f"{EMOJI['help']} <b>Помощь</b>\n\n"
        f"🎯 <b>Как играть:</b>\n"
        f"1. Создай игру\n"
        f"2. Пригласи друзей по ссылке\n"
        f"3. Запусти распределение\n\n"
        f"🤖 <b>Команды:</b>\n"
        f"/start - начать\n"
        f"/menu - меню\n"
        f"/help - помощь\n\n"
        f"🎅 <b>Приятной игры!</b>"
    )
    
    await update.message.reply_text(text, parse_mode="HTML")

# ------------------ ОБРАБОТЧИКИ КНОПОК ------------------
async def create_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание игры"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    # Создаем пользователя если его нет
    if user_id not in users_db:
        users_db[user_id] = {"games": [], "state": None}
        save_storage()
    
    users_db[user_id]["state"] = "wait_game_name"
    save_storage()
    
    await query.edit_message_text(
        f"{EMOJI['create']} <b>Создание игры</b>\n\n"
        f"Придумай название для своей игры:\n\n"
        f"<i>Пример:</i> Новогоднее чудо\n"
        f"<i>Пример:</i> Офисный Санта\n\n"
        f"Отправь мне название:",
        parse_mode="HTML"
    )

async def my_games_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Мои игры"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    # Находим игры пользователя
    user_games = []
    for game_id, game in games_db.items():
        if user_id in game.get("players", []) and not game.get("started", False):
            user_games.append(game)
    
    if not user_games:
        text = f"{EMOJI['tree']} <b>У тебя пока нет активных игр</b>\n\nСоздай первую игру!"
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
            [InlineKeyboardButton(f"{EMOJI['home']} Назад", callback_data="main_menu")]
        ]
    else:
        text = f"{EMOJI['list']} <b>Твои игры</b>\n\n"
        keyboard = []
        
        for game in user_games[:5]:  # Показываем максимум 5 игр
            game_name = game["name"]
            is_owner = f"{EMOJI['crown']} " if game["owner"] == user_id else ""
            text += f"{is_owner}<b>{game_name}</b>\n"
            text += f"   {EMOJI['money']} {game['amount']} ₽ | {EMOJI['users']} {len(game['players'])}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(f"{EMOJI['tree']} {game_name[:15]}...", callback_data=f"game_{game['id']}")
            ])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI['home']} Назад", callback_data="main_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def game_details_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали игры"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = games_db.get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    
    text = (
        f"{EMOJI['tree']} <b>{game['name']}</b>\n"
        f"{EMOJI['money']} <b>Сумма:</b> {game['amount']} ₽\n"
        f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}"
    )
    
    keyboard = []
    
    if user_id == game["owner"]:
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['link']} Пригласить", callback_data=f"invite_{game_id}"),
            InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
        ])
        keyboard.append([InlineKeyboardButton(f"{EMOJI['play']} Запустить игру", callback_data=f"start_{game_id}")])
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['edit']} Изменить сумму", callback_data=f"edit_{game_id}"),
            InlineKeyboardButton(f"{EMOJI['trash']} Удалить", callback_data=f"delete_{game_id}")
        ])
    elif user_id in game["players"]:
        keyboard.append([InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")])
        keyboard.append([InlineKeyboardButton(f"{EMOJI['wish']} Пожелания", callback_data=f"wish_{game_id}")])
    
    keyboard.append([
        InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="my_games"),
        InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")
    ])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    if user_id in users_db:
        users_db[user_id]["state"] = None
        save_storage()
    
    text = f"{EMOJI['gift']} <b>Главное меню</b>"
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['create']} Создать игру", callback_data="create_game")],
        [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
        [InlineKeyboardButton(f"{EMOJI['help']} Помощь", callback_data="help")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def help_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    query = update.callback_query
    await query.answer()
    
    text = (
        f"{EMOJI['help']} <b>Помощь</b>\n\n"
        f"🎮 <b>Как играть:</b>\n"
        f"1. Создай игру\n"
        f"2. Пригласи друзей по ссылке\n"
        f"3. Запусти распределение\n\n"
        f"🎅 <b>Бот активен 24/7!</b>\n"
        f"Игры сохраняются в памяти и не пропадают."
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def invite_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приглашение"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = games_db.get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    invite_link = f"https://t.me/{context.bot.username}?start={game_id}"
    
    text = (
        f"{EMOJI['gift']} <b>Приглашение в игру</b>\n\n"
        f"{EMOJI['tree']} <b>{game['name']}</b>\n"
        f"{EMOJI['money']} <b>Сумма:</b> {game['amount']} ₽\n"
        f"{EMOJI['users']} <b>Участников:</b> {len(game['players'])}\n\n"
        f"{EMOJI['link']} <b>Ссылка для присоединения:</b>\n"
        f"{invite_link}\n\n"
        f"Отправь эту ссылку друзьям!"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"game_{game_id}")],
        [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ------------------ ОБРАБОТЧИКИ ДЛЯ НЕДОСТАЮЩИХ КНОПОК ------------------

async def players_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Участники игры"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = games_db.get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    # Получаем информацию об участниках
    players_text = f"{EMOJI['users']} <b>Участники игры:</b>\n\n"
    
    try:
        for i, uid in enumerate(game["players"], 1):
            # Пытаемся получить информацию о пользователе
            try:
                user_info = await context.bot.get_chat(int(uid))
                name = user_info.first_name or user_info.username or "Аноним"
                if user_info.last_name:
                    name += f" {user_info.last_name}"
                
                if uid == game["owner"]:
                    players_text += f"{i}. {EMOJI['crown']} <b>{name}</b> (Создатель)\n"
                else:
                    players_text += f"{i}. {name}\n"
            except:
                players_text += f"{i}. Игрок {i}\n"
    except Exception as e:
        print(f"Ошибка при получении информации об участниках: {e}")
        players_text += "Не удалось загрузить список участников\n"
    
    text = f"{EMOJI['tree']} <b>{game['name']}</b>\n\n{players_text}"
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"game_{game_id}")],
        [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def start_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск игры (распределение участников)"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = games_db.get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    
    # Проверяем, что пользователь - владелец игры
    if user_id != game["owner"]:
        await query.answer("Только создатель игры может её запустить!", show_alert=True)
        return
    
    # Проверяем, что есть хотя бы 2 участника
    if len(game["players"]) < 2:
        await query.answer("Нужно минимум 2 участника!", show_alert=True)
        return
    
    # Проверяем, что игра ещё не запущена
    if game.get("started", False):
        await query.answer("Игра уже запущена!", show_alert=True)
        return
    
    # Создаем пары (Тайный Санта -> Получатель)
    players = game["players"].copy()
    random.shuffle(players)
    
    pairs = {}
    for i in range(len(players)):
        giver = players[i]
        receiver = players[(i + 1) % len(players)]
        pairs[giver] = receiver
    
    # Сохраняем пары и отмечаем игру как запущенную
    game["pairs"] = pairs
    game["started"] = True
    save_storage()
    
    # Отправляем сообщения участникам
    success_count = 0
    for giver, receiver in pairs.items():
        try:
            # Получаем информацию о получателе
            receiver_info = await context.bot.get_chat(int(receiver))
            receiver_name = receiver_info.first_name or receiver_info.username or "Тайный Друг"
            
            # Формируем сообщение для дарителя
            message = (
                f"{EMOJI['gift']} <b>Твой Тайный Санта!</b>\n\n"
                f"{EMOJI['star']} <b>Твой получатель:</b> {receiver_name}\n"
                f"{EMOJI['money']} <b>Сумма подарка:</b> {game['amount']} ₽\n"
                f"{EMOJI['tree']} <b>Игра:</b> {game['name']}\n\n"
                f"{EMOJI['santa']} <b>Совет Санты:</b>\n"
                f"Узнай интересы получателя и прояви креативность!\n\n"
                f"Счастливого Рождества! 🎄"
            )
            
            await context.bot.send_message(giver, message, parse_mode="HTML")
            success_count += 1
            
        except Exception as e:
            print(f"Ошибка отправки сообщения пользователю {giver}: {e}")
    
    # Отправляем сообщение создателю со списком пар
    try:
        pairs_list = f"{EMOJI['mail']} <b>Полный список пар (только для тебя):</b>\n\n"
        
        for giver, receiver in pairs.items():
            try:
                giver_info = await context.bot.get_chat(int(giver))
                receiver_info = await context.bot.get_chat(int(receiver))
                
                giver_name = giver_info.first_name or giver_info.username or "Игрок"
                receiver_name = receiver_info.first_name or receiver_info.username or "Игрок"
                
                pairs_list += f"• {giver_name} → {receiver_name}\n"
            except:
                pairs_list += f"• Игрок {giver[:4]}... → Игрок {receiver[:4]}...\n"
        
        await context.bot.send_message(game["owner"], pairs_list, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки списка пар создателю: {e}")
    
    # Уведомляем участников, которые не указали пожелания
    for uid in game["players"]:
        user = users_db.get(uid, {})
        if "wishes" not in user or game_id not in user["wishes"] or not user["wishes"][game_id].get("wish"):
            try:
                await context.bot.send_message(
                    uid,
                    f"{EMOJI['info']} <b>Напоминание о пожеланиях</b>\n\n"
                    f"{EMOJI['tree']} Игра '{game['name']}' началась!\n\n"
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
    
    await query.edit_message_text(
        f"{EMOJI['check']} <b>Распределение проведено!</b>\n\n"
        f"Участникам отправлены сообщения с их получателями.\n"
        f"Тебе отправлен полный список пар.\n\n"
        f"{EMOJI['lock']} <b>Игра завершена и удалена из списка активных.</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
            [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
        ])
    )

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление игры"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = games_db.get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    
    # Проверяем, что пользователь - владелец игры
    if user_id != game["owner"]:
        await query.answer("Только создатель игры может её удалить!", show_alert=True)
        return
    
    # Уведомляем участников об удалении
    for uid in game["players"]:
        if uid != user_id:  # Не отправляем сообщение себе
            try:
                await context.bot.send_message(
                    uid,
                    f"{EMOJI['info']} <b>Игра удалена</b>\n\n"
                    f"{EMOJI['tree']} Игра '{game['name']}' была удалена создателем.",
                    parse_mode="HTML"
                )
            except:
                pass
    
    # Удаляем игру из базы данных
    del games_db[game_id]
    save_storage()
    
    # Удаляем игру из списков пользователей
    for uid, user_data in users_db.items():
        if "games" in user_data and game_id in user_data["games"]:
            user_data["games"].remove(game_id)
    
    await query.edit_message_text(
        f"{EMOJI['check']} <b>Игра удалена</b>\n\n"
        f"Игра '{game['name']}' успешно удалена.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
            [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
        ])
    )

async def wish_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пожелания"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = games_db.get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    
    if user_id not in game["players"]:
        await query.answer("Вы не участник этой игры!", show_alert=True)
        return
    
    # Устанавливаем состояние для получения пожеланий
    if user_id in users_db:
        users_db[user_id]["state"] = f"wait_wish_{game_id}"
        save_storage()
    
    await query.edit_message_text(
        f"{EMOJI['wish']} <b>Укажи свои пожелания</b>\n\n"
        f"Что бы ты хотел получить в подарок?\n\n"
        f"<i>Примеры:</i>\n"
        f"• Книга по программированию\n"
        f"• Тёплый шарф\n"
        f"• Набор для рисования\n"
        f"• Сюрприз\n\n"
        f"Отправь мне свой список:",
        parse_mode="HTML"
    )

async def edit_amount_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменение суммы"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    game = games_db.get(game_id)
    
    if not game:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    user_id = str(query.from_user.id)
    
    # Проверяем, что пользователь - владелец игры
    if user_id != game["owner"]:
        await query.answer("Только создатель игры может менять сумму!", show_alert=True)
        return
    
    # Устанавливаем состояние для получения новой суммы
    if user_id in users_db:
        users_db[user_id]["state"] = f"wait_amount_{game_id}"
        save_storage()
    
    await query.edit_message_text(
        f"{EMOJI['edit']} <b>Изменение суммы</b>\n\n"
        f"Текущая сумма: {game['amount']} ₽\n\n"
        f"Введи новую сумму в рублях:\n\n"
        f"<i>Пример:</i> 1000\n"
        f"<i>Пример:</i> 1500.50\n\n"
        f"Отправь мне сумму:",
        parse_mode="HTML"
    )

# ------------------ ТЕКСТОВЫЙ ОБРАБОТЧИК ------------------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    
    # Создаем пользователя если его нет
    if user_id not in users_db:
        users_db[user_id] = {"games": [], "state": None}
        save_storage()
    
    user_state = users_db[user_id].get("state")
    
    # ---- СОЗДАНИЕ ИГРЫ: НАЗВАНИЕ ----
    if user_state == "wait_game_name":
        if len(text) < 2:
            await update.message.reply_text("Слишком короткое название. Минимум 2 символа:")
            return
        
        users_db[user_id]["tmp_name"] = text
        users_db[user_id]["state"] = "wait_game_amount"
        save_storage()
        
        await update.message.reply_text(
            f"{EMOJI['money']} Отлично! Теперь введи сумму подарка в рублях:\n\n"
            f"<i>Пример:</i> 1000\n"
            f"<i>Пример:</i> 1500.50\n\n"
            f"Отправь мне сумму:",
            parse_mode="HTML"
        )
        return
    
    # ---- СОЗДАНИЕ ИГРЫ: СУММА ----
    if user_state == "wait_game_amount":
        try:
            # Очищаем текст
            clean_text = text.replace(" ", "").replace(",", ".")
            amount = float(clean_text)
            
            if amount <= 0:
                await update.message.reply_text("Сумма должна быть больше 0. Попробуй снова:")
                return
                
            if amount > 1000000:
                await update.message.reply_text("Максимум 1,000,000 ₽. Попробуй снова:")
                return
                
        except ValueError:
            await update.message.reply_text("Это не похоже на число. Пример: 1000 или 1500.50:")
            return
        
        # СОЗДАЕМ ИГРУ
        game_id = str(uuid.uuid4())[:8]
        game_name = users_db[user_id]["tmp_name"]
        
        if amount.is_integer():
            amount_str = str(int(amount))
        else:
            amount_str = f"{amount:.2f}"
        
        games_db[game_id] = {
            "id": game_id,
            "name": game_name,
            "amount": amount_str,
            "owner": user_id,
            "players": [user_id],
            "started": False,
            "pairs": {},
            "created_time": time.time(),
            "last_modified": time.time()
        }
        
        # Обновляем пользователя
        users_db[user_id]["games"].append(game_id)
        users_db[user_id]["state"] = None
        del users_db[user_id]["tmp_name"]
        save_storage()
        
        # ОТПРАВЛЯЕМ ОТВЕТ
        invite_link = f"https://t.me/{context.bot.username}?start={game_id}"
        
        response_text = (
            f"{EMOJI['tree']}✨ <b>Игра создана!</b>\n\n"
            f"🎄 <b>{game_name}</b>\n"
            f"💰 <b>Сумма:</b> {amount_str} ₽\n"
            f"👥 <b>Участников:</b> 1\n\n"
            f"🔗 <b>Ссылка для друзей:</b>\n"
            f"{invite_link}\n\n"
            f"{EMOJI['santa']} Отправь ссылку друзьям!\n"
            f"{EMOJI['bell']} Когда все соберутся — запусти распределение!"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(f"{EMOJI['link']} Пригласить", callback_data=f"invite_{game_id}"),
                InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"players_{game_id}")
            ],
            [InlineKeyboardButton(f"{EMOJI['play']} Запустить игру", callback_data=f"start_{game_id}")],
            [InlineKeyboardButton(f"{EMOJI['wish']} Пожелания", callback_data=f"wish_{game_id}")],
            [InlineKeyboardButton(f"{EMOJI['list']} Мои игры", callback_data="my_games")],
            [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            response_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        print(f"✅ Игра создана: {game_id}, всего игр: {len(games_db)}")
        return
    
    # ---- ПОЖЕЛАНИЯ ----
    if user_state and user_state.startswith("wait_wish_"):
        game_id = user_state.split("_")[-1]
        game = games_db.get(game_id)
        
        if not game:
            await update.message.reply_text("Игра не найдена!")
            return
        
        # Сохраняем пожелания
        if "wishes" not in users_db[user_id]:
            users_db[user_id]["wishes"] = {}
        
        users_db[user_id]["wishes"][game_id] = text
        users_db[user_id]["state"] = None
        save_storage()
        
        await update.message.reply_text(
            f"{EMOJI['check']} <b>Пожелания сохранены!</b>\n\n"
            f"Твой Тайный Санта увидит эти пожелания после распределения.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['back']} К игре", callback_data=f"game_{game_id}")],
                [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
            ])
        )
        return
    
    # ---- ИЗМЕНЕНИЕ СУММЫ ----
    if user_state and user_state.startswith("wait_amount_"):
        game_id = user_state.split("_")[-1]
        game = games_db.get(game_id)
        
        if not game:
            await update.message.reply_text("Игра не найдена!")
            return
        
        try:
            # Очищаем текст
            clean_text = text.replace(" ", "").replace(",", ".")
            amount = float(clean_text)
            
            if amount <= 0:
                await update.message.reply_text("Сумма должна быть больше 0. Попробуй снова:")
                return
                
        except ValueError:
            await update.message.reply_text("Это не похоже на число. Пример: 1000 или 1500.50:")
            return
        
        if amount.is_integer():
            amount_str = str(int(amount))
        else:
            amount_str = f"{amount:.2f}"
        
        # Обновляем сумму в игре
        game["amount"] = amount_str
        game["last_modified"] = time.time()
        users_db[user_id]["state"] = None
        save_storage()
        
        await update.message.reply_text(
            f"{EMOJI['check']} <b>Сумма обновлена!</b>\n\n"
            f"🎄 <b>{game['name']}</b>\n"
            f"💰 <b>Новая сумма:</b> {amount_str} ₽\n"
            f"👥 <b>Участников:</b> {len(game['players'])}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['back']} К игре", callback_data=f"game_{game_id}")],
                [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
            ])
        )
        return
    
    # Если не поняли сообщение
    await update.message.reply_text(
        f"{EMOJI['info']} Используй кнопки меню для навигации.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['home']} Меню", callback_data="main_menu")]
        ])
    )

# ------------------ ПРИСОЕДИНЕНИЕ ПО ССЫЛКЕ ------------------
async def handle_start_with_param(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка /start с параметром (пригласительная ссылка)"""
    args = context.args
    
    if args and len(args[0]) == 8:
        game_id = args[0]
        game = games_db.get(game_id)
        
        if not game:
            await update.message.reply_text(
                f"{EMOJI['cross']} <b>Игра не найдена!</b>\n\n"
                f"Ссылка устарела или игра была удалена.",
                parse_mode="HTML"
            )
            return
        
        if game.get("started", False):
            await update.message.reply_text(
                f"{EMOJI['cross']} <b>Игра уже началась!</b>\n\n"
                f"Распределение уже проведено, присоединиться нельзя.",
                parse_mode="HTML"
            )
            return
        
        user_id = str(update.effective_user.id)
        
        if user_id in game["players"]:
            await update.message.reply_text(
                f"{EMOJI['info']} <b>Ты уже в игре!</b>\n\n"
                f"🎄 <b>{game['name']}</b>\n"
                f"💰 {game['amount']} ₽\n"
                f"👥 Участников: {len(game['players'])}\n\n"
                f"Ждем начала распределения!",
                parse_mode="HTML"
            )
            return
        
        # Добавляем пользователя в игру
        game["players"].append(user_id)
        game["last_modified"] = time.time()
        
        # Добавляем игру пользователю
        if user_id not in users_db:
            users_db[user_id] = {"games": [], "state": None}
        users_db[user_id]["games"].append(game_id)
        save_storage()
        
        await update.message.reply_text(
            f"{EMOJI['check']} <b>Ты присоединился к игре!</b>\n\n"
            f"🎄 <b>{game['name']}</b>\n"
            f"💰 <b>Сумма:</b> {game['amount']} ₽\n"
            f"👥 <b>Участников:</b> {len(game['players'])}\n\n"
            f"{EMOJI['santa']} Ждем, когда создатель запустит распределение!",
            parse_mode="HTML"
        )
        
        print(f"✅ Пользователь {user_id} присоединился к игре {game_id}")
        
        # Уведомляем создателя о новом участнике
        try:
            await context.bot.send_message(
                game["owner"],
                f"{EMOJI['bell']} <b>Новый участник!</b>\n\n"
                f"К твоей игре '{game['name']}' присоединился новый участник.\n"
                f"{EMOJI['users']} Теперь участников: {len(game['players'])}",
                parse_mode="HTML"
            )
        except:
            pass
    else:
        await start(update, context)

# ------------------ FASTAPI ------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan контекст для FastAPI"""
    global application
    
    print("=" * 50)
    print("🎅 Инициализация Тайного Санты...")
    print("=" * 50)
    
    # Проверяем токен
    if not BOT_TOKEN:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не установлен!")
        raise RuntimeError("BOT_TOKEN не установлен")
    
    # Создаем приложение Telegram
    print("🤖 Создаю приложение Telegram...")
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        print("✅ Приложение создано")
    except Exception as e:
        print(f"❌ Ошибка создания приложения: {e}")
        raise
    
    # Регистрируем обработчики
    print("📝 Регистрирую обработчики...")
    try:
        # Команды
        application.add_handler(CommandHandler("start", handle_start_with_param))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("help", help_command))
        
        # Callback кнопки
        application.add_handler(CallbackQueryHandler(create_game_cb, pattern="create_game"))
        application.add_handler(CallbackQueryHandler(my_games_cb, pattern="my_games"))
        application.add_handler(CallbackQueryHandler(game_details_cb, pattern="game_"))
        application.add_handler(CallbackQueryHandler(main_menu_cb, pattern="main_menu"))
        application.add_handler(CallbackQueryHandler(help_cb, pattern="help"))
        application.add_handler(CallbackQueryHandler(invite_cb, pattern="invite_"))
        application.add_handler(CallbackQueryHandler(players_cb, pattern="players_"))
        application.add_handler(CallbackQueryHandler(start_game_cb, pattern="start_"))
        application.add_handler(CallbackQueryHandler(delete_cb, pattern="delete_"))
        application.add_handler(CallbackQueryHandler(wish_cb, pattern="wish_"))
        application.add_handler(CallbackQueryHandler(edit_amount_cb, pattern="edit_"))
        
        # Текстовые сообщения
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
        
        print("✅ Обработчики зарегистрированы")
    except Exception as e:
        print(f"❌ Ошибка регистрации обработчиков: {e}")
        raise
    
    # Инициализируем
    print("⚙️ Инициализирую приложение...")
    try:
        await application.initialize()
        print("✅ Приложение инициализировано")
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        raise
    
    # Настраиваем webhook если есть URL
    if WEBHOOK_URL:
        print(f"🌐 Настраиваю webhook: {WEBHOOK_URL}")
        try:
            await application.bot.set_webhook(WEBHOOK_URL)
            print("✅ Webhook установлен")
        except Exception as e:
            print(f"❌ Ошибка установки webhook: {e}")
    else:
        print("ℹ️ Webhook не настроен")
    
    # Запускаем активный пинг
    print("🔔 Запускаю активный пинг...")
    try:
        ping_thread = threading.Thread(target=active_ping, daemon=True)
        ping_thread.start()
        print("✅ Активный пинг запущен")
    except Exception as e:
        print(f"⚠️  Ошибка запуска пинга: {e}")
    
    print("=" * 50)
    print(f"📊 Статистика:")
    print(f"   🎮 Игр в памяти: {len(games_db)}")
    print(f"   👤 Пользователей: {len(users_db)}")
    print(f"   💾 Данные сохранены в: {STORAGE_FILE}")
    print("=" * 50)
    print("🎅 Тайный Санта готов к работе!")
    print("=" * 50)
    
    yield
    
    print("🎄 Останавливаю бота...")
    if application:
        await application.shutdown()
    print("✅ Бот остановлен")

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(req: Request):
    """Endpoint для webhook"""
    global application
    
    if not application:
        return {"ok": False, "error": "Приложение не инициализировано"}, 500
    
    try:
        data = await req.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        print(f"❌ Ошибка в webhook: {e}")
        return {"ok": False, "error": str(e)}, 500

@app.get("/")
async def root():
    """Главная страница"""
    return {
        "status": "online",
        "service": "secret-santa-bot",
        "games": len(games_db),
        "users": len(users_db),
        "timestamp": time.time(),
        "message": "🎅 Тайный Санта активен! Активный пинг включен.",
        "active_ping": "enabled",
        "ping_interval": "120 seconds",
        "storage_file": STORAGE_FILE,
        "data_persistent": True
    }

@app.get("/ping")
async def ping():
    """Простой ping"""
    return {
        "status": "pong",
        "timestamp": time.time(),
        "message": "Бот активен"
    }

@app.get("/wakeup")
async def wakeup():
    """Пробуждение"""
    return {
        "status": "awake",
        "timestamp": time.time(),
        "message": "🎅 Бот бодрствует благодаря активному пингу!",
        "games_count": len(games_db),
        "users_count": len(users_db)
    }

@app.get("/status")
async def status():
    """Статус"""
    active_games = len([g for g in games_db.values() if not g.get("started", False)])
    finished_games = len([g for g in games_db.values() if g.get("started", False)])
    
    return {
        "status": "active",
        "memory_storage": "enabled",
        "active_ping": "enabled",
        "persistent_storage": "enabled",
        "statistics": {
            "total_games": len(games_db),
            "active_games": active_games,
            "finished_games": finished_games,
            "total_users": len(users_db)
        },
        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time()
    }

@app.get("/debug")
async def debug():
    """Отладочная информация"""
    return {
        "storage": "persistent_file",
        "storage_file": STORAGE_FILE,
        "games": list(games_db.keys()),
        "users_count": len(users_db),
        "games_count": len(games_db),
        "timestamp": time.time(),
        "active_ping": True,
        "environment": {
            "render": "RENDER_EXTERNAL_URL" in os.environ,
            "railway": "RAILWAY_STATIC_URL" in os.environ,
            "heroku": "HEROKU_APP_NAME" in os.environ
        }
    }

# ------------------ ЗАПУСК ------------------
def main():
    """Главная функция"""
    print("=" * 50)
    print("🚀 ЗАПУСК ТАЙНОГО САНТЫ")
    print("=" * 50)
    print("🔥 ОСОБЕННОСТИ:")
    print("• Активный пинг каждые 2 минуты")
    print("• Постоянное хранилище в файле data.json")
    print("• Простая и надежная работа")
    print("• Не спит благодаря активному пингу")
    print("• Данные не пропадают при перезапуске")
    print("=" * 50)
    
    # Определяем хостинг
    if "RENDER_EXTERNAL_URL" in os.environ:
        print(f"🎨 Хостинг: Render")
        print(f"🌐 URL: {os.environ['RENDER_EXTERNAL_URL']}")
    elif "RAILWAY_STATIC_URL" in os.environ:
        print(f"🚂 Хостинг: Railway")
        print(f"🌐 URL: https://{os.environ['RAILWAY_STATIC_URL']}")
    elif "HEROKU_APP_NAME" in os.environ:
        print(f"⚡ Хостинг: Heroku")
        print(f"🌐 URL: https://{os.environ['HEROKU_APP_NAME']}.herokuapp.com")
    else:
        print(f"💻 Режим: Локальная разработка")
    
    print(f"🔧 Порт: {PORT}")
    print(f"🔑 BOT_TOKEN: {'✅ Установлен' if BOT_TOKEN else '❌ Отсутствует'}")
    print(f"🌐 WEBHOOK_URL: {'✅ Установлен' if WEBHOOK_URL else '❌ Отсутствует'}")
    print(f"💾 Хранилище: {STORAGE_FILE}")
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
