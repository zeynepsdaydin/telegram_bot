import os
import json

MEMORY_FILE = "sessions.json"

def load_sessions():
    """Tüm kullanıcı oturumlarını dosyadan okur."""
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Bellek dosyası okunurken hata oluştu, sıfırlanıyor: {e}")
        return {}

def save_sessions(sessions):
    """Tüm kullanıcı oturumlarını dosyaya yazar."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Bellek dosyası kaydedilirken hata oluştu: {e}")

def update_memory(user_id, user_message, ai_reply):
    """
    Kullanıcı mesajını ve AI yanıtını geçmişe ekler.
    Geçmişteki teknik detayları analiz ederek oturum özetini (summary) günceller.
    """
    user_id = str(user_id)
    sessions = load_sessions()


    if user_id not in sessions:
        sessions[user_id] = {
            "history": [],
            "summary": "Kullanıcı elektrikli araç ve gömülü sistemler projesi üzerinde çalışan bir mühendis."
        }

    session = sessions[user_id]

    session["history"].append({"role": "user", "content": user_message})
    session["history"].append({"role": "assistant", "content": ai_reply})

  
    if len(session["history"]) > 20:
        session["history"] = session["history"][-20:]

  
    current_summary = session.get("summary", "")
    
    keywords = {
        "motor": "Motor ve motor sürücü ünitesi detayları",
        "can": "CAN Bus iletişim protokolü parametreleri",
        "bms": "BMS (Batarya Yönetim Sistemi) yapılandırması",
        "lora": "LoRa kablosuz haberleşme modülleri",
        "arduino": "Arduino tabanlı donanım mimarisi",
        "nextion": "Nextion HMI ekran arayüzü tasarımı"
    }

    updated_notes = []
    for key, desc in keywords.items():
        if key in user_message.lower() and desc not in current_summary:
            updated_notes.append(f"- {desc}: {user_message[:100]}")

    if updated_notes:
        new_notes_str = "\n".join(updated_notes)
        session["summary"] = f"{current_summary}\n{new_notes_str}"

    save_sessions(sessions)

def clear_session(user_id):
    """Kullanıcının tüm geçmiş ve özet verilerini sıfırlar."""
    user_id = str(user_id)
    sessions = load_sessions()
    if user_id in sessions:
        sessions[user_id] = {
            "history": [],
            "summary": "Oturum sıfırlandı. Yeni teknik süreç başladı."
        }
        save_sessions(sessions)