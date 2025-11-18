import sqlite3
import hashlib

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

conn = sqlite3.connect('expenses.db')
c = conn.cursor()

# --- 1. Users Table ---
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL
)
''')

# --- 2. Expenses Table ---
c.execute('''
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    expense_date DATE NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT,
    FOREIGN KEY (username) REFERENCES users (username)
)
''')

# --- 3. Goals Table ---
c.execute('''
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    goal_name TEXT NOT NULL,
    target_amount REAL NOT NULL,
    current_amount REAL DEFAULT 0,
    image_url TEXT,
    FOREIGN KEY (username) REFERENCES users (username)
)
''')

# --- 4. Badges Table ---
c.execute('''
CREATE TABLE IF NOT EXISTS badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    badge_name TEXT NOT NULL,
    date_unlocked DATE NOT NULL,
    UNIQUE(username, badge_name),
    FOREIGN KEY (username) REFERENCES users (username)
)
''')

# --- 5. Debts Table (REQUIRED FOR SPLIT BILL) ---
c.execute('''
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL,
    payer_username TEXT NOT NULL,
    owes_username TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT DEFAULT 'unpaid',
    FOREIGN KEY (expense_id) REFERENCES expenses (id),
    FOREIGN KEY (payer_username) REFERENCES users (username),
    FOREIGN KEY (owes_username) REFERENCES users (username)
)
''')

# Add default users
try:
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
              ('Itachibanker19', make_hashes('Killer1980')))
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
              ('demo', make_hashes('demo123')))
except sqlite3.IntegrityError:
    print("Default users already exist.")

conn.commit()
conn.close()
print("✅ Database updated with ALL tables (Users, Expenses, Goals, Badges, Debts).")
