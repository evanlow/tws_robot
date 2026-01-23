# TWS Robot - Contributing Guide

**Thank you for considering contributing to TWS Robot!** 🎉

---

## 🎯 Ways to Contribute

### 1. Report Bugs
Found something broken? [Open an issue](https://github.com/evanlow/tws_robot/issues) with:
- What you were trying to do
- What happened (include error messages)
- What you expected to happen
- Your environment (OS, Python version)

### 2. Suggest Features
Have an idea? Open an issue with:
- Description of the feature
- Why it would be useful
- Example use case

### 3. Improve Documentation
- Fix typos or unclear explanations
- Add examples
- Improve diagrams
- Translate to other languages

### 4. Submit Code
- Fix bugs
- Add new strategies
- Improve performance
- Add tests

---

## 🚀 Quick Start for Contributors

### 1. Development Setup

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/tws_robot.git
cd tws_robot

# Set up environment
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate      # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Run tests to verify setup
pytest tests/ -v
```

**✅ All tests must pass** before you start developing.

---

## 📜 Prime Directive - Our Development Philosophy

**READ THIS FIRST:** [prime_directive.md](prime_directive.md)

**TL;DR:**
- ✅ **100% test pass rate** - No exceptions
- ✅ **Zero warnings** - Clean test output always
- ✅ **Verify before coding** - Never assume APIs exist
- ✅ **Test after changes** - Run tests before committing

**Every contribution must maintain:**
```bash
pytest tests/ -v
# Must show: 690 passed, 0 warnings
```

---

## 🔧 Development Workflow

### Before You Start

1. **Read the Prime Directive:** [prime_directive.md](prime_directive.md)
2. **Understand the architecture:** [docs/architecture/overview.md](docs/architecture/overview.md)
3. **Check existing issues:** Someone might already be working on it

### Making Changes

```bash
# Create feature branch
git checkout -b feature/amazing-feature

# Make your changes
# ... edit files ...

# Run tests frequently
pytest tests/ -v

# Commit with clear message
git commit -m "feat: add amazing feature"

# Push and create PR
git push origin feature/amazing-feature
```

### Commit Message Format

Use conventional commits:
```
feat: add new strategy
fix: correct calculation error
docs: improve README clarity
test: add missing test cases
refactor: simplify risk calculation
```

---

## 🧪 Testing Requirements

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_backtest_engine.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Clear cache and rerun
pytest tests/ --cache-clear -v
```

### Writing Tests

**Every new feature needs tests:**

```python
# tests/test_your_feature.py
import pytest
from backtest.strategy import Strategy, StrategyConfig

def test_your_new_feature():
    """Test that your feature works correctly."""
    # Arrange
    config = StrategyConfig(
        name="TestStrategy",
        symbols=['AAPL'],
        initial_capital=100000
    )
    strategy = MyNewStrategy(config)
    
    # Act
    result = strategy.some_method()
    
    # Assert
    assert result.is_valid
    assert result.value > 0
```

**Test both success and failure cases:**
```python
def test_strategy_handles_invalid_input():
    """Test that strategy rejects invalid input."""
    with pytest.raises(ValueError):
        strategy = MyStrategy(invalid_config)
```

---

## 📋 Code Standards

### Strategy Development

**Always inherit from Strategy base class:**
```python
from backtest.strategy import Strategy, StrategyConfig
from backtest.data_models import MarketData

class MyStrategy(Strategy):
    """Your strategy description."""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        # Validate parameters
        self.period = config.parameters.get('period', 20)
        if self.period < 2:
            raise ValueError("Period must be at least 2")
    
    def on_start(self):
        """Initialize strategy state."""
        pass
    
    def on_bar(self, market_data: MarketData):
        """Process market data and generate signals."""
        # Your trading logic here
        pass
    
    def on_stop(self):
        """Cleanup when strategy stops."""
        pass
```

### API Verification

**Follow Prime Directive Section 2:**

```python
# ❌ WRONG - Don't assume
from backtest.data import BarData  # Does BarData exist?
position = risk_manager.validate_trade()  # Does this method exist?

# ✅ RIGHT - Verify first
# Use grep_search to verify:
# grep_search("class Bar", "backtest/data_models.py")
from backtest.data_models import Bar
# Use read_file to verify method:
# read_file("risk/risk_manager.py", check methods)
result = risk_manager.check_trade_risk()
```

### Docstrings

**Use clear, comprehensive docstrings:**
```python
def calculate_position_size(
    self,
    equity: float,
    entry_price: float,
    stop_loss: float
) -> int:
    """
    Calculate position size based on risk parameters.
    
    Args:
        equity: Current account equity in dollars
        entry_price: Planned entry price per share
        stop_loss: Stop loss price per share
    
    Returns:
        Number of shares to trade
    
    Raises:
        ValueError: If stop_loss >= entry_price for long positions
    
    Example:
        >>> sizer = PositionSizer(risk_pct=0.02)
        >>> shares = sizer.calculate_position_size(100000, 150.00, 145.00)
        >>> print(shares)  # 266 shares
    """
    if stop_loss >= entry_price:
        raise ValueError("Stop loss must be below entry price")
    
    risk_per_share = entry_price - stop_loss
    risk_amount = equity * self.risk_pct
    return int(risk_amount / risk_per_share)
```

---

## 📚 Documentation Standards

### User-Facing Documentation
- Use plain language (avoid jargon)
- Include examples
- Explain "why" not just "how"
- Add visual diagrams where helpful

### Developer Documentation
- Be technical and precise
- Include code examples
- Document edge cases
- Link to related docs

### When You Change Code

**Update these if affected:**
- README.md - If user-facing feature
- USER_GUIDE.md - If strategy or workflow changes
- API_REFERENCE.md - If API changes
- CHANGELOG.md - Always document changes

---

## 🎨 Pull Request Process

### Before Submitting

**Checklist:**
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] Zero warnings
- [ ] Added tests for new features
- [ ] Updated documentation
- [ ] Followed Prime Directive
- [ ] Clear commit messages
- [ ] Rebased on latest main

