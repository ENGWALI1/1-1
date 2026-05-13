import os
import json
import zipfile
import shutil
from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"
HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')

# ==================== فك ضغط قوي يبحث عن كل JSON ====================
def extract_all_json(zip_path):
    """يفك الضغط ويجمع كل محتوى JSON من أي مجلد فرعي"""
    pages = {}
    extract_dir = "extracted_temp"
    
    # تنظيف المجلد القديم
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    
    # فك الضغط
    print(f"📦 فك ضغط {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)
    
    # البحث عن كل ملف JSON
    json_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith('.json'):
                json_files.append(os.path.join(root, file))
    
    print(f"📄 وجدت {len(json_files)} ملف JSON")
    
    # قراءة كل ملف
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # استخراج رقم الصفحة من اسم الملف
                filename = os.path.basename(file_path)
                page_num = filename.replace('page_', '').replace('.json', '')
                
                # إذا كان الرقم ليس رقماً، حاول استخراجه من المحتوى
                if not page_num.isdigit():
                    # ابحث عن أول مفتاح رقمي في البيانات
                    if isinstance(data, dict):
                        for key in data.keys():
                            if str(key).isdigit():
                                page_num = str(key)
                                data = data[key]
                                break
                
                # تخزين البيانات (حتى لو لم تكن كاملة)
                if isinstance(data, dict):
                    pages[page_num] = {
                        "title": data.get('title', f'صفحة {page_num}'),
                        "content_original": data.get('content_original', data.get('content', str(data))),
                        "translation": data.get('translation', ''),
                        "content_line_by_line": data.get('content_line_by_line', []),
                        "exercises": data.get('exercises', [])
                    }
                else:
                    pages[page_num] = {
                        "title": f'صفحة {page_num}',
                        "content_original": str(data),
                        "translation": '',
                        "content_line_by_line": [],
                        "exercises": []
                    }
                print(f"✅ صفحة {page_num} من {filename}")
        except Exception as e:
            print(f"⚠️ خطأ في {file_path}: {e}")
    
    # تنظيف المجلد المؤقت
    shutil.rmtree(extract_dir)
    
    return pages

# تحميل الكتاب من ZIP
zip_path = 'student_pages.zip'
if os.path.exists(zip_path):
    BOOK = extract_all_json(zip_path)
    print(f"✅ تم تحميل {len(BOOK)} صفحة بنجاح!")
else:
    print(f"❌ الملف {zip_path} غير موجود!")
    BOOK = {}

# تخزين حالة المستخدمين
user_states = {}

# ==================== دوال مساعدة ====================
def format_line_by_line(lines):
    if not lines:
        return "لا توجد ترجمة سطرية"
    result = ""
    for item in lines:
        en = item.get('en', '')
        ar = item.get('ar', '')
        result += f"📖 {en}\n🌐 {ar}\n\n"
    return result

def format_exercises(exercises):
    if not exercises:
        return "لا توجد تمارين في هذه الصفحة"
    result = "📝 **حلول التمارين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, ex in enumerate(exercises, 1):
        text = ex.get('text', ex.get('question', 'سؤال'))
        answer = ex.get('answer', '---')
        result += f"**{i}. {text}**\n✅ {answer}\n\n"
    return result

def get_page_buttons(page_num, mode):
    buttons = []
    
    # أزرار التنقل
    nav = []
    if int(page_num) > 1:
        nav.append({"text": "◀️ السابق", "callback_data": f"page_{int(page_num)-1}"})
    if int(page_num) < len(BOOK):
        nav.append({"text": "التالي ▶️", "callback_data": f"page_{int(page_num)+1}"})
    if nav:
        buttons.append(nav)
    
    # أزرار الميزات
    feature_buttons = []
    if mode != 'original':
        feature_buttons.append({"text": "🔤 النص الأصلي", "callback_data": f"mode_original_{page_num}"})
    if mode != 'translated':
        feature_buttons.append({"text": "🔤 الترجمة", "callback_data": f"mode_translated_{page_num}"})
    if mode != 'solved':
        feature_buttons.append({"text": "📝 حل التمارين", "callback_data": f"mode_solved_{page_num}"})
    
    if feature_buttons:
        buttons.append(feature_buttons)
    
    buttons.append([{"text": "🏠 القائمة الرئيسية", "callback_data": "main_menu"}])
    return {"inline_keyboard": buttons}

# ==================== إعداد Webhook ====================
@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>{len(BOOK)} صفحة تم تحميلها</p>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'message' not in data and 'callback_query' not in data:
        return 'OK'
    
    # معالجة الأزرار التفاعلية
    if 'callback_query' in data:
        callback = data['callback_query']
        chat_id = callback['message']['chat']['id']
        message_id = callback['message']['message_id']
        callback_data = callback['data']
        user_id = callback['from']['id']
        
        print(f"🔘 {callback_data}")
        
        if callback_data == 'main_menu':
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً!\n📚 {len(BOOK)} صفحة\nاضغط 📖 كتاب الطالب",
                "reply_markup": keyboard
            })
            requests.post(URL + '/deleteMessage', json={
                "chat_id": chat_id,
                "message_id": message_id
            })
            return 'OK'
        
        if callback_data.startswith('mode_'):
            parts = callback_data.split('_')
            mode = parts[1]
            page_num = parts[2]
            
            if page_num in BOOK:
                page = BOOK[page_num]
                if mode == 'original':
                    content = page.get('content_original', 'لا يوجد محتوى')
                elif mode == 'translated':
                    content = format_line_by_line(page.get('content_line_by_line', []))
                    if not content or content == "لا توجد ترجمة سطرية":
                        content = page.get('translation', 'لا توجد ترجمة')
                else:
                    content = format_exercises(page.get('exercises', []))
                
                title = page.get('title', f'صفحة {page_num}')
                requests.post(URL + '/editMessageText', json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": f"📖 {title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons(page_num, mode)
                })
            return 'OK'
        
        if callback_data.startswith('page_'):
            page_num = callback_data.split('_')[1]
            user_state = user_states.get(user_id, {})
            mode = user_state.get('mode', 'original')
            
            if page_num in BOOK:
                page = BOOK[page_num]
                if mode == 'original':
                    content = page.get('content_original', 'لا يوجد محتوى')
                elif mode == 'translated':
                    content = format_line_by_line(page.get('content_line_by_line', []))
                    if not content or content == "لا توجد ترجمة سطرية":
                        content = page.get('translation', 'لا توجد ترجمة')
                else:
                    content = format_exercises(page.get('exercises', []))
                
                title = page.get('title', f'صفحة {page_num}')
                requests.post(URL + '/editMessageText', json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": f"📖 {title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons(page_num, mode)
                })
                user_states[user_id] = {'mode': mode, 'page': page_num}
            return 'OK'
        
        return 'OK'
    
    # معالجة الرسائل النصية
    if 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')
        user_id = data['message']['from']['id']
        
        print(f"📨 {text}")
        
        if text == '/start':
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً!\n📚 {len(BOOK)} صفحة\nاضغط على الزر لبدء القراءة",
                "reply_markup": keyboard
            })
        
        elif text == "📖 كتاب الطالب":
            user_states[user_id] = {'mode': 'original'}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"📄 أرسل رقم الصفحة (1-{len(BOOK)}):"
            })
        
        elif text.isdigit():
            if text in BOOK:
                page = BOOK[text]
                mode = user_states.get(user_id, {}).get('mode', 'original')
                
                if mode == 'original':
                    content = page.get('content_original', 'لا يوجد محتوى')
                elif mode == 'translated':
                    content = format_line_by_line(page.get('content_line_by_line', []))
                    if not content or content == "لا توجد ترجمة سطرية":
                        content = page.get('translation', 'لا توجد ترجمة')
                else:
                    content = format_exercises(page.get('exercises', []))
                
                title = page.get('title', f'صفحة {text}')
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": f"📖 {title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons(text, mode)
                })
                user_states[user_id] = {'mode': mode, 'page': text}
            else:
                requests.post(URL + '/sendMessage', json={
                    "chat_id": chat_id,
                    "text": f"❌ الصفحة {text} غير موجودة\n📚 الصفحات المتوفرة: 1 إلى {len(BOOK)}"
                })
        
        else:
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "اضغط على 📖 كتاب الطالب لبدء القراءة",
                "reply_markup": keyboard
            })
    
    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
