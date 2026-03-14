import logging
import os
import asyncio
import requests
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Environment Variables
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

app = Flask('')

@app.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n\nማረጋገጥ የሚፈልጉትን ዜና እዚህ ይጻፉልኝ።")

@dp.message()
async def auto_check_info(message: types.Message):
    if not message.text: return
    
    query = message.text
    status_msg = await message.answer("🔍 መረጃውን እያጣራሁ ነው... እባክዎ ይጠብቁ።")

    # ለአድሚኑ (አማን) ሪፖርት መላክ
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"🚨 **ጥያቄ:** {query}")
        except: pass

    try:
        # እጅግ በጣም አስተማማኝ የፍለጋ ዘዴ (DuckDuckGo API)
        search_url = f"https://api.duckduckgo.com/?q={query}&format=json"
        response = requests.get(search_url).json()
        
        links = []
        # ከዋናው መልስ ሊንክ ካለ
        if response.get('AbstractURL'):
            links.append(response['AbstractURL'])
            
        # ከሌሎች ተያያዥ መልሶች ሊንክ መፈለግ
        for topic in response.get('RelatedTopics', []):
            if 'FirstURL' in topic:
                links.append(topic['FirstURL'])
            if len(links) >= 3: break

        if links:
            response_text = "✅ **የተገኘ መረጃ፦**\n\n"
            for i, l in enumerate(links, 1):
                response_text += f"{i}. 🔗 {l}\n\n"
        else:
            # ፍለጋው ውጤት ካላመጣ ቀጥታ ሊንኩን መስጠት
            response_text = f"❌ ዝርዝር መረጃ አሁን ላይ ማግኘት አልቻልኩም። ለበለጠ መረጃ ይህን ሊንክ ይጫኑ፦\n\n🔗 https://www.google.com/search?q={query.replace(' ', '+')}"

        await status_msg.edit_text(response_text, disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Error: {e}")
        await status_msg.edit_text("⚠️ ቴክኒካዊ ችግር አጋጥሟል። ቆይተው ይሞክሩ።")

async def main():
    Thread(target=run_flask).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
