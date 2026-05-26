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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ BOT_TOKEN غير موجود")
    exit(1)

URL = f"https://api.telegram.org/bot{TOKEN}"
ADMIN_ID = 1662780469  # ضع معرفك هنا
SYRIATEL_NUMBERS = ["15570270"]
FREE_REQUESTS = 10

# سرعات الصوت
VOICE_RATES = {"بطيء": "-30%", "عادي": "-15%", "سريع": "+1%"}

user_book_choice = {}
user_test_data = {}

# ==================== نظام الاشتراك البسيط ====================

DATA_FILE = "data.json"

def load_data():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"subs": {}, "pending": [], "usage": {}}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_subscribed(user_id):
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str in data.get("subs", {}):
        expiry = data["subs"][user_id_str].get("expiry", "")
        return expiry and datetime.now().isoformat() < expiry
    return False

def add_subscription(user_id):
    data = load_data()
    expiry = (datetime.now() + timedelta(days=30)).isoformat()
    data["subs"][str(user_id)] = {
        "expiry": expiry,
        "subscribed_at": datetime.now().isoformat()
    }
    save_data(data)
    print(f"✅ تم إضافة اشتراك للمستخدم {user_id}")

def add_pending(user_id, transaction_id, first_name, username):
    data = load_data()
    request_id = str(random.randint(10000, 99999))
    if "pending" not in data:
        data["pending"] = []
    data["pending"].append({
        "id": request_id,
        "user_id": user_id,
        "transaction_id": transaction_id,
        "first_name": first_name,
        "username": username,
        "created_at": datetime.now().isoformat()
    })
    save_data(data)
    return request_id

def get_pending():
    data = load_data()
    return data.get("pending", [])

def remove_pending(request_id):
    data = load_data()
    data["pending"] = [r for r in data.get("pending", []) if r["id"] != request_id]
    save_data(data)

def get_user_usage(user_id):
    data = load_data()
    return data.get("usage", {}).get(str(user_id), 0)

def increment_user_usage(user_id):
    data = load_data()
    if "usage" not in data:
        data["usage"] = {}
    data["usage"][str(user_id)] = data["usage"].get(str(user_id), 0) + 1
    save_data(data)

def reset_user_usage(user_id):
    data = load_data()
    if "usage" in data:
        data["usage"][str(user_id)] = 0
        save_data(data)

def check_and_deduct_request(user_id):
    if user_id == ADMIN_ID:
        return True
    if is_subscribed(user_id):
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
        return "✅ **مشترك نشط**\n🎉 وصول غير محدود لمدة 30 يوماً"
    remaining = get_remaining_requests(user_id)
    if remaining == 0:
        return f"⚠️ **لقد انتهت طلباتك المجانية!**\n💳 اشترك الآن بـ 50 ل.س فقط"
    return f"📊 **الطلبات المجانية المتبقية:** {remaining} من {FREE_REQUESTS}"

# ==================== دوال مساعدة ====================
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "text": text, "protect_content": True}
    if reply_markup:
        data["reply_markup"] = reply_markup
    if parse_mode:
        data["parse_mode"] = parse_mode
    return requests.post(URL + "/sendMessage", json=data)

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "protect_content": True}
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

# ==================== تحميل الكتب والملفات ====================

