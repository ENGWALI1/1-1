import os
import json
import zipfile
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

TOKEN = os.environ['BOT_TOKEN']
URL = f"https://api.telegram.org/bot{TOKEN}"
HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')

# ==================== فك ضغط وقراءة الملفات ====================
def extract_and_load(zip_path):
    """فك ضغط الملف وقراءة جميع ملفات JSON"""
    pages = {}
    extract_dir = "student_pages_temp"
    
    # فك الضغط
    if os.path.exists(extract_dir):
        import shutil
        shutil.rmtree(extract_dir)
    
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)
    
    # البحث عن جميع ملفات JSON
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # استخراج رقم الصفحة من اسم الملف
                        page_num = file.replace('page_', '').replace('.json', '')
                        
                        # تخزين جميع البيانات (الأصلي، الترجمة، التمارين)
                        pages[page_num] = {
                            "title": data.get('title', f'صفحة {page_num}'),
                            "content_original": data.get('content_original', data.get('content', '')),
                            "translation": data.get('translation', ''),
                            "content_line_by_line": data.get('content_line_by_line', []),
                            "exercises": data.get('exercises', [])
                        }
                except Exception as e:
                    print(f"خطأ في {file}: {e}")
    
    return pages

# تحميل الكتاب من ZIP
zip_path = 'student_pages.zip'
if os.path.exists(zip_path):
    BOOK = extract_and_load(zip_path)
    print(f"✅ تم تحميل {len(BOOK)} صفحة من {zip_path}")
else:
    print(f"❌ {zip_path} غير موجود")
    BOOK = {}

# تخزين حالة المستخدمين
user_states = {}  # {'user_id': {'book': 'student', 'page': '10', 'mode': 'original'}}

# ==================== دوال مساعدة ====================
def format_line_by_line(lines):
    """تنسيق الترجمة سطراً بسطر"""
    if not lines:
        return "لا توجد ترجمة سطرية"
    result = ""
    for item in lines:
        en = item.get('en', '')
        ar = item.get('ar', '')
        result += f"📖 {en}\n🌐 {ar}\n\n"
    return result

def format_exercises(exercises):
    """تنسيق حلول التمارين"""
    if not exercises:
        return "لا توجد تمارين في هذه الصفحة"
    
    result = "📝 **حلول التمارين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, ex in enumerate(exercises, 1):
        ex_type = ex.get('type', '')
        if ex_type == 'speaking':
            questions = ex.get('questions', [])
            answers = ex.get('answers', [])
            result += f"**🗣️ نشاط المحادثة {i}:**\n"
            for j, q in enumerate(questions):
                result += f"**سؤال {j+1}:** {q}\n"
                if j < len(answers):
                    result += f"✅ {answers[j]}\n"
            result += "\n"
        else:
            text = ex.get('text', ex.get('question', 'سؤال'))
            answer = ex.get('answer', '---')
            result += f"**{i}. {text}**\n✅ {answer}\n\n"
    return result

def get_page_buttons(page_num, mode):
    """أزرار التنقل والترجمة وحل التمارين"""
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
    
    # زر القائمة الرئيسية
    buttons.append([{"text": "🏠 القائمة الرئيسية", "callback_data": "main_menu"}])
    
    return {"inline_keyboard": buttons}

