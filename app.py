from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os

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


# ─── AUTO RETURN DIGITAL BOOKS ───────────────────────────────────────────────
# Helper function - not a route
# Runs every time dashboard loads
def auto_return_digital_books():
    conn = get_db_connection()
    conn.execute('''
        UPDATE borrow_transactions
        SET status = "returned"
        WHERE status = "borrowed"
        AND borrow_date IS NOT NULL
        AND julianday("now") - julianday(borrow_date) > 14
        AND book_id IN (
            SELECT id FROM books
            WHERE type IN ("digital", "Digital")
        )
    ''')
    conn.commit()
    conn.close()


# ─── HOME PAGE ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    q = request.args.get('q', '')
    conn = get_db_connection()

    if q:
        search = '%' + q + '%'
        books = conn.execute('''
            SELECT b.*, u.username as owner_name
            FROM books b
            JOIN users u ON b.owner_id = u.id
            WHERE b.status = "available"
            AND (b.title LIKE ? OR b.author LIKE ? OR b.category LIKE ?)
        ''', (search, search, search)).fetchall()
    else:
        books = conn.execute('''
            SELECT b.*, u.username as owner_name
            FROM books b
            JOIN users u ON b.owner_id = u.id
            WHERE b.status = "available"
        ''').fetchall()

    conn.close()
    return render_template('index.html', books=books, q=q)


# ─── REGISTER ────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email    = request.form['email']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                         (username, email, hashed_password))
            conn.commit()

            new_user = conn.execute('SELECT * FROM users WHERE email = ?',
                                    (email,)).fetchone()
            conn.close()

            user_obj = User(new_user['id'], new_user['username'], new_user['email'], new_user['role'])
            login_user(user_obj)

            flash('Registration successful! Welcome to Book Sharing Platform.', 'success')
            return redirect(url_for('dashboard'))

        except sqlite3.IntegrityError:
            flash('Username or email already exists!', 'danger')
            conn.close()

    return render_template('register.html')


