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

if __name__ == "__main__":
    init_db()