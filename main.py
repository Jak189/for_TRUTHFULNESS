import logging, os, asyncio, requests, feedparser, sqlite3
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

# የዜና ምንጮች
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
    while True:
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    entry = feed.entries[0]
                    if entry.link not in sent_news:
                        # ምስል ካለ ለመሳብ (YouTube thumbnails or RSS images)
                        image_url = entry.get('media_thumbnail', [{'url': None}])[0]['url']
                        if not image_url and 'media_content' in entry:
                            image_url = entry['media_content'][0]['url']
                        
                        builder = InlineKeyboardBuilder()
                        builder.row(
                            types.InlineKeyboardButton(text="✅ አጽድቅ (Approve)", callback_data="ok_send"),
                            types.InlineKeyboardButton(text="❌ ይቅር (Ignore)", callback_data="no_skip")
                        )
                        
                        admin_msg = (
                            f"📩 **አዲስ ዜና ለፍቃድ ቀርቧል!**\n\n"
                            f"📝 {entry.title}\n"
                            f"🔗 {entry.link}\n"
                            f"🖼 Image/Video: {'አለ' if image_url else 'የለም'}"
                        )
                        
                        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=builder.as_markup())
                        sent_news.add(entry.link)
            except Exception as e:
                logging.error(f"Error: {e}")
        await asyncio.sleep(600)

# --- Button Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    # መረጃውን ከሜሴጁ ላይ መሳብ
    original_text = callback.message.text
    news_title = original_text.split("📝 ")[1].split("\n")[0]
    news_link = original_text.split("🔗 ")[1].split("\n")[0]
    
    # ሰፊ ማብራሪያና የሁለት ቋንቋ ጽሁፍ
    broadcast_msg = (
        f"🔔 **ሰበር ዜና / BREAKING NEWS**\n\n"
        f"🇪🇹 **ርዕስ፦** {news_title}\n"
        f"🇬🇧 **Title:** {news_title}\n\n"
        f"🔍 **ማብራሪያ፦**\n"
        f"ከYouTube እና ከታማኝ የዜና ምንጮች የተገኘ አዲስ መረጃ ነው። ዝርዝሩን ከታች ባለው ሊንክ መከታተል ትችላላችሁ።\n"
        f"New update from verified sources. Details are available on the link below.\n\n"
        f"🔗 {news_link}"
    )
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    
    count = 0
    for user in users:
        try:
            # ቴሌግራም ሊንኩን ወደ ምስል/ቪዲዮ እንዲቀይረው send_message ላይ link preview እናበራለን
            await bot.send_message(user[0], broadcast_msg, disable_web_page_preview=False)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await callback.message.edit_text(f"✅ ዜናው ከነማብራሪያው ለ {count} ሰዎች ተሰራጭቷል!")
    await callback.answer()

@dp.callback_query(F.data == "no_skip")
async def ignore_news(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ ዜናው ውድቅ ተደርጓል።")
    await callback.answer()

# --- Basic Handlers ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    register_user(message.from_user.id)
    # ቪዲዮ በ Caption መልክ ለመላክ
    welcome_msg = (
        "እንኳን በሰላም መጡ! ⚖️\n"
        "እዚህ እውነተኛ ዜናዎችን ከነቪዲዮ ማብራሪያቸው ያገኛሉ።"
    )
    await message.answer(welcome_msg)

@dp.message()
async def handle_msg(message: types.Message):
    register_user(message.from_user.id)
    # የፍለጋ Logic እዚህ (DuckDuckGo Search)
    pass

# --- Server ---
@app.route('/')
def home(): return "Pro News System Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_for_approval())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
