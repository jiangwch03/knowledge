"""试爬 deep_crawl 安全限流：null/≤0 不得落到 max_pages=1；depth≤0 抬到 1"""

from knowledge_content.service.trial_crawl_service import clamp_trial_deep_crawl_limits as _clamp_trial_deep_crawl_limits


class TestClampTrialDeepCrawlLimits:
    def test_null_max_pages_becomes_trial_cap(self):
        strategy = {'max_pages': None, 'max_depth': 5}
        _clamp_trial_deep_crawl_limits(strategy)
        assert strategy['max_pages'] == 3
        assert strategy['max_depth'] == 1

    def test_zero_or_negative_max_pages_becomes_trial_cap(self):
        for raw in (0, -1):
            strategy = {'max_pages': raw, 'max_depth': 0}
            _clamp_trial_deep_crawl_limits(strategy)
            assert strategy['max_pages'] == 3
            assert strategy['max_depth'] == 1

    def test_explicit_one_raised_to_min_two(self):
        """crawl4ai stream + max_pages=1 会空 yield，显式 1 也要抬到 2"""
        strategy = {'max_pages': 1, 'max_depth': 0}
        _clamp_trial_deep_crawl_limits(strategy)
        assert strategy['max_pages'] == 2
        assert strategy['max_depth'] == 1

    def test_explicit_value_capped_at_three(self):
        strategy = {'max_pages': 200, 'max_depth': 10}
        _clamp_trial_deep_crawl_limits(strategy)
        assert strategy['max_pages'] == 3
        assert strategy['max_depth'] == 1

    def test_null_or_negative_depth_raised_to_one(self):
        """null/-1/0 表示不限或误写 → 试爬必须 depth≥1 才能验扩链"""
        for raw in (None, '', -1, 0):
            strategy = {'max_pages': 3, 'max_depth': raw}
            _clamp_trial_deep_crawl_limits(strategy)
            assert strategy['max_depth'] == 1, f'raw={raw!r}'
