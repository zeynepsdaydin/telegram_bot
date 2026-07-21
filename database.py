import sqlite3
from datetime import datetime

DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            user_question TEXT,
            bot_response TEXT,
            timestamp DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action TEXT,
            query TEXT,
            result TEXT,
            timestamp DATETIME
        )
    ''')
    
    conn.commit()
    conn.close()

def log_chat(username, user_question, bot_response):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO chat_history (username, user_question, bot_response, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (username, user_question, bot_response, datetime.now()))
    conn.commit()
    conn.close()

def log_api_call(user_id, action, query, result):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO api_logs (user_id, action, query, result, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(user_id), action, query, str(result), datetime.now()))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()