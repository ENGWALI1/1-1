import os
import json
import logging
from flask import Flask, request, abort
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext
from telegram.constants import ParseMode

# ==================== اللوغ ====================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== فلاسك ====================
app = Flask(__name__)

# ==================== التوكن ====================
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN غير موجود في المتغيرات البيئية!")

# ==================== تحميل الكتاب ====================
with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)

# ==================== الأزرار ====================
menu = ReplyKeyboardMarkup([["📖 كتاب الطالب"]], resize_keyboard=True)

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
            # تقسيم النص إذا كان طويل
            if len(content) > 4000:
                for i in range(0, len(content), 4000):
                    await update.message.reply_text(f"📖 صفحة {page} ({i//4000+1})\n\n{content[i:i+4000]}")
            else:
                await update.message.reply_text(f"📖 صفحة {page}\n\n{content}")
        else:
            await update.message.reply_text(f"❌ الصفحة {page} غير موجودة! (الصفحات المتاحة: 1-{max(BOOK.keys())})")
        context.user_data['waiting_page'] = False

# ==================== Webhook ====================
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_json()
        update = Update.de_json(json_string, app.bot)
        app.process_update(update)
        return 'ok'
    else:
        abort(403)

@app.route('/')
def home():
    return "🤖 البوت شغال! | Bot is alive!"

@app.route('/setwebhook')
def set_webhook():
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    app.bot.setWebhook(webhook_url)
    return f"Webhook set to: {webhook_url}"

# ==================== التشغيل ====================
if __name__ == '__main__':
    # إنشاء التطبيق
    app = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), ask_page))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, read_page))
    
    # تشغيل الـ webhook
    port = int(os.environ.get('PORT', 10000))
    app.bot.setWebhook(f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}")
    
    print(f"🚀 البوت شغال على PORT: {port} | صفحات: {len(BOOK)}")
    app.run(host='0.0.0.0', port=port)
