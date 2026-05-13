import os
import json
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

app = Flask(__name__)

# التوكن من البيئة
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ BOT_TOKEN missing!")
    exit(1)

HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'atwithali91-bot.onrender.com')
WEBHOOK_URL = f"https://{HOSTNAME}/{TOKEN}"

print(f"🚀 TOKEN: {TOKEN[:20]}...")
print(f"🌐 WEBHOOK: {WEBHOOK_URL}")

# الكتاب
with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)
print(f"📚 {len(BOOK)} pages")

application = Application.builder().token(TOKEN).build()
menu = ReplyKeyboardMarkup([["📖 كتاب الطالب"]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🎉 {len(BOOK)} صفحة 📚", reply_markup=menu)

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['page_wait'] = True
    await update.message.reply_text("📄 رقم الصفحة:")

async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if context.user_data.get('page_wait'):
        if text in BOOK:
            await update.message.reply_text(f"📖 {text}\n\n{BOOK[text]['content'][:3000]}")
        else:
            await update.message.reply_text("❌ غير موجود!")
        context.user_data['page_wait'] = False

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), book))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))

# كل الـ routes
@app.route('/', methods=['GET'])
def home():
    return f"🤖 OK | {len(BOOK)} pages | <a href='/set'>SET</a>"

@app.route('/set', methods=['GET'])
def set_webhook():
    application.bot.set_webhook(WEBHOOK_URL)
    return f"✅ SET {WEBHOOK_URL}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(), application.bot)
    application.process_update(update)
    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
