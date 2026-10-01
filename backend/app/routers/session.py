"""会话接口：向前端提供可选在岗身份名册。

本平台为单机演示后台，身份切换由前端选择后经 X-Operator-Id 请求头回传，
后端不保存会话状态，所有授权均以请求头解析出的操作人为准。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.identity import TEAM_DRIVERS, USERS, user_public

router = APIRouter(prefix="/api/session", tags=["会话与身份"])


@router.get("/users")
def list_users() -> dict[str, Any]:
    """返回可切换的在岗操作人，以及各班组在册驾驶员名册。"""
    return {
        "users": [user_public(user) for user in USERS.values()],
        "drivers": TEAM_DRIVERS,
    }
