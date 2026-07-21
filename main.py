import os
import requests
import telebot
import memory
import json
from dotenv import load_dotenv
from database import log_chat, init_db
from material_service import search_material_in_report

load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
init_db()


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

# --- GÖREV 2 & GÖREV 3: ARAC (TOOL) ŞEMALARI ---
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_material_in_report",
            "description": "Excel mukayese raporu içerisinde elektrikli araç malzemeleri, ürün adları, birim fiyatları, satın alma linkleri ve gerekçelerini arar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Aranacak malzemenin adı (Örn: 'motor', 'sürücü', 'kablo', 'bms')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_context_summary",
            "description": "Kullanıcının bu oturumdaki geçmiş konuşmalarının özetini ve teknik arka planını getirir. Kullanıcı geçmişte bahsettiği bir projeden, motordan veya bileşenden bahsettiğinde veya botun kullanıcıyı tanıması gerektiğinde çağrılmalıdır.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

def get_ai_response(user_message, session, user_id):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY').strip()}",
        "Content-Type": "application/json",
    }
    
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
4. If you need to remember past technical details (project name, motor model, components used) or recognize the user's background, you MUST call the 'get_user_context_summary' tool before asking the user.
5. REMEMBER past details fetched from the tool and do not ask for them again.
6. Make the user feel recognized by tailoring your suggestions based on their technical background.
7. Talk ONLY about hardware, software, embedded systems, CAN Bus, BMS, and motor drivers. Refuse non-engineering questions.
8. If the user asks about component prices, materials, or details inside the project report, you MUST use the 'search_material_in_report' tool to fetch live data.
9. When you use the 'search_material_in_report' tool, you MUST explicitly include the "fiyat_listesi" (all supplier prices), "link", and "miktar" details of the products in your final response."""
    
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    if "history" in session:
        messages.extend(session["history"][-10:])

    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": "google/gemma-4-26b-a4b-it:free",
        "messages": messages,
        "tools": tools_schema,
        "temperature": 0.1,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response_json = response.json()
        
        print(f"API Yanıtı: {response.text}")
        
        if response.status_code != 200:
            return f"Teknik bir hata ile karşılaştım (API Hata Kodu: {response.status_code})."
            
        if "choices" in response_json and len(response_json["choices"]) > 0:
            choice = response_json["choices"][0]["message"]
        elif "error" in response_json:
            return f"API Hatası (OpenRouter): {response_json['error'].get('message', 'Detay belirtilmedi')}"
        else:
            return "Şu an sunucu yoğunluğu nedeniyle yanıt üretilemedi, lütfen tekrar deneyin."
        
        # --- TOOL CALLING KONTROL DÖNGÜSÜ ---
        if "tool_calls" in choice:
            tool_call = choice["tool_calls"][0]
            function_name = tool_call["function"]["name"]
            arguments = json.loads(tool_call["function"]["arguments"] or "{}")
            
            # GÖREV 2: Excel Malzeme/Fiyat Araması
            if function_name == "search_material_in_report":
                search_query = arguments.get("query", "")
                print(f"[TOOL] Gemma Excel araması istedi: {search_query}")
                tool_result = search_material_in_report(user_id, search_query)
                
                messages.append(choice)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })
                
            # GÖREV 3 EKSİĞİ: Bağlam/Geçmiş Özeti Sorgulama Aracı
            elif function_name == "get_user_context_summary":
                print("[TOOL] Gemma Oturum Geçmişini İstedi.")
                summary_data = session.get("summary", "Henüz bir geçmiş veya özet bulunmuyor.")
                
                messages.append(choice)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "content": json.dumps({"oturum_ozeti": summary_data}, ensure_ascii=False)
                })
            
            # Aracı çalıştırdıktan sonra elde edilen veriyle modele ikinci ve nihai çağrıyı yapıyoruz
            second_payload = {
                "model": "google/gemma-4-26b-a4b-it:free",
                "messages": messages,
                "temperature": 0.1,
            }
            
            second_response = requests.post(url, headers=headers, json=second_payload, timeout=15)
            second_json = second_response.json()
            
            if "choices" in second_json and len(second_json["choices"]) > 0:
                return second_json["choices"][0]["message"]["content"]
            else:
                return "Canlı veri işlenirken sunucudan geçersiz bir yanıt döndü."
                
        if "content" in choice and choice["content"]:
            return choice["content"]
        else:
            return "Boş veya geçersiz bir yanıt döndü."
        
    except Exception as e:
        return f"Bağlantı sırasında bir hata oluştu: {str(e)}"


# --- MESAJ YÖNETİCİSİ ---
@bot.message_handler(func=lambda message: True)
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
        
        ai_reply = get_ai_response(user_text, session, user_id)
        
        memory.update_memory(user_id, user_text, ai_reply)

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