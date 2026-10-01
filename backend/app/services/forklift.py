"""场车管理业务规则：归属判定、状态流转、字段校验与操作留痕。

归属必须落到人：每台车有「归属班组 + 责任人（本班组车辆管理员）」。
维修 / 年检 / 报废与字段修改一律先按「当前操作人」鉴权——
非车辆管理员、非本班组的操作当场驳回，并说明缺的是角色授权还是班组授权；
换人（驾驶员交接、跨班组归属调整）只追加交接记录，历史台账仍记原班组与原责任人。
"""
from __future__ import annotations

from typing import Any

from app.identity import (
    ROLE_ADMIN,
    TEAM_DRIVERS,
    User,
    now_ts,
)
from app.store import store

MODULE = "forklift"
HANDOVER_MODULE = "forklift_handover"
LOG_MODULE = "forklift_log"

REQUIRED_FIELDS = ["车辆编号", "车辆类型", "动力类型"]
# 仅本班组车辆管理员可改的台账字段（只读岗、驾驶员、外班组一律不可改）。
EDITABLE_FIELDS = ["核定载重", "年检日期"]
STATUS_ORDER = ["正常", "维修中", "待年检", "已报废"]
ACTION_RULES = {"安排维修": "维修中", "安排年检": "待年检", "申请报废": "已报废"}
NEGATIVE_ACTIONS = []


class AuthorizationError(Exception):
    """鉴权未通过：消息里写明缺哪项授权，供接口原样回给前端。"""


