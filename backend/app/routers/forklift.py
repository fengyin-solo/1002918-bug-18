"""场车管理接口：维护场内车辆，覆盖详情、字段修改、安排维修/年检、报废与换人交接。

路由层只负责取「当前操作人」并转交服务层；归属判定与授权一律在 services 里做。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.identity import TEAM_DRIVERS, User, current_user, user_public
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.forklift import ForkliftService

router = APIRouter(prefix="/api/forklift", tags=["场车管理"])

service = ForkliftService()

LIST_FIELDS = ["车辆编号", "车辆类型", "动力类型", "核定载重", "行驶区域", "驾驶员", "年检日期", "车辆状态", "归属班组", "责任人"]
STATUSES = ["正常", "维修中", "待年检", "已报废"]


@router.get("/teams")
def list_teams() -> dict[str, Any]:
    """提供班组与在册驾驶员名册，供交接表单选择。"""
    return {"teams": list(TEAM_DRIVERS), "drivers": TEAM_DRIVERS}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按车辆编号检索"),
    status: str | None = Query(default=None, description="正常、维修中、待年检、已报废"),
    team: str | None = Query(default=None, description="按归属班组过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按车辆编号、状态与归属班组过滤场车管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, team=team, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出场车管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "forklift", "total": total, "items": items}


@router.get("/{entry_id}/detail", response_model=dict)
def get_detail(entry_id: int) -> dict[str, Any]:
    """读取车辆详情：归属快照、交接痕迹与操作台账。"""
    detail = service.get_detail(entry_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"场内车辆 {entry_id} 不存在或已归档")
    return detail


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条场内车辆明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"场内车辆 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload, user: User = Depends(current_user)) -> ActionResult:
    """登记一条场内车辆（仅车辆管理员），归属落到登记人所在班组。"""
    entry, message = service.create_entry(payload.values, user)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="场内车辆已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    user: User = Depends(current_user),
) -> ActionResult:
    """对单条场内车辆执行安排维修、安排年检、申请报废；越权或代办会被当场驳回并说明缺项。"""
    action = str(payload.values.get("action") or "").strip()
    detail = str(payload.values.get("detail") or payload.remark or "").strip()
    entry, message = service.run_action(entry_id, action, user, detail)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/fields", response_model=ActionResult)
def update_fields(
    entry_id: int,
    payload: EntryPayload,
    user: User = Depends(current_user),
) -> ActionResult:
    """修改核定载重、年检日期：仅本班组车辆管理员可改，只读岗只能查看。"""
    entry, message = service.update_fields(entry_id, payload.values, user)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/handover", response_model=ActionResult)
def handover(
    entry_id: int,
    payload: EntryPayload,
    user: User = Depends(current_user),
) -> ActionResult:
    """换人：同班组驾驶员交接或跨班组归属调整；原责任人与原班组只追加痕迹，不被覆盖。"""
    values = payload.values
    entry, message = service.handover(
        entry_id,
        new_driver=str(values.get("new_driver") or ""),
        new_team=str(values.get("new_team") or "") or None,
        new_owner_id=str(values.get("new_owner_id") or "") or None,
        remark=str(values.get("remark") or payload.remark or ""),
        user=user,
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/{entry_id}/permissions")
def get_permissions(entry_id: int, user: User = Depends(current_user)) -> dict[str, Any]:
    """返回当前操作人对这台车的可操作项，供详情页决定按钮/表单是否可编辑。最终仍以后端鉴权为准。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"场内车辆 {entry_id} 不存在或已归档")
    is_owner_admin = user.is_admin and user.team == entry.get("归属班组")
    scrapped = entry.get("status") == "已报废"
    return {
        "user": user_public(user),
        "role": user.role,
        "team": user.team,
        "is_readonly": user.is_readonly,
        "can_edit_fields": is_owner_admin,
        "can_run_actions": is_owner_admin and not scrapped,
        "can_handover_same_team": is_owner_admin,
        "can_take_over": user.is_admin and user.team != entry.get("归属班组") and not scrapped,
        "scrapped": scrapped,
    }
