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

# --- የዜና ምንጮች (የጠየቅካቸው በሙሉ ተካተዋል) ---
NEWS_FEEDS = [
    # የሀገር ውስጥ
    "https://www.ethiopianreporter.com/feed/",
    "https://waltainfo.com/feed/",
    "https://www.fanabc.com/feed/",
    "https://addisstandard.com/feed/",
    "https://zehabesha.com/feed/",
    "https://www.ena.et/am/feed/",
    # አለም አቀፍ
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://news.yahoo.com/rss/",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "http://feeds.foxnews.com/foxnews/latest",
    "https://www.reutersagency.com/feed/",
    # ልዩ ፍለጋዎች (ለ Tikvah እና Abel Berhanu)
    "https://news.google.com/rss/search?q=Tikvah+Ethiopia+OR+Abel+Berhanu&hl=am&gl=ET&ceid=ET:am",
    "https://news.google.com/rss/search?q=AP+News+OR+Reuters+OR+NYTimes&hl=en&gl=US&ceid=US:en"
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
                for entry in feed.entries[:2]:
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
        await asyncio.sleep(20)

# --- Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    msg_text = callback.message.text
    try:
        news_link = msg_text.split("🔗 ሊንክ: ")[1].split("\n")[0].strip()
        news_title = msg_text.split("📝 ርዕስ: ")[1].split("\n")[0]
        
        # Scraping
        res = requests.get(news_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        full_text_en = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 60])

        am_title = await translate_text(news_title, 'am')
        am_body = await translate_text(full_text_en[:3000], 'am')

        broadcast_msg = f"📢 **BREAKING NEWS**\n\n🇪🇹 **ርዕስ፦ {am_title}**\n\n📝 **ዝርዝር ዘገባ፦**\n{am_body}\n\n🔗 {news_link}"
        
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
            except: pass
        await callback.message.edit_text(f"✅ ለ {count} አድራሻዎች ተሰራጭቷል!")
    except Exception as e:
        await callback.answer(f"Error: {e}", show_alert=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    await message.answer("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️")

# --- 📊 ስታቲስቲክስ እና ዝርዝር መረጃ ---
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
        report += "\n💡 ዝርዝር ዳታ ለማየት የቁጥሩን ቁጥር Reply ያድርጉ።"
        await message.answer(report)

@dp.message(F.reply_to_message & (F.from_user.id == ADMIN_ID))
async def get_user_detail(message: types.Message):
    if message.text.isdigit():
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, type, username FROM entities WHERE id = %s", (int(message.text),))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            await message.answer(f"👤 **ዝርዝር መረጃ**\n\n🆔 Telegram ID: `{user[0]}`\n📂 አይነት: {user[1]}\n🏷 ስም: @{user[2]}")

# --- 💬 የAI ቻት (በሁለት ቋንቋ ምላሽ የሚሰጥ) ---
@dp.message()
async def chat_and_reg(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    
    if not message.text.startswith('/') and message.from_user.id != ADMIN_ID:
        # ጥያቄውን ወደ እንግሊዝኛ ቀይሮ መልስ መፈለግ (ለአሁኑ ቀጥታ ትርጉም ነው የምሰጠው)
        am_msg = await translate_text(message.text, 'am')
        en_msg = await translate_text(message.text, 'en')
        
        response = f"🇪🇹 {am_msg}\n\n🇬🇧 {en_msg}"
        await message.reply(response)

# --- Server ---
@app.route('/')
def home(): return "Bot is Online!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
