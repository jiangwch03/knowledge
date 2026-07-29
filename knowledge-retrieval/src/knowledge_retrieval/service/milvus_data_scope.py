"""向量侧 data_scope → Milvus filter 表达式。"""

from __future__ import annotations

from sqlalchemy import func, or_, select

from knowledge_common.common import get_current_session, with_session
from knowledge_common.common.aspect.data_scope import GetDataScope
from knowledge_common.mapper.do.dept_do import SysDept
from knowledge_common.mapper.do.role_do import SysRoleDept
from knowledge_common.vo.user_vo import CurrentUserModel


class MilvusDataScopeBuilder:
    """将若依 data_scope 语义落到 Milvus 标量 filter（dept_id / user_id）。"""

    @classmethod
    async def build_filter(cls, current_user: CurrentUserModel) -> str:
        user = current_user.user
        if user.admin:
            return ''

        clauses: list[str] = []
        custom_role_ids = [r.role_id for r in user.role if r.data_scope == GetDataScope.DATA_SCOPE_CUSTOM]

        for role in user.role:
            if role.data_scope == GetDataScope.DATA_SCOPE_ALL:
                return ''
            if role.data_scope == GetDataScope.DATA_SCOPE_SELF:
                clauses.append(f'user_id == {int(user.user_id)}')
            elif role.data_scope == GetDataScope.DATA_SCOPE_DEPT:
                if user.dept_id is None:
                    clauses.append('user_id == -1')
                else:
                    clauses.append(f'dept_id == {int(user.dept_id)}')
            elif role.data_scope == GetDataScope.DATA_SCOPE_DEPT_AND_CHILD:
                dept_ids = await cls._dept_and_children(user.dept_id)
                clauses.append(cls._in_expr('dept_id', dept_ids))
            elif role.data_scope == GetDataScope.DATA_SCOPE_CUSTOM:
                dept_ids = await cls._custom_dept_ids(custom_role_ids or [role.role_id])
                clauses.append(cls._in_expr('dept_id', dept_ids))
            else:
                clauses.append('user_id == -1')

        if not clauses:
            return f'user_id == {int(user.user_id)}'
        if len(clauses) == 1:
            return clauses[0]
        return '(' + ' || '.join(clauses) + ')'

    @staticmethod
    def _in_expr(field: str, values: list[int]) -> str:
        if not values:
            return f'{field} == -1'
        joined = ', '.join(str(int(v)) for v in values)
        return f'{field} in [{joined}]'

    @classmethod
    @with_session
    async def _dept_and_children(cls, dept_id: int | None) -> list[int]:
        if dept_id is None:
            return []
        session = get_current_session()
        rows = (
            await session.execute(
                select(SysDept.dept_id).where(
                    or_(SysDept.dept_id == dept_id, func.find_in_set(dept_id, SysDept.ancestors))
                )
            )
        ).scalars().all()
        return [int(x) for x in rows]

    @classmethod
    @with_session
    async def _custom_dept_ids(cls, role_ids: list[int]) -> list[int]:
        if not role_ids:
            return []
        session = get_current_session()
        rows = (
            await session.execute(select(SysRoleDept.dept_id).where(SysRoleDept.role_id.in_(role_ids)))
        ).scalars().all()
        return [int(x) for x in rows]
