"""场车管理业务规则：归属必须落到「班组 + 责任人」，所有变更都留痕。

授权口径（在服务层统一判定，接口层只负责把当前操作人传进来）：
- 只读岗：只能查看，任何写操作一律拒绝；
- 驾驶员：只可查看，车辆登记/维修/年检/报废/交接都不在其授权内；
- 车辆管理员：只能动归属本班组的车；替别的班组代办当场驳回，
  并说明缺少「该班组车辆管理员授权」这一项；
- 换人（交接）：只能由现任归属班组的车辆管理员发起，接任人也必须是
  车辆管理员；交接后车辆归属切到新任班组，但历任责任人与历史台账条目
  原样保留，重新进入仍能追到上一位责任人。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.auth import ROLE_ADMIN, ROLE_READONLY, STAFF_INDEX
from app.store import store

MODULE = "forklift"
REQUIRED_FIELDS = ["车辆编号", "车辆类型", "动力类型"]
#: 归属管理员可维护的技术档案字段；其余字段一律不允许通过普通编辑改写
EDITABLE_FIELDS = ["核定载重", "年检日期", "行驶区域", "驾驶员"]
STATUS_ORDER = ["正常", "维修中", "待年检", "已报废"]
ACTION_RULES = {"安排维修": "维修中", "安排年检": "待年检", "申请报废": "已报废"}


def _now() -> str:
    """当前时间，秒级；同一演示进程里足够区分先后。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _append_ledger(entry: dict[str, Any], action: str, staff: dict[str, str], detail: str) -> None:
    """追加一条动态台账：发生时的班组与操作人随条目快照，归属调整后历史不改名。"""
    entry.setdefault("动态台账", []).append({
        "时间": _now(),
        "动作": action,
        "班组": staff["班组"],
        "操作人工号": staff["id"],
        "操作人": staff["姓名"],
        "说明": detail,
    })


