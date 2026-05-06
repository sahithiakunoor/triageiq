"""
Train Models page — uses API (POST /train + GET /train/status) correctly.
Training runs in the backend process, saves to backend/models/ guaranteed.
Status cards read from GET /model/info.
"""

import streamlit as st
import tempfile, os, sys, time
import pandas as pd


from utils import api_get, api_post, api_upload

PRI_COLOR = {"P1":"#e05252","P2":"#d4845a","P3":"#c9a84c","P4":"#5a9e7a","P5":"#7090a0"}
CAT_COLOR = {"Bug":"#e05252","New Feature":"#5a7fd4","Improvement":"#5aaab4",
             "Task":"#5a9e7a","Test":"#9a6ab4"}


def _bar(label, count, total, color, subtitle=""):
    pct = int(count / total * 100) if total else 0
    return f"""<div style="margin-bottom:.8rem">
      <div style="display:flex;justify-content:space-between;margin-bottom:.25rem">
        <span style="font-size:.85rem;color:#8090a8">{label}
          <span style="font-size:.74rem;color:#4a5060">{subtitle}</span>
        </span>
        <span style="font-family:'IBM Plex Mono',monospace;color:{color};font-size:.72rem">{count:,} ({pct}%)</span>
      </div>
      <div style="background:#1e2330;border-radius:2px;height:3px;overflow:hidden">
        <div style="width:{pct}%;height:100%;background:{color};border-radius:2px"></div>
      </div></div>"""


def _model_card(col, title, src, model_name, acc, f1, wf1):
    src_color = "#5a9e7a" if src not in ("not_trained", "", None) else "#e05252"
    col.markdown(
        f'<div class="card">'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:.68rem;'
        f'text-transform:uppercase;letter-spacing:.08em;color:#4a5060;margin-bottom:.7rem">{title}</div>'
        f'<div style="display:flex;gap:1.5rem;flex-wrap:wrap">'
        f'<div><div style="font-size:.72rem;color:#4a5060;margin-bottom:.2rem">Source</div>'
        f'<div style="font-weight:500;color:{src_color};font-size:.88rem">{src or "not_trained"}</div></div>'
        f'<div><div style="font-size:.72rem;color:#4a5060;margin-bottom:.2rem">Model</div>'
        f'<div style="font-weight:500;color:#8090a8;font-size:.88rem">{model_name or "—"}</div></div>'
        + (f'<div><div style="font-size:.72rem;color:#4a5060;margin-bottom:.2rem">Accuracy</div>'
           f'<div style="font-weight:500;color:#5a8aaa;font-family:\'IBM Plex Mono\',monospace">{acc}</div></div>' if acc else '')
        + (f'<div><div style="font-size:.72rem;color:#4a5060;margin-bottom:.2rem">Macro F1</div>'
           f'<div style="font-weight:500;color:#5a8aaa;font-family:\'IBM Plex Mono\',monospace">{f1}</div></div>' if f1 else '')
        + (f'<div><div style="font-size:.72rem;color:#4a5060;margin-bottom:.2rem">Weighted F1</div>'
           f'<div style="font-weight:500;color:#5a8aaa;font-family:\'IBM Plex Mono\',monospace">{wf1}</div></div>' if wf1 else '')
        + '</div></div>',
        unsafe_allow_html=True
    )

PRIORITY_DISPLAY = {
    "P1": "Blocker",
    "P2": "Critical",
    "P3": "Major",
    "P4": "Minor",
    "P5": "Trivial",
}

RAW_PRIORITY_TO_P = {
    "blocker": "P1",
    "critical": "P2",
    "major": "P3",
    "minor": "P4",
    "trivial": "P5",
    "highest": "P1",
    "high": "P2",
    "medium": "P3",
    "low": "P4",
    "lowest": "P5",
}


def _find_col(df, candidates):
    lower_map = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        key = cand.lower().strip()
        if key in lower_map:
            return lower_map[key]
    return None


def _normalize_issue_type(x):
    x = str(x).strip().lower()

    if x in ("bug", "defect", "patch"):
        return "Bug"
    if x in ("new feature", "feature", "feature request", "wish"):
        return "New Feature"
    if x in ("improvement", "enhancement", "refactoring"):
        return "Improvement"
    if x in ("test", "testing"):
        return "Test"
    if x in ("task", "sub-task", "subtask", "story", "epic", "documentation", "doc"):
        return "Task"

    return "Task"


