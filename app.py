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
                        page_num = file.replace("page_", "").replace(".json", "")
                        if not page_num.isdigit() and isinstance(data, dict):
                            for k in data.keys():
                                if str(k).isdigit():
                                    page_num = str(k)
                                    data = data[k]
                                    break
                        pages[page_num] = {
                            "title": data.get("title", f"صفحة {page_num}"),
                            "content_original": data.get("content_original", data.get("content", "")),
                            "translation": data.get("translation", ""),
                            "content_line_by_line": data.get("content_line_by_line", []),
                            "exercises": data.get("exercises", [])
                        }
                except Exception as e:
                    print(f"⚠️ خطأ في {file}: {e}")

    shutil.rmtree(extract_dir)
    return pages

STUDENT_PAGES = load_student_pages()
print(f"✅ تم تحميل {len(STUDENT_PAGES)} صفحة من كتاب الطالب")

# ==================== دوال التنسيق (مثل الكود القديم) ====================
def get_page_content(page_num, mode, user_id):
    page = STUDENT_PAGES.get(str(page_num))
    if not page:
        return None, None

    if mode == "original":
        content = page.get("content_original", "لا يوجد محتوى")
    elif mode == "translated":
        lines = page.get("content_line_by_line", [])
        if lines:
            content = "\n".join([f"📖 **{item['en']}**\n🌐 {item['ar']}" for item in lines])
        else:
            content = page.get("translation", "⚠️ لا توجد ترجمة")
    else:  # solved
        exercises = page.get("exercises", [])
        if exercises:
            lines = ["📝 **حلول التمارين**", "━━━━━━━━━━━━━━━━━━━━━━━━", ""]
            for i, ex in enumerate(exercises, 1):
                text = ex.get("text", ex.get("question", "سؤال"))
                answer = ex.get("answer", "---")
                lines.append(f"**{i}. {text}**\n✅ {answer}\n")
            content = "\n".join(lines)
        else:
            content = "📝 لا توجد تمارين في هذه الصفحة"

    return page["title"], content

def get_page_buttons(book_type, page_num, mode, min_page, max_page, user_id=None):
    buttons = []
    nav = []
    if page_num > min_page:
        nav.append({"text": "◀️ السابق", "callback_data": f"student_{mode}_p_{page_num-1}"})
    if page_num < max_page:
        nav.append({"text": "التالي ▶️", "callback_data": f"student_{mode}_p_{page_num+1}"})
    if nav:
        buttons.append(nav)

    # أزرار الترجمة وحل التمارين (كما في الكود القديم)
    if mode == "original":
        buttons.append([
            {"text": "🔤 الترجمة", "callback_data": f"student_translated_p_{page_num}"},
            {"text": "📝 حل التمارين", "callback_data": f"student_solved_p_{page_num}"}
        ])
    elif mode == "translated":
        buttons.append([
            {"text": "🔤 النص الأصلي", "callback_data": f"student_original_p_{page_num}"},
            {"text": "📝 حل التمارين", "callback_data": f"student_solved_p_{page_num}"}
        ])
    else:
        buttons.append([
            {"text": "🔤 النص الأصلي", "callback_data": f"student_original_p_{page_num}"},
            {"text": "🔤 الترجمة", "callback_data": f"student_translated_p_{page_num}"}
        ])

    buttons.append([{"text": "🏠 القائمة الرئيسية", "callback_data": "back_to_main"}])
    return {"inline_keyboard": buttons}

# ==================== إعداد الـ Webhook ====================
@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>{len(STUDENT_PAGES)} صفحة</p>"

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
        user_id = callback['from']['id']

        print(f"🔘 {cb_data} from {user_id}")

        if cb_data == "back_to_main":
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً!\n📚 {len(STUDENT_PAGES)} صفحة\nاضغط الزر 👇",
                "reply_markup": keyboard
            })
            requests.post(URL + '/deleteMessage', json={
                "chat_id": chat_id,
                "message_id": msg_id
            })
            return 'OK'

        # تحليل callback_data (مثل: student_original_p_10)
        parts = cb_data.split("_")
        if len(parts) >= 4:
            book_type = parts[0]   # student
            mode = parts[1]        # original / translated / solved
            page_num = int(parts[3])

            pages_list = sorted([int(p) for p in STUDENT_PAGES.keys()])
            min_page = min(pages_list)
            max_page = max(pages_list)

            title, content = get_page_content(page_num, mode, user_id)
            if content:
                # تقطيع النص الطويل
                if len(content) > 4000:
                    content = content[:4000] + "\n\n...(يوجد محتوى إضافي)"

                requests.post(URL + '/editMessageText', json={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                    "reply_markup": get_page_buttons(book_type, page_num, mode, min_page, max_page, user_id),
                    "parse_mode": "Markdown"
                })
        return 'OK'

    # معالجة الرسائل النصية
    if 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')
        user_id = data['message']['from']['id']
        print(f"📨 {text} from {user_id}")

        if text == '/start':
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً بك!\n📚 {len(STUDENT_PAGES)} صفحة\nاضغط الزر 👇",
                "reply_markup": keyboard
            })

        elif text == "📖 كتاب الطالب":
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"📄 أرسل رقم الصفحة (1-{len(STUDENT_PAGES)}):"
            })

        elif text.isdigit():
            page_num = int(text)
            pages_list = sorted([int(p) for p in STUDENT_PAGES.keys()])
            if page_num in pages_list:
                title, content = get_page_content(page_num, "original", user_id)
                if content:
                    if len(content) > 4000:
                        content = content[:4000] + "\n\n...(يوجد محتوى إضافي)"
                    requests.post(URL + '/sendMessage', json={
                        "chat_id": chat_id,
                        "text": f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                        "reply_markup": get_page_buttons("student", page_num, "original", min(pages_list), max(pages_list), user_id),
                        "parse_mode": "Markdown"
                    })
            else:
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": f"❌ الصفحة {page_num} غير موجودة\n📚 المتوفرة: {pages_list}"
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
