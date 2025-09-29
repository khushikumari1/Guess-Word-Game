from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import sqlite3
import random
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

DATABASE = 'guess_the_word.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # Create tables
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'player',
            date_registered TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS guesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            guess TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (word_id) REFERENCES words (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        user = conn.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        
        if not user or user['role'] != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('play'))
        return f(*args, **kwargs)
    return decorated_function

def validate_username(username):
    if len(username) < 5:
        return False, "Username must be at least 5 characters long"
    
    has_upper = any(c.isupper() for c in username)
    has_lower = any(c.islower() for c in username)
    
    if not (has_upper and has_lower):
        return False, "Username must contain both uppercase and lowercase letters"
    
    return True, "Valid"

def validate_password(password):
    if len(password) < 5:
        return False, "Password must be at least 5 characters long"
    
    has_alpha = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '$%*@' for c in password)
    
    if not (has_alpha and has_digit and has_special):
        return False, "Password must contain letters, numbers, and one of: $, %, *, @"
    
    return True, "Valid"

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('play'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Validate username
        is_valid_username, username_msg = validate_username(username)
        if not is_valid_username:
            flash(username_msg, 'error')
            return render_template('register.html')
        
        # Validate password
        is_valid_password, password_msg = validate_password(password)
        if not is_valid_password:
            flash(password_msg, 'error')
            return render_template('register.html')
        
        # Check if username already exists
        conn = get_db_connection()
        existing_user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'error')
            conn.close()
            return render_template('register.html')
        
        # Create new user
        password_hash = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', 
                    (username, password_hash))
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT id, username, password_hash, role FROM users WHERE username = ?', 
                           (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            return redirect(url_for('play'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/play')
@login_required
def play():
    # Check daily word limit
    today = date.today()
    conn = get_db_connection()
    
    # Count words played today
    words_played_today = conn.execute('''
        SELECT COUNT(DISTINCT word_id) as count 
        FROM guesses 
        WHERE user_id = ? AND DATE(date) = ?
    ''', (session['user_id'], today)).fetchone()['count']
    
    if words_played_today >= 3:
        flash('You have reached your daily limit of 3 words. Come back tomorrow!', 'info')
        conn.close()
        return render_template('play.html', game_over=True, daily_limit_reached=True)
    
    # Get current game state
    current_word_id = session.get('current_word_id')
    current_attempts = session.get('current_attempts', 0)
    game_won = session.get('game_won', False)
    game_lost = session.get('game_lost', False)
    
    # Get previous guesses for current word
    previous_guesses = []
    if current_word_id:
        guesses = conn.execute('''
            SELECT guess, attempt_number FROM guesses 
            WHERE user_id = ? AND word_id = ? 
            ORDER BY attempt_number
        ''', (session['user_id'], current_word_id)).fetchall()
        
        for guess in guesses:
            # Get the target word to compare
            target_word = conn.execute('SELECT word FROM words WHERE id = ?', 
                                     (current_word_id,)).fetchone()['word']
            feedback = get_guess_feedback(guess['guess'], target_word)
            previous_guesses.append({
                'guess': guess['guess'],
                'attempt': guess['attempt_number'],
                'feedback': feedback
            })
    
    conn.close()
    
    return render_template('play.html', 
                         previous_guesses=previous_guesses,
                         current_attempts=current_attempts,
                         current_word_id=current_word_id,
                         game_won=game_won,
                         game_lost=game_lost,
                         daily_limit_reached=False)

@app.route('/start_new_game')
@login_required
def start_new_game():
    # Reset game state
    session.pop('current_word_id', None)
    session.pop('current_attempts', None)
    session.pop('game_won', None)
    session.pop('game_lost', None)
    
    # Get a random word
    conn = get_db_connection()
    words = conn.execute('SELECT id, word FROM words').fetchall()
    conn.close()
    
    if not words:
        flash('No words available. Please contact admin.', 'error')
        return redirect(url_for('play'))
    
    random_word = random.choice(words)
    session['current_word_id'] = random_word['id']
    session['current_attempts'] = 0
    session['game_won'] = False
    session['game_lost'] = False
    
    return redirect(url_for('play'))

@app.route('/guess', methods=['POST'])
@login_required
def make_guess():
    guess = request.form['guess'].upper().strip()
    
    # Validate guess
    if len(guess) != 5 or not guess.isalpha():
        flash('Please enter a valid 5-letter word.', 'error')
        return redirect(url_for('play'))
    
    current_word_id = session.get('current_word_id')
    if not current_word_id:
        flash('Please start a new game first.', 'error')
        return redirect(url_for('play'))
    
    current_attempts = session.get('current_attempts', 0)
    if current_attempts >= 5:
        flash('Maximum attempts reached.', 'error')
        return redirect(url_for('play'))
    
    # Get target word
    conn = get_db_connection()
    target_word = conn.execute('SELECT word FROM words WHERE id = ?', 
                              (current_word_id,)).fetchone()['word']
    
    # Save guess
    current_attempts += 1
    conn.execute('''
        INSERT INTO guesses (user_id, word_id, guess, attempt_number) 
        VALUES (?, ?, ?, ?)
    ''', (session['user_id'], current_word_id, guess, current_attempts))
    conn.commit()
    conn.close()
    
    session['current_attempts'] = current_attempts
    
    # Check if won
    if guess == target_word:
        session['game_won'] = True
        flash('Congratulations! You guessed the word correctly!', 'success')
    elif current_attempts >= 5:
        session['game_lost'] = True
        flash(f'Better luck next time! The word was: {target_word}', 'info')
    
    return redirect(url_for('play'))

def get_guess_feedback(guess, target_word):
    feedback = []
    target_letters = list(target_word)
    guess_letters = list(guess)
    
    # First pass: mark exact matches (green)
    for i in range(5):
        if guess_letters[i] == target_letters[i]:
            feedback.append('green')
            target_letters[i] = None  # Mark as used
            guess_letters[i] = None
        else:
            feedback.append(None)
    
    # Second pass: mark partial matches (orange)
    for i in range(5):
        if feedback[i] is None and guess_letters[i] is not None:
            if guess_letters[i] in target_letters:
                feedback[i] = 'orange'
                # Remove the matched letter from target
                target_letters[target_letters.index(guess_letters[i])] = None
            else:
                feedback[i] = 'grey'
    
    return feedback

@app.route('/admin/reports')
@admin_required
def admin_reports():
    return render_template('admin_reports.html')

@app.route('/api/daily_report')
@admin_required
def daily_report():
    conn = get_db_connection()
    
    # Get today's stats
    today = date.today()
    
    # Number of users who played today
    users_played = conn.execute('''
        SELECT COUNT(DISTINCT user_id) as count 
        FROM guesses 
        WHERE DATE(date) = ?
    ''', (today,)).fetchone()['count']
    
    # Number of words tried today
    words_tried = conn.execute('''
        SELECT COUNT(DISTINCT word_id) as count 
        FROM guesses 
        WHERE DATE(date) = ?
    ''', (today,)).fetchone()['count']
    
    # Number of correct guesses today
    correct_guesses = conn.execute('''
        SELECT COUNT(*) as count 
        FROM guesses g
        JOIN words w ON g.word_id = w.id
        WHERE g.guess = w.word AND DATE(g.date) = ?
    ''', (today,)).fetchone()['count']
    
    conn.close()
    
    return jsonify({
        'date': today.strftime('%Y-%m-%d'),
        'users_played': users_played,
        'words_tried': words_tried,
        'correct_guesses': correct_guesses
    })

@app.route('/api/user_report')
@admin_required
def user_report():
    conn = get_db_connection()
    
    # Get all users with their stats
    users = conn.execute('''
        SELECT u.id, u.username, u.date_registered,
               COUNT(DISTINCT g.word_id) as words_tried,
               COUNT(CASE WHEN g.guess = w.word THEN 1 END) as correct_guesses
        FROM users u
        LEFT JOIN guesses g ON u.id = g.user_id
        LEFT JOIN words w ON g.word_id = w.id
        WHERE u.role = 'player'
        GROUP BY u.id, u.username, u.date_registered
        ORDER BY u.date_registered DESC
    ''').fetchall()
    
    conn.close()
    
    user_data = []
    for user in users:
        user_data.append({
            'id': user['id'],
            'username': user['username'],
            'date_registered': user['date_registered'],
            'words_tried': user['words_tried'],
            'correct_guesses': user['correct_guesses']
        })
    
    return jsonify(user_data)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
