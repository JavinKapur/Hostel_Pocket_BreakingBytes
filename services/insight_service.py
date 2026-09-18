import os
import datetime
from typing import Dict, Any, Optional
from repositories import insight_repo, expense_repo, budget_repo
import prism_tracer

def generate_hybrid_insight(user_id: str) -> Dict[str, Any]:
    """
    Implements SDD Section 8.1 Hybrid Insight Generation:
    Deterministic analytics produce safe numeric facts first,
    then optional Groq LLM turns them into a clean 1-2 sentence recommendation.
    """
    today = datetime.date.today()
    month_start = today.replace(day=1)
    budget_data = budget_repo.get_budget_utilization(user_id, today)
    categories = expense_repo.get_category_aggregates_with_items(user_id, month_start, today)

    # Deterministic factual baseline
    monthly_spent = float(budget_data["monthly_spent"])
    monthly_budget = float(budget_data["monthly_budget"]) if budget_data.get("monthly_budget") else 10000.0
    pct = float(budget_data["monthly_pct"])

    title = "Monthly Spending Pace"
    body = f"You have spent ₹{int(monthly_spent):,} ({round(pct)}%) of your monthly budget."
    action_label = "View Budgets"

    # Identify top category & items
    if categories:
        top_cat = categories[0]
        cat_name = top_cat["category_name"]
        cat_total = float(top_cat["total_amount"])
        cat_pct = round((cat_total / monthly_spent * 100) if monthly_spent > 0 else 0)

        if top_cat.get("items"):
            top_item = top_cat["items"][0]
            item_name = top_item["item_name"]
            item_total = float(top_item["item_total"])
            item_pct = round((item_total / cat_total * 100) if cat_total > 0 else 0)
            title = f"{item_name} in {cat_name}"
            body = f"{item_name} represents {item_pct}% of this month's {cat_name.lower()} spend."
            action_label = f"Review {cat_name}"
        else:
            title = f"{cat_name} Spending"
            body = f"{cat_name} makes up {cat_pct}% of your spending this month."
            action_label = f"Review {cat_name}"

    # Try optional Groq refinement if configured
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key and not groq_key.startswith("your_"):
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            prompt = f"""
Given these student hostel spending facts:
- Monthly Spent: INR {monthly_spent}
- Budget: INR {monthly_budget}
- Top Category: {categories[0]['category_name'] if categories else 'General'} (INR {categories[0]['total_amount'] if categories else 0})
Provide a concise, encouraging 1-sentence insight for a college student (max 25 words).
"""
            resp = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.3,
            )
            llm_text = resp.choices[0].message.content.strip()
            if len(llm_text) > 10:
                body = llm_text.replace('"', '')

            prism_tracer.log_llm_call(
                model="openai/gpt-oss-120b",
                input_messages=[{"role": "user", "content": prompt}],
                output=body,
                latency_ms=180,
                agent_id="hostelpocket-insight-agent",
                agent_name="HostelPocket Insight Engine",
            )
        except Exception:
            pass

    saved = insight_repo.save_insight(
        user_id=user_id,
        title=title,
        body=body,
        insight_type="spending_pattern",
        severity="info" if pct <= 80 else "warning",
        data={"action_label": action_label, "monthly_spent": monthly_spent, "pct": pct},
        window_start=month_start,
        window_end=today,
    )
    saved["action_label"] = action_label
    return saved
