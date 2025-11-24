"""
Multi-strategy orchestration system.

Coordinates multiple trading strategies, manages signal aggregation,
enforces portfolio-level constraints, and handles dynamic allocation.
"""

import logging
from typing import Dict, List, Optional, Set, Any
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
from threading import Lock

from .signal import Signal, SignalType, SignalStrength
from .base_strategy import BaseStrategy, StrategyConfig


logger = logging.getLogger(__name__)


@dataclass
class StrategyAllocation:
    """
    Strategy allocation information.
    
    Attributes:
        strategy: Strategy instance
        allocation: Percentage of total capital (0.0-1.0)
        available_capital: Current available capital
        used_capital: Currently used capital
        signals_processed: Total signals processed
        signals_accepted: Signals that were accepted
        signals_rejected: Signals that were rejected
    """
    strategy: BaseStrategy
    allocation: float
    available_capital: float = 0.0
    used_capital: float = 0.0
    signals_processed: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0


class StrategyOrchestrator:
    """
    Central coordinator for multi-strategy execution.
    
    Manages:
    - Strategy registration and lifecycle
    - Market data distribution
    - Signal aggregation and conflict resolution
    - Portfolio-level risk constraints
    - Dynamic capital allocation
    
    Example:
        >>> orch = StrategyOrchestrator(total_capital=100000.0)
        >>> orch.register_strategy(strategy1, allocation=0.4)
        >>> orch.register_strategy(strategy2, allocation=0.6)
        >>> orch.start()
        >>> 
        >>> # Market data arrives
        >>> orch.distribute_market_data(market_data)
        >>> 
        >>> # Process signals from strategies
        >>> result = orch.process_signal("Strategy1", signal)
    """
    
    def __init__(
        self, 
        total_capital: float = 100000.0,
        portfolio_heat_limit: float = 0.5,
        max_concentration: float = 0.3
    ):
        """
        Initialize strategy orchestrator.
        
        Args:
            total_capital: Total available capital
            portfolio_heat_limit: Maximum portfolio heat (0.0-1.0)
            max_concentration: Maximum concentration in single position (0.0-1.0)
        """
        self.total_capital = total_capital
        self.portfolio_heat_limit = portfolio_heat_limit
        self.max_concentration = max_concentration
        
        # Strategy management
        self.active_strategies: Dict[str, StrategyAllocation] = {}
        self._lock = Lock()
        
        # State tracking
        self.is_running = False
        self._positions: Dict[str, float] = {}  # symbol -> total position value
        self._portfolio_heat = 0.0
        
        logger.info(
            f"StrategyOrchestrator initialized: "
            f"capital=${total_capital:,.2f}, "
            f"heat_limit={portfolio_heat_limit}, "
            f"max_concentration={max_concentration}"
        )
    
    def register_strategy(self, strategy: BaseStrategy, allocation: float):
        """
        Register a strategy with capital allocation.
        
        Args:
            strategy: Strategy instance
            allocation: Percentage of total capital (0.0-1.0)
            
        Raises:
            ValueError: If allocation invalid or strategy already registered
            RuntimeError: If orchestrator is already running
        """
        if self.is_running:
            raise RuntimeError("Cannot register strategies while running")
        
        # Validate allocation
        if allocation < 0.0 or allocation > 1.0:
            raise ValueError(f"Invalid allocation {allocation}: must be 0.0-1.0")
        
        # Check if strategy already registered
        if strategy.config.name in self.active_strategies:
            raise ValueError(f"Strategy {strategy.config.name} already registered")
        
        # Check total allocation doesn't exceed 100%
        current_total = sum(
            alloc.allocation for alloc in self.active_strategies.values()
        )
        
        if current_total + allocation > 1.0:
            raise ValueError(
                f"Total allocation exceeds 1.0: current={current_total}, "
                f"adding={allocation}"
            )
        
        # Calculate available capital
        available_capital = self.total_capital * allocation
        
        # Create allocation record
        strat_alloc = StrategyAllocation(
            strategy=strategy,
            allocation=allocation,
            available_capital=available_capital
        )
        
        with self._lock:
            self.active_strategies[strategy.config.name] = strat_alloc
        
        logger.info(
            f"Registered strategy '{strategy.config.name}': "
            f"allocation={allocation:.1%}, capital=${available_capital:,.2f}"
        )
    
    def unregister_strategy(self, strategy_name: str):
        """
        Unregister a strategy.
        
        Args:
            strategy_name: Name of strategy to remove
            
        Raises:
            ValueError: If strategy not found
        """
        if strategy_name not in self.active_strategies:
            raise ValueError(f"Strategy '{strategy_name}' not found")
        
        with self._lock:
            alloc = self.active_strategies.pop(strategy_name)
        
        logger.info(
            f"Unregistered strategy '{strategy_name}': "
            f"freed allocation={alloc.allocation:.1%}"
        )
    
    def get_strategy_allocation(self, strategy_name: str) -> float:
        """
        Get allocation for a strategy.
        
        Args:
            strategy_name: Strategy name
            
        Returns:
            Allocation percentage (0.0-1.0)
        """
        if strategy_name not in self.active_strategies:
            raise ValueError(f"Strategy '{strategy_name}' not found")
        
        return self.active_strategies[strategy_name].allocation
    
    def get_available_capital(self, strategy_name: str) -> float:
        """
        Get available capital for a strategy.
        
        Args:
            strategy_name: Strategy name
            
        Returns:
            Available capital amount
        """
        if strategy_name not in self.active_strategies:
            raise ValueError(f"Strategy '{strategy_name}' not found")
        
        alloc = self.active_strategies[strategy_name]
        return alloc.available_capital - alloc.used_capital
    
    def distribute_market_data(self, market_data: Dict[str, Any]) -> List[str]:
        """
        Distribute market data to subscribed strategies.
        
        Args:
            market_data: Market data dictionary with 'symbol' key
            
        Returns:
            List of strategy names that received the data
        """
        if not self.is_running:
            return []
        
        symbol = market_data.get('symbol')
        if not symbol:
            logger.warning("Market data missing 'symbol' field")
            return []
        
        received = []
        
        with self._lock:
            for name, alloc in self.active_strategies.items():
                # Check if strategy subscribes to this symbol
                if symbol in alloc.strategy.config.symbols:
                    try:
                        # Send data to strategy (would call strategy.on_bar() in real system)
                        received.append(name)
                    except Exception as e:
                        logger.error(f"Error distributing to {name}: {e}")
        
        return received
    
    def process_signal(
        self, 
        strategy_name: str, 
        signal: Signal
    ) -> Dict[str, Any]:
        """
        Process a signal from a strategy.
        
        Args:
            strategy_name: Name of strategy generating signal
            signal: Trading signal
            
        Returns:
            Dictionary with processing result:
                - accepted (bool): Whether signal was accepted
                - signal (Signal): The processed signal
                - reason (str): Rejection reason if not accepted
            
        Raises:
            ValueError: If strategy not registered
        """
        if strategy_name not in self.active_strategies:
            raise ValueError(f"Strategy '{strategy_name}' not registered")
        
        alloc = self.active_strategies[strategy_name]
        alloc.signals_processed += 1
        
        # Validate signal
        if not signal.validate():
            alloc.signals_rejected += 1
            return {
                'accepted': False,
                'signal': signal,
                'reason': 'Invalid signal: failed validation'
            }
        
        # Check negative quantity
        if signal.quantity is not None and signal.quantity < 0:
            alloc.signals_rejected += 1
            return {
                'accepted': False,
                'signal': signal,
                'reason': 'Invalid signal: negative quantity'
            }
        
        # Check allocation constraints
        signal_value = (signal.quantity or 0) * (signal.target_price or 0)
        
        if signal_value > self.get_available_capital(strategy_name):
            alloc.signals_rejected += 1
            return {
                'accepted': False,
                'signal': signal,
                'reason': f'Exceeds strategy allocation: needs ${signal_value:,.2f}, '
                         f'available ${self.get_available_capital(strategy_name):,.2f}'
            }
        
        # Check portfolio constraints
        constraints = self.check_portfolio_constraints(signal)
        
        if not constraints['passed']:
            alloc.signals_rejected += 1
            return {
                'accepted': False,
                'signal': signal,
                'reason': constraints['reason']
            }
        
        # Signal accepted
        alloc.signals_accepted += 1
        alloc.used_capital += signal_value
        
        # Update position tracking
        current_position = self._positions.get(signal.symbol, 0.0)
        self._positions[signal.symbol] = current_position + signal_value
        
        logger.debug(
            f"Signal accepted from {strategy_name}: "
            f"{signal.signal_type.value} {signal.quantity} {signal.symbol}"
        )
        
        return {
            'accepted': True,
            'signal': signal,
            'reason': 'Signal accepted'
        }
    
    def check_portfolio_constraints(self, signal: Signal) -> Dict[str, Any]:
        """
        Check if signal satisfies portfolio-level constraints.
        
        Args:
            signal: Signal to check
            
        Returns:
            Dictionary with:
                - passed (bool): Whether constraints passed
                - reason (str): Failure reason if not passed
                - checks (dict): Individual constraint check results
        """
        checks = {}
        
        # Check portfolio heat
        signal_heat = self._calculate_signal_heat(signal)
        total_heat = self._portfolio_heat + signal_heat
        
        checks['heat'] = {
            'current': self._portfolio_heat,
            'signal_add': signal_heat,
            'total': total_heat,
            'limit': self.portfolio_heat_limit,
            'passed': total_heat <= self.portfolio_heat_limit
        }
        
        # Check concentration
        signal_value = (signal.quantity or 0) * (signal.target_price or 0)
        current_position = self._positions.get(signal.symbol, 0.0)
        new_position = current_position + signal_value
        concentration = new_position / self.total_capital
        
        checks['concentration'] = {
            'current': current_position / self.total_capital,
            'signal_add': signal_value / self.total_capital,
            'total': concentration,
            'limit': self.max_concentration,
            'passed': concentration <= self.max_concentration
        }
        
        # Determine overall result
        all_passed = all(check['passed'] for check in checks.values())
        
        reason = "All constraints passed"
        if not all_passed:
            failed = [name for name, check in checks.items() if not check['passed']]
            reason = f"Failed constraints: {', '.join(failed)}"
        
        return {
            'passed': all_passed,
            'reason': reason,
            'checks': checks
        }
    
    def _calculate_signal_heat(self, signal: Signal) -> float:
        """
        Calculate heat contribution of a signal.
        
        Args:
            signal: Trading signal
            
        Returns:
            Heat value (0.0-1.0)
        """
        # Simplified heat calculation
        # In real system, would factor in volatility, position size, etc.
        signal_value = (signal.quantity or 0) * (signal.target_price or 0)
        return (signal_value / self.total_capital) * 0.5  # Scale factor
    
    def get_position(self, symbol: str) -> float:
        """
        Get total position value for a symbol across all strategies.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Total position value
        """
        return self._positions.get(symbol, 0.0)
    
    def rebalance_allocations(self, new_allocations: Dict[str, float]):
        """
        Rebalance strategy allocations.
        
        Args:
            new_allocations: Dict mapping strategy name to new allocation
            
        Raises:
            ValueError: If total allocation doesn't sum to 1.0
        """
        # Validate total allocation
        total = sum(new_allocations.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Allocations must sum to 1.0, got {total}")
        
        # Update allocations
        with self._lock:
            for strategy_name, allocation in new_allocations.items():
                if strategy_name not in self.active_strategies:
                    logger.warning(f"Strategy '{strategy_name}' not found for rebalancing")
                    continue
                
                alloc = self.active_strategies[strategy_name]
                old_allocation = alloc.allocation
                alloc.allocation = allocation
                alloc.available_capital = self.total_capital * allocation
                
                logger.info(
                    f"Rebalanced '{strategy_name}': "
                    f"{old_allocation:.1%} -> {allocation:.1%}"
                )
    
    def get_portfolio_status(self) -> Dict[str, Any]:
        """
        Get current portfolio status.
        
        Returns:
            Dictionary with portfolio metrics
        """
        total_strategies = len(self.active_strategies)
        
        with self._lock:
            allocated_capital = sum(
                alloc.available_capital for alloc in self.active_strategies.values()
            )
            
            used_capital = sum(
                alloc.used_capital for alloc in self.active_strategies.values()
            )
        
        return {
            'total_strategies': total_strategies,
            'active_strategies': total_strategies,  # All registered are active
            'total_capital': self.total_capital,
            'allocated_capital': allocated_capital,
            'used_capital': used_capital,
            'available_capital': allocated_capital - used_capital,
            'portfolio_heat': self._portfolio_heat,
            'positions': dict(self._positions)
        }
    
    def get_strategy_status(self, strategy_name: str) -> Dict[str, Any]:
        """
        Get status for a specific strategy.
        
        Args:
            strategy_name: Strategy name
            
        Returns:
            Dictionary with strategy metrics
        """
        if strategy_name not in self.active_strategies:
            raise ValueError(f"Strategy '{strategy_name}' not found")
        
        alloc = self.active_strategies[strategy_name]
        
        return {
            'name': strategy_name,
            'allocation': alloc.allocation,
            'available_capital': alloc.available_capital,
            'used_capital': alloc.used_capital,
            'signals_processed': alloc.signals_processed,
            'signals_accepted': alloc.signals_accepted,
            'signals_rejected': alloc.signals_rejected
        }
    
    def start(self):
        """Start the orchestrator"""
        if self.is_running:
            logger.warning("Orchestrator already running")
            return
        
        self.is_running = True
        logger.info("Strategy orchestrator started")
    
    def stop(self):
        """Stop the orchestrator"""
        if not self.is_running:
            return
        
        self.is_running = False
        logger.info("Strategy orchestrator stopped")
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()


class SignalAggregator:
    """
    Aggregate signals from multiple strategies for the same symbol.
    
    Combines signals using confidence-weighted logic.
    """
    
    def aggregate(self, signals: List[Signal]) -> Optional[Signal]:
        """
        Aggregate multiple signals into one.
        
        Args:
            signals: List of signals for same symbol
            
        Returns:
            Aggregated signal or None if signals cancel out
        """
        if not signals:
            return None
        
        if len(signals) == 1:
            return signals[0]
        
        # Separate by direction
        buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in signals if s.signal_type == SignalType.SELL]
        
        # Calculate weighted quantities
        buy_qty = sum(s.quantity * s.confidence for s in buy_signals)
        sell_qty = sum(s.quantity * s.confidence for s in sell_signals)
        
        # Net position
        net_qty = buy_qty - sell_qty
        
        if abs(net_qty) < 0.01:
            return None  # Signals cancel out
        
        # Create aggregated signal
        signal_type = SignalType.BUY if net_qty > 0 else SignalType.SELL
        
        # Weighted average confidence
        total_confidence = sum(s.confidence for s in signals)
        avg_confidence = total_confidence / len(signals)
        
        # Weighted average price
        avg_price = sum(s.target_price * s.confidence for s in signals) / total_confidence
        
        return Signal(
            symbol=signals[0].symbol,
            signal_type=signal_type,
            strength=SignalStrength.STRONG if avg_confidence > 0.7 else SignalStrength.MODERATE,
            timestamp=datetime.now(),
            quantity=int(abs(net_qty)),
            target_price=avg_price,
            confidence=avg_confidence,
            strategy_name="Aggregated",
            reason=f"Aggregated from {len(signals)} signals"
        )


