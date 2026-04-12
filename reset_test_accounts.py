import sqlite3
from werkzeug.security import generate_password_hash

# Connect to database
conn = sqlite3.connect('database.db')

# Update test account passwords
test_accounts = [
    ('admin@bookshare.com', 'admin123'),
    ('john@example.com', 'password123'),
    ('sarah@example.com', 'password123')
]

print("Resetting test account passwords...\n")

for email, password in test_accounts:
    hashed = generate_password_hash(password)
    conn.execute('UPDATE users SET password = ? WHERE email = ?', (hashed, email))
    print(f"✅ Reset password for: {email}")
    print(f"   Password: {password}\n")

conn.commit()
conn.close()

print("Done! You can now login with:")
print("- admin@bookshare.com / admin123")
print("- john@example.com / password123")
print("- sarah@example.com / password123")