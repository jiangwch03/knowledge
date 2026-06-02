from typing import Any

from knowledge_common.entity.do.menu_do import SysMenu
from knowledge_common.entity.do.post_do import SysPost
from knowledge_common.entity.do.user_do import SysUser, SysUserPost, SysUserRole
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_common.entity.do.dept_do import SysDept
from knowledge_common.entity.do.role_do import SysRole, SysRoleMenu


class UserDao:

    @classmethod
    async def get_user_by_id(cls, db: AsyncSession, user_id: int) -> dict[str, Any]:
        """
        根据user_id获取用户信息

        :param db: orm对象
        :param user_id: 用户id
        :return: 当前user_id的用户信息对象
        """
        query_user_basic_info = (
            (
                await db.execute(
                    select(SysUser)
                    .where(SysUser.status == '0', SysUser.del_flag == '0', SysUser.user_id == user_id)
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
                    .where(SysUser.status == '0', SysUser.del_flag == '0', SysUser.user_id == user_id)
                    .join(
                        SysDept,
                        and_(SysUser.dept_id == SysDept.dept_id, SysDept.status == '0', SysDept.del_flag == '0'),
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
                    .where(SysUser.status == '0', SysUser.del_flag == '0', SysUser.user_id == user_id)
                    .join(SysUserRole, SysUser.user_id == SysUserRole.user_id, isouter=True)
                    .join(
                        SysRole,
                        and_(SysUserRole.role_id == SysRole.role_id, SysRole.status == '0', SysRole.del_flag == '0'),
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
                    .where(SysUser.status == '0', SysUser.del_flag == '0', SysUser.user_id == user_id)
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
                        .where(SysUser.status == '0', SysUser.del_flag == '0', SysUser.user_id == user_id)
                        .join(SysUserRole, SysUser.user_id == SysUserRole.user_id, isouter=True)
                        .join(
                            SysRole,
                            and_(
                                SysUserRole.role_id == SysRole.role_id, SysRole.status == '0', SysRole.del_flag == '0'
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
