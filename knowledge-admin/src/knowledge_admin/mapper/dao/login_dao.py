from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.do.dept_do import SysDept
from knowledge_common.mapper.do.user_do import SysUser
from sqlalchemy import Row, and_, select


async def login_by_account(user_name: str) -> Row[tuple[SysUser, SysDept]] | None:
    """
    根据用户名查询用户信息

    :param user_name: 用户名
    :return: 用户对象
    """
    db = get_current_session()
    user = (
        await db.execute(
            select(SysUser, SysDept)
            .where(SysUser.user_name == user_name, SysUser.del_flag == DeleteFlag.NORMAL.value)
            .join(
                SysDept,
                and_(SysUser.dept_id == SysDept.dept_id, SysDept.status == '0', SysDept.del_flag == DeleteFlag.NORMAL.value),
                isouter=True,
            )
            .distinct()
        )
    ).first()

    return user
