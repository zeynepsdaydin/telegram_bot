import json
import os

MEMORY_FILE = "sessions.json"

def load_sessions():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_sessions(sessions):
    with open(MEMORY_FILE, 'w') as f:
        json.dump(sessions, f, indent=4)

def update_memory(user_id, user_text, ai_reply):
    sessions = load_sessions()
    user_id = str(user_id)
    if user_id not in sessions:
        sessions[user_id] = {"history": [], "summary": "Henüz özet yok."}
    
    sessions[user_id]["history"].append({"role": "user", "content": user_text})
    sessions[user_id]["history"].append({"role": "assistant", "content": ai_reply})
    
    if len(sessions[user_id]["history"]) > 20:
        sessions[user_id]["history"] = sessions[user_id]["history"][-10:]
        
    save_sessions(sessions)