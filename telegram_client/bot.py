import base64
import os
import time

from dotenv import load_dotenv
import requests
import telebot
from telebot import apihelper

load_dotenv("../.env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
if not TELEGRAM_TOKEN:
    err_text = "TELEGRAM_TOKEN bulunamadı. .env dosyasını kontrol edin."
    raise ValueError(err_text)

# Telegram API'ye giden isteklerde geçici ağ kopmalarına karşı otomatik tekrar dene
apihelper.RETRY_ON_ERROR = True
apihelper.RETRY_TIMEOUT = 5  # saniye

bot = telebot.TeleBot(TELEGRAM_TOKEN)
API_URL = "http://127.0.0.1:8000/api/v1/chat"


def safe_chat_action(chat_id: int, action: str) -> None:
    """send_chat_action geçici ağ hatasında botu çökertmesin diye korumalı çağrı."""
    try:
        bot.send_chat_action(chat_id, action)
    except (requests.exceptions.RequestException, ConnectionError, OSError) as e:
        print(f"⚠️ send_chat_action başarısız (görmezden geliniyor): {e!s}")


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    welcome_text = (
        "⚡ *EV & Embedded Systems AI Asistanı Aktif*\n\n"
        "• CAN Bus, BMS, Motor Sürücü ve LoRa sorularınızı sorabilirsiniz.\n"
        "• Mukayese raporundaki malzeme/fiyatları sorgulayabilirsiniz.\n"
        "• Devre şeması veya donanım fotoğrafları göndererek teknik analiz alabilirsiniz."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")


# --- GÖREV 4: FOTOĞRAF MESAJLARINI YAKALAMA VE API'YE İLETME ---
@bot.message_handler(content_types=["photo"])
def handle_photo_message(message):
    user_id = str(message.chat.id)
    username = message.from_user.username or message.from_user.first_name or "Unknown"
    caption = message.caption or ""

    safe_chat_action(message.chat.id, "typing")

    try:
        # En yüksek çözünürlüklü fotoğrafı seç ve indir
        photo_info = message.photo[-1]
        file_info = bot.get_file(photo_info.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Görseli base64 formatına dönüştür
        image_base64 = base64.b64encode(downloaded_file).decode("utf-8")

        payload = {
            "user_id": user_id,
            "username": username,
            "message": caption,
            "image_base64": image_base64,
        }

        response = requests.post(API_URL, json=payload, timeout=60)

        if response.status_code == 200:
            api_data = response.json()
            bot_reply = api_data.get("response", "Görsel analizi yapılamadı.")
        else:
            bot_reply = f"⚠️ Görsel Analiz Hatası ({response.status_code})"

    except requests.exceptions.Timeout:
        bot_reply = "⏱️ Görsel analizi zaman aşımına uğradı. Lütfen tekrar deneyin."
    except requests.exceptions.ConnectionError:
        bot_reply = "⚠️ API Sunucusuna ulaşılamıyor (FastAPI servisinin çalıştığından emin olun)."
    except requests.exceptions.RequestException as e:
        bot_reply = f"Hata: {e!s}"

    bot.send_message(message.chat.id, bot_reply)


# --- METİN MESAJLARINI YAKALAMA ---
@bot.message_handler(content_types=["text"])
def handle_text_messages(message):
    if not message.text or message.text.startswith("/"):
        return

    user_id = str(message.chat.id)
    username = message.from_user.username or message.from_user.first_name or "Unknown"
    user_text = message.text

    safe_chat_action(message.chat.id, "typing")

    try:
        payload = {
            "user_id": user_id,
            "username": username,
            "message": user_text,
        }

        response = requests.post(API_URL, json=payload, timeout=60)

        if response.status_code == 200:
            api_data = response.json()
            bot_reply = api_data.get("response", "API'den boş yanıt döndü.")
        else:
            bot_reply = f"⚠️ Servis Hatası ({response.status_code})"

    except requests.exceptions.Timeout:
        bot_reply = "⏱️ İstek zaman aşımına uğradı. Lütfen tekrar deneyin."
    except requests.exceptions.ConnectionError:
        bot_reply = (
            "⚠️ API Sunucusuna ulaşılamıyor (FastAPI servisinin çalıştığından emin olun)."
        )
    except requests.exceptions.RequestException as e:
        bot_reply = f"Hata: {e!s}"

    bot.send_message(message.chat.id, bot_reply)


if __name__ == "__main__":
    print("🤖 Telegram İstemcisi dinlemede (Metin + Fotoğraf Destekli)...")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:  # noqa: BLE001 - kasıtlı geniş yakalama: bot asla tamamen ölmesin
            print(f"⚠️ Polling çöktü, 5 saniye sonra yeniden başlatılıyor: {e!s}")
            time.sleep(5)