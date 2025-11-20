"""
Unit tests for configuration system.

Tests ConfigLoader, ConfigValidator, ConfigWatcher, and ConfigManager.
"""

import pytest
import yaml
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from strategies.config import (
    ConfigLoader, ConfigValidator, ConfigWatcher, ConfigManager
)
from strategies.base_strategy import StrategyConfig


# Fixtures

@pytest.fixture
def temp_config_dir():
    """Create temporary config directory"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_config_data():
    """Sample configuration data"""
    return {
        'name': 'TestStrategy',
        'symbols': ['AAPL', 'MSFT'],
        'enabled': True,
        'parameters': {
            'period': 20,
            'std_dev': 2.0,
            'rsi_period': 14
        },
        'risk_limits': {
            'max_position_size': 1000,
            'max_daily_loss': 500.0,
            'position_sizing': 'fixed'
        }
    }


@pytest.fixture
def config_loader(temp_config_dir):
    """Create ConfigLoader instance"""
    return ConfigLoader(temp_config_dir)


@pytest.fixture
def create_config_file(temp_config_dir, sample_config_data):
    """Helper to create config files"""
    def _create_file(filename: str, data: dict = None):
        if data is None:
            data = sample_config_data
        
        filepath = Path(temp_config_dir) / filename
        with open(filepath, 'w') as f:
            yaml.dump(data, f)
        return filepath
    
    return _create_file


# Test ConfigLoader

def test_config_loader_initialization(temp_config_dir):
    """Test ConfigLoader initialization"""
    loader = ConfigLoader(temp_config_dir)
    
    assert loader.config_dir == Path(temp_config_dir)
    assert Path(temp_config_dir).exists()


def test_load_config_file_not_found(config_loader):
    """Test loading non-existent config file"""
    with pytest.raises(FileNotFoundError):
        config_loader.load_config("nonexistent.yaml")


def test_load_config_success(config_loader, create_config_file):
    """Test successful config loading"""
    create_config_file("test.yaml")
    
    config = config_loader.load_config("test.yaml")
    
    assert isinstance(config, StrategyConfig)
    assert config.name == "TestStrategy"
    assert config.symbols == ['AAPL', 'MSFT']
    assert config.enabled is True
    assert config.parameters['period'] == 20


def test_load_config_caching(config_loader, create_config_file):
    """Test configuration caching"""
    create_config_file("test.yaml")
    
    # Load twice
    config1 = config_loader.load_config("test.yaml")
    config2 = config_loader.load_config("test.yaml")
    
    # Should return same data (from cache)
    assert config1.name == config2.name
    assert config1.symbols == config2.symbols


def test_load_config_force_reload(config_loader, create_config_file, temp_config_dir):
    """Test force reload of configuration"""
    filepath = create_config_file("test.yaml")
    
    # Load initial config
    config1 = config_loader.load_config("test.yaml")
    assert config1.name == "TestStrategy"
    
    # Modify the file
    time.sleep(0.1)  # Ensure different mtime
    with open(filepath, 'w') as f:
        yaml.dump({'name': 'ModifiedStrategy', 'symbols': ['AAPL']}, f)
    
    # Force reload
    config2 = config_loader.load_config("test.yaml", force_reload=True)
    assert config2.name == "ModifiedStrategy"


def test_load_config_missing_name(config_loader, create_config_file):
    """Test config validation - missing name"""
    create_config_file("invalid.yaml", {'symbols': ['AAPL']})
    
    with pytest.raises(ValueError, match="Missing 'name'"):
        config_loader.load_config("invalid.yaml")


def test_load_config_missing_symbols(config_loader, create_config_file):
    """Test config validation - missing symbols"""
    create_config_file("invalid.yaml", {'name': 'Test'})
    
    with pytest.raises(ValueError, match="Missing 'symbols'"):
        config_loader.load_config("invalid.yaml")


def test_load_config_empty_file(config_loader, temp_config_dir):
    """Test loading empty config file"""
    filepath = Path(temp_config_dir) / "empty.yaml"
    filepath.touch()
    
    with pytest.raises(ValueError, match="Empty configuration"):
        config_loader.load_config("empty.yaml")


def test_load_all_configs(config_loader, create_config_file):
    """Test loading all config files"""
    create_config_file("config1.yaml", {'name': 'Strategy1', 'symbols': ['AAPL']})
    create_config_file("config2.yaml", {'name': 'Strategy2', 'symbols': ['MSFT']})
    
    configs = config_loader.load_all_configs()
    
    assert len(configs) == 2
    names = [c.name for c in configs]
    assert 'Strategy1' in names
    assert 'Strategy2' in names


def test_save_config(config_loader, temp_config_dir):
    """Test saving configuration"""
    config = StrategyConfig(
        name="SaveTest",
        symbols=["AAPL"],
        parameters={'period': 30}
    )
    
    config_loader.save_config(config, "saved.yaml")
    
    # Verify file was created
    filepath = Path(temp_config_dir) / "saved.yaml"
    assert filepath.exists()
    
    # Load and verify
    loaded_config = config_loader.load_config("saved.yaml")
    assert loaded_config.name == "SaveTest"
    assert loaded_config.parameters['period'] == 30


def test_reload_config(config_loader, create_config_file):
    """Test config reload"""
    filepath = create_config_file("test.yaml")
    
    # Initial load
    config1 = config_loader.load_config("test.yaml")
    
    # Modify file
    time.sleep(0.1)
    with open(filepath, 'w') as f:
        yaml.dump({'name': 'Reloaded', 'symbols': ['AAPL']}, f)
    
    # Reload
    config2 = config_loader.reload_config("test.yaml")
    assert config2.name == "Reloaded"


def test_is_config_modified(config_loader, create_config_file):
    """Test checking if config is modified"""
    filepath = create_config_file("test.yaml")
    
    # Load config
    config_loader.load_config("test.yaml")
    
    # Not modified yet
    assert not config_loader.is_config_modified("test.yaml")
    
    # Modify file
    time.sleep(0.1)
    filepath.touch()
    
    # Now modified
    assert config_loader.is_config_modified("test.yaml")


def test_clear_cache(config_loader, create_config_file):
    """Test clearing config cache"""
    create_config_file("test.yaml")
    
    # Load to populate cache
    config_loader.load_config("test.yaml")
    assert len(config_loader._config_cache) > 0
    
    # Clear cache
    config_loader.clear_cache()
    assert len(config_loader._config_cache) == 0


def test_get_config_files(config_loader, create_config_file):
    """Test getting list of config files"""
    create_config_file("config1.yaml")
    create_config_file("config2.yaml")
    
    files = config_loader.get_config_files()
    
    assert len(files) == 2
    assert "config1.yaml" in files
    assert "config2.yaml" in files


def test_validate_config_file(config_loader, create_config_file):
    """Test config file validation"""
    # Valid config
    create_config_file("valid.yaml")
    is_valid, error = config_loader.validate_config_file("valid.yaml")
    assert is_valid
    assert error is None
    
    # Invalid config
    create_config_file("invalid.yaml", {'name': 'Test'})  # Missing symbols
    is_valid, error = config_loader.validate_config_file("invalid.yaml")
    assert not is_valid
    assert error is not None


# Test ConfigValidator

def test_validate_parameters_valid():
    """Test parameter validation with valid params"""
    params = {
        'period': 20,
        'std_dev': 2.0,
        'rsi_period': 14
    }
    
    is_valid, errors = ConfigValidator.validate_parameters(params)
    assert is_valid
    assert len(errors) == 0


def test_validate_parameters_invalid_type():
    """Test parameter validation with invalid type"""
    params = {
        'period': "20",  # Should be int
    }
    
    is_valid, errors = ConfigValidator.validate_parameters(params)
    assert not is_valid
    assert len(errors) > 0


def test_validate_parameters_out_of_range():
    """Test parameter validation with out-of-range values"""
    params = {
        'period': -5,  # Below minimum
        'std_dev': 20.0  # Above maximum
    }
    
    is_valid, errors = ConfigValidator.validate_parameters(params)
    assert not is_valid
    assert len(errors) == 2


def test_validate_risk_limits_valid():
    """Test risk limit validation with valid limits"""
    limits = {
        'max_position_size': 1000,
        'max_daily_loss': 500.0,
        'position_sizing': 'fixed'
    }
    
    is_valid, errors = ConfigValidator.validate_risk_limits(limits)
    assert is_valid
    assert len(errors) == 0


def test_validate_risk_limits_invalid():
    """Test risk limit validation with invalid limits"""
    limits = {
        'max_position_size': -100,  # Negative
        'position_sizing': 'invalid'  # Not in allowed values
    }
    
    is_valid, errors = ConfigValidator.validate_risk_limits(limits)
    assert not is_valid
    assert len(errors) > 0


def test_validate_config_complete():
    """Test complete config validation"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"],
        parameters={'period': 20, 'std_dev': 2.0},
        risk_limits={'max_position_size': 1000}
    )
    
    is_valid, errors = ConfigValidator.validate_config(config)
    assert is_valid
    assert len(errors) == 0


