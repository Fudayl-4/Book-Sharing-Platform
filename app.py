from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-later'

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database connection function
def get_db_connection():
    connection = sqlite3.connect('database.db')
    connection.row_factory = sqlite3.Row
    return connection

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email, role):
        self.id = id
        self.username = username
        self.email = email
        self.role = role

# Load user for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['email'], user['role'])
    return None

# Home page - Display books from database
@app.route('/')
def index():

    # Get the search query from the URL e.g. /?q=python
    # If nothing is searched, q will be empty string ''
    q = request.args.get('q', '')

    conn = get_db_connection()

    if q:
        # If user searched something — filter books by title, author or category
        # % is a wildcard in SQL LIKE — means "anything before or after"
        # so %python% matches "Python Crash Course", "Learn Python" etc.
        search = '%' + q + '%'
        books = conn.execute('''
            SELECT b.*, u.username as owner_name
            FROM books b
            JOIN users u ON b.owner_id = u.id
            WHERE b.status = "available"
            AND (b.title LIKE ? OR b.author LIKE ? OR b.category LIKE ?)
        ''', (search, search, search)).fetchall()
    else:
        # No search — show all available books as normal
        books = conn.execute('''
            SELECT b.*, u.username as owner_name
            FROM books b
            JOIN users u ON b.owner_id = u.id
            WHERE b.status = "available"
        ''').fetchall()

    conn.close()
    return render_template('index.html', books=books, q=q)

# Register page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Hash the password
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                        (username, email, hashed_password))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists!', 'danger')
            conn.close()
    
    return render_template('register.html')

# Login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['email'], user['role'])
            login_user(user_obj)
            flash('Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('dashboard'))
        else:
            flash('Invalid email or password!', 'danger')
    
    return render_template('login.html')

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# Dashboard (requires login)
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    
    # Get user's books
    my_books = conn.execute('SELECT * FROM books WHERE owner_id = ?', 
                           (current_user.id,)).fetchall()
    
    # Get borrowed books
    borrowed_books = conn.execute('''
        SELECT b.*, u.username as owner_name 
        FROM borrow_transactions bt
        JOIN books b ON bt.book_id = b.id
        JOIN users u ON b.owner_id = u.id
        WHERE bt.borrower_id = ? AND bt.status = "borrowed"
    ''', (current_user.id,)).fetchall()
    
    conn.close()
    return render_template('dashboard.html', my_books=my_books, borrowed_books=borrowed_books)

#Borrow Page
# Borrow page - shows the form AND handles form submission
@app.route('/borrow/<int:book_id>', methods=['GET', 'POST'])
@login_required
def borrow(book_id):

    # Connect to database
    conn = get_db_connection()

    # Fetch the book using the ID from the URL
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    # If book doesn't exist, go back home
    if book is None:
        flash('Book not found!', 'danger')
        conn.close()
        return redirect(url_for('index'))

    # ---------- When user submits the form (POST request) ----------
    if request.method == 'POST':

        # Get the data the user typed in the form
        proposed_date     = request.form['borrowDate']
        proposed_time     = request.form['borrowTime']
        proposed_location = request.form['borrowLocation']
        notes             = request.form['notes']

        # Save this borrow request into the database
        conn.execute('''
            INSERT INTO borrow_requests 
            (book_id, borrower_id, proposed_date, proposed_time, proposed_location, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (book_id, current_user.id, proposed_date, proposed_time, proposed_location, 'pending'))

        conn.commit()
        conn.close()

        # Tell the user it worked
        flash('Borrow request sent successfully! Wait for the owner to accept.', 'success')

        # Send them back to home page
        return redirect(url_for('index'))

    # ---------- When user just opens the page (GET request) ----------
    # Just show the borrow form with book details
    conn.close()
    return render_template('borrow.html', book=book)

# Add Book page - show form and handle submission
@app.route('/add_book', methods=['GET', 'POST'])
@login_required  # only logged in users can add books
def add_book():

    # When user submits the form
    if request.method == 'POST':

        # Get basic book details from the form
        title    = request.form['title']
        author   = request.form['author']
        category = request.form['category']
        booktype = request.form['type']  # 'physical' or 'digital'

        # These will be empty by default
        location_notes = None
        file_path      = None

        # If physical book - get location notes
        if booktype == 'physical':
            location_notes = request.form['location_notes']

        # If digital book - get download link
        if booktype == 'digital':
            file_path = request.form['download_link']

        # Save the book into the database
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO books (owner_id, title, author, category, type, location_notes, file_path, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (current_user.id, title, author, category, booktype, location_notes, file_path, 'available'))

        conn.commit()
        conn.close()

        flash('Your book has been listed successfully!', 'success')
        return redirect(url_for('dashboard'))

    # When user just opens the page - show the empty form
    return render_template('add_book.html')

# Delete a book - only the owner can delete their own book
@app.route('/delete_book/<int:book_id>')
@login_required
def delete_book(book_id):

    conn = get_db_connection()

    # Fetch the book first to check who owns it
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    # If book doesn't exist
    if book is None:
        flash('Book not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Security check — make sure the logged in user is the owner
    # Without this, any user could delete anyone's book by changing the URL
    if book['owner_id'] != current_user.id:
        flash('You can only delete your own books!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Safe to delete now
    conn.execute('DELETE FROM books WHERE id = ?', (book_id,))
    conn.commit()
    conn.close()

    flash('Book deleted successfully!', 'success')
    return redirect(url_for('dashboard'))


# Edit a book - show form with existing data and save changes
@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):

    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    # Book not found
    if book is None:
        flash('Book not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Security check — only owner can edit
    if book['owner_id'] != current_user.id:
        flash('You can only edit your own books!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # When user submits the edited form
    if request.method == 'POST':
        title          = request.form['title']
        author         = request.form['author']
        category       = request.form['category']
        location_notes = request.form.get('location_notes', '')
        download_link  = request.form.get('download_link', '')

        # Update the book row in database
        conn.execute('''
            UPDATE books
            SET title = ?, author = ?, category = ?, location_notes = ?, file_path = ?
            WHERE id = ?
        ''', (title, author, category, location_notes, download_link, book_id))

        conn.commit()
        conn.close()

        flash('Book updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    conn.close()
    # Pass existing book data to the form so fields are pre-filled
    return render_template('edit_book.html', book=book)










# Run the app
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)