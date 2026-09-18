import urllib.parse
import io
import base64
import qrcode
from PIL import Image

# Known dummy UPI IDs for room members
ROOM_UPI_REGISTRY = {
    "Rahul": "rahul.sharma@okhdfcbank",
    "Arjun": "arjun.verma@icici",
    "Karan": "karan98@paytm",
    "Javin": "javin@okaxis",
    "Room 304": "room304hostel@okhdfcbank",
}


def get_user_upi_id(user_name: str) -> str:
    """Returns the registered or inferred UPI ID for a user."""
    cleaned = user_name.strip()
    return ROOM_UPI_REGISTRY.get(cleaned, f"{cleaned.lower().replace(' ', '')}@upi")


def create_upi_uri(
    vpa: str,
    name: str,
    amount: float,
    note: str = "HostelPocket Split",
) -> str:
    """
    Constructs a standard NPCI compliant UPI URL:
    upi://pay?pa={vpa}&pn={name}&am={amount:.2f}&cu=INR&tn={note}
    """
    params = {
        "pa": vpa,
        "pn": name,
        "am": f"{amount:.2f}",
        "cu": "INR",
        "tn": note,
    }
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"upi://pay?{query_string}"


def get_app_deep_links(vpa: str, name: str, amount: float, note: str = "HostelPocket Split") -> dict:
    """
    Returns app-specific intent schemes for major Indian UPI apps:
    Google Pay, PhonePe, Paytm, and BHIM/Generic.
    """
    standard_uri = create_upi_uri(vpa, name, amount, note)
    query_string = standard_uri.replace("upi://pay?", "")

    return {
        "standard": standard_uri,
        "gpay": f"gpay://upi/pay?{query_string}",
        "phonepe": f"phonepe://pay?{query_string}",
        "paytm": f"paytmmp://pay?{query_string}",
        "bhim": f"upi://pay?{query_string}",
    }


def generate_upi_qr_image(
    vpa: str,
    name: str,
    amount: float,
    note: str = "HostelPocket Split",
    box_size: int = 7,
    border: int = 2,
) -> Image.Image:
    """Generates a PIL Image of the UPI QR code containing prefilled payee and amount."""
    upi_uri = create_upi_uri(vpa, name, amount, note)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(upi_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#14213D", back_color="#FFFFFF")
    return img.convert("RGB")


def generate_upi_qr_base64(
    vpa: str,
    name: str,
    amount: float,
    note: str = "HostelPocket Split",
) -> str:
    """Returns a base64 encoded data URI for embedding in HTML/markdown."""
    img = generate_upi_qr_image(vpa, name, amount, note)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"


def render_upi_payment_card_html(
    vpa: str,
    name: str,
    amount: float,
    note: str = "HostelPocket Split",
) -> str:
    """Generates a modern, responsive HTML card with QR code, deep links, and copy actions."""
    qr_b64 = generate_upi_qr_base64(vpa, name, amount, note)
    links = get_app_deep_links(vpa, name, amount, note)

    html = f"""
    <div style="background:#FFFFFF; border:1px solid #EDEAE3; border-radius:14px; padding:20px; box-shadow:0 4px 16px rgba(0,0,0,0.06); max-width:380px; margin:10px auto; text-align:center; font-family:'IBM Plex Sans', sans-serif;">
        <div style="font-size:12px; font-weight:700; color:#84806F; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:4px;">UPI Fast Pay</div>
        <div style="font-size:26px; font-weight:700; color:#14213D; font-family:'IBM Plex Mono', monospace;">₹{amount:,.2f}</div>
        <div style="font-size:13px; color:#14213D; margin-top:2px;">To: <strong>{name}</strong> (<span style="color:#84806F;">{vpa}</span>)</div>
        
        <div style="margin:16px auto; width:180px; height:180px; padding:8px; background:#FFFFFF; border-radius:10px; border:1px solid #EDEAE3; box-shadow:0 2px 8px rgba(0,0,0,0.04);">
            <img src="{qr_b64}" alt="Scan to Pay via UPI" style="width:100%; height:100%; object-fit:contain;" />
        </div>
        <div style="font-size:11.5px; color:#84806F; margin-bottom:14px;">Scan with <strong>Google Pay</strong>, <strong>PhonePe</strong>, or <strong>Paytm</strong></div>
        
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px;">
            <a href="{links['gpay']}" target="_blank" style="display:block; text-decoration:none; padding:9px 6px; background:#4285F4; color:#FFFFFF; border-radius:8px; font-size:12px; font-weight:600;">
                GPay App ↗
            </a>
            <a href="{links['phonepe']}" target="_blank" style="display:block; text-decoration:none; padding:9px 6px; background:#5f259f; color:#FFFFFF; border-radius:8px; font-size:12px; font-weight:600;">
                PhonePe ↗
            </a>
            <a href="{links['paytm']}" target="_blank" style="display:block; text-decoration:none; padding:9px 6px; background:#00b9f5; color:#FFFFFF; border-radius:8px; font-size:12px; font-weight:600;">
                Paytm ↗
            </a>
            <a href="{links['standard']}" target="_blank" style="display:block; text-decoration:none; padding:9px 6px; background:#14213D; color:#FFFFFF; border-radius:8px; font-size:12px; font-weight:600;">
                Any UPI App ↗
            </a>
        </div>
        
        <div style="font-size:11px; color:#84806F; border-top:1px dashed #EDEAE3; padding-top:8px;">
            Note: <em>{note}</em>
        </div>
    </div>
    """
    return html
