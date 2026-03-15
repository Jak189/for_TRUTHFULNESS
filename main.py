import logging, os, asyncio, requests, feedparser, sqlite3
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Setup ---
API_TOKEN = os.getenv('BOT_TOKEN')
# አስተውል፡ ADMIN_ID ቁጥር መሆን አለበት (ለምሳሌ፡ 12345678)
ADMIN_ID = int(os.getenv('ADMIN_ID')) 
app = Flask('')

# Database Setup (ተጠቃሚዎችን በቋሚነት ለመመዝገብ)
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
db.commit()

# የዜና ምንጮች (YouTube, TV Channels, International)
NEWS_FEEDS = [
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC6f_uV6mO_nL_8_IubZkF7w", # Abel Birhanu
    "https://www.fanabc.com/feed/", # Fana BC
    "https://www.ebc.et/feed/", # EBC
    "https://feeds.bbci.co.uk/news/world/rss.xml", # BBC World
    "https://www.aljazeera.com/xml/rss/all.xml" # Al Jazeera
]

sent_news = set()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Functions ---

def register_user(user_id):
    """ማንኛውም ሰው ቦቱን ሲያወራው በዳታቤዝ ውስጥ ይመዘግባል"""
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    db.commit()

async def fetch_news_for_approval():
    """አዳዲስ ዜናዎችን ፈልጎ መጀመሪያ ለአድሚን (ለአንተ) ለፍቃድ የሚያቀርብ"""
    while True:
        logging.info("Checking news sources...")
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    entry = feed.entries[0]
                    if entry.link not in sent_news:
                        # የማጽደቂያ በተኖች (Buttons)
                        builder = InlineKeyboardBuilder()
                        builder.row(
                            types.InlineKeyboardButton(text="✅ አጽድቅ (Approve)", callback_data="send_all"),
                            types.InlineKeyboardButton(text="❌ ይቅር (Ignore)", callback_data="ignore")
                        )
                        
                        admin_msg = (
                            f"📩 **አዲስ ዜና ለፍቃድ ቀርቧል!**\n\n"
                            f"📝 **ርዕስ:** {entry.title}\n"
                            f"🔗 **ሊንክ:** {entry.link}\n\n"
                            f"ይህ ዜና ለሁሉም ተመዝጋቢዎች ይላክ?"
                        )
                        
                        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=builder.as_markup())
                        sent_news.add(entry.link)
            except Exception as e:
                logging.error(f"Error checking {url}: {e}")
        
        await asyncio.sleep(600) # በየ 10 ደቂቃው ይፈትሻል

# --- Callbacks (የበተን ትዕዛዞች) ---

@dp.callback_query(F.data == "send_all")
async def approve_news(callback: types.CallbackQuery):
    # ከሜሴጁ ላይ ርዕሱንና ሊንኩን መለየት
    original_text = callback.message.text
    # እዚህ ጋር ግርድፍ ትርጉም ወይም ማብራሪያ ማከል ይቻላል
    
    broadcast_msg = (
        f"🔔 **ሰበር ዜና / BREAKING NEWS**\n\n"
        f"📌 {original_text.split('📝 ርዕስ: ')[1].split('🔗 ሊንክ:')[0].strip()}\n\n"
        f"አዲስ መረጃ ወጥቷል፤ ዝርዝሩን ከታች ባለው ሊንክ ይመልከቱ።\n"
        f"New information is out; check the link below for details.\n\n"
        f"🔗 {original_text.split('🔗 ሊንክ: ')[1].split('ይህ ዜና')[0].strip()}"
    )
    
    # ለሁሉም ተጠቃሚዎች መላክ
    cursor.execute("SELECT user_id FROM users")
    all_users = cursor.fetchall()
    
    success = 0
    for user in all_users:
        try:
            await bot.send_message(user[0], broadcast_msg)
            success += 1
            await asyncio.sleep(0.05) # ፍጥነት ለመቀነስ
        except: pass
    
    await callback.message.edit_text(f"✅ ዜናው ለ {success} ተጠቃሚዎች ተሰራጭቷል!")
    await callback.answer()

@dp.callback_query(F.data == "ignore")
async def ignore_news(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ ዜናው ውድቅ ተደርጓል።")
    await callback.answer()

# --- Message Handlers ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    register_user(message.from_user.id)
    
    # ቪዲዮ በ caption ለመላክ (ቪዲዮው ቴሌግራም ላይ ካለ ሊንኩን ወይም File ID ይጠቀሙ)
    welcome_text = (
        "እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n"
        "Welcome to for_TRUTHFULNESS!\n\n"
        "እዚህ እውነተኛ እና የተጣሩ ዜናዎችን ያገኛሉ።\n"
        "You will get verified and real news here."
    )
    
    # ማሳሰቢያ፡ ቪዲዮ ለመላክ .mp4 ሊንክ ያስፈልጋል
    video_url = "https://www.sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4" 
    
    try:
        await message.answer_video(video=video_url, caption=welcome_text)
    except:
        await message.answer(welcome_text)

@dp.message()
async def handle_search(message: types.Message):
    register_user(message.from_user.id)
    # የፍለጋ ተግባር (እንደ ቀድሞው)
    query = message.text
    if not query: return
    
    status = await message.answer("🔍 መረጃውን እያጣራሁ ነው...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        search_url = f"https://www.google.com/search?q={query}+news"
        res = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        links = []
        for a in soup.find_all('a', href=True):
            if a['href'].startswith('/url?q='):
                link = a['href'].split('/url?q=')[1].split('&')[0]
                if "google.com" not in link: links.append(link)
            if len(links) == 3: break
        
        if links:
            await status.edit_text("✅ **የተገኘ መረጃ፦**\n\n" + "\n\n".join(links))
        else:
            await status.edit_text(f"❌ አልተገኘም፤ እዚህ ይሞክሩ፡ https://www.google.com/search?q={query}")
    except:
        await status.edit_text("⚠️ ችግር አጋጥሟል።")

# --- Server Keep-Alive ---
@app.route('/')
def home(): return "News Approval System is Live!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    # የዜና መከታተያውን ማስጀመር
    asyncio.create_task(fetch_news_for_approval())
    # ቦቱን ማስጀመር
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
