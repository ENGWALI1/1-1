import os
import json
from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"
HOSTNAME = os.environ['RENDER_EXTERNAL_HOSTNAME']

with open('student_textbook.json', 'r', encoding='utf-8') as f:
    BOOK = json.load(f)

print(f"🚀 @withali91_bot - {len(BOOK)} صفحة")

@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>{len(BOOK)} صفحة</p>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    chat_id = data['message']['chat']['id']
    text = data['message']['text']
    
    print(f"📨 {text}")
    
    if text == '/start':
        keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
        requests.post(URL + '/sendMessage', json={
            "chat_id": chat_id,
            "text": f"🎉 مرحباً!\n📚 {len(BOOK)} صفحة\nاضغط 📖",
            "reply_markup": keyboard
        })
    
    elif text == "📖 كتاب الطالب":
        requests.post(URL + '/sendMessage', json={
            "chat_id": chat_id,
            "text": "📄 رقم الصفحة (1-80):"
        })
    
    elif text.isdigit() and text in BOOK:
        content = BOOK[text]['content'][:3000]
        requests.post(URL + '/sendMessage', json={
            "chat_id": chat_id,
            "text": f"📖 صفحة {text}\n\n{content}"
        })
    
    else:
        keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
        requests.post(URL + '/sendMessage', json={
            "chat_id": chat_id,
            "text": "📖 كتاب الطالب",
            "reply_markup": keyboard
        })
    
    return 'OK'

if __name__ == '__main__':
    port