def load_pages_from_zip(zip_path):
    pages = {}
    
    if not os.path.exists(zip_path):
        print(f"⚠️ الملف {zip_path} غير موجود")
        return pages
    
    extract_dir = zip_path.replace(".zip", "_extracted")
    
    try:
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
        print(f"✅ تم فك ضغط {os.path.basename(zip_path)}")
    except Exception as e:
        print(f"❌ خطأ في فك الضغط: {e}")
        return pages
    
    json_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".json"):
                json_files.append(os.path.join(root, file))
    
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            filename = os.path.basename(file_path)
            page_match = re.search(r'(\d+)', filename)
            page_num = page_match.group(1) if page_match else None
            
            if not page_num:
                continue
            
            actual_data = data
            if isinstance(data, dict) and page_num in data:
                actual_data = data[page_num]
            elif isinstance(data, dict):
                for key, value in data.items():
                    if str(key).isdigit() and isinstance(value, dict):
                        actual_data = value
                        page_num = str(key)
                        break
            
            if not isinstance(actual_data, dict):
                continue
            
            translation = actual_data.get("content_line_by_line", [])
            if not translation:
                translation = actual_data.get("translation", [])
            
            cleaned_translation = []
            if translation and isinstance(translation, list):
                for item in translation:
                    if isinstance(item, dict):
                        en_text = item.get("en", "")
                        ar_text = item.get("ar", "")
                        if en_text or ar_text:
                            cleaned_translation.append({"en": en_text, "ar": ar_text})
            
            pages[page_num] = {
                "title": actual_data.get("title", f"صفحة {page_num}"),
                "content_original": actual_data.get("content_original", actual_data.get("content", "")),
                "content_line_by_line": cleaned_translation,
                "exercises": actual_data.get("exercises", actual_data.get("solved", []))
            }
            
        except Exception as e:
            print(f"⚠️ خطأ في تحميل {file_path}: {e}")
    
    try:
        shutil.rmtree(extract_dir)
    except:
        pass
    
    return pages

def load_grammar_rules():
    rules = {}
    zip_path = "lessons.zip"
    
    if not os.path.exists(zip_path):
        return rules
    
    extract_dir = "lessons_temp"
    
    try:
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
    except Exception as e:
        print(f"❌ خطأ في فك ضغط القواعد: {e}")
        return rules
    
    txt_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".txt"):
                txt_files.append(os.path.join(root, file))
    
    for file_path in txt_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                filename = os.path.basename(file_path)
                rule_name = filename.replace(".txt", "")
                rules[rule_name] = clean_text_for_telegram(content)
        except Exception as e:
            print(f"⚠️ خطأ في {file_path}: {e}")
    
    try:
        shutil.rmtree(extract_dir)
    except:
        pass
    
    return rules

# ==================== الاختبارات ====================
TESTS_BY_LEVEL = {
    "beginner_1": [], "beginner_2": [], "intermediate_1": [], "intermediate_2": [], "advanced": []
}

def load_tests():
    tests = {}
    zip_path = "tests.zip"
    
    if not os.path.exists(zip_path):
        return tests
    
    extract_dir = "tests_temp"
    
    try:
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
    except Exception as e:
        print(f"❌ خطأ في فك ضغط الاختبارات: {e}")
        return tests
    
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
                        grammar_name = data.get("grammar_name", file.replace(".json", ""))
                        if grammar_name:
                            tests[grammar_name] = {"data": data, "level": level}
                            TESTS_BY_LEVEL[level].append(grammar_name)
                except Exception as e:
                    print(f"⚠️ خطأ في تحميل الاختبار {file_path}: {e}")
    
    try:
        shutil.rmtree(extract_dir)
    except:
        pass
    
    return tests

# ==================== دوال تنظيف النص ====================
def clean_text_for_telegram(text):
    if not text:
        return text
    text = text.replace('┌', '').replace('┐', '').replace('└', '').replace('┘', '')
    text = text.replace('├', '').replace('┤', '').replace('─', '').replace('│', '')
    text = text.replace('█', '').replace('░', '').replace('▒', '').replace('▓', '')
    text = text.replace('┃', '').replace('━', '').replace('┏', '').replace('┓', '')
    text = text.replace('┗', '').replace('┛', '')
    text = re.sub(r'\n{4,}', '\n\n', text)
    return text.strip()

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

def format_translation(translation_lines):
    if not translation_lines:
        return None, ["🚫 **لا توجد ترجمة متوفرة لهذه الصفحة**"]
    
    MAX_LENGTH = 3800
    all_parts = []
    current_part = "🌐 **الترجمة إلى العربية**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    current_length = len(current_part)
    part_index = 0
    
    for item in translation_lines:
        if isinstance(item, dict):
            en_text = item.get('en', '')
            ar_text = item.get('ar', '')
            
            if en_text and ar_text:
                line = f"📖 **{en_text}**\n🌐 {ar_text}\n\n"
            elif ar_text and not en_text:
                line = f"🌐 {ar_text}\n\n"
            else:
                continue
            
            if current_length + len(line) > MAX_LENGTH:
                all_parts.append(current_part)
                part_index += 1
                current_part = f"🌐 **الترجمة إلى العربية (الجزء {part_index + 1})**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                current_length = len(current_part)
            
            current_part += line
            current_length += len(line)
    
    if current_part and current_part != "🌐 **الترجمة إلى العربية**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n":
        all_parts.append(current_part)
    
    if not all_parts:
        return None, ["🚫 **لا توجد ترجمة متوفرة لهذه الصفحة**"]
    
    return len(all_parts), all_parts

