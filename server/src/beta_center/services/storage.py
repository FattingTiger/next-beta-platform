from __future__ import annotations

import hashlib
import io
import os
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError


class StorageError(ValueError):
    pass


DIRECTORY_MODE = 0o2750
FILE_MODE = 0o640


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    sha256: str
    content_type: str


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        # The setgid bit keeps every object in the deployment's private
        # storage group. The application owner can write while the gateway's
        # group membership is read-only; no permissions are granted to others.
        self.root.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        self._harden_directory(self.root)

    def path_for(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise StorageError("非法文件路径")
        return candidate

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def delete(self, key: str | None) -> None:
        if not key:
            return
        path = self.path_for(key)
        path.unlink(missing_ok=True)
        if path.parent.is_dir():
            self._sync_directory(path.parent)

    def verify_writable(self) -> None:
        probe = self.root / f".health-{uuid.uuid4().hex}"
        descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, FILE_MODE)
        try:
            os.write(descriptor, b"ok")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            probe.unlink(missing_ok=True)

    async def save_upload(
        self,
        upload: UploadFile,
        *,
        namespace: str,
        extension: str,
        max_bytes: int,
        expected_content_types: set[str] | None = None,
    ) -> StoredObject:
        if expected_content_types and upload.content_type not in expected_content_types:
            raise StorageError("不支持的文件类型")
        key = self._new_key(namespace, extension)
        destination = self.path_for(key)
        self._prepare_directory(destination.parent)
        temp = destination.with_suffix(destination.suffix + ".part")
        digest = hashlib.sha256()
        size = 0
        try:
            with temp.open("xb") as handle:
                temp.chmod(FILE_MODE)
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise StorageError(f"文件超过 {max_bytes // (1024 * 1024)} MB 限制")
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if size == 0:
                raise StorageError("文件不能为空")
            self._commit_temp(temp, destination)
        except Exception:
            temp.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        return StoredObject(
            key=key,
            size=size,
            sha256=digest.hexdigest(),
            content_type=upload.content_type or "application/octet-stream",
        )

    async def save_image(
        self,
        upload: UploadFile,
        *,
        namespace: str,
        max_bytes: int,
        max_dimension: int = 8000,
    ) -> StoredObject:
        allowed = {"image/jpeg", "image/png", "image/webp"}
        if upload.content_type not in allowed:
            raise StorageError("截图仅支持 JPEG、PNG 或 WebP")
        payload = await upload.read(max_bytes + 1)
        await upload.close()
        if not payload:
            raise StorageError("图片不能为空")
        if len(payload) > max_bytes:
            raise StorageError(f"图片超过 {max_bytes // (1024 * 1024)} MB 限制")
        try:
            with Image.open(io.BytesIO(payload)) as source:
                self._validate_image_header(source, max_dimension=max_dimension)
                source.verify()
            with Image.open(io.BytesIO(payload)) as source:
                self._validate_image_header(source, max_dimension=max_dimension)
                image = ImageOps.exif_transpose(source)
                if max(image.size) > max_dimension:
                    image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                if image.mode in {"RGBA", "LA"}:
                    image.save(output, format="WEBP", quality=90, method=6, exact=True)
                else:
                    image.convert("RGB").save(output, format="WEBP", quality=90, method=6)
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
            raise StorageError("图片内容损坏或格式不受支持") from exc
        clean = output.getvalue()
        if len(clean) > max_bytes:
            raise StorageError(f"处理后的图片超过 {max_bytes // (1024 * 1024)} MB 限制")
        key = self._new_key(namespace, ".webp")
        destination = self.path_for(key)
        self._prepare_directory(destination.parent)
        temp = destination.with_suffix(".webp.part")
        try:
            with temp.open("xb") as handle:
                temp.chmod(FILE_MODE)
                handle.write(clean)
                handle.flush()
                os.fsync(handle.fileno())
            self._commit_temp(temp, destination)
        except Exception:
            temp.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        return StoredObject(
            key=key,
            size=len(clean),
            sha256=hashlib.sha256(clean).hexdigest(),
            content_type="image/webp",
        )

    def _new_key(self, namespace: str, extension: str) -> str:
        if not namespace.replace("-", "").replace("_", "").isalnum():
            raise StorageError("非法存储命名空间")
        suffix = extension if extension.startswith(".") else f".{extension}"
        now = datetime.now(UTC)
        return f"{namespace}/{now:%Y/%m}/{uuid.uuid4().hex}{suffix.lower()}"

    @staticmethod
    def _validate_image_header(source: Image.Image, *, max_dimension: int) -> None:
        width, height = source.size
        if width <= 0 or height <= 0:
            raise StorageError("图片尺寸无效")
        if max(width, height) > 16_000 or width * height > 32_000_000:
            raise StorageError("图片像素尺寸过大")
        if getattr(source, "n_frames", 1) != 1:
            raise StorageError("不支持动态图或多帧图片")

    def _prepare_directory(self, directory: Path) -> None:
        directory.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        current = directory
        while current == self.root or self.root in current.parents:
            self._harden_directory(current)
            if current == self.root:
                break
            current = current.parent

    @staticmethod
    def _harden_directory(directory: Path) -> None:
        """Apply and verify the private directory contract.

        Production runs with ``beta-files`` as the application's primary group,
        so POSIX setgid must stick and descendants inherit that group. Darwin
        may silently clear setgid when a temporary parent gives the directory a
        group the unprivileged test process does not belong to. In that local
        case the meaningful safety boundary is still owner/group ``0750`` with
        no access for others; requiring an un-settable bit would make the
        cross-platform test lie about the access controls that actually matter.
        """

        directory.chmod(DIRECTORY_MODE)
        metadata = directory.stat()
        mode = stat.S_IMODE(metadata.st_mode)
        if mode & 0o777 != 0o750:
            raise StorageError("存储目录权限不安全")

        if os.name != "posix":
            return
        process_groups = set(os.getgroups())
        if hasattr(os, "getegid"):
            process_groups.add(os.getegid())
        can_set_group_inheritance = (
            getattr(os, "geteuid", lambda: -1)() == 0 or metadata.st_gid in process_groups
        )
        if can_set_group_inheritance and not mode & stat.S_ISGID:
            raise StorageError("存储目录无法启用组继承权限")

    def _commit_temp(self, temp: Path, destination: Path) -> None:
        temp.replace(destination)
        destination.chmod(FILE_MODE)
        self._sync_directory(destination.parent)

    @staticmethod
    def _sync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
