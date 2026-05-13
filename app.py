import os
import json
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ['BOT_TOKEN']
HOSTNAME = os.environ['RENDER_EXTERNAL_HOSTNAME']

print("🚀 Bot starting...")
with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)
print(f"📚 Loaded {len(BOOK)} pages")

application = Application.builder().token(TOKEN).build()

menu = ReplyKeyboardMarkup([["📖 كتاب الطالب"]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("👤 /start received")
    await update.message.reply_text(
        f"🎉 مرحباً!\n📚 {len(BOOK)} صفحة متاحة\nاضغط 👇",
        reply_markup=menu
    )

async def handle_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("📖 Book button clicked")
    context.user_data['waiting_page'] = True
    await update.message.reply_text("📄 أرسل رقم الصفحة (1-80):")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    print(f"💬 Received: {text}")
    
    if context.user_data.get('waiting_page'):
        if text in BOOK:
            content = BOOK[text]['content'][:3000]
            await update.message.reply_text(f"📖 **صفحة {text}**\n\n{content}")
            print(f"✅ Sent page {text}")
        else:
            await update.message.reply_text(f"❌ صفحة {text} غير موجودة!")
        context.user_data['waiting_page'] = False
    else:
        await update.message.reply_text("اضغط /start أو 📖 كتاب الطالب", reply_markup=menu)

# إضافة handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), handle_book))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_json(), application.bot)
        application.process_update(update)
        return "OK"
    except Exception as e:
        print(f"❌ Error: {e}")
        return "Error", 500

@app.route('/')
def home():
    return f"<h1>🤖 البوت شغال!</h1><p>📚 {len(BOOK)} صفحة</p><a href='/set'>Set Webhook</a>"

@app.route('/set')
def set_webhook():
    url = f"https://{HOSTNAME}/{TOKEN}"
    application.bot.set_webhook(url)
    return f"<h1>✅ Webhook set!</h1><p>{url}</p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
