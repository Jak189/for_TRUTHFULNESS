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
# Render ላይ ያስገባኸው የ Neon ሊንክ እዚህ ይነበባል
DATABASE_URL = os.getenv('DATABASE_URL')
app = Flask('')
translator = Translator()

# --- Database Connection (PostgreSQL/Neon) ---
def get_db_connection():
    # SSL mode የግድ ያስፈልጋል ለ Neon
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # ተጠቃሚዎችን እና ግሩፖችን የሚመዘግብ ሰንጠረዥ
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id BIGINT PRIMARY KEY, 
                type TEXT, 
                username TEXT
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        logging.info("Database initialized!")
    except Exception as e:
        logging.error(f"DB Error: {e}")

init_db()

# የዜና ምንጮች
NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=Ethiopia&hl=am&gl=ET&ceid=ET:am",
    "https://www.fanabc.com/feed/",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml"
]

sent_news = set()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Functions ---

async def translate_to_amharic(text):
    """እንግሊዝኛውን ወደ አማርኛ የሚቀይር"""
    try:
        translated = await asyncio.to_thread(translator.translate, text, dest='am')
        return translated.text
    except:
        return text

def register_entity(entity_id, entity_type, username=None):
    """አዳዲስ ተጠቃሚዎችን በቋሚነት ዳታቤዝ ላይ ይጨምራል"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO entities (id, type, username) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (entity_id, entity_type, username)
        )
        conn.commit()
        cur.close()
        conn.close()
    except: pass

async def fetch_news_loop():
    """አዳዲስ ዜናዎችን በየ 10 ሰከንዱ የሚፈትሽ"""
    while True:
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    entry = feed.entries[0]
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
        await asyncio.sleep(10)

# --- Button Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    msg_text = callback.message.text
    news_link = msg_text.split("🔗 ሊንክ: ")[1].split("\n")[0].strip()
    news_title = msg_text.split("📝 ርዕስ: ")[1].split("\n")[0]
    
    # 1. Scraping: የዜናውን ሙሉ ጽሁፍ ከሊንኩ መሳብ
    full_text_en = ""
    try:
        res = requests.get(news_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        full_text_en = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
    except:
        full_text_en = "ዝርዝር መረጃ ማግኘት አልተቻለም።"

    # 2. Translation: ርዕሱንና ሙሉ ጽሁፉን መተርጎም
    am_title = await translate_to_amharic(news_title)
    am_body = await translate_to_amharic(full_text_en[:3500]) # ለትርጉም እንዳይከብድ ተቆርጦ

    # 3. Final Broadcast: ለሁሉም ተጠቃሚዎች ይላካል
    broadcast_msg = (
        f"🔔 **ሰበር ዜና / BREAKING NEWS**\n\n"
        f"🇪🇹 **{am_title}**\n\n"
        f"📝 **ዝርዝር ዘገባ፦**\n{am_body}\n\n"
        f"🔗 **Link:** {news_link}"
    )
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM entities")
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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    await message.answer("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️")

@dp.message()
async def auto_register(message: types.Message):
    # ግሩፕ ውስጥም ሆነ በግል ቦቱን ሲያናግሩ ይመዘግባል
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)

# --- Server (Render Keep-Alive) ---
@app.route('/')
def home(): return "Bot is Online with Neon DB!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
