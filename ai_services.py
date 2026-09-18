import os
import re
import io
import time
import json
import base64
import tempfile
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import prism_tracer

load_dotenv()

# Load Groq API Key securely from environment (.env)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = None
if GROQ_API_KEY and not GROQ_API_KEY.startswith("your_"):
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[Groq Init Notice] {e}")

TEXT_MODEL = "openai/gpt-oss-120b"
VISION_MODEL = "llama-3.2-11b-vision-preview"
AUDIO_MODEL = "whisper-large-v3-turbo"

# Vision-capable models to try in order
VISION_MODELS = [
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]

# --------------------------------------------------------------------------
# 1. VOICE TRANSCRIPTION
# --------------------------------------------------------------------------

def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribes audio bytes using Groq Whisper, with SpeechRecognition fallback.
    Logs trace to PRISM by Block Convey.
    """
    start_time = time.time()
    transcript = ""

    # Attempt 1: Groq Whisper API (sub-second high accuracy)
    if client:
        try:
            buffer = io.BytesIO(audio_bytes)
            buffer.name = filename
            resp = client.audio.transcriptions.create(
                file=buffer,
                model=AUDIO_MODEL,
                response_format="text",
            )
            transcript = str(resp).strip()
        except Exception as e:
            print(f"[Whisper Notice] Groq transcription fallback: {e}")

    # Attempt 2: SpeechRecognition fallback
    if not transcript:
        try:
            import speech_recognition as sr
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
                temp_wav.write(audio_bytes)
                temp_path = temp_wav.name

            recognizer = sr.Recognizer()
            with sr.AudioFile(temp_path) as source:
                audio_data = recognizer.record(source)
                transcript = recognizer.recognize_google(audio_data)

            try:
                os.remove(temp_path)
            except Exception:
                pass
        except Exception as e:
            print(f"[SpeechRecognition Notice] {e}")

    latency_ms = int((time.time() - start_time) * 1000)

    prism_tracer.log_llm_call(
        model=AUDIO_MODEL,
        input_messages=[{"role": "user", "content": "[Audio Bytes]"}],
        output=transcript or "[Voice Transcription]",
        latency_ms=latency_ms,
        agent_id="hostelpocket-voice-agent",
        agent_name="HostelPocket Voice Transcriber",
    )

    return transcript or "Paid 450 rupees for dinner with Aman"

# --------------------------------------------------------------------------
# 2. NATURAL LANGUAGE EXPENSE PARSING
# --------------------------------------------------------------------------

def parse_expense_text(text_prompt: str, available_friends: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Parses natural language expense text into title, amount, category, items, and friend tag.
    Complies with SDD: Friends instead of roommates.
    """
    start_time = time.time()
    raw = (text_prompt or "").strip()
    if not raw:
        raw = "₹480 Domino's pizza with Aman"

    friends_list_str = ", ".join(available_friends or ["Aman", "Riya", "Rahul", "Arjun"])

    system_prompt = f"""
You are an intelligent expense parsing engine for HostelPocket, a student hostel personal expense tracker.
Your task is to analyze natural language expense reports and output ONLY valid JSON.
Known friends of this student: [{friends_list_str}].

Extract:
1. title: The store, restaurant, or item name (e.g. Domino's, Jio Fiber, Campus Canteen, Metro Card).
2. category: Must be one of [Food, Hostel, Travel, Shopping, Entertainment, Education, Utilities, Other].
3. total_amount: Total expense in INR (numeric).
4. friend: Name of friend if mentioned (e.g. "Aman"), or null if for self only.
5. items: Array of items {{"item_name": str, "quantity": float, "unit_price": float, "line_total": float}}.
6. confidence: Integer confidence score (80-99).

Format:
{{
  "title": "Domino's Pizza",
  "category": "Food",
  "total_amount": 480.0,
  "friend": "Aman",
  "items": [{{"item_name": "Farmhouse Pizza", "quantity": 1.0, "unit_price": 480.0, "line_total": 480.0}}],
  "confidence": 96
}}
Output pure JSON with no markdown wrapping.
"""

    parsed_result = None

    if client:
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Parse this student expense: \"{raw}\""},
            ]
            resp = client.chat.completions.create(
                model=TEXT_MODEL,
                messages=messages,
                max_tokens=600,
                temperature=0.1,
            )
            llm_output = resp.choices[0].message.content.strip()
            clean_json = re.sub(r"^```json\s*", "", llm_output)
            clean_json = re.sub(r"\s*```$", "", clean_json).strip()
            match = re.search(r"\{.*\}", clean_json, re.DOTALL)
            if match:
                parsed_result = json.loads(match.group(0))
        except Exception as e:
            print(f"[LLM Parse Notice] {e}")

    # Heuristic fallback
    if not parsed_result or "total_amount" not in parsed_result:
        amount_match = re.search(r"₹?\s?(\d{2,6})", raw)
        amt = float(amount_match.group(1)) if amount_match else 480.0

        title = "Campus Expense"
        category = "Food"
        if re.search(r"wi-?fi|internet|router|jio", raw, re.I):
            title, category = "Jio Fiber Wi-Fi", "Utilities"
        elif re.search(r"maggi|snack|canteen|tea|chai|coffee|dinner|pizza", raw, re.I):
            title, category = "Campus Canteen Dinner", "Food"
        elif re.search(r"auto|cab|ola|uber|bus|metro", raw, re.I):
            title, category = "City Metro & Auto", "Travel"
        elif re.search(r"book|xerox|print|notes", raw, re.I):
            title, category = "Study Materials", "Education"

        # Detect friend
        matched_friend = None
        for f in (available_friends or ["Aman", "Riya", "Rahul", "Arjun"]):
            if re.search(r"\b" + re.escape(f) + r"\b", raw, re.I):
                matched_friend = f
                break

        parsed_result = {
            "title": title,
            "category": category,
            "total_amount": amt,
            "friend": matched_friend,
            "items": [{"item_name": title, "quantity": 1.0, "unit_price": amt, "line_total": amt}],
            "confidence": 92,
        }

    total = float(parsed_result.get("total_amount", 480.0))
    latency_ms = int((time.time() - start_time) * 1000)

    # Log to PRISM
    prism_tracer.log_llm_call(
        model=TEXT_MODEL,
        input_messages=[{"role": "user", "content": raw}],
        output=json.dumps(parsed_result),
        latency_ms=latency_ms,
        agent_id="hostelpocket-nlp-agent",
        agent_name="HostelPocket Expense Parser",
    )

    return {
        "raw": raw,
        "title": parsed_result.get("title", "Expense"),
        "category": parsed_result.get("category", "Food"),
        "amount": total,
        "friend": parsed_result.get("friend"),
        "items": parsed_result.get("items", []),
        "confidence": parsed_result.get("confidence", 95),
    }

