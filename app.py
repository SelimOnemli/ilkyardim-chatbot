from flask import Flask, request, render_template, session, redirect, url_for, Response
import csv
import os
import requests
import json
from dotenv import load_dotenv
from datetime import datetime
import html
import re

app = Flask(__name__)
app.secret_key = 'super-secret-key'
load_dotenv()

def get_local_response(message):
    csv_file = os.path.join(os.path.dirname(__file__), 'first_aid_data.csv')
    if not os.path.exists(csv_file):
        print(f"Hata: CSV dosyası bulunamadı: {csv_file}")
        return False

    local_knowledge = {}
    with open(csv_file, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            local_knowledge[row['keyword'].strip()] = row['response'].strip()

    message = message.lower()
    for keyword, response in local_knowledge.items():
        if keyword in message:
            return response
    return False

def format_response(text):
    """API yanıtını yerel veri formatına uygun hale getirir."""
    if not text or "Yanıt alınamadı" in text or "bilgim yok" in text.lower():
        return "Bu durum için yeterli bilgim yok. Lütfen 112'yi arayın veya en yakın sağlık kuruluşuna başvurun."

    # Format kontrolü: BAŞLIK, adımlar ve not içeriyor mu?
    pattern = r'^(.*?):(\n\d+\..*?)(\n\nNot:.*)?$'
    match = re.match(pattern, text, re.DOTALL)
    if not match:
        # Format uygun değilse, metni olduğu gibi döndür ve varsayılan not ekle
        print(f"Format hatası: Yanıt regex desenine uymuyor: {text}")
        if not text.endswith("Not:"):
            text += "\n\nNot: Durum devam ederse en yakın sağlık kuruluşuna başvurun."
        return text.strip()

def call_api(soru, model):
    prompt = (
        "Sen bir ilk yardım uzmanısın. Yanıtların kısa, net ve sadece Türkçe olsun. "
        "Sorunun bir ilk yardım durumu olduğunu varsay ve cevabını şu formatta, adım adım bir liste olarak ver:\n"
        "BAŞLIK:\n1. Adım 1\n2. Adım 2\n3. Adım 3\n...\n\nNot: [Durumun ciddiyetine göre öneri, örneğin 'Hemen 112'yi arayın' veya 'Durum devam ederse hastaneye gidin']\n"
        "Eğer soruyu cevaplayamazsan veya ilk yardım durumu değilse, şu şekilde yanıt ver: 'Bu durum için yeterli bilgim yok. Lütfen 112'yi arayın veya en yakın sağlık kuruluşuna başvurun.'\n"
        "Sorumluluk reddi: Bu chatbot tıbbi bir profesyonelin yerini tutmaz. Acil durumlarda 112'yi arayın.\n"
        f"Soru: {soru}\n"
        "Örnek yanıt:\n"
        "BAŞ AĞRISI:\n1. Sessiz ve karanlık bir odada dinlenin\n2. Bol su için\n3. Ağrı kesici alabilirsiniz (parasetamol gibi)\n\nNot: Ağrı şiddetlenirse veya sık sık tekrarlarsa doktora başvurun"
    )

    try:
        if model == 'gemini':
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                raise ValueError("Gemini API anahtarı tanımlı değil!")
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            print(f"Gemini API Yanıtı: {json.dumps(data, indent=2, ensure_ascii=False)}")  # Ayrıntılı hata ayıklama
            if 'candidates' not in data or not data['candidates']:
                return "Bu durum için yeterli bilgim yok. Lütfen 112'yi arayın veya en yakın sağlık kuruluşuna başvurun."
            text = data['candidates'][0]['content']['parts'][0]['text'] or 'Yanıt alınamadı'
            return format_response(text)

        elif model == 'deepseek':
            api_key = os.getenv('DEEPSEEK_API_KEY')
            if not api_key:
                raise ValueError("DeepSeek API anahtarı tanımlı değil!")
            response = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]},
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            print(f"DeepSeek API Yanıtı: {json.dumps(data, indent=2, ensure_ascii=False)}")  # Ayrıntılı hata ayıklama
            text = data['choices'][0]['message']['content'] or 'Yanıt alınamadı'
            return format_response(text)

        elif model == 'chatgpt':
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OpenAI API anahtarı tanımlı değil!")
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": prompt}]},
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            print(f"OpenAI API Yanıtı: {json.dumps(data, indent=2, ensure_ascii=False)}")  # Ayrıntılı hata ayıklama
            text = data['choices'][0]['message']['content'] or 'Yanıt alınamadı'
            return format_response(text)

        else:
            return "Geçersiz model seçimi."
    except requests.exceptions.RequestException as e:
        print(f"API İsteği Hatası ({model}): {str(e)}")
        return "Bu durum için yeterli bilgim yok. Lütfen 112'yi arayın veya en yakın sağlık kuruluşuna başvurun."
    except Exception as e:
        print(f"API Hatası ({model}): {str(e)}")
        return "Bu durum için yeterli bilgim yok. Lütfen 112'yi arayın veya en yakın sağlık kuruluşuna başvurun."

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        if 'chat_history' not in session:
            session['chat_history'] = []

        if request.method == 'POST':
            soru = html.escape(request.form.get('soru', '').strip())
            model = request.form.get('model', 'gemini')
            if not soru:
                return Response(json.dumps({'error': 'Boş soru gönderilemez'}), status=400, mimetype='application/json')

            response = get_local_response(soru)
            if not response:
                response = call_api(soru, model)

            session['chat_history'].append({'role': 'user', 'content': soru, 'timestamp': datetime.now().isoformat()})
            session['chat_history'].append({'role': 'bot', 'content': response, 'timestamp': datetime.now().isoformat()})
            session.modified = True

            return Response(json.dumps({'cevap': response}), mimetype='application/json')

        # GET isteği için şablonu render et
        return render_template('index.html', chat_history=session['chat_history'])

    except Exception as e:
        print(f"Index Hatası: {str(e)}")
        return Response(json.dumps({'error': 'Bir hata oluştu. Lütfen tekrar deneyin.'}), status=500, mimetype='application/json')

@app.route('/new_chat')
def new_chat():
    session['chat_history'] = []
    session.modified = True
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)