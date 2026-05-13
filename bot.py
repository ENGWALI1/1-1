import os
import json
import zipfile
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

# ==================== فك ضغط الملفات ====================
def extract_zip(zip_name):
    zip_path = os.path.join(BASE_DIR, zip_name)
    extract_to = os.path.join(BASE_DIR, zip_name.replace(".zip", ""))
    
    if os.path.exists(zip_path):
        print(f"📦 جاري فك {zip_name}...")
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_to)
        print(f"✅ تم فك {zip_name}")
        return True
    return False

extract_zip("student_pages.zip")

# ==================== البحث عن الملفات (حتى لو كانت داخل مجلد فرعي) ====================
def find_json_files(folder_path):
    """يبحث عن جميع ملفات JSON في المجلد وأي مجلدات فرعية"""
    json_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".json"):
                json_files.append(os.path.join(root, file))
    return json_files

# ==================== تحميل صفحات كتاب الطالب ====================
STUDENT_PAGES = {}
student_folder = os.path.join(BASE_DIR, "student_pages")

if os.path.exists(student_folder):
    print(f"📂 البحث عن JSON في: {student_folder}")
    json_files = find_json_files(student_folder)
    print(f"📄 عدد ملفات JSON التي تم العثور عليها: {len(json_files)}")
    
    for filepath in json_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                filename = os.path.basename(filepath)
                page_num = filename.replace(".json", "").replace("page_", "")
                
                if isinstance(data, dict):
                    content = data.get("content_original", data.get("content", str(data)))
                else:
                    content = str(data)
                STUDENT_PAGES[page_num] = content
                print(f"  ✅ صفحة {page_num} من {filename}")
        except Exception as e:
            print(f"  ⚠️ خطأ في {filepath}: {e}")
    
    print(f"✅ تم تحميل {len(STUDENT_PAGES)} صفحة من كتاب الطالب")
else:
    print(f"❌ مجلد {student_folder} غير موجود")

# ==================== القائمة ====================
menu = ReplyKeyboardMarkup([
    ["📖 كتاب الطالب"],
    ["🏠 الرئيسية"]
], resize_keyboard=True)

# ==================== أوامر البوت ====================
async def start(update, context):
    await update.message.reply_text(
        f"🎓 مرحباً!\n📚 صفحات الطالب المتوفرة: {len(STUDENT_PAGES)}\n\nاختر من القائمة:",
        reply_markup=menu
    )

async def student_book(update, context):
    context.user_data["book"] = "student"
    await update.message.reply_text("📖 أرسل رقم الصفحة")

async def show_page(update, context):
    try:
        page = str(int(update.message.text.strip()))
        if context.user_data.get("book") == "student":
            if page in STUDENT_PAGES:
                content = STUDENT_PAGES[page]
                if len(content) > 4000:
                    content = content[:4000] + "\n\n... (يوجد محتوى إضافي)"
                await update.message.reply_text(f"📖 صفحة {page}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}")
            else:
                pages_list = sorted([int(p) for p in STUDENT_PAGES.keys()])
                await update.message.reply_text(f"❌ الصفحة {page} غير موجودة\nالصفحات المتوفرة: {pages_list[:20]}")
        else:
            await update.message.reply_text("❌ اختر كتاب الطالب أولاً")
    except ValueError:
        await update.message.reply_text("❌ أرسل رقم صفحة صحيح")

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
