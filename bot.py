import os
import json
import logging
from flask import Flask, request, abort
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext

# ==================== اللوغ ====================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== فلاسك ====================
app = Flask(__name__)

# ==================== التوكن ====================
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN غير موجود!")

# ==================== تحميل الكتاب ====================
try:
    with open('student_textbook.json', 'r', encoding='utf-8') as f:
        BOOK = json.load(f)
except FileNotFoundError:
    raise FileNotFoundError("❌ student_textbook.json مش موجود!")

# ==================== الأزرار ====================
menu = ReplyKeyboardMarkup([["📖 كتاب الطالب"]], resize_keyboard=True)

# ==================== الـ Application ====================
application = ApplicationBuilder().token(TOKEN).build()

# ==================== الأوامر ====================
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        f"📚 كتاب الطالب يحتوي على {len(BOOK)} صفحة.\nاضغط على الزر 👇", 
        reply_markup=menu
    )

async def ask_page(update: Update, context: CallbackContext) -> None:
    context.user_data['waiting_page'] = True
    await update.message.reply_text("📄 أرسل رقم الصفحة (1-80):")

async def read_page(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('waiting_page'):
        page = update.message.text.strip()
        if page in BOOK:
            content = BOOK[page]["content"]
            if len(content) > 4000:
                for i in range(0, len(content), 4000):
                    await update.message.reply_text(f"📖 صفحة {page} ({i//4000+1})\n\n{content[i:i+4000]}")
            else:
                await update.message.reply_text(f"📖 صفحة {page}\n\n{content}")
        else:
            await update.message.reply_text(f"❌ الصفحة {page} غير موجودة!")
        context.user_data['waiting_page'] = False

# إضافة المعالجات
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), ask_page))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, read_page))

# ==================== Webhook ====================
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(), application.bot)
    application.process_update(update)
    return 'OK'

@app.route('/')
def home():
    return f"🤖 البوت شغال! | صفحات: {len(BOOK)}"

@app.route('/setwebhook')
def set_webhook():
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    application.bot.setWebhook(webhook_url)
    return f"✅ Webhook: {webhook_url}"

# ==================== تشغيل ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 البوت شغال على PORT: {port}")
    print(f"📚 عدد الصفحات: {len(BOOK)}")
    app.run(host='0.0.0.0', port=port, debug=False)
