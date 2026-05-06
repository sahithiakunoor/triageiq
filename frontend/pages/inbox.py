import streamlit as st
from utils import api_get, badge, PRI_COLOR, CAT_COLOR, STA_COLOR, PRI_LABEL


def open_ticket(ticket_id):
    st.session_state["dtid"] = ticket_id
    st.session_state["page_choice"] = "Issue Detail"


def render():
    st.markdown("""<div style="padding:1.2rem 0 1rem">
      <div style="font-family:'IBM Plex Serif',serif;font-size:1.6rem;font-weight:600;color:#cdd0d8">Inbox</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:.7rem;color:#4a5060;margin-top:.3rem">
        Click a ticket to open the full human review workspace
      </div>
    </div>""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 1, 2])
    sf = c1.selectbox("Status", ["All", "pending", "approved", "edited", "rejected"], label_visibility="collapsed")
    pf = c2.selectbox("Priority", ["All", "P1", "P2", "P3", "P4", "P5"], label_visibility="collapsed")

    if c3.button("Refresh", use_container_width=False):
        st.rerun()

    params = {}
    if sf != "All":
        params["status"] = sf
    if pf != "All":
        params["priority"] = pf

    tickets = api_get("/tickets", params)

    if not tickets:
        st.markdown(
            '<div style="text-align:center;padding:3rem;color:#3a4050;font-family:\'IBM Plex Mono\',monospace;font-size:.78rem">NO ISSUES YET</div>',
            unsafe_allow_html=True
        )
        return

    total = len(tickets)
    pending = sum(1 for t in tickets if t["status"] == "pending")
    p1p2 = sum(1 for t in tickets if t["priority"] in ("P1", "P2"))

    m1, m2, m3 = st.columns(3)
    m1.metric("Total", total)
    m2.metric("Pending", pending)
    m3.metric("P1/P2", p1p2)

    st.markdown("<div style='height:.3rem'></div>", unsafe_allow_html=True)

    for t in tickets:
        pri = t.get("priority", "P3")
        cat = t.get("category", "Task")
        sta = t.get("status", "pending")

        pc = PRI_COLOR.get(pri, "#7090a0")
        cc = CAT_COLOR.get(cat, "#7090a0")
        sc = STA_COLOR.get(sta, "#7090a0")
        pd = PRI_LABEL.get(pri, pri)

        ticket_id = t["id"]
        title = t.get("title", "")[:75]
        summary = t.get("summary", "")[:110]
        created_at = (t.get("created_at") or "")[:10]
        sla_risk = t.get("sla_risk", "")

        st.markdown(f"""
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:.4rem">
            <div>
              <div style="font-family:'IBM Plex Mono',monospace;color:#3a4050;font-size:.65rem;margin-bottom:.25rem">#{ticket_id}</div>
              <div style="color:#b0b8c8;font-size:.9rem;margin-bottom:.4rem;font-weight:500">{title}</div>
              <div style="display:flex;gap:.35rem;flex-wrap:wrap">
                {badge(cat, cc)} {badge(f"{pri}·{pd}", pc)} {badge(sta.upper(), sc)} {badge(t.get("assigned_to") or "Unassigned", "#5a8aaa")}
              </div>
            </div>
            <div style="text-align:right;font-family:'IBM Plex Mono',monospace;font-size:.65rem;color:#3a4050">
              {created_at}<br>
              <span style="color:{pc}">{sla_risk}</span>
            </div>
          </div>
          {f'<div style="color:#4a5060;font-size:.82rem;margin-top:.5rem;line-height:1.6">{summary}…</div>' if summary else ""}
        </div>
        """, unsafe_allow_html=True)

        st.button(
            "Open ticket for review →",
            key=f"open_ticket_{ticket_id}",
            use_container_width=True,
            on_click=open_ticket,
            args=(ticket_id,)
        )