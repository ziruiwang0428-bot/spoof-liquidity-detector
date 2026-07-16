from __future__ import annotations

from spoof_liquidity_detector.features import build_features, build_lifecycles
from spoof_liquidity_detector.providers.base import OrderEventProvider
from spoof_liquidity_detector.schema import AccountEconomics, AccountRiskProfile, DetectionResult
from spoof_liquidity_detector.accounts import AccountProfiler
from spoof_liquidity_detector.statistics import SuspiciousLiquidityDetector


class DetectionPipeline:
    def __init__(
        self,
        provider: OrderEventProvider,
        detector: SuspiciousLiquidityDetector | None = None,
    ) -> None:
        self.provider = provider
        self.detector = detector or SuspiciousLiquidityDetector()

    def run(self) -> list[DetectionResult]:
        events = self.provider.load_events()
        lifecycles = build_lifecycles(events)
        features = build_features(lifecycles)
        return self.detector.score(features)

    def run_accounts(
        self,
        economics: dict[str, AccountEconomics] | None = None,
        profiler: AccountProfiler | None = None,
    ) -> list[AccountRiskProfile]:
        results = self.run()
        account_profiler = profiler or AccountProfiler()
        return account_profiler.profile(results, economics=economics)
