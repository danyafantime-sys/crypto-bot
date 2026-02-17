import telebot
import sqlite3
import hashlib
from datetime import datetime

# ============== КОНФИГ ==============
API_TOKEN = '8237520473:AAE-Mz3f0tuVlWGviPDMsgK28162WVIMBZw'
ADMIN_PASSWORD = 'admin123'
TINKOFF_CARD = '2200 7012 4937 9964'
ADMIN_NICK = '@OldikTeam1337'

bot = telebot.TeleBot(API_TOKEN)

# Словарь для хранения временных данных (шаги регистрации)
user_steps = {}

# ============== БАЗА ДАННЫХ ==============
def init_database():
    conn = sqlite3.connect('crypto_exchange.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  telegram_id INTEGER UNIQUE,
                  rub_balance REAL DEFAULT 0,
                  usdt_balance REAL DEFAULT 0,
                  is_admin INTEGER DEFAULT 0,
                  created_at TEXT)''')
    conn.commit()
    conn.close()

def get_user_by_telegram_id(telegram_id):
    conn = sqlite3.connect('crypto_exchange.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return result

def get_user_by_username(username):
    conn = sqlite3.connect('crypto_exchange.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return result

def create_user(telegram_id, username, password):
    conn = sqlite3.connect('crypto_exchange.db')
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO users 
                    (username, password, telegram_id, created_at)
                    VALUES (?, ?, ?, ?)""",
                 (username, password, telegram_id, str(datetime.now())))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def update_user_password(username, new_password):
    conn = sqlite3.connect('crypto_exchange.db')
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET password = ? WHERE username = ?", (new_password, username))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

# ============== КОМАНДЫ ==============
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user = get_user_by_telegram_id(message.from_user.id)
    user_id = message.from_user.id
    
    # Очищаем предыдущие шаги
    if user_id in user_steps:
        del user_steps[user_id]
    
    if user:
        bot.reply_to(message, 
            f"👋 Привет, {user[1]}!\n\n"
            f"💰 Баланс RUB: {user[4]:.2f}\n"
            f"💵 Баланс USDT: {user[5]:.2f}\n\n"
            f"/balance - Баланс\n"
            f"/deposit - Пополнить\n"
            f"/change_password - Сменить пароль\n"
            f"/admin - Админка")
    else:
        bot.reply_to(message,
            "🚀 Добро пожаловать в Crypto Bot!\n\n"
            "/register - Регистрация\n"
            "/login - Вход")

@bot.message_handler(commands=['register'])
def cmd_register(message):
    user_id = message.from_user.id
    
    # Проверяем, не зарегистрирован ли уже
    if get_user_by_telegram_id(user_id):
        bot.reply_to(message, "❌ Ты уже зарегистрирован! Используй /login")
        return
    
    # Очищаем предыдущие шаги
    if user_id in user_steps:
        del user_steps[user_id]
    
    # Запоминаем, что пользователь начал регистрацию
    user_steps[user_id] = {'step': 'waiting_username'}
    
    bot.reply_to(message, "📝 Придумай логин (только буквы и цифры):")

@bot.message_handler(func=lambda message: message.from_user.id in user_steps and user_steps[message.from_user.id]['step'] == 'waiting_username')
def process_username(message):
    user_id = message.from_user.id
    username = message.text.strip()
    
    if not username.isalnum():
        bot.reply_to(message, "❌ Логин только буквы и цифры. Попробуй снова:")
        return
    
    if get_user_by_username(username):
        bot.reply_to(message, "❌ Логин занят. Придумай другой:")
        return
    
    # Сохраняем логин и переходим к следующему шагу
    user_steps[user_id]['username'] = username
    user_steps[user_id]['step'] = 'waiting_password'
    
    bot.reply_to(message, "🔑 Теперь придумай пароль (минимум 6 символов):")

@bot.message_handler(func=lambda message: message.from_user.id in user_steps and user_steps[message.from_user.id]['step'] == 'waiting_password')
def process_password(message):
    user_id = message.from_user.id
    password = message.text.strip()
    
    if len(password) < 6:
        bot.reply_to(message, "❌ Пароль должен быть минимум 6 символов. Попробуй снова:")
        return
    
    username = user_steps[user_id]['username']
    
    if create_user(user_id, username, password):
        bot.reply_to(message, f"✅ Регистрация успешна! Твой логин: {username}")
    else:
        bot.reply_to(message, "❌ Ошибка регистрации")
    
    # Очищаем шаги
    del user_steps[user_id]

@bot.message_handler(commands=['login'])
def cmd_login(message):
    user_id = message.from_user.id
    
    if get_user_by_telegram_id(user_id):
        bot.reply_to(message, "❌ Ты уже вошел!")
        return
    
    # Очищаем предыдущие шаги
    if user_id in user_steps:
        del user_steps[user_id]
    
    # Запоминаем, что пользователь начал вход
    user_steps[user_id] = {'step': 'waiting_login_username'}
    
    bot.reply_to(message, "🔐 Введи логин:")

@bot.message_handler(func=lambda message: message.from_user.id in user_steps and user_steps[message.from_user.id]['step'] == 'waiting_login_username')
def process_login_username(message):
    user_id = message.from_user.id
    username = message.text.strip()
    
    user = get_user_by_username(username)
    
    if not user:
        bot.reply_to(message, "❌ Пользователь не найден. Попробуй снова:")
        return
    
    user_steps[user_id]['username'] = username
    user_steps[user_id]['step'] = 'waiting_login_password'
    
    bot.reply_to(message, "🔑 Введи пароль:")

@bot.message_handler(func=lambda message: message.from_user.id in user_steps and user_steps[message.from_user.id]['step'] == 'waiting_login_password')
def process_login_password(message):
    user_id = message.from_user.id
    password = message.text.strip()
    username = user_steps[user_id]['username']
    
    user = get_user_by_username(username)
    
    if user[2] == password:
        conn = sqlite3.connect('crypto_exchange.db')
        c = conn.cursor()
        c.execute("UPDATE users SET telegram_id = ? WHERE username = ?", (user_id, username))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Вход выполнен! Добро пожаловать, {username}")
    else:
        bot.reply_to(message, "❌ Неверный пароль. Попробуй снова:")
        return
    
    # Очищаем шаги
    del user_steps[user_id]

# ============== СМЕНА ПАРОЛЯ ==============
@bot.message_handler(commands=['change_password'])
def cmd_change_password(message):
    user_id = message.from_user.id
    user = get_user_by_telegram_id(user_id)
    
    if not user:
        bot.reply_to(message, "❌ Сначала войди через /login")
        return
    
    # Очищаем предыдущие шаги
    if user_id in user_steps:
        del user_steps[user_id]
    
    user_steps[user_id] = {'step': 'waiting_old_password'}
    
    bot.reply_to(message, "🔐 Введи ТЕКУЩИЙ пароль:")

@bot.message_handler(func=lambda message: message.from_user.id in user_steps and user_steps[message.from_user.id]['step'] == 'waiting_old_password')
def process_old_password(message):
    user_id = message.from_user.id
    old_password = message.text.strip()
    user = get_user_by_telegram_id(user_id)
    
    if user[2] != old_password:
        bot.reply_to(message, "❌ Неверный пароль. Попробуй снова:")
        return
    
    user_steps[user_id]['step'] = 'waiting_new_password'
    
    bot.reply_to(message, "🔑 Введи НОВЫЙ пароль (минимум 6 символов):")

@bot.message_handler(func=lambda message: message.from_user.id in user_steps and user_steps[message.from_user.id]['step'] == 'waiting_new_password')
def process_new_password(message):
    user_id = message.from_user.id
    new_password = message.text.strip()
    user = get_user_by_telegram_id(user_id)
    
    if len(new_password) < 6:
        bot.reply_to(message, "❌ Пароль должен быть минимум 6 символов. Введи снова:")
        return
    
    if update_user_password(user[1], new_password):
        bot.reply_to(message, "✅ Пароль успешно изменен!")
    else:
        bot.reply_to(message, "❌ Ошибка при смене пароля")
    
    del user_steps[user_id]

@bot.message_handler(commands=['balance'])
def cmd_balance(message):
    user = get_user_by_telegram_id(message.from_user.id)
    
    if not user:
        bot.reply_to(message, "❌ Сначала войди через /login")
        return
    
    bot.reply_to(message,
        f"💰 Твой баланс:\n"
        f"💳 RUB: {user[4]:.2f}\n"
        f"💵 USDT: {user[5]:.2f}")

@bot.message_handler(commands=['deposit'])
def cmd_deposit(message):
    user = get_user_by_telegram_id(message.from_user.id)
    
    if not user:
        bot.reply_to(message, "❌ Сначала войди через /login")
        return
    
    bot.reply_to(message,
        f"💳 Пополнение RUB:\n\n"
        f"Переведи на карту:\n"
        f"💳 {TINKOFF_CARD}\n\n"
        f"После перевода напиши админу {ADMIN_NICK}")

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    user_id = message.from_user.id
    
    # Очищаем предыдущие шаги
    if user_id in user_steps:
        del user_steps[user_id]
    
    user_steps[user_id] = {'step': 'waiting_admin_password'}
    
    bot.reply_to(message, "🔐 Введи пароль админа:")

@bot.message_handler(func=lambda message: message.from_user.id in user_steps and user_steps[message.from_user.id]['step'] == 'waiting_admin_password')
def process_admin_password(message):
    user_id = message.from_user.id
    
    if message.text.strip() == ADMIN_PASSWORD:
        bot.reply_to(message,
            "👑 Панель администратора:\n\n"
            "/users - Список пользователей\n"
            "/addmoney логин сумма - Пополнить баланс RUB")
    else:
        bot.reply_to(message, "❌ Неверный пароль")
    
    del user_steps[user_id]

@bot.message_handler(commands=['users'])
def cmd_users(message):
    conn = sqlite3.connect('crypto_exchange.db')
    c = conn.cursor()
    c.execute("SELECT username, rub_balance, usdt_balance FROM users ORDER BY rub_balance DESC LIMIT 10")
    users = c.fetchall()
    conn.close()
    
    if not users:
        bot.reply_to(message, "📭 Пользователей пока нет")
        return
    
    text = "📋 Список пользователей:\n\n"
    for u in users:
        text += f"👤 {u[0]}: {u[1]:.2f} RUB | {u[2]:.2f} USDT\n"
    
    bot.reply_to(message, text)

@bot.message_handler(commands=['addmoney'])
def cmd_addmoney(message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "❌ Использование: /addmoney логин сумма")
            return
        
        username = parts[1]
        amount = float(parts[2])
        
        conn = sqlite3.connect('crypto_exchange.db')
        c = conn.cursor()
        c.execute("UPDATE users SET rub_balance = rub_balance + ? WHERE username = ?", (amount, username))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ Баланс {username} пополнен на {amount} RUB")
    except:
        bot.reply_to(message, "❌ Ошибка. Проверь формат: /addmoney логин сумма")

# Обработка всех остальных сообщений (сброс шагов)
@bot.message_handler(func=lambda message: True)
def handle_all(message):
    user_id = message.from_user.id
    # Если пользователь в каком-то шаге, но пишет фигню - сбрасываем
    if user_id in user_steps:
        del user_steps[user_id]
        bot.reply_to(message, "🔄 Действие отменено. Используй /start для начала работы.")

# ============== ЗАПУСК ==============
if __name__ == '__main__':
    print("Запуск базы данных...")
    init_database()
    print("Бот запущен и работает!")
    bot.infinity_polling()