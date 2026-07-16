"""format_exception_message / ServiceException 文案透出回归"""

from knowledge_common.exceptions.exception import ServiceException, format_exception_message


def test_service_exception_str_and_message_aligned():
    e = ServiceException(message='hooks step wait 缺少 selector')
    assert str(e) == 'hooks step wait 缺少 selector'
    assert e.message == 'hooks step wait 缺少 selector'
    assert format_exception_message(e) == 'hooks step wait 缺少 selector'


def test_service_exception_positional_message():
    e = ServiceException('positional')
    assert str(e) == 'positional'
    assert format_exception_message(e) == 'positional'


def test_service_exception_empty_message_falls_back_to_type():
    e = ServiceException()
    assert e.message == ''
    assert str(e) == ''
    assert format_exception_message(e) == 'ServiceException'


def test_format_plain_exception():
    e = ValueError('bad value')
    assert format_exception_message(e) == 'bad value'


def test_format_empty_plain_exception():
    e = RuntimeError()
    assert format_exception_message(e) == 'RuntimeError'
