"""
Google Sheets integration — read/write spreadsheets, append rows, create sheets.

GOOGLE_SHEETS_ID env var: default spreadsheet ID to use.
Service account must be shared on the spreadsheet (Editor access).
"""

import os
from typing import Optional, Any

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_SHEET_ID = lambda: os.getenv("GOOGLE_SHEETS_ID", "")


def _get_service():
    from integrations.google import get_credentials
    from googleapiclient.discovery import build
    creds = get_credentials(SCOPES)
    if not creds:
        return None
    try:
        return build("sheets", "v4", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"[SHEETS] build error: {e}")
        return None


def read_range(range_: str, sheet_id: Optional[str] = None) -> list[list]:
    """Read a range like 'Sheet1!A1:D10'. Returns list of rows."""
    svc = _get_service()
    if not svc:
        return []
    sid = sheet_id or DEFAULT_SHEET_ID()
    if not sid:
        return []
    try:
        result = svc.spreadsheets().values().get(
            spreadsheetId=sid, range=range_
        ).execute()
        return result.get("values", [])
    except Exception as e:
        print(f"[SHEETS] read_range error: {e}")
        return []


def write_range(range_: str, values: list[list], sheet_id: Optional[str] = None) -> bool:
    """Write values to a range. Returns True on success."""
    svc = _get_service()
    if not svc:
        return False
    sid = sheet_id or DEFAULT_SHEET_ID()
    if not sid:
        return False
    try:
        svc.spreadsheets().values().update(
            spreadsheetId=sid,
            range=range_,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()
        return True
    except Exception as e:
        print(f"[SHEETS] write_range error: {e}")
        return False


def append_rows(sheet_name: str, rows: list[list], sheet_id: Optional[str] = None) -> bool:
    """Append rows to the end of a sheet."""
    svc = _get_service()
    if not svc:
        return False
    sid = sheet_id or DEFAULT_SHEET_ID()
    if not sid:
        return False
    try:
        svc.spreadsheets().values().append(
            spreadsheetId=sid,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
        return True
    except Exception as e:
        print(f"[SHEETS] append error: {e}")
        return False


def create_spreadsheet(title: str) -> Optional[str]:
    """Create a new Google Spreadsheet. Returns the sheet ID."""
    svc = _get_service()
    if not svc:
        return None
    try:
        result = svc.spreadsheets().create(
            body={"properties": {"title": title}}
        ).execute()
        return result.get("spreadsheetId")
    except Exception as e:
        print(f"[SHEETS] create error: {e}")
        return None


def log_sale_to_sheet(sale: dict, sheet_id: Optional[str] = None) -> bool:
    """Append a sale record to a 'Sales' sheet tab."""
    from datetime import datetime
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        sale.get("title", ""),
        sale.get("amount", 0),
        sale.get("niche", ""),
        sale.get("product_type", ""),
        sale.get("listing_id", ""),
        sale.get("source", "etsy"),
    ]
    return append_rows("Sales", [row], sheet_id)


def log_expense_to_sheet(expense: dict, sheet_id: Optional[str] = None) -> bool:
    """Append an expense to an 'Expenses' sheet tab."""
    from datetime import datetime
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        expense.get("description", ""),
        expense.get("amount", 0),
        expense.get("category", ""),
    ]
    return append_rows("Expenses", [row], sheet_id)


def get_sheet_summary(sheet_id: Optional[str] = None) -> dict:
    """Read key financial summary from a 'Summary' tab."""
    data = read_range("Summary!A1:B20", sheet_id)
    result = {}
    for row in data:
        if len(row) >= 2:
            result[row[0]] = row[1]
    return result


def sheets_available() -> bool:
    from integrations.google import has_any_credentials
    sid = DEFAULT_SHEET_ID()
    return has_any_credentials() and bool(sid)
