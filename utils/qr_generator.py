import qrcode
import os
from io import BytesIO
import base64

def generate_qr_code(data: str) -> str:
    """Генерирует QR-код и возвращает его в формате base64"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def generate_book_qr(book_id: int, copy_id: int) -> str:
    """Генерирует QR-код для конкретного экземпляра книги"""
    data = f"book:{book_id}:{copy_id}"
    return generate_qr_code(data) 