import logging, os, asyncio, requests, feedparser, sqlite3
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
app = Flask('')
translator = Translator()

# Database Setup
db = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY, type TEXT, username TEXT)")
db.commit()

# የዜና ምንጮች (YouTube, Google, Yahoo, International)
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

async def translate_text(text):
    """ጽሁፍን ወደ አማርኛ የሚተረጉም"""
    try:
        translated = await asyncio.to_thread(translator.translate, text, dest='am')
        return translated.text
    except:
        return text

def register_entity(entity_id, entity_type, username=None):
    cursor.execute("INSERT OR IGNORE INTO entities (id, type, username) VALUES (?, ?, ?)", (entity_id, entity_type, username))
    db.commit()

async def fetch_news_for_approval():
    """በየ 10 ሰከንዱ አዳዲስ ዜናዎችን ለአድሚን ያቀርባል"""
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
    
    # 1. Scraping: ሁሉንም የዜናውን ጽሁፍ መሳብ
    full_text_en = ""
    try:
        res = requests.get(news_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # ሁሉንም አንቀጾች (p tags) ሰብስቦ ማቀናጀት
        paragraphs = soup.find_all('p')
        full_text_en = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
    except:
        full_text_en = "ዝርዝር መረጃ ማግኘት አልተቻለም።"

    # 2. Translation: ሙሉውን ጽሁፍ መተርጎም
    amharic_title = await translate_text(news_title)
    # ጽሁፉ በጣም ረጅም ከሆነ ለትርጉም እንዲመች ቆርጦ መላክ
    amharic_body = await translate_text(full_text_en[:3000]) 

    # 3. Final Message: በአማርኛ በዝርዝር የተጻፈ መልእክት
    broadcast_msg = (
        f"🔔 **ሰበር ዜና / BREAKING NEWS**\n\n"
        f"🇪🇹 **{amharic_title}**\n\n"
        f"📝 **ዝርዝር ዘገባ፦**\n{amharic_body}\n\n"
        f"🔗 **ሙሉውን መረጃ በእንግሊዝኛ ለማንበብ፦** {news_link}"
    )
    
    cursor.execute("SELECT id FROM entities")
    targets = cursor.fetchall()
    
    count = 0
    for target in targets:
        try:
            # ለሰዎችና ለግሩፖች ይላካል
            await bot.send_message(target[0], broadcast_msg, disable_web_page_preview=False)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await callback.message.edit_text(f"✅ ዜናው በአማርኛ ተተርጉሞ ለ {count} አድራሻዎች ተሰራጭቷል!")

# --- Common Handlers ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    entity_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, entity_type, message.from_user.username)
    await message.answer("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\nእዚህ ዜናዎችን በአማርኛ በዝርዝር ያገኛሉ።")

@dp.message(Command("stat"))
async def cmd_stat(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        cursor.execute("SELECT type, COUNT(*) FROM entities GROUP BY type")
        stats = cursor.fetchall()
        report = "📊 **የቦቱ ስታቲስቲክስ፦**\n"
        for s in stats:
            report += f"🔹 {s[0].capitalize()}: {s[1]}\n"
        await message.answer(report)

@dp.message()
async def record_everything(message: types.Message):
    # ማንኛውም መልእክት ሲላክ ሰዎችንና ግሩፖችን ይመዘግባል
    entity_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, entity_type, message.from_user.username)

# --- Server ---
@app.route('/')
def home(): return "Truthfulness Full Translator Bot is Online!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_for_approval())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
