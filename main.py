import logging, os, asyncio, requests, feedparser, sqlite3
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Setup ---
API_TOKEN = os.getenv('BOT_TOKEN')
# ADMIN_ID-ን ወደ ቁጥር መቀየር (ካልተሳካ ስህተት እንዳይፈጥር try/except ተጠቅሜያለሁ)
try:
    ADMIN_ID = int(os.getenv('ADMIN_ID'))
except:
    ADMIN_ID = 0
    logging.error("ADMIN_ID አልተገኘም ወይም ቁጥር አይደለም!")

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
        if ADMIN_ID == 0:
            await asyncio.sleep(60)
            continue
            
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    entry = feed.entries[0]
                    if entry.link not in sent_news:
                        builder = InlineKeyboardBuilder()
                        # Callback Data-ውን አሳጥረነዋል (ስህተት እንዳይፈጠር)
                        builder.row(
                            types.InlineKeyboardButton(text="✅ አጽድቅ (Approve)", callback_data="ok_send"),
                            types.InlineKeyboardButton(text="❌ ይቅር (Ignore)", callback_data="no_skip")
                        )
                        
                        admin_msg = (
                            f"📩 **አዲስ ዜና ለፍቃድ ቀርቧል!**\n\n"
                            f"📝 {entry.title}\n"
                            f"🔗 {entry.link}\n\n"
                            f"ይህ ዜና ለሁሉም ይላክ?"
                        )
                        
                        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=builder.as_markup())
                        sent_news.add(entry.link)
            except Exception as e:
                logging.error(f"Error: {e}")
        await asyncio.sleep(600)

# --- Button Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    # ከሜሴጁ ላይ ዜናውን መለየት
    news_content = callback.message.text.replace("📩 አዲስ ዜና ለፍቃድ ቀርቧል!", "").replace("ይህ ዜና ለሁሉም ይላክ?", "").strip()
    
    broadcast_msg = (
        f"🔔 **ሰበር ዜና / BREAKING NEWS**\n\n"
        f"{news_content}\n\n"
        f"አዲስ መረጃ ወጥቷል።\nNew information is out."
    )
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    
    count = 0
    for user in users:
        try:
            await bot.send_message(user[0], broadcast_msg)
            count += 1
        except: pass
    
    await callback.message.edit_text(f"✅ ዜናው ለ {count} ሰዎች ተሰራጭቷል!")
    await callback.answer("ተልኳል!")

@dp.callback_query(F.data == "no_skip")
async def ignore_news(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ ዜናው እንዲቀር ተደርጓል።")
    await callback.answer()

# --- Basic Handlers ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    register_user(message.from_user.id)
    await message.answer("እንኳን በሰላም መጡ! አዳዲስ ዜናዎችን እዚህ ያገኛሉ።")

@dp.message()
async def handle_msg(message: types.Message):
    register_user(message.from_user.id)
    # የፍለጋ ተግባር እዚህ ይቀጥላል...
    pass

# --- Server ---
@app.route('/')
def home(): return "Approval System Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_for_approval())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
