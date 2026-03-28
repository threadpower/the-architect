"""
Oracle Thesis Engine v2.0
Threadpower Labs — Jeremy Lambert

Now includes:
- Dalio Big Cycle as META-THESIS (operating system)
- 12 core theses (up from 7)
- Sub-signal aggregation
- Cycle position tracking
- Stage transition detection
"""

import yaml
from datetime import date, datetime
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel
from enum import Enum


class ThesisStatus(str, Enum):
    CONFIRMING = "CONFIRMING"
    NEUTRAL = "NEUTRAL"
    CHALLENGING = "CHALLENGING"


class DalioCyclePosition(BaseModel):
    current_stage: float
    stage_name: str
    stage_direction: str
    historical_parallel: str
    active_indicators: List[str]
    transition_signals: List[str]
    decline_signal_count: int
    transition_signal_count: int
    assessment: str


class ThesisSignal(BaseModel):
    thesis_name: str
    thesis_short_name: str
    dalio_stages: List[int]
    status: ThesisStatus
    confidence: int
    matching_headlines: List[str]
    assessment: str
    related_positions: List[str]
    sub_signal_matches: List[str]
    timestamp: datetime = datetime.utcnow()


class OraclePosture(BaseModel):
    posture: str
    confidence: int
    confirming_count: int
    neutral_count: int
    challenging_count: int
    dalio_position: DalioCyclePosition
    war_day: int
    fibonacci_day: Tuple[int, bool]
    days_to_birthday: int
    strongest_thesis: str
    weakest_thesis: str


