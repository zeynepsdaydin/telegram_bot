import os
import requests
import telebot
import memory
from dotenv import load_dotenv
from database import log_chat, init_db

load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
init_db()


# --- ÖZEL KOMUTLAR ---
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(
        message,
        "Elektrikli araç ve gömülü sistemler asistanı aktif. Teknik sorularınızı sorabilirsiniz.",
    )


@bot.message_handler(commands=["reset"])
def reset_memory(message):
    memory.clear_session(str(message.from_user.id))
    bot.reply_to(message, "Oturum ve bellek verileri başarıyla sıfırlandı.")


# --- YAPAY ZEKA BAĞLANTISI ---
def get_ai_response(user_message, session):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
    }
    
    # Sıkılaştırılmış, doğrudan cevaba odaklanan sistem promptu
    system_prompt = """Sen profesyonel bir Elektrikli Araç ve Gömülü Sistemler mühendisisin.

    --- DİL KURALI ---
    Kullanıcının yazdığı mesajın dili neyse, cevabını KESİNLİKLE aynı dilde ver. 
    Eğer kullanıcı İngilizce yazdıysa İngilizce, Türkçe yazdıysa Türkçe cevapla.
    Başka bir dilde cevap verme veya dili otomatik değiştirme.

    --- TEKNİK KURALLAR ---
    1. KESİNLİKLE GEREKSİZ LAF ETME, GİRİŞ VE SONUÇ CÜMLELERİNİ KISALT.
    2. SADECE TEKNİK ÇÖZÜME ODAKLAN. Madde imleri (bullet points) veya kod blokları kullan.
    3. Kullanıcı sorduğu soruya direkt cevap ver, lafı uzatma.
    Sana sağlanan 'Konuşma Geçmişi' ve 'Oturum Özeti' verilerini mutlaka analiz et ve dikkate al.
    4. Kullanıcı ile olan etkileşiminde geçmişteki teknik detayları (proje adı, motor modeli, kullanılan parçalar vb.) hatırla ve bunları tekrar sorma.
    5. KURAL: Kullanıcıyı tanıdığını hissettir; daha önce paylaştığı teknik bilgileri temel alarak kişiselleştirilmiş ve tutarlı öneriler sun.
    6. Sadece donanım, yazılım, gömülü sistemler, CAN Bus, BMS, motor sürücüler hakkında konuş.
    7. Mühendislik dışındaki soruları reddet. Teknik, net ve çözüm odaklı ol."""

    summary = session.get("summary", "Henüz özet yok.")
    messages = [
        {
            "role": "system",
            "content": system_prompt + f"\n\n--- OTURUM ÖZETİ ---\n{summary}",
        }
    ]

    if "history" in session:
        messages.extend(session["history"][-10:])

    messages.append({"role": "user", "content": user_message})

    # Model ismi kararlı çalışan "google/gemma-2-9b-it:free" ile güncellendi.
    payload = {
        "model": "google/gemma-2-9b-it:free",
        "messages": messages,
        "temperature": 0.1,  # Daha kesin ve mekanik yanıtlar için düşürüldü.
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response_json = response.json()
        
        # Hata tespiti için API yanıtını konsola basar
        print(f"API Yanıtı: {response.text}")
        
        if response.status_code == 200:
            if "choices" in response_json and len(response_json["choices"]) > 0:
                return response_json["choices"][0]["message"]["content"]
            elif "error" in response_json:
                return f"API Hatası (OpenRouter): {response_json['error'].get('message', 'Detay belirtilmedi')}"
            else:
                return "Beklenmedik API yanıt biçimi."
        else:
            return f"Teknik bir hata ile karşılaştım (API Hata Kodu: {response.status_code})."
    except Exception as e:
        return f"Bağlantı sırasında bir hata oluştu: {str(e)}"


# --- MESAJ YÖNETİCİSİ ---
@bot.message_handler(func=lambda message: True)
def chat_handler(message):
    # Eğer mesaj metni yoksa (fotoğraf, dosya vb.) işlem yapma
    if not message.text:
        return

    # Komut kontrolü (Sistem komutlarının AI'ya gitmesini engeller)
    if message.text.startswith("/"):
        return

    try:
        # Hata olasılıklarını engellemek için chat_id ilk sırada tanımlandı
        chat_id = message.chat.id
        user_id = str(message.from_user.id)
        user_text = message.text
        username = message.from_user.username or message.from_user.first_name

        # Botun çalıştığını göstermek için animasyon tetiklenir
        bot.send_chat_action(chat_id, "typing")

        session = memory.load_sessions().get(user_id, {"history": [], "summary": "Henüz özet yok."})
        
        # AI yanıtı üretilir
        ai_reply = get_ai_response(user_text, session)
        
        # Bellek güncellenir
        memory.update_memory(user_id, user_text, ai_reply)

        # Karakter sınırına göre mesaj bölme işlemi uygulanır
        if len(ai_reply) > 4000:
            for i in range(0, len(ai_reply), 4000):
                bot.send_message(chat_id, ai_reply[i : i + 4000])
        else:
            bot.send_message(chat_id, ai_reply)

        log_chat(username, user_text, ai_reply)

    except Exception as e:
        print(f"SİSTEM HATASI: {e}")
        try:
            bot.send_message(message.chat.id, f"Sistem hatası: {str(e)}")
        except Exception as send_error:
            print(f"Hata mesajı gönderilemedi: {send_error}")


if __name__ == "__main__":
    print("Bot başarıyla başlatıldı!")
    bot.infinity_polling()