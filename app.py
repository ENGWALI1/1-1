import os
import json
import zipfile
import shutil
import re
import asyncio
import edge_tts
from flask import Flask, request
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"
ADMIN_ID = 1662780469

# ==================== القوائم ====================
unsubscribed_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "💳 اشتراك", "🛠️ الدعم الفني", "🏠 الرئيسية"]
    ],
    "resize_keyboard": True
}

subscribed_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "🛠️ الدعم الفني", "🏠 الرئيسية"]
    ],
    "resize_keyboard": True
}

admin_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "💳 اشتراك"],
        ["📋 طلبات الاشتراك", "👥 المشتركين"],
        ["🛠️ الدعم الفني", "🏠 الرئيسية"]
    ],
    "resize_keyboard": True
}

# ==================== نظام الاشتراك ====================
def load_subs():
    subs_path = "subs.json"
    if os.path.exists(subs_path):
        with open(subs_path, 'r') as f:
            return json.load(f)
    return {}

def save_subs(data):
    with open("subs.json", 'w') as f:
        json.dump(data, f, indent=2)

def is_subscribed(user_id):
    subs = load_subs()
    expiry = subs.get(str(user_id))
    if expiry and datetime.now().isoformat() < expiry:
        return True
    return False

def get_user_menu(user_id):
    if user_id == ADMIN_ID:
        return admin_menu
    elif is_subscribed(user_id):
        return subscribed_menu
    else:
        return unsubscribed_menu

# ==================== فك ضغط وقراءة صفحات الكتاب ====================
def load_pages_from_zip(zip_path):
    pages = {}
    extract_dir = zip_path.replace(".zip", "")
    
    if not os.path.exists(zip_path):
        print(f"❌ {zip_path} غير موجود")
        return pages
    
    if not os.path.exists(extract_dir):
        print(f"📦 فك ضغط {zip_path}...")
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
        print(f"✅ تم فك الضغط")
    else:
        print(f"✅ المجلد {extract_dir} موجود مسبقاً")
    
    for root, _, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".json"):
                if file == "index.json":
                    continue
                
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        if content.count('{') > 1 and content.count('}') > 1:
                            match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', content, re.DOTALL)
                            if match:
                                content = match.group(1)
                        
                        data = json.loads(content)
                        
                        if not isinstance(data, dict):
                            continue
                        
                        page_num = None
                        for key in data.keys():
                            if str(key).isdigit():
                                page_num = str(key)
                                data = data[key]
                                break
                        
                        if not page_num:
                            page_num = file.replace("page_", "").replace(".json", "")
                        
                        pages[page_num] = {
                            "title": data.get("title", f"صفحة {page_num}"),
                            "content_original": data.get("content_original", ""),
                            "content_line_by_line": data.get("content_line_by_line", []),
                            "exercises": data.get("exercises", [])
                        }
                        print(f"  ✅ صفحة {page_num}")
                except Exception as e:
                    print(f"  ⚠️ خطأ في {file}: {e}")
    
    return pages

# تحميل الكتابين
print("📚 تحميل كتاب الطالب...")
STUDENT_PAGES = load_pages_from_zip("student_pages.zip")

print("📚 تحميل كتاب الأنشطة...")
ACTIVITY_PAGES = load_pages_from_zip("activity_pages.zip")

student_list = sorted([int(p) for p in STUDENT_PAGES.keys()])
activity_list = sorted([int(p) for p in ACTIVITY_PAGES.keys()])

STUDENT_MIN = min(student_list) if student_list else 1
STUDENT_MAX = max(student_list) if student_list else 80
ACTIVITY_MIN = min(activity_list) if activity_list else 1
ACTIVITY_MAX = max(activity_list) if activity_list else 64

print(f"✅ كتاب الطالب: {len(STUDENT_PAGES)} صفحة ({STUDENT_MIN} إلى {STUDENT_MAX})")
print(f"✅ كتاب الأنشطة: {len(ACTIVITY_PAGES)} صفحة ({ACTIVITY_MIN} إلى {ACTIVITY_MAX})")

