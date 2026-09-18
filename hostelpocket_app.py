"""
HostelPocket — Hostel Expense Tracker for Students
Production Iteration strictly adhering to the Software Design Document (SDD)
- PostgreSQL-backed persistence
- Daily and Monthly circular budget meters
- Expandable category drilldown with item-level purchase history
- Named Friends only (no roommate concept)
- Unified Evidence banner (no UPI SMS section)
- Safe sample UPI QR & deep links
- Hybrid AI insights and dismissible reminders
- Deterministic back navigation
"""

import os
import time
import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

# Data and service layer imports
from db.connection import get_connection
from db.migrations import run_migrations
from repositories import (
    user_repo,
    friend_repo,
    budget_repo,
    expense_repo,
    timeline_repo,
    reminder_repo,
    insight_repo,
)
from services import insight_service
from utils.money import format_inr, validate_item_totals
from utils.dates import get_today, get_current_month_range, format_date_human
from ui.qr import build_sample_upi_uri, generate_sample_qr_base64, get_upi_app_deep_links, validate_sample_upi_id
from ui.components import render_circular_budget_meter, render_evidence_banner
import ai_services
import prism_tracer

# Ensure database tables exist on startup
try:
    run_migrations()
except Exception as e:
    st.error(f"Database migration notice: {e}")

# --------------------------------------------------------------------------
# DESIGN SYSTEM & TOKENS
# --------------------------------------------------------------------------

NAVY = "#14213D"
PAPER = "#F7F5F1"
MARIGOLD = "#E8A33D"
GREEN = "#3A6B52"
BRICK = "#B23A2E"
GREY = "#84806F"
PAPER_DIM = "#EDEAE3"

F_DISPLAY = "'Space Grotesk', sans-serif"
F_BODY = "'IBM Plex Sans', sans-serif"
F_MONO = "'IBM Plex Mono', monospace"

