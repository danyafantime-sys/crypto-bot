import telebot
import psycopg2
from psycopg2.extras import DictCursor
import hashlib
from datetime import datetime, timedelta
import time
import os
import threading

# ============== КОНФИГ ==============
API_TOKEN = '8237520473:AAE-Mz3f0tuVlWGviPDMsgK28162WVIMBZw'
ADMIN_PASSWORD = 'admin123'
TINKOFF_CARD = '2200 7012 4937 9964'
ADMIN_NICK = '@OldikTeam1337'

bot = telebot.TeleBot(API_TOKEN)

# Словарь для хранения временных данных
user_steps = {}
# Словарь для хранения статуса админа
admin_sessions = {}

# ============== ПОДКЛЮЧЕНИЕ К БАЗЕ ==============
def get_db():
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        # Если нет URL, используем SQLite для локального теста
        import sqlite3
        return sqlite3.connect('crypto_exchange.db')
    
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# ============== ИНИЦИАЛИЗАЦИЯ БАЗЫ ==============
def init_database():
    conn = get_db()
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id SERIAL PRIMARY KEY,
                  username TEXT UNIQUE,
                  password TEXT,
                  telegram_id BIGINT UNIQUE,
                  rub_balance REAL DEFAULT 0,
                  usdt_balance REAL DEFAULT 0,
                  btc_balance REAL DEFAULT 0,
                  eth_balance REAL DEFAULT 0,
                  is_admin INTEGER DEFAULT 0,
                  admin_level INTEGER DEFAULT 0,
                  is_verified INTEGER DEFAULT 0,
                  is_blocked INTEGER DEFAULT 0,
                  block_reason TEXT,
                  full_name TEXT,
                  birth_date TEXT,
                  passport_number TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  last_active TIMESTAMP)''')
    
    # Таблица прав админов
    c.execute('''CREATE TABLE IF NOT EXISTS admin_permissions
                 (admin_id INTEGER REFERENCES users(user_id),
                  can_manage_users INTEGER DEFAULT 0,
                  can_manage_admins INTEGER DEFAULT 0,
                  can_manage_trades INTEGER DEFAULT 0,
                  can_manage_disputes INTEGER DEFAULT 0,
                  can_manage_verification INTEGER DEFAULT 0,
                  can_view_logs INTEGER DEFAULT 0,
                  can_block_users INTEGER DEFAULT 0,
                  can_freeze_funds INTEGER DEFAULT 0)''')
    
    # Таблица ордеров
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (order_id SERIAL PRIMARY KEY,
                  seller_id INTEGER REFERENCES users(user_id),
                  seller_username TEXT,
                  crypto_type TEXT,
                  amount REAL,
                  price_per_unit REAL,
                  total_price REAL,
                  currency TEXT DEFAULT 'RUB',
                  status TEXT DEFAULT 'active',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  min_limit REAL DEFAULT 0,
                  max_limit REAL,
                  payment_method TEXT)''')
    
    # Таблица сделок
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (trade_id SERIAL PRIMARY KEY,
                  order_id INTEGER REFERENCES orders(order_id),
                  buyer_id INTEGER REFERENCES users(user_id),
                  seller_id INTEGER REFERENCES users(user_id),
                  buyer_username TEXT,
                  seller_username TEXT,
                  crypto_type TEXT,
                  amount REAL,
                  price REAL,
                  total REAL,
                  status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  paid_at TIMESTAMP,
                  completed_at TIMESTAMP,
                  dispute_reason TEXT,
                  dispute_winner TEXT,
                  escrow_frozen INTEGER DEFAULT 0,
                  release_date TIMESTAMP)''')
    
    # Таблица верификации
    c.execute('''CREATE TABLE IF NOT EXISTS verification
                 (id SERIAL PRIMARY KEY,
                  user_id INTEGER REFERENCES users(user_id),
                  full_name TEXT,
                  birth_date TEXT,
                  passport_number TEXT,
                  status TEXT DEFAULT 'pending',
                  admin_comment TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  reviewed_at TIMESTAMP,
                  reviewed_by INTEGER REFERENCES users(user_id))''')
    
    # Таблица транзакций
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id SERIAL PRIMARY KEY,
                  from_user TEXT,
                  to_user TEXT,
                  amount REAL,
                  currency TEXT,
                  type TEXT,
                  trade_id INTEGER,
                  status TEXT,
                  date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица правил
    c.execute('''CREATE TABLE IF NOT EXISTS rules
                 (id SERIAL PRIMARY KEY,
                  rule_text TEXT,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_by INTEGER REFERENCES users(user_id))''')
    
    # Таблица тикетов поддержки
    c.execute('''CREATE TABLE IF NOT EXISTS support_tickets
                 (ticket_id SERIAL PRIMARY KEY,
                  user_id INTEGER REFERENCES users(user_id),
                  username TEXT,
                  subject TEXT,
                  message TEXT,
                  status TEXT DEFAULT 'open',
                  assigned_to INTEGER REFERENCES users(user_id),
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  closed_at TIMESTAMP,
                  closed_by INTEGER REFERENCES users(user_id))''')
    
    # Добавляем первого админа
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("""INSERT INTO users 
                    (username, password, telegram_id, is_admin, admin_level)
                    VALUES (%s, %s, %s, %s, %s) RETURNING user_id""",
                 ('admin', 'admin123', 0, 1, 999))
        admin_id = c.fetchone()[0]
        
        c.execute("""INSERT INTO admin_permissions VALUES
                    (%s, 1, 1, 1, 1, 1, 1, 1, 1)""", (admin_id,))
    
    # Добавляем правила
    c.execute("SELECT * FROM rules")
    if not c.fetchone():
        default_rules = """Правила использования P2P биржи:

1. Запрещено создавать фейковые ордера
2. Запрещено мошенничество любого рода
3. После подтверждения оплаты продавец обязан отправить криптовалюту
4. Средства замораживаются на 48 часов после сделки
5. Спорные ситуации решает администрация
6. За нарушение - блокировка без возврата средств"""
        
        c.execute("INSERT INTO rules (rule_text) VALUES (%s)", (default_rules,))
    
    conn.commit()
    conn.close()

# ============== ФУНКЦИИ РАБОТЫ С БД ==============
def get_user_by_telegram_id(telegram_id):
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return result

def get_user_by_username(username):
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM users WHERE username = %s", (username,))
    result = c.fetchone()
    conn.close()
    return result

def create_user(telegram_id, username, password):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO users 
                    (username, password, telegram_id)
                    VALUES (%s, %s, %s)""",
                 (username, password, telegram_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating user: {e}")
        return False
    finally:
        conn.close()

def update_user_password(username, new_password):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET password = %s WHERE username = %s", (new_password, username))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def create_order(seller_id, seller_username, crypto_type, amount, price_per_unit, min_limit=0, max_limit=None, payment_method="Любой"):
    conn = get_db()
    c = conn.cursor()
    try:
        total_price = amount * price_per_unit
        c.execute("""INSERT INTO orders 
                    (seller_id, seller_username, crypto_type, amount, price_per_unit, total_price, 
                     min_limit, max_limit, payment_method)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING order_id""",
                 (seller_id, seller_username, crypto_type, amount, price_per_unit, total_price,
                  min_limit, max_limit, payment_method))
        order_id = c.fetchone()[0]
        conn.commit()
        return order_id
    except Exception as e:
        print(f"Error creating order: {e}")
        return None
    finally:
        conn.close()

def get_active_orders(crypto_type=None):
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    if crypto_type:
        c.execute("""SELECT * FROM orders 
                     WHERE status = 'active' AND crypto_type = %s 
                     ORDER BY price_per_unit ASC""", (crypto_type,))
    else:
        c.execute("""SELECT * FROM orders 
                     WHERE status = 'active' 
                     ORDER BY created_at DESC""")
    result = c.fetchall()
    conn.close()
    return result

def get_order_by_id(order_id):
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
    result = c.fetchone()
    conn.close()
    return result

def create_trade(order_id, buyer_id, buyer_username, amount):
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    try:
        # Получаем информацию об ордере
        c.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
        order = c.fetchone()
        
        if not order or order['status'] != 'active':
            return False, "Ордер неактивен"
        
        # Проверяем лимиты
        if amount < order['min_limit']:
            return False, f"Минимальная сумма: {order['min_limit']}"
        
        if order['max_limit'] and amount > order['max_limit']:
            return False, f"Максимальная сумма: {order['max_limit']}"
        
        # Проверяем баланс покупателя (RUB)
        c.execute("SELECT rub_balance FROM users WHERE user_id = %s", (buyer_id,))
        buyer_balance = c.fetchone()[0]
        
        total_price = amount * order['price_per_unit']
        
        if buyer_balance < total_price:
            return False, "Недостаточно средств"
        
        # Замораживаем средства покупателя
        c.execute("UPDATE users SET rub_balance = rub_balance - %s WHERE user_id = %s", 
                 (total_price, buyer_id))
        
        # Создаем сделку
        release_date = datetime.now() + timedelta(days=2)
        
        c.execute("""INSERT INTO trades 
                    (order_id, buyer_id, seller_id, buyer_username, seller_username,
                     crypto_type, amount, price, total, status, release_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING trade_id""",
                 (order_id, buyer_id, order['seller_id'], buyer_username, order['seller_username'],
                  order['crypto_type'], amount, order['price_per_unit'], total_price, 'pending', release_date))
        
        trade_id = c.fetchone()[0]
        
        # Обновляем количество в ордере
        new_amount = order['amount'] - amount
        if new_amount <= 0:
            c.execute("UPDATE orders SET status = 'completed' WHERE order_id = %s", (order_id,))
        else:
            c.execute("UPDATE orders SET amount = %s WHERE order_id = %s", (new_amount, order_id))
        
        conn.commit()
        return True, trade_id
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def confirm_payment(trade_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""UPDATE trades 
                     SET status = 'paid', paid_at = CURRENT_TIMESTAMP
                     WHERE trade_id = %s AND status = 'pending'""", (trade_id,))
        conn.commit()
        return c.rowcount > 0
    except:
        return False
    finally:
        conn.close()

def confirm_receipt(trade_id):
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    try:
        # Получаем информацию о сделке
        c.execute("SELECT * FROM trades WHERE trade_id = %s", (trade_id,))
        trade = c.fetchone()
        
        if trade['status'] != 'paid':
            return False, "Сделка не в статусе 'оплачено'"
        
        # Переводим крипту покупателю
        crypto_col = f"{trade['crypto_type'].lower()}_balance"
        c.execute(f"UPDATE users SET {crypto_col} = {crypto_col} + %s WHERE user_id = %s",
                 (trade['amount'], trade['buyer_id']))
        
        # Меняем статус сделки
        c.execute("""UPDATE trades 
                     SET status = 'frozen', completed_at = CURRENT_TIMESTAMP
                     WHERE trade_id = %s""", (trade_id,))
        
        conn.commit()
        return True, "Сделка завершена, средства заморожены на 48 часов"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def release_funds(trade_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM trades WHERE trade_id = %s", (trade_id,))
        trade = c.fetchone()
        
        if trade['status'] != 'frozen':
            return False, "Средства не заморожены"
        
        # Переводим RUB продавцу
        c.execute("UPDATE users SET rub_balance = rub_balance + %s WHERE user_id = %s",
                 (trade['total'], trade['seller_id']))
        
        c.execute("UPDATE trades SET status = 'completed' WHERE trade_id = %s", (trade_id,))
        
        conn.commit()
        return True, "Средства разморожены и отправлены продавцу"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_user_trades(user_id, limit=10):
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("""SELECT * FROM trades 
                 WHERE buyer_id = %s OR seller_id = %s 
                 ORDER BY created_at DESC LIMIT %s""",
              (user_id, user_id, limit))
    result = c.fetchall()
    conn.close()
    return result

def auto_release_funds():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT trade_id FROM trades WHERE status = 'frozen' AND release_date <= CURRENT_TIMESTAMP")
    frozen = c.fetchall()
    
    for trade_id in frozen:
        release_funds(trade_id[0])
    
    conn.close()

def create_verification_request(user_id, full_name, birth_date, passport_number):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO verification 
                    (user_id, full_name, birth_date, passport_number)
                    VALUES (%s, %s, %s, %s)""",
                 (user_id, full_name, birth_date, passport_number))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_pending_verifications():
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("""SELECT v.*, u.username FROM verification v
                 JOIN users u ON v.user_id = u.user_id
                 WHERE v.status = 'pending'""")
    result = c.fetchall()
    conn.close()
    return result

def approve_verification(verification_id, user_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE verification SET status = 'approved' WHERE id = %s", (verification_id,))
        c.execute("UPDATE users SET is_verified = 1 WHERE user_id = %s", (user_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def reject_verification(verification_id, comment):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE verification SET status = 'rejected', admin_comment = %s WHERE id = %s", (comment, verification_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def check_admin_permission(admin_id, permission):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT admin_level FROM users WHERE user_id = %s", (admin_id,))
    level = c.fetchone()
    
    if level and level[0] >= 999:
        conn.close()
        return True
    
    c.execute(f"SELECT {permission} FROM admin_permissions WHERE admin_id = %s", (admin_id,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1

def get_rules():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT rule_text FROM rules ORDER BY id DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result[0] if result else "Правила не найдены"

def create_support_ticket(user_id, username, subject, message):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO support_tickets 
                    (user_id, username, subject, message)
                    VALUES (%s, %s, %s, %s) RETURNING ticket_id""",
                 (user_id, username, subject, message))
        ticket_id = c.fetchone()[0]
        conn.commit()
        return ticket_id
    except:
        return None
    finally:
        conn.close()

def get_open_tickets():
    conn = get_db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM support_tickets WHERE status = 'open' ORDER BY created_at")
    result = c.fetchall()
    conn.close()
    return result

def close_ticket(ticket_id, admin_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""UPDATE support_tickets 
                     SET status = 'closed', closed_at = CURRENT_TIMESTAMP, closed_by = %s
                     WHERE ticket_id = %s""", (admin_id, ticket_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def withdraw_request(user_id, amount, currency, address):
    conn = get_db()
    c = conn.cursor()
    try:
        if currency == 'RUB':
            c.execute("UPDATE users SET rub_balance = rub_balance - %s WHERE user_id = %s", (amount, user_id))
        elif currency == 'USDT':
            c.execute("UPDATE users SET usdt_balance = usdt_balance - %s WHERE user_id = %s", (amount, user_id))
        elif currency == 'BTC':
            c.execute("UPDATE users SET btc_balance = btc_balance - %s WHERE user_id = %s", (amount, user_id))
        elif currency == 'ETH':
            c.execute("UPDATE users SET eth_balance = eth_balance - %s WHERE user_id = %s", (amount, user_id))
        
        c.execute("""INSERT INTO transactions 
                    (from_user, to_user, amount, currency, type, status)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                 (str(user_id), 'withdraw', amount, currency, 'withdraw', 'completed'))
        
        conn.commit()
        return True, "Заявка на вывод создана"
    except:
        return False, "Ошибка"
    finally:
        conn.close()

# ============== КОМАНДЫ БОТА ==============
# (ЗДЕСЬ ВСТАВЛЯЕМ ВСЕ ОБРАБОТЧИКИ ИЗ ПРЕДЫДУЩИХ СООБЩЕНИЙ)
# Я пропущу их для краткости, но ты вставь сюда все команды из предыдущих частей
# Они остаются без изменений, только функции БД мы уже заменили

@bot.message_handler(commands=['start'])
def cmd_start(message):
    # ... (весь код из предыдущих частей)
    pass

# ============== ЗАПУСК ==============
if __name__ == '__main__':
    print("Инициализация базы данных...")
    init_database()
    print("База данных готова!")
    print("Бот запущен и работает!")
    
    # Запускаем поток для автоматической разморозки
    def scheduler():
        while True:
            time.sleep(3600)  # 1 час
            auto_release_funds()
            print("Автоматическая разморозка выполнена")
    
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    
    bot.infinity_polling()