class ThesisEngine:
    def __init__(self, config_path: str = "config/thesis_framework_v2.yaml"):
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        self.framework = raw
        self.theses = raw["theses"]
        self.meta = raw["meta"]
        self.dalio = raw["dalio_big_cycle"]
        self.sub_signals = raw.get("sub_signals", {})
        self.war_start = date.fromisoformat(self.meta["war_start_date"])

    # ============================================================
    # DALIO BIG CYCLE META-THESIS
    # ============================================================

    def assess_dalio_cycle(
        self, headlines: List[str], market_data: Optional[dict] = None
    ) -> DalioCyclePosition:
        """
        Assess current position in Dalio's Big Cycle based on
        headline signals and market data.
        """
        decline_keywords = self.dalio["key_signals"]["confirming_decline"]
        transition_keywords = self.dalio["key_signals"]["confirming_transition"]

        decline_matches = []
        transition_matches = []

        for headline in headlines:
            hl = headline.lower()
            for kw in decline_keywords:
                if kw.lower() in hl:
                    decline_matches.append(headline)
                    break
            for kw in transition_keywords:
                if kw.lower() in hl:
                    transition_matches.append(headline)
                    break

        # Determine active stage indicators
        active_indicators = []

        # Stage 4 indicators
        stage4 = self.dalio["stages"][4]["indicators"]
        if stage4["debt_to_gdp"]["current"] > stage4["debt_to_gdp"]["threshold_warning"]:
            active_indicators.append(
                f"Debt/GDP at {stage4['debt_to_gdp']['current']}% "
                f"(warning: {stage4['debt_to_gdp']['threshold_warning']}%)"
            )
        if stage4["political_polarization"]["trend"] == "extreme":
            active_indicators.append("Political polarization at extreme levels")
        if stage4["military_overextension"]["active_conflicts"] >= 2:
            active_indicators.append(
                f"{stage4['military_overextension']['active_conflicts']} active conflicts"
            )

        # Stage 5 indicators
        stage5 = self.dalio["stages"][5]["indicators"]
        if stage5["interest_payments_vs_defense"]["status"] == "interest_exceeds_defense":
            active_indicators.append("Interest payments exceed defense spending")
        if stage5["reserve_currency_share"]["current_pct"] < 60:
            active_indicators.append(
                f"Dollar reserve share at {stage5['reserve_currency_share']['current_pct']}% "
                f"(peak: {stage5['reserve_currency_share']['peak_pct']}%)"
            )
        if stage5["credit_stress"]["private_credit_distress"]:
            active_indicators.append("Private credit distress signals active")

        # Market data overrides
        if market_data:
            vix = market_data.get("vix", 0)
            if vix >= 30:
                active_indicators.append(f"VIX at {vix} — fear territory")
            oil = market_data.get("oil_wti", 0)
            if oil >= 100:
                active_indicators.append(f"Oil at ${oil} — Stage 5 energy vulnerability exposed")

        # Stage 5 rate expectations
        rate_data = stage5.get("rate_expectations", {})
        if rate_data.get("fed_cut_probability_current", 1.0) < 0.10:
            active_indicators.append(
                f"Rate cut probability collapsed to {rate_data['fed_cut_probability_current']*100:.0f}%"
            )

        # Determine current stage assessment
        current_stage = self.dalio["current_stage"]
        stage_names = {
            4: "Overextension",
            5: "Bad Financial Conditions",
            6: "Conflict & Restructuring"
        }
        stage_int = int(current_stage)
        stage_name = stage_names.get(stage_int, f"Stage {stage_int}")

        # Generate assessment
        decline_count = len(decline_matches)
        transition_count = len(transition_matches)

        if decline_count >= 5 and transition_count >= 3:
            assessment = (
                f"Stage {current_stage} ACTIVE — {decline_count} decline signals and "
                f"{transition_count} transition signals detected. The old order is cracking "
                f"AND the new architecture is being built simultaneously. "
                f"Classic Stage 5→6 transition dynamics."
            )
        elif decline_count >= 3:
            assessment = (
                f"Stage {current_stage} — {decline_count} decline signals dominant. "
                f"Unraveling accelerating. Watch for transition catalysts."
            )
        elif transition_count >= 3:
            assessment = (
                f"Stage {current_stage} — {transition_count} transition signals active. "
                f"New order construction underway despite surface volatility."
            )
        else:
            assessment = (
                f"Stage {current_stage} — Mixed signals. "
                f"{decline_count} decline, {transition_count} transition."
            )

        return DalioCyclePosition(
            current_stage=current_stage,
            stage_name=stage_name,
            stage_direction=self.dalio["stage_direction"],
            historical_parallel=self.dalio["historical_parallel"],
            active_indicators=active_indicators,
            transition_signals=transition_matches[:5],
            decline_signal_count=decline_count,
            transition_signal_count=transition_count,
            assessment=assessment
        )

    # ============================================================
    # TIME CALCULATIONS
    # ============================================================

    def get_war_day(self, check_date: date = None) -> int:
        if check_date is None:
            check_date = date.today()
        return (check_date - self.war_start).days + 1

    def get_fibonacci_day(self, check_date: date = None) -> Tuple[int, bool]:
        war_day = self.get_war_day(check_date)
        fib_sequence = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]
        return war_day, war_day in fib_sequence

    def get_days_to_birthday(self, check_date: date = None) -> int:
        if check_date is None:
            check_date = date.today()
        birthday = date.fromisoformat(self.meta["birthday"])
        return (birthday - check_date).days

    def get_sprint_day(self, check_date: date = None) -> int:
        if check_date is None:
            check_date = date.today()
        sprint_start = date.fromisoformat(self.meta["sprint_start_date"])
        return (check_date - sprint_start).days + 1

    # ============================================================
    # SUB-SIGNAL MATCHING
    # ============================================================

    def match_sub_signals(self, headlines: List[str]) -> Dict[str, List[str]]:
        """
        Match headlines against sub-signal keyword groups.
        Returns dict of sub_signal_name → matching headlines.
        """
        matches = {}
        for sub_name, sub_config in self.sub_signals.items():
            sub_matches = []
            keywords = sub_config.get("keywords", [])
            for headline in headlines:
                hl = headline.lower()
                for kw in keywords:
                    if kw.lower() in hl:
                        sub_matches.append(headline)
                        break
            if sub_matches:
                matches[sub_name] = sub_matches
        return matches

    # ============================================================
    # THESIS MATCHING (12 theses)
    # ============================================================

    def match_thesis(
        self,
        thesis: dict,
        headlines: List[str],
        sub_signal_matches: Dict[str, List[str]],
        market_data: Optional[dict] = None
    ) -> ThesisSignal:
        name = thesis["name"]
        short_name = thesis["short_name"]
        base_confidence = thesis.get("confidence", 50)
        related_positions = thesis.get("related_positions", [])
        dalio_stages = thesis.get("dalio_stages", [])

        # Get confirming/challenging keywords
        confirming_keywords = thesis.get("key_signals", {}).get("confirming", [])
        challenging_keywords = thesis.get("key_signals", {}).get("challenging", [])

        # Handle dual-path theses (Fink Binary, Rate Flip, Digital Dollar)
        if short_name == "fink_binary":
            confirming_keywords = (
                thesis.get("key_signals", {}).get("confirming_abundance", []) +
                thesis.get("key_signals", {}).get("confirming_recession", [])
            )
        elif short_name == "rate_flip":
            confirming_keywords = (
                thesis.get("key_signals", {}).get("confirming_dovish", []) +
                thesis.get("key_signals", {}).get("confirming_hawkish", [])
            )
        elif short_name == "digital_dollar":
            confirming_keywords = (
                thesis.get("key_signals", {}).get("confirming_dedollarization", []) +
                thesis.get("key_signals", {}).get("confirming_upgrade", [])
            )

        # Score headlines
        confirming_matches = []
        challenging_matches = []

        for headline in headlines:
            hl = headline.lower()
            for kw in confirming_keywords:
                if kw.lower() in hl:
                    confirming_matches.append(headline)
                    break
            for kw in challenging_keywords:
                if kw.lower() in hl:
                    challenging_matches.append(headline)
                    break

        # Add sub-signal bonus
        thesis_sub_signals = []
        for sub_name, sub_config in self.sub_signals.items():
            if short_name in sub_config.get("feeds_into", []):
                if sub_name in sub_signal_matches:
                    thesis_sub_signals.append(sub_name)
                    confirming_matches.extend(sub_signal_matches[sub_name][:2])

        # Calculate status
        confirm_score = len(confirming_matches)
        challenge_score = len(challenging_matches)
        net_score = confirm_score - challenge_score

        if net_score >= 2:
            status = ThesisStatus.CONFIRMING
            confidence_adj = min(base_confidence + (net_score * 2), 95)
        elif net_score <= -2:
            status = ThesisStatus.CHALLENGING
            confidence_adj = max(base_confidence - (abs(net_score) * 4), 20)
        else:
            status = ThesisStatus.NEUTRAL
            confidence_adj = base_confidence

        # Market data overrides
        if market_data:
            if short_name == "fink_binary":
                oil = market_data.get("oil_wti", 0)
                thresholds = thesis.get("key_signals", {}).get("key_thresholds", {})
                if oil <= thresholds.get("oil_abundance", 70):
                    status = ThesisStatus.CONFIRMING
                    confidence_adj = min(confidence_adj + 10, 95)
                elif oil >= thresholds.get("oil_recession_warning", 120):
                    status = ThesisStatus.CONFIRMING
                    confidence_adj = min(confidence_adj + 10, 95)

            elif short_name == "btc_decoupling":
                btc_chg = market_data.get("btc_24h_pct", 0)
                sp_chg = market_data.get("sp500_24h_pct", 0)
                if btc_chg > sp_chg + 1.0:
                    status = ThesisStatus.CONFIRMING
                    confidence_adj = min(confidence_adj + 8, 95)

            elif short_name == "rate_flip":
                vix = market_data.get("vix", 0)
                oil = market_data.get("oil_wti", 0)
                if oil >= 100 and vix >= 25:
                    status = ThesisStatus.CHALLENGING
                    confidence_adj = max(confidence_adj - 5, 30)

            elif short_name == "trump_feedback":
                sp_chg = market_data.get("sp500_24h_pct", 0)
                if sp_chg < -1.0:
                    status = ThesisStatus.CONFIRMING
                    confidence_adj = min(confidence_adj + 5, 95)

        # Generate assessment
        status_emoji = {"CONFIRMING": "✅", "NEUTRAL": "⚖️", "CHALLENGING": "⚠️"}
        emoji = status_emoji[status.value]

        if confirming_matches:
            sample = confirming_matches[0][:80]
        elif challenging_matches:
            sample = challenging_matches[0][:80]
        else:
            sample = "No strong signals"

        assessment = (
            f"{emoji} {name} [{'/'.join(str(s) for s in dalio_stages)}]: "
            f"{status.value} ({confidence_adj}%) — {sample}"
        )

        return ThesisSignal(
            thesis_name=name,
            thesis_short_name=short_name,
            dalio_stages=dalio_stages,
            status=status,
            confidence=confidence_adj,
            matching_headlines=(confirming_matches + challenging_matches)[:8],
            assessment=assessment,
            related_positions=related_positions,
            sub_signal_matches=thesis_sub_signals
        )

    # ============================================================
    # FULL SCAN
    # ============================================================

    def run_full_scan(
        self,
        headlines: List[str],
        market_data: Optional[dict] = None
    ) -> Tuple[DalioCyclePosition, List[ThesisSignal]]:
        """
        Run Dalio meta-thesis + all 12 theses against headlines and market data.
        Returns (DalioCyclePosition, List[ThesisSignal]).
        """
        # Dalio cycle assessment
        dalio = self.assess_dalio_cycle(headlines, market_data)

        # Sub-signal matching
        sub_matches = self.match_sub_signals(headlines)

        # All 12 theses
        signals = []
        for thesis in self.theses:
            signal = self.match_thesis(thesis, headlines, sub_matches, market_data)
            signals.append(signal)

        signals.sort(key=lambda s: s.confidence, reverse=True)
        return dalio, signals

    def get_overall_posture(
        self,
        dalio: DalioCyclePosition,
        signals: List[ThesisSignal]
    ) -> OraclePosture:
        """Determine overall investment posture from Dalio + 12 theses."""
        confirming = sum(1 for s in signals if s.status == ThesisStatus.CONFIRMING)
        challenging = sum(1 for s in signals if s.status == ThesisStatus.CHALLENGING)
        neutral = len(signals) - confirming - challenging
        avg_confidence = sum(s.confidence for s in signals) / len(signals) if signals else 50

        if confirming >= 8:
            posture = "AGGRESSIVE"
        elif confirming >= 6 and challenging <= 2:
            posture = "MODERATE_AGGRESSIVE"
        elif challenging >= 4:
            posture = "DEFENSIVE"
        elif confirming >= 4:
            posture = "MODERATE"
        else:
            posture = "NEUTRAL"

        strongest = max(signals, key=lambda s: s.confidence) if signals else None
        weakest = min(signals, key=lambda s: s.confidence) if signals else None

        return OraclePosture(
            posture=posture,
            confidence=round(avg_confidence),
            confirming_count=confirming,
            neutral_count=neutral,
            challenging_count=challenging,
            dalio_position=dalio,
            war_day=self.get_war_day(),
            fibonacci_day=self.get_fibonacci_day(),
            days_to_birthday=self.get_days_to_birthday(),
            strongest_thesis=strongest.thesis_name if strongest else "",
            weakest_thesis=weakest.thesis_name if weakest else ""
        )

    def get_clarity_progress(self) -> dict:
        for thesis in self.theses:
            if thesis["short_name"] == "clarity_act":
                progress = thesis.get("progress", {})
                return {
                    "current_step": progress.get("current_step", 0),
                    "total_steps": progress.get("total_steps", 7),
                    "steps": progress.get("steps", {}),
                    "moreno_deadline": progress.get("moreno_deadline"),
                    "polymarket_odds": progress.get("polymarket_odds"),
                    "pct_complete": round(
                        progress.get("current_step", 0) /
                        progress.get("total_steps", 7) * 100
                    )
                }
        return {}


