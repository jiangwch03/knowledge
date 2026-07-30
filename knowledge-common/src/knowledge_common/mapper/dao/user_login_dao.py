from collections.abc import Sequence

from sqlalchemy import and_, select

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.do.dept_do import SysDept
from knowledge_common.mapper.do.menu_do import SysMenu
from knowledge_common.mapper.do.post_do import SysPost
from knowledge_common.mapper.do.role_do import SysRole, SysRoleMenu
from knowledge_common.mapper.do.user_do import SysUser, SysUserPost, SysUserRole
from knowledge_common.mapper.dao.base_dao import BaseDao


class UserDao(BaseDao):

    @classmethod
    async def get_user_by_id(cls, user_id: int) -> dict[str, Sequence[SysUser | SysDept | SysRole | SysMenu] | SysUser | SysDept | None]:
        """
        根据user_id获取用户信息

        :param user_id: 用户id
        :return: 当前user_id的用户信息对象
        """
        db = get_current_session()
        query_user_basic_info = (
            (
                await db.execute(
                    select(SysUser)
                    .where(SysUser.status == '0', SysUser.del_flag == DeleteFlag.NORMAL.value, SysUser.user_id == user_id)
                    .distinct()
                )
            )
            .scalars()
            .first()
        )
        query_user_dept_info = (
            (
                await db.execute(
                    select(SysDept)
                    .select_from(SysUser)
                    .where(SysUser.status == '0', SysUser.del_flag == DeleteFlag.NORMAL.value, SysUser.user_id == user_id)
                    .join(
                        SysDept,
                        and_(SysUser.dept_id == SysDept.dept_id, SysDept.status == '0', SysDept.del_flag == DeleteFlag.NORMAL.value),
                    )
                    .distinct()
                )
            )
            .scalars()
            .first()
        )
        query_user_role_info = (
            (
                await db.execute(
                    select(SysRole)
                    .select_from(SysUser)
                    .where(SysUser.status == '0', SysUser.del_flag == DeleteFlag.NORMAL.value, SysUser.user_id == user_id)
                    .join(SysUserRole, SysUser.user_id == SysUserRole.user_id, isouter=True)
                    .join(
                        SysRole,
                        and_(SysUserRole.role_id == SysRole.role_id, SysRole.status == '0', SysRole.del_flag == DeleteFlag.NORMAL.value),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        query_user_post_info = (
            (
                await db.execute(
                    select(SysPost)
                    .select_from(SysUser)
                    .where(SysUser.status == '0', SysUser.del_flag == DeleteFlag.NORMAL.value, SysUser.user_id == user_id)
                    .join(SysUserPost, SysUser.user_id == SysUserPost.user_id, isouter=True)
                    .join(SysPost, and_(SysUserPost.post_id == SysPost.post_id, SysPost.status == '0'))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        role_id_list = [item.role_id for item in query_user_role_info]
        if 1 in role_id_list:
            query_user_menu_info = (
                (await db.execute(select(SysMenu).where(SysMenu.status == '0').distinct())).scalars().all()
            )
        else:
            query_user_menu_info = (
                (
                    await db.execute(
                        select(SysMenu)
                        .select_from(SysUser)
                        .where(SysUser.status == '0', SysUser.del_flag == DeleteFlag.NORMAL.value, SysUser.user_id == user_id)
                        .join(SysUserRole, SysUser.user_id == SysUserRole.user_id, isouter=True)
                        .join(
                            SysRole,
                            and_(
                                SysUserRole.role_id == SysRole.role_id, SysRole.status == '0', SysRole.del_flag == DeleteFlag.NORMAL.value
                            ),
                            isouter=True,
                        )
                        .join(SysRoleMenu, SysRole.role_id == SysRoleMenu.role_id, isouter=True)
                        .join(SysMenu, and_(SysRoleMenu.menu_id == SysMenu.menu_id, SysMenu.status == '0'))
                        .order_by(SysMenu.order_num)
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )

        results = {
            'user_basic_info': query_user_basic_info,
            'user_dept_info': query_user_dept_info,
            'user_role_info': query_user_role_info,
            'user_post_info': query_user_post_info,
            'user_menu_info': query_user_menu_info,
        }

        return results
