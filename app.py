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
import logging

# إعداد نظام التسجيل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ BOT_TOKEN غير موجود")
    exit(1)

URL = f"https://api.telegram.org/bot{TOKEN}"
ADMIN_ID = 1662780469
SYRIATEL_NUMBERS = ["15570270"]
PRICES = {"1_month": 50}
FREE_REQUESTS = 10  # عدد الطلبات المجانية

# ==================== ملفات الاستخدام ====================
def load_user_usage():
    try:
        with open("user_usage.json", 'r') as f:
            return json.load(f)
    except:
        return {}

def save_user_usage(data):
    with open("user_usage.json", 'w') as f:
        json.dump(data, f, indent=2)

def check_and_deduct_request(user_id):
    """التحقق من رصيد المستخدم وخصم طلب"""
    # المسؤول لا يخضع للحد
    if user_id == ADMIN_ID:
        return True
    
    # التحقق من الاشتراك
    if is_subscribed(user_id):
        return True
    
    usage = load_user_usage()
    user_data = usage.get(str(user_id), {"used": 0})
    
    if user_data["used"] >= FREE_REQUESTS:
        return False
    
    # خصم طلب
    user_data["used"] = user_data.get("used", 0) + 1
    usage[str(user_id)] = user_data
    save_user_usage(usage)
    
    # إرسال تحذير عند قرب النفاد
    remaining = FREE_REQUESTS - user_data["used"]
    return True

def get_remaining_requests(user_id):
    """الحصول على عدد الطلبات المتبقية"""
    if user_id == ADMIN_ID or is_subscribed(user_id):
        return "غير محدود"
    
    usage = load_user_usage()
    user_data = usage.get(str(user_id), {"used": 0})
    remaining = FREE_REQUESTS - user_data["used"]
    return max(0, remaining)

def get_usage_message(user_id):
    """رسالة حالة الاستخدام"""
    if user_id == ADMIN_ID:
        return "👑 أنت المسؤول، لديك وصول غير محدود"
    
    if is_subscribed(user_id):
        return "✅ مشترك نشط - وصول غير محدود"
    
    remaining = get_remaining_requests(user_id)
    return f"📊 **الطلبات المجانية المتبقية:** {remaining} من {FREE_REQUESTS}\n💳 بعد نفادها، اشترك بـ 50 ل.س فقط للوصول غير المحدود!"

def reset_user_requests_on_subscription(user_id):
    """إعادة تعيين الاستخدام بعد الاشتراك"""
    usage = load_user_usage()
    if str(user_id) in usage:
        usage[str(user_id)]["used"] = 0
        save_user_usage(usage)

# ==================== القوائم (نفسها) ====================
unsubscribed_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "📝 تمارين", "💳 اشتراك"],
        ["📊 رصيدي", "🛠️ الدعم الفني", "🏠 الرئيسية"]
    ],
    "resize_keyboard": True
}

subscribed_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "📝 تمارين"],
        ["📊 رصيدي", "🛠️ الدعم الفني", "🏠 الرئيسية"]
    ],
    "resize_keyboard": True
}

admin_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "📝 تمارين", "💳 اشتراك"],
        ["📋 طلبات الاشتراك", "👥 المشتركين"],
        ["📊 رصيدي", "🛠️ الدعم الفني", "🏠 الرئيسية"]
    ],
    "resize_keyboard": True
}

# ==================== نظام الاشتراك (نفسه) ====================
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

# ==================== باقي الدوال (تحميل الكتب والقواعد والاختبارات) ====================
# [سيتم إضافة دوال load_pages_from_zip, load_grammar_rules, load_tests هنا]
# (نفس الكود السابق)

# ==================== دوال مساعدة ====================
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

def delete_message(chat_id, message_id):
    requests.post(URL + "/deleteMessage", json={"chat_id": chat_id, "message_id": message_id})

# ==================== دوال الاشتراك ====================
def show_pending_requests(chat_id, user_id):
    if user_id != ADMIN_ID:
        send_message(chat_id, "❌ هذا الأمر للمسؤول فقط.")
        return
    pending = load_pending()
    if not pending:
        send_message(chat_id, "📭 لا توجد طلبات اشتراك معلقة.")
        return
    text = "📋 **طلبات الاشتراك المعلقة**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for inv_id, p in pending.items():
        text += f"\n📌 **رقم الطلب:** `{inv_id}`\n"
        text += f"👤 {p.get('first_name', p.get('username', 'بدون'))}\n"
        text += f"🆔 `{p['user_id']}`\n"
        text += f"💰 {p.get('amount', 50)} ل.س\n"
        text += f"📞 {p.get('transaction_id', 'لم يرسل بعد')}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    send_message(chat_id, text, parse_mode="Markdown")

def show_active_subscriptions(chat_id, user_id):
    if user_id != ADMIN_ID:
        send_message(chat_id, "❌ هذا الأمر للمسؤول فقط.")
        return
    subs = load_subs()
    if not subs:
        send_message(chat_id, "📭 لا يوجد مشتركين حالياً.")
        return
    text = "👥 **المشتركين الحاليين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for uid, expiry in subs.items():
        expiry_date = expiry[:10] if expiry else "غير محدد"
        text += f"\n🆔 `{uid}`\n📅 ينتهي: {expiry_date}\n"
    send_message(chat_id, text, parse_mode="Markdown")

def contact_teacher(chat_id):
    keyboard = {"inline_keyboard": [[{"text": "🛠️ الدعم الفني", "url": "https://t.me/ENGWALI1"}]]}
    send_message(chat_id, "🛠️ اضغط على الزر أدناه للتواصل مع الدعم الفني:", keyboard)

