import os
import requests
import telebot
from dotenv import load_dotenv
from database import log_chat, init_db

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

print("TEST API KEY:", OPENROUTER_API_KEY) 
bot = telebot.TeleBot(TELEGRAM_TOKEN)
init_db() 

def get_ai_response(user_message):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "google/gemma-4-26b-a4b-it:free", # Seçtiğin model
        "messages": [
            {
                "role": "system",
                "content": "Sen profesyonel bir Gömülü Sistemler ve Yazılım Mühendisliği asistanısın. Sadece donanım, yazılım, Arduino, mikrodenetleyiciler, haberleşme protokolleri ve mühendislik projeleri ile ilgili sorulara cevap ver. Kullanıcıya teknik, net, açıklayıcı ve çözüm odaklı cevaplar ver. Mühendislik alanı dışındaki sorulara 'Ben bir IoT ve Gömülü Sistemler uzmanıyım, bu konuda yardımcı olamam' diyerek nazikçe reddet."
            },
            {"role": "user", "content": user_message}
        ]
    }
    
  
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            # HATAYI TERMİNALDE GÖRMEK İÇİN BU SATIRI EKLEDİK
            print(f"OPENROUTER HATASI: {response.text}") 
            return f"API Hatası Kodu: {response.status_code}"
    except Exception as e:
        return "Bağlantı sırasında bir hata oluştu."

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_text = message.text
    username = message.from_user.username or message.from_user.first_name 
    
    bot.send_chat_action(message.chat.id, 'typing')
    
    ai_reply = get_ai_response(user_text)
    bot.reply_to(message, ai_reply)
    
    log_chat(username, user_text, ai_reply)
    print(f"[{username}]: {user_text} -> Yanıtlandı.")

if __name__ == "__main__":
    print("Bot başarıyla başlatıldı! Telegram'dan mesaj atabilirsin...")
    bot.infinity_polling()