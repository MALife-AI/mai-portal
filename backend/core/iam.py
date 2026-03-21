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
    department: str = ""


class IAMEngine:
    def __init__(self, iam_path: Path) -> None:
        self._path = iam_path
        self._roles: dict[str, RolePolicy] = {}
        self._users: dict[str, UserEntry] = {}
        self._departments: dict[str, dict[str, str]] = {}
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

        self._departments.clear()
        for dept_id, dept_info in data.get("departments", {}).items():
            self._departments[dept_id] = dept_info if isinstance(dept_info, dict) else {}

        self._users.clear()
        for u in data.get("users", []):
            uid = u["user_id"]
            self._users[uid] = UserEntry(
                user_id=uid,
                roles=u.get("roles", []),
                department=u.get("department", ""),
            )

    def user_exists(self, user_id: str) -> bool:
        return user_id in self._users

    def get_user_roles(self, user_id: str) -> list[str]:
        entry = self._users.get(user_id)
        return entry.roles if entry else []

    def get_user_department(self, user_id: str) -> str:
        entry = self._users.get(user_id)
        return entry.department if entry else ""

    def get_departments(self) -> dict[str, dict[str, str]]:
        return dict(self._departments)

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

    def _check_department_folder(self, user_id: str, rel_path: str) -> bool | None:
        """Shared/{dept_id}/ 경로의 부서 접근 권한 확인.

        Returns:
            True if allowed, False if denied, None if not a department folder.
        """
        parts = rel_path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "Shared" and parts[1] in self._departments:
            folder_dept = parts[1]
            user_dept = self.get_user_department(user_id)
            # admin 역할은 모든 부서 폴더 접근 가능
            if "admin" in self.get_user_roles(user_id):
                return True
            return user_dept == folder_dept
        return None

    def can_read(self, user_id: str, rel_path: str) -> bool:
        from fnmatch import fnmatch
        normalized = self._normalize(rel_path)

        # 부서 폴더 접근 제어 우선 적용
        dept_check = self._check_department_folder(user_id, normalized)
        if dept_check is not None:
            return dept_check

        return any(fnmatch(normalized, pat) for pat in self.allowed_read_paths(user_id))

    def can_write(self, user_id: str, rel_path: str) -> bool:
        from fnmatch import fnmatch
        normalized = self._normalize(rel_path)

        # 부서 폴더 접근 제어 우선 적용
        dept_check = self._check_department_folder(user_id, normalized)
        if dept_check is not None:
            return dept_check

        return any(fnmatch(normalized, pat) for pat in self.allowed_write_paths(user_id))

    def as_dict(self) -> dict:
        """Return the current IAM configuration as a serialisable dict."""
        departments = dict(self._departments)
        roles = {}
        for name, pol in self._roles.items():
            roles[name] = {"allowed_paths": {"read": pol.read, "write": pol.write}}
        users = [
            {"user_id": u.user_id, "roles": u.roles, "department": u.department}
            for u in self._users.values()
        ]
        return {"departments": departments, "roles": roles, "users": users}

    def save(self, data: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        self.reload()
