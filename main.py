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
DATABASE_URL = os.getenv('DATABASE_URL') # Neon Connection String እዚህ ይገባል
app = Flask('')
translator = Translator()

# --- Database Setup (Neon PostgreSQL) ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # ተጠቃሚዎችን እና ግሩፖችን ለመመዝገብ
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

init_db()

# የዜና ምንጮች
NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=Ethiopia&hl=am&gl=ET&ceid=ET:am",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC6f_uV6mO_nL_8_IubZkF7w",
    "https://www.fanabc.com/feed/",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://news.yahoo.com/rss/"
]

sent_news = set()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Helpers ---

async def translate_to_amharic(text):
    """እንግሊዝኛውን ወደ አማርኛ ሙሉ በሙሉ የሚተረጉም"""
    try:
        translated = await asyncio.to_thread(translator.translate, text, dest='am')
        return translated.text
    except:
        return text

def register_entity(entity_id, entity_type, username=None):
    """ሰዎችንና ግሩፖችን በቋሚነት የሚመዘግብ"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO entities (id, type, username) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
        (entity_id, entity_type, username)
    )
    conn.commit()
    cur.close()
    conn.close()

async def fetch_news_loop():
    """በየ 10 ሰከንዱ አዳዲስ ዜናዎችን የሚፈትሽ"""
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

# --- Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    msg_text = callback.message.text
    news_link = msg_text.split("🔗 ሊንክ: ")[1].split("\n")[0].strip()
    news_title = msg_text.split("📝 ርዕስ: ")[1].split("\n")[0]
    
    # 1. Scraping: ሙሉውን የዜና ጽሁፍ መሳብ
    full_text_en = ""
    try:
        res = requests.get(news_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        full_text_en = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 60])
    except:
        full_text_en = "ዝርዝር መረጃ ማግኘት አልተቻለም።"

    # 2. Translation: ሙሉውን ጽሁፍ ወደ አማርኛ መተርጎም
    am_title = await translate_to_amharic(news_title)
    am_body = await translate_to_amharic(full_text_en[:3500]) 

    # 3. Message: በአማርኛ በዝርዝር የተቀናጀ መልእክት
    broadcast_msg = (
        f"🔔 **ሰበር ዜና / BREAKING NEWS**\n\n"
        f"🇪🇹 **ርዕስ፦ {am_title}**\n\n"
        f"📝 **ዝርዝር ዘገባ (Detailed Summary)፦**\n{am_body}\n\n"
        f"🔗 **ሊንክ (Link):** {news_link}"
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
            # ለሰዎችና ለግሩፖች ይላካል
            await bot.send_message(target[0], broadcast_msg, disable_web_page_preview=False)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await callback.message.edit_text(f"✅ ለ {count} አድራሻዎች (ሰዎችና ግሩፖች) ተሰራጭቷል!")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    await message.answer("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\nዜናዎችን በአማርኛ በዝርዝር እዚህ ያገኛሉ።")

@dp.message(Command("stat"))
async def cmd_stat(message: types.Message):
    """የተመዘገቡ ሰዎችንና ግሩፖችን ብዛት ለአድሚን ያሳያል"""
    if message.from_user.id == ADMIN_ID:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT type, COUNT(*) FROM entities GROUP BY type")
        stats = cur.fetchall()
        cur.close()
        conn.close()
        report = "📊 **የቦቱ ስታቲስቲክስ፦**\n"
        for s in stats:
            report += f"🔹 {s[0].capitalize()}: {s[1]}\n"
        await message.answer(report)

@dp.message()
async def auto_reg(message: types.Message):
    """ማንኛውም መልእክት ሲላክ አዲስ ከሆነ ይመዘግባል"""
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)

# --- Server ---
@app.route('/')
def home(): return "Truthfulness Neon Bot is Live!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
