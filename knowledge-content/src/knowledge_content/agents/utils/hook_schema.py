"""hooks 声明 schema 与校验"""

from knowledge_common.exceptions.exception import ServiceException

_VALID_HOOK_PHASES = frozenset({
    'on_before_request',
    'on_page_loaded',
    'on_after_page_load',
})

_VALID_STEP_TYPES = frozenset({
    'click',
    'fill',
    'wait',
    'evaluate',
})


def validate_hooks(hooks: dict | None) -> None:
    """
    校验 hooks 声明结构

    :param hooks: strategy_config.hooks
    :raises ServiceException: 结构非法时抛出
    """
    if not hooks:
        return
    if not isinstance(hooks, dict):
        raise ServiceException(message='hooks 必须是 JSON 对象')

    for phase, actions in hooks.items():
        if phase not in _VALID_HOOK_PHASES:
            raise ServiceException(message=f'不支持的 hook 阶段: {phase}')
        if not isinstance(actions, list):
            raise ServiceException(message=f'hooks.{phase} 必须是数组')
        for idx, action in enumerate(actions):
            if not isinstance(action, dict):
                raise ServiceException(message=f'hooks.{phase}[{idx}] 必须是对象')
            steps = action.get('steps')
            if not isinstance(steps, list) or not steps:
                raise ServiceException(message=f'hooks.{phase}[{idx}].steps 必须是非空数组')
            for step_idx, step in enumerate(steps):
                _validate_step(phase, idx, step_idx, step)


def _validate_step(phase: str, action_idx: int, step_idx: int, step: dict) -> None:
    if not isinstance(step, dict):
        raise ServiceException(
            message=f'hooks.{phase}[{action_idx}].steps[{step_idx}] 必须是对象',
        )
    step_type = step.get('type')
    if step_type not in _VALID_STEP_TYPES:
        raise ServiceException(
            message=f'不支持的 hook step type: {step_type}',
        )
    if step_type in ('click', 'fill', 'wait') and not step.get('selector'):
        raise ServiceException(
            message=f'hooks step {step_type} 缺少 selector',
        )
    if step_type == 'fill' and 'value' not in step:
        raise ServiceException(message='hooks fill step 缺少 value')
