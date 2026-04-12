-- Delete tables if they already exist (for fresh start)
DROP TABLE IF EXISTS borrow_transactions;
DROP TABLE IF EXISTS borrow_requests;
DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS users;

-- Users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT DEFAULT 'member',
    location TEXT,
    contact_info TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Books table
CREATE TABLE books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT DEFAULT 'available',
    location_notes TEXT,
    type TEXT NOT NULL,
    image_file TEXT, -- Added this to store "data.jpg", "python.webp", etc.
    file_path TEXT,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users (id)
);

-- Borrow Requests table
CREATE TABLE borrow_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    borrower_id INTEGER NOT NULL,
    proposed_date TEXT,
    proposed_time TEXT,
    proposed_location TEXT,
    status TEXT DEFAULT 'pending',
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books (id),
    FOREIGN KEY (borrower_id) REFERENCES users (id)
);

-- Borrow Transactions table
CREATE TABLE borrow_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    borrower_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    request_id INTEGER,
    borrow_date TIMESTAMP,
    return_date TIMESTAMP,
    status TEXT DEFAULT 'borrowed',
    FOREIGN KEY (book_id) REFERENCES books (id),
    FOREIGN KEY (borrower_id) REFERENCES users (id),
    FOREIGN KEY (owner_id) REFERENCES users (id),
    FOREIGN KEY (request_id) REFERENCES borrow_requests (id)
);