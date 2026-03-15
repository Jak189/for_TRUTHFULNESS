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
    # Render ላይ የተቀመጠውን DATABASE_URL በቀጥታ ይጠቀማል
    # sslmode=require መጨመሩን ያረጋግጣል
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE, 
                type TEXT, 
                username TEXT
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"DB Init Error: {e}")

init_db()

# --- የዜና ምንጮች ---
NEWS_FEEDS = [
    "https://www.ethiopianreporter.com/feed/",
    "https://waltainfo.com/feed/",
    "https://www.fanabc.com/feed/",
    "https://addisstandard.com/feed/",
    "https://zehabesha.com/feed/",
    "https://www.ena.et/am/feed/",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://news.yahoo.com/rss/",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "http://feeds.foxnews.com/foxnews/latest",
    "https://www.reutersagency.com/feed/",
    "https://news.google.com/rss/search?q=Tikvah+Ethiopia+OR+Abel+Berhanu&hl=am&gl=ET&ceid=ET:am",
    "https://news.google.com/rss/search?q=Ethiopia+News+Agency+OR+Addis+Standard&hl=am&gl=ET&ceid=ET:am"
]

sent_news = set()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Helpers ---

async def translate_text(text, target='am'):
    try:
        translated = await asyncio.to_thread(translator.translate, text, dest=target)
        return translated.text
    except:
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

async def fetch_news_loop():
    while True:
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    if entry.link not in sent_news:
                        builder = InlineKeyboardBuilder()
                        builder.row(
                            types.InlineKeyboardButton(text="✅ አጽድቅ (Approve)", callback_data="ok_send"),
                            types.InlineKeyboardButton(text="❌ ይቅር (Ignore)", callback_data="no_skip")
                        )
                        admin_msg = f"📩 **አዲስ ዜና ለፍቃድ ቀርቧል!**\n\n📝 ርዕስ: {entry.title}\n🔗 ሊንክ: {entry.link}"
                        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=builder.as_markup())
                        sent_news.add(entry.link)
            except: pass
        await asyncio.sleep(15)

# --- Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    msg_text = callback.message.text
    try:
        news_link = msg_text.split("🔗 ሊንክ: ")[1].split("\n")[0].strip()
        news_title = msg_text.split("📝 ርዕስ: ")[1].split("\n")[0]
        
        # Scraping
        full_text_en = ""
        try:
            res = requests.get(news_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            paragraphs = soup.find_all('p')
            full_text_en = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 60])
        except:
            full_text_en = "መረጃውን ማግኘት አልተቻለም።"

        am_title = await translate_text(news_title, 'am')
        am_body = await translate_text(full_text_en[:3500], 'am')

        broadcast_msg = (
            f"📢 **BREAKING NEWS**\n\n"
            f"🇪🇹 **ርዕስ፦ {am_title}**\n\n"
            f"📝 **ዝርዝር ዘገባ፦**\n{am_body}\n\n"
            f"🔗 **ሊንክ (Link):** {news_link}"
        )
        
        # ዳታቤዝ ግንኙነት ፍተሻ
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM entities")
        targets = cur.fetchall()
        cur.close()
        conn.close()
        
        count = 0
        for target in targets:
            try:
                await bot.send_message(target[0], broadcast_msg)
                count += 1
                await asyncio.sleep(0.05)
            except: pass
        await callback.message.edit_text(f"✅ ለ {count} አድራሻዎች ተሰራጭቷል!")
    except Exception as e:
        # ስህተት ካለ ለተጠቃሚው እንዲታይ
        await callback.answer(f"Error: {str(e)}", show_alert=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    await message.answer("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️")

@dp.message(Command("stat"))
async def cmd_stat(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id, username FROM entities ORDER BY id ASC")
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            report = "📊 **ተጠቃሚዎች ዝርዝር፦**\n"
            for r in rows:
                report += f"{r[0]}. @{r[1] if r[1] else 'None'}\n"
            report += "\n💡 ዝርዝር ዳታ ለማየት ቁጥሩን Reply ያድርጉ።"
            await message.answer(report)
        except Exception as e:
            await message.answer(f"Database Error: {e}")

@dp.message(F.reply_to_message & (F.from_user.id == ADMIN_ID))
async def get_user_detail(message: types.Message):
    if message.text.isdigit():
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT user_id, type, username FROM entities WHERE id = %s", (int(message.text),))
            user = cur.fetchone()
            cur.close()
            conn.close()
            if user:
                await message.answer(f"👤 **መረጃ**\n🆔 ID: `{user[0]}`\n📂 Type: {user[1]}\n🏷 User: @{user[2]}")
        except: pass

@dp.message()
async def auto_reg_and_chat(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    
    if not message.text.startswith('/') and message.from_user.id != ADMIN_ID:
        am_msg = await translate_text(message.text, 'am')
        en_msg = await translate_text(message.text, 'en')
        await message.reply(f"🇪🇹 {am_msg}\n\n🇬🇧 {en_msg}")

# --- Server ---
@app.route('/')
def home(): return "Multi-Source News Bot Live!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