# ============================================================
# DEMO
# ============================================================
if __name__ == "__main__":
    engine = ThesisEngine("config/thesis_framework_v2.yaml")

    headlines = [
        "S&P 500 falls to 7-month low as Iran war fears mount",
        "VIX crosses 30 as Nasdaq enters correction territory",
        "Trump extends Iran energy strike deadline 10 days to April 6",
        "Oil surges above $110 as Strait of Hormuz remains restricted",
        "Bitcoin holds near $66K despite broad equity selloff — decoupling signal",
        "Meta cuts hundreds of jobs across Reality Labs and Facebook",
        "OECD raises US inflation forecast to 4.2% for 2026",
        "Congress declares tokenization inevitable in historic hearing",
        "Morgan Stanley files for bank-branded Bitcoin ETF (MSBT)",
        "Strategy announces $44.1B capital raise for Bitcoin accumulation",
        "BlackRock CEO Fink warns $150 oil triggers global recession",
        "Philippines declares national energy emergency",
        "Pakistan confirms mediating US-Iran indirect talks",
        "Eight tankers pass through Strait of Hormuz with Iranian fees",
        "CLARITY Act stablecoin yield deal reached in principle",
        "Sri Lanka implements 4-day work week due to energy crisis",
        "Tesla Optimus Gen 3 in production at Fremont factory",
        "BRICS nations accelerate yuan settlement mechanisms",
        "Tether announces Big Four audit of $184B stablecoin reserves",
        "Iran charging yuan-denominated tolls at Strait of Hormuz",
        "Apollo fund hit with 11.2% redemption requests — private credit stress",
        "US national debt interest payments exceed defense spending for first time",
        "Federal Reserve trapped — can't cut (inflation) can't hike (recession risk)",
        "Bitcoin fourth halving supply squeeze entering month 11 — acceleration phase",
        "Rate cut expectations collapsed from 95% to 5% in one month",
        "Rare earth mineral reserves may last only weeks at current strike pace",
        "Saudi Arabia considering joining war against Iran — Gulf realignment",
        "59% of Americans say Iran war was wrong decision — political pressure mounting",
    ]

    market = {
        "btc_price": 66100,
        "btc_24h_pct": -3.8,
        "sp500_price": 6369,
        "sp500_24h_pct": -1.7,
        "oil_wti": 101,
        "oil_brent": 110,
        "gold": 4510,
        "vix": 31,
    }

    print("=" * 70)
    print("🔮 ORACLE THESIS SCAN v2.0 — 12 THESES + DALIO META")
    print(f"   Date: {date.today()} | War Day: {engine.get_war_day()} | "
          f"Sprint Day: {engine.get_sprint_day()}")
    print(f"   Days to Birthday: {engine.get_days_to_birthday()} | "
          f"Fibonacci: {engine.get_fibonacci_day()}")
    print("=" * 70)

    dalio, signals = engine.run_full_scan(headlines, market)

    # Dalio Meta-Thesis
    print(f"\n📊 DALIO BIG CYCLE: Stage {dalio.current_stage} "
          f"({dalio.stage_name}) — {dalio.stage_direction}")
    print(f"   Historical Parallel: {dalio.historical_parallel}")
    print(f"   Decline Signals: {dalio.decline_signal_count} | "
          f"Transition Signals: {dalio.transition_signal_count}")
    print(f"   Assessment: {dalio.assessment}")
    print(f"\n   Active Indicators:")
    for ind in dalio.active_indicators:
        print(f"     • {ind}")

    # 12 Theses
    print(f"\n{'=' * 70}")
    print("📋 12-THESIS SCAN")
    print(f"{'=' * 70}")
    for signal in signals:
        print(f"\n{signal.assessment}")
        if signal.sub_signal_matches:
            print(f"   Sub-signals: {', '.join(signal.sub_signal_matches)}")
        print(f"   Positions: {', '.join(signal.related_positions)}")

    # Overall Posture
    posture = engine.get_overall_posture(dalio, signals)
    print(f"\n{'=' * 70}")
    print(f"🎯 OVERALL POSTURE: {posture.posture} "
          f"(Confidence: {posture.confidence}%)")
    print(f"   Confirming: {posture.confirming_count} | "
          f"Neutral: {posture.neutral_count} | "
          f"Challenging: {posture.challenging_count}")
    print(f"   Strongest: {posture.strongest_thesis}")
    print(f"   Weakest: {posture.weakest_thesis}")

    # CLARITY
    clarity = engine.get_clarity_progress()
    print(f"\n📋 CLARITY Act: Step {clarity['current_step']}/{clarity['total_steps']} "
          f"({clarity['pct_complete']}%)")
    print(f"\n   🐂 The bull is {posture.days_to_birthday} days from home.")
