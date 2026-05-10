"""CSV export functionality for orders."""
import csv
import io
from typing import List

from models import Order


async def generate_orders_csv(orders: List[Order], lang: str) -> io.BytesIO:
    """
    Generate a CSV file with order data.

    Args:
        orders: List of Order objects to export
        lang: Language code for localized headers

    Returns:
        BytesIO object containing CSV data
    """
    # Use StringIO for CSV writing
    text_output = io.StringIO()

    # Define CSV headers
    headers = [
        "order_id",
        "user_id",
        "username",
        "status",
        "full_name",
        "contact_phone",
        "delivery_address",
        "payment_method",
        "delivery_notes",
        "order_text",
        "created_at",
        "sent_at",
        "received_at",
    ]

    # Write CSV content
    writer = csv.DictWriter(text_output, fieldnames=headers)
    writer.writeheader()

    for order in orders:
        row = {
            "order_id": order.id,
            "user_id": order.user_id,
            "username": order.username or "",
            "status": order.status or "",
            "full_name": order.full_name or "",
            "contact_phone": order.contact_phone or "",
            "delivery_address": order.delivery_address or "",
            "payment_method": order.payment_method or "",
            "delivery_notes": order.delivery_notes or "",
            "order_text": order.order_text or "",
            "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S") if order.created_at else "",
            "sent_at": order.sent_at.strftime("%Y-%m-%d %H:%M:%S") if order.sent_at else "",
            "received_at": order.received_at.strftime("%Y-%m-%d %H:%M:%S") if order.received_at else "",
        }
        writer.writerow(row)

    # Add UTF-8 BOM so Excel on Windows auto-detects Unicode correctly.
    csv_bytes = io.BytesIO(text_output.getvalue().encode("utf-8-sig"))
    return csv_bytes

