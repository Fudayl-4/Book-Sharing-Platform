import sqlite3

conn = sqlite3.connect('database.db')

# Add is_blocked column to users table
conn.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")

conn.commit()
conn.close()
print('Done!')