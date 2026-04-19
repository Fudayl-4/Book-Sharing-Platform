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

# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()

    # Get owner's books, and if borrowed, also fetch exchange details
    my_books = conn.execute('''
    SELECT b.*,
           br.proposed_date, br.proposed_time, br.proposed_location,
           u.username as borrower_name
    FROM books b
    LEFT JOIN borrow_requests br ON br.book_id = b.id AND br.status = "accepted"
    LEFT JOIN users u ON br.borrower_id = u.id
    WHERE b.owner_id = ?
''', (current_user.id,)).fetchall()


    # Get borrowed books WITH exchange details
    borrowed_books = conn.execute('''
        SELECT b.*, u.username as owner_name,
               br.proposed_date, br.proposed_time, br.proposed_location
        FROM borrow_transactions bt
        JOIN books b ON bt.book_id = b.id
        JOIN users u ON b.owner_id = u.id
        JOIN borrow_requests br ON bt.request_id = br.id
        WHERE bt.borrower_id = ? AND bt.status = "borrowed"
    ''', (current_user.id,)).fetchall()

    # Get incoming borrow requests on owner's books
    incoming_requests = conn.execute('''
        SELECT br.*, b.title as book_title, b.author as book_author,
               u.username as borrower_name
        FROM borrow_requests br
        JOIN books b ON br.book_id = b.id
        JOIN users u ON br.borrower_id = u.id
        WHERE b.owner_id = ? AND br.status IN ("pending", "alternative_suggested")
    ''', (current_user.id,)).fetchall()

    # Get alternative suggestions waiting for borrower response
    pending_alternatives = conn.execute('''
        SELECT br.*, b.title as book_title
        FROM borrow_requests br
        JOIN books b ON br.book_id = b.id
        WHERE br.borrower_id = ? AND br.status = "alternative_suggested"
''', (current_user.id,)).fetchall()

    conn.close()
    return render_template('dashboard.html',
                       my_books=my_books,
                       borrowed_books=borrowed_books,
                       incoming_requests=incoming_requests,
                       pending_alternatives=pending_alternatives)


# Accept a borrow request
@app.route('/accept_request/<int:request_id>')
@login_required
def accept_request(request_id):

    conn = get_db_connection()

    borrow_req = conn.execute('SELECT * FROM borrow_requests WHERE id = ?',
                              (request_id,)).fetchone()

    if borrow_req is None:
        flash('Request not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    book = conn.execute('SELECT * FROM books WHERE id = ?',
                        (borrow_req['book_id'],)).fetchone()

    # Owner accepts pending request OR borrower accepts alternative suggestion
    if book['owner_id'] != current_user.id and borrow_req['borrower_id'] != current_user.id:
        flash('You are not authorized to do this!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Mark request as accepted
    conn.execute('UPDATE borrow_requests SET status = "accepted" WHERE id = ?',
                 (request_id,))

    # Mark book as borrowed
    conn.execute('UPDATE books SET status = "borrowed" WHERE id = ?',
                 (borrow_req['book_id'],))

    # Create transaction record
    conn.execute('''
        INSERT INTO borrow_transactions (book_id, borrower_id, owner_id, request_id, status)
        VALUES (?, ?, ?, ?, "borrowed")
    ''', (borrow_req['book_id'], borrow_req['borrower_id'], book['owner_id'], request_id))

    conn.commit()
    conn.close()

    flash('Request accepted! Book is now marked as borrowed.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():

    conn = get_db_connection()

    if request.method == 'POST':

        username     = request.form['username']
        email        = request.form['email']
        new_password = request.form['new_password']

        if new_password:
            hashed_password = generate_password_hash(new_password)
            conn.execute('''
                UPDATE users SET username = ?, email = ?, password = ?
                WHERE id = ?
            ''', (username, email, hashed_password, current_user.id))
        else:
            conn.execute('''
                UPDATE users SET username = ?, email = ?
                WHERE id = ?
            ''', (username, email, current_user.id))

        conn.commit()
        conn.close()

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))

    # GET request — fetch current user data to pre-fill the form
    user = conn.execute('SELECT * FROM users WHERE id = ?',
                        (current_user.id,)).fetchone()
    conn.close()
    return render_template('profile.html', user=user)

