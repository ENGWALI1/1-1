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

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"
ADMIN_ID = 1662780469

# ==================== القوائم (نفس الكود السابق) ====================
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
    try:
        with open("subs.json", 'r') as f:
            return json.load(f)
    except:
        return {}

def save_subs(data):
    with open("subs.json", 'w') as f:
        json.dump(data, f, indent=2)

def load_pending():
    try:
        with open("pending.json", 'r') as f:
            return json.load(f)
    except:
        return {}

def save_pending(data):
    with open("pending.json", 'w') as f:
        json.dump(data, f, indent=2)

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

# ==================== دوال الاشتراك ====================
async def request_subscription(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username or "بدون معرف"
    first_name = update.effective_user.first_name or ""
    
    pending = load_pending()
    invoice_id = random.randint(100000, 999999)
    pending[str(invoice_id)] = {
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "plan": "1_month",
        "amount": 50,
        "status": "pending"
    }
    save_pending(pending)
    
    await update.message.reply_text(
        "✅ **تم استلام طلب اشتراكك!**\n\n"
        "📞 أرسل المبلغ (50 ل.س) إلى رقم سيريتل كاش: `15570270`\n\n"
        "📌 بعد إتمام التحويل، أرسل **رقم العملية** (ID العملية)\n"
        "مثال: `600044062208`",
        parse_mode='Markdown'
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ قبول", "callback_data": f"approve_{invoice_id}"},
                {"text": "❌ رفض", "callback_data": f"reject_{invoice_id}"}
            ]
        ]
    }
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 **طلب اشتراك جديد**\n"
             f"👤 {first_name}\n"
             f"🆔 `{user_id}`\n"
             f"📝 @{username}\n"
             f"📦 شهر واحد (50 ل.س)\n"
             f"📌 رقم الطلب: `{invoice_id}`",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

async def approve_subscription(invoice_id, context):
    pending = load_pending()
    if str(invoice_id) not in pending:
        return False
    
    payment = pending[str(invoice_id)]
    user_id = payment["user_id"]
    
    expiry = (datetime.now() + timedelta(days=30)).isoformat()
    subs = load_subs()
    subs[str(user_id)] = expiry
    save_subs(subs)
    
    del pending[str(invoice_id)]
    save_pending(pending)
    
    await context.bot.send_message(
        chat_id=user_id,
        text="🎉 **تم تفعيل اشتراكك بنجاح!**\n\n"
             "✅ يمكنك الآن الوصول إلى جميع محتويات البوت.\n"
             "📚 استمتع بالتعلم!",
        parse_mode='Markdown'
    )
    return True

async def reject_subscription(invoice_id, context):
    pending = load_pending()
    if str(invoice_id) not in pending:
        return False
    
    user_id = pending[str(invoice_id)]["user_id"]
    del pending[str(invoice_id)]
    save_pending(pending)
    
    await context.bot.send_message(
        chat_id=user_id,
        text="❌ **عذراً، لم يتم قبول طلب الاشتراك**\n\n"
             "يرجى مراجعة بيانات الدفع أو التواصل مع الدعم الفني.\n"
             "🛠️ للدعم: @ENGWALI1",
        parse_mode='Markdown'
    )
    return True

async def show_pending_requests(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر للمسؤول فقط.")
        return
    
    pending = load_pending()
    if not pending:
        await update.message.reply_text("📭 لا توجد طلبات اشتراك معلقة.")
        return
    
    text = "📋 **طلبات الاشتراك المعلقة**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for inv_id, p in pending.items():
        text += f"\n📌 رقم الطلب: `{inv_id}`\n"
        text += f"👤 {p.get('first_name', p.get('username', 'بدون'))}\n"
        text += f"🆔 `{p['user_id']}`\n"
        text += f"💰 {p['amount']} ل.س\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

# ==================== باقي الكود (فك الضغط، الصوت، التنسيق) ====================
# ... (نفس الكود السابق من load_pages_from_zip إلى get_page_buttons)

# ==================== إعداد الـ Webhook ====================
@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1>"

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
        
        if cb_data.startswith("approve_"):
            invoice_id = cb_data.split("_")[1]
            # تشغيل الدالة غير المتزامنة
            asyncio.run(approve_subscription(invoice_id, app))
            requests.post(URL + '/editMessageText', json={
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": "✅ تم قبول طلب الاشتراك وتفعيل المستخدم."
            })
            return 'OK'
        
        if cb_data.startswith("reject_"):
            invoice_id = cb_data.split("_")[1]
            asyncio.run(reject_subscription(invoice_id, app))
            requests.post(URL + '/editMessageText', json={
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": "❌ تم رفض طلب الاشتراك."
            })
            return 'OK'
        
        # باقي معالجات الأزرار (الصوت، الترجمة، التنقل)
        # ... (نفس الكود السابق)
    
    # معالجة الرسائل النصية
    if 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')
        user_id = data['message']['from']['id']
        
        if text == '/start' or text == "🏠 الرئيسية":
            keyboard = get_user_menu(user_id)
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً بك!\nاختر من القائمة 👇",
                "reply_markup": keyboard
            })
        
        elif text == "💳 اشتراك":
            # تشغيل دالة الاشتراك
            asyncio.run(request_subscription(update, app))
        
        # باقي الأوامر (كتب، قواعد، دعم فني، إلخ)
        # ... (نفس الكود السابق)
    
    return 'OK'

if __name__ == '__main__':
    # إنشاء الملفات إذا لم تكن موجودة
    if not os.path.exists("subs.json"):
        with open("subs.json", 'w') as f:
            json.dump({}, f)
    if not os.path.exists("pending.json"):
        with open("pending.json", 'w') as f:
            json.dump({}, f)
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