def format_exercises(exercises):
    if not exercises:
        return "لا توجد تمارين في هذه الصفحة"
    result = "📝 **حلول التمارين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, ex in enumerate(exercises, 1):
        if isinstance(ex, dict):
            question = ex.get('text') or ex.get('question') or f'سؤال {i}'
            answer = ex.get('answer') or ex.get('a') or '---'
            if isinstance(answer, list):
                answer = ', '.join(str(a) for a in answer)
            result += f"**{i}. {question}**\n✅ {answer}\n\n"
        elif isinstance(ex, str):
            result += f"**{i}. {ex[:200]}**\n\n"
    return result

# ==================== دالة الصوت ====================
def text_to_audio(text, book_type, page_num, speed="عادي"):
    audio_dir = "audio"
    os.makedirs(audio_dir, exist_ok=True)
    
    clean_text = text.replace('*', '').replace('_', '').replace('`', '')
    clean_text = clean_text.replace('━', '').replace('**', '').replace('|', '')
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    lines = clean_text.split('\n')
    english_parts = []
    for line in lines:
        arabic_chars = sum(1 for c in line if '\u0600' <= c <= '\u06FF')
        total_chars = len(line.strip())
        if total_chars > 0:
            arabic_ratio = arabic_chars / total_chars
            if arabic_ratio < 0.5:
                english_parts.append(line)
    
    clean_text = ' '.join(english_parts)
    
    if not clean_text or len(clean_text.strip()) < 10:
        clean_text = f"Page {page_num} of {book_type} book."
    
    rate = VOICE_RATES.get(speed, "-15%")
    audio_filename = f"{book_type}_{page_num}_{speed}.mp3"
    audio_path = os.path.join(audio_dir, audio_filename)
    
    if os.path.exists(audio_path):
        return audio_path
    
    async def _gen():
        try:
            communicate = edge_tts.Communicate(clean_text[:3000], "en-US-JennyNeural", rate=rate)
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

# ==================== دوال الأزرار ====================
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
            {"text": "🔊 الصوت", "callback_data": f"audio_speed_{prefix}_{page_num}"},
            {"text": "📝 حل التمارين", "callback_data": f"{prefix}_solved_{page_num}"}
        ])
    elif mode == 'translated':
        buttons.append([
            {"text": "🔤 النص الأصلي", "callback_data": f"{prefix}_original_{page_num}"},
            {"text": "📝 حل التمارين", "callback_data": f"{prefix}_solved_{page_num}"}
        ])
    elif mode == 'solved':
        buttons.append([
            {"text": "🔤 النص الأصلي", "callback_data": f"{prefix}_original_{page_num}"},
            {"text": "🌐 الترجمة", "callback_data": f"{prefix}_translated_{page_num}"}
        ])
    
    buttons.append([{"text": "🏠 القائمة الرئيسية", "callback_data": "main_menu"}])
    return {"inline_keyboard": buttons}

def get_audio_speed_buttons(book_type, page_num):
    prefix = "student" if book_type == "student" else "activity"
    return {
        "inline_keyboard": [
            [
                {"text": "🐢 بطيء", "callback_data": f"audio_{prefix}_{page_num}_بطيء"},
                {"text": "🐕 عادي", "callback_data": f"audio_{prefix}_{page_num}_عادي"},
                {"text": "🐇 سريع", "callback_data": f"audio_{prefix}_{page_num}_سريع"}
            ],
            [{"text": "🔙 رجوع", "callback_data": f"{prefix}_original_{page_num}"}]
        ]
    }

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
        send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n🎟️ رصيدك المتبقي: {remaining}\n💳 اشترك الآن بـ 50 ل.س فقط", parse_mode="Markdown")
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
        send_message(chat_id, "❌ انتهت الجلسة. ابدأ اختباراً جديداً.")
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
    send_message(chat_id, text, {"inline_keyboard": buttons}, "Markdown")

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
    text = f"📊 **نتيجة الاختبار**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 {data['test_title']}\n✅ {data['score']} من {data['total']}\n📈 النسبة: {percentage:.0f}%\n⭐ {rating}\n\n🔙 اضغط /start للعودة"
    send_message(chat_id, text, {"keyboard": [["🏠 الرئيسية"]], "resize_keyboard": True}, "Markdown")

