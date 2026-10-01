"""会话接口：向前端提供可选操作人名册与当前身份，便于演示「换个人/换个岗位」。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import STAFF, current_staff, public_staff

router = APIRouter(prefix="/api/session", tags=["会话"])


@router.get("/staff")
def list_staff() -> dict[str, object]:
    """人员名册：工号、姓名、班组、岗位。"""
    return {"items": [public_staff(item) for item in STAFF]}


@router.get("/me")
def whoami(staff: dict = Depends(current_staff)) -> dict[str, str]:
    """按 X-Operator-Id 解析出的当前操作人。"""
    return public_staff(staff)
