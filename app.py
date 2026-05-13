import os
import json
import zipfile
from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"
HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')

# ==================== فك ضغط الملفات ====================
def extract_and_load(zip_path):
    """فك ضغط الملف وقراءة جميع ملفات JSON"""
    pages = {}
    extract_dir = "student_pages_temp"
    
    # فك الضغط
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)
    
    # البحث عن جميع ملفات JSON
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # استخراج رقم الصفحة من اسم الملف
                        page_num = file.replace('page_', '').replace('.json', '')
                        # إذا كان الملف يحتوي على عدة صفحات
                        if isinstance(data, dict):
                            if page_num in data:
                                pages[page_num] = data[page_num]
                            elif 'content' in data:
                                pages[page_num] = data
                            else:
                                # البحث عن مفتاح رقمي
                                for key in data:
                                    if str(key).isdigit():
                                        pages[str(key)] = data[key]
                                        break
                        else:
                            pages[page_num] = {"content": str(data)}
                except Exception as e:
                    print(f"خطأ في {file}: {e}")
    
    return pages

# تحميل الكتاب من ZIP
zip_path = 'student_pages.zip'
if os.path.exists(zip_path):
    BOOK = extract_and_load(zip_path)
    print(f"✅ تم تحميل {len(BOOK)} صفحة من {zip_path}")
else:
    print(f"❌ {zip_path} غير موجود")
    BOOK = {}

# تخزين حالة المستخدمين
waiting_for_page = {}

@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>{len(BOOK)} صفحة</p>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'message' not in data:
        return 'OK'
    
    chat_id = data['message']['chat']['id']
    text = data['message'].get('text', '')
    user_id = data['message']['from']['id']
    
    print(f"📨 {text} from {user_id}")
    
    # أمر /start
    if text == '/start':
        keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
        requests.post(URL + '/sendMessage', json={
            "chat_id": chat_id,
            "text": f"🎉 مرحباً!\n📚 {len(BOOK)} صفحة\nاضغط 📖 كتاب الطالب",
            "reply_markup": keyboard
        })
    
    # زر كتاب الطالب
    elif text == "📖 كتاب الطالب":
        waiting_for_page[user_id] = True
        requests.post(URL + '/sendMessage', json={
            "chat_id": chat_id,
            "text": f"📄 أرسل رقم الصفحة (1-{len(BOOK)}):"
        })
    
    # إذا كان المستخدم ينتظر إرسال رقم صفحة
    elif user_id in waiting_for_page:
        if text.isdigit() and text in BOOK:
            page_data = BOOK[text]
            content = page_data.get('content', page_data.get('content_original', str(page_data)))
            title = page_data.get('title', f'صفحة {text}')
            
            # تنظيف المحتوى (إزالة العلامات الزائدة)
            content = content[:4000]
            
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"📖 {title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}"
            })
            del waiting_for_page[user_id]
        else:
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"❌ '{text}' ليس رقم صفحة صحيح.\nأرسل رقماً من 1 إلى {len(BOOK)}"
            })
    
    # أي نص آخر
    else:
        keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
        requests.post(URL + '/sendMessage', json={
            "chat_id": chat_id,
            "text": "اضغط على 📖 كتاب الطالب",
            "reply_markup": keyboard
        })
    
    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
