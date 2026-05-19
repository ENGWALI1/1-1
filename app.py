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
    print("❌ BOT_TOKEN غير موجود")
    exit(1)

URL = f"https://api.telegram.org/bot{TOKEN}"
ADMIN_ID = 1662780469
SYRIATEL_NUMBERS = ["15570270"]
PRICES = {"1_month": 50}

# تخزين اختيار المستخدم (student أو activity)
user_book_choice = {}
# تخزين حالة الاشتراك (مرحلة انتظار رقم العملية)
user_plan_choice = {}

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

# ==================== فك ضغط وتحميل البيانات ====================
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

print("📚 تحميل كتاب الطالب...")
STUDENT_PAGES = load_pages_from_zip("student_pages.zip")

print("📚 تحميل كتاب الأنشطة...")
ACTIVITY_PAGES = load_pages_from_zip("activity_pages.zip")

STUDENT_LIST = sorted([int(p) for p in STUDENT_PAGES.keys()])
ACTIVITY_LIST = sorted([int(p) for p in ACTIVITY_PAGES.keys()])

STUDENT_MIN = min(STUDENT_LIST) if STUDENT_LIST else 1
STUDENT_MAX = max(STUDENT_LIST) if STUDENT_LIST else 80
ACTIVITY_MIN = min(ACTIVITY_LIST) if ACTIVITY_LIST else 1
ACTIVITY_MAX = max(ACTIVITY_LIST) if ACTIVITY_LIST else 64

print(f"✅ كتاب الطالب: {len(STUDENT_PAGES)} صفحة ({STUDENT_MIN} إلى {STUDENT_MAX})")
print(f"✅ كتاب الأنشطة: {len(ACTIVITY_PAGES)} صفحة ({ACTIVITY_MIN} إلى {ACTIVITY_MAX})")

# ==================== دوال العرض ====================
def format_text(content):
    if not content:
        return "لا يوجد محتوى"
    content = content.replace("---", "\n━━━━━━━━━━━━━━━━━━━━━━━━\n")
    content = content.replace("Grammar", "\n📚 **Grammar**\n")
    content = content.replace("Listening", "\n🎧 **Listening**\n")
    content = content.replace("Speaking", "\n💬 **Speaking**\n")
    content = content.replace("Reading", "\n📖 **Reading**\n")
    content = content.replace("Writing", "\n✏️ **Writing**\n")
    content = content.replace("Vocabulary", "\n📝 **Vocabulary**\n")
    content = content.replace("Pronunciation", "\n🔊 **Pronunciation**\n")
    return content[:4000]

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
        if isinstance(ex, str):
            result += f"**{i}. {ex[:200]}**\n\n"
        elif isinstance(ex, dict):
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
            elif ex_type == 'matching':
                result += f"**🔗 تمرين المزاوجة {i}:**\n"
                result += f"✅ **الحل:** {ex.get('answer', '---')}\n\n"
            else:
                question = ex.get('text') or ex.get('question') or ex.get('q') or f'سؤال {i}'
                answer = ex.get('answer') or ex.get('a') or ex.get('solution') or ex.get('correct') or '---'
                if isinstance(answer, list):
                    answer = ', '.join(str(a) for a in answer)
                if isinstance(answer, bool):
                    answer = "صحيح" if answer else "خطأ"
                result += f"**{i}. {question}**\n✅ {answer}\n\n"
        elif isinstance(ex, list):
            result += f"**{i}. {', '.join(str(x) for x in ex[:5])}**\n\n"
        else:
            result += f"**{i}. {str(ex)[:200]}**\n\n"
    
    return result

def text_to_audio(text, book_type, page_num):
    audio_dir = "audio"
    os.makedirs(audio_dir, exist_ok=True)
    
    clean_text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    if len(clean_text) < 10:
        clean_text = f"Page {page_num} of {book_type} book."
    
    audio_path = os.path.join(audio_dir, f"{book_type}_{page_num}.mp3")
    
    if os.path.exists(audio_path):
        return audio_path
    
    async def _gen():
        try:
            communicate = edge_tts.Communicate(clean_text[:3000], "en-US-JennyNeural")
            await communicate.save(audio_path)
            return audio_path
        except:
            return None
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_gen())
        loop.close()
        return result
    except:
        return None

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
        try:
            days_left = (datetime.fromisoformat(expiry) - datetime.now()).days
            text += f"\n🆔 `{uid}`\n📅 ينتهي: {expiry_date}\n📆 متبقي: {days_left} يوم\n"
        except:
            text += f"\n🆔 `{uid}`\n📅 ينتهي: {expiry_date}\n"
    send_message(chat_id, text, parse_mode="Markdown")

def contact_teacher(chat_id):
    keyboard = {"inline_keyboard": [[{"text": "🛠️ الدعم الفني", "url": "https://t.me/ENGWALI1"}]]}
    send_message(chat_id, "🛠️ اضغط على الزر أدناه للتواصل مع الدعم الفني:", keyboard)

