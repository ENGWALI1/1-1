import os
import json
import zipfile
import shutil
import re
import asyncio
import random
import edge_tts
from flask import Flask, request
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ BOT_TOKEN غير موجود في متغيرات البيئة")
    exit(1)

URL = f"https://api.telegram.org/bot{TOKEN}"
ADMIN_ID = 1662780469
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
def load_subs():
    try:
        with open("subs.json", 'r') as f:
            return json.load(f)
    except:
        return {}

def save_subs(data):
    with open("subs.json", 'w') as f:
        json.dump(data, f)

def load_pending():
    try:
        with open("pending.json", 'r') as f:
            return json.load(f)
    except:
        return {}

def save_pending(data):
    with open("pending.json", 'w') as f:
        json.dump(data, f)

def is_subscribed(user_id):
    subs = load_subs()
    expiry = subs.get(str(user_id))
    return expiry and datetime.now().isoformat() < expiry

def get_user_menu(user_id):
    if user_id == ADMIN_ID:
        return admin_menu
    elif is_subscribed(user_id):
        return subscribed_menu
    else:
        return unsubscribed_menu
        def load_pages_from_zip(zip_path):
    pages = {}
    extract_dir = zip_path.replace(".zip", "")
    
    if not os.path.exists(zip_path):
        return pages
    
    if not os.path.exists(extract_dir):
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
    
    for root, _, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".json") and file != "index.json":
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        page_num = file.replace("page_", "").replace(".json", "")
                        if isinstance(data, dict):
                            for key in data.keys():
                                if str(key).isdigit():
                                    page_num = str(key)
                                    data = data[key]
                                    break
                        pages[page_num] = {
                            "title": data.get("title", f"صفحة {page_num}"),
                            "content_original": data.get("content_original", ""),
                            "content_line_by_line": data.get("content_line_by_line", []),
                            "exercises": data.get("exercises", [])
                        }
                except:
                    pass
    return pages

STUDENT_PAGES = load_pages_from_zip("student_pages.zip")
ACTIVITY_PAGES = load_pages_from_zip("activity_pages.zip")

STUDENT_LIST = sorted([int(p) for p in STUDENT_PAGES.keys()])
ACTIVITY_LIST = sorted([int(p) for p in ACTIVITY_PAGES.keys()])

STUDENT_MIN = min(STUDENT_LIST) if STUDENT_LIST else 1
STUDENT_MAX = max(STUDENT_LIST) if STUDENT_LIST else 80
ACTIVITY_MIN = min(ACTIVITY_LIST) if ACTIVITY_LIST else 1
ACTIVITY_MAX = max(ACTIVITY_LIST) if ACTIVITY_LIST else 64

print(f"📚 كتاب الطالب: {len(STUDENT_PAGES)} صفحة")
print(f"📚 كتاب الأنشطة: {len(ACTIVITY_PAGES)} صفحة")
def format_text(content):
    if not content:
        return "لا يوجد محتوى"
    content = content.replace("---", "\n━━━━━━━━━━━━━━━━━━━━━━━━\n")
    content = content.replace("Grammar", "\n📚 Grammar\n")
    content = content.replace("Listening", "\n🎧 Listening\n")
    content = content.replace("Speaking", "\n💬 Speaking\n")
    content = content.replace("Reading", "\n📖 Reading\n")
    content = content.replace("Writing", "\n✏️ Writing\n")
    return content[:4000]

def text_to_audio(text, book_type, page_num):
    audio_dir = "audio"
    os.makedirs(audio_dir, exist_ok=True)
    
    clean_text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    if len(clean_text) < 10:
        clean_text = f"Page {page_num}"
    
    audio_path = os.path.join(audio_dir, f"{book_type}_{page_num}.mp3")
    
    if os.path.exists(audio_path):
        return audio_path
    
    async def _gen():
        await edge_tts.Communicate(clean_text[:3000], "en-US-JennyNeural").save(audio_path)
        return audio_path
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_gen())
        loop.close()
        return result
    except:
        return None
        def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    if parse_mode:
        data["parse_mode"] = parse_mode
    requests.post(URL + "/sendMessage", json=data)

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    if parse_mode:
        data["parse_mode"] = parse_mode
    requests.post(URL + "/editMessageText", json=data)

def answer_callback(callback_id, text=None):
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text
    requests.post(URL + "/answerCallbackQuery", json=data)
    @app.route('/')