# Owner accepts a borrow request
    @app.route('/accept_request/<int:request_id>')
    @login_required
    def accept_request(request_id):

      conn = get_db_connection()

    # Get the request details
    borrow_req = conn.execute('SELECT * FROM borrow_requests WHERE id = ?',
                              (request_id,)).fetchone()

    if borrow_req is None:
        flash('Request not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Security check — make sure current user owns the book
    book = conn.execute('SELECT * FROM books WHERE id = ?',
                        (borrow_req['book_id'],)).fetchone()

    if book['owner_id'] != current_user.id:
        flash('You are not authorized to do this!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Mark the request as accepted
    conn.execute('UPDATE borrow_requests SET status = "accepted" WHERE id = ?',
                 (request_id,))

    # Mark the book as borrowed so it disappears from home page
    conn.execute('UPDATE books SET status = "borrowed" WHERE id = ?',
                 (borrow_req['book_id'],))

    # Create a transaction record for tracking
    conn.execute('''
        INSERT INTO borrow_transactions (book_id, borrower_id, owner_id, request_id, status)
        VALUES (?, ?, ?, ?, "borrowed")
    ''', (borrow_req['book_id'], borrow_req['borrower_id'], current_user.id, request_id))

    conn.commit()
    conn.close()

    flash('Request accepted! Book is now marked as borrowed.', 'success')
    return redirect(url_for('dashboard'))


# Owner rejects a borrow request
@app.route('/reject_request/<int:request_id>')
@login_required
def reject_request(request_id):

    conn = get_db_connection()

    borrow_req = conn.execute('SELECT * FROM borrow_requests WHERE id = ?',
                              (request_id,)).fetchone()

    if borrow_req is None:
        flash('Request not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Security check
    book = conn.execute('SELECT * FROM books WHERE id = ?',
                        (borrow_req['book_id'],)).fetchone()

    if book['owner_id'] != current_user.id:
        flash('You are not authorized to do this!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Simply mark request as rejected — book stays available
    conn.execute('UPDATE borrow_requests SET status = "rejected" WHERE id = ?',
                 (request_id,))

    conn.commit()
    conn.close()

    flash('Request rejected.', 'info')
    return redirect(url_for('dashboard'))

# Owner suggests alternative date/time/location
@app.route('/suggest_alternative/<int:request_id>', methods=['GET', 'POST'])
@login_required
def suggest_alternative(request_id):

    conn = get_db_connection()

    # Get the request
    borrow_req = conn.execute('SELECT * FROM borrow_requests WHERE id = ?',
                              (request_id,)).fetchone()

    if borrow_req is None:
        flash('Request not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Security check — only book owner can suggest alternative
    book = conn.execute('SELECT * FROM books WHERE id = ?',
                        (borrow_req['book_id'],)).fetchone()

    if book['owner_id'] != current_user.id:
        flash('You are not authorized to do this!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    if request.method == 'POST':

        new_date     = request.form['proposed_date']
        new_time     = request.form['proposed_time']
        new_location = request.form['proposed_location']

        # Update the request with new suggested details
        # and mark status as "alternative_suggested" so borrower knows
        conn.execute('''
            UPDATE borrow_requests
            SET proposed_date = ?, proposed_time = ?, proposed_location = ?,
                status = "alternative_suggested"
            WHERE id = ?
        ''', (new_date, new_time, new_location, request_id))

        conn.commit()
        conn.close()

        flash('Alternative suggested! Waiting for borrower to respond.', 'success')
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template('suggest_alternative.html', req=borrow_req, book=book)


# Mark a physical book as returned - only owner can do this
@app.route('/mark_returned/<int:book_id>')
@login_required
def mark_returned(book_id):

    conn = get_db_connection()

    # Security check — make sure current user owns this book
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    if book['owner_id'] != current_user.id:
        flash('You are not authorized to do this!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Mark book as available again
    conn.execute('UPDATE books SET status = "available" WHERE id = ?', (book_id,))

    # Mark the transaction as returned
    conn.execute('''
        UPDATE borrow_transactions SET status = "returned"
        WHERE book_id = ? AND status = "borrowed"
    ''', (book_id,))

    conn.commit()
    conn.close()

    flash('Book marked as returned and is available again!', 'success')
    return redirect(url_for('dashboard'))


# Mark digital book as returned - only borrower can do this
@app.route('/return_digital/<int:book_id>')
@login_required
def return_digital(book_id):

    conn = get_db_connection()

    # Check the transaction belongs to current user
    transaction = conn.execute('''
        SELECT * FROM borrow_transactions
        WHERE book_id = ? AND borrower_id = ? AND status = "borrowed"
    ''', (book_id, current_user.id)).fetchone()

    if transaction is None:
        flash('No active borrow found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Mark book as available again
    conn.execute('UPDATE books SET status = "available" WHERE id = ?', (book_id,))

    # Mark transaction as returned
    conn.execute('''
        UPDATE borrow_transactions SET status = "returned"
        WHERE book_id = ? AND borrower_id = ? AND status = "borrowed"
    ''', (book_id, current_user.id))

    conn.commit()
    conn.close()

    flash('Digital book marked as returned!', 'success')
    return redirect(url_for('dashboard'))


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
    
    # Prevent owner from borrowing their own book
    if book['owner_id'] == current_user.id:
       flash('You cannot borrow your own book!', 'danger')
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