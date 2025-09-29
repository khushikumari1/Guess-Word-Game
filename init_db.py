import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = 'guess_the_word.db'

# 20 five-letter English words for the game
WORDS = [
    'ABOUT', 'ABOVE', 'ABUSE', 'ACTOR', 'ACUTE', 'ADMIT', 'ADOPT', 'ADULT', 'AFTER', 'AGAIN',
    'AGENT', 'AGREE', 'AHEAD', 'ALARM', 'ALBUM', 'ALERT', 'ALIEN', 'ALIGN', 'ALIKE', 'ALIVE'
]

def init_database():
    """Initialize the database with tables and sample data"""
    conn = sqlite3.connect(DATABASE)
    
    # Create tables
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'player',
            date_registered TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS guesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            guess TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (word_id) REFERENCES words (id)
        )
    ''')
    
    # Insert sample words
    print("Inserting sample words...")
    for word in WORDS:
        try:
            conn.execute('INSERT INTO words (word) VALUES (?)', (word,))
            print(f"Added word: {word}")
        except sqlite3.IntegrityError:
            print(f"Word {word} already exists, skipping...")
    
    # Create default admin user
    admin_username = 'admin'
    admin_password = 'Admin123$'  # Change this in production!
    admin_password_hash = generate_password_hash(admin_password)
    
    try:
        conn.execute('''
            INSERT INTO users (username, password_hash, role) 
            VALUES (?, ?, ?)
        ''', (admin_username, admin_password_hash, 'admin'))
        print(f"Created admin user: {admin_username}")
        print(f"Admin password: {admin_password}")
        print("⚠️  IMPORTANT: Change the admin password in production!")
    except sqlite3.IntegrityError:
        print("Admin user already exists, skipping...")
    
    conn.commit()
    conn.close()
    print("Database initialization completed!")

if __name__ == '__main__':
    init_database()
