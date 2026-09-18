import streamlit as st
from utils.money import format_inr

NAVY = "#14213D"
MARIGOLD = "#E8A33D"
GREEN = "#3A6B52"
BRICK = "#B23A2E"
GREY = "#84806F"
PAPER_DIM = "#EDEAE3"

def render_circular_budget_meter(title: str, spent: float, budget: float, period_label: str = "") -> str:
    """
    Renders an SVG circular budget meter with states at <80% (green), 80-100% (marigold), and >100% (brick).
    Complies with SDD Section 5.1 & FR-10.
    """
    if budget is None or budget <= 0:
        return f"""
        <div style="background:var(--secondary-background-color, #EDEAE3); border-radius:14px; padding:20px; text-align:center; border:1px dashed #84806F;">
            <div style="font-size:12px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.06em;">{title}</div>
            <div style="font-size:14px; color:#14213D; margin:10px 0;">No active budget set</div>
            <div style="font-size:12px; color:#84806F;">Set a budget to track spending limits.</div>
        </div>
        """

    pct = (spent / budget) * 100
    remaining = budget - spent

    # Determine status color per SDD FR-10
    if pct > 100:
        stroke_color = BRICK
        status_text = "Over Budget"
    elif pct >= 80:
        stroke_color = MARIGOLD
        status_text = "Approaching Limit"
    else:
        stroke_color = GREEN
        status_text = "On Track"

    # SVG circular path calculation
    # Circumference for radius=42 is ~264
    circumference = 264.0
    dash_offset = circumference - (min(pct, 100) / 100.0 * circumference)

    return f"""
    <div style="background:var(--secondary-background-color, #F7F5F1); border:1px solid #EDEAE3; border-radius:14px; padding:20px 16px; text-align:center; box-shadow:0 2px 10px rgba(0,0,0,0.04);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span style="font-size:11.5px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.06em;">{title}</span>
            <span style="font-size:11px; font-weight:700; color:{stroke_color}; background:{stroke_color}22; padding:2px 8px; border-radius:12px;">{status_text}</span>
        </div>
        <div style="position:relative; width:110px; height:110px; margin:0 auto;">
            <svg width="110" height="110" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="transparent" stroke="#E2DFD8" stroke-width="9" />
                <circle cx="50" cy="50" r="42" fill="transparent" stroke="{stroke_color}" stroke-width="9"
                        stroke-dasharray="{circumference}" stroke-dashoffset="{dash_offset}"
                        stroke-linecap="round" transform="rotate(-90 50 50)" />
            </svg>
            <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); text-align:center;">
                <div style="font-family:'Space Grotesk', sans-serif; font-size:19px; font-weight:700; color:var(--text-color, #14213D);">{round(pct)}%</div>
            </div>
        </div>
        <div style="margin-top:10px;">
            <div style="font-family:'IBM Plex Mono', monospace; font-size:15px; font-weight:600; color:var(--text-color, #14213D);">
                {format_inr(spent)} <span style="font-size:12px; color:#84806F; font-weight:400;">/ {format_inr(budget)}</span>
            </div>
            <div style="font-size:12px; color:{GREEN if remaining >= 0 else BRICK}; font-weight:500; margin-top:3px;">
                {format_inr(abs(remaining))} {'remaining' if remaining >= 0 else 'overspent'}
            </div>
        </div>
    </div>
    """

def render_evidence_banner():
    """
    Renders a unified Evidence attachment banner with image/PDF preview per REQ-03 & FR-04.
    """
    st.markdown('<div style="font-size:12px; font-weight:700; text-transform:uppercase; color:#84806F; letter-spacing:0.06em; margin-bottom:4px;">Receipt / Screenshot Evidence</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Upload bill photo, delivery order screenshot, or PDF receipt",
        type=["png", "jpg", "jpeg", "pdf"],
        key="evidence_uploader",
        help="Upload single or multiple evidence files.",
    )
    return uploaded
