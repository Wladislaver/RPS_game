import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
import random
import os
import asyncio
import sqlite3

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_balances (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 1000
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_games (
            user_id INTEGER PRIMARY KEY,
            opponent_id INTEGER,
            move TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Функция для получения баланса пользователя
def get_user_balance(user_id):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM user_balances WHERE user_id = ?', (user_id,))
    balance = cursor.fetchone()
    conn.close()
    return balance[0] if balance else 1000

# Функция для обновления баланса пользователя
def update_user_balance(user_id, amount):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO user_balances (user_id, balance) VALUES (?, ?)', (user_id, 1000))
    cursor.execute('UPDATE user_balances SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

# Функция для добавления активной игры
def add_active_game(user_id, opponent_id, move=None):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO active_games (user_id, opponent_id, move) VALUES (?, ?, ?)', (user_id, opponent_id, move))
    conn.commit()
    conn.close()

# Функция для получения активной игры
def get_active_game(user_id):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT opponent_id, move FROM active_games WHERE user_id = ?', (user_id,))
    game = cursor.fetchone()
    conn.close()
    return {"opponent_id": game[0], "move": game[1]} if game else None

# Функция для удаления активной игры
def remove_active_game(user_id):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM active_games WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# Функция отображения главного меню
async def show_main_menu(message: types.Message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)

    invite_link = f"https://t.me/{(await bot.get_me()).username}?start={user_id}"

    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="🎮 Играть с ботом", callback_data="play_vs_bot"),
        types.InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="add_funds"),
        types.InlineKeyboardButton(text="👥 Пригласить друга", url=invite_link)
    )
    
    await message.answer(
        f"👋 Добро пожаловать в SIFA Games!\n\n"
        f"Ваш текущий баланс: {balance} SIFA",
        reply_markup=builder.as_markup()
    )

# Стартовое сообщение с проверкой приглашения
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) > 1 and args[1].isdigit():
        inviter_id = int(args[1])

        # Проверка, чтобы нельзя было пригласить самого себя или бота
        if inviter_id == user_id or inviter_id == (await bot.get_me()).id:
            await message.answer("Некорректное приглашение! 😅")
            return

        # Инициализация игры с приглашением
        add_active_game(user_id, inviter_id)
        add_active_game(inviter_id, user_id)

        await message.answer(
            f"🎮 Вы приняли приглашение от пользователя с ID {inviter_id}! Игра начинается."
        )
        await send_move_options(message)
    else:
        # Если нет аргументов, показываем главное меню
        await show_main_menu(message)

# Пополнение баланса
@dp.callback_query(lambda c: c.data == "add_funds")
async def add_funds(callback: types.CallbackQuery):
    update_user_balance(callback.from_user.id, 500)
    await callback.message.edit_text(
        f"💳 Ваш баланс пополнен на 500 SIFA!\n"
        f"Текущий баланс: {get_user_balance(callback.from_user.id)} SIFA",
        reply_markup=InlineKeyboardBuilder().add(
            types.InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")
        ).as_markup()
    )

# Возврат в главное меню
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await show_main_menu(callback.message)

# Игра с ботом
@dp.callback_query(lambda c: c.data == "play_vs_bot")
async def play_vs_bot(callback: types.CallbackQuery):
    if get_user_balance(callback.from_user.id) < 10:
        await callback.answer("Недостаточно SIFA!", show_alert=True)
        return
    await send_move_options(callback.message, vs_bot=True)

# Отправка кнопок для выбора жеста
async def send_move_options(message: types.Message, vs_bot=False):
    builder = InlineKeyboardBuilder()
    moves = [("✊ Камень", "rock"), ("✋ Бумага", "paper"), ("✌️ Ножницы", "scissors")]
    for text, move in moves:
        if vs_bot:
            builder.add(types.InlineKeyboardButton(text=text, callback_data=f"bot_move_{move}"))
        else:
            builder.add(types.InlineKeyboardButton(text=text, callback_data=f"pvp_move_{move}"))
    await message.answer("Выберите ваш жест:", reply_markup=builder.as_markup())

# Обработка хода для игры с ботом
@dp.callback_query(lambda c: c.data.startswith("bot_move_"))
async def bot_move(callback: types.CallbackQuery):
    user_move = callback.data.split("_")[2]
    await resolve_game(callback, user_move, vs_bot=True)

# Обработка хода для игры с другом
@dp.callback_query(lambda c: c.data.startswith("pvp_move_"))
async def pvp_move(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_move = callback.data.split("_")[2]
    add_active_game(user_id, get_active_game(user_id)["opponent_id"], user_move)

    opponent_id = get_active_game(user_id)["opponent_id"]
    opponent_game = get_active_game(opponent_id)

    if opponent_game and opponent_game["move"]:
        await resolve_pvp_game(user_id, opponent_id)
    else:
        await callback.message.edit_text("Ожидаем ход соперника...")

# Функция для определения результата игры с ботом
async def resolve_game(callback, user_move, vs_bot=False):
    moves_dict = {"rock": "✊", "paper": "✋", "scissors": "✌️"}
    user_choice = moves_dict[user_move]
    bot_choice = random.choice(list(moves_dict.values()))

    result, balance_change = calculate_result(user_choice, bot_choice)
    update_user_balance(callback.from_user.id, balance_change)

    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="🎮 Сыграть снова", callback_data="play_vs_bot"),
        types.InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")
    )

    await callback.message.edit_text(
        f"Ваш выбор: {user_choice}\n"
        f"Выбор бота: {bot_choice}\n\n"
        f"{result}\n"
        f"Баланс: {get_user_balance(callback.from_user.id)} SIFA",
        reply_markup=builder.as_markup()
    )

# Функция для определения результата игры 1 на 1
async def resolve_pvp_game(user_id, opponent_id):
    moves_dict = {"rock": "✊", "paper": "✋", "scissors": "✌️"}
    user_move = get_active_game(user_id)["move"]
    opponent_move = get_active_game(opponent_id)["move"]

    user_choice = moves_dict[user_move]
    opponent_choice = moves_dict[opponent_move]

    result_user, balance_change_user = calculate_result(user_choice, opponent_choice)
    result_opponent, balance_change_opponent = calculate_result(opponent_choice, user_choice)

    update_user_balance(user_id, balance_change_user)
    update_user_balance(opponent_id, balance_change_opponent)

    await bot.send_message(
        user_id,
        f"Ваш выбор: {user_choice}\n"
        f"Выбор соперника: {opponent_choice}\n\n"
        f"{result_user}\n"
        f"Баланс: {get_user_balance(user_id)} SIFA"
    )

    await bot.send_message(
        opponent_id,
        f"Ваш выбор: {opponent_choice}\n"
        f"Выбор соперника: {user_choice}\n\n"
        f"{result_opponent}\n"
        f"Баланс: {get_user_balance(opponent_id)} SIFA"
    )

    remove_active_game(user_id)
    remove_active_game(opponent_id)

# Функция для расчета результата
def calculate_result(user_choice, opponent_choice):
    if user_choice == opponent_choice:
        return "Ничья!", 0
    elif (user_choice == "✊" and opponent_choice == "✌️") or \
         (user_choice == "✋" and opponent_choice == "✊") or \
         (user_choice == "✌️" and opponent_choice == "✋"):
        return "Вы выиграли +20 SIFA! 🎉", 20
    else:
        return "Вы проиграли 10 SIFA 😢", -10

if __name__ == "__main__":
    logger.info("Starting bot...")
    asyncio.run(dp.start_polling(bot))