import os
import json
import zipfile
import shutil
import re
import asyncio
import random
import sqlite3
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
FREE_REQUESTS = 10

# تخزين مؤقت
user_book_choice = {}
user_plan_choice = {}
user_test_data = {}

# ==================== دوال مساعدة مع حماية المحتوى ====================
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    data = {
        "chat_id": chat_id, 
        "text": text,
        "protect_content": True
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    if parse_mode:
        data["parse_mode"] = parse_mode
    return requests.post(URL + "/sendMessage", json=data)

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode=None):
    data = {
        "chat_id": chat_id, 
        "message_id": message_id, 
        "text": text,
        "protect_content": True
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    if parse_mode:
        data["parse_mode"] = parse_mode
    return requests.post(URL + "/editMessageText", json=data)

def delete_message(chat_id, message_id):
    return requests.post(URL + "/deleteMessage", json={"chat_id": chat_id, "message_id": message_id})

def send_voice(chat_id, voice_path):
    with open(voice_path, 'rb') as audio:
        files = {'voice': audio}
        data = {"chat_id": chat_id, "protect_content": True}
        return requests.post(URL + "/sendVoice", files=files, data=data)

# ==================== قاعدة بيانات SQLite ====================
DB_PATH = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_usage
                 (user_id TEXT PRIMARY KEY, used INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                 (user_id TEXT PRIMARY KEY, expiry TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_requests
                 (invoice_id TEXT PRIMARY KEY, user_id TEXT, username TEXT, 
                  first_name TEXT, amount INTEGER, transaction_id TEXT, plan TEXT)''')
    conn.commit()
    conn.close()
    print("✅ قاعدة البيانات جاهزة")

def get_user_usage(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT used FROM user_usage WHERE user_id = ?", (str(user_id),))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def increment_user_usage(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO user_usage (user_id, used) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET used = used + 1", (str(user_id),))
    conn.commit()
    conn.close()

def reset_user_usage(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE user_usage SET used = 0 WHERE user_id = ?", (str(user_id),))
    conn.commit()
    conn.close()

def load_subs():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, expiry FROM subscriptions")
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def save_subs(subs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM subscriptions")
    for user_id, expiry in subs.items():
        c.execute("INSERT INTO subscriptions (user_id, expiry) VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    conn.close()

def is_subscribed(user_id):
    subs = load_subs()
    expiry = subs.get(str(user_id))
    return expiry and datetime.now().isoformat() < expiry

def load_pending():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT invoice_id, user_id, username, first_name, amount, transaction_id, plan FROM pending_requests")
    rows = c.fetchall()
    conn.close()
    pending = {}
    for row in rows:
        pending[row[0]] = {
            "user_id": row[1],
            "username": row[2],
            "first_name": row[3],
            "amount": row[4],
            "transaction_id": row[5],
            "plan": row[6]
        }
    return pending

def save_pending(pending):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM pending_requests")
    for invoice_id, p in pending.items():
        c.execute("INSERT INTO pending_requests (invoice_id, user_id, username, first_name, amount, transaction_id, plan) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (invoice_id, p["user_id"], p.get("username", ""), p.get("first_name", ""), p["amount"], p.get("transaction_id", ""), p["plan"]))
    conn.commit()
    conn.close()

def remove_pending_request(invoice_id):
    pending = load_pending()
    if invoice_id in pending:
        del pending[invoice_id]
        save_pending(pending)

# ==================== دوال الاستخدام ====================
def check_and_deduct_request(user_id):
    if user_id == ADMIN_ID or is_subscribed(user_id):
        return True
    used = get_user_usage(user_id)
    if used >= FREE_REQUESTS:
        return False
    increment_user_usage(user_id)
    return True

def get_remaining_requests(user_id):
    if user_id == ADMIN_ID or is_subscribed(user_id):
        return "غير محدود"
    used = get_user_usage(user_id)
    remaining = FREE_REQUESTS - used
    return max(0, remaining)

def get_usage_message(user_id):
    if user_id == ADMIN_ID:
        return "👑 أنت المسؤول، لديك وصول غير محدود"
    if is_subscribed(user_id):
        subs = load_subs()
        expiry = subs.get(str(user_id), "")
        expiry_date = expiry[:10] if expiry else "غير محدد"
        return f"✅ **مشترك نشط**\n📅 ينتهي: {expiry_date}\n🎉 وصول غير محدود"
    remaining = get_remaining_requests(user_id)
    if remaining == 0:
        return f"⚠️ **لقد انتهت طلباتك المجانية!**\n💳 اشترك بـ 50 ل.س فقط للوصول غير المحدود"
    return f"📊 **الطلبات المجانية المتبقية:** {remaining} من {FREE_REQUESTS}"

def reset_user_requests_on_subscription(user_id):
    reset_user_usage(user_id)

# ==================== القوائم ====================
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

def get_user_menu(user_id):
    if user_id == ADMIN_ID:
        return admin_menu
    elif is_subscribed(user_id):
        return subscribed_menu
    else:
        return unsubscribed_menu

# ==================== تحميل البيانات ====================
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

# ==================== تحميل الاختبارات ====================
TESTS_BY_LEVEL = {
    "beginner_1": [],
    "beginner_2": [],
    "intermediate_1": [],
    "intermediate_2": [],
    "advanced": []
}

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
    
    for level in TESTS_BY_LEVEL:
        TESTS_BY_LEVEL[level] = []
    
    for root, dirs, files in os.walk(extract_dir):
        level = os.path.basename(root)
        if level not in TESTS_BY_LEVEL:
            continue
        
        for file in files:
            if file.endswith(".json"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        grammar_name = data.get("grammar_name")
                        if grammar_name:
                            tests[grammar_name] = {
                                "data": data,
                                "level": level
                            }
                            TESTS_BY_LEVEL[level].append(grammar_name)
                            print(f"✅ {grammar_name} → {level}")
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

init_db()

STUDENT_LIST = sorted([int(p) for p in STUDENT_PAGES.keys()])
ACTIVITY_LIST = sorted([int(p) for p in ACTIVITY_PAGES.keys()])

STUDENT_MIN = min(STUDENT_LIST) if STUDENT_LIST else 1
STUDENT_MAX = max(STUDENT_LIST) if STUDENT_LIST else 80
ACTIVITY_MIN = min(ACTIVITY_LIST) if ACTIVITY_LIST else 1
ACTIVITY_MAX = max(ACTIVITY_LIST) if ACTIVITY_LIST else 64

print(f"✅ كتاب الطالب: {len(STUDENT_PAGES)} صفحة")
print(f"✅ كتاب الأنشطة: {len(ACTIVITY_PAGES)} صفحة")
print(f"✅ القواعد: {len(GRAMMAR_RULES)} قاعدة")
print(f"✅ الاختبارات: {len(TESTS)}")

print("📊 المستويات:")
for level, tests_list in TESTS_BY_LEVEL.items():
    print(f"   {level}: {len(tests_list)} اختبار")

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
    for test_name in TESTS_BY_LEVEL.get(level_id, []):
        if test_name in TESTS:
            display_name = test_name.replace("_", " ").title()
            buttons.append([{"text": f"📝 {display_name}", "callback_data": f"test_{test_name}"}])
    buttons.append([{"text": "🔙 رجوع", "callback_data": "back_to_levels"}])
    return {"inline_keyboard": buttons}

# ==================== دوال الاختبارات ====================
def start_test(chat_id, user_id, test_name):
    if not check_and_deduct_request(user_id):
        remaining = get_remaining_requests(user_id)
        send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ رصيدك المتبقي: {remaining}\n\n💳 اشترك الآن بـ 50 ل.س فقط للوصول غير المحدود", parse_mode="Markdown")
        return
    
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
    
    question_text = q['text'].replace('*', '').replace('_', '').replace('`', '')
    
    text = f"📝 *{data['test_title']}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n*السؤال {current + 1} من {data['total']}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n❓ {question_text}\n\n📌 اختر الإجابة الصحيحة:"
    
    buttons = []
    for i, opt in enumerate(q["options"]):
        opt_text = str(opt).replace('*', '').replace('_', '').replace('`', '')
        buttons.append([{"text": f"{i+1}. {opt_text}", "callback_data": f"test_ans_{current}_{i}"}])
    
    keyboard = {"inline_keyboard": buttons}
    send_message(chat_id, text, keyboard, "Markdown")

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
    if user_id == ADMIN_ID:
        text = "👑 **المسؤول**\n━━━━━━━━━━━━━━━━━━━━━━━━\n✅ وصول غير محدود"
    elif is_subscribed(user_id):
        subs = load_subs()
        expiry = subs.get(str(user_id), "")
        expiry_date = expiry[:10] if expiry else "غير محدد"
        text = f"✅ **مشترك نشط**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📅 ينتهي: {expiry_date}\n🎉 وصول غير محدود"
    else:
        used = get_user_usage(user_id)
        remaining = FREE_REQUESTS - used
        text = f"📊 **رصيد الطلبات المجانية**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🎟️ المتبقي: {remaining} من {FREE_REQUESTS}\n\n💳 اشترك الآن بـ 50 ل.س فقط للوصول غير المحدود\n\n📞 سيريتل كاش: 15570270"
    send_message(chat_id, text, parse_mode="Markdown")

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
        
        if cb_data.startswith("test_ans_"):
            parts = cb_data.split("_")
            if len(parts) >= 3:
                q_idx = int(parts[2])
                a_idx = int(parts[3])
                handle_test_answer(chat_id, user_id, q_idx, a_idx)
            return "OK"
        
        if cb_data.startswith("test_"):
            test_name = cb_data.replace("test_", "")
            delete_message(chat_id, msg_id)
            start_test(chat_id, user_id, test_name)
            return "OK"
        
        if cb_data.startswith("level_"):
            level_id = cb_data.replace("level_", "")
            delete_message(chat_id, msg_id)
            send_message(chat_id, f"📝 **اختر الاختبار:**", get_test_buttons(level_id))
            return "OK"
        
        if cb_data == "back_to_levels":
            delete_message(chat_id, msg_id)
            send_message(chat_id, "📝 **اختر المستوى:**", get_level_buttons())
            return "OK"
        
        if cb_data == "main_menu":
            keyboard = get_user_menu(chat_id)
            delete_message(chat_id, msg_id)
            send_message(chat_id, "🎉 مرحباً بك! اختر من القائمة 👇", keyboard)
            return "OK"
        
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
        
        if cb_data == "back_to_grammar":
            delete_message(chat_id, msg_id)
            send_message(chat_id, "📚 **اختر القاعدة التي تريد دراستها:**", get_grammar_buttons())
            return "OK"
        
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
        
        if cb_data.startswith("approve_"):
            invoice_id = cb_data.split("_")[1]
            pending = load_pending()
            if invoice_id in pending:
                user_id = pending[invoice_id]["user_id"]
                expiry = (datetime.now() + timedelta(days=30)).isoformat()
                subs = load_subs()
                subs[str(user_id)] = expiry
                save_subs(subs)
                reset_user_requests_on_subscription(user_id)
                remove_pending_request(invoice_id)
                edit_message(chat_id, msg_id, f"✅ تم تفعيل الاشتراك بنجاح!")
                send_message(user_id, "🎉 **تم تفعيل اشتراكك بنجاح!**\n✅ يمكنك الآن الوصول إلى جميع محتويات البوت.")
            return "OK"
        
        if cb_data.startswith("reject_"):
            invoice_id = cb_data.split("_")[1]
            pending = load_pending()
            if invoice_id in pending:
                user_id = pending[invoice_id]["user_id"]
                remove_pending_request(invoice_id)
                edit_message(chat_id, msg_id, f"❌ تم رفض الطلب")
                send_message(user_id, "❌ **عذراً، لم يتم قبول طلب الاشتراك**\nيرجى مراجعة بيانات الدفع أو التواصل مع الدعم الفني.")
            return "OK"
        
        if cb_data.startswith("audio_"):
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n🎟️ رصيدك المتبقي: {remaining}\n💳 اشترك الآن للوصول غير المحدود", parse_mode="Markdown")
                return "OK"
            parts = cb_data.split("_")
            prefix = parts[1]
            page_num = parts[2]
            send_message(chat_id, "🎵 جاري تجهيز الصوت...")
            pages = STUDENT_PAGES if prefix == "student" else ACTIVITY_PAGES
            if page_num in pages:
                text = pages[page_num].get("content_original", "")
                audio_path = text_to_audio(text, prefix, page_num)
                if audio_path and os.path.exists(audio_path):
                    send_voice(chat_id, audio_path)
                else:
                    send_message(chat_id, "❌ عذراً، حدث خطأ في إنشاء الصوت")
            return "OK"
        
        parts = cb_data.split("_")
        if len(parts) >= 3:
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n🎟️ رصيدك المتبقي: {remaining}\n💳 اشترك الآن للوصول غير المحدود", parse_mode="Markdown")
                return "OK"
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
        
        if text == "📊 رصيدي":
            show_my_balance(chat_id, user_id)
            return "OK"
        
        if text == '/start' or text == "🏠 الرئيسية":
            keyboard = get_user_menu(user_id)
            remaining_msg = get_usage_message(user_id)
            send_message(chat_id, f"🎉 مرحباً بك!\n\n{remaining_msg}", keyboard)
        
        elif text == "💳 اشتراك":
            keyboard = {"inline_keyboard": [[{"text": "1 شهر - 50 ل.س", "callback_data": "sub_1_month"}], [{"text": "🔙 رجوع", "callback_data": "main_menu"}]]}
            send_message(chat_id, "💳 **نظام الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━━━\nاختر الباقة المناسبة لك:", keyboard, "Markdown")
        
        elif text == "📖 كتاب الطالب":
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n🎟️ رصيدك المتبقي: {remaining}\n💳 اشترك الآن للوصول غير المحدود", parse_mode="Markdown")
                return "OK"
            user_book_choice[user_id] = "student"
            send_message(chat_id, f"📖 كتاب الطالب - أرسل رقم الصفحة ({STUDENT_MIN}-{STUDENT_MAX}):")
        
        elif text == "✏️ كتاب الأنشطة":
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n🎟️ رصيدك المتبقي: {remaining}\n💳 اشترك الآن للوصول غير المحدود", parse_mode="Markdown")
                return "OK"
            user_book_choice[user_id] = "activity"
            send_message(chat_id, f"✏️ كتاب الأنشطة - أرسل رقم الصفحة ({ACTIVITY_MIN}-{ACTIVITY_MAX}):")
        
        elif text == "📚 القواعد":
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n🎟️ رصيدك المتبقي: {remaining}\n💳 اشترك الآن للوصول غير المحدود", parse_mode="Markdown")
                return "OK"
            if GRAMMAR_RULES:
                send_message(chat_id, "📚 **اختر القاعدة التي تريد دراستها:**", get_grammar_buttons())
            else:
                send_message(chat_id, "📚 لا توجد قواعد متوفرة حالياً.")
        
        elif text == "📝 تمارين":
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n🎟️ رصيدك المتبقي: {remaining}\n💳 اشترك الآن للوصول غير المحدود", parse_mode="Markdown")
                return "OK"
            send_message(chat_id, "📝 **اختر المستوى:**", get_level_buttons())
        
        elif text == "📋 طلبات الاشتراك":
            show_pending_requests(chat_id, user_id)
        
        elif text == "👥 المشتركين":
            show_active_subscriptions(chat_id, user_id)
        
        elif text == "🛠️ الدعم الفني":
            contact_teacher(chat_id)
        
        elif re.match(r'^\d{5,}$', text.replace(" ", "")):
            pending = load_pending()
            invoice_id = str(random.randint(100000, 999999))
            plan_data = user_plan_choice.get(user_id, {"plan": "1_month", "amount": 50})
            pending[invoice_id] = {
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
            if not check_and_deduct_request(user_id):
                remaining = get_remaining_requests(user_id)
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n🎟️ رصيدك المتبقي: {remaining}\n💳 اشترك الآن للوصول غير المحدود", parse_mode="Markdown")
                return "OK"
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
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
