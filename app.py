import os
import json
import zipfile
import shutil
from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"
HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')

# ==================== فك ضغط وقراءة صفحات الطالب ====================
def load_student_pages():
    pages = {}
    zip_path = "student_pages.zip"
    extract_dir = "student_pages_temp"

    if not os.path.exists(zip_path):
        print(f"❌ {zip_path} غير موجود")
        return pages

    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)

    print(f"📦 فك ضغط {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)

    for root, _, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".json"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # استخراج رقم الصفحة (قد يكون داخل الملف أو من اسمه)
                        page_num = None
                        if isinstance(data, dict):
                            # البحث عن مفتاح رقمي في الملف
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
                        print(f"✅ صفحة {page_num}")
                except Exception as e:
                    print(f"⚠️ خطأ في {file}: {e}")

    shutil.rmtree(extract_dir)
    return pages

STUDENT_PAGES = load_student_pages()
pages_list = sorted([int(p) for p in STUDENT_PAGES.keys()])
MIN_PAGE = min(pages_list) if pages_list else 1
MAX_PAGE = max(pages_list) if pages_list else 80
print(f"✅ تم تحميل {len(STUDENT_PAGES)} صفحة (من {MIN_PAGE} إلى {MAX_PAGE})")

# ==================== دوال عرض المحتوى ====================
def format_original(content):
    """عرض النص الأصلي"""
    if not content:
        return "لا يوجد محتوى نصي في هذه الصفحة"
    return content

def format_translation(lines):
    """عرض الترجمة سطراً بسطر"""
    if not lines:
        return "لا توجد ترجمة لهذه الصفحة"
    result = ""
    for item in lines:
        en = item.get('en', '')
        ar = item.get('ar', '')
        result += f"📖 **{en}**\n🌐 {ar}\n\n"
    return result

def format_exercises(exercises):
    """عرض حلول التمارين"""
    if not exercises:
        return "لا توجد تمارين في هذه الصفحة"
    result = "📝 **حلول التمارين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, ex in enumerate(exercises, 1):
        text = ex.get('text', f'سؤال {i}')
        answer = ex.get('answer', '---')
        result += f"**{i}. {text}**\n✅ {answer}\n\n"
    return result

def get_page_buttons(page_num, mode):
    """أزرار التنقل والترجمة وحل التمارين"""
    buttons = []
    
    # أزرار التنقل
    nav = []
    if int(page_num) > MIN_PAGE:
        nav.append({"text": "◀️ السابق", "callback_data": f"page_{int(page_num)-1}"})
    if int(page_num) < MAX_PAGE:
        nav.append({"text": "التالي ▶️", "callback_data": f"page_{int(page_num)+1}"})
    if nav:
        buttons.append(nav)
    
    # أزرار الترجمة وحل التمارين (حسب الوضع الحالي)
    if mode == 'original':
        buttons.append([
            {"text": "🌐 الترجمة", "callback_data": f"translated_{page_num}"},
            {"text": "📝 حل التمارين", "callback_data": f"solved_{page_num}"}
        ])
    elif mode == 'translated':
        buttons.append([
            {"text": "🔤 النص الأصلي", "callback_data": f"original_{page_num}"},
            {"text": "📝 حل التمارين", "callback_data": f"solved_{page_num}"}
        ])
    else:  # solved
        buttons.append([
            {"text": "🔤 النص الأصلي", "callback_data": f"original_{page_num}"},
            {"text": "🌐 الترجمة", "callback_data": f"translated_{page_num}"}
        ])
    
    buttons.append([{"text": "🏠 القائمة الرئيسية", "callback_data": "main_menu"}])
    return {"inline_keyboard": buttons}

# ==================== إعداد الـ Webhook ====================
@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>{len(STUDENT_PAGES)} صفحة ({MIN_PAGE} إلى {MAX_PAGE})</p>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or ('message' not in data and 'callback_query' not in data):
        return 'OK'

    # معالجة الأزرار (callback_query)
    if 'callback_query' in data:
        callback = data['callback_query']
        chat_id = callback['message']['chat']['id']
        msg_id = callback['message']['message_id']
        cb_data = callback['data']
        
        print(f"🔘 {cb_data}")
        
        if cb_data == "main_menu":
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً بك!\n📚 الصفحات المتوفرة: {MIN_PAGE} إلى {MAX_PAGE}\nاضغط الزر 👇",
                "reply_markup": keyboard
            })
            requests.post(URL + '/deleteMessage', json={
                "chat_id": chat_id,
                "message_id": msg_id
            })
            return 'OK'
        
        # معالجة أزرار الترجمة وحل التمارين والتنقل
        parts = cb_data.split("_")
        
        if parts[0] == 'original':
            page_num = parts[1]
            page = STUDENT_PAGES.get(page_num)
            if page:
                title = page.get("title", f"صفحة {page_num}")
                content = format_original(page.get("content_original", ""))
                requests.post(URL + '/editMessageText', json={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons(page_num, 'original'),
                    "parse_mode": "Markdown"
                })
        
        elif parts[0] == 'translated':
            page_num = parts[1]
            page = STUDENT_PAGES.get(page_num)
            if page:
                title = page.get("title", f"صفحة {page_num}")
                content = format_translation(page.get("content_line_by_line", []))
                requests.post(URL + '/editMessageText', json={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": f"📖 **{title} - الترجمة**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons(page_num, 'translated'),
                    "parse_mode": "Markdown"
                })
        
        elif parts[0] == 'solved':
            page_num = parts[1]
            page = STUDENT_PAGES.get(page_num)
            if page:
                title = page.get("title", f"صفحة {page_num}")
                content = format_exercises(page.get("exercises", []))
                requests.post(URL + '/editMessageText', json={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": f"📖 **{title} - حلول التمارين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons(page_num, 'solved'),
                    "parse_mode": "Markdown"
                })
        
        elif parts[0] == 'page':
            page_num = parts[1]
            page = STUDENT_PAGES.get(page_num)
            if page:
                title = page.get("title", f"صفحة {page_num}")
                content = format_original(page.get("content_original", ""))
                requests.post(URL + '/editMessageText', json={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons(page_num, 'original'),
                    "parse_mode": "Markdown"
                })
        
        return 'OK'

    # معالجة الرسائل النصية
    if 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')
        print(f"📨 {text}")
        
        if text == '/start':
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً بك!\n📚 الصفحات المتوفرة: {MIN_PAGE} إلى {MAX_PAGE}\nاضغط الزر 👇",
                "reply_markup": keyboard
            })
        
        elif text == "📖 كتاب الطالب":
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"📄 أرسل رقم الصفحة ({MIN_PAGE}-{MAX_PAGE}):"
            })
        
        elif text.isdigit():
            page_num = text
            if int(page_num) in pages_list:
                page = STUDENT_PAGES.get(page_num)
                if page:
                    title = page.get("title", f"صفحة {page_num}")
                    content = format_original(page.get("content_original", ""))
                    requests.post(URL + '/sendMessage', json={
                        "chat_id": chat_id,
                        "text": f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                        "reply_markup": get_page_buttons(page_num, 'original'),
                        "parse_mode": "Markdown"
                    })
            else:
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": f"❌ الصفحة {page_num} غير موجودة\n📚 الصفحات المتوفرة: {pages_list}"
                })
        
        else:
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "اضغط على 📖 كتاب الطالب لبدء القراءة",
                "reply_markup": keyboard
            })
    
    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
