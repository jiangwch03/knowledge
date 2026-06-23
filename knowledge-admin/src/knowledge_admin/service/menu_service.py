from collections.abc import Sequence
from typing import Any

from knowledge_common.common.constant import CommonConstant, MenuConstant
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel
from knowledge_common.exceptions.exception import ServiceException, ServiceWarning
from knowledge_common.mapper.do.menu_do import SysMenu
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.utils.string_util import StringUtil
from knowledge_common.vo.role_vo import RoleMenuQueryModel
from knowledge_common.vo.user_vo import CurrentUserModel

from knowledge_admin.mapper.dao.menu_dao import MenuDao
from knowledge_admin.mapper.dao.role_dao import RoleDao
from knowledge_admin.vo.menu_vo import DeleteMenuModel, MenuModel, MenuQueryModel, MenuTreeModel


class MenuService:
    """
    菜单管理模块服务层
    """

    @classmethod
    async def get_menu_tree_services(
        cls, current_user: CurrentUserModel | None = None
    ) -> list[dict[str, Any]]:
        """
        获取菜单树信息service

        :param current_user: 当前用户对象
        :return: 菜单树信息对象
        """
        menu_list_result = await MenuDao.get_menu_list_for_tree(
            current_user.user.user_id, current_user.user.role
        )
        menu_tree_model_result = cls.list_to_tree(menu_list_result)
        menu_tree_result = [menu.model_dump(exclude_unset=True, by_alias=True) for menu in menu_tree_model_result]

        return menu_tree_result

    @classmethod
    async def get_role_menu_tree_services(
        cls, role_id: int, current_user: CurrentUserModel | None = None
    ) -> RoleMenuQueryModel:
        """
        根据角色id获取菜单树信息service

        :param role_id: 角色id
        :param current_user: 当前用户对象
        :return: 当前角色id的菜单树信息对象
        """
        menu_list_result = await MenuDao.get_menu_list_for_tree(
            current_user.user.user_id, current_user.user.role
        )
        menu_tree_result = cls.list_to_tree(menu_list_result)
        role = await RoleDao.get_role_detail_by_id(role_id)
        role_menu_list = await RoleDao.get_role_menu_dao(role)
        checked_keys = [row.menu_id for row in role_menu_list]
        result = RoleMenuQueryModel(menus=menu_tree_result, checkedKeys=checked_keys)

        return result

    @classmethod
    async def get_menu_list_services(
        cls, page_object: MenuQueryModel, current_user: CurrentUserModel | None = None
    ) -> list[dict[str, Any]]:
        """
        获取菜单列表信息service

        :param page_object: 分页查询参数对象
        :param current_user: 当前用户对象
        :return: 菜单列表信息对象
        """
        menu_list_result = await MenuDao.get_menu_list(
            page_object, current_user.user.user_id, current_user.user.role
        )

        return CamelCaseUtil.transform_result(menu_list_result)

    @classmethod
    async def check_menu_name_unique_services(cls, page_object: MenuModel) -> bool:
        """
        校验菜单名称是否唯一service

        :param page_object: 菜单对象
        :return: 校验结果
        """
        menu_id = -1 if page_object.menu_id is None else page_object.menu_id
        menu = await MenuDao.get_menu_detail_by_info(MenuModel(menuName=page_object.menu_name))
        if menu and menu.menu_id != menu_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    @transactional()
    async def add_menu_services(cls, page_object: MenuModel) -> CrudResponseModel:
        """
        新增菜单信息service

        :param page_object: 新增菜单对象
        :return: 新增菜单校验结果
        """
        if not await cls.check_menu_name_unique_services(page_object):
            raise ServiceException(message=f'新增菜单{page_object.menu_name}失败，菜单名称已存在')
        if page_object.is_frame == MenuConstant.YES_FRAME and not StringUtil.is_http(page_object.path):
            raise ServiceException(message=f'新增菜单{page_object.menu_name}失败，地址必须以http(s)://开头')
        await MenuDao.add_menu_dao(page_object)
        return CrudResponseModel(is_success=True, message='新增成功')

    @classmethod
    @transactional()
    async def edit_menu_services(cls, page_object: MenuModel) -> CrudResponseModel:
        """
        编辑菜单信息service

        :param page_object: 编辑部门对象
        :return: 编辑菜单校验结果
        """
        edit_menu = page_object.model_dump(exclude_unset=True)
        menu_info = await cls.menu_detail_services(page_object.menu_id)
        if menu_info.menu_id:
            if not await cls.check_menu_name_unique_services(page_object):
                raise ServiceException(message=f'修改菜单{page_object.menu_name}失败，菜单名称已存在')
            if page_object.is_frame == MenuConstant.YES_FRAME and not StringUtil.is_http(page_object.path):
                raise ServiceException(message=f'修改菜单{page_object.menu_name}失败，地址必须以http(s)://开头')
            if page_object.menu_id == page_object.parent_id:
                raise ServiceException(message=f'修改菜单{page_object.menu_name}失败，上级菜单不能选择自己')
            await MenuDao.edit_menu_dao(edit_menu)
            return CrudResponseModel(is_success=True, message='更新成功')
        raise ServiceException(message='菜单不存在')

    @classmethod
    @transactional()
    async def delete_menu_services(cls, page_object: DeleteMenuModel) -> CrudResponseModel:
        """
        删除菜单信息service

        :param page_object: 删除菜单对象
        :return: 删除菜单校验结果
        """
        if page_object.menu_ids:
            menu_id_list = page_object.menu_ids.split(',')
            for menu_id in menu_id_list:
                if (await MenuDao.has_child_by_menu_id_dao(int(menu_id))) > 0:
                    raise ServiceWarning(message='存在子菜单,不允许删除')
                if (await MenuDao.check_menu_exist_role_dao(int(menu_id))) > 0:
                    raise ServiceWarning(message='菜单已分配,不允许删除')
                await MenuDao.delete_menu_dao(MenuModel(menuId=menu_id))
            return CrudResponseModel(is_success=True, message='删除成功')
        raise ServiceException(message='传入菜单id为空')

    @classmethod
    async def menu_detail_services(cls, menu_id: int) -> MenuModel:
        """
        获取菜单详细信息service

        :param menu_id: 菜单id
        :return: 菜单id对应的信息
        """
        menu = await MenuDao.get_menu_detail_by_id(menu_id=menu_id)
        result = MenuModel(**CamelCaseUtil.transform_result(menu)) if menu else MenuModel()

        return result

    @classmethod
    def list_to_tree(cls, permission_list: Sequence[SysMenu]) -> list[MenuTreeModel]:
        """
        工具方法：根据菜单列表信息生成树形嵌套数据

        :param permission_list: 菜单列表信息
        :return: 菜单树形嵌套数据
        """
        _permission_list = [
            MenuTreeModel(id=item.menu_id, label=item.menu_name, parentId=item.parent_id) for item in permission_list
        ]
        # 转成id为key的字典
        mapping: dict[int, MenuTreeModel] = dict(zip([i.id for i in _permission_list], _permission_list, strict=False))

        # 树容器
        container: list[MenuTreeModel] = []

        for d in _permission_list:
            # 如果找不到父级项，则是根节点
            parent = mapping.get(d.parent_id)
            if parent is None:
                container.append(d)
            else:
                children: list[MenuTreeModel] = parent.children
                if not children:
                    children = []
                children.append(d)
                parent.children = children

        return container
