import sqlite3
from werkzeug.security import generate_password_hash

password = generate_password_hash("password123")

# Connect to database
connection = sqlite3.connect('database.db')
cursor = connection.cursor()

print("Adding sample data...")

# Add sample users
users = [
    ('admin', 'admin@example.com', 'admin123', 'admin'),
    ('john_doe', 'john@example.com', 'password123', 'member'),
    ('sarah_smith', 'sarah@example.com', 'password123', 'member'),
]

print("\n📝 Adding users...")
for username, email, password, role in users:
    hashed_password = generate_password_hash(password)
    try:
        cursor.execute('''INSERT INTO users (username, email, password, role) 
                         VALUES (?, ?, ?, ?)''',
                      (username, email, hashed_password, role))
        print(f"✅ Added user: {username}")
    except sqlite3.IntegrityError:
        print(f"⚠️  User {username} already exists, skipping...")

# Commit users first
connection.commit()

# Add sample books
books = [
    (2, 'Data Analytics', 'Wiley', 'Computer Science', 'physical', 'Main Library, Shelf A3'),
    (2, 'Python Crash Course', 'Eric Matthes', 'Programming', 'digital', None),
    (3, 'Cloud Computing', 'Dr Kumar Saurabh', 'Computer Science', 'physical', 'Available at City Center'),
    (3, 'Atomic Habits', 'James Clear', 'Productivity', 'digital', None),
    (2, '48 Rules of Power', 'Robert Greene', 'Self-Help', 'physical', 'University Campus'),
    (3, 'The 5am Club', 'Robin Sharma', 'Productivity', 'digital', None),
]

print("\n📚 Adding books...")
for owner_id, title, author, category, book_type, location_notes in books:
    cursor.execute('''INSERT INTO books 
                     (owner_id, title, author, category, book_type, location_notes) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (owner_id, title, author, category, book_type, location_notes))
    print(f"✅ Added book: {title}")

# Commit and close
connection.commit()
connection.close()

print("\n✅ Sample data added successfully!")
print("\n📊 Summary:")
print(f"   - {len(users)} users added")
print(f"   - {len(books)} books added")
print("\n🔐 Test Accounts:")
print("   Admin: admin@bookshare.com / admin123")
print("   User1: john@example.com / password123")
print("   User2: sarah@example.com / password123")