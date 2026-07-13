import os
import requests
import telebot
import memory
from dotenv import load_dotenv
from database import log_chat, init_db

load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
init_db() 

def get_ai_response(user_message, session):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json"
    }
    system_prompt = """Sen profesyonel bir Elektrikli Araç Geliştirme ve Gömülü Sistemler uzmanısın.

    --- BÖLÜM 1: BELLEK VE BAĞLAM YÖNETİMİ ---
    1. KURAL: Sana sağlanan 'Konuşma Geçmişi' ve 'Oturum Özeti' verilerini mutlaka analiz et ve dikkate al.
    2. KURAL: Kullanıcı ile olan etkileşiminde geçmişteki teknik detayları (proje adı, motor modeli, kullanılan parçalar vb.) hatırla ve bunları tekrar sorma.
    3. KURAL: Kullanıcıyı tanıdığını hissettir; daha önce paylaştığı teknik bilgileri temel alarak kişiselleştirilmiş ve tutarlı öneriler sun.

    --- BÖLÜM 2: UZMANLIK VE ETİK KURALLAR ---
    4. KURAL: Her zaman kullanıcının yazdığı dilde (Türkçe veya İngilizce) cevap ver.
    5. KURAL: Sadece donanım, yazılım, gömülü sistemler, CAN Bus, BMS, motor sürücüler ve haberleşme protokolleri ile ilgili teknik soruları cevapla.
    6. KURAL: Mühendislik dışındaki soruları 'Ben bir Elektrikli Araç ve Gömülü Sistemler uzmanıyım, bu konuda yardımcı olamam' diyerek reddet.
    7. KURAL: Teknik, net, açıklayıcı ve çözüm odaklı ol. Mühendislik terminolojisini (akım, voltaj, PWM, PID vb.) doğru kullan.
    8. KURAL: Tasarım süreçlerinde güvenlik ve verimlilik odaklı en iyi mühendislik pratiklerini (best practices) öner."""


    summary = session.get('summary', 'Henüz özet yok.')
    messages = [{"role": "system", "content": system_prompt + f"\n\n--- OTURUM ÖZETİ ---\n{summary}"}]
    
    if "history" in session:
        messages.extend(session["history"])
    
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": "google/gemma-4-26b-a4b-it:free",
        "messages": messages
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return "Teknik bir hata ile karşılaştım (API Hatası)."
    except Exception:
        return "Bağlantı sırasında bir hata oluştu."

@bot.message_handler(func=lambda message: True)
def chat_handler(message):
    user_id = str(message.from_user.id)
    user_text = message.text
    username = message.from_user.username or message.from_user.first_name 
    
    session = memory.load_sessions().get(user_id, {"history": [], "summary": "Henüz özet yok."})
    
    bot.send_chat_action(message.chat.id, 'typing')
    
    ai_reply = get_ai_response(user_text, session)
    
    memory.update_memory(user_id, user_text, ai_reply)
    
    if len(ai_reply) > 4000:
        for i in range(0, len(ai_reply), 4000):
            bot.reply_to(message, ai_reply[i:i+4000])
    else:
        bot.reply_to(message, ai_reply)
    log_chat(username, user_text, ai_reply)

if __name__ == "__main__":
    print("Bot başarıyla başlatıldı!")
    bot.infinity_polling()