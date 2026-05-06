import streamlit as st
from utils import api_get, api_post, PRI_COLOR, CAT_COLOR, STA_COLOR, PRI_LABEL

def _bar(label, count, total, color, sub=""):
    pct=int(count/total*100) if total else 0
    return f"""<div style="margin-bottom:.8rem">
      <div style="display:flex;justify-content:space-between;margin-bottom:.25rem">
        <span style="font-size:.85rem;color:#8090a8">{label} <span style="color:#4a5060;font-size:.75rem">{sub}</span></span>
        <span style="font-family:'IBM Plex Mono',monospace;color:{color};font-size:.72rem">{count:,} ({pct}%)</span>
      </div>
      <div style="background:#1e2330;border-radius:2px;height:3px;overflow:hidden">
        <div style="width:{pct}%;height:100%;background:{color};border-radius:2px"></div>
      </div></div>"""

def render():
    st.markdown("""<div style="padding:1.2rem 0 1rem">
      <div style="font-family:'IBM Plex Serif',serif;font-size:1.6rem;font-weight:600;color:#cdd0d8">Analytics</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:.7rem;color:#4a5060;margin-top:.3rem">Real-time insights across all triaged issues</div>
    </div>""", unsafe_allow_html=True)

    _,col_r=st.columns([4,1])
    if col_r.button("Reset DB",use_container_width=True):
        if st.session_state.get("confirm_reset"):
            result=api_post("/reset",{})
            if result:
                st.success(f"Deleted {result.get('deleted',0)} issues.")
                st.session_state["confirm_reset"]=False; st.rerun()
        else:
            st.session_state["confirm_reset"]=True; st.rerun()
    if st.session_state.get("confirm_reset"):
        st.warning("Click Reset DB again to confirm.")

    data=api_get("/analytics")
    if not data or data.get("total",0)==0:
        st.markdown('<div style="text-align:center;padding:3rem;color:#3a4050;font-family:\'IBM Plex Mono\',monospace;font-size:.78rem">NO DATA YET — SUBMIT ISSUES TO SEE ANALYTICS</div>',unsafe_allow_html=True)
        return

    total=data["total"]; approved=data["resolved"]; approval_rate=data["resolution_rate"]
    p1p2=data["p1_p2_count"]; avg_ms=data["avg_processing_ms"]
    by_cat=data.get("by_category",{}); by_pri=data.get("by_priority",{}); by_sta=data.get("by_status",{})

    k1,k2,k3,k4,k5=st.columns(5)
    k1.metric("Total",total); k2.metric("Approved",approved); k3.metric("Approval Rate",f"{approval_rate}%")
    k4.metric("P1/P2",p1p2); k5.metric("Avg triage",f"{avg_ms}ms")
    st.markdown("<div style='height:.3rem'></div>",unsafe_allow_html=True)

    left,right=st.columns(2,gap="large")
    with left:
        st.markdown('<div class="label" style="margin-bottom:.6rem">Issue type</div>',unsafe_allow_html=True)
        st.markdown('<div class="card">'+"".join(_bar(c,n,total,CAT_COLOR.get(c,"#7090a0")) for c,n in sorted(by_cat.items(),key=lambda x:-x[1]))+'</div>',unsafe_allow_html=True)
        st.markdown('<div class="label" style="margin-bottom:.6rem">Status</div>',unsafe_allow_html=True)
        st.markdown('<div class="card">'+"".join(_bar(s.capitalize(),n,total,STA_COLOR.get(s,"#7090a0")) for s,n in sorted(by_sta.items(),key=lambda x:-x[1]))+'</div>',unsafe_allow_html=True)

    with right:
        st.markdown('<div class="label" style="margin-bottom:.6rem">Priority</div>',unsafe_allow_html=True)
        st.markdown('<div class="card">'+"".join(_bar(p,by_pri.get(p,0),total,PRI_COLOR.get(p,"#7090a0"),PRI_LABEL.get(p,"")) for p in ["P1","P2","P3","P4","P5"] if by_pri.get(p,0)>0)+'</div>',unsafe_allow_html=True)
        pending=by_sta.get("pending",0)
        st.markdown(f"""<div class="card">
          <div class="label" style="margin-bottom:.8rem">URGENCY ANALYSIS</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
            <div><div class="label">Pending</div><div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:#c9a84c">{pending}</div></div>
            <div><div class="label">High urgency</div><div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:#e05252">{p1p2}</div></div>
            <div><div class="label">Avg triage</div><div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:#5a8aaa">{avg_ms}ms</div></div>
            <div><div class="label">Approval Rate</div><div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:#5a9e7a">{approval_rate}%</div></div>
          </div></div>""", unsafe_allow_html=True)