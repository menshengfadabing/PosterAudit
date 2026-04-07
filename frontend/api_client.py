"""封装所有 FastAPI 调用"""
import io
from typing import Optional

import httpx

from frontend.config import API_BASE_URL, API_KEY

_HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}
_TIMEOUT = 120.0


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, headers=_HEADERS, timeout=_TIMEOUT)


# ── 品牌规则 ──────────────────────────────────────────────────────────────────

def list_brands() -> list[dict]:
    with _client() as c:
        r = c.get("/api/v1/brands")
        r.raise_for_status()
        return r.json()


def create_brand(file_bytes: bytes, filename: str, brand_name: str) -> dict:
    with _client() as c:
        r = c.post(
            "/api/v1/brands",
            data={"brand_name": brand_name},
            files={"file": (filename, io.BytesIO(file_bytes), "application/octet-stream")},
        )
        r.raise_for_status()
        return r.json()


def update_brand(brand_id: str, action: str = "update", brand_name: Optional[str] = None) -> dict:
    data: dict = {"action": action}
    if brand_name:
        data["brand_name"] = brand_name
    with _client() as c:
        r = c.put(f"/api/v1/brands/{brand_id}", data=data)
        r.raise_for_status()
        return r.json()


def delete_brand(brand_id: str) -> None:
    with _client() as c:
        r = c.delete(f"/api/v1/brands/{brand_id}")
        r.raise_for_status()


def upload_reference_images(
    brand_id: str,
    files: list[tuple[str, bytes]],   # [(filename, bytes), ...]
    image_type: str = "logo",
    description: str = "",
) -> dict:
    with _client() as c:
        r = c.post(
            f"/api/v1/brands/{brand_id}/images",
            data={"image_type": image_type, "description": description},
            files=[("files", (name, io.BytesIO(data), "image/png")) for name, data in files],
        )
        r.raise_for_status()
        return r.json()


def delete_reference_image(brand_id: str, filename: str) -> None:
    with _client() as c:
        r = c.delete(f"/api/v1/brands/{brand_id}/images/{filename}")
        r.raise_for_status()


# ── 审核 ──────────────────────────────────────────────────────────────────────

def submit_audit(
    brand_id: str,
    images: list[tuple[str, bytes]],   # [(filename, bytes), ...]
    mode: str = "async",
    batch_size: Optional[int] = None,
    compression: str = "balanced",
) -> dict:
    data: dict = {"brand_id": brand_id, "mode": mode, "compression": compression}
    if batch_size:
        data["batch_size"] = str(batch_size)
    with _client() as c:
        r = c.post(
            "/api/v1/audit",
            data=data,
            files=[("images", (name, io.BytesIO(b), "image/png")) for name, b in images],
        )
        r.raise_for_status()
        return r.json()


def get_task(task_id: str) -> dict:
    with _client() as c:
        r = c.get(f"/api/v1/tasks/{task_id}")
        r.raise_for_status()
        return r.json()


def list_history(brand_id: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
    params: dict = {"page": page, "page_size": page_size}
    if brand_id:
        params["brand_id"] = brand_id
    with _client() as c:
        r = c.get("/api/v1/history", params=params)
        r.raise_for_status()
        return r.json()
