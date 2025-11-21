# Prime Directive: Development Guidelines

**Last Updated:** November 21, 2025  
**Purpose:** Ensure high-quality, maintainable code by learning from past experiences and establishing best practices for all team members, AI agents, and contributors.

---

## 🎯 Core Principles

### 1. **Verify First, Code Second**
Never assume how existing code works. Always verify before implementing.

**❌ Don't:**
```python
# Assuming without checking
timeframe=TimeFrame.DAILY  # Does DAILY exist?
def on_bar(self, symbol, bar):  # Is this the right signature?
```

**✅ Do:**
```python
# Step 1: Check existing code
# grep_search(query="class TimeFrame", includePattern="data_models.py")
# read_file to see: DAY_1, HOUR_1, MINUTE_1

# Step 2: Use correct values
timeframe=TimeFrame.DAY_1
def on_bar(self, market_data):  # Matches base class signature
```

### 2. **Defensive Programming Always**
Assume nothing. Handle None, validate inputs, check bounds.

**❌ Don't:**
```python
position = self.get_position(symbol)
if position <= 0:  # Crashes if None!
    ...
```

**✅ Do:**
```python
position = self.get_position(symbol) or 0  # Default to 0
if position <= 0:
    ...

# Or more explicit:
position = self.get_position(symbol)
if position is None:
    position = 0
```

### 3. **Test Incrementally, Not All At Once**
Build and verify in small steps. Don't write 300 lines before testing.

**✅ Development Flow:**
```python
# Step 1: Test component in isolation
data_manager = HistoricalDataManager(data_dir)
data_manager.load_csv(...)
print(f"✓ Loaded {len(bars)} bars")  # Verify!

# Step 2: Test next component
strategy = MyStrategy(config)
strategy.on_start()  # Does it initialize?

# Step 3: Test integration
result = engine.run()  # Now combine them
```

---

## 🔍 Pre-Implementation Checklist

Before writing ANY new code that uses existing classes/methods:

### ☑️ Research Phase (Mandatory)

1. **Check Method Signatures**
   ```python
   # Use grep_search to find the method definition
   grep_search(query="def method_name", includePattern="filename.py")
   ```

2. **Verify Enum Values**
   ```python
   # Read the enum definition
   read_file("path/to/file.py", offset=line_number, limit=30)
   ```

3. **Inspect Data Structures**
   ```python
   # Check class attributes and properties
   grep_search(query="class ClassName", includePattern="*.py")
   list_code_usages(symbolName="ClassName")
   ```

4. **Find Usage Examples**
   ```python
   # See how others use this API
   grep_search(query="method_call.*pattern", isRegexp=True)
   ```

### ☑️ Before Calling Any Method

- [ ] Checked the method signature (parameters, types, order)
- [ ] Verified return type (can it be None? Optional?)
- [ ] Checked for required imports
- [ ] Looked for existing usage examples
- [ ] Understood parameter types (enum vs string, int vs Optional[int])

### ☑️ Before Using Enums/Constants

- [ ] Verified actual enum value names (not assumed)
- [ ] Checked if it's a string enum or value enum
- [ ] Imported the enum properly

---

## 🚨 Common Pitfalls & Solutions

### Pitfall 1: Wrong Enum Values
**Problem:** Assuming enum names without checking
```python
TimeFrame.DAILY  # ❌ Doesn't exist
```
**Solution:** Always verify enum definitions
```python
TimeFrame.DAY_1  # ✅ Actual value
```
**Prevention:** Read enum source code first, add reference comment:
```python
# TimeFrame: DAY_1, HOUR_1, MINUTE_1, MINUTE_5, etc.
```

### Pitfall 2: Method Signature Mismatch
**Problem:** Implementing interface without checking base class
```python
def on_bar(self, symbol, bar):  # ❌ Wrong signature
```
**Solution:** Check abstract method in base class
```python
def on_bar(self, market_data):  # ✅ Matches Strategy base class
```
**Prevention:** Use `grep_search` to find base class method signature

### Pitfall 3: Attribute Name Assumptions
**Problem:** Guessing attribute names
```python
market_data.symbol  # ❌ It's plural!
```
**Solution:** Check class definition
```python
market_data.symbols  # ✅ Returns list
market_data.get_bar(symbol)  # ✅ Gets bar for symbol
```
**Prevention:** Read class docstrings and inspect attributes

