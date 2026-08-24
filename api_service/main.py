import asyncio
import base64
import json
import os
import telebot
from telebot.types import Update

from database import (
    get_all_logs,
    get_all_users,
    get_system_stats,
    get_user_chat_history,
    init_db,
    log_chat,
    update_chat_evaluation,
)
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import httpx
from material_service import search_material_in_report
import memory
from pydantic import BaseModel

# .env dosyasını kök dizinden yükle
load_dotenv("../.env")

# Veri tabanını başlat
init_db()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe_audio(audio_base64: str) -> str:
    """Base64 kodlu ses verisini Groq Whisper API ile metne çevirir."""
    audio_bytes = base64.b64decode(audio_base64)

    files = {"file": ("voice.ogg", audio_bytes, "audio/ogg")}
    data = {"model": "whisper-large-v3-turbo", "language": "tr"}
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GROQ_TRANSCRIBE_URL, headers=headers, files=files, data=data
        )

    if response.status_code != 200:
        print(f"⚠️ Groq transkripsiyon hatası ({response.status_code}): {response.text}")
        error_text = "Ses metne çevrilemedi (Groq API hatası)."
        raise RuntimeError(error_text)

    return response.json().get("text", "").strip()


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL_NAME = "google/gemma-4-26b-a4b-it:free"
FALLBACK_MODELS = [
    MODEL_NAME,
    "nvidia/nemotron-3-nano-30b-a3b:free"
]

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com",
    "X-Title": "EV Embedded Systems API",
}

app = FastAPI(
    title="EV & Embedded Systems AI Service",
    description="Central API providing LLM, RAG, Memory and Vision capabilities.",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    user_id: str
    username: str | None = "Anonymous"
    message: str = ""
    image_base64: str | None = None


class ChatResponse(BaseModel):
    response: str
    status: str = "success"


class VoiceChatRequest(BaseModel):
    user_id: str
    username: str | None = "Anonymous"
    audio_base64: str


class EvaluateRequest(BaseModel):
    chat_id: int
    user_question: str
    bot_response: str


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "AI Core API"}


