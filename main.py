import logging
import os
import asyncio
import requests
import feedparser
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Environment Variables
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

# መከታተል የምትፈልጋቸው የዜና ምንጮች (RSS Feeds)
# እዚህ ውስጥ ተጨማሪ የፈለግከውን የዜና ሊንክ መጨመር ትችላለህ
NEWS_FEEDS = [
    "https://www.aljazeera.com/xml/rss/all.xml", 
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
]

# የተላኩ ዜናዎችን መቆጣጠሪያ
sent_news = set()

app = Flask('')

@app.route('/')
def home():
    return "Bot is Running with News Monitor!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# 1. አዲስ ዜናዎችን የሚከታተል ተግባር (Background Task)
async def fetch_latest_news():
    while True:
        logging.info("Checking for new stories...")
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                # ከመጀመሪያዎቹ 2 አዳዲስ ዜናዎች ብቻ
                for entry in feed.entries[:2]:
                    if entry.link not in sent_news:
                        news_msg = f"🔔 **ሰበር ዜና ተገኝቷል!**\n\n📌 {entry.title}\n\n🔗 {entry.link}"
                        
                        if ADMIN_ID:
                            await bot.send_message(ADMIN_ID, news_msg)
                        
                        sent_news.add(entry.link)
                        # የትውስታ መጠኑ እንዳይሞላ ከ 1000 በላይ ሲሆን አጽዳ
                        if len(sent_news) > 1000:
                            sent_news.clear()
            except Exception as e:
                logging.error(f"News monitor error: {e}")
        
        await asyncio.sleep(600) # በየ 10 ደቂቃው ይፈትሻል

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply("እንኳን ወደ for_TRUTHFULNESS በሰላም መጡ! ⚖️\n\nአዳዲስ ዜናዎችን እከታተላለሁ፣ እንዲሁም የፈለጉትን መረጃ እዚህ መፈለግ ይችላሉ።")

# 2. የፍለጋ ተግባር (Search Function)
@dp.message()
async def auto_check_info(message: types.Message):
    if not message.text: return
    
    query = message.text
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
    except Exception as e:
        await status_msg.edit_text("⚠️ ችግር አጋጥሟል። ቆይተው ይሞክሩ።")

async def main():
    # Flask-ን ማስጀመር
    Thread(target=run_flask).start()
    
    # የዜና መከታተያውን በ asyncio ማስጀመር
    asyncio.create_task(fetch_latest_news())
    
    # ቦቱን ማስጀመር
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
