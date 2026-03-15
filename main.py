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

# Database Setup
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
db.commit()

# የዜና ምንጮች (YouTube, TV Channels, International)
NEWS_FEEDS = [
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC6f_uV6mO_nL_8_IubZkF7w", # Abel Birhanu
    "https://www.fanabc.com/feed/",
    "https://www.ebc.et/feed/",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml"
]

sent_news = set()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Functions ---

def register_user(user_id):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    db.commit()

async def fetch_news_for_approval():
    """አዳዲስ ዜናዎችን ፈልጎ ለአድሚን ለፍቃድ የሚያቀርብ"""
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
                        
                        admin_msg = (
                            f"📩 **አዲስ ዜና ለፍቃድ ቀርቧል!**\n\n"
                            f"📝 ርዕስ: {entry.title}\n"
                            f"🔗 ሊንክ: {entry.link}\n\n"
                            f"ይህ ዜና ተተንትኖ ለሁሉም ይላክ?"
                        )
                        
                        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=builder.as_markup())
                        sent_news.add(entry.link)
            except Exception as e:
                logging.error(f"News fetch error: {e}")
        await asyncio.sleep(600)

# --- Button Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    # መረጃውን ከሜሴጁ ላይ መሳብ
    original_text = callback.message.text
    news_title = original_text.split("📝 ርዕስ: ")[1].split("\n")[0]
    news_link = original_text.split("🔗 ሊንክ: ")[1].split("\n")[0].strip()
    
    # 1. ከዌብሳይቱ ላይ ዝርዝር መረጃውን ለመሳብ (Scraping)
    detailed_summary = ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        page = requests.get(news_link, headers=headers, timeout=10)
        soup = BeautifulSoup(page.text, 'html.parser')
        
        # ዋናውን ጽሁፍ (Paragraphs) መፈለግ
        paragraphs = soup.find_all('p')
        # የመጀመሪያዎቹን 3 አንቀጾች ለዝርዝር ማብራሪያ መውሰድ
        summary_text = "\n\n".join([p.get_text() for p in paragraphs[:3] if len(p.get_text()) > 20])
        detailed_summary = summary_text[:900] # ቴሌግራም ላይ እንዳይቆረጥ መቆጣጠር
    except:
        detailed_summary = "ዝርዝር መረጃውን ከታች ያለውን ሊንክ በመጫን መከታተል ትችላላችሁ።"

    # 2. ለተጠቃሚዎች የሚላከው መልእክት አቀራረብ
    broadcast_msg = (
        f"🔔 **ሰበር ዜና / BREAKING NEWS**\n\n"
        f"📌 **ርዕስ፦** {news_title}\n\n"
        f"📝 **ዝርዝር ማብራሪያ፦**\n{detailed_summary}\n\n"
        f"🔗 **ሙሉውን መረጃ ለማንበብ፦** {news_link}"
    )
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    
    count = 0
    for user in users:
        try:
            # ዜናውን ከነ ምስል ቅድመ-ዕይታው (Preview) መላክ
            await bot.send_message(user[0], broadcast_msg, disable_web_page_preview=False)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await callback.message.edit_text(f"✅ ዜናው በዝርዝር ተጽፎ ለ {count} ሰዎች ተሰራጭቷል!")
    await callback.answer()

@dp.callback_query(F.data == "no_skip")
async def ignore_news(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ ዜናው እንዲቀር ተደርጓል።")
    await callback.answer()

# --- Basic Handlers ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    register_user(message.from_user.id)
    welcome_msg = (
        "እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n\n"
        "እዚህ እውነተኛ ዜናዎችን ከነዝርዝር ማብራሪያቸው ያገኛሉ።"
    )
    await message.answer(welcome_msg)

# --- Server Keep-Alive ---
@app.route('/')
def home(): return "Professional News Scraper System is Online!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_for_approval())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
