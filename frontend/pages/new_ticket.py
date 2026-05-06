import streamlit as st
from utils import api_post, badge, PRI_COLOR, CAT_COLOR, PRI_LABEL

EXAMPLES = [
    ("NullPointerException in JdbcTemplate.queryForObject with empty result",
     "After upgrading Spring Boot from 2.7.8 to 3.0.2, JdbcTemplate.queryForObject throws NPE instead of EmptyResultDataAccessException when the query returns no rows. Java 17, PostgreSQL 15."),
    ("Kafka Streams application loses messages during broker failover",
     "When a Kafka broker goes down during processing, some messages are dropped instead of being retried. Using Kafka 3.4.0 with exactly-once semantics enabled. Production issue."),
    ("Add support for virtual threads in Spring WebFlux",
     "Spring WebFlux should support Java 21 virtual threads (Project Loom) as an alternative to the reactive model for developers who prefer the imperative programming style."),
    ("Maven shade plugin generates invalid JAR when module-info.class is present",
     "Build fails with Invalid signature file digest for Manifest main attributes when shade plugin processes a multi-release JAR. Maven 3.9.1, Java 17."),
]

def go_to_inbox_page():
    st.session_state["page_choice"] = "Inbox"
    st.session_state["nav_to_inbox"] = True

def render():
    st.markdown("""
    <div style="padding:1.2rem 0 1rem">
      <div style="font-family:'IBM Plex Serif',serif;font-size:1.6rem;font-weight:600;
                  color:#cdd0d8;letter-spacing:-.01em">New Issue</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:.7rem;color:#4a5060;
                  margin-top:.3rem;letter-spacing:.03em">
        All 5 pipeline layers run in sequence
      </div>
    </div>""", unsafe_allow_html=True)

    col_form, col_result = st.columns([1, 1.4], gap="large")

    with col_form:
        st.markdown('<div class="label" style="margin-bottom:.5rem">Quick examples</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        for i, (t, d) in enumerate(EXAMPLES):
            if [c1, c2][i%2].button(t[:24]+"…", key=f"ex{i}", use_container_width=True):
                st.session_state["title_val"]           = t
                st.session_state["desc_val"]            = d
                st.session_state["last_analyzed_title"] = ""

        st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)
        title = st.text_input(
            "Issue title *",
            value=st.session_state.get("title_val",""),
            placeholder="e.g. NullPointerException in X when Y"
        )
        desc = st.text_area(
            "Description",
            value=st.session_state.get("desc_val",""),
            placeholder="Java version · library version · steps to reproduce · stack trace",
            height=140
        )

        st.session_state["title_val"] = title
        st.session_state["desc_val"]  = desc

        evaluate = st.toggle("Run LLM evaluation", value=False)
        go = st.button("Analyze Issue →", type="primary", use_container_width=True)

    with col_result:
        if go and title.strip():
            last_analyzed = st.session_state.get("last_analyzed_title", "")
            if title.strip() == last_analyzed:
                st.warning("This issue was already analyzed. Edit the title or clear the form to submit a new one.")
                r = None
            else:
                with st.spinner("Running pipeline…"):
                    r = api_post("/analyze", {"title":title,"description":desc,"evaluate":evaluate})
            if r is None:
                pass
            elif "Duplicate ticket detected" in str(r.get("detail", "")):
                st.error(r.get("detail"))
            elif r.get("detail","").startswith("Models not trained"):
                st.error("Models not trained. Go to Train Models, upload the CSV, and train first.")
            else:
                _show(r)
                st.session_state["last_tid"] = r.get("ticket_id")
                st.session_state["last_analyzed_title"] = title.strip()
                st.session_state["title_val"] = ""
                st.session_state["desc_val"] = ""
                
        elif go:
            st.warning("Enter an issue title.")
        else:
            st.markdown("""
            <div style="border:1px solid #1e2330;border-radius:6px;padding:3rem 2rem;
                        text-align:center;background:#0c0f16;margin-top:.5rem">
              <div style="font-family:'IBM Plex Mono',monospace;font-size:.7rem;
                          color:#3a4050;letter-spacing:.06em">AWAITING INPUT</div>
              <div style="font-size:.88rem;color:#4a5060;margin-top:.5rem">
                Submit an issue to begin analysis
              </div>
            </div>""", unsafe_allow_html=True)