### Pitfall 4: None Type Errors
**Problem:** Not handling None return values
```python
position = get_position(symbol)
if position > 0:  # ❌ Crashes if None
```
**Solution:** Always handle None explicitly
```python
position = get_position(symbol) or 0
if position > 0:  # ✅ Safe
```
**Prevention:** Check return type hints: `Optional[T]` means None is possible

### Pitfall 5: Parameter Type Confusion
**Problem:** Passing string where enum expected
```python
self.buy(symbol, quantity, "market order")  # ❌ String not OrderType
```
**Solution:** Use proper enum type
```python
self.buy(symbol, quantity, OrderType.MARKET)  # ✅ Enum
```
**Prevention:** Check method signature for parameter types

---

## 🛠️ Mandatory Tools Usage

### Before Implementation

| Task | Tool | Example |
|------|------|---------|
| Find method definition | `grep_search` | `grep_search(query="def on_bar", includePattern="strategy.py")` |
| Read enum values | `read_file` | `read_file("data_models.py", offset=17, limit=30)` |
| Check class usage | `list_code_usages` | `list_code_usages(symbolName="Strategy")` |
| Find patterns | `grep_search` (regex) | `grep_search(query="TimeFrame\\.", isRegexp=True)` |
| Verify structure | `read_file` | `read_file("file.py", offset=50, limit=100)` |

### During Development

| Task | Tool | Example |
|------|------|---------|
| Run tests | `run_in_terminal` | `python test_module.py` |
| Check errors | `get_errors` | `get_errors(filePaths=["path/to/file.py"])` |
| Verify changes | `read_file` | Read modified sections |

---

## 📋 Development Workflow (The Right Way™)

### Phase 1: Research (15-20% of time)
```
1. Understand the requirement
2. Find relevant existing code
3. Check base classes and interfaces
4. Verify data structures and enums
5. Look for usage examples
6. Document findings in comments
```

### Phase 2: Design (10-15% of time)
```
1. Sketch out the implementation
2. Identify dependencies
3. Plan for error handling
4. Consider edge cases
5. Keep it simple initially
```

### Phase 3: Implementation (40-50% of time)
```
1. Start with minimal working code
2. Match signatures exactly
3. Add defensive checks (None, bounds, types)
4. Use proper types (enums, not strings)
5. Add logging/print statements for debugging
6. Keep functions small and focused
```

### Phase 4: Testing (20-30% of time)
```
1. Test each component in isolation
2. Add unit tests as you go
3. Run tests frequently (after each component)
4. Fix errors immediately - don't accumulate
5. Verify integration works
6. Run full test suite before committing
```

---

## ✅ Code Quality Standards

### Type Safety
```python
# ✅ GOOD: Use type hints
def calculate_position_size(
    self, 
    symbol: str, 
    price: float,
    fraction: Optional[float] = None
) -> int:
    ...

# ✅ GOOD: Handle Optional types
position: Optional[int] = self.get_position(symbol)
if position is None:
    position = 0
```

### Error Handling
```python
# ✅ GOOD: Validate inputs
if not symbol or symbol not in self.config.symbols:
    return

# ✅ GOOD: Check preconditions
if len(prices) < self.lookback_period:
    return  # Not enough data

# ✅ GOOD: Handle exceptions gracefully
try:
    result = risky_operation()
except SpecificError as e:
    log.warning(f"Operation failed: {e}")
    return default_value
```

### Documentation
```python
# ✅ GOOD: Document assumptions and constraints
def on_bar(self, market_data):
    """
    Process market data bar
    
    Note: MarketData.symbols is a list (plural)
    Note: get_position() returns Optional[int] - check for None!
    """
    for symbol in market_data.symbols:  # Note: plural!
        position = self.get_position(symbol) or 0  # Handle None
        ...
```

---

## 🎓 Learning from Errors

### Week 4 Day 3 Lessons Learned

#### Error 1: TimeFrame.DAILY
- **What happened:** Used `TimeFrame.DAILY` without checking enum
- **Why:** Assumed naming convention
- **Fix:** Check enum source, use `TimeFrame.DAY_1`
- **Lesson:** Never assume enum values - always verify

#### Error 2: on_bar(symbol, bar)
- **What happened:** Wrong method signature for Strategy.on_bar()
- **Why:** Didn't check base class abstract method
- **Fix:** Use correct signature `on_bar(market_data)`
- **Lesson:** Always check base class/interface signatures

