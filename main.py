import os
import random
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

games = {}
user_states = {}
organizer_games = {}
bot_username = None

def generate_game_id():
    return str(uuid.uuid4())[:8]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_username
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if bot_username is None:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
    
    if context.args and len(context.args) > 0:
        game_id = context.args[0]
        if game_id in games:
            game = games[game_id]
            
            if game["state"] != "collecting":
                await update.message.reply_text("🎄 Эта игра ещё не готова к регистрации участников!")
                return
            
            if user_id in game["participants"]:
                await update.message.reply_text("🎅 Ты уже зарегистрирован в этой игре!")
                return
            
            game["participants"][user_id] = username
            user_states[user_id] = {"role": "participant", "state": "registered", "game_id": game_id}
            
            await update.message.reply_text(
                f"🎉 Ура! Ты в игре «{game['name']}»!\n"
                f"🎁 Участников уже: {len(game['participants'])}\n\n"
                "❄️ Жди волшебного сообщения с именем того,\n"
                "кому ты будешь дарить подарок! 🎄✨"
            )
            return
        else:
            await update.message.reply_text("🎅 Упс! Игра с таким кодом не найдена.")
            return
    
    keyboard = [
        [
            InlineKeyboardButton("🎅 Организатор", callback_data="role_organizer"),
            InlineKeyboardButton("🎁 Участник", callback_data="role_participant")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎄✨ Привет! Добро пожаловать в Тайного Санту! ✨🎄\n\n"
        "🎅 Выбери свою роль:",
        reply_markup=reply_markup
    )

async def show_organizer_menu(context, user_id, message_func, edit=False):
    user_games = organizer_games.get(user_id, [])
    
    keyboard = [[InlineKeyboardButton("🎄 Создать новую игру", callback_data="new_game")]]
    
    incomplete_games = []
    complete_games = []
    
    if user_games:
        for game_id in user_games:
            if game_id in games:
                game = games[game_id]
                if game["state"] == "collecting":
                    complete_games.append((game_id, game))
                elif game["state"] in ["waiting_sum", "waiting_name"]:
                    incomplete_games.append((game_id, game))
    
    for game_id, game in incomplete_games:
        btn_text = f"⏳ {game['name']} (не завершена)"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"resume_game_{game_id}")])
    
    for game_id, game in complete_games:
        btn_text = f"🎁 {game['name']} ({len(game['participants'])} уч.)"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_game_{game_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🎅✨ Панель организатора ✨🎅\n\n"
        "Выбери существующую игру или создай новую:"
    )
    
    if edit:
        await message_func(text, reply_markup=reply_markup)
    else:
        await message_func(text, reply_markup=reply_markup)

