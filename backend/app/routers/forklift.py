"""场车管理接口：维护场内车辆，覆盖登记、安排维修、安排年检、申请报废与换人交接。

所有写接口都带当前操作人依赖，授权判定在 service 层完成；
查接口（列表/明细/导出）对全部登录身份开放，但写操作只有归属班组的
车辆管理员能办，只读岗与代办一律在后端驳回。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import current_staff
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.forklift import ForkliftService

router = APIRouter(prefix="/api/forklift", tags=["场车管理"])

service = ForkliftService()

STATUSES = ["正常", "维修中", "待年检", "已报废"]


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


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict[str, Any]:
    """读取单条场内车辆明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"场内车辆 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload, staff: dict = Depends(current_staff)) -> ActionResult:
    """登记一条场内车辆；归属自动落到登记人班组与本人名下，缺字段时说明原因。"""
    entry, message = service.create_entry(payload.values, staff)
    if entry is None:
        return ActionResult(ok=False, message=message or "登记失败")
    return ActionResult(ok=True, message="场内车辆已登记", entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload, staff: dict = Depends(current_staff)) -> ActionResult:
    """修改核定载重、年检日期等技术档案；只读岗与非归属班组管理员会被驳回。"""
    entry, message = service.update_fields(entry_id, payload.values, staff)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload, staff: dict = Depends(current_staff)) -> ActionResult:
    """对单条场内车辆执行安排维修、安排年检、申请报废；越权代办在服务层驳回。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, staff, payload.remark)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/handover", response_model=ActionResult)
def handover(entry_id: int, payload: EntryPayload, staff: dict = Depends(current_staff)) -> ActionResult:
    """换人交接：现任归属班组管理员发起，接任人必须是车辆管理员，全程留痕。"""
    successor_id = str(payload.values.get("successor_id") or "").strip()
    entry, message = service.handover(entry_id, successor_id=successor_id, staff=staff, remark=payload.remark)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