#### Error 3: market_data.symbol
- **What happened:** Accessed `.symbol` (singular) instead of `.symbols` (plural)
- **Why:** Assumed single symbol, didn't inspect class
- **Fix:** Use `.symbols` list and iterate
- **Lesson:** Inspect data structure before accessing attributes

#### Error 4: buy(symbol, qty, "reason")
- **What happened:** Passed string as third parameter instead of OrderType enum
- **Why:** Misread method signature
- **Fix:** Use `OrderType.MARKET` enum
- **Lesson:** Check parameter types, not just parameter names

#### Error 5: position <= 0
- **What happened:** Compared None to int, causing TypeError
- **Why:** Didn't handle None return value
- **Fix:** Use `position or 0` to default None to 0
- **Lesson:** Check if methods return Optional types

---

## 📝 Quick Reference Template

Add this comment block at the top of new files:

```python
"""
Quick Reference for this module:

Key Classes:
- ClassName: .attribute1 (type), .method1(params) -> return_type

Important Enums:
- EnumName: VALUE_1, VALUE_2, VALUE_3

Common Patterns:
- Pattern 1: description
- Pattern 2: description

Gotchas:
- Thing that returns None - handle it!
- Attribute is plural (.symbols not .symbol)
- Use EnumType not string
"""
```

---

## 🚀 Integration Best Practices

### When Integrating New Code

1. **Start Simple**
   - Minimal working example first
   - One feature at a time
   - Verify each step

2. **Incremental Integration**
   ```python
   # ✅ Add one component at a time
   # Step 1: Add data loading only
   # Step 2: Add strategy initialization
   # Step 3: Add execution logic
   # Step 4: Add analytics
   ```

3. **Verify At Each Step**
   - Run tests after each addition
   - Check for warnings (they matter!)
   - Fix issues before proceeding

4. **Don't Skip Testing**
   - "I'll test it later" = technical debt
   - Test as you go
   - Automated tests > manual testing

---

## 🎯 Success Metrics

### Before Considering Code "Done"

- [ ] All unit tests passing (100%)
- [ ] No compiler/linter warnings
- [ ] No None-type errors
- [ ] All edge cases handled
- [ ] Code reviewed (by peer or self)
- [ ] Documentation complete
- [ ] Integration tested
- [ ] Performance acceptable

### Definition of "Done"

Code is only done when:
1. ✅ Tests pass
2. ✅ No warnings
3. ✅ Error handling complete
4. ✅ Integrated and verified
5. ✅ Documented
6. ✅ Committed with clear message

---

## 🤝 Team Expectations

### For All Team Members (Human & AI)

1. **Read this document before starting work**
2. **Follow the checklist - every time**
3. **Ask questions if unsure - don't guess**
4. **Test incrementally - don't batch**
5. **Fix errors immediately - don't defer**
6. **Document learnings - update this file**

### For AI Agents Specifically

1. **Always use verification tools before implementing**
   - `grep_search`, `read_file`, `list_code_usages`
2. **Never assume - always verify**
3. **Test each component before moving on**
4. **Read error messages completely and act on them**
5. **Keep implementations simple initially**
6. **Ask for clarification if requirements are ambiguous**

### For Code Reviewers

1. **Check that verification was done**
   - Were existing patterns checked?
   - Were types validated?
2. **Look for None handling**
3. **Verify test coverage**
4. **Ensure error handling present**
5. **Confirm documentation exists**

---

## 📚 Resources

### Internal Documentation
- `README.md` - Project overview
- `backtest/README.md` - Backtesting framework docs
- `risk/README.md` - Risk management docs
- Test files - Living examples of correct usage

### When in Doubt
1. Check existing tests - they show correct usage
2. Use `grep_search` to find patterns
3. Read the source code - it's the truth
4. Ask the team - collaboration over guessing

---

## 🔄 Document Maintenance

### When to Update This Document

- After encountering a new type of error
- When establishing a new pattern
- After team retrospectives
- When tooling changes
- Quarterly review minimum

### How to Update

1. Add specific examples
2. Keep it practical, not theoretical
3. Include code snippets
4. Update "Lessons Learned" section
5. Date the changes

---

## 💡 Remember

> **"The best code is code that works correctly the first time because you took the time to verify before implementing."**

> **"Tests are not overhead - they're proof your code works."**

> **"Defensive programming isn't paranoia - it's professionalism."**

---

**Revision History:**
- 2025-11-21: Initial creation based on Week 4 Day 3 lessons learned

**Next Review:** 2025-12-21

---

*This is a living document. Update it as we learn. Share it with the team. Follow it every time.*