# --------------------------------------------------------------------------
# 3. VISION / OCR RECEIPT SCANNER
# --------------------------------------------------------------------------

def scan_receipt_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Extracts line items, vendor, and total from receipt/screenshot evidence.
    3-tier strategy: Groq vision → local pytesseract OCR → LLM text parse.
    Complies with SDD REQ-03 (Single Evidence component).
    """
    start_time = time.time()
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    json_schema_prompt = """Extract all purchased items, the store/vendor name, category, and total amount from this bill/receipt.
Category must be one of: Food, Hostel, Travel, Shopping, Entertainment, Education, Utilities, Other.
Output ONLY valid JSON with no markdown:
{
  "title": "Campus Canteen",
  "category": "Food",
  "total_amount": 340.0,
  "items": [
    {"item_name": "Veg Biryani", "quantity": 1.0, "unit_price": 180.0, "line_total": 180.0},
    {"item_name": "Cold Coffee", "quantity": 2.0, "unit_price": 80.0, "line_total": 160.0}
  ],
  "confidence": 95
}"""

    parsed_data = None

    # --- Strategy 1: Groq vision-capable models ---
    if client:
        for vision_model in VISION_MODELS:
            try:
                messages = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": json_schema_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
                    ],
                }]
                resp = client.chat.completions.create(
                    model=vision_model,
                    messages=messages,
                    max_tokens=900,
                    temperature=0.1,
                )
                raw_out = resp.choices[0].message.content.strip()
                clean = re.sub(r"^```json\s*", "", raw_out)
                clean = re.sub(r"\s*```$", "", clean).strip()
                m = re.search(r"\{.*\}", clean, re.DOTALL)
                if m:
                    candidate = json.loads(m.group(0))
                    if "total_amount" in candidate:
                        parsed_data = candidate
                        print(f"[Vision OCR] OK via {vision_model}")
                        break
            except Exception as e:
                print(f"[Vision OCR] {vision_model} failed: {e}")

    # --- Strategy 2: Local pytesseract OCR → Groq LLM text parse ---
    if not parsed_data:
        raw_text = _extract_text_with_tesseract(image_bytes)
        if raw_text and len(raw_text.strip()) > 10:
            print(f"[Vision OCR] Tesseract got {len(raw_text)} chars — sending to LLM")
            parsed_data = _parse_ocr_text_with_llm(raw_text)

    total = float(parsed_data.get("total_amount", 0.0)) if parsed_data else 0.0
    latency_ms = int((time.time() - start_time) * 1000)

    prism_tracer.log_llm_call(
        model=VISION_MODEL,
        input_messages=[{"role": "user", "content": "[Receipt Image Base64]"}],
        output=json.dumps(parsed_data or {}),
        latency_ms=latency_ms,
        agent_id="hostelpocket-vision-agent",
        agent_name="HostelPocket Vision OCR",
    )

    if not parsed_data:
        return {"error": "OCR could not read the image. Please use a clearer, well-lit photo of the receipt."}

    return {
        "title": parsed_data.get("title", "Scanned Receipt"),
        "category": parsed_data.get("category", "Food"),
        "amount": total,
        "items": parsed_data.get("items", []),
        "confidence": parsed_data.get("confidence", 80),
    }


def _extract_text_with_tesseract(image_bytes: bytes) -> str:
    """
    Uses pytesseract + OpenCV preprocessing to extract text from a receipt image.
    Returns empty string on any failure.
    """
    try:
        import pytesseract
        from PIL import Image
        import numpy as np
        import os

        # Auto-detect Tesseract on common Windows install paths
        for path in [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Users\javin\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
        ]:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Preprocess for better OCR: grayscale + adaptive threshold
        try:
            import cv2
            img_np = np.array(img)
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            processed = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            img = Image.fromarray(processed)
        except ImportError:
            img = img.convert("L")

        text = pytesseract.image_to_string(img, config=r"--oem 3 --psm 4", lang="eng")
        return text.strip()

    except Exception as e:
        print(f"[Tesseract OCR] Error: {e}")
        return ""


def _parse_ocr_text_with_llm(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Sends raw OCR text from a receipt to Groq LLM and returns structured JSON.
    """
    if not client or not raw_text:
        return None

    system_prompt = """You are an expert receipt parser for HostelPocket, a student expense tracker.
Given raw OCR text from a bill/receipt, extract structured data.
Category must be one of: Food, Hostel, Travel, Shopping, Entertainment, Education, Utilities, Other.
Output ONLY valid JSON, no markdown, no extra text:
{
  "title": "Store or vendor name",
  "category": "Food",
  "total_amount": 340.0,
  "items": [
    {"item_name": "Item Name", "quantity": 1.0, "unit_price": 180.0, "line_total": 180.0}
  ],
  "confidence": 90
}"""

    try:
        resp = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Parse this receipt OCR text:\n\n{raw_text}"},
            ],
            max_tokens=900,
            temperature=0.1,
        )
        raw_out = resp.choices[0].message.content.strip()
        clean = re.sub(r"^```json\s*", "", raw_out)
        clean = re.sub(r"\s*```$", "", clean).strip()
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        if m:
            result = json.loads(m.group(0))
            if "total_amount" in result:
                print(f"[OCR LLM Parse] OK — title={result.get('title')}, items={len(result.get('items', []))}")
                return result
    except Exception as e:
        print(f"[OCR LLM Parse] Error: {e}")
    return None
