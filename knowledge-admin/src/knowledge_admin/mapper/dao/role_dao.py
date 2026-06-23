from collections.abc import Sequence
from datetime import datetime, time
from typing import Any

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.common.vo import PageModel
from knowledge_common.mapper.do.dept_do import SysDept
from knowledge_common.mapper.do.menu_do import SysMenu
from knowledge_common.mapper.do.role_do import SysRole, SysRoleDept, SysRoleMenu
from knowledge_common.mapper.do.user_do import SysUser, SysUserRole
from knowledge_common.utils.page_util import PageUtil
from knowledge_common.vo.role_vo import RoleDeptModel, RoleMenuModel, RoleModel, RolePageQueryModel
from sqlalchemy import ColumnElement, and_, delete, desc, func, select, update


class RoleDao:
    """
    角色管理模块数据库操作层
    """

    @classmethod
    async def get_role_by_name(cls, role_name: str) -> SysRole | None:
        """
        根据角色名获取在用角色信息

        :param role_name: 角色名
        :return: 当前角色名的角色信息对象
        """
        db = get_current_session()
        query_role_info = (
            (
                await db.execute(
                    select(SysRole)
                    .where(SysRole.status == '0', SysRole.del_flag == DeleteFlag.NORMAL.value, SysRole.role_name == role_name)
                    .order_by(desc(SysRole.create_time))
                    .distinct()
                )
            )
            .scalars()
            .first()
        )

        return query_role_info

    @classmethod
    async def get_role_by_info(cls, role: RoleModel) -> SysRole | None:
        """
        根据角色参数获取角色信息

        :param role: 角色参数
        :return: 当前角色参数的角色信息对象
        """
        db = get_current_session()
        query_role_info = (
            (
                await db.execute(
                    select(SysRole)
                    .where(
                        SysRole.del_flag == DeleteFlag.NORMAL.value,
                        SysRole.role_name == role.role_name if role.role_name else True,
                        SysRole.role_key == role.role_key if role.role_key else True,
                    )
                    .order_by(desc(SysRole.create_time))
                    .distinct()
                )
            )
            .scalars()
            .first()
        )

        return query_role_info

    @classmethod
    async def get_role_by_id(cls, role_id: int) -> SysRole | None:
        """
        根据角色id获取在用角色信息

        :param role_id: 角色id
        :return: 当前角色id的角色信息对象
        """
        db = get_current_session()
        role_info = (
            (
                await db.execute(
                    select(SysRole).where(SysRole.role_id == role_id, SysRole.status == '0', SysRole.del_flag == DeleteFlag.NORMAL.value)
                )
            )
            .scalars()
            .first()
        )

        return role_info

    @classmethod
    async def get_role_detail_by_id(cls, role_id: int) -> SysRole | None:
        """
        根据role_id获取角色详细信息

        :param role_id: 角色id
        :return: 当前role_id的角色信息对象
        """
        db = get_current_session()
        query_role_info = (
            (await db.execute(select(SysRole).where(SysRole.del_flag == DeleteFlag.NORMAL.value, SysRole.role_id == role_id).distinct()))
            .scalars()
            .first()
        )

        return query_role_info

    @classmethod
    async def get_role_select_option_dao(cls) -> Sequence[SysRole]:
        """
        获取编辑页面对应的在用角色列表信息

        :return: 角色列表信息
        """
        db = get_current_session()
        role_info = (
            (
                await db.execute(
                    select(SysRole).where(SysRole.role_id != 1, SysRole.status == '0', SysRole.del_flag == DeleteFlag.NORMAL.value)
                )
            )
            .scalars()
            .all()
        )

        return role_info

    @classmethod
    async def get_role_list(
        cls, query_object: RolePageQueryModel, data_scope_sql: ColumnElement, is_page: bool = False
    ) -> PageModel | list:
        """
        根据查询参数获取角色列表信息

        :param query_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 角色列表信息对象
        """
        db = get_current_session()
        query = (
            select(SysRole)
            .join(SysUserRole, SysUserRole.role_id == SysRole.role_id, isouter=True)
            .join(SysUser, SysUser.user_id == SysUserRole.user_id, isouter=True)
            .join(SysDept, SysDept.dept_id == SysUser.dept_id, isouter=True)
            .where(
                SysRole.del_flag == DeleteFlag.NORMAL.value,
                SysRole.role_id == query_object.role_id if query_object.role_id is not None else True,
                SysRole.role_name.like(f'%{query_object.role_name}%') if query_object.role_name else True,
                SysRole.role_key.like(f'%{query_object.role_key}%') if query_object.role_key else True,
                SysRole.status == query_object.status if query_object.status else True,
                SysRole.create_time.between(
                    datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                    datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)),
                )
                if query_object.begin_time and query_object.end_time
                else True,
                data_scope_sql,
            )
            .order_by(SysRole.role_sort)
            .distinct()
        )
        role_list = await PageUtil.paginate(
            query, query_object.page_num, query_object.page_size, is_page
        )

        return role_list

    @classmethod
    async def add_role_dao(cls, role: RoleModel) -> SysRole:
        """
        新增角色数据库操作

        :param role: 角色对象
        :return:
        """
        db = get_current_session()
        db_role = SysRole(**role.model_dump(exclude={'admin'}))
        db.add(db_role)
        await db.flush()

        return db_role

    @classmethod
    async def edit_role_dao(cls, role: dict[str, Any]) -> None:
        """
        编辑角色数据库操作

        :param role: 需要更新的角色字典
        :return:
        """
        db = get_current_session()
        await db.execute(update(SysRole), [role])

    @classmethod
    async def delete_role_dao(cls, role: RoleModel) -> None:
        """
        删除角色数据库操作

        :param role: 角色对象
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(SysRole)
            .where(SysRole.role_id == role.role_id)
            .values(del_flag=DeleteFlag.DELETED.value, update_by=role.update_by, update_time=role.update_time)
        )

    @classmethod
    async def get_role_menu_dao(cls, role: RoleModel) -> Sequence[SysMenu]:
        """
        根据角色id获取角色菜单关联列表信息

        :param role: 角色对象
        :return: 角色菜单关联列表信息
        """
        db = get_current_session()
        role_menu_query_all = (
            (
                await db.execute(
                    select(SysMenu)
                    .join(SysRoleMenu, SysRoleMenu.menu_id == SysMenu.menu_id)
                    .where(
                        SysRoleMenu.role_id == role.role_id,
                        ~SysMenu.menu_id.in_(
                            select(SysMenu.parent_id)
                            .select_from(SysMenu)
                            .join(
                                SysRoleMenu,
                                and_(SysRoleMenu.menu_id == SysMenu.menu_id, SysRoleMenu.role_id == role.role_id),
                            )
                        )
                        if role.menu_check_strictly
                        else True,
                    )
                    .order_by(SysMenu.parent_id, SysMenu.order_num)
                )
            )
            .scalars()
            .all()
        )

        return role_menu_query_all

    @classmethod
    async def add_role_menu_dao(cls, role_menu: RoleMenuModel) -> None:
        """
        新增角色菜单关联信息数据库操作

        :param role_menu: 用户角色菜单关联对象
        :return:
        """
        db = get_current_session()
        db_role_menu = SysRoleMenu(**role_menu.model_dump())
        db.add(db_role_menu)

    @classmethod
    async def delete_role_menu_dao(cls, role_menu: RoleMenuModel) -> None:
        """
        删除角色菜单关联信息数据库操作

        :param role_menu: 角色菜单关联对象
        :return:
        """
        db = get_current_session()
        await db.execute(delete(SysRoleMenu).where(SysRoleMenu.role_id.in_([role_menu.role_id])))

    @classmethod
    async def get_role_dept_dao(cls, role: RoleModel) -> Sequence[SysDept]:
        """
        根据角色id获取角色部门关联列表信息

        :param role: 角色对象
        :return: 角色部门关联列表信息
        """
        db = get_current_session()
        role_dept_query_all = (
            (
                await db.execute(
                    select(SysDept)
                    .join(SysRoleDept, SysRoleDept.dept_id == SysDept.dept_id)
                    .where(
                        SysRoleDept.role_id == role.role_id,
                        ~SysDept.dept_id.in_(
                            select(SysDept.parent_id)
                            .select_from(SysDept)
                            .join(
                                SysRoleDept,
                                and_(SysRoleDept.dept_id == SysDept.dept_id, SysRoleDept.role_id == role.role_id),
                            )
                        )
                        if role.dept_check_strictly
                        else True,
                    )
                    .order_by(SysDept.parent_id, SysDept.order_num)
                )
            )
            .scalars()
            .all()
        )

        return role_dept_query_all

    @classmethod
    async def add_role_dept_dao(cls, role_dept: RoleDeptModel) -> None:
        """
        新增角色部门关联信息数据库操作

        :param role_dept: 用户角色部门关联对象
        :return:
        """
        db = get_current_session()
        db_role_dept = SysRoleDept(**role_dept.dict())
        db.add(db_role_dept)

    @classmethod
    async def delete_role_dept_dao(cls, role_dept: RoleDeptModel) -> None:
        """
        删除角色部门关联信息数据库操作

        :param role_dept: 角色部门关联对象
        :return:
        """
        db = get_current_session()
        await db.execute(delete(SysRoleDept).where(SysRoleDept.role_id.in_([role_dept.role_id])))

    @classmethod
    async def count_user_role_dao(cls, role_id: int) -> int | None:
        """
        根据角色id查询角色关联用户数量

        :param role_id: 角色id
        :return: 角色关联用户数量
        """
        db = get_current_session()
        user_count = (
            await db.execute(select(func.count('*')).select_from(SysUserRole).where(SysUserRole.role_id == role_id))
        ).scalar()

        return user_count
