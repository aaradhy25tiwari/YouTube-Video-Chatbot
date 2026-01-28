import os
import sqlite3
import hashlib
import urllib.parse as urlparse
from datetime import datetime
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from dotenv import load_dotenv

# --- 1. Setup & Config ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

st.set_page_config(page_title="Video Whisperer", page_icon="🎥")

# --- 2. Database Functions (SQLite) ---
def init_db():
    conn = sqlite3.connect('app_data.db')
    c = conn.cursor()
    # Updated: Added 'email' column to users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, email TEXT)''')

    # History Table (unchanged)
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT, 
                  video_url TEXT, 
                  summary TEXT, 
                  transcript TEXT, 
                  timestamp DATETIME)''')
    conn.commit()
    conn.close()

def make_hashes(pwd):
    return hashlib.sha256(str.encode(pwd)).hexdigest()

def check_hashes(pwd, hashed_text):
    if make_hashes(pwd) == hashed_text:
        return True
    return False

# Updated: Accepts email
def add_user(user, pwd, email):
    conn = sqlite3.connect('app_data.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users(username, password, email) VALUES (?,?,?)', 
                  (user, make_hashes(pwd), email))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # Username exists
    finally:
        conn.close()

def login_user(user, pwd):
    conn = sqlite3.connect('app_data.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (user,))
    user_data = c.fetchall()
    conn.close()
    if user_data:
        if check_hashes(pwd, user_data[0][1]):
            return True
    return False

def save_history(user, url, summary, transcript):
    conn = sqlite3.connect('app_data.db')
    c = conn.cursor()
    c.execute('INSERT INTO history(username, video_url, summary, transcript, timestamp) VALUES (?,?,?,?,?)', (user, url, summary, transcript, datetime.now()))
    conn.commit()
    conn.close()

def get_user_history(user):
    conn = sqlite3.connect('app_data.db')
    c = conn.cursor()
    c.execute('SELECT video_url, summary, transcript, timestamp, id FROM history WHERE username = ? ORDER BY id DESC', (user,))
    data = c.fetchall()
    conn.close()
    return data

# Initialize DB on start
init_db()

# --- 3. Helper Functions ---
def get_video_id(url):
    parsed_url = urlparse.urlparse(url)
    if parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            p = urlparse.parse_qs(parsed_url.query)
            return p.get('v', [None])[0]
    return url

# --- 4. Authentication Logic ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🎥 Video Whisperer - Login")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        username = st.text_input("Username")
        password = st.text_input("Password", type='password')
        if st.button("Login"):
            if login_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Logged In")
                st.rerun()
            else:
                st.error("Incorrect Username or Password")

    with tab2:
        st.subheader("Create New Account")
        new_user = st.text_input("New Username")
        new_email = st.text_input("Email Address") # Added Field
        new_pass = st.text_input("New Password", type='password')
        conf_pass = st.text_input("Confirm Password", type='password') # Added Field

        if st.button("Sign Up"):
            if new_pass != conf_pass:
                st.error("Passwords do not match!")
            elif not new_user or not new_pass or not new_email:
                st.warning("Please fill in all fields.")
            else:
                if add_user(new_user, new_pass, new_email):
                    st.success("Account Created! Please go to Login tab.")
                else:
                    st.warning("Username already exists.")

    st.stop() # Stop here if not logged in

# --- 5. Main Application Logic (Only runs if logged in) ---
st.sidebar.title(f"Welcome, {st.session_state.username}")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

# Security Check
if not api_key:
    st.error("⚠️ GEMINI_API_KEY not found in environment variables.")
    st.stop()

client = genai.Client(api_key=api_key)

# Sidebar - History Selection
st.sidebar.divider()
st.sidebar.subheader("📜 History")
history_data = get_user_history(st.session_state.username)

# Create a dictionary to map labels to data for the selectbox
history_options = {f"{row[0]} ({row[3]})": row for row in history_data}

selected_history = st.sidebar.selectbox(
    "Load past video", 
    options=["Select a video..."] + list(history_options.keys())
)

# Load history if selected
if selected_history != "Select a video..." and "history_loaded" not in st.session_state:
    data = history_options[selected_history]
    st.session_state.transcript = data[2]
    st.session_state.summary = data[1]
    st.session_state.messages = [] # Start fresh chat on old history
    st.session_state.history_loaded = True # Prevent constant reloading
    st.success(f"Loaded history for: {data[0]}")

# Sidebar - New Video Input
st.sidebar.divider()
st.sidebar.subheader("➕ New Video")
video_url = st.sidebar.text_input("YouTube URL")
process_button = st.sidebar.button("Process Video")

st.title("🎥 Chat with YouTube Videos")

# Process Logic
if process_button and video_url:
    with st.spinner("Transcribing and summarizing..."):
        try:
            video_id = get_video_id(video_url)
            api = YouTubeTranscriptApi()
            transcript_obj = api.fetch(video_id, languages=['en', 'hi'])
            full_text = " ".join([t.text for t in transcript_obj])

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite", 
                contents=f"Summarize this video transcript: {full_text}"
            )

            # Update Session State
            st.session_state.transcript = full_text
            st.session_state.summary = response.text
            st.session_state.messages = []

            # Save to Database History
            save_history(st.session_state.username, video_url, response.text, full_text)
            st.toast("Saved to history!")

        except Exception as e:
            st.error(f"An error occurred: {e}")

# Display Summary
if "summary" in st.session_state:
    st.subheader("Video Summary")
    st.write(st.session_state.summary)
    st.divider()

# Chat Interface
if "transcript" in st.session_state:
    st.subheader("Ask a Question")

    # Initialize messages if not present
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask something about the video"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        full_prompt = f"Using this transcript: {st.session_state.transcript}. Answer this: {prompt}"

        try:
            response = client.models.generate_content(model="gemini-2.5-flash-lite", contents=full_prompt)
            with st.chat_message("assistant"):
                st.markdown(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})
        except (ValueError, RuntimeError) as e:
            st.error(f"Error generating response: {e}")
