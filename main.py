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
        return title, raw_text
    try:
        prompt = f"""
        You are an expert news reporter. 
        Read this title and snippet:
        Title: {title}
        Details: {raw_text[:1000]}

        Task:
        1. Translate and write a clear Amharic title.
        2. Write a short, clear, and comprehensive Amharic explanation (summary) of what this news is about, even if the source snippet is short.
        
        Format output exactly like this:
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
        return title, raw_text

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

        # AIው ራሱ አብራርቶ ያዘጋጀዋል
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

# --- 4. አዲስ አባል ሲቀላቀል እንኳን ደህና መጣችሁ ለማለት ---
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

# --- 2 እና 3. የ AI ቻት እና በግሩፕ ውስጥ የመልስ ገደብ ---
@dp.message()
async def chat_and_reg(message: types.Message):
    e_type = "private" if message.chat.type == "private" else "group"
    register_entity(message.chat.id, e_type, message.chat.username or message.chat.title)
    
    bot_info = await bot.get_me()
    is_private = message.chat.type == "private"
    is_admin = message.from_user.id == ADMIN_ID
    
    # ቦቱ Reply ከተደረገለት ማረጋገጫ
    is_replied_to_bot = (
        message.reply_to_message and 
        message.reply_to_message.from_user and 
        message.reply_to_message.from_user.id == bot_info.id
    )

    # 3. በግሩፕ ውስጥ ከሆነ፦ ፕራይቬት ካልሆነ፣ Admin ካላዘዘው እና Reply ካልተደረገለት አይመልስም
    if not is_private and not is_admin and not is_replied_to_bot:
        return

    if not message.text.startswith('/'):
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        try:
            if ai_model:
                # 2. ለማንኛውም ጥያቄ ምላሽ እንዲሰጥ እና እንደ እውነተኛ ሰው እንዲያወራ የተሰጠ መመሪያ
                prompt = f"""
                You are a smart, empathetic, and helpful AI assistant.
                - Answer ANY question the user asks accurately and naturally.
                - Talk like a real human peer—warm, direct, and concise.
                - Reply strictly in the EXACT SAME LANGUAGE the user writes in.
                - If written in Amharic (or Amharic in Latin alphabet), reply in natural Amharic.
                - Do NOT mirror or repeat the user's question back to them.

                User message: {message.text}
                """
                response = await asyncio.to_thread(ai_model.generate_content, prompt)
                if response and response.text:
                    await message.reply(response.text.strip())
                else:
                    await message.reply("ይቅርታ፣ ጥያቄውን ማዘጋጀት አልተቻለም።")
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
