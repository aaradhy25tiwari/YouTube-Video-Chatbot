from youtube_transcript_api import YouTubeTranscriptApi
import urllib.parse as urlparse
from google import genai
import streamlit as st

# --- Layout and Sidebar ---
st.set_page_config(page_title="Video Whisperer", page_icon="🎥")
st.title("🎥 Chat with YouTube Videos")

with st.sidebar:
    api_key = st.text_input("Enter Gemini API Key", type="password")
    video_url = st.text_input("YouTube URL")
    process_button = st.button("Process Video")

# --- Initialize Client ---
if api_key:
    client = genai.Client(api_key=api_key)

# --- Helper Function ---
def get_video_id(url):
    """Extracts the video ID from various YouTube URL formats."""
    parsed_url = urlparse.urlparse(url)
    if parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            p = urlparse.parse_qs(parsed_url.query)
            return p.get('v', [None])[0]
    return url 

# --- 1. Processing Logic ---
if process_button and video_url:
    if not api_key:
        st.error("Please enter a Gemini API Key first")
    else:
        with st.spinner("Transcribing and summarizing..."):
            video_id = get_video_id(video_url)
            api = YouTubeTranscriptApi()
            transcript = api.fetch(video_id, languages=['en', 'hi'])
            full_text = " ".join([t.text for t in transcript])

            # Summarize
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
            model="gemini-2.5-flash-lite", 
            contents=f"Summarize this video transcript: {full_text}"
        )

        # Store in session state so it persists during chat
        st.session_state.transcript = full_text
        st.session_state.summary = response.text
        st.session_state.messages = [] # Reset chat for new video

# --- 2. Display Summary ---
if "summary" in st.session_state:
    st.subheader("Video Summary")
    st.write(st.session_state.summary)
    st.divider()

# --- 3. Chat Interface ---
if "transcript" in st.session_state:
    st.subheader("Ask a Question")

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("What was the main point of the second half?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response using transcript context
        full_prompt = f"Using this transcript: {st.session_state.transcript}. Answer this: {prompt}"
        response = client.models.generate_content(model="gemini-2.5-flash-lite", contents=full_prompt)

        with st.chat_message("assistant"):
            st.markdown(response.text)
        st.session_state.messages.append({"role": "assistant", "content": response.text})
