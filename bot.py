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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== تحميل كتاب الطالب ====================
STUDENT_PAGES = {}
json_path = os.path.join(BASE_DIR, "student_textbook.json")

if os.path.exists(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for page_num, page_data in data.items():
            content = page_data.get("content", "لا يوجد محتوى")
            title = page_data.get("title", f"صفحة {page_num}")
            STUDENT_PAGES[page_num] = {
                "title": title,
                "content": content
            }
    print(f"✅ تم تحميل {len(STUDENT_PAGES)} صفحة من كتاب الطالب")
else:
    print(f"❌ الملف {json_path} غير موجود")

# ==================== القائمة ====================
menu = ReplyKeyboardMarkup([
    ["📖 كتاب الطالب"],
    ["🏠 الرئيسية"]
], resize_keyboard=True)

# ==================== أوامر البوت ====================
async def start(update, context):
    await update.message.reply_text(
        f"🎓 مرحباً بك في البوت!\n"
        f"📚 عدد صفحات كتاب الطالب: {len(STUDENT_PAGES)}\n\n"
        f"اختر 📖 كتاب الطالب ثم أرسل رقم الصفحة (1-80)",
        reply_markup=menu
    )

async def student_book(update, context):
    context.user_data["book"] = "student"
    await update.message.reply_text(
        "📖 أرسل رقم الصفحة (1-80)\n"
        f"الصفحات المتوفرة: 1 إلى {len(STUDENT_PAGES)}"
    )

async def show_page(update, context):
    try:
        page = str(int(update.message.text.strip()))
        
        if context.user_data.get("book") != "student":
            await update.message.reply_text("❌ اختر 📖 كتاب الطالب أولاً من القائمة")
            return
        
        if page in STUDENT_PAGES:
            page_data = STUDENT_PAGES[page]
            content = page_data["content"]
            title = page_data["title"]
            
            # تقسيم النص الطويل
            if len(content) > 4000:
                content = content[:4000] + "\n\n... (يوجد محتوى إضافي)"
            
            await update.message.reply_text(
                f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ الصفحة {page} غير موجودة\n"
                f"الصفحات المتوفرة: 1 إلى {len(STUDENT_PAGES)}"
            )
    except ValueError:
        await update.message.reply_text("❌ أرسل رقم صفحة صحيح (مثال: 10)")

async def back_home(update, context):
    context.user_data.clear()
    await start(update, context)

# ==================== التشغيل ====================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), student_book))
    app.add_handler(MessageHandler(filters.Text("🏠 الرئيسية"), back_home))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, show_page))
    
    print("=" * 60)
    print(f"🔥 البوت شغال! صفحات الطالب: {len(STUDENT_PAGES)}")
    print("=" * 60)
    app.run_polling()

if __name__ == "__main__":
    main()
