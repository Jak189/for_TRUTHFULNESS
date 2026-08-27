import logging, os, asyncio, requests, feedparser, psycopg2
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import google.generativeai as genai

# --- Setup ---
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
DATABASE_URL = os.getenv('DATABASE_URL')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

app = Flask('')

# --- Gemini AI Setup ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    ai_model = None

# --- Database Setup (Neon PostgreSQL) ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # የተጠቃሚዎች መረጃ
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE, 
                type TEXT, 
                username TEXT
            )
        """)
        # የተላኩ ዜናዎች መያዣ (እንዳይደገሙ)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_news_db (
                link TEXT PRIMARY KEY
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"DB Init Error: {e}")

init_db()

# --- የሳይበርና ሃኪንግ ዜናዎች ብቻ (Cybersecurity & Hacking Feeds) ---
NEWS_FEEDS = [
    "https://feeds.feedburner.com/TheHackersNews",
    "https://www.bleepingcomputer.com/feed/",
    "https://cyberscoop.com/feed/",
    "https://www.darkreading.com/rss.xml",
    "https://news.google.com/rss/search?q=cybersecurity+OR+hacking+OR+malware&hl=en&gl=US&ceid=US:en"
]

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Helpers ---

def is_news_sent(link):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT link FROM sent_news_db WHERE link = %s", (link,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row is not None
    except:
        return False

def save_sent_news(link):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO sent_news_db (link) VALUES (%s) ON CONFLICT DO NOTHING", (link,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Save News Error: {e}")

async def ai_translate(text, target_lang="Amharic"):
    if not ai_model or not text.strip():
        return text
    try:
        prompt = f"Translate this cybersecurity news into clear, natural {target_lang}. Return ONLY translation:\n\n{text}"
        res = await asyncio.to_thread(ai_model.generate_content, prompt)
        return res.text.strip()
    except Exception as e:
        logging.error(f"Translation Error: {e}")
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
    except Exception as e:
        logging.error(f"Register Error: {e}")

async def fetch_news_loop():
    while True:
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:2]:
                    if not is_news_sent(entry.link):
                        builder = InlineKeyboardBuilder()
                        builder.row(
                            types.InlineKeyboardButton(text="✅ አጽድቅ (Approve)", callback_data="ok_send"),
                            types.InlineKeyboardButton(text="❌ ይቅር (Ignore)", callback_data="no_skip")
                        )
                        admin_msg = f"📩 **አዲስ የሳይበር/ሃኪንግ ዜና ቀርቧል!**\n\n📝 ርዕስ: {entry.title}\n🔗 ሊንክ: {entry.link}"
                        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=builder.as_markup())
                        save_sent_news(entry.link)
            except Exception as e:
                logging.error(f"Feed Fetch Error: {e}")
        await asyncio.sleep(60)

# --- Handlers ---

@dp.callback_query(F.data == "ok_send")
async def approve_news(callback: types.CallbackQuery):
    msg_text = callback.message.text
    try:
        news_link = msg_text.split("🔗 ሊንክ: ")[1].split("\n")[0].strip()
        news_title = msg_text.split("📝 ርዕስ: ")[1].split("\n")[0]
        
        res = requests.get(news_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        full_text_en = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 60])

        am_title = await ai_translate(news_title, "Amharic")
        am_body = await ai_translate(full_text_en[:2000], "Amharic")

        broadcast_msg = f"🛡 **CYBER & HACKING NEWS**\n\n🇪🇹 **ርዕስ፦ {am_title}**\n\n📝 **ዝርዝር ዘገባ፦**\n{am_body}\n\n🔗 {news_link}"
        
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
                await asyncio.sleep(0.05)
                count += 1
            except Exception as e:
                logging.error(f"Send Error: {e}")
        await callback.message.edit_text(f"✅ ለ {count} አድራሻዎች ተሰራጭቷል!")
    except Exception as e:
        await callback.answer(f"Error: {e}", show_alert=True)

@dp.callback_query(F.data == "no_skip")
async def ignore_news(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ ዜናው ታልፏል (ተሰርዟል)።")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    await message.answer("ሰላም! እንኳን ወደ የሳይበር ደህንነት፣ ሃኪንግ እና AI ረዳት ቦት በሰላም መጡ። 🛡️🤖\n\nየምትፈልጉትን ማንኛውንም ጥያቄ መጠየቅ ትችላላችሁ!")

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
        await message.answer(report)

# --- 💬 ሰው መሰል AI ቻት (Human-like AI Persona) ---
@dp.message()
async def chat_and_reg(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    
    if not message.text.startswith('/'):
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        try:
            if ai_model:
                # ቦቱ ልክ እንደ እውነተኛ ሰውና አስተዋይ AI እንዲያወራ የተሰጠ መመሪያ
                prompt = f"""
                You are a smart, empathetic, and highly capable AI assistant, functioning just like Gemini.
                Your persona:
                - Talk like a real, thoughtful human peer—warm, helpful, concise, and direct.
                - Do NOT repeat, mirror, or echo the user's text back to them.
                - Always reply strictly in the EXACT SAME LANGUAGE the user writes in.
                - If the user writes in Amharic (or Amharic in Latin alphabet/Fidel), reply in natural, fluent Amharic.
                - If the user writes in English, reply in English.
                - Never output multiple languages or translations side by side.
                
                User input: {message.text}
                """
                response = await asyncio.to_thread(ai_model.generate_content, prompt)
                if response and response.text:
                    await message.reply(response.text.strip())
                else:
                    await message.reply("ይቅርታ፣ መልሱን ማዘጋጀት አልተቻለም።")
            else:
                await message.reply("⚠️ GEMINI_API_KEY በ Render ላይ አልተዘጋጀም።")
                
        except Exception as e:
            logging.error(f"AI Error: {e}")
            await message.reply("ይቅርታ፣ አሁን መልስ መስጠት አልተቻለም። እባክዎ ትንሽ ቆይተው ይሞክሩ።")

# --- Server ---
@app.route('/')
def home(): return "Bot is Active!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(fetch_news_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
