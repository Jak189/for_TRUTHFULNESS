import logging, os, asyncio, requests, feedparser, psycopg2
from bs4 import BeautifulSoup
from googletrans import Translator
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Setup ---
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
DATABASE_URL = os.getenv('DATABASE_URL')
app = Flask('')
translator = Translator()

# --- Database Setup (Neon PostgreSQL) ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # የተጠቃሚዎች ሰንጠረዥ
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE, 
                type TEXT, 
                username TEXT
            )
        """)
        # የተላኩ ዜናዎች ሰንጠረዥ (መደጋገምን ለመከላከል)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_news (
                id SERIAL PRIMARY KEY,
                link TEXT UNIQUE
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"DB Init Error: {e}")

init_db()

# --- የሳይበር ደህንነት እና የሃኪንግ ዜና ምንጮች ---
NEWS_FEEDS = [
    "https://feeds.feedburner.com/TheHackersNews",
    "https://www.bleepingcomputer.com/feed/",
    "https://threatpost.com/feed/",
    "https://www.darkreading.com/rss.xml",
    "https://cyberscoop.com/feed/"
]

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Helpers ---

async def translate_text(text, target='am'):
    try:
        translated = await asyncio.to_thread(translator.translate, text, dest=target)
        return translated.text
    except Exception as e:
        logging.error(f"Translation Error: {e}")
        return text

def register_entity(user_id, e_type, username=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO entities (user_id, type, username) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET username = %s",
            (user_id, e_type, username, username)
        )
        conn.commit()
        cur.close()
        conn.close()
    except: pass

def is_news_sent(link):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM sent_news WHERE link = %s", (link,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result is not None
    except:
        return False

def mark_news_as_sent(link):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO sent_news (link) VALUES (%s) ON CONFLICT DO NOTHING", (link,))
        conn.commit()
        cur.close()
        conn.close()
    except: pass

async def fetch_news_loop():
    while True:
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:2]:
                    if not is_news_sent(entry.link):
                        builder = InlineKeyboardBuilder()
                        builder.row(
                            types.InlineKeyboardButton(text="✅ አጽድቅ (Approve)", callback_data="ok_send"),
                            types.InlineKeyboardButton(text="❌ ይቅር (Ignore)", callback_data="no_skip")
                        )
                        admin_msg = f"🛡 **አዲስ የሳይበር ዜና ለፍቃድ ቀርቧል!**\n\n📝 ርዕስ: {entry.title}\n🔗 ሊንክ: {entry.link}"
                        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=builder.as_markup())
                        mark_news_as_sent(entry.link)
            except Exception as e:
                logging.error(f"Fetch News Error: {e}")
            await asyncio.sleep(10)
        await asyncio.sleep(300) # በየ 5 ደቂቃው አዳዲስ ዜናዎችን ይፈትሻል

# --- Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    msg_text = callback.message.text
    try:
        news_link = msg_text.split("🔗 ሊንክ: ")[1].split("\n")[0].strip()
        news_title = msg_text.split("📝 ርዕስ: ")[1].split("\n")[0]
        
        # Web Scraping
        res = requests.get(news_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        full_text_en = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 60])

        am_title = await translate_text(news_title, 'am')
        am_body = await translate_text(full_text_en[:2000], 'am')

        broadcast_msg = f"💻 **HACKING & CYBERSECURITY NEWS**\n\n🇪🇹 **ርዕስ፦ {am_title}**\n\n📝 **ዝርዝር ዘገባ፦**\n{am_body}\n\n🔗 [ምንጭ]({news_link})"
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM entities")
        targets = cur.fetchall()
        cur.close()
        conn.close()
        
        count = 0
        for target in targets:
            try:
                await bot.send_message(target[0], broadcast_msg, parse_mode="Markdown")
                count += 1
                await asyncio.sleep(0.05) # Rate limit መከላከያ
            except: pass
        await callback.message.edit_text(f"✅ የሳይበር ዜናው ለ {count} አድራሻዎች ተሰራጭቷል!")
    except Exception as e:
        await callback.answer(f"Error: {e}", show_alert=True)

@dp.callback_query(F.data == "no_skip")
async def ignore_news(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ ዜናው ተዘልሏል።")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    await message.answer("እንኳን ወደ የሳይበር ደህንነት እና የሃኪንግ ዜናዎች ቦት በሰላም መጡ! 🛡")

# --- 📊 ስታቲስቲክስ ---
@dp.message(Command("stat"))
async def cmd_stat(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username FROM entities ORDER BY id ASC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        report = "📊 **የተመዘገቡ አድራሻዎች፦**\n\n"
        for r in rows:
            report += f"{r[0]}. @{r[1] if r[1] else 'ያልታወቀ'}\n"
        await message.answer(report)

# --- 💬 የAI ቻት ---
@dp.message()
async def chat_and_reg(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    
    if not message.text.startswith('/') and message.from_user.id != ADMIN_ID:
        am_msg = await translate_text(message.text, 'am')
        en_msg = await translate_text(message.text, 'en')
        
        response = f"🇪🇹 {am_msg}\n\n🇬🇧 {en_msg}"
        await message.reply(response)

# --- Server ---
@app.route('/')
def home(): return "Cyber News Bot is Online!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
