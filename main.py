import logging
import os
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from googlesearch import search

# መረጃዎች
API_TOKEN = '8671915044:AAGvfAUSqlLfpWdbz74M0FbAuxMQftdmHmA'
ADMIN_ID = '8394878208'

# Flask ለ Render (Keep Alive እንዲሆን)
app = Flask('')

@app.route('/')
def home():
    return "for_TRUTHFULNESS Bot is Running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# Bot Setup
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n\nማረጋገጥ የሚፈልጉትን ዜና ወይም መረጃ እዚህ ይጻፉልኝ።")

@dp.message_handler()
async def auto_check_info(message: types.Message):
    query = message.text
    status_msg = await message.answer("🔍 መረጃውን እያጣራሁ ነው... እባክዎ ይጠብቁ።")

    # ለአንተ (Admin) መረጃ መላክ
    await bot.send_message(ADMIN_ID, f"🚨 **ጥያቄ መጣ!**\n👤 **ከ:** {message.from_user.full_name}\n📝 **ጥያቄ:** {query}")

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

if __name__ == '__main__':
    # Flask-ን በሌላ Thread ማስጀመር
    t = Thread(target=run_flask)
    t.start()
    
    # ቦቱን ማስጀመር
    executor.start_polling(dp, skip_updates=True)
