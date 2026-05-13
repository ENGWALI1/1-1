import os
import json
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

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
    print(f"✅ تم تحميل {len(STUDENT_PAGES)} صفحة")

# ==================== القائمة الرئيسية (أزرار ثابتة) ====================
main_menu = ReplyKeyboardMarkup([
    ["📖 كتاب الطالب", "🏠 الرئيسية"]
], resize_keyboard=True)

# ==================== دوال الأزرار التفاعلية ====================
def get_page_buttons(page_num):
    buttons = []
    nav = []
    
    if int(page_num) > 1:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"page_{int(page_num)-1}"))
    if int(page_num) < len(STUDENT_PAGES):
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"page_{int(page_num)+1}"))
    
    if nav:
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)

# ==================== الأوامر ====================
async def start(update, context):
    """أمر /start"""
    await update.message.reply_text(
        f"🎓 مرحباً بك!\n📚 عدد الصفحات: {len(STUDENT_PAGES)}\n\nاضغط على 📖 كتاب الطالب",
        parse_mode='Markdown',
        reply_markup=main_menu
    )

async def student_book(update, context):
    """عند الضغط على زر '📖 كتاب الطالب'"""
    context.user_data["book"] = "student"
    await update.message.reply_text(
        f"📖 أرسل رقم الصفحة من 1 إلى {len(STUDENT_PAGES)}"
    )

async def show_page(update, context):
    """عند إرسال رقم صفحة"""
    try:
        page_num = str(int(update.message.text.strip()))
        
        if context.user_data.get("book") != "student":
            await update.message.reply_text("❌ اضغط على 📖 كتاب الطالب أولاً")
            return
        
        if page_num in STUDENT_PAGES:
            content = STUDENT_PAGES[page_num]["content"]
            title = STUDENT_PAGES[page_num]["title"]
            
            if len(content) > 4000:
                content = content[:4000] + "\n\n...(يوجد محتوى إضافي)"
            
            await update.message.reply_text(
                f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                parse_mode='Markdown',
                reply_markup=get_page_buttons(page_num)
            )
            context.user_data["current_page"] = page_num
        else:
            await update.message.reply_text(f"❌ الصفحة {page_num} غير موجودة")
    except ValueError:
        await update.message.reply_text("❌ أرسل رقم صفحة صحيح")

async def back_home(update, context):
    """عند الضغط على زر '🏠 الرئيسية'"""
    context.user_data.clear()
    await start(update, context)

# ==================== معالج الأزرار التفاعلية ====================
async def handle_callback(update, context):
    """عند الضغط على أزرار 'السابق'، 'التالي'، 'القائمة الرئيسية'"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "main_menu":
        await query.message.delete()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🎓 مرحباً بك!\n📚 عدد الصفحات: {len(STUDENT_PAGES)}",
            reply_markup=main_menu
        )
        return
    
    if data.startswith("page_"):
        page_num = data.split("_")[1]
        
        if page_num in STUDENT_PAGES:
            content = STUDENT_PAGES[page_num]["content"]
            title = STUDENT_PAGES[page_num]["title"]
            
            if len(content) > 4000:
                content = content[:4000] + "\n\n...(يوجد محتوى إضافي)"
            
            await query.edit_message_text(
                f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                parse_mode='Markdown',
                reply_markup=get_page_buttons(page_num)
            )

# ==================== التشغيل ====================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # أوامر عامة
    app.add_handler(CommandHandler("start", start))
    
    # الأزرار الثابتة (ReplyKeyboardMarkup)
    app.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), student_book))
    app.add_handler(MessageHandler(filters.Text("🏠 الرئيسية"), back_home))
    
    # رسائل نصية (أرقام الصفحات)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, show_page))
    
    # الأزرار التفاعلية (InlineKeyboardMarkup)
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("=" * 60)
    print(f"🔥 البوت شغال! {len(STUDENT_PAGES)} صفحة")
    print("=" * 60)
    app.run_polling()

if __name__ == "__main__":
    main()
