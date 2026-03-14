import logging
import os
import asyncio
import requests
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# መረጃዎችን ከ Environment Variables ላይ መሳብ
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

# Flask Setup (Render እንዳይዘጋው)
app = Flask('')

@app.route('/')
def home():
    return "for_TRUTHFULNESS Bot is Running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# Bot Setup
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n\nማረጋገጥ የሚፈልጉትን ዜና ወይም መረጃ እዚህ ይጻፉልኝ።")

@dp.message()
async def auto_check_info(message: types.Message):
    if not message.text: return
    
    query = message.text
    status_msg = await message.answer("🔍 መረጃውን እያጣራሁ ነው... እባክዎ ይጠብቁ።")

    # ለአንተ (Admin) ሪፖርት መላክ
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"🚨 **ጥያቄ!**\n👤 **ከ:** {message.from_user.full_name}\n📝 **ጥያቄ:** {query}")
        except: pass

    try:
        # ጎግልን እንደ ሰው ሆኖ ለመጠየቅ (Headers)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        search_url = f"https://www.google.com/search?q={query}+news"
        
        response = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links = []
        # የጎግል የፍለጋ ውጤት ሊንኮችን መልቀም
        # ማሳሰቢያ፡ የጎግል ዲዛይን ሲቀየር እነዚህ 'h3' እና 'a' ታጎች ሊቀየሩ ይችላሉ
        for g in soup.find_all('div', class_='tF2Cxc'):
            link = g.find('a')['href']
            if link:
                links.append(link)
            if len(links) == 3: break

        if links:
            response_text = "✅ **የፍለጋ ውጤቶች ተገኝተዋል፡**\n\n"
            for i, link in enumerate(links, 1):
                response_text += f"{i}. 🔗 {link}\n\n"
        else:
            response_text = "❌ ይቅርታ፣ አሁን ላይ መረጃውን ማግኘት አልቻልኩም። እባክዎ ጥያቄውን በሌላ ቃላት (ለምሳሌ በእንግሊዝኛ) ይሞክሩ።"

        await status_msg.edit_text(response_text, disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Search Error: {e}")
        await status_msg.edit_text("⚠️ ፍለጋውን ማከናወን አልቻልኩም። ቆይተው ይሞክሩ።")

async def main():
    # Flask-ን ማስጀመር
    Thread(target=run_flask).start()
    # ቦቱን ማስጀመር
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