async def show_game_menu(context, game_id, message_func):
    game = games[game_id]
    invite_link = f"https://t.me/{bot_username}?start={game_id}"
    
    keyboard = [
        [InlineKeyboardButton("👥 Посмотреть участников", callback_data=f"view_participants_{game_id}")],
        [InlineKeyboardButton("🎉 Запустить распределение!", callback_data=f"run_game_{game_id}")],
        [InlineKeyboardButton("🔙 К списку игр", callback_data="back_to_games")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message_func(
        f"🎄 Игра: «{game['name']}» 🎄\n\n"
        f"💰 Сумма подарка: {game['gift_sum']} ₽\n"
        f"👥 Участников: {len(game['participants'])}\n\n"
        f"🔗 Ссылка для друзей:\n{invite_link}\n\n"
        "✨ Отправь эту ссылку участникам! ✨",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_username
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    data = query.data
    
    if bot_username is None:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
    
    if data == "role_organizer":
        user_states[user_id] = {"role": "organizer", "state": "menu"}
        if user_id not in organizer_games:
            organizer_games[user_id] = []
        await show_organizer_menu(context, user_id, query.edit_message_text, edit=True)
    
    elif data == "role_participant":
        await query.edit_message_text(
            "🎁 Ты выбрал роль участника! 🎁\n\n"
            "❄️ Попроси у организатора ссылку для входа в игру.\n"
            "Просто перейди по ней — и ты в игре! 🎄✨"
        )
    
    elif data == "new_game":
        user_states[user_id] = {"role": "organizer", "state": "waiting_name"}
        await query.edit_message_text(
            "🎄 Создаём новую игру! 🎄\n\n"
            "✨ Придумай название для игры\n"
            "(например: «Новый год 2025» или «Офис»):"
        )
    
    elif data.startswith("select_game_"):
        game_id = data.replace("select_game_", "")
        if game_id in games:
            user_states[user_id]["state"] = "menu"
            user_states[user_id]["active_game"] = game_id
            await show_game_menu(context, game_id, query.edit_message_text)
    
    elif data.startswith("resume_game_"):
        game_id = data.replace("resume_game_", "")
        if game_id in games:
            game = games[game_id]
            user_states[user_id]["active_game"] = game_id
            user_states[user_id]["state"] = game["state"]
            
            if game["state"] == "waiting_sum":
                await query.edit_message_text(
                    f"🎄 Продолжаем настройку игры «{game['name']}»! 🎄\n\n"
                    "💰 Введи сумму подарка (например 3000):"
                )
    
    elif data.startswith("view_participants_"):
        game_id = data.replace("view_participants_", "")
        if game_id in games:
            game = games[game_id]
            participants = game["participants"]
            
            if participants:
                participant_list = "\n".join(
                    [f'🎁 <a href="tg://user?id={uid}">{name}</a>' for uid, name in participants.items()]
                )
            else:
                participant_list = "Пока никого нет 😢"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"select_game_{game_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"👥 Участники игры «{game['name']}»:\n\n"
                f"{participant_list}\n\n"
                f"✨ Всего: {len(participants)} чел.",
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    
    elif data.startswith("run_game_"):
        game_id = data.replace("run_game_", "")
        if game_id in games:
            await run_game(query, context, game_id, user_id)
    
    elif data == "back_to_games":
        user_states[user_id]["state"] = "menu"
        await show_organizer_menu(context, user_id, query.edit_message_text, edit=True)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_username
    user_id = update.effective_user.id
    text = update.message.text
    username = update.effective_user.username or update.effective_user.first_name
    
    if bot_username is None:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
    
    if user_id not in user_states:
        await update.message.reply_text("🎄 Напиши /start чтобы начать! ✨")
        return
    
    state = user_states[user_id]
    
    if state["role"] == "organizer":
        if state["state"] == "waiting_name":
            game_id = generate_game_id()
            games[game_id] = {
                "id": game_id,
                "name": text,
                "admin": user_id,
                "participants": {user_id: username},
                "gift_sum": None,
                "state": "waiting_sum"
            }
            organizer_games[user_id].append(game_id)
            user_states[user_id]["state"] = "waiting_sum"
            user_states[user_id]["active_game"] = game_id
            
            await update.message.reply_text(
                f"🎉 Отлично! Игра «{text}» создана!\n"
                f"🎅 Ты автоматически добавлен как участник.\n\n"
                "💰 Теперь введи сумму подарка (например 3000):"
            )
        
        elif state["state"] == "waiting_sum":
            if not text.isdigit():
                await update.message.reply_text("🎅 Введи число, например 3000!")
                return
            
            game_id = state.get("active_game")
            if not game_id or game_id not in games:
                await update.message.reply_text("🎄 Напиши /start чтобы начать заново!")
                return
            
            game = games[game_id]
            game["gift_sum"] = int(text)
            game["state"] = "collecting"
            user_states[user_id]["state"] = "menu"
            
            invite_link = f"https://t.me/{bot_username}?start={game_id}"
            
            keyboard = [
                [InlineKeyboardButton("👥 Посмотреть участников", callback_data=f"view_participants_{game_id}")],
                [InlineKeyboardButton("🎉 Запустить распределение!", callback_data=f"run_game_{game_id}")],
                [InlineKeyboardButton("🔙 К списку игр", callback_data="back_to_games")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🎄✨ Игра «{game['name']}» готова! ✨🎄\n\n"
                f"💰 Сумма подарка: {game['gift_sum']} ₽\n"
                f"👥 Участников: {len(game['participants'])} (включая тебя)\n\n"
                f"🔗 Ссылка для друзей:\n{invite_link}\n\n"
                "❄️ Отправь эту волшебную ссылку участникам!\n"
                "Когда все соберутся — жми «Запустить распределение»! 🎅",
                reply_markup=reply_markup
            )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in organizer_games or not organizer_games[user_id]:
        await update.message.reply_text("🎅 У тебя нет активных игр!")
        return
    
    user_game_ids = organizer_games[user_id]
    active_games = [gid for gid in user_game_ids if gid in games]
    
    if not active_games:
        await update.message.reply_text("🎅 У тебя нет активных игр!")
        return
    
    if len(active_games) == 1:
        await run_game_by_command(update, context, active_games[0], user_id)
    else:
        keyboard = []
        for game_id in active_games:
            game = games[game_id]
            btn_text = f"🎁 {game['name']} ({len(game['participants'])} уч.)"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"run_game_{game_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🎄 Выбери игру для запуска распределения:",
            reply_markup=reply_markup
        )

async def run_game_by_command(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id: str, user_id: int):
    if game_id not in games:
        await update.message.reply_text("🎅 Игра не найдена!")
        return
    
    game = games[game_id]
    
    if len(game["participants"]) < 2:
        await update.message.reply_text(
            f"❄️ Недостаточно участников!\n"
            f"Сейчас: {len(game['participants'])}\n"
            "Нужно минимум 2 человека! 🎅"
        )
        return
    
    participants = list(game["participants"].items())
    random.shuffle(participants)
    
    results = []
    for i in range(len(participants)):
        giver_id, giver_name = participants[i]
        receiver_id, receiver_name = participants[(i + 1) % len(participants)]
        results.append((giver_id, giver_name, receiver_id, receiver_name))
    
    success_count = 0
    for giver_id, giver_name, receiver_id, receiver_name in results:
        try:
            await context.bot.send_message(
                chat_id=giver_id,
                text=f"🎄✨ Тайный Санта выбрал тебя! ✨🎄\n\n"
                     f"🎁 Ты даришь подарок: @{receiver_name}\n"
                     f"💰 Сумма: {game['gift_sum']} ₽\n\n"
                     f"❄️ Пусть этот подарок принесёт радость! 🎅"
            )
            success_count += 1
        except Exception:
            pass
    
    participant_list = "\n".join([f"🎁 {name}" for _, name in participants])
    await update.message.reply_text(
        f"🎉✨ Игра «{game['name']}» завершена! ✨🎉\n\n"
        f"👥 Участников: {len(participants)}\n"
        f"📨 Сообщений отправлено: {success_count}\n\n"
        f"🎄 Участники:\n{participant_list}\n\n"
        "❄️ Счастливого Нового Года! 🎅🎄"
    )
    
    for giver_id, _, _, _ in results:
        if giver_id in user_states:
            del user_states[giver_id]
    
    if user_id in organizer_games:
        organizer_games[user_id] = [g for g in organizer_games[user_id] if g != game_id]
    
    del games[game_id]

async def run_game(query, context: ContextTypes.DEFAULT_TYPE, game_id: str, user_id: int):
    if game_id not in games:
        await query.edit_message_text("🎅 Игра не найдена!")
        return
    
    game = games[game_id]
    
    if len(game["participants"]) < 2:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"select_game_{game_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"❄️ Недостаточно участников!\n"
            f"Сейчас: {len(game['participants'])}\n"
            "Нужно минимум 2 человека! 🎅",
            reply_markup=reply_markup
        )
        return
    
    participants = list(game["participants"].items())
    random.shuffle(participants)
    
    results = []
    for i in range(len(participants)):
        giver_id, giver_name = participants[i]
        receiver_id, receiver_name = participants[(i + 1) % len(participants)]
        results.append((giver_id, giver_name, receiver_id, receiver_name))
    
    success_count = 0
    for giver_id, giver_name, receiver_id, receiver_name in results:
        try:
            await context.bot.send_message(
                chat_id=giver_id,
                text=f"🎄✨ Тайный Санта выбрал тебя! ✨🎄\n\n"
                     f"🎁 Ты даришь подарок: @{receiver_name}\n"
                     f"💰 Сумма: {game['gift_sum']} ₽\n\n"
                     f"❄️ Пусть этот подарок принесёт радость! 🎅"
            )
            success_count += 1
        except Exception:
            pass
    
    participant_list = "\n".join([f"🎁 {name}" for _, name in participants])
    
    keyboard = [[InlineKeyboardButton("🔙 К списку игр", callback_data="back_to_games")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🎉✨ Игра «{game['name']}» завершена! ✨🎉\n\n"
        f"👥 Участников: {len(participants)}\n"
        f"📨 Сообщений отправлено: {success_count}\n\n"
        f"🎄 Участники:\n{participant_list}\n\n"
        "❄️ Счастливого Нового Года! 🎅🎄",
        reply_markup=reply_markup
    )
    
    for giver_id, _, _, _ in results:
        if giver_id in user_states:
            del user_states[giver_id]
    
    if user_id in organizer_games:
        organizer_games[user_id] = [g for g in organizer_games[user_id] if g != game_id]
    
    del games[game_id]

async def games_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_states:
        user_states[user_id] = {"role": "organizer", "state": "menu"}
    
    if user_id not in organizer_games:
        organizer_games[user_id] = []
    
    await show_organizer_menu(context, user_id, update.message.reply_text, edit=False)


def main():
    token = os.getenv("BOT_TOKEN")
    
    if not token:
        print("🎅 Ошибка: BOT_TOKEN не установлен!")
        print("Добавьте токен бота в переменные окружения.")
        return
    
    app = ApplicationBuilder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("games", games_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("🎄 Бот Тайный Санта запущен! ✨")
    app.run_polling()


if __name__ == "__main__":
    main()
