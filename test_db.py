import sqlite3

# Connect to database
conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row  # Makes results accessible like dictionaries
cursor = conn.cursor()

print("=" * 50)
print("DATABASE TEST")
print("=" * 50)

# Test 1: Get all users
print("\n📊 TEST 1: Fetching all users...")
users = cursor.execute('SELECT * FROM users').fetchall()
print(f"Found {len(users)} users:")
for user in users:
    print(f"  - {user['username']} ({user['email']}) - Role: {user['role']}")

# Test 2: Get all books
print("\n📚 TEST 2: Fetching all books...")
books = cursor.execute('SELECT * FROM books').fetchall()
print(f"Found {len(books)} books:")
for book in books:
    print(f"  - {book['title']} by {book['author']} ({book['book_type']})")

# Test 3: Get books with owner names (JOIN query)
print("\n🔗 TEST 3: Fetching books with owner names (JOIN)...")
books_with_owners = cursor.execute('''
    SELECT b.title, b.author, b.book_type, u.username as owner_name
    FROM books b
    JOIN users u ON b.owner_id = u.id
''').fetchall()
for book in books_with_owners:
    print(f"  - {book['title']} (Owner: {book['owner_name']})")

# Test 4: Get only physical books
print("\n📦 TEST 4: Fetching only physical books...")
physical_books = cursor.execute('''
    SELECT * FROM books WHERE book_type = "physical"
''').fetchall()
print(f"Found {len(physical_books)} physical books:")
for book in physical_books:
    print(f"  - {book['title']}")

# Test 5: Search books by title
print("\n🔍 TEST 5: Searching for books with 'Python' in title...")
search_results = cursor.execute('''
    SELECT * FROM books WHERE title LIKE ?
''', ('%Python%',)).fetchall()
for book in search_results:
    print(f"  - {book['title']} by {book['author']}")

conn.close()

print("\n" + "=" * 50)
print("✅ All tests completed successfully!")
print("=" * 50)