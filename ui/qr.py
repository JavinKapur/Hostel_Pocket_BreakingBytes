import urllib.parse
import io
import base64
import re
import qrcode
from PIL import Image

def validate_sample_upi_id(upi_id: str) -> bool:
    """Validates basic format of sample UPI ID (e.g. user@bank)."""
    if not upi_id:
        return False
    return bool(re.match(r"^[\w\.\-]+@[\w\-]+$", upi_id.strip()))

def build_sample_upi_uri(sample_upi_id: str, friend_name: str, amount: float = None) -> str:
    """
    Constructs an NPCI-compliant sample UPI URI per SDD Section 9.1:
    upi://pay?pa=<sample-upi-id>&pn=<url-encoded-friend-name>&am=<amount>&cu=INR
    """
    clean_upi = sample_upi_id.strip()
    encoded_name = urllib.parse.quote(friend_name.strip())
    uri = f"upi://pay?pa={clean_upi}&pn={encoded_name}"
    if amount is not None and amount > 0:
        uri += f"&am={amount:.2f}"
    uri += "&cu=INR"
    return uri

def generate_sample_qr_base64(sample_upi_id: str, friend_name: str, amount: float = None) -> str:
    """Generates a high-contrast sample UPI QR code encoded as a base64 PNG data URL."""
    uri = build_sample_upi_uri(sample_upi_id, friend_name, amount)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#14213D", back_color="#FFFFFF").convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def get_upi_app_deep_links(sample_upi_id: str, friend_name: str, amount: float = None) -> dict:
    """Returns app-specific intent schemes for mobile test shortcuts."""
    uri = build_sample_upi_uri(sample_upi_id, friend_name, amount)
    params = uri.replace("upi://pay?", "")
    return {
        "standard": uri,
        "gpay": f"gpay://upi/pay?{params}",
        "phonepe": f"phonepe://pay?{params}",
        "paytm": f"paytmmp://pay?{params}",
    }
