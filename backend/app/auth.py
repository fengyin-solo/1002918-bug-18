"""会话与授权：身份落到「工号 + 岗位 + 班组」，场车管理的每一项操作都按此判定。

演示环境没有登录页，前端通过 X-Operator-Id 请求头切换当前操作人；
不带请求头时默认给一个车辆管理员身份，保证克隆下来直接能起。
"""
from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

ROLE_ADMIN = "车辆管理员"
ROLE_READONLY = "只读岗"
ROLE_DRIVER = "驾驶员"

#: 演示用人员名册：真实项目里这里换成用户中心/数据库查询
STAFF: list[dict[str, str]] = [
    {"id": "U001", "姓名": "王强", "班组": "甲班", "岗位": ROLE_ADMIN},
    {"id": "U002", "姓名": "赵敏", "班组": "甲班", "岗位": ROLE_READONLY},
    {"id": "U003", "姓名": "赵六", "班组": "甲班", "岗位": ROLE_DRIVER},
    {"id": "U006", "姓名": "孙七", "班组": "甲班", "岗位": ROLE_DRIVER},
    {"id": "U004", "姓名": "李娜", "班组": "乙班", "岗位": ROLE_ADMIN},
    {"id": "U005", "姓名": "钱进", "班组": "乙班", "岗位": ROLE_READONLY},
    {"id": "U007", "姓名": "周九", "班组": "乙班", "岗位": ROLE_DRIVER},
    {"id": "U008", "姓名": "吴十", "班组": "乙班", "岗位": ROLE_DRIVER},
]

STAFF_INDEX: dict[str, dict[str, str]] = {item["id"]: item for item in STAFF}

DEFAULT_STAFF_ID = "U001"


def public_staff(item: dict[str, str]) -> dict[str, str]:
    """对外暴露的人员信息：名册本身不含密钥，直接按条目返回。"""
    return dict(item)


def current_staff(x_operator_id: str | None = Header(default=None)) -> dict[str, str]:
    """FastAPI 依赖：解析当前操作人，工号无法识别时按 401 驳回。"""
    staff_id = (x_operator_id or DEFAULT_STAFF_ID).strip()
    staff = STAFF_INDEX.get(staff_id)
    if staff is None:
        raise HTTPException(status_code=401, detail=f"工号 {staff_id} 无法识别，请重新选择登录身份")
    return dict(staff)
