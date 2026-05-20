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

# تخزين اختيار المستخدم
user_book_choice = {}
user_plan_choice = {}
user_test_data = {}

# ==================== القوائم ====================
unsubscribed_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "📝 تمارين", "💳 اشتراك"],
        ["🛠️ الدعم الفني", "🏠 الرئيسية"]
    ],
    "resize_keyboard": True
}

subscribed_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "📝 تمارين"],
        ["🛠️ الدعم الفني", "🏠 الرئيسية"]
    ],
    "resize_keyboard": True
}

admin_menu = {
    "keyboard": [
        ["📖 كتاب الطالب", "✏️ كتاب الأنشطة"],
        ["📚 القواعد", "📝 تمارين", "💳 اشتراك"],
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

# ==================== تحميل القواعد ====================
def clean_text_for_telegram(text):
    if not text:
        return text
    text = text.replace('┌', '').replace('┐', '').replace('└', '').replace('┘', '')
    text = text.replace('├', '').replace('┤', '').replace('─', '').replace('│', '')
    text = text.replace('█', '').replace('░', '').replace('▒', '').replace('▓', '')
    text = text.replace('┃', '').replace('━', '').replace('┏', '').replace('┓', '')
    text = text.replace('┗', '').replace('┛', '').replace('**', '').replace('__', '')
    text = re.sub(r'\n{4,}', '\n\n', text)
    return text.strip()

def load_grammar_rules():
    rules = {}
    zip_path = "lessons.zip"
    extract_dir = "lessons"
    
    if not os.path.exists(zip_path):
        return rules
    
    if not os.path.exists(extract_dir):
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
    
    for root, _, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".txt"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        rule_name = file.replace(".txt", "")
                        rules[rule_name] = clean_text_for_telegram(f.read())
                except:
                    pass
    return rules

# ==================== تحميل الاختبارات (يدعم المجلدات الفرعية) ====================
def load_tests():
    tests = {}
    zip_path = "tests.zip"
    extract_dir = "tests_temp"
    
    if not os.path.exists(zip_path):
        print("❌ tests.zip غير موجود")
        return tests
    
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    
    print("📦 فك ضغط tests.zip...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)
    
    # طباعة هيكل المجلدات
    print("📂 هيكل المجلدات بعد فك الضغط:")
    for root, dirs, files in os.walk(extract_dir):
        level = os.path.basename(root)
        indent = "  " * (root.count(os.sep) - extract_dir.count(os.sep))
        print(f"{indent}📁 {level}/")
        for file in files:
            print(f"{indent}  📄 {file}")
    
    # البحث في جميع المجلدات الفرعية عن ملفات JSON
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".json"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        grammar_name = data.get("grammar_name")
                        
                        # استخراج المستوى من اسم المجلد
                        level = os.path.basename(root)
                        if level not in ["beginner_1", "beginner_2", "intermediate_1", "intermediate_2", "advanced"]:
                            level = "intermediate_1"
                        
                        if grammar_name:
                            tests[grammar_name] = {
                                "data": data,
                                "level": level
                            }
                            print(f"✅ تم تحميل اختبار: {grammar_name} (المستوى: {level})")
                except Exception as e:
                    print(f"⚠️ خطأ في {file}: {e}")
    
    shutil.rmtree(extract_dir)
    return tests

print("📚 تحميل كتاب الطالب...")
STUDENT_PAGES = load_pages_from_zip("student_pages.zip")

print("📚 تحميل كتاب الأنشطة...")
ACTIVITY_PAGES = load_pages_from_zip("activity_pages.zip")

print("📚 تحميل القواعد النحوية...")
GRAMMAR_RULES = load_grammar_rules()

print("📚 تحميل الاختبارات...")
TESTS = load_tests()

STUDENT_LIST = sorted([int(p) for p in STUDENT_PAGES.keys()])
ACTIVITY_LIST = sorted([int(p) for p in ACTIVITY_PAGES.keys()])

STUDENT_MIN = min(STUDENT_LIST) if STUDENT_LIST else 1
STUDENT_MAX = max(STUDENT_LIST) if STUDENT_LIST else 80
ACTIVITY_MIN = min(ACTIVITY_LIST) if ACTIVITY_LIST else 1
ACTIVITY_MAX = max(ACTIVITY_LIST) if ACTIVITY_LIST else 64

# ترتيب الاختبارات حسب المستوى
TESTS_BY_LEVEL = {
    "beginner_1": [],
    "beginner_2": [],
    "intermediate_1": [],
    "intermediate_2": [],
    "advanced": []
}

for name, test in TESTS.items():
    level = test["level"]
    if level in TESTS_BY_LEVEL:
        TESTS_BY_LEVEL[level].append(name)
        print(f"📌 {name} -> {level}")

print(f"✅ كتاب الطالب: {len(STUDENT_PAGES)} صفحة")
print(f"✅ كتاب الأنشطة: {len(ACTIVITY_PAGES)} صفحة")
print(f"✅ القواعد: {len(GRAMMAR_RULES)} قاعدة")
print(f"✅ الاختبارات: {len(TESTS)}")

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
        if isinstance(ex, dict):
            question = ex.get('text') or ex.get('question') or f'سؤال {i}'
            answer = ex.get('answer') or '---'
            result += f"**{i}. {question}**\n✅ {answer}\n\n"
        else:
            result += f"**{i}. {ex}**\n\n"
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

def get_grammar_buttons():
    buttons = []
    for rule_name in GRAMMAR_RULES.keys():
        display_name = rule_name.replace("_", " ").title()
        buttons.append([{"text": f"📘 {display_name}", "callback_data": f"grammar_{rule_name}"}])
    buttons.append([{"text": "🔙 رجوع", "callback_data": "main_menu"}])
    return {"inline_keyboard": buttons}

def get_level_buttons():
    level_names = {
        "beginner_1": "🥉 مستوى مبتدئ 1",
        "beginner_2": "🥈 مستوى مبتدئ 2",
        "intermediate_1": "🥇 مستوى متوسط 1",
        "intermediate_2": "🏆 مستوى متوسط 2",
        "advanced": "⭐ مستوى متقدم"
    }
    buttons = []
    for level_id, level_name in level_names.items():
        if TESTS_BY_LEVEL.get(level_id):
            buttons.append([{"text": level_name, "callback_data": f"level_{level_id}"}])
    buttons.append([{"text": "🔙 رجوع", "callback_data": "main_menu"}])
    return {"inline_keyboard": buttons}

def get_test_buttons(level_id):
    buttons = []
    if level_id not in TESTS_BY_LEVEL:
        return {"inline_keyboard": [[{"text": "🔙 رجوع", "callback_data": "back_to_levels"}]]}
    
    for test_name in TESTS_BY_LEVEL.get(level_id, []):
        if test_name in TESTS:
            display_name = test_name.replace("_", " ").title()
            buttons.append([{"text": f"📝 {display_name}", "callback_data": f"test_{test_name}"}])
    
    buttons.append([{"text": "🔙 رجوع", "callback_data": "back_to_levels"}])
    return {"inline_keyboard": buttons}

# ==================== دوال الاختبارات ====================
def start_test(chat_id, user_id, test_name):
    logging.info(f"🚀 بدء اختبار: {test_name} للمستخدم {user_id}")
    
    if test_name not in TESTS:
        send_message(chat_id, "❌ الاختبار غير موجود")
        return
    
    test = TESTS[test_name]["data"]
    questions = test.get("questions", [])
    
    if not questions:
        send_message(chat_id, "❌ لا توجد أسئلة في هذا الاختبار")
        return
    
    user_test_data[user_id] = {
        "test_name": test_name,
        "test_title": test.get("title", test_name.replace("_", " ").title()),
        "questions": questions,
        "current": 0,
        "score": 0,
        "total": len(questions)
    }
    
    logging.info(f"📊 عدد الأسئلة: {len(questions)}")
    send_question(chat_id, user_id)

def send_question(chat_id, user_id):
    data = user_test_data.get(user_id)
    if not data:
        send_message(chat_id, "❌ انتهت الجلسة. ابدأ اختباراً جديداً من قائمة التمارين.")
        return
    
    current = data["current"]
    if current >= data["total"]:
        show_test_result(chat_id, user_id)
        return
    
    q = data["questions"][current]
    
    # تنظيف النص من الأحرف الخاصة
    question_text = q['text'].replace('*', '').replace('_', '').replace('`', '')
    
    text = f"📝 *{data['test_title']}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n*السؤال {current + 1} من {data['total']}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n❓ {question_text}\n\n📌 اختر الإجابة الصحيحة:"
    
    buttons = []
    for i, opt in enumerate(q["options"]):
        # تنظيف الخيارات أيضاً
        opt_text = str(opt).replace('*', '').replace('_', '').replace('`', '')
        buttons.append([{"text": f"{i+1}. {opt_text}", "callback_data": f"test_ans_{current}_{i}"}])
    
    keyboard = {"inline_keyboard": buttons}
    
    # استخدام send_message مع parse_mode=None للتأكد من وصول الرسالة
    send_message(chat_id, text, keyboard, None)
    logging.info(f"📤 تم إرسال السؤال {current + 1} من {data['total']}")

def show_test_result(chat_id, user_id):
    data = user_test_data.pop(user_id, None)
    if not data:
        return
    
    percentage = (data["score"] / data["total"]) * 100
    
    if percentage >= 90:
        rating = "⭐ ممتاز!"
    elif percentage >= 75:
        rating = "👍 جيد جداً"
    elif percentage >= 60:
        rating = "📘 جيد"
    elif percentage >= 40:
        rating = "📖 يحتاج إلى مراجعة"
    else:
        rating = "📚 حاول مرة أخرى"
    
    text = f"📊 **نتيجة الاختبار**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 {data['test_title']}\n✅ {data['score']} من {data['total']}\n📈 النسبة: {percentage:.0f}%\n⭐ {rating}\n\n🔙 اضغط /start للعودة إلى القائمة الرئيسية"
    
    keyboard = {"keyboard": [["🏠 الرئيسية"]], "resize_keyboard": True}
    send_message(chat_id, text, keyboard, "Markdown")

def handle_test_answer(chat_id, user_id, question_idx, answer_idx):
    data = user_test_data.get(user_id)
    if not data:
        send_message(chat_id, "❌ انتهت الجلسة. ابدأ اختباراً جديداً من قائمة التمارين.")
        return
    
    if question_idx != data["current"]:
        return
    
    q = data["questions"][question_idx]
    is_correct = (answer_idx + 1) == q["correct"]
    
    if is_correct:
        data["score"] += 1
        result_text = f"✅ **صحيح!**\n{q.get('explanation', 'إجابة صحيحة')}"
    else:
        correct_opt = q["options"][q["correct"] - 1]
        result_text = f"❌ **خطأ!**\n✅ الإجابة الصحيحة: {correct_opt}\n{q.get('explanation', '')}"
    
    data["current"] += 1
    send_message(chat_id, result_text, parse_mode="Markdown")
    
    if data["current"] >= data["total"]:
        show_test_result(chat_id, user_id)
    else:
        send_question(chat_id, user_id)

# ==================== دوال مساعدة ====================
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    if parse_mode:
        data["parse_mode"] = parse_mode
    
    response = requests.post(URL + "/sendMessage", json=data)
    logging.info(f"📤 إرسال رسالة: {response.status_code} - {response.text[:100]}")
    return response

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

# ==================== معالج Webhook ====================
@app.route('/')
def home():
    return "🤖 Bot is running!"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data:
        return "OK"
    
    if 'callback_query' in data:
        cb = data['callback_query']
        cb_data = cb['data']
        chat_id = cb['message']['chat']['id']
        msg_id = cb['message']['message_id']
        user_id = cb['from']['id']
        
        logging.info(f"📩 Callback data: {cb_data}")
        
        # 1. الإجابة على سؤال الاختبار
        if cb_data.startswith("test_ans_"):
            parts = cb_data.split("_")
            if len(parts) >= 3:
                q_idx = int(parts[2])
                a_idx = int(parts[3])
                logging.info(f"📝 إجابة على السؤال {q_idx}: الخيار {a_idx}")
                handle_test_answer(chat_id, user_id, q_idx, a_idx)
            return "OK"
        
        # 2. اختيار اختبار معين
        if cb_data.startswith("test_"):
            test_name = cb_data.replace("test_", "")
            logging.info(f"📚 بدء الاختبار: {test_name}")
            delete_message(chat_id, msg_id)
            start_test(chat_id, user_id, test_name)
            return "OK"
        
        # 3. اختيار مستوى
        if cb_data.startswith("level_"):
            level_id = cb_data.replace("level_", "")
            logging.info(f"🎯 اختيار المستوى: {level_id}")
            delete_message(chat_id, msg_id)
            send_message(chat_id, f"📝 **اختر الاختبار من المستوى {level_id.replace('_', ' ')}:**", get_test_buttons(level_id))
            return "OK"
        
        # 4. رجوع إلى المستويات
        if cb_data == "back_to_levels":
            logging.info(f"🔙 رجوع إلى المستويات")
            delete_message(chat_id, msg_id)
            send_message(chat_id, "📝 **اختر المستوى:**", get_level_buttons())
            return "OK"
        
        # 5. القائمة الرئيسية
        if cb_data == "main_menu":
            keyboard = get_user_menu(chat_id)
            delete_message(chat_id, msg_id)
            send_message(chat_id, "🎉 مرحباً بك! اختر من القائمة 👇", keyboard)
            return "OK"
        
        # 6. أزرار القواعد
        if cb_data.startswith("grammar_"):
            rule_name = cb_data.replace("grammar_", "")
            if rule_name in GRAMMAR_RULES:
                content = GRAMMAR_RULES[rule_name]
                keyboard = {"inline_keyboard": [[{"text": "🔙 رجوع إلى القائمة", "callback_data": "back_to_grammar"}]]}
                if len(content) > 4000:
                    parts = [content[i:i+4000] for i in range(0, len(content), 4000)]
                    send_message(chat_id, parts[0], keyboard)
                    for part in parts[1:]:
                        send_message(chat_id, part)
                else:
                    send_message(chat_id, content, keyboard)
            else:
                send_message(chat_id, "❌ القاعدة غير موجودة")
            return "OK"
        
        # 7. رجوع إلى قائمة القواعد
        if cb_data == "back_to_grammar":
            delete_message(chat_id, msg_id)
            send_message(chat_id, "📚 **اختر القاعدة التي تريد دراستها:**", get_grammar_buttons())
            return "OK"
        
        # 8. اختيار الباقة
        if cb_data.startswith("sub_"):
            plan = cb_data.replace("sub_", "")
            amount = PRICES.get(plan, 50)
            numbers_text = "\n".join(SYRIATEL_NUMBERS)
            user_plan_choice[chat_id] = {"plan": plan, "amount": amount, "step": "waiting_transaction"}
            keyboard = {"inline_keyboard": [[{"text": "🔙 رجوع", "callback_data": "main_menu"}]]}
            edit_message(chat_id, msg_id,
                f"✅ **تم اختيار الباقة: {plan.replace('_', ' ')}**\n"
                f"💰 المبلغ: {amount} ل.س\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📞 **أرقام سيريتل كاش:**\n{numbers_text}\n\n"
                f"🔄 الرجاء إرسال المبلغ إلى أحد الأرقام أعلاه.\n\n"
                f"📌 بعد إتمام التحويل، أرسل **رقم عملية التحويل** (ID العملية).\n"
                f"مثال: `600044062208`", keyboard, "Markdown")
            return "OK"
        
        # 9. قبول اشتراك
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
                edit_message(chat_id, msg_id, f"✅ تم تفعيل الاشتراك بنجاح!")
                send_message(user_id, "🎉 **تم تفعيل اشتراكك بنجاح!**\n✅ يمكنك الآن الوصول إلى جميع محتويات البوت.")
            return "OK"
        
        # 10. رفض اشتراك
        if cb_data.startswith("reject_"):
            invoice_id = cb_data.split("_")[1]
            pending = load_pending()
            if invoice_id in pending:
                user_id = pending[invoice_id]["user_id"]
                del pending[invoice_id]
                save_pending(pending)
                edit_message(chat_id, msg_id, f"❌ تم رفض الطلب")
                send_message(user_id, "❌ **عذراً، لم يتم قبول طلب الاشتراك**\nيرجى مراجعة بيانات الدفع أو التواصل مع الدعم الفني.")
            return "OK"
        
        # 11. تشغيل الصوت
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
        
        # 12. أزرار التنقل والترجمة والتمارين
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
                    get_page_buttons(book_type, page_num, mode, min_page, max_page))
        return "OK"
    
    if 'message' in data:
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        user_id = msg['from']['id']
        
        logging.info(f"📨 رسالة من {user_id}: {text}")
        
        if text == '/start' or text == "🏠 الرئيسية":
            keyboard = get_user_menu(user_id)
            send_message(chat_id, "🎉 مرحباً بك! اختر من القائمة 👇", keyboard)
        
        elif text == "💳 اشتراك":
            keyboard = {"inline_keyboard": [[{"text": "1 شهر - 50 ل.س", "callback_data": "sub_1_month"}], [{"text": "🔙 رجوع", "callback_data": "main_menu"}]]}
            send_message(chat_id, "💳 **نظام الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━━━\nاختر الباقة المناسبة لك:", keyboard, "Markdown")
        
        elif text == "📖 كتاب الطالب":
            user_book_choice[user_id] = "student"
            send_message(chat_id, f"📖 كتاب الطالب - أرسل رقم الصفحة ({STUDENT_MIN}-{STUDENT_MAX}):")
        
        elif text == "✏️ كتاب الأنشطة":
            user_book_choice[user_id] = "activity"
            send_message(chat_id, f"✏️ كتاب الأنشطة - أرسل رقم الصفحة ({ACTIVITY_MIN}-{ACTIVITY_MAX}):")
        
        elif text == "📚 القواعد":
            if GRAMMAR_RULES:
                send_message(chat_id, "📚 **اختر القاعدة التي تريد دراستها:**", get_grammar_buttons())
            else:
                send_message(chat_id, "📚 لا توجد قواعد متوفرة حالياً.")
        
        elif text == "📝 تمارين":
            send_message(chat_id, "📝 **اختر المستوى:**", get_level_buttons())
        
        elif text == "📋 طلبات الاشتراك":
            show_pending_requests(chat_id, user_id)
        
        elif text == "👥 المشتركين":
            show_active_subscriptions(chat_id, user_id)
        
        elif text == "🛠️ الدعم الفني":
            contact_teacher(chat_id)
        
        elif re.match(r'^\d{5,}$', text.replace(" ", "")):
            pending = load_pending()
            invoice_id = random.randint(100000, 999999)
            plan_data = user_plan_choice.get(user_id, {"plan": "1_month", "amount": 50})
            pending[str(invoice_id)] = {
                "user_id": user_id,
                "username": msg['from'].get('username', ''),
                "first_name": msg['from'].get('first_name', ''),
                "amount": plan_data["amount"],
                "transaction_id": text,
                "plan": plan_data["plan"]
            }
            save_pending(pending)
            if user_id in user_plan_choice:
                del user_plan_choice[user_id]
            send_message(chat_id, f"✅ **تم استلام طلبك بنجاح!**\n📌 رقم العملية: `{text}`\n⏳ سيتم مراجعته قريباً.", parse_mode="Markdown")
            keyboard = {"inline_keyboard": [[{"text": "✅ قبول", "callback_data": f"approve_{invoice_id}"}, {"text": "❌ رفض", "callback_data": f"reject_{invoice_id}"}]]}
            send_message(ADMIN_ID, f"🔔 **طلب اشتراك جديد**\n👤 {msg['from'].get('first_name', '')}\n🆔 `{user_id}`\n💰 {plan_data['amount']} ل.س\n📌 {text}\n📌 رقم الطلب: {invoice_id}", keyboard, "Markdown")
        
        elif text.isdigit():
            selected_book = user_book_choice.get(user_id)
            if selected_book == "student":
                if text in STUDENT_PAGES:
                    page = STUDENT_PAGES[text]
                    send_message(chat_id, f"📖 **{page['title']}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{format_text(page.get('content_original', ''))}", get_page_buttons("student", text, "original", STUDENT_MIN, STUDENT_MAX))
                else:
                    send_message(chat_id, f"❌ الصفحة {text} غير موجودة في كتاب الطالب")
            elif selected_book == "activity":
                if text in ACTIVITY_PAGES:
                    page = ACTIVITY_PAGES[text]
                    send_message(chat_id, f"✏️ **{page['title']}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{format_text(page.get('content_original', ''))}", get_page_buttons("activity", text, "original", ACTIVITY_MIN, ACTIVITY_MAX))
                else:
                    send_message(chat_id, f"❌ الصفحة {text} غير موجودة في كتاب الأنشطة")
            else:
                send_message(chat_id, "❌ اختر كتاباً أولاً (📖 كتاب الطالب أو ✏️ كتاب الأنشطة)")
        
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