async def process_chat_message(
    user_id: str,
    username: str | None,
    user_text: str,
    image_base64: str | None = None,
) -> str:
    try:
        # 1. Oturum Geçmişini Yükle
        session = memory.load_sessions().get(
            user_id, {"history": [], "summary": "Henüz özet yok."}
        )

        # 2. Sistem Yönergesi
        system_content = """[ABSOLUTE PRIORITY: LANGUAGE ENFORCEMENT]
You MUST ALWAYS reply in the EXACT SAME language as the user's latest input message.
- If the user writes in English, your entire response MUST be 100% English. Do NOT use Turkish.
- If the user writes in Turkish, your entire response MUST be 100% Turkish.
- If the user asks to change language (e.g. "türkçe anlat", "türkçe sormuştum"), IMMEDIATELY switch to that language and answer the previous question in that language.

[ROLE]
You are a helpful, precise Electric Vehicle and Embedded Systems Engineer.

[SCOPE & DOMAIN]
You assist with:
- Electric Vehicles (EV), Powertrain, Inverters, Motor Drivers
- Battery Management Systems (BMS)
- Automotive & Embedded Communication Protocols (CAN Bus, UART, SPI, I2C, LoRa)
- Microcontrollers & Hardware (Arduino, STM32, ESP32, Raspberry Pi, Sensors, Displays, HMI)
- Embedded Software, C/C++, Python, Firmware, and Project/Internship Reports.

[RULES]
1. Eliminate introductory fluff and generic conversational filler. Jump straight to the technical content or solution.
2. Structure your answers clearly using bullet points, short concise paragraphs, or code blocks where appropriate.
3. CONVERSATIONAL CONTEXT & FOLLOW-UPS:
   - When the user asks follow-up questions (e.g. "türkçe açıkla", "örnek ver", "ne demek", "neden"), ALWAYS answer based on the previous conversation history.
   - When asked about reports, hardware components, or microcontrollers (including Arduino, sensors, etc.), treat them as VALID technical queries.
4. OUT-OF-SCOPE FILTER:
   - Only reject queries that are completely unrelated to engineering/tech/EV/hardware/software (e.g., cooking recipes, gossip, sports news).
   - If a message is entirely out-of-scope and does NOT contain an [EXCEL RAPORUNDAN GELEN CANLI VERİ] block, politely state: "Sadece donanım, yazılım, EV, CAN Bus, BMS ve motor sürücüleri ile ilgili konularda yardımcı olabilirim."
   - EXCEPTION: If the message contains [EXCEL RAPORUNDAN GELEN CANLI VERİ], NEVER reject it, even for consumables (tape, alcohol, gloves, etc.).
5. IMAGE ANALYSIS:
   - If an image is not related to engineering/hardware/EV/circuits, state that you only analyze technical hardware visuals.
   - If related, analyze components and list findings/recommendations cleanly.
6. EXCEL RAPORU SORGULARI:
   - [EXCEL RAPORUNDAN GELEN CANLI VERİ] bloğu geldiğinde ham veriyi eksiksiz aktar (Ürün adı, miktar, tüm firma fiyatları, link, sebep). Asla birleştirme veya özetleme yapma."""

        if session.get("summary"):
            system_content += f"\n\n[OTURUM BİLGİSİ VE ÖZETİ]:\n{session['summary']}"

        messages = [{"role": "system", "content": system_content}]

        # 3. Geçmiş Konuşmaları Ekle (Son 6 mesaj)
        for item in session.get("history", [])[-6:]:
            role = item.get("role", "user")
            if role not in ["user", "assistant", "system"]:
                role = "user"
            messages.append({"role": role, "content": item.get("content", "")})

        # 4. İstek Türüne Göre Payload Hazırlama
        if image_base64:
            logged_question = f"[FOTOĞRAF ANALİZİ]: {user_text}" if user_text else "[FOTOĞRAF ANALİZİ]"
            prompt_instruction = user_text if user_text else "Görseldeki devreyi/donanımı teknik olarak analiz et."

            user_content = [
                {"type": "text", "text": prompt_instruction},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    },
                },
            ]
            messages.append({"role": "user", "content": user_content})
        else:
            logged_question = user_text

            # Excel (RAG) Kontrolü
            user_msg_lower = user_text.lower()
            chat_words = [
                "merhaba", "selam", "sa", "as", "nasilsin", "nasılsın",
                "naber", "iyi", "sagol", "sağol", "tesekkurler", "teşekkürler", "hello", "hi"
            ]
            excel_keywords = [
                "fiyat", "malzeme", "rapor", "stok", "kaç para", "ne kadar", "var mı", "fiyatı", "price", "cost"
            ]

            is_chat = any(cw in user_msg_lower for cw in chat_words)
            has_keyword = any(kw in user_msg_lower for kw in excel_keywords)

            current_user_message = user_text
            if has_keyword and not is_chat:
                excel_res = search_material_in_report(user_id, user_text)
                if isinstance(excel_res, dict) and excel_res.get("status") == "success":
                    live_data_str = json.dumps(excel_res["data"], ensure_ascii=False)
                    current_user_message += f"\n\n[EXCEL RAPORUNDAN GELEN CANLI VERİ (MUTLAKA YANITA YANSITILMALI)]:\n{live_data_str}"

            messages.append({"role": "user", "content": current_user_message})

        # 5. OpenRouter Asenkron İstek
        payload = {
            "models": FALLBACK_MODELS,
            "messages": messages,
            "temperature": 0.1,
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(OPENROUTER_URL, headers=HEADERS, json=payload)
            res_json = response.json()

            if response.status_code == 429:
                retry_after = (
                    res_json.get("error", {}).get("metadata", {}).get("retry_after_seconds")
                )
                if retry_after and retry_after <= 30:
                    print(f"⏳ 429 alındı, {retry_after} saniye bekleyip tekrar deneniyor...")
                    await asyncio.sleep(retry_after)
                    response = await client.post(OPENROUTER_URL, headers=HEADERS, json=payload)
                    res_json = response.json()

        ai_reply = ""
        if response.status_code == 200 and "choices" in res_json and len(res_json["choices"]) > 0:
            ai_reply = res_json["choices"][0]["message"].get("content") or ""

        if not ai_reply:
            print(f"⚠️ OpenRouter boş/hatalı yanıt ({response.status_code}): {res_json}")
            if response.status_code == 429:
                ai_reply = "⏳ Şu an yoğunluk var (ücretsiz model kapasitesi doldu). Birkaç dakika sonra tekrar dener misin?"
            elif response.status_code == 404:
                ai_reply = "⚠️ Kullanılan model artık kullanılamıyor. Bu, geliştiriciye bildirilmesi gereken bir durum (model listesinin güncellenmesi lazım)."
            elif response.status_code == 400:
                ai_reply = "⚠️ İstek formatında bir sorun oluştu. Bu, geliştiriciye bildirilmesi gereken bir durum."
            else:
                ai_reply = f"⚠️ Beklenmeyen bir hata oluştu ({response.status_code}). Tekrar dener misin?"

        # 6. Bellek Güncelleme ve Loglama
        memory.update_memory(user_id, logged_question, ai_reply)
        log_chat(user_id, username, logged_question, ai_reply)

        return ai_reply

    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dış servis bağlantı hatası: {exc!s}",
        ) from exc


