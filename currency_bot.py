import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import sqlite3
from datetime import datetime, timezone
import configparser

def create_table(conn):
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS currency_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        currency TEXT,
        rate REAL,
        next_updated DATETIME
    )
    """)
    cursor.execute("""
              CREATE TABLE IF NOT EXISTS visits (
                  id INTEGER PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  visit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
              )
              """)
    conn.commit()

async def fetch_data_from_api(url):
    URL = f'https://v6.exchangerate-api.com/v6/latest/USD'
    async with httpx.AsyncClient() as client:
        config = configparser.ConfigParser()
        config.read('config.ini')
        api_key = config['DEFAULT']['API_Key']
        client.headers["Authorization"] = "Bearer " + api_key
        response = await client.get(URL)
        data = response.json()
    conversion_rates = data.get('conversion_rates', {})
    next_updated = data.get('time_next_update_utc')
    return conversion_rates, next_updated

def insert_data_into_db(conn, conversion_rates, next_updated):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM currency_rates")
    for currency, rate in conversion_rates.items():
        cursor.execute("INSERT INTO currency_rates (currency, rate, next_updated) VALUES (?, ?, ?)",
                       (currency, rate, next_updated))
    conn.commit()

def is_table_empty(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    return count == 0

def check_data_in_db(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT next_updated FROM currency_rates LIMIT 1")
    next_updated = cursor.fetchone()
    next_updated = datetime.strptime(next_updated[0], '%a, %d %b %Y %H:%M:%S %z')
    current_time = get_current_utc_time()
    if current_time >= next_updated:
        return True
    return False

def get_current_utc_time():
    return datetime.now(timezone.utc)

async def get_rate(target):
    database = 'currency_rates_api.db'
    conn = sqlite3.connect(database)
    table_empty = is_table_empty(conn, 'currency_rates')
    if table_empty or check_data_in_db(conn):
        conversion_rates, next_updated = await fetch_data_from_api('https://api.exchangerate-api.com/v6/latest/USD')
        if conversion_rates and next_updated:
            insert_data_into_db(conn, conversion_rates, next_updated)
            print("Receive data from api")
        if conversion_rates[target] is None:
            return {"rate": "Курс не найден", "time": None}
        date = get_current_utc_time()
        formatted_date = date.strftime("%d-%m-%Y")
        return {"rate": conversion_rates[target], "time": formatted_date}
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT rate FROM currency_rates WHERE currency = ?", (target,))
        row = cursor.fetchone()
        if row:
            rate = row[0]
            date = get_current_utc_time()
            formatted_date = date.strftime("%d-%m-%Y")
            result = {"rate": rate, "time": formatted_date}
        else:
            result = {"rate": "Курс не найден", "time": None}
        conn.close()
        print("Receive data from cash")
    return result

async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = update.effective_user.id
    log_visit(user_id)
    target = update.message.text.upper()
    result = await get_rate(target)
    if result['rate'] != "Курс не найден":
        text = (f"На {result['time']} 1 USD = {result['rate']} {target}")
    else:
        text = result['rate']
    await update.message.reply_text(text)

def log_visit(user_id):
    conn = sqlite3.connect('currency_rates_api.db')
    c = conn.cursor()
    c.execute("INSERT INTO visits (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = update.effective_user.id
    log_visit(user_id)
    keyboard = [[InlineKeyboardButton("Узнать курс", callback_data='rate')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Добро пожаловать в бот. Нажмите кнопку «Узнать курс»,чтобы начать.",
        reply_markup=reply_markup
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Введите код валюты (например, «RUB» - Российский рубль, «EUR» - Евро, «CNY» - Юань, «AED» - Дирхам (ОАЭ), «AMD» - Армянский драм, «GEL» - Грузинский лари, «KZT» - Казахстанский тенге, «RSD» - Сербский динар и другие.)")

async def get_visits_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = sqlite3.connect('currency_rates_api.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_id FROM visits")
    total_visits = c.fetchall()
    conn.close()
    text = (f"{total_visits}")
    await update.message.reply_text(text)

def main() -> None:
    database = 'currency_rates_api.db'
    conn = sqlite3.connect(database)
    create_table(conn)
    config = configparser.ConfigParser()
    config.read('config.ini')
    TOKEN = config['DEFAULT']['TOKEN']
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, rate))

    application.run_polling()

if __name__ == '__main__':
    main()


