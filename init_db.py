import sqlite3

connection = sqlite3.connect('database.db')

with open('schema.sql') as f:
    connection.executescript(f.read())

cur = connection.cursor()

# Create a sample user
cur.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
            ('admin', 'admin@example.com', 'admin123', 'Member'))

# Sample Books matching your specific image files
sample_books = [
    ('Data Analytics', 'Wiley', 'Computer Science', 'Physical', 'data.jpg'),
    ('Python Crash Course', 'Eric Matthes', 'Programming', 'Digital', 'python.webp'),
    ('Cloud Computing', 'Dr. Kumar Saurabh', 'Computer Science', 'Physical', 'cloud.jpg'),
    ('Atomic Habits', 'James Clear', 'Self Improvement', 'Digital', 'atomic habits.webp'),
    ('48 Rules of Power', 'Robert Greene', 'Productivity', 'Physical', 'power.webp'),
    ('The 5am Club', 'Robin Sharma', 'Productivity', 'Digital', '5am.jpg')
]

for book in sample_books:
    cur.execute("""
        INSERT INTO books (owner_id, title, author, category, type, image_file) 
        VALUES (?, ?, ?, ?, ?, ?)""",
        (1, book[0], book[1], book[2], book[3], book[4])
    )

connection.commit()
connection.close()

print("Database reset! 6 unique books with images added.")