def _show(r):
    cat    = r.get("category","Bug");   pri = r.get("priority","P3")
    urgency = r.get("urgency_score", r.get("sla_breach_pct",40))
    ms     = r.get("processing_ms",0); cc = int(r.get("category_confidence",0)*100)
    pc     = int(r.get("priority_confidence",0)*100)
    pcol   = PRI_COLOR.get(pri,"#7090a0"); ccol = CAT_COLOR.get(cat,"#7090a0")
    ucol   = "#e05252" if urgency>70 else "#c9a84c" if urgency>40 else "#5a9e7a"
    ml     = r.get("category_source","DistilBERT"); pd = PRI_LABEL.get(pri,pri)

    st.markdown(f"""
    <div style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;margin-bottom:1rem">
      {badge(cat,ccol)} {badge(f"{pri} · {pd}",pcol)}
      <span style="font-family:'IBM Plex Mono',monospace;font-size:.68rem;color:#4a5060">{ms}ms</span>
    </div>""", unsafe_allow_html=True)

    st.markdown(f"""<div class="card">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:1rem">
        <div><div class="label">Classifier</div>
             <div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:{ccol}">{cc}%</div>
             <div class="bar-wrap"><div class="bar" style="width:{cc}%;background:{ccol}"></div></div>
             <div style="font-size:.67rem;color:#3a4050;font-family:'IBM Plex Mono',monospace">{ml}</div></div>
        <div><div class="label">Priority</div>
             <div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:{pcol}">{pc}%</div>
             <div class="bar-wrap"><div class="bar" style="width:{pc}%;background:{pcol}"></div></div>
             <div style="font-size:.67rem;color:#3a4050;font-family:'IBM Plex Mono',monospace">XGBoost</div></div>
        <div><div class="label">Urgency</div>
             <div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:{ucol}">{urgency}</div>
             <div class="bar-wrap"><div class="bar" style="width:{urgency}%;background:{ucol}"></div></div>
             <div style="font-size:.67rem;color:#3a4050;font-family:'IBM Plex Mono',monospace">Score /100</div></div>
        <div><div class="label">KB Chunks</div>
             <div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:#5a8aaa">{r.get("kb_chunks_used",0)}</div>
             <div class="bar-wrap"><div class="bar" style="width:100%;background:#5a8aaa"></div></div>
             <div style="font-size:.67rem;color:#3a4050;font-family:'IBM Plex Mono',monospace">ChromaDB</div></div>
      </div>
    </div>""", unsafe_allow_html=True)

    srcs = r.get("kb_sources",[])
    if srcs:
        chips = "".join(f'<span class="kb-chip">{s}</span>' for s in srcs)
        st.markdown(f'<div style="margin-bottom:.8rem">{chips}</div>', unsafe_allow_html=True)

    ents = r.get("entities",{})
    ent_items = [f'<span class="ent-chip">{v}</span>' for vals in ents.values() for v in (vals or [])]
    if ent_items:
        st.markdown(f'<div class="card"><div class="label" style="margin-bottom:.5rem">Entities · spaCy</div>{"".join(ent_items)}</div>', unsafe_allow_html=True)

    ej = r.get("escalation_justification","")
    if ej:
        st.markdown(f"""<div style="background:#0c0f16;border:1px solid #1e2330;border-radius:4px;
                           padding:.7rem 1rem;margin-bottom:.8rem">
          <span style="font-family:'IBM Plex Mono',monospace;font-size:.65rem;
                       color:#3a4050;text-transform:uppercase;letter-spacing:.06em">Rationale</span>
          <div style="font-size:.84rem;color:#6a7080;margin-top:.25rem">{ej}</div>
        </div>""", unsafe_allow_html=True)

    if r.get("summary"):
        st.markdown(f'<div class="card"><div class="label" style="margin-bottom:.4rem">Summary · Llama 3.3-70B</div><p style="line-height:1.75;color:#9aa0b0;font-size:.9rem;margin:0">{r["summary"]}</p></div>', unsafe_allow_html=True)

    qs = r.get("clarifying_questions",[])
    if qs:
        items = "".join(f'<div style="display:flex;gap:.7rem;padding:.4rem 0;border-bottom:1px solid #141824"><span style="font-family:\'IBM Plex Mono\',monospace;color:#2a3f6a;font-size:.68rem;flex-shrink:0;padding-top:.1rem">Q{i+1}</span><span style="color:#6a7080;font-size:.86rem;line-height:1.6">{q}</span></div>' for i,q in enumerate(qs))
        st.markdown(f'<div class="card"><div class="label" style="margin-bottom:.4rem">Clarifying Questions</div>{items}</div>', unsafe_allow_html=True)

    draft = r.get("draft_reply","")
    if draft:
        st.markdown(f'<div class="card"><div class="label" style="margin-bottom:.7rem">Maintainer Draft Reply</div><div class="draft-box">{draft}</div></div>', unsafe_allow_html=True)
        st.download_button("Download draft", draft, file_name="draft_reply.txt", use_container_width=True)

    eval_scores = r.get("eval_scores")
    if eval_scores and "error" not in eval_scores:
        _show_eval(eval_scores)

    tid = r.get("ticket_id")
    if tid:
        st.markdown(f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:.68rem;color:#6a7585;margin-top:.4rem">Issue #{tid} saved · pending review</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
        st.button(
            "Go to Inbox to Review →",
            type="primary",
            use_container_width=True,
            on_click=go_to_inbox_page
        )


def _show_eval(scores):
    dims = ["faithfulness","relevance","completeness","tone"]
    cols = {5:"#5a9e7a",4:"#5a8aaa",3:"#c9a84c",2:"#d4845a",1:"#e05252"}
    overall = scores.get("overall",0); oc = cols.get(round(overall),"#6a7080")
    rows = ""
    for d in dims:
        s = scores.get(d,{}); sc = s.get("score",0); c = cols.get(sc,"#6a7080")
        bar = "▓"*sc + "░"*(5-sc)
        rows += (f'<div style="display:flex;gap:1rem;align-items:flex-start;padding:.4rem 0;'
                 f'border-bottom:1px solid #141824">'
                 f'<div style="min-width:90px;font-size:.8rem;text-transform:capitalize;color:#8090a8">{d}</div>'
                 f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{c};font-size:.75rem;flex-shrink:0">{bar}</div>'
                 f'<div style="color:#4a5060;font-size:.78rem;line-height:1.5">{s.get("reason","")}</div></div>')
    imp = scores.get("improvement","")
    imp_html = f'<div style="margin-top:.7rem;font-size:.8rem;color:#4a5060;border-top:1px solid #141824;padding-top:.5rem">{imp}</div>' if imp else ""
    st.markdown(
        f'<div class="card">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.7rem">'
        f'<div class="label">LLM Evaluation · Llama-as-Judge</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1rem;color:{oc}">{overall}/5</div>'
        f'</div>{rows}{imp_html}</div>',
        unsafe_allow_html=True
    )