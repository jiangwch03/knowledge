"""试爬指纹门禁：同 url+策略同指纹；改 wait_for / 文案元数据行为"""

from knowledge_content.agents.utils.trial_verified_gate import build_trial_fingerprint


def test_fingerprint_stable_across_meta_and_key_order():
    cfg_a = {
        'needs_user_input': False,
        'strategy_summary': '文案A',
        'site_type': '文档站',
        'browser_config': {'headless': True},
        'crawler_run_config': {'wait_for': '.main'},
    }
    cfg_b = {
        'crawler_run_config': {'wait_for': '.main'},
        'browser_config': {'headless': True},
        'site_type': '其他',
        'strategy_summary': '文案B',
        'needs_user_input': True,
    }
    assert build_trial_fingerprint('https://ex.com/docs/', cfg_a) == build_trial_fingerprint(
        ' https://ex.com/docs/ ', cfg_b,
    )


def test_fingerprint_changes_when_wait_for_changes():
    base = {'crawler_run_config': {'wait_for': '.a'}}
    other = {'crawler_run_config': {'wait_for': '.b'}}
    assert build_trial_fingerprint('https://ex.com', base) != build_trial_fingerprint(
        'https://ex.com', other,
    )