# ==================== إعداد Webhook ====================
@app.route('/')
def home():
    return f"<h1>🤖 @withali91_bot</h1><p>{len(BOOK)} صفحة</p>"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'message' not in data and 'callback_query' not in data:
        return 'OK'
    
    # معالجة الضغط على الأزرار التفاعلية (InlineKeyboard)
    if 'callback_query' in data:
        callback = data['callback_query']
        chat_id = callback['message']['chat']['id']
        message_id = callback['message']['message_id']
        callback_data = callback['data']
        user_id = callback['from']['id']
        
        print(f"🔘 {callback_data} from {user_id}")
        
        # القائمة الرئيسية
        if callback_data == 'main_menu':
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً بك!\n📚 {len(BOOK)} صفحة\nاضغط 📖 كتاب الطالب",
                "reply_markup": keyboard
            })
            requests.post(URL + '/deleteMessage', json={
                "chat_id": chat_id,
                "message_id": message_id
            })
            return 'OK'
        
        # تغيير وضع العرض (أصلي/ترجمة/حلول)
        if callback_data.startswith('mode_'):
            parts = callback_data.split('_')
            mode = parts[1]
            page_num = parts[2]
            
            if page_num in BOOK:
                page = BOOK[page_num]
                if mode == 'original':
                    content = page.get('content_original', 'لا يوجد محتوى')
                elif mode == 'translated':
                    if page.get('content_line_by_line'):
                        content = format_line_by_line(page.get('content_line_by_line', []))
                    else:
                        content = page.get('translation', 'لا توجد ترجمة')
                elif mode == 'solved':
                    content = format_exercises(page.get('exercises', []))
                else:
                    content = page.get('content_original', 'لا يوجد محتوى')
                
                title = page.get('title', f'صفحة {page_num}')
                
                requests.post(URL + '/editMessageText', json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": f"📖 {title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                    "reply_markup": get_page_buttons(page_num, mode)
                })
            return 'OK'
        
        # التنقل بين الصفحات
        if callback_data.startswith('page_'):
            page_num = callback_data.split('_')[1]
            user_state = user_states.get(user_id, {})
            mode = user_state.get('mode', 'original')
            
            if page_num in BOOK:
                page = BOOK[page_num]
                if mode == 'original':
                    content = page.get('content_original', 'لا يوجد محتوى')
                elif mode == 'translated':
                    if page.get('content_line_by_line'):
                        content = format_line_by_line(page.get('content_line_by_line', []))
                    else:
                        content = page.get('translation', 'لا توجد ترجمة')
                elif mode == 'solved':
                    content = format_exercises(page.get('exercises', []))
                else:
                    content = page.get('content_original', 'لا يوجد محتوى')
                
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
        
        print(f"📨 {text} from {user_id}")
        
        # أمر /start
        if text == '/start':
            keyboard = {"keyboard": [["📖 كتاب الطالب"]], "resize_keyboard": True}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"🎉 مرحباً!\n📚 {len(BOOK)} صفحة\n📖 اضغط على الزر لبدء القراءة\n🔤 الترجمة و 📝 الحلول متوفرة",
                "reply_markup": keyboard
            })
        
        # زر كتاب الطالب
        elif text == "📖 كتاب الطالب":
            user_states[user_id] = {'mode': 'original'}
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": "📄 أرسل رقم الصفحة (مثال: 10):"
            })
        
        # إذا أرسل المستخدم رقماً
        elif text.isdigit() and text in BOOK:
            page = BOOK[text]
            mode = user_states.get(user_id, {}).get('mode', 'original')
            
            if mode == 'original':
                content = page.get('content_original', 'لا يوجد محتوى')
            elif mode == 'translated':
                if page.get('content_line_by_line'):
                    content = format_line_by_line(page.get('content_line_by_line', []))
                else:
                    content = page.get('translation', 'لا توجد ترجمة')
            elif mode == 'solved':
                content = format_exercises(page.get('exercises', []))
            else:
                content = page.get('content_original', 'لا يوجد محتوى')
            
            title = page.get('title', f'صفحة {text}')
            
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"📖 {title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n{content[:4000]}",
                "reply_markup": get_page_buttons(text, mode)
            })
            user_states[user_id] = {'mode': mode, 'page': text}
        
        # رقم غير موجود
        elif text.isdigit():
            requests.post(URL + '/sendMessage', json={
                "chat_id": chat_id,
                "text": f"❌ الصفحة {text} غير موجودة\n📚 الصفحات المتوفرة: 1 إلى {len(BOOK)}"
            })
        
        # أي نص آخر
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
