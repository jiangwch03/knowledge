from typing import Any

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.mapper.do.post_do import SysPost
from knowledge_common.mapper.do.user_do import SysUserPost
from knowledge_common.vo.post_vo import PostModel, PostPageQueryModel
from knowledge_common.utils.page_util import PageUtil
from sqlalchemy import delete, func, select, update


class PostDao:
    """
    岗位管理模块数据库操作层
    """

    @classmethod
    async def get_post_by_id(cls, post_id: int) -> SysPost | None:
        """
        根据岗位id获取在用岗位详细信息

        :param post_id: 岗位id
        :return: 在用岗位信息对象
        """
        db = get_current_session()
        post_info = (
            (await db.execute(select(SysPost).where(SysPost.post_id == post_id, SysPost.status == '0')))
            .scalars()
            .first()
        )

        return post_info

    @classmethod
    async def get_post_detail_by_id(cls, post_id: int) -> SysPost | None:
        """
        根据岗位id获取岗位详细信息

        :param post_id: 岗位id
        :return: 岗位信息对象
        """
        db = get_current_session()
        post_info = (await db.execute(select(SysPost).where(SysPost.post_id == post_id))).scalars().first()

        return post_info

    @classmethod
    async def get_post_detail_by_info(cls, post: PostModel) -> SysPost | None:
        """
        根据岗位参数获取岗位信息

        :param post: 岗位参数对象
        :return: 岗位信息对象
        """
        db = get_current_session()
        post_info = (
            (
                await db.execute(
                    select(SysPost).where(
                        SysPost.post_name == post.post_name if post.post_name else True,
                        SysPost.post_code == post.post_code if post.post_code else True,
                        SysPost.post_sort == post.post_sort if post.post_sort else True,
                    )
                )
            )
            .scalars()
            .first()
        )

        return post_info

    @classmethod
    async def get_post_list(
        cls, query_object: PostPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取岗位列表信息

        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 岗位列表信息对象
        """
        db = get_current_session()
        query = (
            select(SysPost)
            .where(
                SysPost.post_code.like(f'%{query_object.post_code}%') if query_object.post_code else True,
                SysPost.post_name.like(f'%{query_object.post_name}%') if query_object.post_name else True,
                SysPost.status == query_object.status if query_object.status else True,
            )
            .order_by(SysPost.post_sort)
            .distinct()
        )
        post_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            query, query_object.page_num, query_object.page_size, is_page
        )

        return post_list

    @classmethod
    async def add_post_dao(cls, post: PostModel) -> SysPost:
        """
        新增岗位数据库操作

        :param post: 岗位对象
        :return:
        """
        db = get_current_session()
        db_post = SysPost(**post.model_dump())
        db.add(db_post)
        await db.flush()

        return db_post

    @classmethod
    async def edit_post_dao(cls, post: dict) -> None:
        """
        编辑岗位数据库操作

        :param post: 需要更新的岗位字典
        :return:
        """
        db = get_current_session()
        await db.execute(update(SysPost), [post])

    @classmethod
    async def delete_post_dao(cls, post: PostModel) -> None:
        """
        删除岗位数据库操作

        :param post: 岗位对象
        :return:
        """
        db = get_current_session()
        await db.execute(delete(SysPost).where(SysPost.post_id.in_([post.post_id])))

    @classmethod
    async def count_user_post_dao(cls, post_id: int) -> int | None:
        """
        根据岗位id查询岗位关联的用户数量

        :param post_id: 岗位id
        :return: 岗位关联的用户数量
        """
        db = get_current_session()
        user_post_count = (
            await db.execute(select(func.count('*')).select_from(SysUserPost).where(SysUserPost.post_id == post_id))
        ).scalar()

        return user_post_count
