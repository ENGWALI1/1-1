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
# ==================== تشخيص المسارات والملفات ====================
print("="*50)
print("📂 بدء فحص البيئة...")
print(f"📁 المسار الأساسي: {BASE_DIR}")

print("\n📦 فحص الملفات المضغوطة:")
for zip_name in ["student_pages.zip", "activity_pages.zip", "lessons.zip", "tests.zip"]:
    zip_path = os.path.join(BASE_DIR, zip_name)
    if os.path.exists(zip_path):
        print(f"  ✅ {zip_name} موجود (حجمه: {os.path.getsize(zip_path)} bytes)")
    else:
        print(f"  ❌ {zip_name} غير موجود")

print("\n📂 فحص المجلدات بعد فك الضغط:")
for folder in ["student_pages", "activity_pages", "lessons", "tests"]:
    folder_path = os.path.join(BASE_DIR, folder)
    if os.path.exists(folder_path):
        files = os.listdir(folder_path)
        print(f"  ✅ مجلد {folder} موجود (عدد الملفات: {len(files)})")
        if files:
            print(f"     - أول 3 ملفات: {files[:3]}")
    else:
        print(f"  ❌ مجلد {folder} غير موجود")
print("="*50)
# ==================== فك ضغط الملفات ====================
print("📦 جاري فك ضغط الملفات...")
for zip_name in ["student_pages.zip", "activity_pages.zip"]:
    zip_path = os.path.join(BASE_DIR, zip_name)
    extract_to = os.path.join(BASE_DIR, zip_name.replace(".zip", ""))
    if os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_to)
        print(f"✅ تم فك {zip_name}")

# ==================== تحميل صفحات كتاب الطالب ====================
STUDENT_PAGES = {}
student_folder = os.path.join(BASE_DIR, "student_pages")
if os.path.exists(student_folder):
    for filename in os.listdir(student_folder):
        if filename.endswith(".json"):
            try:
                filepath = os.path.join(student_folder, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    page_num = filename.replace("page_", "").replace(".json", "")
                    # تخزين المحتوى النصي فقط
                    content = data.get("content_original", data.get("content", str(data)))
                    STUDENT_PAGES[page_num] = content
                    print(f"✅ صفحة {page_num}")
            except Exception as e:
                print(f"⚠️ خطأ في {filename}: {e}")
    print(f"✅ تم تحميل {len(STUDENT_PAGES)} صفحة من كتاب الطالب")

# ==================== القائمة ====================
menu = ReplyKeyboardMarkup([
    ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
    ["🏠 الرئيسية"]
], resize_keyboard=True)

# ==================== أوامر البوت ====================
async def start(update, context):
    await update.message.reply_text(
        f"🎓 مرحباً بك!\n📚 عدد صفحات الطالب المتوفرة: {len(STUDENT_PAGES)}\n\nاختر من القائمة:",
        reply_markup=menu
    )

async def student_book(update, context):
    context.user_data["book"] = "student"
    await update.message.reply_text("📖 أرسل رقم الصفحة (مثال: 10)")

async def activity_book(update, context):
    await update.message.reply_text("✏️ كتاب الأنشطة - سيتم إضافته قريباً")

async def show_page(update, context):
    try:
        page = str(int(update.message.text.strip()))
        if context.user_data.get("book") == "student":
            if page in STUDENT_PAGES:
                content = STUDENT_PAGES[page]
                # تقسيم النص الطويل
                if len(content) > 4000:
                    content = content[:4000] + "\n\n... (يوجد محتوى إضافي)"
                await update.message.reply_text(f"📖 صفحة {page}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}")
            else:
                await update.message.reply_text(f"❌ الصفحة {page} غير موجودة\nالصفحات المتوفرة: {sorted([int(p) for p in STUDENT_PAGES.keys()])[:20]}")
        else:
            await update.message.reply_text("❌ اختر كتاب الطالب أولاً من القائمة")
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
    app.add_handler(MessageHandler(filters.Text("✏️ كتاب الأنشطة"), activity_book))
    app.add_handler(MessageHandler(filters.Text("🏠 الرئيسية"), back_home))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, show_page))
    
    print("=" * 60)
    print(f"🔥 البوت شغال! عدد صفحات الطالب: {len(STUDENT_PAGES)}")
    print("=" * 60)
    app.run_polling()

if __name__ == "__main__":
    main()