st.set_page_config(
    page_title="HostelPocket — Expense Tracker for Students",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS matching SDD Section 5 & Appendix B
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {{
  --hp-navy: var(--text-color, #14213D); 
  --hp-paper: var(--background-color, #F7F5F1); 
  --hp-paper-dim: var(--secondary-background-color, #EDEAE3);
  --hp-marigold: {MARIGOLD};
  --hp-green: {GREEN}; 
  --hp-brick: {BRICK}; 
  --hp-grey: {GREY}; 
  --hp-radius: 12px;
}}

html, body, [class*="css"] {{ font-family:{F_BODY}; }}
#MainMenu, header, footer {{ display:none !important; }}

.block-container {{ padding-top:1.6rem; padding-bottom:3rem; max-width:1160px; }}

h1,h2,h3,h4 {{ font-family:{F_DISPLAY} !important; color:var(--hp-navy) !important; }}
h3 {{ font-size:1.4rem !important; margin-bottom:0.2rem !important; }}

.hp-mono {{ font-family:{F_MONO}; font-variant-numeric:tabular-nums; }}
.hp-card {{
  border:1px solid var(--hp-paper-dim); padding:16px; border-radius:var(--hp-radius);
  background:var(--hp-paper); box-shadow:0 1px 4px rgba(0,0,0,0.05); margin-bottom:12px;
}}
.hp-badge {{
  display:inline-flex; align-items:center; gap:4px; font-size:11px; font-weight:700;
  padding:3px 8px; border-radius:999px; line-height:1.5;
}}
.hp-badge-green {{ color:{GREEN}; background:{GREEN}22; }}
.hp-badge-marigold {{ color:#8a5d16; background:{MARIGOLD}33; }}
.hp-badge-brick {{ color:{BRICK}; background:{BRICK}22; }}

[data-testid="baseButton-primary"] {{
  background-color:{MARIGOLD} !important; color:#14213D !important; border:none !important;
  font-family:{F_BODY} !important; font-weight:700 !important; border-radius:8px !important;
}}
[data-testid="baseButton-secondary"] {{
  background-color:transparent !important; color:var(--hp-navy) !important; border:1px solid var(--hp-paper-dim) !important;
  font-family:{F_BODY} !important; font-weight:600 !important; border-radius:8px !important;
}}
section[data-testid="stSidebar"] {{ background-color:var(--hp-paper); border-right:1px solid var(--hp-paper-dim); }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# CENTRALIZED ROUTING & SESSION STATE (Appendix C)
# --------------------------------------------------------------------------

def init_session():
    d = st.session_state
    d.setdefault("authenticated", True)
    d.setdefault("user_id", None)
    d.setdefault("user_email", "javin.student@gmail.com")
    d.setdefault("display_name", "Javin")
    d.setdefault("route", "dashboard")
    d.setdefault("nav_stack", [])
    d.setdefault("selected_expense_id", None)
    d.setdefault("active_friend_qr", None)
    d.setdefault("quick_add_success", None)

    # Resolve default user from DB
    if not d.user_id:
        user = user_repo.get_user_by_email(d.user_email)
        if user:
            d.user_id = str(user["id"])
            d.display_name = user["display_name"]
        else:
            new_u = user_repo.create_user(d.user_email, "student123", "Javin")
            d.user_id = str(new_u["id"])

init_session()
S = st.session_state

def navigate_to(new_route: str):
    """Centralized router: pushes previous route onto navigation stack per SDD Appendix C."""
    if S.route != new_route:
        S.nav_stack.append(S.route)
        S.route = new_route

def navigate_back():
    """Centralized router: deterministic back action popping navigation stack."""
    if S.nav_stack:
        S.route = S.nav_stack.pop()
    else:
        S.route = "dashboard"

# --------------------------------------------------------------------------
# TOP HEADER & DETERMINISTIC BACK BUTTON
# --------------------------------------------------------------------------

def render_top_header():
    today_str = datetime.date.today().strftime("%A, %d %B %Y")
    hour = datetime.datetime.now().hour
    greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")

    c_back, c_title, c_prof = st.columns([1.2, 5, 2])
    with c_back:
        if S.route != "dashboard":
            if st.button("← Back", key="btn_global_back", type="secondary"):
                navigate_back()
                st.rerun()
    with c_title:
        st.markdown(
            f'<div style="font-size:12px; color:{GREY};">{today_str}</div>'
            f'<div style="font-family:{F_DISPLAY}; font-size:18px; font-weight:700; color:var(--text-color, #14213D);">'
            f'{greeting}, {S.display_name}</div>',
            unsafe_allow_html=True,
        )
    with c_prof:
        st.markdown(
            f'<div style="text-align:right; font-size:12px; color:{GREY};">'
            f'<span>HostelPocket • PRISM Active ⚡</span></div>',
            unsafe_allow_html=True,
        )
    st.markdown('<hr style="border:none; border-top:1px solid #EDEAE3; margin:8px 0 16px 0;" />', unsafe_allow_html=True)

# --------------------------------------------------------------------------
# SCREEN 1: DASHBOARD (SDD Appendix B Wireframe & Section 5.1)
# --------------------------------------------------------------------------

def screen_dashboard():
    render_top_header()
    user_id = S.user_id
    today = get_today()
    month_start, month_end = get_current_month_range()

    # 1. Budget Hero: Two circular meters (Daily and Monthly) per SDD FR-10
    budget_data = budget_repo.get_budget_utilization(user_id, today)

    c_daily, c_monthly = st.columns(2)
    with c_daily:
        daily_html = render_circular_budget_meter(
            title="Daily Budget",
            spent=budget_data["daily_spent"],
            budget=budget_data["daily_budget"],
            period_label="Today",
        )
        st.markdown(daily_html, unsafe_allow_html=True)
        if budget_data["daily_budget"] is None:
            if st.button("Set Daily Budget", key="btn_set_daily_b"):
                navigate_to("budgets")
                st.rerun()

    with c_monthly:
        monthly_html = render_circular_budget_meter(
            title="Monthly Budget",
            spent=budget_data["monthly_spent"],
            budget=budget_data["monthly_budget"],
            period_label=today.strftime("%B %Y"),
        )
        st.markdown(monthly_html, unsafe_allow_html=True)
        if budget_data["monthly_budget"] is None:
            if st.button("Set Monthly Budget", key="btn_set_monthly_b"):
                navigate_to("budgets")
                st.rerun()

    st.write("")

    # 2. Quick Actions Bar (Appendix B)
    st.markdown('<div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.08em; margin-bottom:8px;">Quick Actions</div>', unsafe_allow_html=True)
    q1, q2, q3, q4, q5 = st.columns(5)
    with q1:
        if st.button("＋ Add Expense", key="qa_add", type="primary", use_container_width=True):
            navigate_to("add_expense")
            st.rerun()
    with q2:
        if st.button("📜 History", key="qa_hist", type="secondary", use_container_width=True):
            navigate_to("history")
            st.rerun()
    with q3:
        if st.button("⏱️ Timeline", key="qa_time", type="secondary", use_container_width=True):
            navigate_to("timeline")
            st.rerun()
    with q4:
        if st.button("🎯 Budgets", key="qa_budg", type="secondary", use_container_width=True):
            navigate_to("budgets")
            st.rerun()
    with q5:
        if st.button("👥 Friends", key="qa_frnd", type="secondary", use_container_width=True):
            navigate_to("friends")
            st.rerun()

    st.write("")

    # 3. Spent by Category with Expandable Item Drilldown (SDD FR-09 / AC-05)
    st.markdown('<div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.08em; margin-bottom:8px;">Spent by Category (Expand to see items)</div>', unsafe_allow_html=True)
    cat_aggregates = expense_repo.get_category_aggregates_with_items(user_id, month_start, today)

    if cat_aggregates:
        for cat in cat_aggregates:
            cat_name = cat["category_name"]
            cat_total = cat["total_amount"]
            with st.expander(f"📁 **{cat_name}** — {format_inr(cat_total)}", expanded=False):
                if cat.get("items"):
                    item_df = pd.DataFrame(cat["items"])
                    item_df.columns = ["Item Purchased", "Total Spent (₹)", "Quantity"]
                    st.dataframe(item_df, use_container_width=True, hide_index=True)
                else:
                    st.caption("No itemized entries recorded for this category yet.")
    else:
        st.info("No expenses logged for this month yet. Tap **＋ Add Expense** to record your first student expense!")

    st.write("")

    # 4. Friends / Sample UPI Payment Shortcuts (SDD Section 9 & Appendix B)
    st.markdown('<div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.08em; margin-bottom:8px;">Friends / Sample UPI Pay Shortcuts</div>', unsafe_allow_html=True)
    friends = friend_repo.get_friends(user_id, include_archived=False)

    if friends:
        f_cols = st.columns(min(len(friends), 4))
        for idx, friend in enumerate(friends[:4]):
            col = f_cols[idx % len(f_cols)]
            with col:
                with st.container(border=True):
                    st.markdown(f"**{friend['name']}**")
                    st.caption(friend.get("sample_upi_id") or "No UPI ID set")
                    if st.button("Show QR ↗", key=f"f_qr_{friend['id']}"):
                        S.active_friend_qr = friend
                        navigate_to("friends")
                        st.rerun()
    else:
        st.caption("No friends added yet. Add friends to quickly generate sample payment QR codes.")

    st.write("")

    # 5. AI Insight Strip & In-App Reminders (SDD Section 8 & Appendix B)
    left_ins, right_rem = st.columns([1.2, 1])
    with left_ins:
        st.markdown('<div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.08em; margin-bottom:8px;">AI Financial Insight</div>', unsafe_allow_html=True)
        latest_insight = insight_repo.get_latest_insight(user_id)
        if not latest_insight:
            latest_insight = insight_service.generate_hybrid_insight(user_id)

        with st.container(border=True):
            st.markdown(f"✨ **{latest_insight['title']}**")
            st.markdown(f'<div style="font-size:13.5px; color:#14213D; margin-bottom:8px;">{latest_insight["body"]}</div>', unsafe_allow_html=True)
            if st.button("🔄 Refresh AI Insight", key="btn_ref_ins", type="secondary"):
                with st.spinner("Analyzing spending facts..."):
                    insight_service.generate_hybrid_insight(user_id)
                    st.rerun()

    with right_rem:
        st.markdown('<div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.08em; margin-bottom:8px;">Active Reminders</div>', unsafe_allow_html=True)
        reminders = reminder_repo.evaluate_and_sync_reminders(user_id, budget_data)
        if reminders:
            for rem in reminders[:2]:
                with st.container(border=True):
                    col_r1, col_r2 = st.columns([4, 1])
                    with col_r1:
                        st.markdown(f"🔔 **{rem['title']}**")
                        st.caption(rem.get("body", ""))
                    with col_r2:
                        if st.button("Dismiss", key=f"d_rem_{rem['id']}"):
                            reminder_repo.dismiss_reminder(user_id, str(rem["id"]))
                            st.rerun()
        else:
            st.caption("No pending reminders. All budget rules are green!")

# --------------------------------------------------------------------------
# SCREEN 2: ADD EXPENSE (SDD Section 5.2 / REQ-02 / REQ-03 / REQ-04 / AC-02)
# --------------------------------------------------------------------------

def screen_add_expense():
    render_top_header()
    user_id = S.user_id
    st.markdown("### Add New Expense")
    st.caption("One reliable source of truth. Enter category, amount, item lines, and optional evidence.")

    categories = expense_repo.get_categories()
    cat_names = [c["name"] for c in categories]
    cat_map = {c["name"]: str(c["id"]) for c in categories}

    friends = friend_repo.get_friends(user_id, include_archived=False)
    friend_options = ["None (Self only)"] + [f["name"] for f in friends]
    friend_map = {f["name"]: str(f["id"]) for f in friends}

    # AI Quick Parse helper
    with st.expander("🎙️ Speak or Type Fast Expense (Groq AI Assisted)", expanded=False):
        voice_audio = st.audio_input("Record expense (e.g. 'Paid 450 rupees for dinner with Aman')")
        nl_input = st.text_input("Or type freeform expense", placeholder="e.g. 480 rupees for pizza with Aman")
        
        if voice_audio:
            with st.spinner("Transcribing with Groq Whisper..."):
                transcript = ai_services.transcribe_audio_bytes(voice_audio.read())
                st.info(f"Recognized: {transcript}")
                parsed = ai_services.parse_expense_text(transcript, [f["name"] for f in friends])
                st.session_state["prefill_title"] = parsed.get("title", "")
                st.session_state["prefill_amount"] = float(parsed.get("amount", 0.0))
                st.session_state["prefill_cat"] = parsed.get("category", "Food")
                st.session_state["prefill_items"] = parsed.get("items", [])
                st.session_state["prefill_friend"] = parsed.get("friend")

        if st.button("Parse Text with AI", key="btn_parse_nl") and nl_input:
            with st.spinner("Parsing with Groq LLM..."):
                parsed = ai_services.parse_expense_text(nl_input, [f["name"] for f in friends])
                st.session_state["prefill_title"] = parsed.get("title", "")
                st.session_state["prefill_amount"] = float(parsed.get("amount", 0.0))
                st.session_state["prefill_cat"] = parsed.get("category", "Food")
                st.session_state["prefill_items"] = parsed.get("items", [])
                st.session_state["prefill_friend"] = parsed.get("friend")
                st.rerun()

    # --- OCR Evidence Section (OUTSIDE form so OCR button can trigger rerun) ---
    st.markdown("---")
    st.markdown('<div style="font-size:12px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.06em; margin-bottom:4px;">📷 Scan Receipt / Bill with OCR</div>', unsafe_allow_html=True)
    st.caption("Upload a clear photo of your bill and click Scan to auto-fill the form.")
    uploaded_evidence = st.file_uploader(
        "Upload bill photo or delivery order screenshot",
        type=["png", "jpg", "jpeg"],
        key="evidence_uploader",
        help="PNG/JPG only. Use a well-lit, flat photo for best accuracy.",
    )
    if uploaded_evidence:
        if st.button("🔍 Scan Bill with OCR → Auto-fill Form", key="btn_ocr_scan", type="primary"):
            with st.spinner("Running OCR on your receipt..."):
                img_bytes = uploaded_evidence.read()
                result = ai_services.scan_receipt_image(img_bytes)
            if "error" in result:
                st.error(f"OCR could not read this image: {result['error']}")
                st.caption("Tip: Use a well-lit, straight-on photo. Avoid blurry or crumpled receipts.")
            else:
                ocr_items = result.get("items", [])
                st.session_state["prefill_title"] = result.get("title", "")
                st.session_state["prefill_amount"] = float(result.get("amount", 0.0))
                st.session_state["prefill_cat"] = result.get("category", "Food")
                st.session_state["prefill_items"] = ocr_items
                conf = result.get("confidence", 80)
                st.success(f"✅ Scanned **{len(ocr_items)} item(s)** (confidence {conf}%). Form auto-filled — review below and click Save.")
                st.rerun()

    st.markdown("---")

    # Main Expense Form
    with st.form("form_add_expense"):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("Expense Title / Merchant", value=st.session_state.get("prefill_title", ""), placeholder="e.g. Domino's Pizza, Metro Recharge")
            amount = st.number_input("Total Amount (₹)", min_value=1.0, value=float(st.session_state.get("prefill_amount", 100.0)), step=10.0)
        with c2:
            default_cat = st.session_state.get("prefill_cat", "Food")
            cat_idx = cat_names.index(default_cat) if default_cat in cat_names else 0
            category_sel = st.selectbox("Category", cat_names, index=cat_idx)
            expense_date = st.date_input("Date", value=datetime.date.today())

        # Optional friend tag (NO ROOMMATES PER REQ-01)
        default_f = st.session_state.get("prefill_friend")
        f_idx = friend_options.index(default_f) if default_f in friend_options else 0
        friend_sel = st.selectbox("Tag a Friend (Optional payment/split context)", friend_options, index=f_idx)

        # Itemization section per SDD Section 5.2 / FR-03
        st.markdown("**Purchased Items (Itemization)**")
        st.caption("Items auto-filled by OCR scan above, or enter manually below.")

        prefilled_items = st.session_state.get("prefill_items", [])
        if prefilled_items:
            items_df = pd.DataFrame(prefilled_items)
            display_cols = [c for c in ["item_name", "quantity", "unit_price", "line_total"] if c in items_df.columns]
            if display_cols:
                disp = items_df[display_cols].copy()
                disp.columns = ["Item Name", "Qty", "Unit Price (₹)", "Line Total (₹)"][:len(display_cols)]
                st.dataframe(disp, use_container_width=True, hide_index=True)
            items_payload = prefilled_items
        else:
            item_n = st.text_input("Item Name", value=st.session_state.get("prefill_title", "") or "Item 1", key="it_name_1")
            c_q, c_p = st.columns(2)
            with c_q:
                item_qty = st.number_input("Quantity", min_value=1.0, value=1.0, step=1.0, key="it_qty_1")
            with c_p:
                item_price = st.number_input("Unit Price (₹)", min_value=0.0, value=float(st.session_state.get("prefill_amount", 100.0)), step=10.0, key="it_pr_1")
            items_payload = [{"item_name": item_n, "quantity": item_qty, "unit_price": item_price, "line_total": item_qty * item_price}]

        note = st.text_area("Optional Note", placeholder="Additional context (e.g. Paid via UPI, reimbursed partly)")

        submit_btn = st.form_submit_button("Save Expense Durably ➔", type="primary")

    if submit_btn:
        if not title:
            st.error("Please provide an expense title.")
            return

        cat_id = cat_map[category_sel]
        f_id = friend_map.get(friend_sel)

        # Handle attachment metadata
        attachments_meta = []
        if uploaded_evidence:
            attachments_meta.append({
                "file_name": uploaded_evidence.name,
                "mime_type": uploaded_evidence.type,
                "storage_key": f"local_evidence_{uploaded_evidence.name}",
                "checksum": "sha256_mock_hash",
            })

        # Atomic Commit to PostgreSQL (SDD Section 7.1)
        with st.spinner("Committing transaction to PostgreSQL..."):
            try:
                saved = expense_repo.save_expense_atomic(
                    user_id=user_id,
                    category_id=cat_id,
                    title=title,
                    amount=amount,
                    expense_date=expense_date,
                    friend_id=f_id,
                    note=note,
                    items=items_payload,
                    attachments=attachments_meta,
                )
                st.success(f"✓ Expense '{title}' ({format_inr(amount)}) committed atomically to PostgreSQL!")
                # Reset prefill state
                for k in ["prefill_title", "prefill_amount", "prefill_cat", "prefill_items", "prefill_friend"]:
                    st.session_state.pop(k, None)
                time.sleep(0.5)
                navigate_to("history")
                st.rerun()
            except Exception as err:
                st.error(f"Transaction rolled back: {err}")

# --------------------------------------------------------------------------
# SCREEN 3: HISTORY (SDD Section 5.3 / FR-05 / FR-06 / AC-03)
# --------------------------------------------------------------------------

def screen_history():
    render_top_header()
    user_id = S.user_id
    st.markdown("### Expense History & Item Ledger")
    st.caption("Durable records stored in PostgreSQL. Expand any expense to see purchased item breakdown.")

    categories = expense_repo.get_categories()
    friends = friend_repo.get_friends(user_id, include_archived=True)

    # Filters (SDD Section 5.3)
    with st.expander("🔍 Search & Filter History", expanded=False):
        cf1, cf2, cf3 = st.columns(3)
        with cf1:
            search_query = st.text_input("Text Search", placeholder="Search title, note, or item...")
        with cf2:
            cat_filter = st.selectbox("Category Filter", ["All Categories"] + [c["name"] for c in categories])
        with cf3:
            friend_filter = st.selectbox("Friend Filter", ["All Friends"] + [f["name"] for f in friends])

    sel_cat_id = None
    if cat_filter != "All Categories":
        sel_cat_id = next((str(c["id"]) for c in categories if c["name"] == cat_filter), None)

    sel_f_id = None
    if friend_filter != "All Friends":
        sel_f_id = next((str(f["id"]) for f in friends if f["name"] == friend_filter), None)

    expenses = expense_repo.get_expenses(
        user_id=user_id,
        category_id=sel_cat_id,
        friend_id=sel_f_id,
        search_query=search_query if search_query else None,
        limit=50,
    )

    if expenses:
        for exp in expenses:
            exp_id = str(exp["id"])
            with st.container(border=True):
                c_top1, c_top2 = st.columns([3, 1])
                with c_top1:
                    f_tag = f" • With **{exp['friend_name']}**" if exp.get("friend_name") else ""
                    st.markdown(f"**{exp['title']}** ({exp['category_name']}{f_tag})")
                    st.caption(f"Date: {format_date_human(exp['expense_date'])} • {exp.get('item_count', 1)} item(s)")
                with c_top2:
                    st.markdown(f"<div style='text-align:right; font-family:{F_MONO}; font-size:18px; font-weight:700;'>{format_inr(exp['amount'])}</div>", unsafe_allow_html=True)

                # Expandable details
                with st.expander("🧾 View Purchased Items & Attachments", expanded=False):
                    details = expense_repo.get_expense_details(user_id, exp_id)
                    if details and details.get("items"):
                        items_df = pd.DataFrame(details["items"])[["item_name", "quantity", "unit_price", "line_total"]]
                        items_df.columns = ["Item Name", "Qty", "Unit Price (₹)", "Line Total (₹)"]
                        st.dataframe(items_df, use_container_width=True, hide_index=True)
                    if details and details.get("attachments"):
                        st.caption(f"📎 Attached Evidence: {details['attachments'][0]['file_name']}")
    else:
        st.info("No matching expenses found.")

# --------------------------------------------------------------------------
# SCREEN 4: TIMELINE (SDD Section 5.4 / FR-13 / AC-06)
# --------------------------------------------------------------------------

def screen_timeline():
    render_top_header()
    user_id = S.user_id
    st.markdown("### Activity Timeline")
    st.caption("Audit-friendly append-only activity feed from PostgreSQL timeline_events.")

    events = timeline_repo.get_timeline_events(user_id, limit=30)
    if events:
        for ev in events:
            ev_type = ev.get("event_type", "event")
            time_str = ev.get("occurred_at").strftime("%d %b, %H:%M") if ev.get("occurred_at") else "Recently"
            payload = ev.get("payload", {})
            with st.container(border=True):
                st.markdown(f"⏱️ **{ev_type.upper()}** • <span style='color:#84806F; font-size:12px;'>{time_str}</span>", unsafe_allow_html=True)
                if isinstance(payload, dict):
                    details = " | ".join(f"{k}: {v}" for k, v in payload.items())
                    st.caption(details)
    else:
        st.info("No timeline activity recorded yet.")

# --------------------------------------------------------------------------
# SCREEN 5: BUDGETS (SDD Section 6 / FR-07 / FR-08 / AC-04)
# --------------------------------------------------------------------------

def screen_budgets():
    render_top_header()
    user_id = S.user_id
    today = get_today()
    month_start, _ = get_current_month_range()

    st.markdown("### Daily & Monthly Budget Management")
    st.caption("Set strict budget caps per SDD Section 6 (FR-07 & FR-08).")

    cur_util = budget_repo.get_budget_utilization(user_id, today)

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("#### 📅 Daily Budget")
            current_d = cur_util.get("daily_budget") or 500.0
            new_daily = st.number_input("Set Today's Budget (₹)", min_value=50.0, value=float(current_d), step=50.0)
            if st.button("Save Daily Budget", key="btn_save_daily_b", type="primary"):
                budget_repo.set_budget(user_id, "day", today, new_daily)
                timeline_repo.append_timeline_event(user_id, "budget.updated", "budget", payload={"period": "day", "amount": new_daily})
                st.success(f"Daily budget set to {format_inr(new_daily)}!")
                st.rerun()

    with c2:
        with st.container(border=True):
            st.markdown("#### 🗓️ Monthly Budget")
            current_m = cur_util.get("monthly_budget") or 10000.0
            new_monthly = st.number_input(f"Set {today.strftime('%B')} Budget (₹)", min_value=500.0, value=float(current_m), step=250.0)
            if st.button("Save Monthly Budget", key="btn_save_monthly_b", type="primary"):
                budget_repo.set_budget(user_id, "month", month_start, new_monthly)
                timeline_repo.append_timeline_event(user_id, "budget.updated", "budget", payload={"period": "month", "amount": new_monthly})
                st.success(f"Monthly budget set to {format_inr(new_monthly)}!")
                st.rerun()

# --------------------------------------------------------------------------
# SCREEN 6: FRIENDS & SAMPLE UPI QR (SDD Section 5.5 & Section 9)
# --------------------------------------------------------------------------

def screen_friends():
    render_top_header()
    user_id = S.user_id
    st.markdown("### Friends & Sample UPI Pay")
    st.caption("Manage friend relationships and generate sample UPI payment deep links / QR codes.")

    # QR modal / display if active
    if S.active_friend_qr:
        af = S.active_friend_qr
        with st.container(border=True):
            c_qr1, c_qr2 = st.columns([1, 1.5])
            upi_id = af.get("sample_upi_id") or "sample.friend@okhdfcbank"
            with c_qr1:
                qr_b64 = generate_sample_qr_base64(upi_id, af["name"], 250.0)
                st.image(qr_b64, caption=f"Scan to Pay {af['name']} (₹250.00)", width=200)
            with c_qr2:
                st.markdown(f"### Sample Pay: {af['name']}")
                st.caption(f"UPI ID: `{upi_id}`")
                links = get_upi_app_deep_links(upi_id, af["name"], 250.0)
                st.markdown(
                    f"""
                    <div style="display:flex; gap:8px; margin-top:10px;">
                        <a href="{links['gpay']}" target="_blank" style="padding:8px 12px; background:#4285F4; color:#fff; border-radius:6px; text-decoration:none; font-size:12px; font-weight:600;">GPay App ↗</a>
                        <a href="{links['phonepe']}" target="_blank" style="padding:8px 12px; background:#5f259f; color:#fff; border-radius:6px; text-decoration:none; font-size:12px; font-weight:600;">PhonePe ↗</a>
                        <a href="{links['paytm']}" target="_blank" style="padding:8px 12px; background:#00b9f5; color:#fff; border-radius:6px; text-decoration:none; font-size:12px; font-weight:600;">Paytm ↗</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.caption("🔒 **Security Note:** Sample UPI payment shortcut only. Does not process real financial transactions.")
                if st.button("Close QR View", key="btn_close_qr"):
                    S.active_friend_qr = None
                    st.rerun()

    # Friends List
    friends = friend_repo.get_friends(user_id, include_archived=False)
    for f in friends:
        with st.container(border=True):
            c_f1, c_f2 = st.columns([3, 1])
            with c_f1:
                st.markdown(f"**{f['name']}**")
                st.caption(f"UPI: `{f.get('sample_upi_id') or 'Not set'}` • Note: {f.get('note') or 'None'}")
            with c_f2:
                if st.button("Generate QR", key=f"gen_qr_{f['id']}"):
                    S.active_friend_qr = f
                    st.rerun()

    # Add Friend Form
    with st.expander("＋ Add New Friend", expanded=False):
        f_name = st.text_input("Friend Name", key="new_f_name")
        f_upi = st.text_input("Sample UPI ID", key="new_f_upi", placeholder="e.g. friend@okhdfcbank")
        f_note = st.text_input("Relationship / Context Note", key="new_f_note", placeholder="e.g. Roommate, Lab Partner")
        if st.button("Add Friend", key="btn_submit_friend", type="primary"):
            if f_name:
                friend_repo.create_friend(user_id, f_name, f_upi, f_note)
                timeline_repo.append_timeline_event(user_id, "friend.created", "friend", payload={"name": f_name})
                st.success(f"Friend '{f_name}' added!")
                st.rerun()

# --------------------------------------------------------------------------
# SIDEBAR ROUTER
# --------------------------------------------------------------------------

NAV_ITEMS = [
    ("dashboard", "🏠 Dashboard"),
    ("add_expense", "＋ Add Expense"),
    ("history", "📜 History"),
    ("timeline", "⏱️ Timeline"),
    ("budgets", "🎯 Budgets"),
    ("friends", "👥 Friends"),
]

with st.sidebar:
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:8px; padding:4px 0 12px 0;">
            <div style="width:10px; height:10px; border-radius:50%; background:{MARIGOLD};"></div>
            <div style="font-family:{F_DISPLAY}; font-size:20px; font-weight:700; color:var(--text-color, #14213D);">HostelPocket</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for route_key, label in NAV_ITEMS:
        active = S.route == route_key
        if st.button(label, key=f"nav_{route_key}", type="primary" if active else "secondary", use_container_width=True):
            navigate_to(route_key)
            st.rerun()

    st.markdown(
        f"""
        <div style="margin-top:28px; padding:12px; background:var(--secondary-background-color, #EDEAE3); border-radius:8px; font-size:11px;">
            <div style="color:{GREEN}; font-weight:700;">● PRISM Active</div>
            <div style="color:#84806F; margin-top:2px;">Block Convey Telemetry</div>
            <div style="color:#84806F; margin-top:4px;">PostgreSQL Port 54321</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Render active route
ROUTER = {
    "dashboard": screen_dashboard,
    "add_expense": screen_add_expense,
    "history": screen_history,
    "timeline": screen_timeline,
    "budgets": screen_budgets,
    "friends": screen_friends,
}

if S.route in ROUTER:
    ROUTER[S.route]()
else:
    screen_dashboard()
