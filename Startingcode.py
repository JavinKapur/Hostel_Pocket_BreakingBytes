import os
import json
import time
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import psycopg2
from dotenv import load_dotenv

# Internal modular services
import prism_tracer
import db_manager
import upi_engine
import ai_services

load_dotenv()

app = FastAPI(
    title="HostelPocket API — Powered by PRISM by Block Convey",
    description="Backend API for HostelPocket student expense management with PRISM tracing, PostgreSQL sync, and UPI payments.",
    version="2.0.0",
)


# --------------------------------------------------------------------------
# REQUEST / RESPONSE SCHEMAS
# --------------------------------------------------------------------------

class ExpenseTextRequest(BaseModel):
    text_prompt: str
    payer_name: str = "Javin"
    group_name: str = "Room 304"


class SettleRequest(BaseModel):
    from_user: str
    to_user: str


class UpiGenerateRequest(BaseModel):
    user_name: str
    amount: float
    note: Optional[str] = "HostelPocket Split"


# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------

@app.get("/")
def home():
    return {
        "status": "Online",
        "service": "HostelPocket Backend",
        "prism_telemetry": "Active",
        "prism_project_id": prism_tracer.PRISM_PROJECT_ID,
        "database": "PostgreSQL Active",
    }


@app.get("/db-test")
def test_db():
    try:
        conn = db_manager.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        db_version = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {
            "database_status": "Connected Successfully!",
            "version": db_version,
            "room_users": [u["name"] for u in db_manager.get_all_users()],
        }
    except Exception as e:
        return {"database_status": "Connection Failed", "error": str(e)}


@app.post("/parse-expense")
def parse_and_save_expense(request: ExpenseTextRequest):
    """
    Parses natural language expense text, saves to PostgreSQL, and records
    traces to PRISM by Block Convey.
    """
    try:
        # 1. AI Parsing with Groq LLM
        parsed = ai_services.parse_expense_text(request.text_prompt)

        # 2. Build splits list
        splits = []
        for roommate in parsed["participants"]:
            splits.append({
                "friend_name": roommate,
                "amount_owed": parsed["per"],
            })

        # 3. Persist to PostgreSQL database
        expense_id = db_manager.add_expense_with_splits(
            paid_by_name=request.payer_name,
            total_amount=parsed["amount"],
            description=f"{parsed['merchant']} ({parsed['category']})",
            category=parsed["category"],
            splits=splits,
            group_name=request.group_name,
        )

        # 4. Generate UPI QR Code and deep links for the payer to request payments
        payer_upi = upi_engine.get_user_upi_id(request.payer_name)
        upi_data = {
            "vpa": payer_upi,
            "per_person_amount": parsed["per"],
            "upi_uri": upi_engine.create_upi_uri(payer_upi, request.payer_name, parsed["per"], f"{parsed['merchant']} Split"),
            "app_deep_links": upi_engine.get_app_deep_links(payer_upi, request.payer_name, parsed["per"], f"{parsed['merchant']} Split"),
            "qr_code_base64": upi_engine.generate_upi_qr_base64(payer_upi, request.payer_name, parsed["per"], f"{parsed['merchant']} Split"),
        }

        return {
            "status": "Success",
            "message": "PRISM trace logged and PostgreSQL synchronized successfully!",
            "expense_id": expense_id,
            "parsed_data": parsed,
            "splits": splits,
            "upi_settlement": upi_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline Processing Error: {str(e)}")


@app.post("/scan-receipt")
async def scan_receipt_endpoint(
    file: UploadFile = File(...),
    payer_name: str = Form("Javin"),
    group_name: str = Form("Room 304"),
):
    """
    Scans a bill/receipt image, runs Vision OCR on Groq, logs trace to PRISM,
    and saves the itemized split to PostgreSQL.
    """
    try:
        content = await file.read()
        parsed = ai_services.scan_receipt_image(content)

        splits = []
        for roommate in parsed["participants"]:
            splits.append({
                "friend_name": roommate,
                "amount_owed": parsed["per"],
            })

        expense_id = db_manager.add_expense_with_splits(
            paid_by_name=payer_name,
            total_amount=parsed["amount"],
            description=f"{parsed['merchant']} (Bill Scan)",
            category=parsed["category"],
            splits=splits,
            group_name=group_name,
        )

        return {
            "status": "Success",
            "expense_id": expense_id,
            "parsed_data": parsed,
            "splits": splits,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Receipt Scan Error: {str(e)}")


@app.get("/balances")
def get_balances(user_name: str = "Javin"):
    """Fetches real-time room balances from PostgreSQL."""
    try:
        balances = db_manager.get_balances_for_user(user_name)
        recent = db_manager.get_recent_expenses(5)
        return {
            "user": user_name,
            "balances": balances,
            "recent_expenses": recent,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/settle")
def settle_debt(request: SettleRequest):
    """Settles outstanding balance between two users in the database."""
    success = db_manager.settle_debt_in_db(request.from_user, request.to_user)
    if success:
        return {"status": "Success", "message": f"Settled balances between {request.from_user} and {request.to_user}"}
    return {"status": "Failed", "message": "Could not settle balance."}


@app.post("/generate-upi-qr")
def generate_upi_qr(request: UpiGenerateRequest):
    """Generates an NPCI-compliant UPI deep link and scannable QR code."""
    vpa = upi_engine.get_user_upi_id(request.user_name)
    qr_b64 = upi_engine.generate_upi_qr_base64(vpa, request.user_name, request.amount, request.note)
    links = upi_engine.get_app_deep_links(vpa, request.user_name, request.amount, request.note)
    return {
        "user": request.user_name,
        "vpa": vpa,
        "amount": request.amount,
        "deep_links": links,
        "qr_code_base64": qr_b64,
    }


@app.get("/prism-telemetry")
def get_prism_telemetry():
    """Returns the most recent traces sent to PRISM by Block Convey."""
    return {
        "status": "Active",
        "traces": prism_tracer.get_telemetry_history(),
    }