class ForkliftService:
    # ---------- 查询 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        team: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("车辆编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if team:
            rows = [row for row in rows if row.get("归属班组") == team]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def get_detail(self, entry_id: int) -> dict[str, Any] | None:
        """详情页：归属快照 + 交接痕迹 + 操作台账，列表与详情读同一份归属字段。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        vehicle_no = entry.get("车辆编号")
        handovers = [h for h in store.rows(HANDOVER_MODULE) if h.get("车辆编号") == vehicle_no]
        logs = [log for log in store.rows(LOG_MODULE) if log.get("车辆编号") == vehicle_no]
        return {
            "entry": entry,
            "handovers": sorted(handovers, key=lambda row: row.get("id", 0)),
            "logs": sorted(logs, key=lambda row: row.get("id", 0)),
        }

    # ---------- 登记 ----------
    def create_entry(self, values: dict[str, Any], user: User) -> tuple[dict[str, Any] | None, str]:
        try:
            self._require_admin(user, team=None, action="登记场内车辆")
        except AuthorizationError as exc:
            return None, str(exc)
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ["车辆编号", "车辆类型", "动力类型", "核定载重", "行驶区域", "年检日期"]:
            if str(values.get(field) or "").strip():
                entry[field] = values[field]
        entry["驾驶员"] = ""  # 驾驶员只能经交接落定，登记时不允许随手填
        entry["车辆状态"] = STATUS_ORDER[0]
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        # 归属落到登记人：谁登记、谁的班组负责。
        entry["归属班组"] = user.team
        entry["责任人"] = user.name
        entry["责任人编号"] = user.id
        rows.append(entry)
        self._append_log(entry, "登记建档", f"登记车辆并归属{user.team}，责任人{user.name}", user)
        return entry, ""

    # ---------- 维修 / 年检 / 报废 ----------
    def run_action(self, entry_id: int, action: str, user: User, detail: str = "") -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场内车辆 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于场车管理可执行范围"
        try:
            self._require_owner_admin(entry, user, action=action)
        except AuthorizationError as exc:
            return None, str(exc)
        if entry.get("status") == STATUS_ORDER[-1]:
            return None, "车辆已报废，不能再安排维修、年检或重复报废"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["车辆状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        self._append_log(entry, action, detail or f"{user.name}登记{action.lstrip('安排申请')}", user)
        return entry, f"场内车辆已{action}"

    # ---------- 台账字段修改（核定载重、年检日期） ----------
    def update_fields(self, entry_id: int, values: dict[str, Any], user: User) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场内车辆 {entry_id} 不存在或已归档"
        changes = {
            field: str(values[field]).strip()
            for field in EDITABLE_FIELDS
            if field in values and str(values[field]).strip()
        }
        if not changes:
            return None, "没有可修改的字段（仅核定载重、年检日期允许修改）"
        try:
            self._require_owner_admin(entry, user, action="修改核定载重或年检日期")
        except AuthorizationError as exc:
            return None, str(exc)
        for field, new_value in changes.items():
            old_value = str(entry.get(field) or "（空）")
            entry[field] = new_value
            self._append_log(entry, f"修改{field}", f"{field}：{old_value} → {new_value}", user)
        return entry, f"已更新 {'、'.join(changes)}"

    # ---------- 换人：驾驶员交接（同班组） / 归属调整（跨班组） ----------
    def handover(
        self,
        entry_id: int,
        *,
        new_driver: str,
        new_team: str | None,
        new_owner_id: str | None,
        remark: str,
        user: User,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场内车辆 {entry_id} 不存在或已归档"
        new_driver = (new_driver or "").strip()
        new_team = (new_team or "").strip()
        if not new_driver:
            return None, "交接必须指定接手驾驶员，不能把驾驶员留空"
        if entry.get("status") == STATUS_ORDER[-1]:
            return None, "车辆已报废，不能再办理驾驶员交接或归属调整"

        old_team = str(entry.get("归属班组") or "")
        old_owner = str(entry.get("责任人") or "")
        old_driver = str(entry.get("驾驶员") or "（未定岗）")
        transfer = bool(new_team and new_team != old_team)

        # 归属调整由接收班组的车辆管理员发起；同班组交接仍要求本人是本班组管理员。
        acting_team = new_team if transfer else old_team
        try:
            self._require_admin(user, team=acting_team, action="归属调整" if transfer else "驾驶员交接")
        except AuthorizationError as exc:
            return None, str(exc)

        if new_driver not in TEAM_DRIVERS.get(acting_team, []):
            drivers = "、".join(TEAM_DRIVERS.get(acting_team, [])) or "（暂无在册驾驶员）"
            return None, f"{acting_team}在册驾驶员为：{drivers}；「{new_driver}」不在名册，不能交接"

        if transfer:
            new_owner = self._resolve_new_owner(new_owner_id, new_team)
            if new_owner is None:
                admins = [f"{u.name}（{u.id}）" for u in _admins_of(new_team)]
                return None, f"归属到{new_team}必须指定该班组车辆管理员为新责任人，可选：{'、'.join(admins)}"
        else:
            new_owner = user  # 同班组交接责任人不变（就是当前管理员本人）

        # 先留痕再覆盖：交接记录固定保存原班组、原责任人、原驾驶员。
        record = {
            "id": self._next_id(HANDOVER_MODULE),
            "车辆编号": entry.get("车辆编号"),
            "交接类型": "归属调整" if transfer else "驾驶员交接",
            "原班组": old_team,
            "原责任人": old_owner,
            "原驾驶员": old_driver,
            "新班组": new_owner.team,
            "新责任人": new_owner.name,
            "新驾驶员": new_driver,
            "操作人": user.name,
            "时间": now_ts(),
            "备注": remark.strip() or ("跨班组归属调整" if transfer else "班组内部换人交接"),
        }
        store.rows(HANDOVER_MODULE).append(record)

        # 保存上一任，重新进入仍能追到责任人。
        entry["上一责任人"] = old_owner
        entry["上一责任人编号"] = entry.get("责任人编号")
        entry["上一班组"] = old_team
        entry["归属班组"] = new_owner.team
        entry["责任人"] = new_owner.name
        entry["责任人编号"] = new_owner.id
        entry["驾驶员"] = new_driver

        self._append_log(
            entry,
            record["交接类型"],
            f"{old_team}/{old_driver} → {new_owner.team}/{new_driver}；历史数据仍归原班组「{old_team}」",
            user,
            acting_team=old_team,
        )
        return entry, (
            f"已办理跨班组归属调整，车辆现归{new_owner.team}·{new_owner.name}"
            if transfer
            else f"驾驶员已由本班组交接给{new_driver}"
        )

    # ---------- 鉴权 ----------
    def _require_owner_admin(self, entry: dict[str, Any], user: User, *, action: str) -> None:
        """维修/年检/报废/字段修改：仅车辆归属班组的车辆管理员可办。"""
        owner_team = str(entry.get("归属班组") or "")
        self._require_admin(user, team=owner_team, action=action)

    def _require_admin(self, user: User, *, team: str | None, action: str) -> None:
        if not user.is_admin:
            raise AuthorizationError(
                f"已驳回：{action}需要「{ROLE_ADMIN}」角色授权，当前身份「{user.name}」是{user.role}，仅可查看"
            )
        if team is not None and user.team != team:
            raise AuthorizationError(
                f"已驳回：车辆归属{team}，{action}需由{team}的车辆管理员办理；"
                f"当前「{user.name}」属{user.team}，缺少「{team}场车管理权」授权，禁止代办"
            )

    def _resolve_new_owner(self, owner_id: str | None, team: str) -> User | None:
        from app.identity import USERS

        if owner_id and owner_id in USERS:
            candidate = USERS[owner_id]
            if candidate.is_admin and candidate.team == team:
                return candidate
        return None

    # ---------- 留痕 ----------
    def _append_log(
        self,
        entry: dict[str, Any],
        action: str,
        detail: str,
        user: User,
        acting_team: str | None = None,
    ) -> None:
        store.rows(LOG_MODULE).append({
            "id": self._next_id(LOG_MODULE),
            "车辆编号": entry.get("车辆编号"),
            "动作": action,
            "明细": detail,
            "操作人": user.name,
            "操作人编号": user.id,
            # 关键：操作时所属班组随台账固定；归属调整只影响之后的账，历史账不改班组。
            "操作时班组": acting_team or user.team,
            "时间": now_ts(),
        })

    def _next_id(self, module: str) -> int:
        return max((int(row.get("id", 0)) for row in store.rows(module)), default=0) + 1


def _admins_of(team: str) -> list[User]:
    from app.identity import USERS

    return [user for user in USERS.values() if user.is_admin and user.team == team]
