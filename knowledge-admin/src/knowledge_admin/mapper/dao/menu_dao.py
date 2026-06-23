from collections.abc import Sequence
from typing import Any

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.do.menu_do import SysMenu
from knowledge_common.mapper.do.role_do import SysRole, SysRoleMenu
from knowledge_common.mapper.do.user_do import SysUser, SysUserRole
from sqlalchemy import and_, delete, func, select, update

from knowledge_admin.vo.menu_vo import MenuModel, MenuQueryModel


class MenuDao:
    """
    菜单管理模块数据库操作层
    """

    @classmethod
    async def get_menu_detail_by_id(cls, menu_id: int) -> SysMenu | None:
        """
        根据菜单id获取菜单详细信息

        :param menu_id: 菜单id
        :return: 菜单信息对象
        """
        db = get_current_session()
        menu_info = (await db.execute(select(SysMenu).where(SysMenu.menu_id == menu_id))).scalars().first()

        return menu_info

    @classmethod
    async def get_menu_detail_by_info(cls, menu: MenuModel) -> SysMenu | None:
        """
        根据菜单参数获取菜单信息

        :param menu: 菜单参数对象
        :return: 菜单信息对象
        """
        db = get_current_session()
        menu_info = (
            (
                await db.execute(
                    select(SysMenu).where(
                        SysMenu.parent_id == menu.parent_id if menu.parent_id else True,
                        SysMenu.menu_name == menu.menu_name if menu.menu_name else True,
                        SysMenu.menu_type == menu.menu_type if menu.menu_type else True,
                    )
                )
            )
            .scalars()
            .first()
        )

        return menu_info

    @classmethod
    async def get_menu_list_for_tree(cls, user_id: int, role: list) -> Sequence[SysMenu]:
        """
        根据角色信息获取所有在用菜单列表信息

        :param user_id: 用户id
        :param role: 用户角色列表信息
        :return: 菜单列表信息
        """
        db = get_current_session()
        role_id_list = [item.role_id for item in role]
        if 1 in role_id_list:
            menu_query_all = (
                (await db.execute(select(SysMenu).where(SysMenu.status == '0').order_by(SysMenu.order_num).distinct()))
                .scalars()
                .all()
            )
        else:
            menu_query_all = (
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

        return menu_query_all

    @classmethod
    async def get_menu_list(
        cls, page_object: MenuQueryModel, user_id: int, role: list
    ) -> Sequence[SysMenu]:
        """
        根据查询参数获取菜单列表信息

        :param page_object: 不分页查询参数对象
        :param user_id: 用户id
        :param role: 用户角色列表
        :return: 菜单列表信息对象
        """
        db = get_current_session()
        role_id_list = [item.role_id for item in role]
        if 1 in role_id_list:
            menu_query_all = (
                (
                    await db.execute(
                        select(SysMenu)
                        .where(
                            SysMenu.status == page_object.status if page_object.status else True,
                            SysMenu.menu_name.like(f'%{page_object.menu_name}%') if page_object.menu_name else True,
                        )
                        .order_by(SysMenu.order_num)
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
        else:
            menu_query_all = (
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
                        .join(
                            SysMenu,
                            and_(
                                SysRoleMenu.menu_id == SysMenu.menu_id,
                                SysMenu.status == page_object.status if page_object.status else True,
                                SysMenu.menu_name.like(f'%{page_object.menu_name}%') if page_object.menu_name else True,
                            ),
                        )
                        .order_by(SysMenu.order_num)
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )

        return menu_query_all

    @classmethod
    async def add_menu_dao(cls, menu: MenuModel) -> SysMenu:
        """
        新增菜单数据库操作

        :param menu: 菜单对象
        :return:
        """
        db = get_current_session()
        db_menu = SysMenu(**menu.model_dump())
        db.add(db_menu)
        await db.flush()

        return db_menu

    @classmethod
    async def edit_menu_dao(cls, menu: dict[str, Any]) -> None:
        """
        编辑菜单数据库操作

        :param menu: 需要更新的菜单字典
        :return:
        """
        db = get_current_session()
        await db.execute(update(SysMenu), [menu])

    @classmethod
    async def delete_menu_dao(cls, menu: MenuModel) -> None:
        """
        删除菜单数据库操作

        :param menu: 菜单对象
        :return:
        """
        db = get_current_session()
        await db.execute(delete(SysMenu).where(SysMenu.menu_id.in_([menu.menu_id])))

    @classmethod
    async def has_child_by_menu_id_dao(cls, menu_id: int) -> int | None:
        """
        根据菜单id查询菜单关联子菜单的数量

        :param menu_id: 菜单id
        :return: 菜单关联子菜单的数量
        """
        db = get_current_session()
        menu_count = (
            await db.execute(select(func.count('*')).select_from(SysMenu).where(SysMenu.parent_id == menu_id))
        ).scalar()

        return menu_count

    @classmethod
    async def check_menu_exist_role_dao(cls, menu_id: int) -> int | None:
        """
        根据菜单id查询菜单关联角色数量

        :param menu_id: 菜单id
        :return: 菜单关联角色数量
        """
        db = get_current_session()
        role_count = (
            await db.execute(select(func.count('*')).select_from(SysRoleMenu).where(SysRoleMenu.menu_id == menu_id))
        ).scalar()

        return role_count
