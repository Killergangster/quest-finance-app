import sqlite3
import hashlib

# Function to hash passwords
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# Connect to the database
conn = sqlite3.connect('expenses.db')
c = conn.cursor()

# --- USERS TABLE ---
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL
)
''')

# --- EXPENSES TABLE ---
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

# --- GOALS TABLE ---
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

# --- BADGES TABLE ---
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

# --- DEBTS TABLE ---
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

# --- Add default users (with custom admin) ---
try:
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
              ('Itachibanker19', make_hashes('Killer1980')))
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
              ('demo', make_hashes('demo123')))
except sqlite3.IntegrityError:
    print("Default users already exist.")

# Commit changes and close
conn.commit()
conn.close()

print("✅ expenses.db database is ready with all features!")
