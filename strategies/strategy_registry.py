"""
Strategy Registry for managing multiple trading strategies.

Provides centralized registration, lifecycle management,
and coordination for all active strategies.
"""

import logging
from typing import Dict, List, Optional, Type
from datetime import datetime

from .base_strategy import BaseStrategy, StrategyState, StrategyConfig
from .signal import Signal


logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    Central registry for managing multiple trading strategies.
    
    Features:
    - Strategy registration and discovery
    - Lifecycle management for all strategies
    - Signal aggregation from multiple strategies
    - Performance monitoring and reporting
    
    Example:
        >>> registry = StrategyRegistry(event_bus)
        >>> 
        >>> # Register strategy classes
        >>> registry.register_strategy_class("BollingerBands", BollingerBandsStrategy)
        >>> 
        >>> # Create and start strategy instance
        >>> config = StrategyConfig(name="BB_AAPL", symbols=["AAPL"])
        >>> registry.create_strategy("BollingerBands", config)
        >>> registry.start_strategy("BB_AAPL")
        >>> 
        >>> # Manage all strategies
        >>> registry.start_all()
        >>> registry.pause_all()
        >>> registry.stop_all()
    """
    
    def __init__(self, event_bus=None):
        """
        Initialize strategy registry.
        
        Args:
            event_bus: Event bus instance for communication
        """
        self.event_bus = event_bus
        
        # Registry of strategy classes (name -> class)
        self._strategy_classes: Dict[str, Type[BaseStrategy]] = {}
        
        # Active strategy instances (name -> instance)
        self._strategies: Dict[str, BaseStrategy] = {}
        
        logger.info("StrategyRegistry initialized")
    
    def register_strategy_class(self, name: str, strategy_class: Type[BaseStrategy]):
        """
        Register a strategy class.
        
        Args:
            name: Strategy type name (e.g., "BollingerBands")
            strategy_class: Strategy class (subclass of BaseStrategy)
        """
        if not issubclass(strategy_class, BaseStrategy):
            raise ValueError(f"{strategy_class} must be a subclass of BaseStrategy")
        
        self._strategy_classes[name] = strategy_class
        logger.info(f"Registered strategy class: {name}")
    
    def unregister_strategy_class(self, name: str):
        """
        Unregister a strategy class.
        
        Args:
            name: Strategy type name
        """
        if name in self._strategy_classes:
            del self._strategy_classes[name]
            logger.info(f"Unregistered strategy class: {name}")
    
    def get_registered_classes(self) -> List[str]:
        """
        Get list of registered strategy class names.
        
        Returns:
            List of strategy type names
        """
        return list(self._strategy_classes.keys())
    
    def create_strategy(self, strategy_type: str, config: StrategyConfig) -> BaseStrategy:
        """
        Create a strategy instance from registered class.
        
        Args:
            strategy_type: Type of strategy (must be registered)
            config: Strategy configuration
            
        Returns:
            Created strategy instance
            
        Raises:
            ValueError: If strategy type not registered or config invalid
        """
        if strategy_type not in self._strategy_classes:
            raise ValueError(f"Strategy type '{strategy_type}' not registered")
        
        if not config.validate():
            raise ValueError(f"Invalid configuration for {config.name}")
        
        if config.name in self._strategies:
            raise ValueError(f"Strategy '{config.name}' already exists")
        
        # Create instance
        strategy_class = self._strategy_classes[strategy_type]
        strategy = strategy_class(config, self.event_bus)
        
        # Register instance
        self._strategies[config.name] = strategy
        
        logger.info(f"Created strategy instance: {config.name} (type: {strategy_type})")
        
        return strategy
    
    def remove_strategy(self, strategy_name: str):
        """
        Remove a strategy instance.
        
        Stops the strategy if running before removing.
        
        Args:
            strategy_name: Name of strategy to remove
        """
        if strategy_name not in self._strategies:
            logger.warning(f"Strategy '{strategy_name}' not found")
            return
        
        strategy = self._strategies[strategy_name]
        
        # Stop if running
        if strategy.state == StrategyState.RUNNING:
            strategy.stop()
        
        del self._strategies[strategy_name]
        logger.info(f"Removed strategy: {strategy_name}")
    
    def get_strategy(self, strategy_name: str) -> Optional[BaseStrategy]:
        """
        Get a strategy instance by name.
        
        Args:
            strategy_name: Name of strategy
            
        Returns:
            Strategy instance or None if not found
        """
        return self._strategies.get(strategy_name)
    
    def get_all_strategies(self) -> List[BaseStrategy]:
        """
        Get all registered strategy instances.
        
        Returns:
            List of all strategy instances
        """
        return list(self._strategies.values())
    
    def get_strategy_names(self) -> List[str]:
        """
        Get names of all registered strategies.
        
        Returns:
            List of strategy names
        """
        return list(self._strategies.keys())
    
    def start_strategy(self, strategy_name: str):
        """
        Start a specific strategy.
        
        Args:
            strategy_name: Name of strategy to start
        """
        strategy = self.get_strategy(strategy_name)
        if not strategy:
            logger.error(f"Strategy '{strategy_name}' not found")
            return
        
        strategy.start()
    
    def stop_strategy(self, strategy_name: str):
        """
        Stop a specific strategy.
        
        Args:
            strategy_name: Name of strategy to stop
        """
        strategy = self.get_strategy(strategy_name)
        if not strategy:
            logger.error(f"Strategy '{strategy_name}' not found")
            return
        
        strategy.stop()
    
    def pause_strategy(self, strategy_name: str):
        """
        Pause a specific strategy.
        
        Args:
            strategy_name: Name of strategy to pause
        """
        strategy = self.get_strategy(strategy_name)
        if not strategy:
            logger.error(f"Strategy '{strategy_name}' not found")
            return
        
        strategy.pause()
    
    def resume_strategy(self, strategy_name: str):
        """
        Resume a specific strategy.
        
        Args:
            strategy_name: Name of strategy to resume
        """
        strategy = self.get_strategy(strategy_name)
        if not strategy:
            logger.error(f"Strategy '{strategy_name}' not found")
            return
        
        strategy.resume()
    
    def start_all(self):
        """Start all registered strategies"""
        for strategy in self._strategies.values():
            if strategy.state in [StrategyState.READY, StrategyState.PAUSED]:
                strategy.start()
        
        logger.info(f"Started {len(self._strategies)} strategies")
    
    def stop_all(self):
        """Stop all registered strategies"""
        for strategy in self._strategies.values():
            if strategy.state != StrategyState.STOPPED:
                strategy.stop()
        
        logger.info(f"Stopped {len(self._strategies)} strategies")
    
    def pause_all(self):
        """Pause all running strategies"""
        paused_count = 0
        for strategy in self._strategies.values():
            if strategy.state == StrategyState.RUNNING:
                strategy.pause()
                paused_count += 1
        
        logger.info(f"Paused {paused_count} strategies")
    
    def resume_all(self):
        """Resume all paused strategies"""
        resumed_count = 0
        for strategy in self._strategies.values():
            if strategy.state == StrategyState.PAUSED:
                strategy.resume()
                resumed_count += 1
        
        logger.info(f"Resumed {resumed_count} strategies")
    
    def reload_config(self, strategy_name: str, new_config: StrategyConfig):
        """
        Hot-reload configuration for a strategy.
        
        Args:
            strategy_name: Name of strategy
            new_config: New configuration
        """
        strategy = self.get_strategy(strategy_name)
        if not strategy:
            logger.error(f"Strategy '{strategy_name}' not found")
            return
        
        strategy.reload_config(new_config)
    
    def get_strategies_by_state(self, state: StrategyState) -> List[BaseStrategy]:
        """
        Get all strategies in a specific state.
        
        Args:
            state: Strategy state to filter by
            
        Returns:
            List of strategies in the specified state
        """
        return [s for s in self._strategies.values() if s.state == state]
    
    def get_strategies_by_symbol(self, symbol: str) -> List[BaseStrategy]:
        """
        Get all strategies trading a specific symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of strategies that trade the symbol
        """
        return [s for s in self._strategies.values() 
                if symbol in s.config.symbols]
    
    def get_running_count(self) -> int:
        """
        Get count of running strategies.
        
        Returns:
            Number of strategies in RUNNING state
        """
        return len(self.get_strategies_by_state(StrategyState.RUNNING))
    
    def get_overall_summary(self) -> Dict[str, any]:
        """
        Get overall summary of all strategies.
        
        Returns:
            Dictionary with aggregate statistics
        """
        total = len(self._strategies)
        running = len(self.get_strategies_by_state(StrategyState.RUNNING))
        paused = len(self.get_strategies_by_state(StrategyState.PAUSED))
        stopped = len(self.get_strategies_by_state(StrategyState.STOPPED))
        error = len(self.get_strategies_by_state(StrategyState.ERROR))
        
        total_signals = sum(s.signals_generated for s in self._strategies.values())
        total_accepted = sum(s.signals_accepted for s in self._strategies.values())
        total_rejected = sum(s.signals_rejected for s in self._strategies.values())
        
        # Get all traded symbols
        all_symbols = set()
        for strategy in self._strategies.values():
            all_symbols.update(strategy.config.symbols)
        
        return {
            'total_strategies': total,
            'running': running,
            'paused': paused,
            'stopped': stopped,
            'error': error,
            'total_signals': total_signals,
            'total_accepted': total_accepted,
            'total_rejected': total_rejected,
            'acceptance_rate': (total_accepted / total_signals 
                               if total_signals > 0 else 0.0),
            'symbols_traded': sorted(list(all_symbols)),
            'timestamp': datetime.now().isoformat()
        }
    
    def get_detailed_report(self) -> List[Dict[str, any]]:
        """
        Get detailed performance report for all strategies.
        
        Returns:
            List of performance summaries for each strategy
        """
        return [strategy.get_performance_summary() 
                for strategy in self._strategies.values()]
    
    def __len__(self) -> int:
        """Return number of registered strategies"""
        return len(self._strategies)
    
    def __contains__(self, strategy_name: str) -> bool:
        """Check if strategy is registered"""
        return strategy_name in self._strategies
    
    def __str__(self) -> str:
        """String representation"""
        return f"StrategyRegistry({len(self._strategies)} strategies)"
    
    def __repr__(self) -> str:
        """Detailed representation"""
        running = self.get_running_count()
        return (f"StrategyRegistry(total={len(self._strategies)}, "
                f"running={running}, "
                f"classes={len(self._strategy_classes)})")
