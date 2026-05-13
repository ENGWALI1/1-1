import os
import json
import asyncio
import logging
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ['BOT_TOKEN']
HOSTNAME = os.environ['RENDER_EXTERNAL_HOSTNAME']
WEBHOOK_URL = f"https://{HOSTNAME}/{TOKEN}"

logger.info(f"🚀 Starting @withali91_bot")
logger.info(f"🌐 Webhook: {WEBHOOK_URL}")

with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)
logger.info(f"📚 Loaded {len(BOOK)} pages")

application = Application.builder().token(TOKEN).build()

menu = ReplyKeyboardMarkup([["📖 كتاب الطالب"]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"👤 /start from {update.effective_user.username}")
    await update.message.reply_text(
        f"🎉 مرحباً!\n📚 كتاب الطالب: {len(BOOK)} صفحة\nاضغط 📖",
        reply_markup=menu
    )

async def book_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📖 Book button from {update.effective_user.username}")
    context.user_data['waiting_page'] = True
    await update.message.reply_text("📄 أرسل رقم الصفحة (1-80):")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    logger.info(f"💬 Text: '{text}'")
    
    if context.user_data.get('waiting_page'):
        if text in BOOK:
            content = BOOK[text]['content'][:3500]
            await update.message.reply_text(f"📖 **صفحة {text}**\n\n{content}")
            logger.info(f"✅ Page {text} sent")
        else:
            await update.message.reply_text(f"❌ صفحة {text} غير موجودة!")
        context.user_data['waiting_page'] = False
    else:
        await update.message.reply_text("📖 اضغط 'كتاب الطالب'", reply_markup=menu)

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), book_request))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

@app.route('/', methods=['GET'])
def home():
    return f"<h1>🤖 @withali91_bot شغال!</h1><p>📚 {len(BOOK)} صفحة</p>"

@app.route('/set', methods=['GET'])
def set_webhook():
    application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🔗 Webhook activated: {WEBHOOK_URL}")
    return f"<h1>✅ Webhook مفعّل!</h1><p>{WEBHOOK_URL}</p>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json()
        update = Update.de_json(json_data, application.bot)
        logger.info(f"📨 Update #{update.update_id}")
        
        # إصلاح الـ async problem
        asyncio.create_task(application.process_update(update))
        return 'OK'
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return 'ERROR', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