def handle_test_answer(chat_id, user_id, question_idx, answer_idx):
    data = user_test_data.get(user_id)
    if not data or question_idx != data["current"]:
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

# ==================== دوال الإدارة ====================

def show_pending_requests(chat_id, user_id):
    if user_id != ADMIN_ID:
        send_message(chat_id, "❌ هذا الأمر للمسؤول فقط.")
        return
    
    pending = get_pending()
    if not pending:
        send_message(chat_id, "📭 لا توجد طلبات اشتراك معلقة.")
        return
    
    for p in pending:
        text = f"🔔 **طلب اشتراك جديد**\n"
        text += f"👤 {p.get('first_name', 'مستخدم')}\n"
        text += f"🆔 `{p['user_id']}`\n"
        text += f"💰 50 ل.س\n"
        text += f"📌 رقم العملية: `{p['transaction_id']}`\n"
        text += f"📌 رقم الطلب: `{p['id']}`"
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ قبول", "callback_data": f"approve_{p['id']}"},
                    {"text": "❌ رفض", "callback_data": f"reject_{p['id']}"}
                ]
            ]
        }
        send_message(chat_id, text, keyboard, "Markdown")

def show_active_subscriptions(chat_id, user_id):
    if user_id != ADMIN_ID:
        send_message(chat_id, "❌ هذا الأمر للمسؤول فقط.")
        return
    
    data = load_data()
    subscriptions = data.get("subs", {})
    if not subscriptions:
        send_message(chat_id, "📭 لا يوجد مشتركين حالياً.")
        return
    
    text = "👥 **المشتركين الحاليين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for uid, info in subscriptions.items():
        expiry = info.get("expiry", "غير محدد")[:10]
        text += f"\n🆔 `{uid}`\n📅 ينتهي: {expiry}\n"
    send_message(chat_id, text, parse_mode="Markdown")

def contact_teacher(chat_id):
    keyboard = {"inline_keyboard": [[{"text": "🛠️ الدعم الفني", "url": "https://t.me/ENGWALI1"}]]}
    send_message(chat_id, "🛠️ اضغط على الزر أدناه للتواصل مع الدعم الفني:", keyboard)

def show_my_balance(chat_id, user_id):
    send_message(chat_id, get_usage_message(user_id), parse_mode="Markdown")

# ==================== تحميل جميع البيانات ====================
print("="*60)
print("🚀 بدء تشغيل بوت تلغرام")
print("="*60)

print("\n📚 تحميل كتاب الطالب...")
STUDENT_PAGES = load_pages_from_zip("student_pages.zip")

print("\n📚 تحميل كتاب الأنشطة...")
ACTIVITY_PAGES = load_pages_from_zip("activity_pages.zip")

print("\n📚 تحميل القواعد النحوية...")
GRAMMAR_RULES = load_grammar_rules()

print("\n📚 تحميل الاختبارات...")
TESTS = load_tests()

# تحميل البيانات
data = load_data()
print(f"\n📁 بيانات المشتركين: {len(data.get('subs', {}))} مشترك")
print(f"📋 طلبات معلقة: {len(data.get('pending', []))}")

STUDENT_LIST = sorted([int(p) for p in STUDENT_PAGES.keys()])
ACTIVITY_LIST = sorted([int(p) for p in ACTIVITY_PAGES.keys()])

STUDENT_MIN = min(STUDENT_LIST) if STUDENT_LIST else 1
STUDENT_MAX = max(STUDENT_LIST) if STUDENT_LIST else 80
ACTIVITY_MIN = min(ACTIVITY_LIST) if ACTIVITY_LIST else 1
ACTIVITY_MAX = max(ACTIVITY_LIST) if ACTIVITY_LIST else 64

