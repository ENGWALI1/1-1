import os
import json
import zipfile
import shutil
import re
import asyncio
import edge_tts
from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"

# تخزين حالة المستخدمين
user_book_choice = {}

# سرعات الصوت
VOICE_RATES = {"بطيء": "-30%", "عادي": "-15%", "سريع": "+1%"}

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

# ==================== دالة تحويل النص إلى صوت (نسخة asyncio) ====================
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
            {"text": "🔊 الصوت", "callback_data": f"audio_speed_{prefix}_{page_num}"},
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

def get_audio_speed_buttons(book_type, page_num):
    prefix = "student" if book_type == "student" else "activity"
    return {
        "inline_keyboard": [
            [
                {"text": "🐢 بطيء", "callback_data": f"audio_{prefix}_{page_num}_بطيء"},
                {"text": "🐕 عادي", "callback_data": f"audio_{prefix}_{page_num}_عادي"},
                {"text": "🐇 سريع", "callback_data": f"audio_{prefix}_{page_num}_سريع"}
            ],
            [{"text": "🔙 رجوع", "callback_data": f"{prefix}_original_{page_num}"}]
        ]
    }

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
        
        # قائمة اختيار سرعة الصوت
        if cb_data.startswith("audio_"):
    parts = cb_data.split("_")
    prefix = parts[1]
    page_num = parts[2]
    
    # إشعار
    requests.post(URL + '/sendMessage', json={
        "chat_id": chat_id,
        "text": "🎵 جاري تجهيز الصوت، انتظر قليلاً..."
    })
    
    pages = STUDENT_PAGES if prefix == "student" else ACTIVITY_PAGES
    if page_num in pages:
        text = pages[page_num].get("content_original", "")
        audio_path = text_to_audio(text, prefix, page_num)
        
        if audio_path and os.path.exists(audio_path):
            with open(audio_path, 'rb') as audio:
                files = {'voice': audio}
                requests.post(URL + '/sendVoice', files=files, data={"chat_id": chat_id})
        else:
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "❌ عذراً، حدث خطأ في إنشاء الصوت"
            })
    return 'OK'
        
        if cb_data == "main_menu":
            keyboard = {"keyboard": [["📖 كتاب الطالب", "✏️ كتاب الأنشطة"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً!\n📖 طالب: {len(STUDENT_PAGES)}\n✏️ أنشطة: {len(ACTIVITY_PAGES)}\nاختر الكتاب 👇",
                "reply_markup": keyboard
            })
            requests.post(URL + '/deleteMessage', json={"chat_id": chat_id, "message_id": msg_id})
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
        
        if text == '/start':
            keyboard = {"keyboard": [["📖 كتاب الطالب", "✏️ كتاب الأنشطة"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً!\n📖 طالب: {len(STUDENT_PAGES)}\n✏️ أنشطة: {len(ACTIVITY_PAGES)}\nاختر الكتاب 👇",
                "reply_markup": keyboard
            })
            user_book_choice.pop(user_id, None)
        
        elif text == "📖 كتاب الطالب":
            user_book_choice[user_id] = "student"
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"📖 أرسل رقم الصفحة ({STUDENT_MIN}-{STUDENT_MAX}):"
            })
        
        elif text == "✏️ كتاب الأنشطة":
            user_book_choice[user_id] = "activity"
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"✏️ أرسل رقم الصفحة ({ACTIVITY_MIN}-{ACTIVITY_MAX}):"
            })
        
        elif text.isdigit():
            page_num = text
            selected_book = user_book_choice.get(user_id)
            
            if selected_book == "student":
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
                else:
                    requests.post(URL + '/sendMessage', json={
                        "chat_id": chat_id,
                        "text": f"❌ الصفحة {page_num} غير موجودة في كتاب الطالب\n📚 الصفحات المتوفرة: {student_list}"
                    })
            
            elif selected_book == "activity":
                if page_num in ACTIVITY_PAGES:
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
                        "text": f"❌ الصفحة {page_num} غير موجودة في كتاب الأنشطة\n📚 الصفحات المتوفرة: {activity_list}"
                    })
            
            else:
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": "❌ اختر كتاباً أولاً (📖 كتاب الطالب أو ✏️ كتاب الأنشطة)"
                })
        
        else:
            keyboard = {"keyboard": [["📖 كتاب الطالب", "✏️ كتاب الأنشطة"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "اضغط على أحد الكتابين 👇",
                "reply_markup": keyboard
            })
    
    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
