# Testing Tools

This module contains strategy testing and validation tools for the OKX trading system.

## Files

- **`strategy_tester.py`**: Comprehensive testing framework for strategy components
- **`__init__.py`**: Module initialization and exports

## Usage

### Run all tests:

```bash
python src/testing/strategy_tester.py
```

### Import and use:

```python
from src.testing import test_strategy_optimizer
test_strategy_optimizer()
```

## Test Coverage

### Data Loading Tests

- Historical data loading validation
- Data type conversion verification
- File format compatibility checks

### Strategy Optimizer Tests

- Parameter configuration validation
- Optimization algorithm testing
- Result generation verification

## Features

- **Comprehensive Testing**: Covers all major strategy components
- **Error Handling**: Detailed error reporting and debugging
- **Performance Validation**: Ensures strategy optimizer works correctly
- **Modular Design**: Easy to extend with additional test cases

## Running Tests

Tests can be run individually or as a complete suite:

```python
# Run specific test
test_data_loading()

# Run all tests
run_all_tests()
```