### PR Description Template

```markdown
## Description
Brief description of what this PR does.

## Motivation
Why is this change needed?

## Changes
- Added X feature
- Fixed Y bug
- Updated Z documentation

## Testing
- [ ] All existing tests pass
- [ ] Added new tests for new functionality
- [ ] Tested manually with [describe scenario]

## Documentation
- [ ] Updated README.md
- [ ] Updated USER_GUIDE.md
- [ ] Updated API_REFERENCE.md
- [ ] Added code comments

## Screenshots (if applicable)
[Add screenshots of new features]

## Breaking Changes
[List any breaking changes]

## Checklist
- [ ] Code follows Prime Directive
- [ ] Tests pass with 0 warnings
- [ ] Documentation updated
- [ ] Commit messages are clear
```

### Review Process

1. **Automated checks** run (tests, linting)
2. **Maintainer review** (1-2 business days)
3. **Feedback addressed** (if needed)
4. **Merged!** 🎉

---

## 🏗️ Architecture Guidelines

### Key Principles

1. **Event-Driven:** Use EventBus for component communication
2. **Modular:** Each module has single responsibility
3. **Testable:** Mock external dependencies
4. **Risk-First:** All trades pass through risk management

### Module Structure

```
tws_robot/
├── backtest/      # Historical testing engine
├── strategies/    # Live trading strategies
├── risk/         # Risk management
├── core/         # Infrastructure (EventBus, etc.)
├── execution/    # Order execution
└── monitoring/   # Performance tracking
```

**Add new features in the right place:**
- New strategy? → `backtest/strategy_templates.py` (backtest) or `strategies/` (live)
- Risk control? → `risk/`
- Core infrastructure? → `core/`

---

## 🐛 Debugging Tips

### Use Logging

```python
import logging

logger = logging.getLogger(__name__)

def process_signal(self, signal):
    logger.debug(f"Processing signal: {signal}")
    # ... your code ...
    logger.info(f"Signal processed successfully")
```

### Use Tests for Debugging

```bash
# Run single test with output
pytest tests/test_your_feature.py::test_specific_case -v -s

# Use breakpoint() in code
def my_function():
    breakpoint()  # Drops into debugger
    # ... rest of code ...
```

### Check Test Output

```bash
# See print statements in tests
pytest tests/ -v -s

# See coverage report
pytest tests/ --cov=. --cov-report=term-missing
```

---

## 🌟 Recognition

Contributors will be:
- Added to CONTRIBUTORS.md
- Credited in release notes
- Thanked in project documentation

**Top contributors may be invited to:**
- Become maintainers
- Help with roadmap decisions
- Review other PRs

---

## ❓ Questions?

- Check [docs/](docs/) folder for architecture details
- Read [prime_directive.md](prime_directive.md) for development philosophy
- Open an issue for clarification
- Join discussions in GitHub Discussions

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

**Thank you for making TWS Robot better!** 🚀

Every contribution, no matter how small, makes a difference. Whether it's fixing a typo, adding a test, or building a new feature - we appreciate your help!
