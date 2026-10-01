"""身份与授权：把操作人落实到「人 + 角色 + 班组」。

场车归属判定必须落到人，因此所有写操作都从请求头 X-Operator-Id 解析当前操作人，
再由场车服务按「角色是否为车辆管理员、班组是否为车辆归属班组」逐条鉴权。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from fastapi import Header, HTTPException

ROLE_ADMIN = "车辆管理员"
ROLE_READONLY = "只读岗"
ROLE_DRIVER = "驾驶员"

OPERATOR_HEADER = "X-Operator-Id"
DEFAULT_OPERATOR_ID = "u5"  # 未带头时按最保守的只读岗处理，宁可不放权


@dataclass(frozen=True)
class User:
    """登录操作人：角色决定能干什么，班组决定能动哪台车。"""

    id: str
    name: str
    role: str
    team: str
    title: str

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_readonly(self) -> bool:
        return self.role == ROLE_READONLY


# 示例账号：三个班组各配车辆管理员，另有只读岗与驾驶员，用于演示越权拦截。
USERS: dict[str, User] = {
    "u1": User("u1", "张工", ROLE_ADMIN, "甲班", "甲班车辆管理员"),
    "u2": User("u2", "王强", ROLE_ADMIN, "乙班", "乙班车辆管理员"),
    "u3": User("u3", "赵磊", ROLE_ADMIN, "丙班", "丙班车辆管理员"),
    "u4": User("u4", "李大力", ROLE_DRIVER, "甲班", "叉车驾驶员"),
    "u5": User("u5", "周敏", ROLE_READONLY, "安环科", "只读台账员"),
}

# 各班组在册驾驶员名册：交接只能交给本班组持证驾驶员，不能随手填名字。
TEAM_DRIVERS: dict[str, list[str]] = {
    "甲班": ["李大力", "陈涛"],
    "乙班": ["马骏", "郭林"],
    "丙班": ["赵磊", "钱坤"],
}


def get_user(operator_id: str | None) -> User:
    """按操作人 id 取身份；缺失时回落只读岗，身份无法识别则拒绝。"""
    if not operator_id:
        return USERS[DEFAULT_OPERATOR_ID]
    user = USERS.get(operator_id.strip())
    if user is None:
        raise HTTPException(status_code=401, detail=f"操作人身份「{operator_id}」无法识别，请重新切换在岗身份")
    return user


def current_user(x_operator_id: str | None = Header(default=None, alias=OPERATOR_HEADER)) -> User:
    """FastAPI 依赖：把请求头解析成当前操作人。"""
    return get_user(x_operator_id)


def now_ts() -> str:
    """操作留痕时间戳。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def user_public(user: User) -> dict[str, str]:
    return asdict(user)
