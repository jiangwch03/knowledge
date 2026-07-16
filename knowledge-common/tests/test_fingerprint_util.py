"""FingerprintUtil 单测"""

from knowledge_common.utils.fingerprint_util import FingerprintUtil


class TestFingerprintUtil:
    def test_same_dict_different_key_order_same_fingerprint(self):
        a = FingerprintUtil.of({'b': 1, 'a': 2})
        b = FingerprintUtil.of({'a': 2, 'b': 1})
        assert a == b
        assert len(a) == 64

    def test_nested_change_changes_fingerprint(self):
        fp1 = FingerprintUtil.of({'wait_for': '.a'})
        fp2 = FingerprintUtil.of({'wait_for': '.b'})
        assert fp1 != fp2

    def test_of_bytes(self):
        assert FingerprintUtil.of_bytes(b'hello') == FingerprintUtil.of_bytes('hello')
        assert len(FingerprintUtil.of_bytes(b'pdf')) == 64
