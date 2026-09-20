# 💸 HostelPocket — Student Hostel Personal Expense Tracker
[![Render Deployment](https://shields.io)](https://hostel-pocket-breakingbytes.onrender.com)
> **Implementation strictly adhering to the Software Design Document (SDD)**
> *Powered by Streamlit, PostgreSQL, PRISM by Block Convey, and Secure Sample UPI Deep Links*

HostelPocket is a personal expense tracker for college students living in university dorms and hostels. It provides:
- **Durable PostgreSQL Persistence**: Atomic transaction commit for expense headers, line items, evidence attachments, and timeline events on `localhost:54321`.
- **Daily & Monthly Budget Meters**: Circular status gauges with utilization indicators (`<80%` on track, `80-100%` warning, `>100%` exceeded).
- **Expandable Category Drilldown**: Drill down into exact purchased item rows contributing to each category's spending.
- **Named Friends Model**: Streamlined relationship concept (replacing roommate split ledgers) with sample UPI ID tagging.
- **Single Evidence Component**: Unified image/PDF receipt & screenshot attachment banner.
- **Sample UPI QR & Deep Links**: Generates standard `upi://pay?pa=...` payment shortcuts for Google Pay, PhonePe, and Paytm with optional prefilled amounts.
- **Hybrid AI Insights & Dismissible Reminders**: Deterministic numeric aggregates combined with Groq LLM refinement (`openai/gpt-oss-120b`).
- **Deterministic Back Navigation**: Centralized route stack navigation with deterministic `← Back` action.
- **PRISM by Block Convey Observability**: All AI and pipeline calls instrumented with official PRISM SDK.

---

## 🏛️ Architecture

```
Streamlit Page / Fragment
      │
      ▼
Use Case Services ───────────► TimelineService (append event)
      │
      ├──────────────────────► Repositories (user, expense, budget, friend, timeline, reminder, insight)
      │                               │
      │                               ▼
      │                          PostgreSQL (localhost:54321)
      │
      ├──────────────────────► Attachment Storage (metadata + files)
      │
      ├──────────────────────► AI Insight & Reminder Services (Groq + Deterministic)
      │
      └──────────────────────► UPI URI Builder ───► QR Renderer
```

---

## 🚀 Quickstart

### 1. Launch Streamlit Application
```powershell
.\venv\Scripts\streamlit.exe run hostelpocket_app.py
```
Open **http://localhost:8501** in your browser.

### 2. Environment Configuration
Copy `.env.example` to `.env` and set your credentials:
```env
GROQ_API_KEY=your_groq_api_key_here
PRISMTRACE_API_KEY=your_prismtrace_api_key_here
PRISMTRACE_PROJECT_ID=your_prismtrace_project_id_here
PRISMTRACE_HOST=https://prism-api-prod.up.railway.app
DATABASE_URL=dbname=postgres user=postgres password=BreakingBytes345 host=localhost port=54321
```
*(Note: `.env` is gitignored and will never be committed to source control).*

---

## 🧪 Requirements Compliance (SDD Traceability)

- **REQ-01 (Friends)**: Replaced roommates with lightweight, user-owned Friends entity (`friends` table).
- **REQ-02 (No SMS)**: Completely removed UPI SMS reading and permissions from Add Expense flow.
- **REQ-03 (Single Evidence)**: Merged receipt and screenshot into one reusable Evidence banner.
- **REQ-04 (Historical Items)**: Header + items normalized persistence (`expense_items`); expandable in History.
- **REQ-05 / REQ-06 (Meters & Budgets)**: Circular SVG meters for Daily and Monthly budgets with 3 status states.
- **REQ-07 (AI Insights & Reminders)**: Persisted, dismissible in-app guidance with deterministic guardrails.
- **REQ-08 (Timeline Storage)**: Append-only `timeline_events` with structured JSONB payloads and timestamps.
- **REQ-09 (Sample UPI QR)**: Safe sample UPI URI generation with app-specific deep links.
- **REQ-10 (Back Navigation)**: Centralized router with stack popping on Back click.
- **REQ-11 (Atomic Writes)**: Single database transaction commits expense, items, attachments, and timeline event before UI confirmation.
