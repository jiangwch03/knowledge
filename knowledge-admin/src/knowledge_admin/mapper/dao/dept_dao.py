from collections.abc import Sequence
from typing import Any

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.do.dept_do import SysDept
from knowledge_common.mapper.do.user_do import SysUser
from knowledge_common.vo.dept_vo import DeptModel
from sqlalchemy import ColumnElement, bindparam, func, select, update
from sqlalchemy.util import immutabledict
from knowledge_common.mapper.dao.base_dao import BaseDao


class DeptDao(BaseDao):
    """
    部门管理模块数据库操作层
    """

    @classmethod
    async def get_dept_by_id(cls, dept_id: int) -> SysDept | None:
        """
        根据部门id获取在用部门信息

        :param dept_id: 部门id
        :return: 在用部门信息对象
        """
        db = get_current_session()
        dept_info = (await db.execute(select(SysDept).where(SysDept.dept_id == dept_id))).scalars().first()

        return dept_info

    @classmethod
    async def get_dept_detail_by_id(cls, dept_id: int) -> SysDept | None:
        """
        根据部门id获取部门详细信息

        :param dept_id: 部门id
        :return: 部门信息对象
        """
        db = get_current_session()
        dept_info = (
            (await db.execute(select(SysDept).where(SysDept.dept_id == dept_id, SysDept.del_flag == DeleteFlag.NORMAL.value)))
            .scalars()
            .first()
        )

        return dept_info

    @classmethod
    async def get_dept_detail_by_info(cls, dept: DeptModel) -> SysDept | None:
        """
        根据部门参数获取部门信息

        :param dept: 部门参数对象
        :return: 部门信息对象
        """
        db = get_current_session()
        dept_info = (
            (
                await db.execute(
                    select(SysDept).where(
                        SysDept.parent_id == dept.parent_id if dept.parent_id else True,
                        SysDept.dept_name == dept.dept_name if dept.dept_name else True,
                        SysDept.del_flag == DeleteFlag.NORMAL.value,
                    )
                )
            )
            .scalars()
            .first()
        )

        return dept_info

    @classmethod
    async def get_dept_info_for_edit_option(
        cls, dept_info: DeptModel, data_scope_sql: ColumnElement
    ) -> Sequence[SysDept]:
        """
        获取部门编辑对应的在用部门列表信息

        :param dept_info: 部门对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门列表信息
        """
        db = get_current_session()
        dept_result = (
            (
                await db.execute(
                    select(SysDept)
                    .where(
                        SysDept.dept_id != dept_info.dept_id,
                        ~SysDept.dept_id.in_(
                            select(SysDept.dept_id).where(func.find_in_set(dept_info.dept_id, SysDept.ancestors))
                        ),
                        SysDept.del_flag == DeleteFlag.NORMAL.value,
                        SysDept.status == '0',
                        data_scope_sql,
                    )
                    .order_by(SysDept.order_num)
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        return dept_result

    @classmethod
    async def get_children_dept_dao(cls, dept_id: int) -> Sequence[SysDept]:
        """
        根据部门id查询当前部门的子部门列表信息

        :param dept_id: 部门id
        :return: 子部门信息列表
        """
        db = get_current_session()
        dept_result = (
            (await db.execute(select(SysDept).where(func.find_in_set(dept_id, SysDept.ancestors)))).scalars().all()
        )

        return dept_result

    @classmethod
    async def get_dept_list_for_tree(
        cls, dept_info: DeptModel, data_scope_sql: ColumnElement
    ) -> Sequence[SysDept]:
        """
        获取所有在用部门列表信息

        :param dept_info: 部门对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 在用部门列表信息
        """
        db = get_current_session()
        dept_result = (
            (
                await db.execute(
                    select(SysDept)
                    .where(
                        SysDept.status == '0',
                        SysDept.del_flag == DeleteFlag.NORMAL.value,
                        SysDept.dept_name.like(f'%{dept_info.dept_name}%') if dept_info.dept_name else True,
                        data_scope_sql,
                    )
                    .order_by(SysDept.order_num)
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        return dept_result

    @classmethod
    async def get_dept_list(
        cls, page_object: DeptModel, data_scope_sql: ColumnElement
    ) -> Sequence[SysDept]:
        """
        根据查询参数获取部门列表信息

        :param page_object: 不分页查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门列表信息对象
        """
        db = get_current_session()
        dept_result = (
            (
                await db.execute(
                    select(SysDept)
                    .where(
                        SysDept.del_flag == DeleteFlag.NORMAL.value,
                        SysDept.dept_id == page_object.dept_id if page_object.dept_id is not None else True,
                        SysDept.status == page_object.status if page_object.status else True,
                        SysDept.dept_name.like(f'%{page_object.dept_name}%') if page_object.dept_name else True,
                        data_scope_sql,
                    )
                    .order_by(SysDept.order_num)
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        return dept_result

    @classmethod
    async def add_dept_dao(cls, dept: DeptModel) -> SysDept:
        """
        新增部门数据库操作

        :param dept: 部门对象
        :return: 新增校验结果
        """
        db = get_current_session()
        db_dept = SysDept(**dept.model_dump())
        db.add(db_dept)
        await db.flush()

        return db_dept

    @classmethod
    async def edit_dept_dao(cls, dept: dict[str, Any]) -> None:
        """
        编辑部门数据库操作

        :param dept: 需要更新的部门字典
        :return: 编辑校验结果
        """
        db = get_current_session()
        await db.execute(update(SysDept), [dept])

    @classmethod
    async def update_dept_children_dao(cls, update_dept: list[dict]) -> None:
        """
        更新子部门信息

        :param update_dept: 需要更新的部门列表
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(SysDept)
            .where(SysDept.dept_id == bindparam('dept_id'))
            .values(
                {
                    'dept_id': bindparam('dept_id'),
                    'ancestors': bindparam('ancestors'),
                }
            ),
            update_dept,
            execution_options=immutabledict({'synchronize_session': None}),
        )

    @classmethod
    async def update_dept_status_normal_dao(cls, dept_id_list: list[int]) -> None:
        """
        批量更新部门状态为正常

        :param dept_id_list: 部门id列表
        :return:
        """
        db = get_current_session()
        await db.execute(update(SysDept).where(SysDept.dept_id.in_(dept_id_list)).values(status='0'))

    @classmethod
    async def delete_dept_dao(cls, dept: DeptModel) -> None:
        """
        删除部门数据库操作

        :param dept: 部门对象
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(SysDept)
            .where(SysDept.dept_id == dept.dept_id)
            .values(del_flag=DeleteFlag.DELETED.value, update_by=dept.update_by, update_time=dept.update_time)
        )

    @classmethod
    async def count_normal_children_dept_dao(cls, dept_id: int) -> int | None:
        """
        根据部门id查询查询所有子部门（正常状态）的数量

        :param dept_id: 部门id
        :return: 所有子部门（正常状态）的数量
        """
        db = get_current_session()
        normal_children_dept_count = (
            await db.execute(
                select(func.count('*'))
                .select_from(SysDept)
                .where(SysDept.status == '0', SysDept.del_flag == DeleteFlag.NORMAL.value, func.find_in_set(dept_id, SysDept.ancestors))
            )
        ).scalar()

        return normal_children_dept_count

    @classmethod
    async def count_children_dept_dao(cls, dept_id: int) -> int | None:
        """
        根据部门id查询查询所有子部门（所有状态）的数量

        :param dept_id: 部门id
        :return: 所有子部门（所有状态）的数量
        """
        db = get_current_session()
        children_dept_count = (
            await db.execute(
                select(func.count('*'))
                .select_from(SysDept)
                .where(SysDept.del_flag == DeleteFlag.NORMAL.value, SysDept.parent_id == dept_id)
                .limit(1)
            )
        ).scalar()

        return children_dept_count

    @classmethod
    async def count_dept_user_dao(cls, dept_id: int) -> int | None:
        """
        根据部门id查询查询部门下的用户数量

        :param dept_id: 部门id
        :return: 部门下的用户数量
        """
        db = get_current_session()
        dept_user_count = (
            await db.execute(
                select(func.count('*')).select_from(SysUser).where(SysUser.dept_id == dept_id, SysUser.del_flag == DeleteFlag.NORMAL.value)
            )
        ).scalar()

        return dept_user_count