def _normalize_priority(x):
    x = str(x).strip()

    if x.upper() in ("P1", "P2", "P3", "P4", "P5"):
        return x.upper()

    return RAW_PRIORITY_TO_P.get(x.lower(), "P3")


def load_and_clean_for_eda(csv_path, sample_n=50000):
    df = pd.read_csv(csv_path, nrows=sample_n, low_memory=False)

    title_col = _find_col(df, ["title", "summary", "issue_title"])
    desc_col = _find_col(df, ["description", "body", "issue_description"])
    type_col = _find_col(df, ["issue_type", "issuetype", "type"])
    priority_col = _find_col(df, ["priority", "priority_name"])

    missing = []
    if not title_col:
        missing.append("title/summary")
    if not desc_col:
        missing.append("description")
    if not type_col:
        missing.append("issue_type/issuetype")
    if not priority_col:
        missing.append("priority")

    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    clean = pd.DataFrame()
    clean["title"] = df[title_col].fillna("").astype(str)
    clean["description"] = df[desc_col].fillna("").astype(str)
    clean["text"] = (clean["title"] + " " + clean["description"]).str.strip()
    clean["issue_type"] = df[type_col].apply(_normalize_issue_type)
    clean["priority"] = df[priority_col].apply(_normalize_priority)

    clean = clean[clean["text"].str.len() > 0]
    clean = clean[clean["priority"].isin(["P1", "P2", "P3", "P4", "P5"])]

    return clean.reset_index(drop=True)

def show_eda(df):
    import plotly.graph_objects as go
    
    st.markdown("""<div style="padding:.5rem 0 1rem">
      <div style="font-family:'IBM Plex Serif',serif;font-size:1.1rem;font-weight:600;color:#cdd0d8">Dataset EDA</div>
    </div>""", unsafe_allow_html=True)

    df["text_len"] = df["text"].str.len()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total rows",     f"{len(df):,}")
    m2.metric("Issue types",    df["issue_type"].nunique())
    m3.metric("Priority levels",df["priority"].nunique())
    m4.metric("Avg text length",f"{int(df['text_len'].mean())} chars")

    BG   = "rgba(0,0,0,0)"; FC = "#8090a8"; GC = "rgba(67,97,238,0.08)"
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div style="font-family:\'IBM Plex Mono\',monospace;font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:#4a5060;margin-bottom:.5rem">Issue type distribution</div>', unsafe_allow_html=True)
        tc = df["issue_type"].value_counts().reset_index()
        tc.columns = ["type","count"]
        fig = go.Figure(go.Bar(
            x=tc["count"], y=tc["type"], orientation="h",
            marker_color=[CAT_COLOR.get(t,"#7090a0") for t in tc["type"]],
            text=tc["count"].apply(lambda v: f"{v:,}"),
            textposition="outside", textfont=dict(color=FC, size=11),
        ))
        fig.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, font=dict(color=FC),
                         xaxis=dict(showgrid=True, gridcolor=GC, zeroline=False),
                         yaxis=dict(autorange="reversed"),
                         margin=dict(l=10,r=60,t=5,b=5), height=280, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown('<div style="font-family:\'IBM Plex Mono\',monospace;font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:#4a5060;margin-bottom:.5rem">Priority distribution</div>', unsafe_allow_html=True)
        pc = df["priority"].value_counts().reindex(["P1","P2","P3","P4","P5"]).dropna().reset_index()
        pc.columns = ["priority","count"]
        pc["label"] = pc["priority"].apply(lambda p: f"{p} — {PRIORITY_DISPLAY.get(p,p)}")
        fig2 = go.Figure(go.Bar(
            x=pc["count"], y=pc["label"], orientation="h",
            marker_color=[PRI_COLOR.get(p,"#7090a0") for p in pc["priority"]],
            text=pc["count"].apply(lambda v: f"{v:,} ({int(v/len(df)*100)}%)"),
            textposition="outside", textfont=dict(color=FC, size=11),
        ))
        fig2.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, font=dict(color=FC),
                          xaxis=dict(showgrid=True, gridcolor=GC, zeroline=False),
                          yaxis=dict(autorange="reversed"),
                          margin=dict(l=10,r=90,t=5,b=5), height=200, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    # Consolidation note
    st.info("**Issue type consolidation applied:** Feature Request/Wish → New Feature · "
            "Enhancement/Refactoring → Improvement · Sub-task/Story/Epic/Documentation → Task · Patch → Bug. "
            "Reduces 14+ raw types to 5 clean categories.")

    # Imbalance warning
    type_v = df["issue_type"].value_counts()
    pri_v  = df["priority"].value_counts()
    tr = type_v.iloc[0] / max(type_v.iloc[-1], 1)
    pr = pri_v.iloc[0]  / max(pri_v.iloc[-1],  1)
    if tr > 5 or pr > 5:
        st.warning(
            f"**Class imbalance detected** — "
            f"Issue types: {type_v.index[0]} is {tr:.0f}x the smallest class. "
            f"Priority: P3 Major is {pr:.0f}x P1 Blocker. "
            f"DistilBERT: CAP/MIN resampling during offline Colab fine-tuning. XGBoost: balanced sample weights during training + rule-based escalation for high-risk P1/P2 cases."
        )


