import logging
import os
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from googlesearch import search

# መረጃዎችን ከ Environment Variables ላይ መሳብ (ለደህንነት)
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

# Flask Setup (Render እንዳይዘጋው ለማድረግ)
app = Flask('')

@app.route('/')
def home():
    return "for_TRUTHFULNESS Bot is Running!"

def run_flask():
    # Render የሚጠቀምበትን Port በራሱ እንዲመርጥ ማድረግ
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# Bot Logging
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    welcome_text = (
        "እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n\n"
        "የጠረጠሩትን ዜና ወይም መረጃ እዚህ ይጻፉልኝ። "
        "እኔ ደግሞ ከታመኑ ድረ-ገጾች ላይ ፈልጌ ውጤቱን እነግርዎታለሁ።"
    )
    await message.reply(welcome_text)

@dp.message_handler()
async def auto_check_info(message: types.Message):
    query = message.text
    user_name = message.from_user.full_name
    
    status_msg = await message.answer("🔍 መረጃውን እያጣራሁ ነው... እባክዎ ጥቂት ሰከንዶች ይጠብቁ።")

    # ለአንተ (Admin) ሪፖርት መላክ
    if ADMIN_ID:
        try:
            report = f"🚨 **አዲስ ጥያቄ!**\n👤 **ከ:** {user_name}\n📝 **ጥያቄ:** {query}"
            await bot.send_message(ADMIN_ID, report)
        except:
            pass

    try:
        # ጎግል ላይ መፈለግ
        search_results = []
        for j in search(query + " news", num_results=3):
            search_results.append(j)

        if search_results:
            response_text = "✅ **የፍለጋ ውጤቶች ተገኝተዋል፡**\n\n"
            for link in search_results:
                response_text += f"🔗 {link}\n\n"
            response_text += "⚠️ መረጃው በትክክለኛ የዜና ድረ-ገጾች ላይ መኖሩን በሊንኮቹ ገብተው ያረጋግጡ።"
        else:
            response_text = "❌ ይቅርታ፣ ስለዚህ ጉዳይ በታመኑ የዜና ምንጮች ላይ ምንም መረጃ አላገኘሁም። መረጃው ትክክል ላይሆን ስለሚችል ጥንቃቄ ያድርጉ።"

        await status_msg.edit_text(response_text, disable_web_page_preview=True)

    except Exception as e:
        await status_msg.edit_text("⚠️ በአሁኑ ሰዓት ፍለጋ ማከናወን አልቻልኩም። እባክዎ ቆይተው ይሞክሩ።")
        print(f"Error: {e}")

if __name__ == '__main__':
    # Flask-ን በሌላ Thread ማስጀመር
    t = Thread(target=run_flask)
    t.start()
    
    # ቦቱን ማስጀመር
    executor.start_polling(dp, skip_updates=True)
