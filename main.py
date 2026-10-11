import os
from pathlib import Path
import requests

# Configuration
SERVER_URL = "https://installing-his-controversial-papua.trycloudflare.com/upload"  # Replace with your server endpoint
API_KEY = "_r0y7ZcKdiGvg47w3heYMen8Mb9PtZBq5z_cO6SujCo"                  # Optional: set to None if no auth
DOWNLOADS_DIR = Path.home() / "storage" / "downloads"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".svg"}

def upload_image(file_path: Path) -> requests.Response:
    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, "application/octet-stream")}
        response = requests.post(SERVER_URL, files=files, headers=headers)

    response.raise_for_status()
    return response

def main():
    if not DOWNLOADS_DIR.exists():
        print(f"Downloads folder not found: {DOWNLOADS_DIR}")
        return

    for item in DOWNLOADS_DIR.iterdir():
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
            try:
                print(f"Uploading {item.name}...")
                resp = upload_image(item)
                print(f"Success: {item.name} - Status {resp.status_code}")
            except Exception as e:
                print(f"Failed: {item.name} - {e}")

if __name__ == "__main__":
    main()