def show_metrics(report, label):
    if not report: return
    acc = report.get("accuracy"); f1 = report.get("macro_f1")
    wf1 = report.get("weighted_f1"); src = report.get("source","—")
    pc  = report.get("per_class", {})
    st.markdown(f'<div style="font-family:\'IBM Plex Serif\',serif;font-size:1rem;font-weight:600;color:#cdd0d8;margin-bottom:.5rem">{label}</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Accuracy",    acc or "—")
    c2.metric("Macro F1",    f1  or "—")
    c3.metric("Weighted F1", wf1 or "—")
    c4.metric("Source",      src)
    if pc:
        rows = ""
        for cls, m in pc.items():
            color = CAT_COLOR.get(cls, PRI_COLOR.get(cls,"#7090a0"))
            rows += (f'<div style="display:grid;grid-template-columns:130px 1fr 1fr 1fr 80px;'
                     f'gap:.5rem;align-items:center;padding:.45rem 0;'
                     f'border-bottom:1px solid #141824">'
                     f'<span style="font-size:.82rem;color:{color}">{cls}</span>'
                     f'<div><div style="font-size:.68rem;color:#4a5060">Precision</div>'
                     f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:.82rem">{m["precision"]}</div></div>'
                     f'<div><div style="font-size:.68rem;color:#4a5060">Recall</div>'
                     f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:.82rem">{m["recall"]}</div></div>'
                     f'<div><div style="font-size:.68rem;color:#4a5060">F1</div>'
                     f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:.82rem">{m["f1"]}</div></div>'
                     f'<div style="font-size:.7rem;color:#4a5060">{m["support"]:,} samples</div>'
                     f'</div>')
        st.markdown(f'<div class="card">{rows}</div>', unsafe_allow_html=True)



def render():
    # Show training success banner if just completed
    if st.session_state.get("training_just_completed"):
        st.success("✅ Both models trained and saved successfully!")
        st.session_state["training_just_completed"] = False

    st.markdown("""<div style="padding:1.2rem 0 1rem">
      <div style="font-family:'IBM Plex Serif',serif;font-size:1.6rem;font-weight:600;color:#cdd0d8">Train Models</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:.7rem;color:#4a5060;margin-top:.3rem">
        Upload the Jira Issues CSV — EDA shown before training
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Model status — session state (fresh after training) or API ──────────
    c1, c2 = st.columns(2)

    fresh_clf = st.session_state.get("last_clf_report", {})
    fresh_pri = st.session_state.get("last_pri_report", {})

    # Fall back to API if no session state
    if not fresh_clf or not fresh_pri:
        info      = api_get("/model/info") or {}
        fresh_clf = fresh_clf or info.get("classifier", {})
        fresh_pri = fresh_pri or info.get("priority",   {})

    clf_src = fresh_clf.get("source") or "not_trained"
    _model_card(c1, "Issue Classifier",
                clf_src,
                fresh_clf.get("model", "distilbert-base-uncased" if "distilbert" in clf_src else "TF-IDF + LR"),
                fresh_clf.get("accuracy"), fresh_clf.get("macro_f1"), fresh_clf.get("weighted_f1"))

    pri_src = fresh_pri.get("source") or "not_trained"
    _model_card(c2, "Priority Predictor (XGBoost)",
                pri_src, "XGBoost",
                fresh_pri.get("accuracy"), fresh_pri.get("macro_f1"), fresh_pri.get("weighted_f1"))

    st.markdown("---")

    # ── DistilBERT notice ─────────────────────────────────────────────────────
    if "distilbert" in clf_src:
        st.success("DistilBERT model detected — classifier will use fine-tuned DistilBERT automatically.")
    else:
        st.info(
            "No DistilBERT model found. Run the Colab notebook to fine-tune DistilBERT, "
            "then place `distilbert_classifier/` in `backend/`. "
            "Until then, training below uses TF-IDF + Logistic Regression."
        )

    # ── CSV Upload ────────────────────────────────────────────────────────────
    st.markdown("""<div style="font-family:'IBM Plex Serif',serif;font-size:1.1rem;
                              font-weight:600;color:#cdd0d8;margin-bottom:.3rem">
      Upload Jira Issues CSV</div>""", unsafe_allow_html=True)

    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    sample_n = st.slider("Sample size (rows)", 5000, 100000, 50000, step=5000)

    if not uploaded:
        st.markdown('<div style="font-size:.82rem;color:#4a5060">Expected columns: '
                    '<code>title/summary</code>, <code>description</code>, '
                    '<code>issue_type/issuetype</code>, <code>priority</code>, '
                    '<code>status</code>, <code>created</code>, <code>resolved</code></div>',
                    unsafe_allow_html=True)
        return

    # Write CSV to temp and show EDA
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    try:
        with st.spinner("Loading dataset for EDA…"):
            df = load_and_clean_for_eda(tmp_path, sample_n=sample_n)
        show_eda(df)
    except Exception as e:
        st.error(f"Failed to load CSV: {e}")
        os.unlink(tmp_path)
        return
    
    st.markdown("---")

    if st.button("Train Priority Model / Refresh Training", type="primary"):
        # ── Upload CSV to backend and start training job ──────────────────────
        uploaded.seek(0)   # reset file position after EDA read
        resp = api_upload("/train/upload", uploaded, data={"sample_n": str(sample_n)})
        if not resp or not resp.get("job_id"):
            st.error("Failed to start training job.")
            os.unlink(tmp_path)
            return

        job_id = resp["job_id"]
        steps  = [
            (0.15, "Loading and cleaning CSV…"),
            (0.35, "Checking issue classifier source…"),
            (0.60, "Training Priority Predictor (XGBoost)…"),
            (0.82, "Saving models to backend/models/…"),
            (0.95, "Finalising…"),
        ]
        bar     = st.progress(0, text="Starting training job…")
        step_i  = 0
        result  = None

        for attempt in range(60):     # max 10 minutes
            time.sleep(10)
            status = api_get(f"/train/status/{job_id}")
            if not status:
                continue
            if status["status"] == "error":
                st.error(f"Training failed:\n```\n{status.get('error','unknown')}\n```")
                os.unlink(tmp_path)
                return
            if status["status"] == "done":
                result = status.get("result") or {}
                bar.progress(1.0, text="Done!")
                break
            if step_i < len(steps):
                frac, msg = steps[step_i]
                bar.progress(frac, text=msg)
                step_i += 1

        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

        if not result:
            st.error("Training timed out. Check the uvicorn terminal for errors.")
            return

        # Store results and rerun to refresh status cards at top
        st.session_state["last_clf_report"]         = result.get("classifier") or {}
        st.session_state["last_pri_report"]         = result.get("priority")   or {}
        st.session_state["training_just_completed"] = True
        st.balloons()
        st.rerun()

        clf_r = result.get("classifier") or {}
        pri_r = result.get("priority")   or {}

        if clf_r:
            st.markdown("---")
            show_metrics(clf_r, "Issue Classifier — Per-class Results")
        if pri_r:
            st.markdown("---")
            show_metrics(pri_r, "Priority Predictor (XGBoost) — Per-class Results")