# ==================== دالة تحويل النص إلى صوت (edge-tts) ====================
def text_to_audio(text, book_type, page_num):
    """تحويل النص إلى صوت باستخدام edge-tts (يدعم النصوص الطويلة)"""
    audio_dir = "audio"
    os.makedirs(audio_dir, exist_ok=True)
    
    # تنظيف النص واستخراج الإنجليزي
    clean_text = text.replace('*', '').replace('_', '').replace('`', '')
    clean_text = clean_text.replace('━', '').replace('**', '').replace('|', '')
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    lines = clean_text.split('\n')
    english_parts = []
    for line in lines:
        arabic_chars = sum(1 for c in line if '\u0600' <= c <= '\u06FF')
        total_chars = len(line.strip())
        if total_chars > 0:
            arabic_ratio = arabic_chars / total_chars
            if arabic_ratio < 0.5:
                english_parts.append(line)
    
    clean_text = ' '.join(english_parts)
    
    if not clean_text or len(clean_text.strip()) < 10:
        clean_text = f"Page {page_num} of {book_type} book."
    
    audio_filename = f"{book_type}_{page_num}.mp3"
    audio_path = os.path.join(audio_dir, audio_filename)
    
    if os.path.exists(audio_path):
        return audio_path
    
    async def _generate_audio():
        try:
            communicate = edge_tts.Communicate(clean_text[:3000], "en-US-JennyNeural")
            await communicate.save(audio_path)
            return audio_path
        except Exception as e:
            print(f"خطأ في edge-tts: {e}")
            return None
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_generate_audio())
        loop.close()
        return result
    except Exception as e:
        print(f"خطأ في تشغيل asyncio: {e}")
        return None

# ==================== دوال عرض المحتوى ====================
def format_original(content):
    if not content:
        return "لا يوجد محتوى نصي"
    
    content = content.replace("---", "\n━━━━━━━━━━━━━━━━━━━━━━━━\n")
    content = content.replace("Grammar", "\n📚 **Grammar**\n")
    content = content.replace("Listening", "\n🎧 **Listening**\n")
    content = content.replace("Speaking", "\n💬 **Speaking**\n")
    content = content.replace("Reading", "\n📖 **Reading**\n")
    content = content.replace("Writing", "\n✏️ **Writing**\n")
    content = content.replace("Vocabulary", "\n📝 **Vocabulary**\n")
    content = content.replace("Pronunciation", "\n🔊 **Pronunciation**\n")
    content = content.replace("Unit plan", "\n📋 **Unit plan**\n")
    content = content.replace("Keep in mind", "\n💡 **Keep in mind**\n")
    
    lines = content.split('\n')
    result = []
    for line in lines:
        if line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
            result.append("")
            result.append(line)
        elif line.strip().startswith(('A.', 'B.', 'C.', 'D.')):
            result.append("")
            result.append(line)
        elif line.strip().startswith(('a.', 'b.', 'c.', 'd.')):
            result.append(f"   {line}")
        else:
            result.append(line)
    
    content = '\n'.join(result)
    
    if len(content) > 4000:
        content = content[:4000] + "\n\n... (يوجد محتوى إضافي تم اختصاره)"
    
    return content

def format_translation(lines):
    if not lines:
        return "لا توجد ترجمة"
    result = ""
    for item in lines:
        result += f"📖 **{item.get('en', '')}**\n🌐 {item.get('ar', '')}\n\n"
    return result

