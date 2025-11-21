"""
Backtest Engine Core

Main orchestration engine for running backtests with strategy integration,
risk management, and performance tracking.

Features:
- Strategy execution with bar-by-bar simulation
- Risk management integration (RiskManager, PositionSizer, etc.)
- Portfolio-level tracking and metrics
- Equity curve calculation
- Multi-strategy support
- Event callbacks

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 2
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .data_models import Bar, MarketData, Position, Trade
from .data_manager import HistoricalDataManager
from .market_simulator import MarketSimulator, Order
from .strategy import Strategy, StrategyConfig

# Import Week 3 risk management components (optional)
try:
    from risk.risk_manager import RiskManager
    from risk.position_sizer import FixedPercentSizer
    from risk.drawdown_monitor import DrawdownMonitor
    RISK_AVAILABLE = True
except ImportError:
    RISK_AVAILABLE = False


@dataclass
class BacktestConfig:
    """Configuration for backtest engine"""
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100000.0
    
    # Risk management
    use_risk_management: bool = False  # Disabled by default for simplicity
    max_position_pct: float = 0.25  # 25% max per position
    max_drawdown_pct: float = 0.20  # 20% max drawdown
    
    # Execution
    commission_per_share: float = 0.005
    min_commission: float = 1.0
    
    # Performance tracking
    track_equity_curve: bool = True


@dataclass
class EquityPoint:
    """Single point in equity curve"""
    timestamp: datetime
    equity: float
    cash: float
    positions_value: float
    drawdown: float = 0.0


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    # Configuration
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    
    # Performance
    final_equity: float
    total_return: float
    total_pnl: float
    
    # Trading stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # Risk metrics
    max_drawdown: float
    max_drawdown_pct: float
    
    # Equity curve
    equity_curve: List[EquityPoint] = field(default_factory=list)
    
    # All trades
    trades: List[Trade] = field(default_factory=list)
    
    def get_return_pct(self) -> float:
        """Get total return percentage"""
        return self.total_return * 100
    
    def get_win_rate_pct(self) -> float:
        """Get win rate percentage"""
        return self.win_rate * 100
    
    def __repr__(self) -> str:
        return (f"BacktestResult({self.strategy_name}: "
                f"Return={self.get_return_pct():.2f}%, "
                f"Trades={self.total_trades}, "
                f"WinRate={self.get_win_rate_pct():.1f}%)")


class BacktestEngine:
    """
    Main backtesting engine
    
    Orchestrates:
    - Historical data replay
    - Strategy execution
    - Risk management
    - Order execution
    - Performance tracking
    """
    
    def __init__(self, config: BacktestConfig, data_manager: HistoricalDataManager):
        """
        Initialize backtest engine
        
        Args:
            config: Backtest configuration
            data_manager: Historical data manager
        """
        self.config = config
        self.data_manager = data_manager
        
        # Market simulator (uses default fill simulator with built-in commission)
        self.market_sim = MarketSimulator(data_manager)
        
        # Strategy
        self.strategy: Optional[Strategy] = None
        
        # Risk management components (Week 3) - optional
        self.risk_manager = None
        self.position_sizer = None
        self.drawdown_monitor = None
        
        # Portfolio state
        self.cash = config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.equity_curve: List[EquityPoint] = []
        self.all_trades: List[Trade] = []
        
        # Peak tracking
        self.peak_equity = config.initial_capital
        self.max_drawdown_value = 0.0
        self.max_drawdown_pct = 0.0
        
        # Callbacks
        self._bar_callbacks: List[Callable] = []
        self._trade_callbacks: List[Callable] = []
    
    # ==================== Setup ====================
    
    def set_strategy(self, strategy: Strategy):
        """
        Attach a strategy to the engine
        
        Args:
            strategy: Strategy instance
        """
        self.strategy = strategy
        
        # Connect strategy to engine callbacks
        strategy._submit_order_callback = self._handle_strategy_order
        strategy._cancel_order_callback = self.market_sim.cancel_order
        strategy._get_position_callback = self._get_position_for_strategy
        
        # Register for trade callbacks
        self.market_sim.register_trade_callback(self._on_trade)
    
    def set_risk_manager(self, risk_manager):
        """Set risk manager"""
        self.risk_manager = risk_manager
    
    def set_position_sizer(self, position_sizer):
        """Set position sizer"""
        self.position_sizer = position_sizer
    
    def set_drawdown_monitor(self, drawdown_monitor):
        """Set drawdown monitor"""
        self.drawdown_monitor = drawdown_monitor
    
    def enable_risk_management(self):
        """Enable risk management with default configs"""
        if not RISK_AVAILABLE:
            print("Warning: Risk management components not available")
            return
        
        self.risk_manager = RiskManager(
            initial_capital=self.config.initial_capital,
            max_position_pct=self.config.max_position_pct,
            max_drawdown_pct=self.config.max_drawdown_pct
        )
        self.position_sizer = FixedPercentSizer(
            position_pct=0.10,  # 10% default
            max_position_pct=self.config.max_position_pct
        )
        self.drawdown_monitor = DrawdownMonitor(
            equity=self.config.initial_capital,
            max_drawdown_pct=self.config.max_drawdown_pct
        )
    
    # ==================== Execution ====================
    
    def run(self) -> BacktestResult:
        """
        Run the backtest
        
        Returns:
            BacktestResult with performance metrics
        """
        if not self.strategy:
            raise ValueError("No strategy set. Call set_strategy() first.")
        
        # Initialize
        self._initialize()
        
        # Run strategy initialization
        self.strategy.on_start()
        
        # Main backtest loop
        bar_count = 0
        for market_data in self.market_sim.replay(
            self.config.start_date,
            self.config.end_date,
            self.strategy.config.symbols
        ):
            bar_count += 1
            
            # Update current market data
            self._update_prices(market_data)
            
            # Update strategy with new bar
            self.strategy._update_bar(market_data)
            
            # Call strategy
            self.strategy.on_bar(market_data)
            
            # Update positions and equity
            self._update_portfolio(market_data)
            
            # Track equity curve
            if self.config.track_equity_curve:
                self._record_equity_point(market_data.timestamp)
            
            # Call custom callbacks
            for callback in self._bar_callbacks:
                callback(market_data)
        
        # Finalize
        self.strategy.on_stop()
        
        # Generate result
        result = self._generate_result()
        
        return result
    
    def _initialize(self):
        """Initialize backtest state"""
        self.cash = self.config.initial_capital
        self.positions = {}
        self.equity_curve = []
        self.all_trades = []
        self.peak_equity = self.config.initial_capital
        self.max_drawdown_value = 0.0
        self.max_drawdown_pct = 0.0
        
        # Register market simulator callbacks
        self.market_sim.register_bar_callback(self._on_bar)
        self.market_sim.register_trade_callback(self._on_trade)
    
    # ==================== Event Handlers ====================
    
    def _on_bar(self, market_data: MarketData):
        """Called for each bar (internal)"""
        pass  # Already handled in run loop
    
    def _on_trade(self, trade: Trade):
        """Called when a trade executes"""
        # Update cash
        if trade.action == 'BUY':
            self.cash -= (trade.value + trade.commission)
        else:
            self.cash += (trade.value - trade.commission)
        
        # Update positions
        self._update_position_from_trade(trade)
        
        # Record trade
        self.all_trades.append(trade)
        
        # Notify strategy
        if self.strategy:
            self.strategy.on_trade(trade)
        
        # Custom callbacks
        for callback in self._trade_callbacks:
            callback(trade)
    
    def _handle_strategy_order(self, order: Order):
        """Handle order from strategy"""
        # Apply risk management if enabled
        if self.config.use_risk_management and self.risk_manager:
            # Check if order is allowed
            current_equity = self._calculate_equity()
            position = self.positions.get(order.symbol)
            current_size = position.quantity if position else 0
            
            # Check risk limits
            allowed, reason = self.risk_manager.can_open_position(
                symbol=order.symbol,
                side='LONG' if order.action == 'BUY' else 'SHORT',
                quantity=order.quantity,
                price=self.strategy.get_current_price(order.symbol) or 0,
                account_value=current_equity
            )
            
            if not allowed:
                print(f"Order rejected by risk manager: {reason}")
                return
            
            # Adjust size with position sizer if enabled
            if self.position_sizer and order.order_type == 'MARKET':
                price = self.strategy.get_current_price(order.symbol) or 0
                suggested_size = self.position_sizer.calculate_position_size(
                    symbol=order.symbol,
                    entry_price=price,
                    account_value=current_equity,
                    risk_per_trade_pct=1.0  # 1% risk per trade
                )
                
                # Use smaller of strategy size and risk-adjusted size
                if suggested_size < order.quantity:
                    order.quantity = suggested_size
        
        # Submit to market simulator
        self.market_sim.submit_order(order)
    
    def _get_position_for_strategy(self, symbol: str) -> Optional[Position]:
        """Get position for strategy queries"""
        return self.positions.get(symbol)
    
    # ==================== Portfolio Management ====================
    
    def _update_prices(self, market_data: MarketData):
        """Update current prices for positions"""
        for symbol in market_data.symbols:
            if symbol in self.positions:
                position = self.positions[symbol]
                position.current_price = market_data.get_close(symbol)
    
    def _update_position_from_trade(self, trade: Trade):
        """Update position from executed trade"""
        symbol = trade.symbol
        
        if symbol not in self.positions:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=0,
                average_cost=0.0,
                current_price=trade.price
            )
        
        position = self.positions[symbol]
        
        if trade.action == 'BUY':
            # Add to position
            total_cost = (position.average_cost * position.quantity + 
                         trade.price * trade.quantity)
            position.quantity += trade.quantity
            position.average_cost = total_cost / position.quantity if position.quantity > 0 else 0
        else:
            # Reduce position
            position.quantity -= trade.quantity
            if position.quantity == 0:
                position.average_cost = 0.0
        
        position.current_price = trade.price
        
        # Remove if flat
        if position.quantity == 0:
            del self.positions[symbol]
    
    def _update_portfolio(self, market_data: MarketData):
        """Update portfolio state and risk metrics"""
        # Update position prices
        self._update_prices(market_data)
        
        # Calculate current equity
        equity = self._calculate_equity()
        
        # Update strategy state
        if self.strategy:
            self.strategy._update_state(self.positions.copy(), self.cash)
        
        # Update drawdown tracking
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        drawdown_value = self.peak_equity - equity
        drawdown_pct = (drawdown_value / self.peak_equity) if self.peak_equity > 0 else 0
        
        if drawdown_value > self.max_drawdown_value:
            self.max_drawdown_value = drawdown_value
        if drawdown_pct > self.max_drawdown_pct:
            self.max_drawdown_pct = drawdown_pct
        
        # Update risk monitors
        if self.drawdown_monitor:
            self.drawdown_monitor.update(equity, market_data.timestamp)
            
            # Check for breaches
            if self.drawdown_monitor.is_breach():
                print(f"WARNING: Drawdown breach at {market_data.timestamp}")
                # Could implement emergency stop here
    
    def _calculate_equity(self) -> float:
        """Calculate current total equity"""
        positions_value = sum(
            position.market_value 
            for position in self.positions.values()
        )
        return self.cash + positions_value
    
    def _record_equity_point(self, timestamp: datetime):
        """Record equity curve point"""
        equity = self._calculate_equity()
        positions_value = sum(p.market_value for p in self.positions.values())
        
        drawdown = 0.0
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - equity) / self.peak_equity
        
        point = EquityPoint(
            timestamp=timestamp,
            equity=equity,
            cash=self.cash,
            positions_value=positions_value,
            drawdown=drawdown
        )
        
        self.equity_curve.append(point)
    
    # ==================== Results ====================
    
    def _generate_result(self) -> BacktestResult:
        """Generate backtest result"""
        final_equity = self._calculate_equity()
        total_return = (final_equity - self.config.initial_capital) / self.config.initial_capital
        
        total_trades = len(self.all_trades)
        winning_trades = sum(1 for t in self.all_trades if self._is_winning_trade(t))
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        
        result = BacktestResult(
            strategy_name=self.strategy.config.name,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
            final_equity=final_equity,
            total_return=total_return,
            total_pnl=final_equity - self.config.initial_capital,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            max_drawdown=self.max_drawdown_value,
            max_drawdown_pct=self.max_drawdown_pct,
            equity_curve=self.equity_curve.copy(),
            trades=self.all_trades.copy()
        )
        
        return result
    
    def _is_winning_trade(self, trade: Trade) -> bool:
        """Determine if a trade is winning (simplified)"""
        # This is simplified - in reality need to match buy/sell pairs
        # For now, just use the trade's P&L relative to position average cost
        return trade.action == 'SELL'  # Placeholder
    
    # ==================== Callbacks ====================
    
    def register_bar_callback(self, callback: Callable[[MarketData], None]):
        """Register callback for each bar"""
        self._bar_callbacks.append(callback)
    
    def register_trade_callback(self, callback: Callable[[Trade], None]):
        """Register callback for each trade"""
        self._trade_callbacks.append(callback)
    
    # ==================== Utility ====================
    
    def get_current_equity(self) -> float:
        """Get current total equity"""
        return self._calculate_equity()
    
    def get_positions(self) -> Dict[str, Position]:
        """Get current positions"""
        return self.positions.copy()
    
    def get_equity_curve(self) -> List[EquityPoint]:
        """Get equity curve"""
        return self.equity_curve.copy()
    
    def __repr__(self) -> str:
        strategy_name = self.strategy.config.name if self.strategy else "No Strategy"
        return f"BacktestEngine({strategy_name})"
