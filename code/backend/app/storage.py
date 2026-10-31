"""Optional S3 snapshot of the DuckDB file, so data survives App Runner redeploys.

App Runner disks are ephemeral. With DUCKDB_S3_URI set we download the file on boot
and upload a fresh copy after every write. Good enough for a single-instance demo.
"""

import logging
import threading
from pathlib import Path
from urllib.parse import urlparse

from . import config

log = logging.getLogger(__name__)
_upload_lock = threading.Lock()


def _split(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip("/")


def restore(path: Path) -> None:
    """Download the last DuckDB snapshot from S3 before the database opens; no-op without DUCKDB_S3_URI."""
    if not config.DUCKDB_S3_URI:
        return
    import boto3
    from botocore.exceptions import ClientError

    bucket, key = _split(config.DUCKDB_S3_URI)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        boto3.client("s3").download_file(bucket, key, str(path))
        log.info("Restored DuckDB snapshot from %s", config.DUCKDB_S3_URI)
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            log.info("No snapshot at %s yet, starting fresh", config.DUCKDB_S3_URI)
        else:
            raise


def snapshot(path: Path) -> None:
    """Upload the DuckDB file in the background. Caller must CHECKPOINT first."""
    if not config.DUCKDB_S3_URI:
        return

    def _upload() -> None:
        import boto3

        bucket, key = _split(config.DUCKDB_S3_URI)
        with _upload_lock:
            try:
                boto3.client("s3").upload_file(str(path), bucket, key)
            except Exception:  # never break a request because the backup failed
                log.exception("DuckDB snapshot upload failed")

    threading.Thread(target=_upload, daemon=True).start()
