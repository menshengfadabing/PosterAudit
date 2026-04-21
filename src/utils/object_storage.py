"""对象存储封装（MinIO）"""

from __future__ import annotations

from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error

from src.utils.config import settings


class ObjectStorage:
    def __init__(self):
        self.enabled = bool(settings.enable_minio_storage)
        self.bucket = settings.minio_bucket.strip()
        self.task_prefix = settings.minio_task_prefix.strip().strip("/")
        self.ref_prefix = settings.minio_reference_prefix.strip().strip("/")
        self._client: Optional[Minio] = None

        if not self.enabled:
            return

        endpoint = settings.minio_endpoint.strip()
        access_key = settings.minio_access_key.strip()
        secret_key = settings.minio_secret_key.strip()
        if not endpoint or not access_key or not secret_key or not self.bucket:
            raise RuntimeError("MinIO 已启用但配置不完整，请检查 MINIO_* 环境变量")

        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=bool(settings.minio_secure),
        )
        self.ensure_bucket()

    @property
    def client(self) -> Minio:
        if not self._client:
            raise RuntimeError("MinIO 未启用")
        return self._client

    def ensure_bucket(self) -> None:
        if not self.enabled:
            return
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_bytes(self, object_key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        if not self.enabled:
            raise RuntimeError("MinIO 未启用")
        data = BytesIO(content)
        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_key,
            data=data,
            length=len(content),
            content_type=content_type,
        )

    def get_bytes(self, object_key: str) -> bytes:
        if not self.enabled:
            raise RuntimeError("MinIO 未启用")
        resp = self.client.get_object(self.bucket, object_key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def delete(self, object_key: str) -> None:
        if not self.enabled:
            return
        try:
            self.client.remove_object(self.bucket, object_key)
        except S3Error:
            # 幂等删除
            return

    def stat_exists(self, object_key: str) -> bool:
        if not self.enabled:
            return False
        try:
            self.client.stat_object(self.bucket, object_key)
            return True
        except S3Error:
            return False

    def build_task_image_key(self, task_id: str, filename: str) -> str:
        parts = [p for p in [self.task_prefix, task_id, filename] if p]
        return "/".join(parts)

    def build_reference_image_key(self, brand_id: str, filename: str) -> str:
        parts = [p for p in [self.ref_prefix, brand_id, filename] if p]
        return "/".join(parts)


object_storage = ObjectStorage()