class ForkliftService:
    # ---- 查询（只读岗、驾驶员、管理员都可看） --------------------------------

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

    # ---- 授权判定 -----------------------------------------------------------

    def _deny_for_mutation(self, staff: dict[str, str], entry: dict[str, Any], verb: str) -> str | None:
        """写操作的统一闸门：先卡岗位，再卡归属班组，驳回时说明缺哪项授权。"""
        if staff["岗位"] == ROLE_READONLY:
            return f"当前为只读岗，仅可查看车辆信息，无{verb}授权"
        if staff["岗位"] != ROLE_ADMIN:
            return f"车辆{verb}仅限车辆管理员办理，当前岗位「{staff['岗位']}」缺少车辆管理员授权"
        owner_team = entry.get("归属班组")
        if owner_team != staff["班组"]:
            return (
                f"车辆 {entry.get('车辆编号')} 归属{owner_team}，"
                f"{verb}需由{owner_team}车辆管理员办理；{staff['班组']}车辆管理员"
                f"{staff['姓名']}缺少{owner_team}车辆管理员授权，代办已驳回"
            )
        return None

    # ---- 登记 ---------------------------------------------------------------

    def create_entry(self, values: dict[str, Any], staff: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
        if staff["岗位"] == ROLE_READONLY:
            return None, "当前为只读岗，仅可查看车辆信息，无登记授权"
        if staff["岗位"] != ROLE_ADMIN:
            return None, f"车辆登记仅限车辆管理员办理，当前岗位「{staff['岗位']}」缺少车辆管理员授权"
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 新登记车辆直接落到登记人所在班组与本人名下，归属从一开始就有人负责
        entry["核定载重"] = values.get("核定载重") or "—"
        entry["行驶区域"] = values.get("行驶区域") or "—"
        entry["驾驶员"] = values.get("驾驶员") or "—"
        entry["年检日期"] = values.get("年检日期") or "—"
        entry["车辆状态"] = STATUS_ORDER[0]
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["归属班组"] = staff["班组"]
        entry["责任人工号"] = staff["id"]
        entry["责任人姓名"] = staff["姓名"]
        entry["历任责任人"] = [{
            "工号": staff["id"], "姓名": staff["姓名"], "班组": staff["班组"], "自": _now(),
        }]
        entry["动态台账"] = []
        _append_ledger(entry, "登记入账", staff, f"车辆登记，归属{staff['班组']}，责任人为{staff['姓名']}")
        rows.append(entry)
        return entry, None

    # ---- 维修 / 年检 / 报废 --------------------------------------------------

    def run_action(
        self, entry_id: int, action: str, staff: dict[str, str], remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场内车辆 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于场车管理可执行范围"
        denial = self._deny_for_mutation(staff, entry, action)
        if denial:
            return None, denial
        target = ACTION_RULES[action]
        if entry.get("status") == STATUS_ORDER[-1]:
            return None, f"车辆 {entry.get('车辆编号')} 已报废，不可再执行{action}"
        entry["status"] = target
        entry["车辆状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        detail = remark.strip() if remark and remark.strip() else f"由{staff['班组']}车辆管理员{staff['姓名']}{action}"
        _append_ledger(entry, action, staff, detail)
        return entry, f"场内车辆已{action}（经办人：{staff['班组']} {staff['姓名']}）"

    # ---- 技术档案编辑：核定载重、年检日期等只能归属管理员改 -------------------

    def update_fields(
        self, entry_id: int, values: dict[str, Any], staff: dict[str, str],
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场内车辆 {entry_id} 不存在或已归档"
        denial = self._deny_for_mutation(staff, entry, "修改车辆档案")
        if denial:
            return None, denial
        changes: list[str] = []
        for field in EDITABLE_FIELDS:
            if field not in values:
                continue
            new_value = str(values.get(field) or "").strip()
            if not new_value:
                return None, f"字段「{field}」不允许清空"
            if str(entry.get(field) or "") != new_value:
                changes.append(f"{field}：{entry.get(field)} → {new_value}")
                entry[field] = new_value
        if not changes:
            return None, "没有检测到可保存的改动"
        _append_ledger(staff=staff, entry=entry, action="档案修改", detail="；".join(changes))
        return entry, "车辆档案已更新"

    # ---- 换人交接：留痕、历史归属不动 ---------------------------------------

    def handover(
        self,
        entry_id: int,
        *,
        successor_id: str,
        staff: dict[str, str],
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场内车辆 {entry_id} 不存在或已归档"
        denial = self._deny_for_mutation(staff, entry, "办理归属交接")
        if denial:
            return None, denial
        successor = STAFF_INDEX.get((successor_id or "").strip())
        if successor is None:
            return None, f"接任人工号 {successor_id} 无法识别，请从车辆管理员名册中选择"
        if successor["岗位"] != ROLE_ADMIN:
            return None, (
                f"接任人「{successor['姓名']}」岗位为{successor['岗位']}，"
                "归属责任人必须由车辆管理员接任，交接已驳回"
            )
        if successor["id"] == staff["id"]:
            return None, "接任人就是当前责任人，无需交接"

        old_owner_id = entry.get("责任人工号")
        old_owner_name = entry.get("责任人姓名")
        old_team = entry.get("归属班组")
        # 只改当前归属指针；历任责任人与历史台账原样保留，永远追得到上一位
        entry["归属班组"] = successor["班组"]
        entry["责任人工号"] = successor["id"]
        entry["责任人姓名"] = successor["姓名"]
        entry.setdefault("历任责任人", []).append({
            "工号": successor["id"],
            "姓名": successor["姓名"],
            "班组": successor["班组"],
            "自": _now(),
        })
        detail = (
            f"{old_team}车辆管理员{old_owner_name}（{old_owner_id}）交出，"
            f"{successor['班组']}车辆管理员{successor['姓名']}（{successor['id']}）接任"
        )
        if remark and remark.strip():
            detail = f"{detail}；备注：{remark.strip()}"
        _append_ledger(entry, "归属交接", staff, detail)
        scope = "跨班组" if old_team != successor["班组"] else "班组内"
        return entry, f"{scope}交接完成，车辆 {entry.get('车辆编号')} 现归属{successor['班组']} {successor['姓名']}"