# ==========================================
# JUDGE AGENT: DEĞERLENDİRME & PUANLAMA MOTORU
# ==========================================


async def judge_agent_evaluation(user_question: str, bot_response: str) -> dict:
    """Görüşmeyi 1-10 arası puanlayan ve teknik nedenini açıklayan Denetçi LLM."""
    judge_system_prompt = """Sen Elektrikli Araçlar, BMS, CAN Bus, Gömülü Sistemler ve Donanım Mühendisliği alanında uzman Baş Denetçisin (LLM-as-a-Judge).
Görevin: Kullanıcının sorusuna asistanın verdiği cevabın teknik doğruluğunu, yeterliliğini ve tutarlılığını denetlemektir.

Değerlendirme Kriterleri:
1. Teknik Doğruluk: Bilgiler mühendislik standartlarına (CAN Bus diferansiyel hatları, BMS hücre voltajları, mikrodenetleyici mimarileri vb.) uygun mu?
2. Kapsam Uygunluğu: Asistan konu dışına çıkmış mı veya gereksiz dolandırmış mı?
3. Soruya Tam Yanıt: Kullanıcının sorduğu şeyi doğrudan cevaplamış mı?

ÇIKTI KURALI:
SADECE ve SADECE aşağıdaki JSON formatında geçerli bir JSON çıktısı döndür. Markdown backtick veya fazladan hiçbir açıklama ekleme:
{
    "score": <1 ile 10 arasında tam sayı puan>,
    "status": "<Doğru | Kısmen Doğru | Hatalı>",
    "reason": "<Neden bu puanın verildiğini, varsa teknik hatayı veya eksikliği belirten 1-2 cümlelik net açıklama>"
}"""

    judge_messages = [
        {"role": "system", "content": judge_system_prompt},
        {
            "role": "user",
            "content": f"[KULLANICI SORUSU]: {user_question}\n\n[ASİSTAN YANITI]: {bot_response}",
        },
    ]

    payload = {
        "models": FALLBACK_MODELS,
        "messages": judge_messages,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(OPENROUTER_URL, headers=HEADERS, json=payload)
            if resp.status_code == 200:
                raw_content = resp.json()["choices"][0]["message"]["content"].strip()
                raw_content = raw_content.replace("```json", "").replace("```", "").strip()
                return json.loads(raw_content)
    except Exception as e:
        print(f"⚠️ Judge Agent Hatası: {e}")

    return {
        "score": 5,
        "status": "Değerlendirilemedi",
        "reason": "Judge Agent yanıtı ayrıştırılamadı veya API zaman aşımına uğradı.",
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    user_id = request.user_id
    username = request.username
    user_text = request.message.strip()
    image_base64 = request.image_base64

    if not user_text and not image_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mesaj veya görsel sağlanmalıdır.",
        )

    ai_reply = await process_chat_message(user_id, username, user_text, image_base64)
    return ChatResponse(response=ai_reply)


@app.post("/api/v1/chat/voice", response_model=ChatResponse)
async def voice_chat_endpoint(request: VoiceChatRequest) -> ChatResponse:
    user_id = request.user_id
    username = request.username

    if not request.audio_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ses verisi sağlanmalıdır.",
        )

    try:
        user_text = await transcribe_audio(request.audio_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ses metne çevrilirken hata oluştu: {exc!s}",
        ) from exc

    if not user_text.strip():
        return ChatResponse(response="⚠️ Sesli mesajdan bir metin çıkaramadım, tekrar dener misin?")

    ai_reply = await process_chat_message(user_id, username, user_text)
    return ChatResponse(response=ai_reply)


