from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


class ApkInspectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ApkInspection:
    package_name: str
    version_name: str
    version_code: int
    min_sdk: int | None
    target_sdk: int | None
    signing_cert_sha256: str
    sha256: str
    file_size: int


class ApkInspector:
    def __init__(
        self,
        *,
        apksigner_path: str,
        aapt_path: str,
        timeout_seconds: int,
        require_tools: bool,
    ) -> None:
        self.apksigner_path = apksigner_path
        self.aapt_path = aapt_path
        self.timeout_seconds = timeout_seconds
        self.require_tools = require_tools

    def tools_available(self) -> bool:
        return bool(shutil.which(self.apksigner_path) and shutil.which(self.aapt_path))

    def inspect(self, path: Path) -> ApkInspection:
        self._verify_zip(path)
        if not self.tools_available():
            message = "服务器缺少 apksigner 或 aapt，已拒绝弱校验上传"
            if self.require_tools:
                raise ApkInspectionError(message)
            raise ApkInspectionError(message)
        signature_output = self._run(
            [self.apksigner_path, "verify", "--verbose", "--print-certs", str(path)],
            "APK 签名验证失败",
        )
        badging_output = self._run([self.aapt_path, "dump", "badging", str(path)], "APK 清单解析失败")
        certificate = self._parse_certificate(signature_output)
        package_name, version_code, version_name = self._parse_package(badging_output)
        return ApkInspection(
            package_name=package_name,
            version_code=version_code,
            version_name=version_name,
            min_sdk=self._parse_optional_int(badging_output, "sdkVersion"),
            target_sdk=self._parse_optional_int(badging_output, "targetSdkVersion"),
            signing_cert_sha256=certificate,
            sha256=self._sha256(path),
            file_size=path.stat().st_size,
        )

    def _run(self, command: list[str], error_message: str) -> str:
        try:
            with tempfile.TemporaryFile() as tool_output:
                completed = subprocess.run(  # noqa: S603
                    command,
                    stdout=tool_output,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                output_size = tool_output.tell()
                tool_output.seek(max(0, output_size - 64 * 1024))
                output = tool_output.read().decode("utf-8", errors="replace").strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ApkInspectionError(error_message) from exc
        if output_size > 1024 * 1024:
            raise ApkInspectionError(f"{error_message}：校验工具输出异常")
        if completed.returncode != 0:
            detail = output[-500:] if output else "工具未返回详细原因"
            raise ApkInspectionError(f"{error_message}：{detail}")
        return output

    @staticmethod
    def _verify_zip(path: Path) -> None:
        if path.suffix.lower() != ".apk":
            raise ApkInspectionError("上传文件必须是 APK")
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 10_000:
                    raise ApkInspectionError("APK 压缩条目数量异常")
                names: set[str] = set()
                total_uncompressed = 0
                for entry in entries:
                    normalized_name = entry.filename.replace("\\", "/")
                    if (
                        not normalized_name
                        or normalized_name.startswith("/")
                        or ".." in Path(normalized_name).parts
                        or normalized_name in names
                    ):
                        raise ApkInspectionError("APK 包含非法或重复的压缩路径")
                    if entry.flag_bits & 0x1:
                        raise ApkInspectionError("APK 不允许包含加密压缩条目")
                    names.add(normalized_name)
                    total_uncompressed += entry.file_size
                    if entry.file_size > 1024 * 1024 * 1024 or total_uncompressed > 2 * 1024**3:
                        raise ApkInspectionError("APK 解压后体积异常")
                    if (
                        entry.file_size > 10 * 1024 * 1024
                        and entry.compress_size > 0
                        and entry.file_size / entry.compress_size > 250
                    ):
                        raise ApkInspectionError("APK 压缩比异常")
                if "AndroidManifest.xml" not in names or not any(
                    name == "classes.dex" or (name.startswith("classes") and name.endswith(".dex"))
                    for name in names
                ):
                    raise ApkInspectionError("文件不是有效的 Android APK")
        except (OSError, zipfile.BadZipFile) as exc:
            raise ApkInspectionError("APK 文件损坏") from exc

    @staticmethod
    def _parse_certificate(output: str) -> str:
        matches = re.findall(r"certificate SHA-256 digest:\s*([0-9A-Fa-f:]{64,95})", output)
        normalized: set[str] = {value.replace(":", "").lower() for value in matches}
        if not normalized:
            raise ApkInspectionError("无法读取 APK 签名证书")
        if len(normalized) != 1:
            raise ApkInspectionError("首版只支持单一签名证书的 APK")
        certificate = normalized.pop()
        if len(certificate) != 64:
            raise ApkInspectionError("APK 签名证书摘要格式异常")
        return certificate

    @staticmethod
    def _parse_package(output: str) -> tuple[str, int, str]:
        match = re.search(
            r"^package:\s+name='([^']+)'\s+versionCode='([0-9]+)'\s+versionName='([^']*)'",
            output,
            re.MULTILINE,
        )
        if not match:
            raise ApkInspectionError("无法读取 APK 包名或版本")
        return match.group(1), int(match.group(2)), match.group(3)

    @staticmethod
    def _parse_optional_int(output: str, key: str) -> int | None:
        match = re.search(rf"^{re.escape(key)}:'([0-9]+)'", output, re.MULTILINE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