def home():
    return "Bot is running"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data:
        return "OK"
    
    # معالجة الأزرار
    if 'callback_query' in data:
        cb = data['callback_query']
        cb_data = cb['data']
        chat_id = cb['message']['chat']['id']
        msg_id = cb['message']['message_id']
        
        # قبول اشتراك
        if cb_data.startswith("approve_"):
            invoice_id = cb_data.split("_")[1]
            pending = load_pending()
            if invoice_id in pending:
                user_id = pending[invoice_id]["user_id"]
                expiry = (datetime.now() + timedelta(days=30)).isoformat()
                subs = load_subs()
                subs[str(user_id)] = expiry
                save_subs(subs)
                del pending[invoice_id]
                save_pending(pending)
                edit_message(chat_id, msg_id, "✅ تم قبول الاشتراك")
                send_message(user_id, "🎉 تم تفعيل اشتراكك بنجاح!")
            return "OK"
        
        # رفض اشتراك
        if cb_data.startswith("reject_"):
            invoice_id = cb_data.split("_")[1]
            pending = load_pending()
            if invoice_id in pending:
                user_id = pending[invoice_id]["user_id"]
                del pending[invoice_id]
                save_pending(pending)
                edit_message(chat_id, msg_id, "❌ تم رفض الاشتراك")
                send_message(user_id, "❌ لم يتم قبول طلب الاشتراك")
            return "OK"
        
        # زر الرئيسية
        if cb_data == "main_menu":
            keyboard = get_user_menu(chat_id)
            edit_message(chat_id, msg_id, "🎉 مرحباً بك! اختر من القائمة 👇", keyboard)
            return "OK"
        
        # أزرار التنقل والترجمة والتمارين
        # ... (سأضيفها لاحقاً)
        
        return "OK"
    
    # معالجة الرسائل
    if 'message' in data:
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        user_id = msg['from']['id']
        
        # أمر /start أو الرئيسية
        if text == '/start' or text == "🏠 الرئيسية":
            keyboard = get_user_menu(user_id)
            send_message(chat_id, "🎉 مرحباً بك! اختر من القائمة 👇", keyboard)
        
        # زر الاشتراك
        elif text == "💳 اشتراك":
            invoice_id = random.randint(100000, 999999)
            pending = load_pending()
            pending[str(invoice_id)] = {
                "user_id": user_id,
                "username": msg['from'].get('username', ''),
                "first_name": msg['from'].get('first_name', ''),
                "amount": 50
            }
            save_pending(pending)
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "✅ قبول", "callback_data": f"approve_{invoice_id}"},
                     {"text": "❌ رفض", "callback_data": f"reject_{invoice_id}"}]
                ]
            }
            
            send_message(chat_id, 
                "✅ تم استلام طلب اشتراكك!\n\n"
                "📞 أرسل المبلغ (50 ل.س) إلى سيريتل كاش: 15570270\n\n"
                "📌 بعد إتمام التحويل، سيتم تفعيل اشتراكك.")
            
            send_message(ADMIN_ID, 
                f"🔔 طلب اشتراك جديد\n👤 {msg['from'].get('first_name', '')}\n🆔 {user_id}",
                keyboard)
        
        # كتاب الطالب
        elif text == "📖 كتاب الطالب":
            send_message(chat_id, f"📖 أرسل رقم الصفحة ({STUDENT_MIN}-{STUDENT_MAX}):")
        
        # كتاب الأنشطة
        elif text == "✏️ كتاب الأنشطة":
            send_message(chat_id, f"✏️ أرسل رقم الصفحة ({ACTIVITY_MIN}-{ACTIVITY_MAX}):")
        
        # إذا كان الرقم
        elif text.isdigit():
            if text in STUDENT_PAGES:
                page = STUDENT_PAGES[text]
                content = format_text(page.get("content_original", ""))
                send_message(chat_id, f"📖 {page['title']}\n\n{content}")
            elif text in ACTIVITY_PAGES:
                page = ACTIVITY_PAGES[text]
                content = format_text(page.get("content_original", ""))
                send_message(chat_id, f"✏️ {page['title']}\n\n{content}")
            else:
                send_message(chat_id, f"❌ الصفحة {text} غير موجودة")
        
        else:
            keyboard = get_user_menu(user_id)
            send_message(chat_id, "اختر من القائمة 👇", keyboard)
    
    return "OK"
    if __name__ == '__main__':
    if not os.path.exists("subs.json"):
        save_subs({})
    if not os.path.exists("pending.json"):
        save_pending({})
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
