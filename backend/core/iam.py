"""IAM Engine: iam.yaml 기반 RBAC + Ownership 권한 관리."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class RolePolicy:
    read: list[str] = field(default_factory=list)
    write: list[str] = field(default_factory=list)


@dataclass
class UserEntry:
    user_id: str
    roles: list[str] = field(default_factory=list)


class IAMEngine:
    def __init__(self, iam_path: Path) -> None:
        self._path = iam_path
        self._roles: dict[str, RolePolicy] = {}
        self._users: dict[str, UserEntry] = {}
        self.reload()

    def reload(self) -> None:
        if not self._path.exists():
            return
        with open(self._path, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        self._roles.clear()
        for name, pol in data.get("roles", {}).items():
            self._roles[name] = RolePolicy(
                read=pol.get("allowed_paths", {}).get("read", []),
                write=pol.get("allowed_paths", {}).get("write", []),
            )

        self._users.clear()
        for u in data.get("users", []):
            uid = u["user_id"]
            self._users[uid] = UserEntry(user_id=uid, roles=u.get("roles", []))

    def user_exists(self, user_id: str) -> bool:
        return user_id in self._users

    def get_user_roles(self, user_id: str) -> list[str]:
        entry = self._users.get(user_id)
        return entry.roles if entry else []

    def allowed_read_paths(self, user_id: str) -> list[str]:
        paths: list[str] = []
        for role_name in self.get_user_roles(user_id):
            policy = self._roles.get(role_name)
            if policy:
                paths.extend(policy.read)
        # 항상 본인 Private 경로 포함
        paths.append(f"/Private/{user_id}/**")
        return list(set(paths))

    def allowed_write_paths(self, user_id: str) -> list[str]:
        paths: list[str] = []
        for role_name in self.get_user_roles(user_id):
            policy = self._roles.get(role_name)
            if policy:
                paths.extend(policy.write)
        paths.append(f"/Private/{user_id}/**")
        return list(set(paths))

    @staticmethod
    def _normalize(path: str) -> str:
        """경로 앞에 /가 없으면 추가하여 IAM 패턴과 매칭 보장."""
        p = path.strip()
        return p if p.startswith("/") else f"/{p}"

    def can_read(self, user_id: str, rel_path: str) -> bool:
        from fnmatch import fnmatch
        normalized = self._normalize(rel_path)
        return any(fnmatch(normalized, pat) for pat in self.allowed_read_paths(user_id))

    def can_write(self, user_id: str, rel_path: str) -> bool:
        from fnmatch import fnmatch
        normalized = self._normalize(rel_path)
        return any(fnmatch(normalized, pat) for pat in self.allowed_write_paths(user_id))

    def as_dict(self) -> dict:
        """Return the current IAM configuration as a serialisable dict."""
        roles = {}
        for name, pol in self._roles.items():
            roles[name] = {"allowed_paths": {"read": pol.read, "write": pol.write}}
        users = [
            {"user_id": u.user_id, "roles": u.roles}
            for u in self._users.values()
        ]
        return {"roles": roles, "users": users}

    def save(self, data: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        self.reload()
