import os
import json
from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"
HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')

# تحميل الكتاب
with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)

print(f"🚀 @withali91_bot - {len(BOOK)} صفحة")

# تخزين حالة المستخدمين (من ينتظر إرسال رقم صفحة)
waiting_for_page = {}

@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>{len(BOOK)} صفحة</p>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
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
            "text": "📄 أرسل رقم الصفحة (1-80):"
        })
    
    # إذا كان المستخدم ينتظر إرسال رقم صفحة
    elif user_id in waiting_for_page:
        if text.isdigit() and text in BOOK:
            content = BOOK[text]['content'][:4000]
            title = BOOK[text].get('title', f'صفحة {text}')
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"📖 {title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}"
            })
            # إزالة المستخدم من قائمة الانتظار بعد عرض الصفحة
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
