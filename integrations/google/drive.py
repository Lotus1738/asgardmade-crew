"""
Google Drive integration — list files, upload, download, create folders.

Service account needs Drive access. Share a folder with the SA email, or enable
domain-wide delegation. GOOGLE_DRIVE_ROOT_FOLDER_ID env var sets the root folder.
"""

import os
import io
from typing import Optional

SCOPES = ["https://www.googleapis.com/auth/drive"]
ROOT_FOLDER = lambda: os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "root")

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".csv": "text/csv",
    ".json": "application/json",
    ".py": "text/x-python",
}


def _get_service():
    from integrations.google import get_credentials
    from googleapiclient.discovery import build
    creds = get_credentials(SCOPES)
    if not creds:
        return None
    try:
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"[DRIVE] build error: {e}")
        return None


def list_files(folder_id: Optional[str] = None, limit: int = 20, query: str = "") -> list[dict]:
    """List files in a Drive folder."""
    svc = _get_service()
    if not svc:
        return []
    folder = folder_id or ROOT_FOLDER()
    try:
        q = f"'{folder}' in parents and trashed=false"
        if query:
            q += f" and name contains '{query}'"
        result = svc.files().list(
            q=q,
            pageSize=limit,
            fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
        ).execute()
        return _format_files(result.get("files", []))
    except Exception as e:
        print(f"[DRIVE] list_files error: {e}")
        return []


def search_files(query: str, limit: int = 10) -> list[dict]:
    """Full-text search across Drive."""
    svc = _get_service()
    if not svc:
        return []
    try:
        result = svc.files().list(
            q=f"fullText contains '{query}' and trashed=false",
            pageSize=limit,
            fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
        ).execute()
        return _format_files(result.get("files", []))
    except Exception as e:
        print(f"[DRIVE] search error: {e}")
        return []


def upload_file(name: str, content: bytes, mime_type: str = "text/plain",
                folder_id: Optional[str] = None) -> Optional[dict]:
    """Upload a file to Drive. Returns file metadata dict."""
    svc = _get_service()
    if not svc:
        return None
    try:
        from googleapiclient.http import MediaIoBaseUpload
        folder = folder_id or ROOT_FOLDER()
        metadata = {"name": name, "parents": [folder]}
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
        file = svc.files().create(
            body=metadata, media_body=media,
            fields="id,name,webViewLink",
        ).execute()
        return {"id": file.get("id"), "name": file.get("name"), "link": file.get("webViewLink")}
    except Exception as e:
        print(f"[DRIVE] upload error: {e}")
        return None


def upload_text(name: str, text: str, folder_id: Optional[str] = None) -> Optional[dict]:
    """Upload a text/markdown file to Drive."""
    return upload_file(name, text.encode("utf-8"), "text/plain", folder_id)


def download_file(file_id: str) -> Optional[bytes]:
    """Download file content by ID."""
    svc = _get_service()
    if not svc:
        return None
    try:
        return svc.files().get_media(fileId=file_id).execute()
    except Exception as e:
        print(f"[DRIVE] download error: {e}")
        return None


def create_folder(name: str, parent_id: Optional[str] = None) -> Optional[str]:
    """Create a Drive folder. Returns folder ID."""
    svc = _get_service()
    if not svc:
        return None
    try:
        parent = parent_id or ROOT_FOLDER()
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent],
        }
        folder = svc.files().create(body=metadata, fields="id").execute()
        return folder.get("id")
    except Exception as e:
        print(f"[DRIVE] create_folder error: {e}")
        return None


def get_recent_files(limit: int = 10) -> list[dict]:
    """Get recently modified files."""
    svc = _get_service()
    if not svc:
        return []
    try:
        result = svc.files().list(
            q="trashed=false",
            pageSize=limit,
            fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
        ).execute()
        return _format_files(result.get("files", []))
    except Exception as e:
        print(f"[DRIVE] recent error: {e}")
        return []


def _format_files(files: list) -> list[dict]:
    result = []
    for f in files:
        size = f.get("size")
        size_str = f"{int(size) // 1024}KB" if size else "—"
        result.append({
            "id": f.get("id"),
            "name": f.get("name"),
            "type": _friendly_mime(f.get("mimeType", "")),
            "mime": f.get("mimeType"),
            "size": size_str,
            "modified": f.get("modifiedTime", ""),
            "link": f.get("webViewLink", ""),
        })
    return result


def _friendly_mime(mime: str) -> str:
    mapping = {
        "application/vnd.google-apps.folder": "📁 Folder",
        "application/vnd.google-apps.document": "📄 Doc",
        "application/vnd.google-apps.spreadsheet": "📊 Sheet",
        "application/vnd.google-apps.presentation": "📊 Slides",
        "application/pdf": "📋 PDF",
        "image/png": "🖼 PNG",
        "image/jpeg": "🖼 JPEG",
        "text/plain": "📝 Text",
        "text/markdown": "📝 Markdown",
    }
    return mapping.get(mime, "📄 File")


def drive_available() -> bool:
    from integrations.google import has_any_credentials
    return has_any_credentials()
