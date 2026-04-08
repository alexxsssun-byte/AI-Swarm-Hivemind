import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "banker_memory.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Projects table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Conversations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    
    # Assumptions table (stores structured data as JSON for flexibility)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS project_state (
            project_id INTEGER PRIMARY KEY,
            assumptions_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    
    # File Tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_or_create_project(name: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM projects WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        project_id = row['id']
    else:
        cursor.execute("INSERT INTO projects (name) VALUES (?)", (name,))
        project_id = cursor.lastrowid
        cursor.execute("INSERT INTO project_state (project_id, assumptions_json) VALUES (?, ?)", (project_id, "{}"))
        conn.commit()
    conn.close()
    return project_id

def get_all_projects() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM projects ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [row['name'] for row in rows]

def summarize_old_messages(project_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''SELECT id, role, content FROM conversations WHERE project_id = ? ORDER BY timestamp ASC''', (project_id,))
        rows = cursor.fetchall()
        
        if len(rows) > 15:
            # Keep the last 10 messages untouched, squash the rest
            to_summarize = rows[:-10]
            ids_to_delete = [r['id'] for r in to_summarize]
            
            text_to_summarize = ""
            for r in to_summarize:
                text_to_summarize += f"[{r['role']}]: {r['content'][:1000]}\n"
                
            from google import genai
            client = genai.Client()
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Summarize this early conversation string into distinct, strictly factual context pillars for an AI memory bank. Preserve crucial facts, numbers, and decisions. Be extremely concise:\n\n{text_to_summarize}"
            )
            summary = resp.text
            
            # Append to project_state assumptions
            cursor.execute("SELECT assumptions_json FROM project_state WHERE project_id = ?", (project_id,))
            state_row = cursor.fetchone()
            current_data = json.loads(state_row['assumptions_json']) if state_row else {}
            
            old_summary = current_data.get("Global_Summary", "")
            current_data["Global_Summary"] = (old_summary + "\n" + summary).strip()
            
            cursor.execute('''
                UPDATE project_state 
                SET assumptions_json = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE project_id = ?
            ''', (json.dumps(current_data), project_id))
            
            placeholders = ','.join(['?']*len(ids_to_delete))
            cursor.execute(f"DELETE FROM conversations WHERE id IN ({placeholders})", ids_to_delete)
            conn.commit()
            
        conn.close()
    except Exception as e:
        print(f"Memory Checkpoint Failed: {e}")

def add_message(project_id: int, role: str, content: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO conversations (project_id, role, content) VALUES (?, ?, ?)", 
                   (project_id, role, content))
    conn.commit()
    conn.close()
    
    import threading
    threading.Thread(target=summarize_old_messages, args=(project_id,)).start()

def get_conversation_history(project_id: int, limit: int = 20) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT role, content FROM (
            SELECT role, content, timestamp FROM conversations 
            WHERE project_id = ? 
            ORDER BY timestamp DESC LIMIT ?
        ) ORDER BY timestamp ASC
    ''', (project_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": row['role'], "content": row['content']} for row in rows]

def update_assumptions(project_id: int, updates: dict):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT assumptions_json FROM project_state WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    if row:
        current_data = json.loads(row['assumptions_json'])
    else:
        current_data = {}
        
    current_data.update(updates)
    
    cursor.execute('''
        UPDATE project_state 
        SET assumptions_json = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE project_id = ?
    ''', (json.dumps(current_data), project_id))
    
    conn.commit()
    conn.close()

def get_assumptions(project_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT assumptions_json FROM project_state WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row['assumptions_json'])
    return {}

def track_file(project_id: int, filename: str, file_type: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO files (project_id, filename, file_type) VALUES (?, ?, ?)", 
                   (project_id, filename, file_type))
    conn.commit()
    conn.close()

def get_tracked_files(project_id: int) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename, file_type FROM files WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"filename": row['filename'], "file_type": row['file_type']} for row in rows]

def delete_project(project_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM files WHERE project_id = ?", (project_id,))
    cursor.execute("DELETE FROM project_state WHERE project_id = ?", (project_id,))
    cursor.execute("DELETE FROM conversations WHERE project_id = ?", (project_id,))
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

# Initialize DB on load
setup_database()
