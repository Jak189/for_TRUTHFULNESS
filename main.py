import logging, os, asyncio, requests, feedparser, sqlite3
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Setup ---
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
app = Flask('')

# Database Setup (User & Group Management)
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, type TEXT)")
db.commit()

# የዜና ምንጮች (ሀገር ውስጥና ውጭ)
NEWS_FEEDS = [
    "https://www.fanabc.com/feed/",
    "https://www.ebc.et/feed/",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.reutersagency.com/feed/",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC6f_uV6mO_nL_8_IubZkF7w" # Abel Birhanu
]

sent_news = set()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Functions ---

def register_target(m: types.Message):
    """ሰዎችንና ግሩፖችን መመዝገቢያ"""
    t_id = m.chat.id
    t_type = m.chat.type
    t_username = m.chat.username or m.chat.title or "Unknown"
    cursor.execute("INSERT OR IGNORE INTO users (id, username, type) VALUES (?, ?, ?)", (t_id, t_username, t_type))
    db.commit()

async def fetch_news_loop():
    """በየ 10 ሰከንዱ አዳዲስ ዜናዎችን መፈለጊያ (Point 2 & 3)"""
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
                        admin_msg = f"📩 **አዲስ ዜና ለፍቃድ!**\n\n📝 ርዕስ: {entry.title}\n🔗 ሊንክ: {entry.link}"
                        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=builder.as_markup())
                        sent_news.add(entry.link)
            except: pass
        await asyncio.sleep(10) # 10 ሰከንድ (Point 2)

# --- Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    """ዜናውን አቀናጅቶ ለሁሉም ማሰራጫ (Point 1, 4 & 6)"""
    msg_text = callback.message.text
    news_link = msg_text.split("🔗 ሊንክ: ")[1].strip()
    news_title = msg_text.split("📝 ርዕስ: ")[1].split("\n")[0]

    # 1. Scraping & Summary (Point 1 & 6)
    detail_am = ""
    try:
        res = requests.get(news_link, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        # የመጀመሪያዎቹን 3 አንቀጾች መውሰድ
        detail_am = "\n\n".join([p.get_text() for p in paragraphs[:3] if len(p.get_text()) > 40])
    except:
        detail_am = "ዝርዝር መረጃውን ከሊንኩ ይመልከቱ።"

    broadcast_msg = (
        f"🔔 **ሰበር ዜና / BREAKING NEWS**\n\n"
        f"📌 **ርዕስ፦** {news_title}\n\n"
        f"📝 **ዝርዝር ማብራሪያ (Detailed Summary)፦**\n{detail_am[:1000]}\n\n"
        f"🔗 **ሙሉውን ለማንበብ፦** {news_link}"
    )

    # 2. ለሁሉም ማድረስ (Point 4)
    cursor.execute("SELECT id FROM users")
    targets = cursor.fetchall()
    count = 0
    for target in targets:
        try:
            # ቪዲዮ ካለ በሊንኩ አማካኝነት ቴሌግራም ራሱ ያመጣዋል (disable_web_page_preview=False)
            await bot.send_message(target[0], broadcast_msg, disable_web_page_preview=False)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await callback.message.edit_text(f"✅ ለ {count} ተቀባዮች (ሰዎችና ግሩፖች) ተልኳል!")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    register_target(message) # መመዝገቢያ (Point 5)
    await message.answer("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️")

@dp.message(Command("stat"))
async def cmd_stat(message: types.Message):
    """የተመዘገቡ አባላትን መረጃ ማሳያ (Point 5)"""
    if message.from_user.id != ADMIN_ID: return
    cursor.execute("SELECT username, type FROM users")
    rows = cursor.fetchall()
    report = "📊 **የቦቱ አባላት መረጃ፦**\n\n"
    for r in rows:
        report += f"🔹 {r[0]} ({r[1]})\n"
    await message.answer(report)

@dp.message()
async def auto_register(message: types.Message):
    """ማንኛውም ሰው ሜሴጅ ሲልክ በራሱ ይመዘግባል (Point 5)"""
    register_target(message)

# --- Server ---
@app.route('/')
def home(): return "Pro News System Online!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