def show_my_balance(chat_id, user_id):
    """عرض رصيد المستخدم المتبقي"""
    if user_id == ADMIN_ID:
        text = "👑 **المسؤول**\n━━━━━━━━━━━━━━━━━━━━━━━━\n✅ وصول غير محدود (بدون قيود)"
    elif is_subscribed(user_id):
        subs = load_subs()
        expiry = subs.get(str(user_id), "")
        expiry_date = expiry[:10] if expiry else "غير محدد"
        text = f"✅ **مشترك نشط**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📅 ينتهي الاشتراك: {expiry_date}\n🎉 وصول غير محدود إلى جميع المحتويات"
    else:
        usage = load_user_usage()
        user_data = usage.get(str(user_id), {"used": 0})
        remaining = FREE_REQUESTS - user_data["used"]
        text = f"📊 **رصيد الطلبات المجانية**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ المتبقي: {remaining} من {FREE_REQUESTS}\n\n💳 بعد نفاذ الرصيد، اشترك بـ 50 ل.س فقط للحصول على:\n✓ وصول غير محدود\n✓ الترجمة الكاملة\n✓ حلول التمارين\n✓ جميع الاختبارات\n✓ خاصية الصوت\n\n📞 سيريتل كاش: 15570270"
    send_message(chat_id, text, parse_mode="Markdown")

# ==================== دوال الاختبارات (مع نظام الاستخدام) ====================
def start_test(chat_id, user_id, test_name):
    # التحقق من الرصيد
    if not check_and_deduct_request(user_id):
        remaining = get_remaining_requests(user_id)
        send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ رصيدك المتبقي: {remaining}\n\n💳 اشترك الآن بـ 50 ل.س فقط للوصول غير المحدود إلى:\n✓ جميع الاختبارات\n✓ الترجمة الكاملة\n✓ حلول التمارين\n✓ خاصية الصوت\n\n📞 أرسل المبلغ إلى سيريتل كاش: 15570270\nثم اضغط على 💳 اشتراك", parse_mode="Markdown")
        return
    
    # باقي الكود (نفس السابق)
    # ...

# ==================== معالج Webhook المعدل ====================
@app.route('/')
def home():
    return "🤖 Bot is running!"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data:
        return "OK"
    
    if 'message' in data:
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        user_id = msg['from']['id']
        
        # أمر عرض الرصيد
        if text == "📊 رصيدي":
            show_my_balance(chat_id, user_id)
            return "OK"
        
        # كتاب الطالب (مع التحقق من الرصيد)
        elif text == "📖 كتاب الطالب":
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ رصيدك المتبقي: {remaining}\n\n💳 اشترك الآن بـ 50 ل.س فقط للوصول غير المحدود!", parse_mode="Markdown")
                return "OK"
            user_book_choice[user_id] = "student"
            send_message(chat_id, f"📖 كتاب الطالب - أرسل رقم الصفحة ({STUDENT_MIN}-{STUDENT_MAX}):")
        
        # كتاب الأنشطة (مع التحقق من الرصيد)
        elif text == "✏️ كتاب الأنشطة":
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ رصيدك المتبقي: {remaining}\n\n💳 اشترك الآن بـ 50 ل.س فقط للوصول غير المحدود!", parse_mode="Markdown")
                return "OK"
            user_book_choice[user_id] = "activity"
            send_message(chat_id, f"✏️ كتاب الأنشطة - أرسل رقم الصفحة ({ACTIVITY_MIN}-{ACTIVITY_MAX}):")
        
        # القواعد (مع التحقق من الرصيد)
        elif text == "📚 القواعد":
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ رصيدك المتبقي: {remaining}\n\n💳 اشترك الآن بـ 50 ل.س فقط للوصول غير المحدود!", parse_mode="Markdown")
                return "OK"
            if GRAMMAR_RULES:
                send_message(chat_id, "📚 **اختر القاعدة التي تريد دراستها:**", get_grammar_buttons())
            else:
                send_message(chat_id, "📚 لا توجد قواعد متوفرة حالياً.")
        
        # تمارين (مع التحقق من الرصيد)
        elif text == "📝 تمارين":
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ رصيدك المتبقي: {remaining}\n\n💳 اشترك الآن بـ 50 ل.س فقط للوصول غير المحدود!", parse_mode="Markdown")
                return "OK"
            send_message(chat_id, "📝 **اختر المستوى:**", get_level_buttons())
        
        # عرض رقم الصفحة (مع التحقق من الرصيد)
        elif text.isdigit():
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ رصيدك المتبقي: {remaining}\n\n💳 اشترك الآن بـ 50 ل.س فقط للوصول غير المحدود!", parse_mode="Markdown")
                return "OK"
            # باقي الكود لعرض الصفحة...
        
        # بدء أو الرئيسية
        elif text == '/start' or text == "🏠 الرئيسية":
            keyboard = get_user_menu(user_id)
            # عرض رسالة ترحيب مع عدد الطلبات المتبقية
            remaining_msg = get_usage_message(user_id)
            send_message(chat_id, f"🎉 مرحباً بك!\n\n{remaining_msg}", keyboard)
        
        # باقي الأوامر...
        
        # معالجة رقم العملية (للاشتراك)
        elif re.match(r'^\d{5,}$', text.replace(" ", "")):
            # [نفس الكود السابق للاشتراك]
            pass
        
        else:
            keyboard = get_user_menu(user_id)
            send_message(chat_id, "اختر من القائمة 👇", keyboard)
    
    return "OK"

# ==================== التشغيل ====================
if __name__ == '__main__':
    if not os.path.exists("subs.json"):
        save_subs({})
    if not os.path.exists("pending.json"):
        save_pending({})
    if not os.path.exists("user_usage.json"):
        save_user_usage({})
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
