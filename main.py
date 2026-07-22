import os
import json
import base64
import requests
import telebot
from dotenv import load_dotenv

import memory
from database import log_chat, init_db
from material_service import search_material_in_report

load_dotenv()

bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
init_db()

# --- OPENROUTER AYARLARI ---
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL_NAME = "google/gemma-4-26b-a4b-it:free"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com",  # OpenRouter için opsiyonel kimlik bilgisi
    "X-Title": "EV Embedded Systems Bot"
}


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(
        message,
        "Elektrikli araç ve gömülü sistemler asistanı aktif. Teknik sorularınızı sorabilir veya donanım görselleri gönderebilirsiniz.",
    )


@bot.message_handler(commands=["reset"])
def reset_memory(message):
    memory.clear_session(str(message.from_user.id))
    bot.reply_to(message, "Oturum ve bellek verileri başarıyla sıfırlandı.")


# --- FOTOĞRAF ANALİZİ (VISION - OPENROUTER GEMMA) ---
@bot.message_handler(content_types=["photo"])
def photo_handler(message):
    try:
        chat_id = message.chat.id
        username = message.from_user.username or message.from_user.first_name

        bot.send_chat_action(chat_id, "typing")

        # Fotoğrafı indir ve Base64'e dönüştür
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        base64_image = base64.b64encode(downloaded_file).decode("utf-8")

        caption_text = message.caption or ""

        vision_prompt = f"""Sen uzman bir Elektrikli Araç ve Gömülü Sistemler Mühendisisin.
GÖREVİN:
1. Sana gönderilen görseli analiz et.
2. Eğer görsel ELEKTRİKLİ ARAÇLAR, MİKROKONTROLÖRLER (Arduino, STM32, ESP32 vb.), SENSÖRLER, BMS, CAN BUS, MOTOR SÜRÜCÜLER, DEVRE ŞEMALARI, KABLO TESİSATI veya MÜHENDİSLİK DONANIMLARI ile İLGİLİ DEĞİLSE:
   - Kullanıcıya nezaketle bu fotoğrafın elektrikli araçlar veya gömülü sistemler konusuyla ilgili olmadığını, sadece teknik ve donanımsal görselleri analiz edebileceğini belirt.
3. Eğer görsel KONUYLA İLGİLİYSEN:
   - Görseldeki bileşenleri, devreyi veya donanımı teknik olarak tanımla.
   - Doğrudan teknik çözüme, tespite veya öneriye odaklan. Madde imleri (bullet points) kullan. Gereksiz giriş/sonuç cümleleri kurma.
Kullanıcının görsel notu: '{caption_text}'"""

        payload = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.2
        }

        response = requests.post(OPENROUTER_URL, headers=HEADERS, json=payload, timeout=30)
        res_json = response.json()

        if response.status_code == 200 and "choices" in res_json and len(res_json["choices"]) > 0:
            ai_reply = res_json["choices"][0]["message"]["content"]
        else:
            err_msg = res_json.get("error", {}).get("message", response.text)
            print(f"OpenRouter Vision Hatası: {err_msg}")
            ai_reply = f"Görsel analiz hatası ({response.status_code}): {err_msg}"

        bot.reply_to(message, ai_reply)
        log_chat(username, f"[FOTOĞRAF] {caption_text}", ai_reply)

    except Exception as e:
        print(f"GÖRSEL İŞLEME HATASI: {e}")
        bot.reply_to(message, f"Fotoğraf işlenirken hata oluştu: {str(e)}")


# --- METİN VE SOHBET YÖNETİCİSİ (OPENROUTER GEMMA) ---
@bot.message_handler(func=lambda message: True, content_types=["text"])
def chat_handler(message):
    if not message.text or message.text.startswith("/"):
        return

    try:
        chat_id = message.chat.id
        user_id = str(message.from_user.id)
        user_text = message.text
        username = message.from_user.username or message.from_user.first_name

        bot.send_chat_action(chat_id, "typing")

        session = memory.load_sessions().get(user_id, {"history": [], "summary": "Henüz özet yok."})

        system_prompt = """[CRITICAL SYSTEM DIRECTION - MANDATORY]
You must detect the language of the user's latest message and reply in the EXACT SAME language.
- If the user writes in English, your response MUST be 100% English.
- If the user writes in Turkish, your response MUST be 100% Turkish.
Never use Turkish if the user's message is in English.

[ROLE]
You are a professional Electric Vehicle and Embedded Systems Engineer.

[RULES]
1. DO NOT make small talk. Eliminate introduction and conclusion sentences.
2. Focus ONLY on the technical solution. Use bullet points or code blocks.
3. Answer the question directly without dragging.
4. REMEMBER past details fetched from user summary and context.
5. Talk ONLY about hardware, software, embedded systems, CAN Bus, BMS, and motor drivers. Refuse non-engineering questions.
6. If the user asks about component prices, materials, or details inside the project report, explicitly mention prices, links, and quantities."""

        full_prompt = f"{system_prompt}\n\n[OTURUM BİLGİSİ VE ÖZETİ]: {session.get('summary', '')}\n"

        if "history" in session:
            full_prompt += "\n[SOHBET GEÇMİŞİ]:\n"
            for item in session["history"][-6:]:
                full_prompt += f"{item['role']}: {item['content']}\n"

        full_prompt += f"\nUser: {user_text}"

        # Excel canlı veri sorgulama tespiti
        excel_keywords = ["fiyat", "malzeme", "rapor", "stok", "kablo", "motor", "sürücü", "bms", "kaç para", "ne kadar", "var mı", "liste"]
        
        if any(word in user_text.lower() for word in excel_keywords) or len(user_text.split()) <= 3:
            excel_res = search_material_in_report(user_id, user_text)
            
            # Eğer malzeme bulunduysa sonuçları prompta ver
            if isinstance(excel_res, dict) and excel_res.get("status") == "success":
                full_prompt += f"\n\n[EXCEL RAPORUNDAN GELEN CANLI VERİ (MUTLAKA YANITA YANSITILMALI)]:\n{json.dumps(excel_res['data'], ensure_ascii=False)}"

        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "user", "content": full_prompt}
            ],
            "temperature": 0.1
        }

        response = requests.post(OPENROUTER_URL, headers=HEADERS, json=payload, timeout=20)
        res_json = response.json()

        if response.status_code == 200 and "choices" in res_json and len(res_json["choices"]) > 0:
            ai_reply = res_json["choices"][0]["message"]["content"]
        else:
            err_msg = res_json.get("error", {}).get("message", response.text)
            ai_reply = f"OpenRouter Hatası ({response.status_code}): {err_msg}"

        memory.update_memory(user_id, user_text, ai_reply)

        if len(ai_reply) > 4000:
            for i in range(0, len(ai_reply), 4000):
                bot.send_message(chat_id, ai_reply[i : i + 4000])
        else:
            bot.send_message(chat_id, ai_reply)

        log_chat(username, user_text, ai_reply)

    except Exception as e:
        print(f"SİSTEM HATASI: {e}")
        bot.send_message(message.chat.id, f"Sistem hatası: {str(e)}")


if __name__ == "__main__":
    print(f"Bot OpenRouter ({MODEL_NAME}) ile başarıyla başlatıldı!")
    bot.infinity_polling()