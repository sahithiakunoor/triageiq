import streamlit as st
from utils import api_get, api_post, badge, PRI_COLOR, CAT_COLOR, STA_COLOR, PRI_LABEL


def render():
    st.markdown("""<div style="padding:1.2rem 0 1rem">
      <div style="font-family:'IBM Plex Serif',serif;font-size:1.6rem;font-weight:600;color:#cdd0d8">Issue Detail</div>
    </div>""", unsafe_allow_html=True)

    col_id, _ = st.columns([1, 2])
    default = st.session_state.get("dtid", "")
    tid_str = col_id.text_input(
        "Issue ID",
        value=str(default) if default else "",
        placeholder="e.g. 1",
        label_visibility="collapsed"
    )

    if not tid_str.strip():
        st.markdown(
            '<div style="color:#3a4050;font-size:.85rem">Enter an issue ID, or click Open ticket from Inbox.</div>',
            unsafe_allow_html=True
        )
        return

    try:
        tid = int(tid_str)
    except ValueError:
        st.error("Invalid ID")
        return

    t = api_get(f"/tickets/{tid}")
    if not t:
        return

    pri = t.get("priority", "P3")
    cat = t.get("category", "Task")
    sta = t.get("status", "pending")

    pcol = PRI_COLOR.get(pri, "#7090a0")
    ccol = CAT_COLOR.get(cat, "#7090a0")
    scol = STA_COLOR.get(sta, "#7090a0")

    breach = t.get("sla_breach_pct", 0)
    pd = PRI_LABEL.get(pri, pri)
    bcol = "#e05252" if breach > 70 else "#c9a84c" if breach > 40 else "#5a9e7a"

    st.markdown(f"""<div class="card">
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:.8rem">
        <div>
          <div style="font-family:'IBM Plex Mono',monospace;color:#3a4050;font-size:.65rem;margin-bottom:.25rem">#{t['id']}</div>
          <div style="font-family:'IBM Plex Serif',serif;font-size:1.15rem;font-weight:600;color:#cdd0d8;margin-bottom:.5rem;line-height:1.35">{t['title']}</div>
          <div style="display:flex;gap:.35rem;flex-wrap:wrap">
            {badge(cat, ccol)}
            {badge(f"{pri}·{pd}", pcol)}
            {badge(sta.upper(), scol)}
            {badge(t.get("assigned_to") or "Unassigned", "#5a8aaa")}
          </div>
        </div>
        <div style="text-align:right">
          <div style="font-family:'IBM Plex Mono',monospace;color:#3a4050;font-size:.65rem">{(t.get('created_at') or '')[:10]}</div>
          <div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;color:{bcol};margin-top:.2rem">{breach}</div>
          <div style="font-size:.68rem;color:#3a4050">urgency score</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    left, right = st.columns([1.1, 1], gap="large")

    with left:
        if t.get("description"):
            st.markdown(
                f'<div class="card"><div class="label" style="margin-bottom:.4rem">Original description</div><p style="color:#6a7080;line-height:1.75;font-size:.86rem;margin:0">{t["description"]}</p></div>',
                unsafe_allow_html=True
            )

        ents = t.get("entities") or {}
        ent_items = [
            f'<span class="ent-chip">{v}</span>'
            for vals in ents.values()
            for v in (vals or [])
        ]

        if ent_items:
            st.markdown(
                f'<div class="card"><div class="label" style="margin-bottom:.4rem">Entities · spaCy</div>{"".join(ent_items)}</div>',
                unsafe_allow_html=True
            )

        if t.get("summary"):
            st.markdown(
                f'<div class="card"><div class="label" style="margin-bottom:.4rem">AI summary</div><p style="line-height:1.75;color:#9aa0b0;font-size:.88rem;margin:0">{t["summary"]}</p></div>',
                unsafe_allow_html=True
            )

        qs = t.get("clarifying_qs") or []
        if qs:
            items = "".join(
                f'<div style="display:flex;gap:.6rem;padding:.4rem 0;border-bottom:1px solid #141824"><span style="font-family:\'IBM Plex Mono\',monospace;color:#2a3f6a;font-size:.65rem;flex-shrink:0">Q{i+1}</span><span style="color:#6a7080;font-size:.84rem">{q}</span></div>'
                for i, q in enumerate(qs)
            )
            st.markdown(
                f'<div class="card"><div class="label" style="margin-bottom:.4rem">Clarifying questions</div>{items}</div>',
                unsafe_allow_html=True
            )

        srcs = t.get("kb_sources") or []
        if srcs:
            chips = "".join(f'<span class="kb-chip">{s}</span>' for s in srcs)
            st.markdown(f'<div style="margin-bottom:.8rem">{chips}</div>', unsafe_allow_html=True)

    with right:
        st.markdown(
            '<div style="font-family:\'IBM Plex Serif\',serif;font-size:1rem;font-weight:600;color:#b0b8c8;margin-bottom:.3rem">Human Review</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div style="color:#4a5060;font-size:.82rem;margin-bottom:1rem">Edit the AI draft if needed, save it, then approve or reject.</div>',
            unsafe_allow_html=True
        )

        if sta in ("approved", "rejected"):
            st.markdown(
                f'<div class="card"><div class="label" style="margin-bottom:.5rem">Final reply · {sta}</div><div class="draft-box">{t.get("agent_reply") or t.get("draft_reply", "")}</div></div>',
                unsafe_allow_html=True
            )

            if t.get("agent_notes"):
                st.markdown(
                    f'<div style="color:#4a5060;font-size:.8rem;margin-top:.3rem">Notes: {t["agent_notes"]}</div>',
                    unsafe_allow_html=True
                )

            if st.button("Back to Inbox", use_container_width=True):
                st.session_state["nav_to_inbox"] = True
                st.rerun()

        else:
            current_reply = t.get("agent_reply") or t.get("draft_reply", "")
            label = "Saved edited reply" if sta == "edited" else "Draft reply from AI"

            st.markdown(
                f'<div class="label" style="margin-bottom:.3rem">{label}</div>',
                unsafe_allow_html=True
            )

            edited = st.text_area(
                "",
                value=current_reply,
                height=180,
                label_visibility="collapsed"
            )

            assigned = st.text_input(
                "Assign to",
                value=t.get("assigned_to") or "",
                placeholder="maintainer@apache.org"
            )

            notes = st.text_input(
                "Notes",
                value=t.get("agent_notes") or "",
                placeholder="e.g. Routed to Spring team"
            )

            ce, ca, cr = st.columns(3)

            if ce.button("Save edit", use_container_width=True):
                api_post(
                    "/review",
                    {
                        "ticket_id": tid,
                        "action": "edit",
                        "agent_reply": edited,
                        "agent_notes": notes,
                        "assigned_to": assigned,
                    }
                )
                st.success("Edit saved. Please approve when ready.")
                st.rerun()

            if ca.button("Approve", type="primary", use_container_width=True):
                if not assigned.strip():
                    st.error("Assignment is required before approval.")
                else:
                    api_post(
                        "/review",
                        {
                            "ticket_id": tid,
                            "action": "approve",
                            "agent_reply": edited,
                            "agent_notes": notes,
                            "assigned_to": assigned,
                        }
                    )
                    st.success(f"Approved and assigned to {assigned}")
                    st.session_state["nav_to_inbox"] = True
                    st.rerun()

            if cr.button("Reject", use_container_width=True):
                api_post(
                    "/review",
                    {
                        "ticket_id": tid,
                        "action": "reject",
                        "agent_reply": edited,
                        "agent_notes": notes,
                        "assigned_to": assigned,
                    }
                )
                st.warning("Rejected")
                st.session_state["nav_to_inbox"] = True
                st.rerun()