def format_exercises(exercises):
    if not exercises:
        return "لا توجد تمارين في هذه الصفحة"
    
    result = "📝 **حلول التمارين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, ex in enumerate(exercises, 1):
        ex_type = ex.get('type', '')
        
        if ex_type == 'speaking':
            questions = ex.get('questions', [])
            answers = ex.get('answers', [])
            result += f"**🗣️ نشاط المحادثة {i}:**\n"
            for j, q in enumerate(questions):
                result += f"**سؤال {j+1}:** {q}\n"
                if j < len(answers):
                    result += f"✅ **نموذج للإجابة:** {answers[j]}\n"
                result += "\n"
        else:
            text = ex.get('text', ex.get('question', f'سؤال {i}'))
            answer = ex.get('answer', '---')
            result += f"**{i}. {text}**\n✅ {answer}\n\n"
    
    return result

def get_page_buttons(book_type, page_num, mode, min_page, max_page):
    buttons = []
    prefix = "student" if book_type == "student" else "activity"
    
    nav = []
    if int(page_num) > min_page:
        nav.append({"text": "◀️ السابق", "callback_data": f"{prefix}_page_{int(page_num)-1}"})
    if int(page_num) < max_page:
        nav.append({"text": "التالي ▶️", "callback_data": f"{prefix}_page_{int(page_num)+1}"})
    if nav:
        buttons.append(nav)
    
    if mode == 'original':
        buttons.append([
            {"text": "🌐 الترجمة", "callback_data": f"{prefix}_translated_{page_num}"},
            {"text": "🔊 الصوت", "callback_data": f"audio_{prefix}_{page_num}"},
            {"text": "📝 حل التمارين", "callback_data": f"{prefix}_solved_{page_num}"}
        ])
    elif mode == 'translated':
        buttons.append([
            {"text": "🔤 النص الأصلي", "callback_data": f"{prefix}_original_{page_num}"},
            {"text": "📝 حل التمارين", "callback_data": f"{prefix}_solved_{page_num}"}
        ])
    else:
        buttons.append([
            {"text": "🔤 النص الأصلي", "callback_data": f"{prefix}_original_{page_num}"},
            {"text": "🌐 الترجمة", "callback_data": f"{prefix}_translated_{page_num}"}
        ])
    
    buttons.append([{"text": "🏠 القائمة الرئيسية", "callback_data": "main_menu"}])
    return {"inline_keyboard": buttons}

# ==================== أوامر البوت ====================
async def subscription_menu(update, context):
    await update.message.reply_text(
        "💳 **نظام الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1 شهر = 50 ل.س\n\n"
        "للاستفادة من:\n"
        "✓ الوصول الكامل إلى جميع الكتب\n"
        "✓ الترجمة الكاملة\n"
        "✓ حلول التمارين النموذجية\n"
        "✓ الوصول إلى جميع الاختبارات\n"
        "✓ خاصية الصوت\n\n"
        "📞 أرسل المبلغ إلى سيريتل كاش: 15570270\n"
        "ثم أرسل /activate لتفعيل اشتراكك",
        parse_mode='Markdown'
    )

