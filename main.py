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
    ai_model = genai.GenerativeModel('gemini-2.5-flash')
else:
    ai_model = None

# --- Database Setup (Neon PostgreSQL) ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE, 
                type TEXT, 
                username TEXT
            )
        """)
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

# --- የዜና ምንጮች ---
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

async def ai_explain_news(title, raw_text):
    """ዜናው ሙሉ መረጃ ባይኖረውም AIው ራሱ አብራርቶ እንዲጽፍ ማድረጊያ"""
    if not ai_model:
        return title, "የዜናውን ዝርዝር ማብራሪያ ማዘጋጀት አልተቻለም።"
    try:
        prompt = f"""
        You are a professional cyber security news translator and summary generator.
        Source Title: {title}
        Source Snippet: {raw_text[:1200]}

        Tasks:
        1. Translate the news title into clear, compelling Amharic.
        2. Write a detailed, highly informative Amharic explanation (at least 3-4 sentences) breaking down what this cyber threat/event is about, even if the snippet is short.
        
        Strict Output Format (Do not deviate):
        TITLE: <Amharic Title>
        BODY: <Amharic Detailed Explanation>
        """
        res = await asyncio.to_thread(ai_model.generate_content, prompt)
        text = res.text.strip()
        
        if "TITLE:" in text and "BODY:" in text:
            parts = text.split("BODY:")
            am_title = parts[0].replace("TITLE:", "").strip()
            am_body = parts[1].strip()
            return am_title, am_body
        return title, text
    except Exception as e:
        logging.error(f"News AI Error: {e}")
        return title, "የዜናውን ዝርዝር ማብራሪያ በ AI ማዘጋጀት አልተቻለም።"

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
        
        raw_text = ""
        try:
            res = requests.get(news_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            soup = BeautifulSoup(res.text, 'html.parser')
            paragraphs = soup.find_all('p')
            raw_text = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 40])
        except:
            raw_text = news_title

        am_title, am_body = await ai_explain_news(news_title, raw_text)

        broadcast_msg = f"🛡 **CYBER & HACKING NEWS**\n\n🇪🇹 **ርዕስ፦ {am_title}**\n\n📝 **ዝርዝር ማብራሪያ፦**\n{am_body}\n\n🔗 {news_link}"
        
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

# --- አዲስ አባል ሲቀላቀል ---
@dp.message(F.new_chat_members)
async def welcome_new_members(message: types.Message):
    bot_info = await bot.get_me()
    for member in message.new_chat_members:
        if member.id != bot_info.id:
            user_name = member.first_name
            await message.reply(f"ሰላም {user_name} 👋\nወደ ግሩፓችን እንኳን በደህና መጡ! 🌼")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    await message.answer("ሰላም! እንኳን ወደ AI ረዳት ቦት በሰላም መጡ። 🛡️🤖")

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

# --- የ AI ቻት ---
@dp.message()
async def chat_and_reg(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    
    bot_info = await bot.get_me()
    is_private = message.chat.type == "private"
    is_admin = message.from_user.id == ADMIN_ID
    
    is_replied_to_bot = (
        message.reply_to_message and 
        message.reply_to_message.from_user and 
        message.reply_to_message.from_user.id == bot_info.id
    )

    # በግሩፕ ውስጥ Reply ካልተደረገ ወይም Admin ካላዘዘው ይተዋል
    if not is_private and not is_admin and not is_replied_to_bot:
        return

    if not message.text.startswith('/'):
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        try:
            if ai_model:
                prompt = f"""
                You are a smart, friendly, and helpful AI assistant.
                - Reply logically, accurately, and naturally to the user's message like a human peer.
                - Match the language of the prompt: If written in Amharic (or Latin Amharic), respond strictly in natural Amharic. If in English, respond in English.
                - Do NOT repeat or echo the user's sentence.

                User input: {message.text}
                """
                response = await asyncio.to_thread(ai_model.generate_content, prompt)
                if response and response.text:
                    await message.reply(response.text.strip())
                else:
                    await message.reply("ይቅርታ፣ አሁን መልሱን ማዘጋጀት አልተቻለም።")
            else:
                await message.reply("⚠️ GEMINI_API_KEY በ Render ላይ አልተዘጋጀም ወይም አልሰራም።")
                
        except Exception as e:
            logging.error(f"AI Error: {e}")
            await message.reply("ይቅርታ፣ አሁን መልስ መስጠት አልተቻለም። እባክዎ GEMINI_API_KEY በ Render ላይ በትክክል መገባቱን ያረጋግጡ።")

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
