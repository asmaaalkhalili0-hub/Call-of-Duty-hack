import os
import sys
import time
import logging
from pathlib import Path
import requests
from requests.exceptions import (
    ConnectionError, Timeout, HTTPError, RequestException, JSONDecodeError
)

# --------------------------
# Configuration
# --------------------------
SERVER_URL = "https://installing-his-controversial-papua.trycloudflare.com/upload"
API_KEY = "_r0y7ZcKdiGvg47w3heYMen8Mb9PtZBq5z_cO6SujCo"
DOWNLOADS_DIR = Path.home() / "storage" / "downloads"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".svg"}

# Timeout settings (seconds)
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubled each retry

# --------------------------
# Logging setup
# --------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("upload_errors.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


def upload_image(file_path: Path) -> requests.Response:
    """
    Upload a single image file to the server.
    Includes detailed logging, timeout, and status-code validation.
    """
    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    logger.info(f"Uploading: {file_path.name} (size: {file_path.stat().st_size} bytes)")

    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, "application/octet-stream")}

        try:
            response = requests.post(
                SERVER_URL,
                files=files,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
            )
            logger.debug(f"Raw response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")

            # Log response body (first 500 chars) for debugging
            body_preview = response.text[:500]
            logger.debug(f"Response body preview: {body_preview}")

            response.raise_for_status()
            return response

        except Timeout as e:
            logger.error(f"Timeout while uploading {file_path.name}: {e}")
            logger.error(f"  - Connection timeout: {CONNECT_TIMEOUT}s, Read timeout: {READ_TIMEOUT}s")
            raise
        except ConnectionError as e:
            logger.error(f"Connection error while uploading {file_path.name}: {e}")
            logger.error("  - Check if the server is reachable and the URL is correct.")
            raise
        except HTTPError as e:
            logger.error(f"HTTP error {response.status_code} for {file_path.name}: {e}")
            # Log the server's error message if available
            try:
                error_detail = response.json()
                logger.error(f"  - Server response: {error_detail}")
            except JSONDecodeError:
                logger.error(f"  - Server returned non-JSON body: {response.text[:200]}")
            raise
        except RequestException as e:
            logger.error(f"Unexpected request error for {file_path.name}: {e}")
            raise


def upload_with_retry(file_path: Path) -> requests.Response:
    """Wrapper that adds retry logic for transient failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return upload_image(file_path)
        except (Timeout, ConnectionError) as e:
            if attempt == MAX_RETRIES:
                logger.error(f"All {MAX_RETRIES} attempts failed for {file_path.name}")
                raise
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(
                f"Attempt {attempt} failed for {file_path.name}. "
                f"Retrying in {wait}s..."
            )
            time.sleep(wait)


def main():
    if not DOWNLOADS_DIR.exists():
        logger.error(f"Downloads folder not found: {DOWNLOADS_DIR}")
        logger.info("Please create the folder or update DOWNLOADS_DIR in the script.")
        return

    logger.info(f"Scanning folder: {DOWNLOADS_DIR}")
    images = [
        item for item in DOWNLOADS_DIR.iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if not images:
        logger.warning("No image files found in the downloads folder.")
        return

    logger.info(f"Found {len(images)} image(s) to upload.")

    success_count = 0
    fail_count = 0

    for item in images:
        try:
            resp = upload_with_retry(item)
            logger.info(f"SUCCESS: {item.name} (HTTP {resp.status_code})")
            success_count += 1
        except Exception as e:
            logger.error(f"FAILED: {item.name} - {e}")
            fail_count += 1

    logger.info(f"Upload complete. Success: {success_count}, Failed: {fail_count}")

    if fail_count > 0:
        logger.warning("Check 'upload_errors.log' for detailed error information.")


if __name__ == "__main__":
    main()
