"""Geração de QR code em SVG inline (server-side, sem JS externo — CSP-safe)."""
import io

import qrcode
import qrcode.image.svg


def qr_svg(data: str) -> str:
    """Retorna o markup <svg> do QR para embutir direto no template."""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    qr.add_data(data)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image().save(buf)
    svg = buf.getvalue().decode()
    # Remove a declaração XML para permitir embutir inline no HTML
    if svg.startswith('<?xml'):
        svg = svg.split('?>', 1)[1].lstrip()
    return svg
