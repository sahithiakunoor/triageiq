import streamlit as st

st.set_page_config(
    page_title="TriageIQ",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from utils import styles

styles()

PAGES = ["New Issue", "Inbox", "Issue Detail", "Analytics", "Train Models"]

# Initialise sidebar navigation
if "page_choice" not in st.session_state:
    st.session_state["page_choice"] = "New Issue"

# Handle redirects BEFORE sidebar radio renders
if st.session_state.pop("nav_to_inbox", False):
    st.session_state["page_choice"] = "Inbox"

if st.session_state.pop("nav_to_detail", False):
    st.session_state["page_choice"] = "Issue Detail"

if st.session_state.pop("go_to_issue_detail", False):
    st.session_state["page_choice"] = "Issue Detail"

# Fetch pending count for sidebar badge
try:
    import httpx as _hx
    _r = _hx.get(
        f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/analytics",
        timeout=2
    )
    _pending = _r.json().get("by_status", {}).get("pending", 0) if _r.status_code == 200 else 0
except Exception:
    _pending = 0

_inbox_label = f"Inbox  🔴 {_pending}" if _pending > 0 else "Inbox"

with st.sidebar:
    st.markdown("""
    <div style="padding:.6rem 0 1.8rem">
      <div style="font-family:'IBM Plex Serif',serif;font-weight:600;font-size:1.35rem;
                  color:#cdd0d8;letter-spacing:-.01em">
        Triage<span style="color:#4a6ad8">IQ</span>
      </div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:.68rem;
                  color:#4a5060;margin-top:.3rem;letter-spacing:.04em">
        OSS ISSUE INTELLIGENCE
      </div>
    </div>""", unsafe_allow_html=True)

    def format_page_name(p):
        return _inbox_label if p == "Inbox" else p

    page = st.radio(
        "nav",
        PAGES,
        key="page_choice",
        format_func=format_page_name,
        label_visibility="collapsed"
    )

    st.markdown("""
    <div style="margin-top:1.5rem;padding-top:1.2rem;border-top:1px solid #1e2330">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:.65rem;
                  text-transform:uppercase;letter-spacing:.08em;color:#3a4050;
                  margin-bottom:.8rem">Pipeline</div>
    </div>""", unsafe_allow_html=True)

    steps = [
        ("01", "DistilBERT", "Issue classifier"),
        ("02", "XGBoost", "Priority predictor"),
        ("03", "spaCy", "Entity extractor"),
        ("04", "ChromaDB", "RAG retrieval"),
        ("05", "Llama 3.3-70B", "Response generator"),
    ]

    for num, name, desc in steps:
        st.markdown(f"""
        <div style="display:flex;gap:.8rem;padding:.4rem 0;
                    border-bottom:1px solid #141824">
          <span style="font-family:'IBM Plex Mono',monospace;color:#2a3f6a;
                       font-size:.65rem;margin-top:.1rem;flex-shrink:0">{num}</span>
          <div>
            <div style="font-size:.82rem;color:#8090a8;font-weight:500">{name}</div>
            <div style="font-size:.7rem;color:#3a4050">{desc}</div>
          </div>
        </div>""", unsafe_allow_html=True)

if page == "New Issue":
    import pages.new_ticket as p
    p.render()

elif page == "Inbox":
    import pages.inbox as p
    p.render()

elif page == "Issue Detail":
    import pages.detail as p
    p.render()

elif page == "Analytics":
    import pages.analytics as p
    p.render()

elif page == "Train Models":
    import pages.train as p
    p.render()