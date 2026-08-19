import json
import os
from threading import Lock

MEMORY_FILE = "sessions.json"
_file_lock = Lock()


def load_sessions() -> dict:
    with _file_lock:
        if not os.path.exists(MEMORY_FILE):
            return {}
        try:
            with open(MEMORY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}


def save_sessions(sessions: dict) -> None:
    with _file_lock:
        try:
            temp_file = f"{MEMORY_FILE}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(sessions, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, MEMORY_FILE)
        except OSError as e:
            print(f"Bellek kayıt hatası: {e!s}")


def update_memory(user_id: str, user_message: str, ai_reply: str) -> None:
    user_id = str(user_id)
    sessions = load_sessions()

    if user_id not in sessions:
        sessions[user_id] = {
            "history": [],
            "summary": "Kullanıcı elektrikli araç ve gömülü sistemler geliştiricisi.",
        }

    session = sessions[user_id]
    session["history"].append({"role": "user", "content": user_message})
    session["history"].append({"role": "assistant", "content": ai_reply})

    if len(session["history"]) > 20:
        session["history"] = session["history"][-20:]

    current_summary = session.get("summary", "")
    keywords = {
        "motor": "Motor & Motor Sürücü",
        "can": "CAN Bus Protokolü",
        "bms": "BMS / Batarya Yönetimi",
        "lora": "LoRa Haberleşme",
        "arduino": "Arduino Mimarisi",
        "nextion": "Nextion HMI Paneli",
        "telemetri": "Telemetri Veri Akışı",
    }

    user_msg_lower = user_message.lower()
    updated_notes = [
        f"- {desc}: {user_message[:80]}"
        for key, desc in keywords.items()
        if key in user_msg_lower and desc not in current_summary
    ]

    if updated_notes:
        session["summary"] = f"{current_summary}\n" + "\n".join(updated_notes)

    save_sessions(sessions)


def clear_session(user_id: str) -> None:
    user_id = str(user_id)
    sessions = load_sessions()
    if user_id in sessions:
        sessions[user_id] = {
            "history": [],
            "summary": "Oturum sıfırlandı. Yeni teknik süreç.",
        }
        save_sessions(sessions)