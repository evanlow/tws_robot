"""
Correlation Analysis & Portfolio Concentration Module

This module provides comprehensive portfolio correlation analysis and concentration
risk management. It calculates correlation matrices between positions, tracks sector
and industry exposures, and provides diversification metrics.

Key Features:
- Correlation matrix calculation between positions
- Portfolio concentration metrics (HHI, top N concentration)
- Sector and industry exposure tracking
- Diversification scoring
- Pair trade identification
- Correlation-based risk warnings

Author: Trading Bot Development Team
Date: November 21, 2025
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
from collections import defaultdict
import numpy as np


@dataclass
class PositionInfo:
    """Information about a single position for correlation analysis"""
    symbol: str
    quantity: int
    market_value: float
    weight: float  # Portfolio weight (0.0 to 1.0)
    sector: Optional[str] = None
    industry: Optional[str] = None
    returns: Optional[List[float]] = None  # Historical returns for correlation
    
    def __str__(self) -> str:
        return f"Position({self.symbol}, ${self.market_value:,.0f}, {self.weight:.1%})"


@dataclass
class CorrelationMetrics:
    """Comprehensive correlation and concentration metrics"""
    timestamp: datetime
    num_positions: int
    total_value: float
    
    # Concentration metrics
    herfindahl_index: float  # 0 to 1 (1 = concentrated, 0 = diversified)
    top_position_pct: float
    top_3_positions_pct: float
    top_5_positions_pct: float
    
    # Correlation metrics
    avg_correlation: float  # Average pairwise correlation
    max_correlation: float  # Highest correlation pair
    high_correlation_pairs: int  # Pairs with correlation > 0.7
    
    # Diversification
    diversification_score: float  # 0 to 100 (100 = well diversified)
    effective_positions: float  # Effective number of independent positions
    
    # Sector/Industry concentration
    sector_concentration: Dict[str, float]  # Sector -> weight
    industry_concentration: Dict[str, float]  # Industry -> weight
    top_sector_pct: float
    top_industry_pct: float
    
    # Risk flags
    is_concentrated: bool  # HHI > 0.25
    has_high_correlations: bool  # Any pair > 0.8
    sector_risk: bool  # Single sector > 50%
    
    def __str__(self) -> str:
        return (
            f"CorrelationMetrics("
            f"positions={self.num_positions}, "
            f"HHI={self.herfindahl_index:.3f}, "
            f"avg_corr={self.avg_correlation:.2f}, "
            f"div_score={self.diversification_score:.0f})"
        )


@dataclass
class CorrelationPair:
    """A pair of correlated positions"""
    symbol1: str
    symbol2: str
    correlation: float
    combined_weight: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    
    def __str__(self) -> str:
        return (
            f"CorrelationPair({self.symbol1}-{self.symbol2}, "
            f"corr={self.correlation:.2f}, "
            f"weight={self.combined_weight:.1%}, "
            f"risk={self.risk_level})"
        )


class CorrelationAnalyzer:
    """
    Portfolio correlation and concentration analyzer.
    
    This class analyzes portfolio positions for correlation risk and concentration
    issues. It calculates correlation matrices, tracks sector exposures, and
    provides diversification metrics to help manage portfolio risk.
    
    Parameters
    ----------
    concentration_threshold : float
        HHI threshold for concentration warning (default: 0.25)
    high_correlation_threshold : float
        Correlation threshold for high correlation warning (default: 0.8)
    critical_correlation_threshold : float
        Correlation threshold for critical warning (default: 0.9)
    max_sector_concentration : float
        Maximum allowed single sector weight (default: 0.50 = 50%)
    max_industry_concentration : float
        Maximum allowed single industry weight (default: 0.35 = 35%)
    min_diversification_score : float
        Minimum acceptable diversification score (default: 60.0)
    
    Example
    -------
    >>> analyzer = CorrelationAnalyzer()
    >>> positions = [
    ...     PositionInfo("AAPL", 100, 15000, 0.15, "Technology", "Consumer Electronics"),
    ...     PositionInfo("MSFT", 50, 18000, 0.18, "Technology", "Software"),
    ... ]
    >>> metrics = analyzer.analyze(positions)
    >>> print(f"HHI: {metrics.herfindahl_index:.3f}")
    >>> print(f"Diversification: {metrics.diversification_score:.0f}")
    """
    
    def __init__(
        self,
        concentration_threshold: float = 0.25,
        high_correlation_threshold: float = 0.8,
        critical_correlation_threshold: float = 0.9,
        max_sector_concentration: float = 0.50,
        max_industry_concentration: float = 0.35,
        min_diversification_score: float = 60.0,
    ):
        # Configuration
        self.concentration_threshold = concentration_threshold
        self.high_correlation_threshold = high_correlation_threshold
        self.critical_correlation_threshold = critical_correlation_threshold
        self.max_sector_concentration = max_sector_concentration
        self.max_industry_concentration = max_industry_concentration
        self.min_diversification_score = min_diversification_score
        
        # State
        self.correlation_matrix: Optional[np.ndarray] = None
        self.symbol_index: Dict[str, int] = {}
        self.metrics_history: List[CorrelationMetrics] = []
        
    def analyze(
        self,
        positions: List[PositionInfo],
        timestamp: Optional[datetime] = None,
    ) -> CorrelationMetrics:
        """
        Analyze portfolio for correlation and concentration risks.
        
        Parameters
        ----------
        positions : List[PositionInfo]
            List of current positions with market values and optional returns data
        timestamp : datetime, optional
            Timestamp for the analysis (default: now)
            
        Returns
        -------
        CorrelationMetrics
            Comprehensive correlation and concentration metrics
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        if not positions:
            return self._empty_metrics(timestamp)
        
        # Calculate basic metrics
        num_positions = len(positions)
        total_value = sum(p.market_value for p in positions)
        
        # Update weights if needed
        for pos in positions:
            if pos.weight == 0 or abs(pos.weight * total_value - pos.market_value) > 0.01:
                pos.weight = pos.market_value / total_value if total_value > 0 else 0
        
        # Calculate concentration metrics
        hhi = self._calculate_herfindahl_index(positions)
        top_1, top_3, top_5 = self._calculate_top_n_concentration(positions)
        
        # Calculate correlation metrics (if returns data available)
        avg_corr, max_corr, high_corr_pairs = self._calculate_correlation_metrics(positions)
        
        # Calculate diversification
        div_score = self._calculate_diversification_score(positions, hhi, avg_corr)
        effective_n = self._calculate_effective_positions(positions)
        
        # Calculate sector/industry concentration
        sector_conc = self._calculate_sector_concentration(positions)
        industry_conc = self._calculate_industry_concentration(positions)
        top_sector = max(sector_conc.values()) if sector_conc else 0.0
        top_industry = max(industry_conc.values()) if industry_conc else 0.0
        
        # Determine risk flags
        is_concentrated = hhi > self.concentration_threshold
        has_high_corr = max_corr > self.high_correlation_threshold
        sector_risk = top_sector > self.max_sector_concentration
        
        metrics = CorrelationMetrics(
            timestamp=timestamp,
            num_positions=num_positions,
            total_value=total_value,
            herfindahl_index=hhi,
            top_position_pct=top_1,
            top_3_positions_pct=top_3,
            top_5_positions_pct=top_5,
            avg_correlation=avg_corr,
            max_correlation=max_corr,
            high_correlation_pairs=high_corr_pairs,
            diversification_score=div_score,
            effective_positions=effective_n,
            sector_concentration=sector_conc,
            industry_concentration=industry_conc,
            top_sector_pct=top_sector,
            top_industry_pct=top_industry,
            is_concentrated=is_concentrated,
            has_high_correlations=has_high_corr,
            sector_risk=sector_risk,
        )
        
        self.metrics_history.append(metrics)
        return metrics
    
    def _empty_metrics(self, timestamp: datetime) -> CorrelationMetrics:
        """Return empty metrics when no positions"""
        return CorrelationMetrics(
            timestamp=timestamp,
            num_positions=0,
            total_value=0.0,
            herfindahl_index=0.0,
            top_position_pct=0.0,
            top_3_positions_pct=0.0,
            top_5_positions_pct=0.0,
            avg_correlation=0.0,
            max_correlation=0.0,
            high_correlation_pairs=0,
            diversification_score=100.0,
            effective_positions=0.0,
            sector_concentration={},
            industry_concentration={},
            top_sector_pct=0.0,
            top_industry_pct=0.0,
            is_concentrated=False,
            has_high_correlations=False,
            sector_risk=False,
        )
    
    def _calculate_herfindahl_index(self, positions: List[PositionInfo]) -> float:
        """
        Calculate Herfindahl-Hirschman Index (HHI) for concentration.
        
        HHI = sum of squared weights
        - 1.0 = completely concentrated (one position)
        - 1/N = perfectly diversified (N equal positions)
        - < 0.15 = well diversified
        - 0.15-0.25 = moderate concentration
        - > 0.25 = high concentration
        """
        return sum(pos.weight ** 2 for pos in positions)
    
    def _calculate_top_n_concentration(
        self, 
        positions: List[PositionInfo]
    ) -> Tuple[float, float, float]:
        """Calculate concentration of top 1, 3, and 5 positions"""
        sorted_positions = sorted(positions, key=lambda p: p.weight, reverse=True)
        
        top_1 = sorted_positions[0].weight if len(sorted_positions) >= 1 else 0.0
        top_3 = sum(p.weight for p in sorted_positions[:3])
        top_5 = sum(p.weight for p in sorted_positions[:5])
        
        return top_1, top_3, top_5
    
    def _calculate_correlation_metrics(
        self,
        positions: List[PositionInfo]
    ) -> Tuple[float, float, int]:
        """
        Calculate correlation metrics if returns data available.
        
        Returns
        -------
        tuple
            (avg_correlation, max_correlation, high_correlation_pairs)
        """
        # Filter positions with returns data
        positions_with_returns = [p for p in positions if p.returns and len(p.returns) > 1]
        
        if len(positions_with_returns) < 2:
            return 0.0, 0.0, 0
        
        # Build returns matrix
        symbols = [p.symbol for p in positions_with_returns]
        returns_matrix = np.array([p.returns for p in positions_with_returns])
        
        # Calculate correlation matrix
        try:
            self.correlation_matrix = np.corrcoef(returns_matrix)
            self.symbol_index = {sym: i for i, sym in enumerate(symbols)}
        except Exception:
            return 0.0, 0.0, 0
        
        # Extract upper triangle (excluding diagonal)
        n = len(positions_with_returns)
        correlations = []
        high_corr_count = 0
        
        for i in range(n):
            for j in range(i + 1, n):
                corr = self.correlation_matrix[i, j]
                if not np.isnan(corr):
                    correlations.append(abs(corr))
                    if abs(corr) > self.high_correlation_threshold:
                        high_corr_count += 1
        
        if not correlations:
            return 0.0, 0.0, 0
        
        avg_corr = np.mean(correlations)
        max_corr = np.max(correlations)
        
        return float(avg_corr), float(max_corr), high_corr_count
    
    def _calculate_diversification_score(
        self,
        positions: List[PositionInfo],
        hhi: float,
        avg_correlation: float,
    ) -> float:
        """
        Calculate diversification score (0-100).
        
        Considers:
        - Number of positions (more is better)
        - HHI (lower is better)
        - Average correlation (lower is better)
        - Sector diversity
        
        100 = perfectly diversified
        0 = highly concentrated
        """
        score = 100.0
        
        # Penalty for few positions
        num_pos = len(positions)
        if num_pos < 5:
            score -= (5 - num_pos) * 10  # -10 per missing position
        elif num_pos < 10:
            score -= (10 - num_pos) * 2  # -2 per missing position
        
        # Penalty for concentration (HHI)
        if hhi > 0.25:
            score -= (hhi - 0.25) * 100  # Scale to 0-100
        elif hhi > 0.15:
            score -= (hhi - 0.15) * 50
        
        # Penalty for high correlation
        if avg_correlation > 0.5:
            score -= (avg_correlation - 0.5) * 50
        
        # Penalty for sector concentration
        sector_conc = self._calculate_sector_concentration(positions)
        if sector_conc:
            max_sector = max(sector_conc.values())
            if max_sector > 0.5:
                score -= (max_sector - 0.5) * 40
        
        return max(0.0, min(100.0, score))
    
    def _calculate_effective_positions(self, positions: List[PositionInfo]) -> float:
        """
        Calculate effective number of positions.
        
        Accounts for concentration: effective_N = 1 / HHI
        - If all positions equal weight: effective_N = N
        - If concentrated: effective_N < N
        """
        hhi = self._calculate_herfindahl_index(positions)
        return 1.0 / hhi if hhi > 0 else 0.0
    
    def _calculate_sector_concentration(
        self,
        positions: List[PositionInfo]
    ) -> Dict[str, float]:
        """Calculate portfolio weight by sector"""
        sector_weights = defaultdict(float)
        
        for pos in positions:
            if pos.sector:
                sector_weights[pos.sector] += pos.weight
            else:
                sector_weights["Unknown"] += pos.weight
        
        return dict(sector_weights)
    
    def _calculate_industry_concentration(
        self,
        positions: List[PositionInfo]
    ) -> Dict[str, float]:
        """Calculate portfolio weight by industry"""
        industry_weights = defaultdict(float)
        
        for pos in positions:
            if pos.industry:
                industry_weights[pos.industry] += pos.weight
            else:
                industry_weights["Unknown"] += pos.weight
        
        return dict(industry_weights)
    
    def get_correlation(self, symbol1: str, symbol2: str) -> Optional[float]:
        """
        Get correlation between two symbols.
        
        Parameters
        ----------
        symbol1 : str
            First symbol
        symbol2 : str
            Second symbol
            
        Returns
        -------
        float or None
            Correlation coefficient, or None if not available
        """
        if self.correlation_matrix is None:
            return None
        
        if symbol1 not in self.symbol_index or symbol2 not in self.symbol_index:
            return None
        
        i = self.symbol_index[symbol1]
        j = self.symbol_index[symbol2]
        
        corr = self.correlation_matrix[i, j]
        return float(corr) if not np.isnan(corr) else None
    
    def get_high_correlation_pairs(
        self,
        positions: List[PositionInfo],
        threshold: Optional[float] = None,
    ) -> List[CorrelationPair]:
        """
        Get pairs of positions with high correlation.
        
        Parameters
        ----------
        positions : List[PositionInfo]
            Current positions
        threshold : float, optional
            Correlation threshold (default: use high_correlation_threshold)
            
        Returns
        -------
        List[CorrelationPair]
            List of highly correlated pairs, sorted by risk
        """
        if threshold is None:
            threshold = self.high_correlation_threshold
        
        if self.correlation_matrix is None:
            return []
        
        pairs = []
        n = len(self.symbol_index)
        
        for i in range(n):
            for j in range(i + 1, n):
                corr = self.correlation_matrix[i, j]
                if np.isnan(corr) or abs(corr) < threshold:
                    continue
                
                # Find symbols
                symbol1 = next(s for s, idx in self.symbol_index.items() if idx == i)
                symbol2 = next(s for s, idx in self.symbol_index.items() if idx == j)
                
                # Find positions
                pos1 = next((p for p in positions if p.symbol == symbol1), None)
                pos2 = next((p for p in positions if p.symbol == symbol2), None)
                
                if pos1 and pos2:
                    combined_weight = pos1.weight + pos2.weight
                    
                    # Determine risk level
                    if abs(corr) >= self.critical_correlation_threshold:
                        risk_level = "CRITICAL"
                    elif abs(corr) >= self.high_correlation_threshold:
                        if combined_weight > 0.3:
                            risk_level = "CRITICAL"
                        elif combined_weight > 0.2:
                            risk_level = "HIGH"
                        else:
                            risk_level = "MEDIUM"
                    else:
                        risk_level = "LOW"
                    
                    pairs.append(CorrelationPair(
                        symbol1=symbol1,
                        symbol2=symbol2,
                        correlation=float(corr),
                        combined_weight=combined_weight,
                        risk_level=risk_level,
                    ))
        
        # Sort by risk level and correlation
        risk_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        pairs.sort(key=lambda p: (risk_order[p.risk_level], -abs(p.correlation)))
        
        return pairs
    
    def get_diversification_suggestions(
        self,
        metrics: CorrelationMetrics
    ) -> List[str]:
        """
        Get suggestions to improve diversification.
        
        Parameters
        ----------
        metrics : CorrelationMetrics
            Current correlation metrics
            
        Returns
        -------
        List[str]
            List of actionable suggestions
        """
        suggestions = []
        
        # Concentration issues
        if metrics.is_concentrated:
            suggestions.append(
                f"Portfolio is concentrated (HHI={metrics.herfindahl_index:.3f}). "
                f"Consider reducing largest positions or adding more positions."
            )
        
        if metrics.top_position_pct > 0.30:
            suggestions.append(
                f"Largest position is {metrics.top_position_pct:.1%} of portfolio. "
                f"Consider reducing to below 25%."
            )
        
        # Correlation issues
        if metrics.has_high_correlations:
            suggestions.append(
                f"Found {metrics.high_correlation_pairs} highly correlated pairs. "
                f"Consider reducing exposure to correlated positions."
            )
        
        if metrics.avg_correlation > 0.6:
            suggestions.append(
                f"Average correlation is high ({metrics.avg_correlation:.2f}). "
                f"Portfolio may move as a single unit during market stress."
            )
        
        # Sector/Industry concentration
        if metrics.sector_risk:
            top_sector = max(metrics.sector_concentration.items(), key=lambda x: x[1])
            suggestions.append(
                f"Sector concentration risk: {top_sector[0]} is {top_sector[1]:.1%} of portfolio. "
                f"Consider diversifying across sectors."
            )
        
        if metrics.top_industry_pct > self.max_industry_concentration:
            suggestions.append(
                f"Largest industry is {metrics.top_industry_pct:.1%} of portfolio. "
                f"Consider reducing to below {self.max_industry_concentration:.1%}."
            )
        
        # Position count
        if metrics.num_positions < 5:
            suggestions.append(
                f"Only {metrics.num_positions} positions. "
                f"Consider increasing to at least 5-10 for better diversification."
            )
        
        # Diversification score
        if metrics.diversification_score < self.min_diversification_score:
            suggestions.append(
                f"Diversification score is {metrics.diversification_score:.0f}/100. "
                f"Target is above {self.min_diversification_score:.0f}."
            )
        
        if not suggestions:
            suggestions.append("Portfolio is well diversified. No immediate concerns.")
        
        return suggestions
    
    def check_new_position_impact(
        self,
        current_positions: List[PositionInfo],
        new_position: PositionInfo,
    ) -> Tuple[bool, str, CorrelationMetrics]:
        """
        Check impact of adding a new position on diversification.
        
        Parameters
        ----------
        current_positions : List[PositionInfo]
            Current positions
        new_position : PositionInfo
            Proposed new position
            
        Returns
        -------
        tuple
            (approved: bool, reason: str, projected_metrics: CorrelationMetrics)
        """
        # Calculate projected portfolio
        projected_positions = current_positions.copy()
        projected_positions.append(new_position)
        
        # Recalculate weights
        total_value = sum(p.market_value for p in projected_positions)
        for pos in projected_positions:
            pos.weight = pos.market_value / total_value
        
        # Analyze projected portfolio
        projected_metrics = self.analyze(projected_positions)
        
        # Check for issues
        issues = []
        
        if new_position.weight > 0.25:
            issues.append(f"Position too large ({new_position.weight:.1%} of portfolio)")
        
        if projected_metrics.is_concentrated:
            issues.append(f"Would increase concentration (HHI={projected_metrics.herfindahl_index:.3f})")
        
        if projected_metrics.sector_risk:
            issues.append(f"Would increase sector risk ({projected_metrics.top_sector_pct:.1%} in one sector)")
        
        # Check correlation with existing positions
        if new_position.returns and self.correlation_matrix is not None:
            high_corr_symbols = []
            for pos in current_positions:
                if pos.returns:
                    corr = self._calculate_pairwise_correlation(pos.returns, new_position.returns)
                    if corr and abs(corr) > self.high_correlation_threshold:
                        high_corr_symbols.append(f"{pos.symbol} ({corr:.2f})")
            
            if high_corr_symbols:
                issues.append(f"High correlation with: {', '.join(high_corr_symbols)}")
        
        if issues:
            return False, "; ".join(issues), projected_metrics
        else:
            return True, "Position approved - improves or maintains diversification", projected_metrics
    
    def _calculate_pairwise_correlation(
        self,
        returns1: List[float],
        returns2: List[float]
    ) -> Optional[float]:
        """Calculate correlation between two return series"""
        if len(returns1) < 2 or len(returns2) < 2:
            return None
        
        # Align lengths
        min_len = min(len(returns1), len(returns2))
        r1 = returns1[-min_len:]
        r2 = returns2[-min_len:]
        
        try:
            corr = np.corrcoef(r1, r2)[0, 1]
            return float(corr) if not np.isnan(corr) else None
        except Exception:
            return None
    
    def get_metrics_summary(self, metrics: CorrelationMetrics) -> Dict:
        """Get summary dictionary of metrics for reporting"""
        return {
            "timestamp": metrics.timestamp.isoformat(),
            "num_positions": metrics.num_positions,
            "total_value": metrics.total_value,
            "concentration": {
                "herfindahl_index": metrics.herfindahl_index,
                "top_position": metrics.top_position_pct,
                "top_3": metrics.top_3_positions_pct,
                "top_5": metrics.top_5_positions_pct,
                "is_concentrated": metrics.is_concentrated,
            },
            "correlation": {
                "average": metrics.avg_correlation,
                "maximum": metrics.max_correlation,
                "high_pairs": metrics.high_correlation_pairs,
                "has_high_correlations": metrics.has_high_correlations,
            },
            "diversification": {
                "score": metrics.diversification_score,
                "effective_positions": metrics.effective_positions,
            },
            "sector_exposure": metrics.sector_concentration,
            "industry_exposure": metrics.industry_concentration,
            "risk_flags": {
                "concentrated": metrics.is_concentrated,
                "high_correlations": metrics.has_high_correlations,
                "sector_risk": metrics.sector_risk,
            }
        }
