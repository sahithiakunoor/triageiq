import os, httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

PRI_COLOR  = {"P1":"#e05252","P2":"#d4845a","P3":"#c9a84c","P4":"#5a9e7a","P5":"#7090a0"}
CAT_COLOR  = {"Bug":"#e05252","New Feature":"#5a7fd4","Improvement":"#5aaab4",
              "Task":"#5a9e7a","Test":"#9a6ab4","Sub-task":"#7090a0"}
PRI_LABEL  = {"P1":"Blocker","P2":"Critical","P3":"Major","P4":"Minor","P5":"Trivial"}
STA_COLOR  = {"pending":"#c9a84c","approved":"#5a9e7a","rejected":"#e05252","edited":"#5a7fd4"}

def styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&family=IBM+Plex+Serif:wght@400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif !important;
    }

    .stApp { background: #0f1117 !important; color: #cdd0d8; }

    section[data-testid="stSidebar"] {
        background: #090c12 !important;
        border-right: 1px solid #1e2330 !important;
    }

    .stButton > button {
        background: transparent !important;
        color: #9aa0b0 !important;
        border: 1px solid #252b3a !important;
        border-radius: 4px !important;
        font-family: 'IBM Plex Sans', sans-serif !important;
        font-size: .85rem !important;
        padding: .4rem .9rem !important;
        transition: all .15s !important;
    }
    .stButton > button:hover {
        border-color: #3d4a6a !important;
        color: #cdd0d8 !important;
        background: #141824 !important;
    }
    .stButton > button[kind="primary"] {
        background: #2a3f8a !important;
        color: #c8d4f8 !important;
        border-color: #2a3f8a !important;
        font-weight: 500 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #3350a8 !important;
        border-color: #3350a8 !important;
    }

    .card {
        background: #13171f;
        border: 1px solid #1e2330;
        border-radius: 6px;
        padding: 1.2rem 1.4rem;
        margin-bottom: .9rem;
    }

    .mono { font-family: 'IBM Plex Mono', monospace; }
    .muted { color: #5a6070; }
    .label {
        font-family: 'IBM Plex Mono', monospace;
        font-size: .68rem;
        text-transform: uppercase;
        letter-spacing: .08em;
        color: #4a5060;
        margin-bottom: .35rem;
    }
    .badge {
        display: inline-block;
        padding: .15rem .55rem;
        border-radius: 3px;
        font-family: 'IBM Plex Mono', monospace;
        font-size: .7rem;
    }
    .draft-box {
        background: #0c0f16;
        border-left: 2px solid #2a3f8a;
        padding: 1rem 1.2rem;
        white-space: pre-wrap;
        font-size: .88rem;
        line-height: 1.8;
        color: #9aa0b0;
        font-family: 'IBM Plex Sans', sans-serif;
        border-radius: 0 4px 4px 0;
    }
    .bar-wrap {
        background: #1e2330;
        border-radius: 2px;
        height: 3px;
        overflow: hidden;
        margin: .35rem 0;
    }
    .bar { height: 100%; border-radius: 2px; }
    .kb-chip {
        display: inline-block;
        background: #111620;
        border: 1px solid #1e2a3a;
        border-radius: 3px;
        padding: .15rem .5rem;
        font-size: .7rem;
        color: #5a8aaa;
        font-family: 'IBM Plex Mono', monospace;
        margin: .1rem;
    }
    .ent-chip {
        display: inline-block;
        background: #140f1e;
        border: 1px solid #2a1e3a;
        border-radius: 3px;
        padding: .15rem .5rem;
        font-size: .7rem;
        color: #8a6aaa;
        font-family: 'IBM Plex Mono', monospace;
        margin: .1rem;
    }

    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        background: #0c0f16 !important;
        border: 1px solid #1e2330 !important;
        border-radius: 4px !important;
        color: #cdd0d8 !important;
        font-family: 'IBM Plex Sans', sans-serif !important;
        font-size: .9rem !important;
        caret-color: #4a6ad8 !important;
    }
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder {
        color: #3a4050 !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #2a3f8a !important;
        box-shadow: none !important;
    }

    div[data-testid="stMetricValue"] {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 1.6rem !important;
        color: #cdd0d8 !important;
    }
    div[data-testid="stMetricLabel"] {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: .7rem !important;
        text-transform: uppercase !important;
        letter-spacing: .06em !important;
        color: #4a5060 !important;
    }

    .stSelectbox > div > div {
        background: #0c0f16 !important;
        border: 1px solid #1e2330 !important;
        border-radius: 4px !important;
        color: #cdd0d8 !important;
    }

    [data-testid="stFileUploader"] {
        background: #0c0f16 !important;
        border: 1px dashed #1e2330 !important;
        border-radius: 6px !important;
    }

    ::-webkit-scrollbar { width: 3px; }
    ::-webkit-scrollbar-track { background: #0f1117; }
    ::-webkit-scrollbar-thumb { background: #252b3a; border-radius: 2px; }
    </style>""", unsafe_allow_html=True)


def badge(text, color):
    bg = color + "18"
    return f'<span class="badge" style="background:{bg};color:{color};border:1px solid {color}30">{text}</span>'

def api_upload(endpoint, file, data=None):
    """Upload a file to the backend via multipart form."""
    try:
        files = {"file": (file.name, file.getvalue(), "text/csv")}
        r = httpx.post(f"{BACKEND_URL}{endpoint}", files=files,
                       data=data or {}, timeout=600)
        if r.status_code == 400:
            return r.json()
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Upload error: {e}")
        return None

def api_post(endpoint, payload):
    try:
        r = httpx.post(f"{BACKEND_URL}{endpoint}", json=payload, timeout=120)

        if r.status_code >= 400:
            try:
                return r.json()
            except Exception:
                return {"detail": r.text}

        return r.json()

    except Exception as e:
        st.error(f"API error: {e}")
        return None

def api_get(endpoint, params=None):
    try:
        r = httpx.get(f"{BACKEND_URL}{endpoint}", params=params or {}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None
    

def api_upload(endpoint, uploaded_file, data=None):
    try:
        files = {
            "file": (
                uploaded_file.name,
                uploaded_file.getvalue(),
                "text/csv",
            )
        }
        r = httpx.post(
            f"{BACKEND_URL}{endpoint}",
            files=files,
            data=data or {},
            timeout=600,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API upload error: {e}")
        return None