import logging
import os
import asyncio
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from googlesearch import search

# መረጃዎች
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

# Flask Setup
app = Flask('')

@app.route('/')
def home():
    return "for_TRUTHFULNESS Bot is Running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# Bot Setup (Version 3 style)
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n\nየጠረጠሩትን ዜና ወይም መረጃ እዚህ ይጻፉልኝ።")

@dp.message()
async def auto_check_info(message: types.Message):
    if not message.text: return
    
    query = message.text
    status_msg = await message.answer("🔍 መረጃውን እያጣራሁ ነው... እባክዎ ይጠብቁ።")

    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"🚨 **ጥያቄ!**\n👤 **ከ:** {message.from_user.full_name}\n📝 **ጥያቄ:** {query}")
        except: pass

    try:
        search_results = []
        for j in search(query + " news", num_results=3):
            search_results.append(j)

        if search_results:
            response_text = "✅ **የፍለጋ ውጤቶች ተገኝተዋል፡**\n\n" + "\n".join([f"🔗 {link}" for link in search_results])
        else:
            response_text = "❌ ስለዚህ ጉዳይ በታመኑ የዜና ምንጮች ላይ ምንም መረጃ አላገኘሁም።"

        await status_msg.edit_text(response_text)
    except Exception:
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