print("\n" + "="*60)
print("📊 ملخص التحميل")
print("="*60)
print(f"📖 كتاب الطالب: {len(STUDENT_PAGES)} صفحة")
print(f"✏️ كتاب الأنشطة: {len(ACTIVITY_PAGES)} صفحة")
print(f"📚 القواعد: {len(GRAMMAR_RULES)} قاعدة")
print(f"📝 الاختبارات: {len(TESTS)} اختبار")
print(f"👥 المشتركين: {len(data.get('subs', {}))}")
print(f"👑 معرف المسؤول: {ADMIN_ID}")
print("="*60)
print("✅ البوت جاهز للعمل!")
print("="*60)

# ==================== معالج Webhook ====================
@app.route('/')
def home():
    return "🤖 Bot is running!"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data:
        return "OK"
    
    # معالجة الأزرار (Callback Queries)
    if 'callback_query' in data:
        cb = data['callback_query']
        cb_data = cb['data']
        chat_id = cb['message']['chat']['id']
        msg_id = cb['message']['message_id']
        user_id = cb['from']['id']
        
        print(f"📨 Callback مستلم: {cb_data} من المستخدم {user_id}")
        
        # قبول طلب اشتراك
        if cb_data.startswith("approve_"):
            request_id = cb_data.split("_")[1]
            
            if user_id != ADMIN_ID:
                send_message(chat_id, "❌ هذا الأمر للمسؤول فقط.")
                return "OK"
            
            pending = get_pending()
            found = None
            for r in pending:
                if r["id"] == request_id:
                    found = r
                    break
            
            if found:
                add_subscription(found["user_id"])
                remove_pending(request_id)
                edit_message(chat_id, msg_id, "✅ تم تفعيل الاشتراك بنجاح!")
                send_message(found["user_id"], "🎉 **تم تفعيل اشتراكك بنجاح!**\n📅 صالح لمدة 30 يوماً")
                print(f"✅ تم قبول طلب {request_id}")
            else:
                edit_message(chat_id, msg_id, f"❌ الطلب {request_id} غير موجود")
            return "OK"
        
        # رفض طلب اشتراك
        if cb_data.startswith("reject_"):
            request_id = cb_data.split("_")[1]
            
            if user_id != ADMIN_ID:
                send_message(chat_id, "❌ هذا الأمر للمسؤول فقط.")
                return "OK"
            
            pending = get_pending()
            found = None
            for r in pending:
                if r["id"] == request_id:
                    found = r
                    break
            
            if found:
                remove_pending(request_id)
                edit_message(chat_id, msg_id, "❌ تم رفض الطلب")
                send_message(found["user_id"], "❌ **عذراً، لم يتم قبول طلب الاشتراك**")
                print(f"❌ تم رفض طلب {request_id}")
            else:
                edit_message(chat_id, msg_id, f"❌ الطلب {request_id} غير موجود")
            return "OK"
        
        # زر الاشتراك
        if cb_data == "subscribe_now":
            keyboard = {"inline_keyboard": [[{"text": "🔙 رجوع", "callback_data": "main_menu"}]]}
            send_message(chat_id, 
                "💳 **نظام الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💰 المبلغ: 50 ل.س فقط\n\n"
                "📞 **أرقام سيريتل كاش:**\n"
                "15570270\n\n"
                "🔄 بعد إتمام التحويل، أرسل **رقم العملية**\n"
                "مثال: `600044062208`", 
                keyboard, "Markdown")
            return "OK"
        
        # معالجة أزرار الصفحات والكتب
        parts = cb_data.split("_")
        if len(parts) >= 3 and (parts[0] == "student" or parts[0] == "activity"):
            if not check_and_deduct_request(user_id):
                send_message(chat_id, f"⚠️ **لقد انتهت طلباتك المجانية!**\n💳 اشترك الآن بـ 50 ل.س فقط", parse_mode="Markdown")
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
                    edit_message(chat_id, msg_id, 
                               f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}", 
                               get_page_buttons(book_type, page_num, mode, min_page, max_page))
                    
                elif action == "translated":
                    translation = page.get("content_line_by_line", [])
                    num_parts, translation_parts = format_translation(translation)
                    
                    if num_parts is None:
                        edit_message(chat_id, msg_id, 
                                   f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{translation_parts[0]}", 
                                   get_page_buttons(book_type, page_num, "original", min_page, max_page))
                    else:
                        mode = "translated"
                        edit_message(chat_id, msg_id, 
                                   f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{translation_parts[0]}", 
                                   get_page_buttons(book_type, page_num, mode, min_page, max_page))
                        for part in translation_parts[1:]:
                            send_message(chat_id, part)
                    
                elif action == "solved":
                    content = format_exercises(page.get("exercises", []))
                    mode = "solved"
                    edit_message(chat_id, msg_id, 
                               f"📖 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}", 
                               get_page_buttons(book_type, page_num, mode, min_page, max_page))
            return "OK"
        
        if cb_data == "back_to_grammar":
            delete_message(chat_id, msg_id)
            send_message(chat_id, "📚 **اختر القاعدة التي تريد دراستها:**", get_grammar_buttons())
            return "OK"
        
        if cb_data == "back_to_levels":
            delete_message(chat_id, msg_id)
            send_message(chat_id, "📝 **اختر المستوى:**", get_level_buttons())
            return "OK"
        
        if cb_data == "main_menu":
            delete_message(chat_id, msg_id)
            send_message(chat_id, "🎉 مرحباً بك! اختر من القائمة 👇", get_user_menu(chat_id))
            return "OK"
        
        # معالجة بقية الأزرار (قواعد، اختبارات، صوت)
        if cb_data.startswith("grammar_"):
            rule_name = cb_data.replace("grammar_", "")
            if rule_name in GRAMMAR_RULES:
                content = GRAMMAR_RULES[rule_name]
                keyboard = {"inline_keyboard": [[{"text": "🔙 رجوع", "callback_data": "back_to_grammar"}]]}
                if len(content) <= 4000:
                    send_message(chat_id, content, keyboard)
                else:
                    parts = [content[i:i+4000] for i in range(0, len(content), 4000)]
                    for i, part in enumerate(parts):
                        if i == 0:
                            send_message(chat_id, part, keyboard)
                        else:
                            send_message(chat_id, part)
            else:
                send_message(chat_id, f"❌ القاعدة غير موجودة")
            return "OK"
        
        if cb_data.startswith("test_"):
            test_name = cb_data.replace("test_", "")
            delete_message(chat_id, msg_id)
            start_test(chat_id, user_id, test_name)
            return "OK"
        
        if cb_data.startswith("level_"):
            level_id = cb_data.replace("level_", "")
            delete_message(chat_id, msg_id)
            send_message(chat_id, "📝 **اختر الاختبار:**", get_test_buttons(level_id))
            return "OK"
        
        if cb_data.startswith("audio_speed_"):
            parts = cb_data.split("_")
            prefix = parts[2]
            page_num = parts[3]
            edit_message(chat_id, msg_id, "🎵 اختر سرعة الصوت:", get_audio_speed_buttons(prefix, page_num))
            return "OK"
        
        if cb_data.startswith("audio_"):
            parts = cb_data.split("_")
            prefix = parts[1]
            page_num = parts[2]
            speed = parts[3]
            
            send_message(chat_id, "🎵 جاري تجهيز الصوت...")
            
            pages = STUDENT_PAGES if prefix == "student" else ACTIVITY_PAGES
            if page_num in pages:
                text = pages[page_num].get("content_original", "")
                audio_path = text_to_audio(text, prefix, page_num, speed)
                if audio_path:
                    send_voice(chat_id, audio_path)
                else:
                    send_message(chat_id, "❌ حدث خطأ في إنشاء الصوت")
            return "OK"
        
        return "OK"
    
    # معالجة الرسائل النصية
    if 'message' in data:
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        user_id = msg['from']['id']
        
        # أمر /start
        if text == '/start' or text == "🏠 الرئيسية":
            send_message(chat_id, f"🎉 مرحباً بك!\n\n{get_usage_message(user_id)}", get_user_menu(user_id))
        
        # زر الاشتراك
        elif text == "💳 اشتراك":
            keyboard = {"inline_keyboard": [[{"text": "✅ اشتراك", "callback_data": "subscribe_now"}]]}
            send_message(chat_id, "اضغط على زر الاشتراك 👇", keyboard)
        
        # عرض رصيدي
        elif text == "📊 رصيدي":
            send_message(chat_id, get_usage_message(user_id), parse_mode="Markdown")
        
        # عرض طلبات الاشتراك (للمسؤول فقط)
        elif text == "📋 طلبات الاشتراك":
            show_pending_requests(chat_id, user_id)
        
        # عرض المشتركين (للمسؤول فقط)
        elif text == "👥 المشتركين":
            show_active_subscriptions(chat_id, user_id)
        
        # الدعم الفني
        elif text == "🛠️ الدعم الفني":
            contact_teacher(chat_id)
        
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
            if GRAMMAR_RULES:
                send_message(chat_id, "📚 **اختر القاعدة التي تريد دراستها:**", get_grammar_buttons())
            else:
                send_message(chat_id, "📚 لا توجد قواعد متوفرة حالياً.")
        
        # تمارين
        elif text == "📝 تمارين":
            send_message(chat_id, "📝 **اختر المستوى:**", get_level_buttons())
        
        # معالجة رقم العملية (أرقام طويلة) - تسجيل فقط
        elif text.isdigit() and len(text) >= 8:
            if is_subscribed(user_id):
                send_message(chat_id, "✅ أنت مشترك بالفعل! لديك وصول غير محدود.")
                return "OK"
            
            # إضافة طلب جديد
            request_id = add_pending(
                user_id=user_id,
                transaction_id=text,
                first_name=msg['from'].get('first_name', ''),
                username=msg['from'].get('username', '')
            )
            
            # تأكيد للمستخدم
            send_message(chat_id, f"✅ **تم استلام طلبك بنجاح!**\n📌 رقم الطلب: `{request_id}`\n⏳ سيتم مراجعته من قبل المسؤول قريباً.", parse_mode="Markdown")
            
            # إرسال للمسؤول
            admin_msg = f"🔔 **طلب اشتراك جديد**\n"
            admin_msg += f"👤 {msg['from'].get('first_name', '')}\n"
            admin_msg += f"🆔 `{user_id}`\n"
            admin_msg += f"💰 50 ل.س\n"
            admin_msg += f"📌 رقم العملية: `{text}`\n"
            admin_msg += f"📌 رقم الطلب: `{request_id}`"
            
            admin_keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ قبول", "callback_data": f"approve_{request_id}"},
                        {"text": "❌ رفض", "callback_data": f"reject_{request_id}"}
                    ]
                ]
            }
            send_message(ADMIN_ID, admin_msg, admin_keyboard, "Markdown")
            print(f"📝 تم إضافة طلب جديد رقم {request_id} من المستخدم {user_id}")
        
        # معالجة رقم الصفحة
        elif text.isdigit():
            selected_book = user_book_choice.get(user_id)
            if selected_book == "student":
                if text in STUDENT_PAGES:
                    page = STUDENT_PAGES[text]
                    content = format_text(page.get("content_original", ""))
                    send_message(chat_id, 
                               f"📖 **{page['title']}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}", 
                               get_page_buttons("student", text, "original", STUDENT_MIN, STUDENT_MAX))
                else:
                    send_message(chat_id, f"❌ الصفحة {text} غير موجودة في كتاب الطالب")
            elif selected_book == "activity":
                if text in ACTIVITY_PAGES:
                    page = ACTIVITY_PAGES[text]
                    content = format_text(page.get("content_original", ""))
                    send_message(chat_id, 
                               f"✏️ **{page['title']}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content}", 
                               get_page_buttons("activity", text, "original", ACTIVITY_MIN, ACTIVITY_MAX))
                else:
                    send_message(chat_id, f"❌ الصفحة {text} غير موجودة في كتاب الأنشطة")
            else:
                send_message(chat_id, "❌ اختر كتاباً أولاً (📖 كتاب الطالب أو ✏️ كتاب الأنشطة)")
        
        else:
            send_message(chat_id, "اختر من القائمة 👇", get_user_menu(user_id))
    
    return "OK"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
