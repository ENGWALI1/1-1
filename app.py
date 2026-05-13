import os
import json
import logging
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ['BOT_TOKEN']
bot = Bot(token=TOKEN)
HOSTNAME = os.environ['RENDER_EXTERNAL_HOSTNAME']

logger.info(f"🚀 @withali91_bot starting...")
logger.info(f"🌐 {HOSTNAME}")

with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)
logger.info(f"📚 {len(BOOK)} pages")

menu = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}

async def start(update: Update, context):
    logger.info(f"👤 /start")
    await update.message.reply_text(f"🎉 {len(BOOK)} صفحة 📚", reply_markup=menu)

async def book(update: Update, context):
    logger.info(f"📖 Book")
    context.user_data['wait_page'] = True
    await update.message.reply_text("📄 رقم الصفحة:")

async def text_msg(update: Update, context):
    text = update.message.text.strip()
    logger.info(f"💬 {text}")
    
    if context.user_data.get('wait_page'):
        if text in BOOK:
            msg = f"📖 صفحة {text}\n\n{BOOK[text]['content'][:3000]}"
            await update.message.reply_text(msg)
            logger.info(f"✅ Page {text}")
        else:
            await update.message.reply_text("❌ غير موجود!")
        context.user_data['wait_page'] = False
    else:
        await update.message.reply_text("📖 كتاب الطالب", reply_markup=menu)

application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), book))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_msg))

@app.route('/', methods=['GET'])
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>{len(BOOK)} صفحة</p>"

@app.route('/set', methods=['GET'])
def set_webhook():
    url = f"https://{HOSTNAME}/{TOKEN}"
    bot.set_webhook(url)
    logger.info(f"🔗 {url}")
    return f"<h1>✅ SET {url}</h1>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_json(), bot)
        logger.info(f"📨 Update #{update.update_id}")
        
        # Synchronous processing
        future = asyncio.run_coroutine_threadsafe(
            application.process_update(update), 
            application.loop or asyncio.new_event_loop()
        )
        future.result(timeout=10)
        return 'OK'
    except Exception as e:
        logger.error(f"❌ {e}")
        return 'ERROR', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