def test_validate_config_invalid_symbols():
    """Test config validation with invalid symbols"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=[],  # Empty
        parameters={'period': 20}
    )
    
    is_valid, errors = ConfigValidator.validate_config(config)
    assert not is_valid
    assert any("symbol" in err.lower() for err in errors)


# Test ConfigWatcher

def test_config_watcher_initialization(temp_config_dir):
    """Test ConfigWatcher initialization"""
    watcher = ConfigWatcher(temp_config_dir)
    
    assert watcher.config_dir == Path(temp_config_dir)
    assert not watcher.is_running()


def test_config_watcher_watch_file(temp_config_dir, create_config_file):
    """Test watching a file"""
    filepath = create_config_file("test.yaml")
    watcher = ConfigWatcher(temp_config_dir)
    
    callback_called = []
    
    def callback(filename):
        callback_called.append(filename)
    
    watcher.watch_file("test.yaml", callback)
    
    assert "test.yaml" in watcher.get_watched_files()


def test_config_watcher_detect_change(temp_config_dir, create_config_file):
    """Test detecting file changes"""
    filepath = create_config_file("test.yaml")
    watcher = ConfigWatcher(temp_config_dir, poll_interval=0.5)
    
    callback_called = []
    
    def callback(filename):
        callback_called.append(filename)
    
    watcher.watch_file("test.yaml", callback)
    watcher.start()
    
    try:
        # Modify file
        time.sleep(0.6)
        filepath.touch()
        
        # Wait for detection
        time.sleep(0.8)
        
        # Callback should have been called
        assert len(callback_called) > 0
        assert callback_called[0] == "test.yaml"
    
    finally:
        watcher.stop()


def test_config_watcher_unwatch_file(temp_config_dir, create_config_file):
    """Test unwatching a file"""
    create_config_file("test.yaml")
    watcher = ConfigWatcher(temp_config_dir)
    
    def callback(filename):
        pass
    
    watcher.watch_file("test.yaml", callback)
    assert "test.yaml" in watcher.get_watched_files()
    
    watcher.unwatch_file("test.yaml")
    assert "test.yaml" not in watcher.get_watched_files()


def test_config_watcher_start_stop(temp_config_dir):
    """Test starting and stopping watcher"""
    watcher = ConfigWatcher(temp_config_dir)
    
    assert not watcher.is_running()
    
    watcher.start()
    assert watcher.is_running()
    
    watcher.stop()
    assert not watcher.is_running()


def test_config_watcher_context_manager(temp_config_dir):
    """Test using watcher as context manager"""
    with ConfigWatcher(temp_config_dir) as watcher:
        assert watcher.is_running()
    
    assert not watcher.is_running()


# Test ConfigManager

def test_config_manager_initialization(temp_config_dir):
    """Test ConfigManager initialization"""
    manager = ConfigManager(temp_config_dir)
    
    assert manager.config_dir == temp_config_dir
    assert manager.loader is not None
    assert manager.watcher is not None


def test_config_manager_load_config(temp_config_dir, create_config_file):
    """Test loading config through manager"""
    create_config_file("test.yaml")
    manager = ConfigManager(temp_config_dir)
    
    config = manager.load_config("test.yaml")
    
    assert config.name == "TestStrategy"
    assert config.symbols == ['AAPL', 'MSFT']


def test_config_manager_hot_reload(temp_config_dir, create_config_file):
    """Test hot-reload functionality"""
    filepath = create_config_file("test.yaml")
    manager = ConfigManager(temp_config_dir, poll_interval=0.5)
    
    callback_called = []
    
    def on_reload(config):
        callback_called.append(config.name)
    
    manager.enable_hot_reload("test.yaml", on_reload)
    manager.start_watching()
    
    try:
        # Modify file
        time.sleep(0.6)
        with open(filepath, 'w') as f:
            yaml.dump({'name': 'HotReloaded', 'symbols': ['AAPL']}, f)
        
        # Wait for reload
        time.sleep(0.8)
        
        # Callback should have been called
        assert len(callback_called) > 0
        assert callback_called[0] == "HotReloaded"
    
    finally:
        manager.stop_watching()


def test_config_manager_disable_hot_reload(temp_config_dir, create_config_file):
    """Test disabling hot-reload"""
    create_config_file("test.yaml")
    manager = ConfigManager(temp_config_dir)
    
    def on_reload(config):
        pass
    
    manager.enable_hot_reload("test.yaml", on_reload)
    assert "test.yaml" in manager.watcher.get_watched_files()
    
    manager.disable_hot_reload("test.yaml")
    assert "test.yaml" not in manager.watcher.get_watched_files()


def test_config_manager_context_manager(temp_config_dir):
    """Test using manager as context manager"""
    with ConfigManager(temp_config_dir) as manager:
        assert manager.is_watching()
    
    assert not manager.is_watching()


# Integration test with real config files

def test_load_bollinger_bands_config():
    """Test loading actual bollinger_bands.yaml config"""
    loader = ConfigLoader("strategies/config")
    
    try:
        config = loader.load_config("bollinger_bands.yaml")
        
        assert config.name == "BollingerBands_AAPL"
        assert "AAPL" in config.symbols
        assert config.parameters['period'] == 20
        assert config.parameters['std_dev'] == 2.0
        assert config.risk_limits['max_position_size'] == 1000
    
    except FileNotFoundError:
        pytest.skip("bollinger_bands.yaml not found")


def test_load_mean_reversion_config():
    """Test loading actual mean_reversion.yaml config"""
    loader = ConfigLoader("strategies/config")
    
    try:
        config = loader.load_config("mean_reversion.yaml")
        
        assert config.name == "MeanReversion_Tech"
        assert len(config.symbols) == 4
        assert "AAPL" in config.symbols
        assert config.parameters['sma_fast'] == 10
        assert config.parameters['sma_slow'] == 50
    
    except FileNotFoundError:
        pytest.skip("mean_reversion.yaml not found")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