# ─── LOGIN ────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):

            if user['is_blocked'] == 1:
                flash('Your account has been blocked. Contact admin.', 'danger')
                return redirect(url_for('login'))

            user_obj = User(user['id'], user['username'], user['email'], user['role'])
            login_user(user_obj)
            flash('Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('dashboard'))
        else:
            flash('Invalid email or password!', 'danger')

    return render_template('login.html')


# ─── LOGOUT ──────────────────────────────────────────────────────────────────

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ─── DASHBOARD ───────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():

    auto_return_digital_books()

    conn = get_db_connection()

    my_books = conn.execute('''
        SELECT b.*,
               br.proposed_date, br.proposed_time, br.proposed_location,
               u.username as borrower_name
        FROM books b
        LEFT JOIN borrow_requests br ON br.book_id = b.id AND br.status = "accepted"
        LEFT JOIN users u ON br.borrower_id = u.id
        WHERE b.owner_id = ?
    ''', (current_user.id,)).fetchall()

    borrowed_books = conn.execute('''
        SELECT b.*, u.username as owner_name,
               br.proposed_date, br.proposed_time, br.proposed_location
        FROM borrow_transactions bt
        JOIN books b ON bt.book_id = b.id
        JOIN users u ON b.owner_id = u.id
        JOIN borrow_requests br ON bt.request_id = br.id
        WHERE bt.borrower_id = ? AND bt.status = "borrowed"
    ''', (current_user.id,)).fetchall()

    incoming_requests = conn.execute('''
        SELECT br.*, b.title as book_title, b.author as book_author,
               u.username as borrower_name
        FROM borrow_requests br
        JOIN books b ON br.book_id = b.id
        JOIN users u ON br.borrower_id = u.id
        WHERE b.owner_id = ? AND br.status IN ("pending", "alternative_suggested")
    ''', (current_user.id,)).fetchall()

    pending_alternatives = conn.execute('''
        SELECT br.*, b.title as book_title
        FROM borrow_requests br
        JOIN books b ON br.book_id = b.id
        WHERE br.borrower_id = ? AND br.status = "alternative_suggested"
    ''', (current_user.id,)).fetchall()

    download_requests = conn.execute('''
        SELECT br.*, b.title as book_title, b.type as book_type,
               u.username as owner_name
        FROM borrow_requests br
        JOIN books b ON br.book_id = b.id
        JOIN users u ON b.owner_id = u.id
        WHERE br.borrower_id = ?
        AND b.type IN ("digital", "Digital")
        AND br.status IN ("pending", "accepted", "rejected")
        ORDER BY br.request_date DESC
    ''', (current_user.id,)).fetchall()

    conn.close()
    return render_template('dashboard.html',
                           my_books=my_books,
                           borrowed_books=borrowed_books,
                           incoming_requests=incoming_requests,
                           pending_alternatives=pending_alternatives,
                           download_requests=download_requests)


# ─── PROFILE ─────────────────────────────────────────────────────────────────

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

    user = conn.execute('SELECT * FROM users WHERE id = ?',
                        (current_user.id,)).fetchone()
    conn.close()
    return render_template('profile.html', user=user)


# ─── BORROW PAGE ─────────────────────────────────────────────────────────────

@app.route('/borrow/<int:book_id>', methods=['GET', 'POST'])
@login_required
def borrow(book_id):
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    if book is None:
        flash('Book not found!', 'danger')
        conn.close()
        return redirect(url_for('index'))

    if book['owner_id'] == current_user.id:
        flash('You cannot borrow your own book!', 'danger')
        conn.close()
        return redirect(url_for('index'))

    if request.method == 'POST':
        proposed_date     = request.form['borrowDate']
        proposed_time     = request.form['borrowTime']
        proposed_location = request.form['borrowLocation']
        notes             = request.form['notes']

        conn.execute('''
            INSERT INTO borrow_requests
            (book_id, borrower_id, proposed_date, proposed_time, proposed_location, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (book_id, current_user.id, proposed_date, proposed_time, proposed_location, 'pending'))

        conn.commit()
        conn.close()
        flash('Borrow request sent successfully! Wait for the owner to accept.', 'success')
        return redirect(url_for('index'))

    conn.close()
    return render_template('borrow.html', book=book)


# ─── DIGITAL BOOK REQUEST ────────────────────────────────────────────────────

@app.route('/digital_request/<int:book_id>')
@login_required
def digital_request(book_id):
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    if book is None:
        flash('Book not found!', 'danger')
        conn.close()
        return redirect(url_for('index'))

    if book['owner_id'] == current_user.id:
        flash('You cannot request your own book!', 'danger')
        conn.close()
        return redirect(url_for('index'))

    existing = conn.execute('''
        SELECT * FROM borrow_requests
        WHERE book_id = ? AND borrower_id = ? AND status IN ("pending", "accepted")
    ''', (book_id, current_user.id)).fetchone()

    if existing:
        flash('You already have an active request for this book!', 'info')
        conn.close()
        return redirect(url_for('index'))

    conn.execute('''
        INSERT INTO borrow_requests
        (book_id, borrower_id, proposed_date, proposed_time, proposed_location, status)
        VALUES (?, ?, "N/A", "N/A", "Digital Download", ?)
    ''', (book_id, current_user.id, 'pending'))

    conn.commit()
    conn.close()
    flash('Download request sent! Wait for the owner to accept.', 'success')
    return redirect(url_for('index'))


# ─── ACCEPT REQUEST ──────────────────────────────────────────────────────────

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

    # Owner accepts pending OR borrower accepts alternative suggestion
    if book['owner_id'] != current_user.id and borrow_req['borrower_id'] != current_user.id:
        flash('You are not authorized to do this!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    conn.execute('UPDATE borrow_requests SET status = "accepted" WHERE id = ?',
                 (request_id,))

    # Only physical books get marked as borrowed
    # Digital books stay available for multiple users
    if book['type'].lower() == 'physical':
        conn.execute('UPDATE books SET status = "borrowed" WHERE id = ?',
                     (borrow_req['book_id'],))

    conn.execute('''
        INSERT INTO borrow_transactions
        (book_id, borrower_id, owner_id, request_id, status, borrow_date)
        VALUES (?, ?, ?, ?, "borrowed", datetime("now"))
    ''', (borrow_req['book_id'], borrow_req['borrower_id'], book['owner_id'], request_id))

    conn.commit()
    conn.close()
    flash('Request accepted! Book is now marked as borrowed.', 'success')
    return redirect(url_for('dashboard'))


# ─── REJECT REQUEST ──────────────────────────────────────────────────────────

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

    book = conn.execute('SELECT * FROM books WHERE id = ?',
                        (borrow_req['book_id'],)).fetchone()

    # Owner rejects OR borrower rejects alternative
    if book['owner_id'] != current_user.id and borrow_req['borrower_id'] != current_user.id:
        flash('You are not authorized to do this!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    conn.execute('UPDATE borrow_requests SET status = "rejected" WHERE id = ?',
                 (request_id,))

    conn.commit()
    conn.close()
    flash('Request rejected.', 'info')
    return redirect(url_for('dashboard'))


# ─── SUGGEST ALTERNATIVE ─────────────────────────────────────────────────────

@app.route('/suggest_alternative/<int:request_id>', methods=['GET', 'POST'])
@login_required
def suggest_alternative(request_id):
    conn = get_db_connection()

    borrow_req = conn.execute('SELECT * FROM borrow_requests WHERE id = ?',
                              (request_id,)).fetchone()

    if borrow_req is None:
        flash('Request not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

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


# ─── MARK RETURNED (PHYSICAL) ────────────────────────────────────────────────

@app.route('/mark_returned/<int:book_id>')
@login_required
def mark_returned(book_id):
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    if book['owner_id'] != current_user.id:
        flash('You are not authorized to do this!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    conn.execute('UPDATE books SET status = "available" WHERE id = ?', (book_id,))
    conn.execute('''
        UPDATE borrow_transactions SET status = "returned"
        WHERE book_id = ? AND status = "borrowed"
    ''', (book_id,))

    conn.commit()
    conn.close()
    flash('Book marked as returned and is available again!', 'success')
    return redirect(url_for('dashboard'))


# ─── MARK RETURNED (DIGITAL) ─────────────────────────────────────────────────

@app.route('/return_digital/<int:book_id>')
@login_required
def return_digital(book_id):
    conn = get_db_connection()

    transaction = conn.execute('''
        SELECT * FROM borrow_transactions
        WHERE book_id = ? AND borrower_id = ? AND status = "borrowed"
    ''', (book_id, current_user.id)).fetchone()

    if transaction is None:
        flash('No active borrow found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    conn.execute('UPDATE books SET status = "available" WHERE id = ?', (book_id,))
    conn.execute('''
        UPDATE borrow_transactions SET status = "returned"
        WHERE book_id = ? AND borrower_id = ? AND status = "borrowed"
    ''', (book_id, current_user.id))

    conn.commit()
    conn.close()
    flash('Digital book marked as returned!', 'success')
    return redirect(url_for('dashboard'))


# ─── ADD BOOK ────────────────────────────────────────────────────────────────

@app.route('/add_book', methods=['GET', 'POST'])
@login_required
def add_book():

    if request.method == 'POST':
        title          = request.form['title']
        author         = request.form['author']
        category       = request.form['category']
        booktype       = request.form['type']
        location_notes = None
        file_path      = None

        if booktype == 'physical':
            location_notes = request.form['location_notes']

        if booktype == 'digital':
            pdf_file = request.files['pdf_file']

            if pdf_file and pdf_file.filename != '':
                if not pdf_file.filename.endswith('.pdf'):
                    flash('Only PDF files are allowed!', 'danger')
                    return redirect(url_for('add_book'))

                pdf_filename  = secure_filename(pdf_file.filename)
                upload_folder = os.path.join(app.root_path, 'static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                pdf_file.save(os.path.join(upload_folder, pdf_filename))
                file_path = 'uploads/' + pdf_filename
            else:
                file_path = request.form.get('download_link', '')

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO books (owner_id, title, author, category, type, location_notes, file_path, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (current_user.id, title, author, category, booktype, location_notes, file_path, 'available'))

        conn.commit()
        conn.close()
        flash('Your book has been listed successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_book.html')


# ─── DOWNLOAD DIGITAL BOOK ───────────────────────────────────────────────────

@app.route('/download/<int:book_id>')
@login_required
def download_book(book_id):
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    conn.close()

    if book is None:
        flash('Book not found!', 'danger')
        return redirect(url_for('index'))

    if book['file_path'] and book['file_path'].startswith('http'):
        return redirect(book['file_path'])

    if book['file_path'] and book['file_path'].startswith('uploads/'):
        return redirect(url_for('static', filename=book['file_path']))

    flash('No download available for this book!', 'danger')
    return redirect(url_for('index'))


# ─── DELETE BOOK ─────────────────────────────────────────────────────────────

@app.route('/delete_book/<int:book_id>')
@login_required
def delete_book(book_id):
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    if book is None:
        flash('Book not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    if book['owner_id'] != current_user.id:
        flash('You can only delete your own books!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    conn.execute('DELETE FROM books WHERE id = ?', (book_id,))
    conn.commit()
    conn.close()
    flash('Book deleted successfully!', 'success')
    return redirect(url_for('dashboard'))


# ─── EDIT BOOK ───────────────────────────────────────────────────────────────

@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

    if book is None:
        flash('Book not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    if book['owner_id'] != current_user.id:
        flash('You can only edit your own books!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title          = request.form['title']
        author         = request.form['author']
        category       = request.form['category']
        location_notes = request.form.get('location_notes', '')
        download_link  = request.form.get('download_link', '')

       # If digital book — make sure download link is not empty
        if book['type'].lower() == 'digital' and not download_link.strip():
            flash('Digital books must have a download link!', 'danger')
            conn.close()
            return redirect(url_for('edit_book', book_id=book_id))

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
    return render_template('edit_book.html', book=book)


# ─── ADMIN DASHBOARD ─────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
def admin_dashboard():

    if current_user.role != 'admin':
        flash('You are not authorized to access this page!', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()

    all_books = conn.execute('''
        SELECT b.*, u.username as owner_name
        FROM books b
        JOIN users u ON b.owner_id = u.id
        ORDER BY b.added_date DESC
    ''').fetchall()

    all_users = conn.execute('''
        SELECT * FROM users
        WHERE role != "admin"
        ORDER BY created_at DESC
    ''').fetchall()

    conn.close()
    return render_template('admin.html',
                           all_books=all_books,
                           all_users=all_users)


# ─── ADMIN DELETE BOOK ────────────────────────────────────────────────────────

@app.route('/admin/delete_book/<int:book_id>')
@login_required
def admin_delete_book(book_id):

    if current_user.role != 'admin':
        flash('Not authorized!', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    conn.execute('DELETE FROM books WHERE id = ?', (book_id,))
    conn.commit()
    conn.close()
    flash('Book deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))


# ─── ADMIN BLOCK USER ─────────────────────────────────────────────────────────

@app.route('/admin/block_user/<int:user_id>')
@login_required
def block_user(user_id):

    if current_user.role != 'admin':
        flash('Not authorized!', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    if user['is_blocked'] == 0:
        conn.execute('UPDATE users SET is_blocked = 1 WHERE id = ?', (user_id,))
        flash(f'{user["username"]} has been blocked!', 'success')
    else:
        conn.execute('UPDATE users SET is_blocked = 0 WHERE id = ?', (user_id,))
        flash(f'{user["username"]} has been unblocked!', 'success')

    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))


# ─── RUN ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)