# ==========================================
# GÖREV 10: YÖNETİM & İZLEME PANELİ ENDPOINT'LERİ
# ==========================================


@app.get("/api/v1/admin/stats")
async def admin_stats():
    """Genel sistem metrikleri ve toplam sayaçlar."""
    return get_system_stats()


@app.get("/api/v1/admin/users")
async def admin_users():
    """Kullanıcı listesi ve son görülme bilgileri."""
    return get_all_users()


@app.get("/api/v1/admin/user/{user_id}/history")
async def admin_user_history(user_id: str):
    """Seçilen kullanıcının tam sohbet dökümü ve bellek özeti."""
    history = get_user_chat_history(user_id)
    session_data = memory.load_sessions().get(user_id, {})
    return {
        "user_id": user_id,
        "summary": session_data.get("summary", "Özet bulunmuyor."),
        "history": history,
    }


@app.get("/api/v1/admin/logs")
async def admin_logs(limit: int = 50):
    """Araç / Tool ve RAG çağrı logları."""
    return get_all_logs(limit=limit)


@app.post("/api/v1/admin/evaluate")
async def evaluate_message_endpoint(req: EvaluateRequest):
    """Admin panelinden seçilen konuşmayı Judge Agent ile denetler ve sonucu veri tabanına kaydeder."""
    result = await judge_agent_evaluation(req.user_question, req.bot_response)
    update_chat_evaluation(
        chat_id=req.chat_id,
        score=result.get("score", 0),
        status=result.get("status", "Bilinmiyor"),
        reason=result.get("reason", ""),
    )
    return result


@app.get("/api/v1/chat/history/{user_id}")
async def get_chat_history_endpoint(user_id: str):
    """Kullanıcının geçmiş mesajlarını web arayüzüne yükler."""
    return get_user_chat_history(user_id)


# ==========================================
# GÖREV 11: TELEGRAM WEBHOOK ENDPOINT
# ==========================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
bot_instance = telebot.TeleBot(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None


@app.post("/api/v1/telegram/webhook")
async def telegram_webhook(request: dict):
    """Telegram sunucularından gelen güncellemeleri doğrudan işler (Görev 11 Webhook)."""
    if not bot_instance:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TELEGRAM_TOKEN yapılandırılmamış.",
        )

    update = Update.de_json(request)
    if not update or not update.message:
        return {"status": "ignored"}

    message = update.message
    user_id = str(message.chat.id)
    username = (
        message.from_user.username
        or message.from_user.first_name
        or "TelegramUser"
    )

    # 1. Fotoğraf Mesajı Yakalama
    if message.photo:
        photo_info = message.photo[-1]
        file_info = bot_instance.get_file(photo_info.file_id)
        downloaded_file = bot_instance.download_file(file_info.file_path)
        image_base64 = base64.b64encode(downloaded_file).decode("utf-8")
        caption = message.caption or ""

        reply = await process_chat_message(
            user_id, username, caption, image_base64
        )
        bot_instance.send_message(message.chat.id, reply)

    # 2. Metin Mesajı Yakalama
    elif message.text:
        if message.text.startswith("/start") or message.text.startswith(
            "/help"
        ):
            welcome = (
                "⚡ *EV & Embedded Systems AI Asistanı Aktif*\n\n"
                "• CAN Bus, BMS ve motor sürücü sorularınızı iletebilirsiniz.\n"
                "• Mukayese raporu stok/fiyat sorgusu yapabilirsiniz.\n"
                "• Donanım fotoğrafı göndererek analiz alabilirsiniz."
            )
            bot_instance.send_message(
                message.chat.id, welcome, parse_mode="Markdown"
            )
        else:
            reply = await process_chat_message(user_id, username, message.text)
            bot_instance.send_message(message.chat.id, reply)

    return {"status": "ok"}


# Bu satırın hemen altına uvicorn başlatma bloğu gelecek:
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)