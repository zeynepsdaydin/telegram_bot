from contextlib import closing
from datetime import datetime, timezone
import sqlite3

DB_NAME = "bot_database.db"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_NAME)


def init_db() -> None:
    with closing(get_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                username TEXT,
                user_question TEXT,
                bot_response TEXT,
                timestamp DATETIME
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                action TEXT,
                query TEXT,
                result TEXT,
                timestamp DATETIME
            )
        """)


def log_chat(
    user_id: str,
    username: str | None,
    user_question: str,
    bot_response: str,
) -> None:
    with closing(get_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_history (user_id, username, user_question, bot_response, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                str(user_id),
                username,
                user_question,
                bot_response,
                datetime.now(timezone.utc),
            ),
        )


def log_api_call(user_id: str, action: str, query: str, result: str) -> None:
    with closing(get_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO api_logs (user_id, action, query, result, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """,
            (str(user_id), action, query, str(result), datetime.now(timezone.utc)),
        )


# --- YÖNETİM PANELİ İÇİN OKUMA FONKSİYONLARI ---


def get_all_users() -> list[dict]:
    """Sistemle etkileşime giren tekil kullanıcı listesini döner."""
    with closing(get_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, username, MAX(timestamp) as last_seen, COUNT(id) as total_messages
            FROM chat_history
            GROUP BY user_id
            ORDER BY last_seen DESC
        """)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_user_chat_history(user_id: str) -> list[dict]:
    """Belirli bir kullanıcının tüm konuşma dökümünü döner."""
    with closing(get_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, username, user_question, bot_response, timestamp
            FROM chat_history
            WHERE user_id = ?
            ORDER BY id ASC
        """,
            (str(user_id),),
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_all_logs(limit: int = 50) -> list[dict]:
    """RAG / Tool çağrı loglarını listeler."""
    with closing(get_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, action, query, result, timestamp
            FROM api_logs
            ORDER BY id DESC
            LIMIT ?
        """,
            (limit,),
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_system_stats() -> dict:
    """Dashboard özet metriklerini hesaplar."""
    with closing(get_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(id) FROM chat_history")
        total_chats = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM chat_history")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(id) FROM api_logs")
        total_tool_calls = cursor.fetchone()[0]

        return {
            "total_messages": total_chats,
            "total_users": total_users,
            "total_tool_calls": total_tool_calls,
        }


if __name__ == "__main__":
    init_db()