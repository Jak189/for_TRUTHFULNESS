import logging
import os
import asyncio
import requests
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Environment Variables (ከ Render Dashboard የሚወሰዱ)
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

# Flask Setup - Render ቦቱን እንዳይዘጋው (Keep-alive)
app = Flask('')

@app.route('/')
def home():
    return "for_TRUTHFULNESS Bot is Running!"

def run_flask():
    # Render የሚሰጠውን Port መጠቀም ወይም 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# Bot Setup (Version 3)
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

    # ለአድሚኑ (አማን) ሪፖርት መላክ
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"🚨 **አዲስ ጥያቄ!**\n👤 **ከ:** {message.from_user.full_name}\n📝 **ጥያቄ:** {query}")
        except: pass

    try:
        # ጎግልን በቀላሉ መፈለግ (Lite Search Method)
        headers = {'User-Agent': 'Mozilla/5.0'}
        search_url = f"https://www.google.com/search?q={query}+news&num=5"
        
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links = []
        # ሁሉንም ሊንኮች ፈልጎ ማጣራት
        for a in soup.find_all('a', href=True):
            link = a['href']
            # ከጎግል የውስጥ ሊንኮች ውጭ የሆኑትን ዋና ዋና ዜናዎች መለየት
            if link.startswith('/url?q='):
                clean_link = link.split('/url?q=')[1].split('&')[0]
                # ጎግል ጋር ተያያዥ የሆኑ ሊንኮችን ማውጣት
                if "google.com" not in clean_link and "accounts.google" not in clean_link:
                    links.append(clean_link)
            
            if len(links) == 3: break # 3 ውጤት ብቻ

        if links:
            response_text = "✅ **የተገኙ መረጃዎች (ሊንኮች)፦**\n\n"
            for i, l in enumerate(links, 1):
                response_text += f"{i}. 🔗 {l}\n\n"
        else:
            response_text = "❌ ይቅርታ፣ ስለዚህ ጉዳይ አሁን ላይ መረጃ ማግኘት አልቻልኩም። እባክዎ ጥያቄውን በሌላ ቃላት ይሞክሩ።"

        await status_msg.edit_text(response_text, disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Error during search: {e}")
        await status_msg.edit_text("⚠️ ቴክኒካዊ ችግር አጋጥሟል። እባክዎ ጥቂት ቆይተው ይሞክሩ።")

async def main():
    # Flask-ን በሌላ Thread ማስጀመር
    Thread(target=run_flask).start()
    # ቦቱን በ Polling ማስጀመር
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
