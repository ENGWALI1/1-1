import os
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== خادم ويب (لإرضاء Render) ====================
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is alive!"

def run_web():
    app_web.run(host='0.0.0.0', port=10000)

Thread(target=run_web).start()

# ==================== التوكن ====================
TOKEN = os.environ.get("BOT_TOKEN")

# ==================== قائمة البوت ====================
menu = ReplyKeyboardMarkup([
    ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
    ["🏠 الرئيسية"]
], resize_keyboard=True)

# ==================== أوامر البوت ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎓 مرحباً بك في البوت التعليمي!\n\n"
        "اختر من القائمة أدناه:",
        reply_markup=menu
    )

async def student_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 تم اختيار كتاب الطالب.\nالميزات الكاملة ستضاف قريباً.")

async def activity_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ تم اختيار كتاب الأنشطة.\nالميزات الكاملة ستضاف قريباً.")

async def back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ==================== تشغيل البوت ====================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), student_book))
    app.add_handler(MessageHandler(filters.Text("✏️ كتاب الأنشطة"), activity_book))
    app.add_handler(MessageHandler(filters.Text("🏠 الرئيسية"), back_home))
    
    print("🚀 البوت شغال على Render...")
    app.run_polling()

if __name__ == "__main__":
    main()