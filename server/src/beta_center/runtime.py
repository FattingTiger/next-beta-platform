from __future__ import annotations

from dataclasses import dataclass

from beta_center.config import Settings
from beta_center.database import Database
from beta_center.security import LoginRateLimiter
from beta_center.services.apk import ApkInspector
from beta_center.services.storage import LocalStorage


@dataclass(slots=True)
class Runtime:
    settings: Settings
    database: Database
    storage: LocalStorage
    apk_inspector: ApkInspector
    login_limiter: LoginRateLimiter
