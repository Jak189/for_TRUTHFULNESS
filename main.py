import logging, os, asyncio, requests, feedparser, sqlite3
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# --- Setup ---
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')
app = Flask('')

# Database Setup (ተጠቃሚዎችን በቋሚነት ለመመዝገብ)
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
db.commit()

# የዜና ምንጮች (የአቤል ብርሀኑ ዩቲዩብ፣ ፋና እና ዓለም አቀፍ)
# ማሳሰቢያ፡ የዩቲዩብ RSS የሚሠራው በChannel ID ነው
NEWS_FEEDS = [
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC6f_uV6mO_nL_8_IubZkF7w", # Abel Birhanu
    "https://www.fanabc.com/feed/", # Fana BC
    "https://www.aljazeera.com/xml/rss/all.xml", # Al Jazeera
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en" # Google News
]

sent_news = set()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Functions ---

def register_user(user_id):
    """ማንኛውም ሰው ቦቱን ሲያወራው በዳታቤዝ ውስጥ ይመዘግባል"""
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    db.commit()

async def fetch_latest_news():
    """አዳዲስ ዜናዎችን ፈልጎ ለሁሉም ተጠቃሚዎች የሚያሰራጭ"""
    while True:
        logging.info("Checking for new stories...")
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    entry = feed.entries[0] # አዲሱን አንድ ዜና ብቻ
                    if entry.link not in sent_news:
                        msg = f"🔔 **ሰበር ዜና!**\n\n📝 {entry.title}\n\n🔗 {entry.link}"
                        
                        # በዳታቤዝ ያሉትን ሁሉንም ተጠቃሚዎች መሳብ
                        cursor.execute("SELECT user_id FROM users")
                        all_users = cursor.fetchall()
                        
                        success_count = 0
                        for user in all_users:
                            try:
                                await bot.send_message(user[0], msg)
                                success_count += 1
                                await asyncio.sleep(0.05) # Spam እንዳይሆን ትንሽ እረፍት
                            except Exception:
                                pass # ቦቱን Block ያደረጉ ሰዎችን ያልፋል
                        
                        # ለአድሚኑ (ለአንተ) ሪፖርት መላክ
                        if ADMIN_ID:
                            report = f"📊 **የዜና ስርጭት ሪፖርት**\n\n✅ ዜናው ለ {success_count} ተጠቃሚዎች ተሰራጭቷል።\n🔗 {entry.link}"
                            await bot.send_message(ADMIN_ID, report)
                        
                        sent_news.add(entry.link)
            except Exception as e:
                logging.error(f"News error: {e}")
        
        await asyncio.sleep(600) # በየ 10 ደቂቃው ይፈትሻል

# --- Handlers ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    register_user(message.from_user.id)
    # የቪዲዮ ሊንክ (የራስህን የቪዲዮ ሊንክ እዚህ መተካት ትችላለህ)
    video_url = "https://raw.githubusercontent.com/aiogram/aiogram/dev/docs/static/img/logo.png" # ለጊዜው በምስል ተተክቷል
    caption = (
        "እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n\n"
        "እኔ አዳዲስ ዜናዎችን ከሀገር ውስጥ (አቤል ብርሀኑ፣ ፋና) እና ከዓለም ዙሪያ "
        "ወዲያውኑ አደርስዎታለሁ። እንዲሁም የሚፈልጉትን መረጃ እዚህ መጻፍ ይችላሉ።"
    )
    
    try:
        # ቪዲዮው የማይሰራ ከሆነ በጽሁፍ ብቻ ይልካል
        await message.answer_photo(photo=video_url, caption=caption)
    except:
        await message.answer(caption)

@dp.message()
async def handle_all(message: types.Message):
    """ማንኛውም ጥያቄ ሲመጣ ተጠቃሚውን መዝግቦ ፍለጋ ያደርጋል"""
    register_user(message.from_user.id)
    
    query = message.text
    if not query: return
    
    status_msg = await message.answer("🔍 መረጃውን እያጣራሁ ነው...")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        search_url = f"https://www.google.com/search?q={query}+news&num=5"
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links = []
        for a in soup.find_all('a', href=True):
            link = a['href']
            if link.startswith('/url?q='):
                clean_link = link.split('/url?q=')[1].split('&')[0]
                if "google.com" not in clean_link:
                    links.append(clean_link)
            if len(links) == 3: break

        if links:
            response_text = "✅ **የተገኘ መረጃ፦**\n\n" + "\n\n".join([f"🔗 {l}" for l in links])
        else:
            response_text = f"❌ ዝርዝር መረጃ አላገኘሁም። እዚህ ይሞክሩ፦\n🔗 https://www.google.com/search?q={query.replace(' ', '+')}"

        await status_msg.edit_text(response_text, disable_web_page_preview=True)
    except:
        await status_msg.edit_text("⚠️ ችግር አጋጥሟል። ቆይተው ይሞክሩ።")

# --- Server Keep-Alive ---
@app.route('/')
def home(): return "Bot with SQLite and News Broadcast is Online!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    # የዜና መከታተያውን ማስጀመር
    asyncio.create_task(fetch_latest_news())
    # ቦቱን ማስጀመር
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