# ==================== معالج Webhook ====================
@app.route('/')
def home():
    return "🤖 Bot is running!"

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
        
        # ✅ زر القائمة الرئيسية
        if cb_data == "main_menu":
            keyboard = get_user_menu(chat_id)
            delete_message(chat_id, msg_id)
            send_message(chat_id, "🎉 مرحباً بك! اختر من القائمة 👇", keyboard)
            return "OK"
        
        # اختيار الباقة
        if cb_data.startswith("sub_"):
            plan = cb_data.replace("sub_", "")
            amount = PRICES.get(plan, 50)
            numbers_text = "\n".join(SYRIATEL_NUMBERS)
            
            # تخزين حالة المستخدم
            user_plan_choice[chat_id] = {"plan": plan, "amount": amount, "step": "waiting_transaction"}
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 رجوع", "callback_data": "main_menu"}]
                ]
            }
            edit_message(chat_id, msg_id,
                f"✅ **تم اختيار الباقة: {plan.replace('_', ' ')}**\n"
                f"💰 المبلغ: {amount} ل.س\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📞 **أرقام سيريتل كاش:**\n{numbers_text}\n\n"
                f"🔄 الرجاء إرسال المبلغ إلى أحد الأرقام أعلاه.\n\n"
                f"📌 بعد إتمام التحويل، أرسل **رقم عملية التحويل** (ID العملية).\n"
                f"مثال: `600044062208`\n\n"
                f"أو اضغط رجوع للإلغاء.",
                keyboard,
                parse_mode="Markdown")
            return "OK"
        
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
                edit_message(chat_id, msg_id, f"✅ تم تفعيل الاشتراك بنجاح!", parse_mode="Markdown")
                send_message(user_id, "🎉 **تم تفعيل اشتراكك بنجاح!**\n✅ يمكنك الآن الوصول إلى جميع محتويات البوت.", parse_mode="Markdown")
            return "OK"
        
        # رفض اشتراك
        if cb_data.startswith("reject_"):
            invoice_id = cb_data.split("_")[1]
            pending = load_pending()
            if invoice_id in pending:
                user_id = pending[invoice_id]["user_id"]
                del pending[invoice_id]
                save_pending(pending)
                edit_message(chat_id, msg_id, f"❌ تم رفض الطلب", parse_mode="Markdown")
                send_message(user_id, "❌ **عذراً، لم يتم قبول طلب الاشتراك**\nيرجى مراجعة بيانات الدفع أو التواصل مع الدعم الفني.", parse_mode="Markdown")
            return "OK"
        
        # تشغيل الصوت
        if cb_data.startswith("audio_"):
            parts = cb_data.split("_")
            prefix = parts[1]
            page_num = parts[2]
            send_message(chat_id, "🎵 جاري تجهيز الصوت...")
            pages = STUDENT_PAGES if prefix == "student" else ACTIVITY_PAGES
            if page_num in pages:
                text = pages[page_num].get("content_original", "")
                audio_path = text_to_audio(text, prefix, page_num)
                if audio_path and os.path.exists(audio_path):
                    with open(audio_path, 'rb') as audio:
                        requests.post(URL + "/sendVoice", files={"voice": audio}, data={"chat_id": chat_id})
                else:
                    send_message(chat_id, "❌ عذراً، حدث خطأ في إنشاء الصوت")
            return "OK"
        
        # أزرار التنقل والترجمة والتمارين
        parts = cb_data.split("_")
        if len(parts) >= 3:
            book_type = "student" if parts[0] == "student" else "activity"
            action = parts[1]
            page_num = parts[2]
            pages = STUDENT_PAGES if book_type == "student" else ACTIVITY_PAGES
            min_page = STUDENT_MIN if book_type == "student" else ACTIVITY_MIN
            max_page = STUDENT_MAX if book_type == "student" else ACTIVITY_MAX
            if page_num in pages:
                page = pages[page_num]
                title = page.get("title", f"صفحة {page_num}")
                if action == "original" or action == "page":
                    content = format_text(page.get("content_original", ""))
                    mode = "original"
                elif action == "translated":
                    content = format_translation(page.get("content_line_by_line", []))
                    mode = "translated"
                elif action == "solved":
                    content = format_exercises(page.get("exercises", []))
                    mode = "solved"
                else:
                    content = format_text(page.get("content_original", ""))
                    mode = "original"
                edit_message(chat_id, msg_id, 
                    f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                    get_page_buttons(book_type, page_num, mode, min_page, max_page),
                    "Markdown")
        return "OK"
    
    # معالجة الرسائل النصية
    if 'message' in data:
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        user_id = msg['from']['id']
        
        # بدء أو الرئيسية
        if text == '/start' or text == "🏠 الرئيسية":
            keyboard = get_user_menu(user_id)
            send_message(chat_id, "🎉 مرحباً بك! اختر من القائمة 👇", keyboard)
        
        # عرض قائمة الاشتراك
        elif text == "💳 اشتراك":
            keyboard = {
                "inline_keyboard": [
                    [{"text": "1 شهر - 50 ل.س", "callback_data": "sub_1_month"}],
                    [{"text": "🔙 رجوع", "callback_data": "main_menu"}]
                ]
            }
            send_message(chat_id, "💳 **نظام الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━━━\nاختر الباقة المناسبة لك:", keyboard, "Markdown")
        
        # كتاب الطالب
        elif text == "📖 كتاب الطالب":
            user_book_choice[user_id] = "student"
            send_message(chat_id, f"📖 كتاب الطالب - أرسل رقم الصفحة ({STUDENT_MIN}-{STUDENT_MAX}):")
        
        # كتاب الأنشطة
        elif text == "✏️ كتاب الأنشطة":
            user_book_choice[user_id] = "activity"
            send_message(chat_id, f"✏️ كتاب الأنشطة - أرسل رقم الصفحة ({ACTIVITY_MIN}-{ACTIVITY_MAX}):")
        
        # القواعد
        elif text == "📚 القواعد":
            send_message(chat_id, "📚 قائمة القواعد (قيد التطوير)")
        
        # طلبات الاشتراك (للأدمن)
        elif text == "📋 طلبات الاشتراك":
            show_pending_requests(chat_id, user_id)
        
        # المشتركين (للأدمن)
        elif text == "👥 المشتركين":
            show_active_subscriptions(chat_id, user_id)
        
        # الدعم الفني
        elif text == "🛠️ الدعم الفني":
            contact_teacher(chat_id)
        
        # معالجة رقم العملية (إذا كان المستخدم في مرحلة الانتظار)
        elif user_id in user_plan_choice and user_plan_choice[user_id].get("step") == "waiting_transaction":
            transaction_id = text.strip()
            if len(transaction_id) >= 5:
                # قبول رقم العملية
                pending = load_pending()
                invoice_id = random.randint(100000, 999999)
                plan_data = user_plan_choice[user_id]
                pending[str(invoice_id)] = {
                    "user_id": user_id,
                    "username": msg['from'].get('username', ''),
                    "first_name": msg['from'].get('first_name', ''),
                    "amount": plan_data["amount"],
                    "transaction_id": transaction_id,
                    "plan": plan_data["plan"]
                }
                save_pending(pending)
                
                # حذف حالة المستخدم
                del user_plan_choice[user_id]
                
                send_message(chat_id, 
                    f"✅ **تم استلام طلبك بنجاح!**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📦 الباقة: {plan_data['plan'].replace('_', ' ')}\n"
                    f"💰 المبلغ: {plan_data['amount']} ل.س\n"
                    f"📌 رقم العملية: `{transaction_id}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"⏳ سيتم مراجعة بياناتك وإعلامك بقبول الاشتراك خلال وقت قصير.\n"
                    f"🙏 شكراً لانتظارك!",
                    parse_mode="Markdown")
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "✅ قبول", "callback_data": f"approve_{invoice_id}"},
                         {"text": "❌ رفض", "callback_data": f"reject_{invoice_id}"}]
                    ]
                }
                send_message(ADMIN_ID,
                    f"🔔 **طلب اشتراك جديد**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 {msg['from'].get('first_name', '')}\n"
                    f"🆔 `{user_id}`\n"
                    f"📝 @{msg['from'].get('username', '')}\n"
                    f"📦 {plan_data['plan'].replace('_', ' ')}\n"
                    f"💰 {plan_data['amount']} ل.س\n"
                    f"📌 رقم العملية: `{transaction_id}`\n"
                    f"📌 رقم الطلب: `{invoice_id}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━",
                    keyboard,
                    "Markdown")
            else:
                send_message(chat_id, "❌ رقم العملية غير صحيح. الرجاء إدخال رقم صحيح (أكثر من 5 أرقام)")
        
        # إذا كان رقماً (صفحة من كتاب)
        elif text.isdigit():
            selected_book = user_book_choice.get(user_id)
            if selected_book == "student":
                if text in STUDENT_PAGES:
                    page = STUDENT_PAGES[text]
                    content = format_text(page.get("content_original", ""))
                    send_message(chat_id, 
                        f"📖 **{page['title']}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                        get_page_buttons("student", text, "original", STUDENT_MIN, STUDENT_MAX),
                        "Markdown")
                else:
                    send_message(chat_id, f"❌ الصفحة {text} غير موجودة في كتاب الطالب\n📚 الصفحات المتوفرة: {STUDENT_LIST[:20]}")
            elif selected_book == "activity":
                if text in ACTIVITY_PAGES:
                    page = ACTIVITY_PAGES[text]
                    content = format_text(page.get("content_original", ""))
                    send_message(chat_id, 
                        f"✏️ **{page['title']}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}",
                        get_page_buttons("activity", text, "original", ACTIVITY_MIN, ACTIVITY_MAX),
                        "Markdown")
                else:
                    send_message(chat_id, f"❌ الصفحة {text} غير موجودة في كتاب الأنشطة\n📚 الصفحات المتوفرة: {ACTIVITY_LIST[:20]}")
            else:
                send_message(chat_id, "❌ اختر كتاباً أولاً (📖 كتاب الطالب أو ✏️ كتاب الأنشطة)")
        
        # أي شيء آخر
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
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
