import os
import json
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging

# اللوغ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# التوكن
TOKEN = os.environ['BOT_TOKEN']
print(f"✅ TOKEN loaded")

# الكتاب
with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)
print(f"✅ BOOK loaded: {len(BOOK)} pages")

# البوت
application = Application.builder().token(TOKEN).build()

# الأزرار
KEYBOARD = [['📖 كتاب الطالب']]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📚 كتاب الطالب: {len(BOOK)} صفحة",
        reply_markup={'keyboard': KEYBOARD, 'resize_keyboard': True}
    )

async def ask_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['waiting'] = True
    await update.message.reply_text("📄 رقم الصفحة (1-80):")

async def handle_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting'):
        page = update.message.text.strip()
        if page in BOOK:
            text = BOOK[page]['content'][:4000]
            await update.message.reply_text(f"📖 صفحة {page}\n\n{text}")
        else:
            await update.message.reply_text("❌ صفحة غير موجودة!")
        context.user_data['waiting'] = False

# إضافة handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.Regex("📖 كتاب الطالب"), ask_page))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_page))

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook_update():
    update = Update.de_json(request.get_json(), application.bot)
    application.process_update(update)
    return 'ok'

@app.route('/')
def index():
    return f'🤖 Bot OK | Pages: {len(BOOK)}'

@app.route('/set')
def set_webhook():
    url = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{TOKEN}"
    application.bot.set_webhook(url)
    return f'Webhook: {url}'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