async def contact_teacher(update, context):
    keyboard = {"inline_keyboard": [[{"text": "🛠️ الدعم الفني", "url": "https://t.me/ENGWALI1"}]]}
    await update.message.reply_text(
        "🛠️ **الدعم الفني**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "اضغط على الزر أدناه للتواصل مع الدعم الفني.",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

async def show_pending_requests(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر للمسؤول فقط.")
        return
    # TODO: إضافة منطق طلبات الاشتراك
    await update.message.reply_text("📋 قائمة طلبات الاشتراك المعلقة (قيد التطوير)")

async def show_active_subscriptions(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر للمسؤول فقط.")
        return
    subs = load_subs()
    if not subs:
        await update.message.reply_text("📭 لا يوجد مشتركين حالياً.")
        return
    text = "👥 **المشتركين الحاليين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for uid, expiry in subs.items():
        expiry_date = expiry[:10] if expiry else "غير محدد"
        text += f"🆔 `{uid}`\n📅 ينتهي: {expiry_date}\n\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def activate_command(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("للمسؤول فقط.")
        return
    try:
        if not context.args:
            await update.message.reply_text("الاستخدام: /activate USER_ID:1_month")
            return
        text = " ".join(context.args)
        user_id_str, plan = text.split(":")
        if plan != "1_month":
            await update.message.reply_text("❌ باقة خاطئة. اختر: 1_month")
            return
        user_id = int(user_id_str)
        expiry = (datetime.now() + timedelta(days=30)).isoformat()
        subs = load_subs()
        subs[str(user_id)] = expiry
        save_subs(subs)
        await update.message.reply_text(f"✅ تم تفعيل المستخدم {user_id} لمدة 30 يوماً.")
        await context.bot.send_message(chat_id=user_id, text="🎉 تم تفعيل اشتراكك بنجاح!")
    except:
        await update.message.reply_text("❌ خطأ. استخدم: /activate USER_ID:1_month")

# ==================== إعداد الـ Webhook ====================
@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>📖 طالب: {len(STUDENT_PAGES)} | ✏️ أنشطة: {len(ACTIVITY_PAGES)}</p>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or ('message' not in data and 'callback_query' not in data):
        return 'OK'

    # معالجة الأزرار
    if 'callback_query' in data:
        callback = data['callback_query']
        chat_id = callback['message']['chat']['id']
        msg_id = callback['message']['message_id']
        cb_data = callback['data']
        
        if cb_data == "main_menu":
            keyboard = get_user_menu(chat_id)
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً!\n📖 طالب: {len(STUDENT_PAGES)}\n✏️ أنشطة: {len(ACTIVITY_PAGES)}\nاختر من القائمة 👇",
                "reply_markup": keyboard
            })
            requests.post(URL + '/deleteMessage', json={"chat_id": chat_id, "message_id": msg_id})
            return 'OK'
        
        if cb_data.startswith("audio_"):
            parts = cb_data.split("_")
            prefix = parts[1]
            page_num = parts[2]
            
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "🎵 جاري تجهيز الصوت..."
            })
            
            pages = STUDENT_PAGES if prefix == "student" else ACTIVITY_PAGES
            if page_num in pages:
                text = pages[page_num].get("content_original", "")
                audio_path = text_to_audio(text, prefix, page_num)
                
                if audio_path and os.path.exists(audio_path):
                    with open(audio_path, 'rb') as audio:
                        requests.post(URL + '/sendVoice', files={'voice': audio}, data={"chat_id": chat_id})
                else:
                    requests.post(URL + '/sendMessage', json={
                        "chat_id": chat_id,
                        "text": "❌ عذراً، حدث خطأ في إنشاء الصوت"
                    })
            return 'OK'
        
        parts = cb_data.split("_")
        if len(parts) < 3:
            return 'OK'
        
        book_type = "student" if parts[0] == "student" else "activity"
        action = parts[1]
        page_num = parts[2]
        
        pages = STUDENT_PAGES if book_type == "student" else ACTIVITY_PAGES
        min_page = STUDENT_MIN if book_type == "student" else ACTIVITY_MIN
        max_page = STUDENT_MAX if book_type == "student" else ACTIVITY_MAX
        
        if page_num not in pages:
            return 'OK'
        
        page = pages[page_num]
        title = page.get("title", f"صفحة {page_num}")
        
        if action == "original" or (action == "page" and len(parts) == 3):
            content = format_original(page.get("content_original", ""))
            mode = 'original'
        elif action == "translated":
            content = format_translation(page.get("content_line_by_line", []))
            mode = 'translated'
        elif action == "solved":
            content = format_exercises(page.get("exercises", []))
            mode = 'solved'
        else:
            content = format_original(page.get("content_original", ""))
            mode = 'original'
        
        requests.post(URL + '/editMessageText', json={
            "chat_id": chat_id,
            "message_id": msg_id,
            "text": f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
            "reply_markup": get_page_buttons(book_type, page_num, mode, min_page, max_page),
            "parse_mode": "Markdown"
        })
        return 'OK'

    # معالجة الرسائل النصية
    if 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')
        user_id = data['message']['from']['id']
        
        if text == '/start' or text == "🏠 الرئيسية":
            keyboard = get_user_menu(user_id)
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً بك!\n📖 طالب: {len(STUDENT_PAGES)}\n✏️ أنشطة: {len(ACTIVITY_PAGES)}\nاختر من القائمة 👇",
                "reply_markup": keyboard
            })
        
        elif text == "📖 كتاب الطالب":
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"📖 أرسل رقم الصفحة ({STUDENT_MIN}-{STUDENT_MAX}):"
            })
        
        elif text == "✏️ كتاب الأنشطة":
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"✏️ أرسل رقم الصفحة ({ACTIVITY_MIN}-{ACTIVITY_MAX}):"
            })
        
        elif text == "📚 القواعد":
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "📚 قائمة القواعد (قيد التطوير)"
            })
        
        elif text == "💳 اشتراك":
            keyboard = get_user_menu(user_id)
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "💳 **نظام الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━━━\n1 شهر = 50 ل.س\n\nللاستفادة من:\n✓ الوصول الكامل إلى جميع الكتب\n✓ الترجمة الكاملة\n✓ حلول التمارين النموذجية\n✓ الوصول إلى جميع الاختبارات\n✓ خاصية الصوت\n\n📞 أرسل المبلغ إلى سيريتل كاش: 15570270\nثم أرسل /activate لتفعيل اشتراكك",
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            })
        
        elif text == "🛠️ الدعم الفني":
            keyboard = {"inline_keyboard": [[{"text": "🛠️ الدعم الفني", "url": "https://t.me/ENGWALI1"}]]}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "🛠️ اضغط على الزر أدناه للتواصل مع الدعم الفني:",
                "reply_markup": keyboard
            })
        
        elif text == "📋 طلبات الاشتراك":
            if user_id == ADMIN_ID:
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": "📋 قائمة طلبات الاشتراك (قيد التطوير)"
                })
            else:
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": "❌ هذا الأمر للمسؤول فقط."
                })
        
        elif text == "👥 المشتركين":
            if user_id == ADMIN_ID:
                subs = load_subs()
                if not subs:
                    requests.post(URL + '/sendMessage', json={
                        "chat_id": chat_id,
                        "text": "📭 لا يوجد مشتركين حالياً."
                    })
                else:
                    result = "👥 **المشتركين الحاليين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    for uid, expiry in subs.items():
                        expiry_date = expiry[:10] if expiry else "غير محدد"
                        result += f"🆔 `{uid}`\n📅 ينتهي: {expiry_date}\n\n"
                    requests.post(URL + '/sendMessage', json={
                        "chat_id": chat_id,
                        "text": result,
                        "parse_mode": "Markdown"
                    })
            else:
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": "❌ هذا الأمر للمسؤول فقط."
                })
        
        elif text.isdigit():
            page_num = text
            if page_num in STUDENT_PAGES:
                page = STUDENT_PAGES[page_num]
                title = page.get("title", f"صفحة {page_num}")
                content = format_original(page.get("content_original", ""))
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons("student", page_num, 'original', STUDENT_MIN, STUDENT_MAX),
                    "parse_mode": "Markdown"
                })
            elif page_num in ACTIVITY_PAGES:
                page = ACTIVITY_PAGES[page_num]
                title = page.get("title", f"صفحة {page_num}")
                content = format_original(page.get("content_original", ""))
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": f"✏️ **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons("activity", page_num, 'original', ACTIVITY_MIN, ACTIVITY_MAX),
                    "parse_mode": "Markdown"
                })
            else:
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": f"❌ الصفحة {page_num} غير موجودة"
                })
        
        else:
            keyboard = get_user_menu(user_id)
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "اختر من القائمة 👇",
                "reply_markup": keyboard
            })
    
    return 'OK'

if __name__ == '__main__':
    # إنشاء ملف subs.json إذا لم يكن موجوداً
    if not os.path.exists("subs.json"):
        with open("subs.json", 'w') as f:
            json.dump({}, f)
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
