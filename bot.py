import os
import json
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== خادم ويب ====================
app_web = Flask('')
@app_web.route('/')
def home():
    return "Bot is alive!"
def run_web():
    app_web.run(host='0.0.0.0', port=10000)
Thread(target=run_web).start()

# ==================== التوكن ====================
TOKEN = os.environ.get("BOT_TOKEN")

# ==================== تحميل الكتاب ====================
with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)

# ==================== الأزرار ====================
menu = ReplyKeyboardMarkup([["📖 كتاب الطالب"]], resize_keyboard=True)

# ==================== الأوامر ====================
async def start(update, context):
    await update.message.reply_text(f"📚 كتاب الطالب يحتوي على {len(BOOK)} صفحة. اضغط على الزر 👇", reply_markup=menu)

async def ask_page(update, context):
    context.user_data['waiting_page'] = True
    await update.message.reply_text("أرسل رقم الصفحة (1-80)")

async def read_page(update, context):
    if context.user_data.get('waiting_page'):
        page = update.message.text.strip()
        if page in BOOK:
            content = BOOK[page]["content"]
            await update.message.reply_text(f"📖 صفحة {page}\n\n{content[:4000]}")
        else:
            await update.message.reply_text(f"❌ الصفحة {page} غير موجودة")
        context.user_data['waiting_page'] = False

# ==================== التشغيل ====================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), ask_page))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, read_page))

print(f"🚀 البوت شغال! {len(BOOK)} صفحة")
app.run_polling()