class ConflictResolver:
    """
    Resolve conflicting signals from different strategies.
    
    Uses priority-based resolution (higher confidence wins).
    """
    
    def resolve(self, signals: List[Signal]) -> Optional[Signal]:
        """
        Resolve conflicting signals.
        
        Args:
            signals: List of conflicting signals
            
        Returns:
            Winning signal based on confidence
        """
        if not signals:
            return None
        
        if len(signals) == 1:
            return signals[0]
        
        # Check if all same direction - if so, aggregate
        signal_types = set(s.signal_type for s in signals)
        
        if len(signal_types) == 1:
            # All same direction - use aggregator
            aggregator = SignalAggregator()
            return aggregator.aggregate(signals)
        
        # Different directions - pick highest confidence
        best_signal = max(signals, key=lambda s: s.confidence)
        
        logger.debug(
            f"Conflict resolved: selected {best_signal.strategy_name} "
            f"(confidence={best_signal.confidence:.2f})"
        )
        
        return best_signal


class AllocationManager:
    """
    Manage dynamic capital allocation across strategies.
    
    Handles rebalancing based on performance and market conditions.
    """
    
    def __init__(self, orchestrator: StrategyOrchestrator):
        """
        Initialize allocation manager.
        
        Args:
            orchestrator: Strategy orchestrator instance
        """
        self.orchestrator = orchestrator
        logger.info("AllocationManager initialized")
    
    def calculate_performance_based_allocation(
        self, 
        performance_metrics: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate new allocations based on strategy performance.
        
        Args:
            performance_metrics: Dict mapping strategy name to performance score
            
        Returns:
            Dict mapping strategy name to new allocation
        """
        # Normalize performance scores
        total_performance = sum(performance_metrics.values())
        
        if total_performance <= 0:
            # Equal allocation if no positive performance
            num_strategies = len(performance_metrics)
            return {
                name: 1.0 / num_strategies 
                for name in performance_metrics.keys()
            }
        
        # Allocate proportionally to performance
        new_allocations = {
            name: perf / total_performance
            for name, perf in performance_metrics.items()
        }
        
        return new_allocations
    
    def rebalance(self, new_allocations: Dict[str, float]):
        """
        Execute rebalancing with new allocations.
        
        Args:
            new_allocations: Dict mapping strategy name to new allocation
        """
        self.orchestrator.rebalance_allocations(new_allocations)
        logger.info("Rebalancing completed")
