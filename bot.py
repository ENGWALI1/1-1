import os
import json
import asyncio
import sys
if sys.version_info >= (3, 12):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
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
    print(f"✅ تم تحميل {len(STUDENT_PAGES)} صفحة من كتاب الطالب")
else:
    print(f"❌ الملف {json_path} غير موجود")

# ==================== القائمة الرئيسية (أزرار دائمة) ====================
main_menu = ReplyKeyboardMarkup([
    ["📖 كتاب الطالب", "🏠 الرئيسية"]
], resize_keyboard=True)

# ==================== دوال مساعدة ====================
def get_page_buttons(page_num):
    """أزرار التنقل بين الصفحات"""
    buttons = []
    nav_buttons = []
    
    if int(page_num) > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"page_{int(page_num)-1}"))
    if int(page_num) < len(STUDENT_PAGES):
        nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"page_{int(page_num)+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)

# ==================== أوامر البوت ====================
async def start(update, context):
    await update.message.reply_text(
        f"🎓 **مرحباً بك في البوت التعليمي!**\n\n"
        f"📚 **عدد صفحات كتاب الطالب:** {len(STUDENT_PAGES)}\n\n"
        f"📖 اضغط على 'كتاب الطالب' ثم أرسل رقم الصفحة،\n"
        f"أو استخدم الأزرار التفاعلية بعد اختيار الصفحة.",
        parse_mode='Markdown',
        reply_markup=main_menu
    )

async def student_book(update, context):
    context.user_data["book"] = "student"
    await update.message.reply_text(
        f"📖 **كتاب الطالب**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"أرسل رقم الصفحة من **1** إلى **{len(STUDENT_PAGES)}**\n\n"
        f"مثال: أرسل `10` لعرض الصفحة 10",
        parse_mode='Markdown'
    )

async def show_page(update, context):
    try:
        page_num = str(int(update.message.text.strip()))
        
        if context.user_data.get("book") != "student":
            await update.message.reply_text("❌ اضغط على '📖 كتاب الطالب' أولاً")
            return
        
        if page_num in STUDENT_PAGES:
            page_data = STUDENT_PAGES[page_num]
            content = page_data["content"]
            title = page_data["title"]
            
            if len(content) > 4000:
                content = content[:4000] + "\n\n... (يوجد محتوى إضافي)"
            
            await update.message.reply_text(
                f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                parse_mode='Markdown',
                reply_markup=get_page_buttons(page_num)
            )
            context.user_data["current_page"] = page_num
        else:
            await update.message.reply_text(
                f"❌ الصفحة {page_num} غير موجودة\n"
                f"الصفحات المتوفرة: 1 إلى {len(STUDENT_PAGES)}"
            )
    except ValueError:
        await update.message.reply_text("❌ أرسل رقم صفحة صحيح (مثال: 10)")

async def back_home(update, context):
    context.user_data.clear()
    await start(update, context)

# ==================== معالج الأزرار التفاعلية ====================
async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "main_menu":
        await query.message.delete()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🎓 **مرحباً بك مجدداً!**\n\n📚 **عدد صفحات كتاب الطالب:** {len(STUDENT_PAGES)}",
            parse_mode='Markdown',
            reply_markup=main_menu
        )
        return
    
    if data.startswith("page_"):
        page_num = data.split("_")[1]
        
        if page_num in STUDENT_PAGES:
            page_data = STUDENT_PAGES[page_num]
            content = page_data["content"]
            title = page_data["title"]
            
            if len(content) > 4000:
                content = content[:4000] + "\n\n... (يوجد محتوى إضافي)"
            
            await query.edit_message_text(
                f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                parse_mode='Markdown',
                reply_markup=get_page_buttons(page_num)
            )
            context.user_data["current_page"] = page_num

# ==================== التشغيل ====================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # الأوامر النصية
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text("📖 كتاب الطالب"), student_book))
    app.add_handler(MessageHandler(filters.Text("🏠 الرئيسية"), back_home))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, show_page))
    
    # الأزرار التفاعلية
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("=" * 60)
    print(f"🔥 البوت شغال! صفحات الطالب: {len(STUDENT_PAGES)}")
    print("=" * 60)
    app.run_polling()

if __name__ == "__main__":
    main()
