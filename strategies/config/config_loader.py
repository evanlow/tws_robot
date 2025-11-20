"""
Configuration loader for trading strategies.

Loads and validates YAML configuration files for strategy parameters,
risk limits, and other settings.
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from ..base_strategy import StrategyConfig


logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Load and manage strategy configurations from YAML files.
    
    Features:
    - Load YAML configuration files
    - Validate configuration structure
    - Convert to StrategyConfig objects
    - Support for environment-specific overrides
    - Configuration caching
    
    Example:
        >>> loader = ConfigLoader("strategies/config")
        >>> config = loader.load_config("bollinger_bands.yaml")
        >>> print(config.name, config.parameters)
    """
    
    def __init__(self, config_dir: str = "strategies/config"):
        """
        Initialize configuration loader.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self._config_cache: Dict[str, Dict[str, Any]] = {}
        self._file_timestamps: Dict[str, float] = {}
        
        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ConfigLoader initialized with directory: {self.config_dir}")
    
    def load_config(self, filename: str, force_reload: bool = False) -> StrategyConfig:
        """
        Load configuration from YAML file.
        
        Args:
            filename: Name of configuration file (e.g., "bollinger_bands.yaml")
            force_reload: Force reload even if cached
            
        Returns:
            StrategyConfig object
            
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid
        """
        filepath = self.config_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Configuration file not found: {filepath}")
        
        # Check if we need to reload
        file_mtime = filepath.stat().st_mtime
        cache_key = str(filepath)
        
        if not force_reload and cache_key in self._config_cache:
            if cache_key in self._file_timestamps:
                if self._file_timestamps[cache_key] == file_mtime:
                    logger.debug(f"Using cached config: {filename}")
                    return self._parse_config(self._config_cache[cache_key], filename)
        
        # Load YAML file
        logger.info(f"Loading configuration: {filename}")
        with open(filepath, 'r') as f:
            config_data = yaml.safe_load(f)
        
        if not config_data:
            raise ValueError(f"Empty configuration file: {filename}")
        
        # Cache the config
        self._config_cache[cache_key] = config_data
        self._file_timestamps[cache_key] = file_mtime
        
        return self._parse_config(config_data, filename)
    
    def load_all_configs(self) -> List[StrategyConfig]:
        """
        Load all YAML configuration files in the config directory.
        
        Returns:
            List of StrategyConfig objects
        """
        configs = []
        
        for filepath in self.config_dir.glob("*.yaml"):
            try:
                config = self.load_config(filepath.name)
                configs.append(config)
            except Exception as e:
                logger.error(f"Failed to load {filepath.name}: {e}")
        
        logger.info(f"Loaded {len(configs)} configurations")
        return configs
    
    def _parse_config(self, config_data: Dict[str, Any], filename: str) -> StrategyConfig:
        """
        Parse raw configuration data into StrategyConfig.
        
        Args:
            config_data: Raw configuration dictionary
            filename: Configuration filename (for error messages)
            
        Returns:
            StrategyConfig object
            
        Raises:
            ValueError: If configuration structure is invalid
        """
        # Validate required fields
        if 'name' not in config_data:
            raise ValueError(f"Missing 'name' field in {filename}")
        
        if 'symbols' not in config_data:
            raise ValueError(f"Missing 'symbols' field in {filename}")
        
        # Extract configuration
        name = config_data['name']
        symbols = config_data['symbols']
        
        # Validate symbols is a list
        if not isinstance(symbols, list):
            symbols = [symbols]
        
        # Optional fields with defaults
        enabled = config_data.get('enabled', True)
        parameters = config_data.get('parameters', {})
        risk_limits = config_data.get('risk_limits', {})
        
        # Create StrategyConfig
        config = StrategyConfig(
            name=name,
            symbols=symbols,
            enabled=enabled,
            parameters=parameters,
            risk_limits=risk_limits
        )
        
        # Validate the config
        if not config.validate():
            raise ValueError(f"Invalid configuration in {filename}")
        
        logger.debug(f"Parsed config: {name} for symbols {symbols}")
        return config
    
    def save_config(self, config: StrategyConfig, filename: str):
        """
        Save configuration to YAML file.
        
        Args:
            config: StrategyConfig to save
            filename: Target filename (e.g., "bollinger_bands.yaml")
        """
        filepath = self.config_dir / filename
        
        # Convert to dictionary
        config_data = {
            'name': config.name,
            'symbols': config.symbols,
            'enabled': config.enabled,
            'parameters': config.parameters,
            'risk_limits': config.risk_limits
        }
        
        # Write to file
        with open(filepath, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
        
        # Update cache
        cache_key = str(filepath)
        self._config_cache[cache_key] = config_data
        self._file_timestamps[cache_key] = filepath.stat().st_mtime
        
        logger.info(f"Saved configuration: {filename}")
    
    def reload_config(self, filename: str) -> StrategyConfig:
        """
        Force reload configuration from file.
        
        Args:
            filename: Configuration filename
            
        Returns:
            Reloaded StrategyConfig
        """
        return self.load_config(filename, force_reload=True)
    
    def is_config_modified(self, filename: str) -> bool:
        """
        Check if configuration file has been modified since last load.
        
        Args:
            filename: Configuration filename
            
        Returns:
            True if file has been modified
        """
        filepath = self.config_dir / filename
        cache_key = str(filepath)
        
        if not filepath.exists():
            return False
        
        if cache_key not in self._file_timestamps:
            return True
        
        current_mtime = filepath.stat().st_mtime
        cached_mtime = self._file_timestamps[cache_key]
        
        return current_mtime != cached_mtime
    
    def clear_cache(self):
        """Clear the configuration cache"""
        self._config_cache.clear()
        self._file_timestamps.clear()
        logger.info("Configuration cache cleared")
    
    def get_config_files(self) -> List[str]:
        """
        Get list of all configuration files in the directory.
        
        Returns:
            List of configuration filenames
        """
        return [f.name for f in self.config_dir.glob("*.yaml")]
    
    def validate_config_file(self, filename: str) -> tuple[bool, Optional[str]]:
        """
        Validate a configuration file without loading it.
        
        Args:
            filename: Configuration filename
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.load_config(filename, force_reload=True)
            return True, None
        except Exception as e:
            return False, str(e)


class ConfigValidator:
    """
    Validate strategy configuration against schemas.
    
    Provides validation rules for different configuration fields
    including parameters, risk limits, and symbol lists.
    """
    
    # Parameter type schemas
    PARAMETER_SCHEMAS = {
        'period': {'type': int, 'min': 1, 'max': 500},
        'std_dev': {'type': (int, float), 'min': 0.1, 'max': 10.0},
        'rsi_period': {'type': int, 'min': 2, 'max': 100},
        'rsi_oversold': {'type': (int, float), 'min': 0, 'max': 100},
        'rsi_overbought': {'type': (int, float), 'min': 0, 'max': 100},
        'sma_fast': {'type': int, 'min': 1, 'max': 200},
        'sma_slow': {'type': int, 'min': 1, 'max': 500},
        'atr_period': {'type': int, 'min': 1, 'max': 100},
        'atr_multiplier': {'type': (int, float), 'min': 0.1, 'max': 10.0},
    }
    
    # Risk limit schemas
    RISK_LIMIT_SCHEMAS = {
        'max_position_size': {'type': int, 'min': 1},
        'max_daily_loss': {'type': (int, float), 'min': 0},
        'max_trades_per_day': {'type': int, 'min': 1},
        'position_sizing': {'type': str, 'allowed': ['fixed', 'percent', 'risk_based']},
        'max_portfolio_allocation': {'type': (int, float), 'min': 0, 'max': 100},
    }
    
    @classmethod
    def validate_parameters(cls, parameters: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate strategy parameters.
        
        Args:
            parameters: Dictionary of parameters to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        for param_name, param_value in parameters.items():
            if param_name not in cls.PARAMETER_SCHEMAS:
                logger.warning(f"Unknown parameter: {param_name}")
                continue
            
            schema = cls.PARAMETER_SCHEMAS[param_name]
            
            # Check type
            expected_type = schema['type']
            if not isinstance(param_value, expected_type):
                errors.append(f"Parameter '{param_name}' must be {expected_type}, got {type(param_value)}")
                continue
            
            # Check min/max
            if 'min' in schema and param_value < schema['min']:
                errors.append(f"Parameter '{param_name}' must be >= {schema['min']}")
            
            if 'max' in schema and param_value > schema['max']:
                errors.append(f"Parameter '{param_name}' must be <= {schema['max']}")
        
        return len(errors) == 0, errors
    
    @classmethod
    def validate_risk_limits(cls, risk_limits: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate risk limits.
        
        Args:
            risk_limits: Dictionary of risk limits to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        for limit_name, limit_value in risk_limits.items():
            if limit_name not in cls.RISK_LIMIT_SCHEMAS:
                logger.warning(f"Unknown risk limit: {limit_name}")
                continue
            
            schema = cls.RISK_LIMIT_SCHEMAS[limit_name]
            
            # Check type
            expected_type = schema['type']
            if not isinstance(limit_value, expected_type):
                errors.append(f"Risk limit '{limit_name}' must be {expected_type}, got {type(limit_value)}")
                continue
            
            # Check allowed values
            if 'allowed' in schema and limit_value not in schema['allowed']:
                errors.append(f"Risk limit '{limit_name}' must be one of {schema['allowed']}")
            
            # Check min/max
            if 'min' in schema and limit_value < schema['min']:
                errors.append(f"Risk limit '{limit_name}' must be >= {schema['min']}")
            
            if 'max' in schema and limit_value > schema['max']:
                errors.append(f"Risk limit '{limit_name}' must be <= {schema['max']}")
        
        return len(errors) == 0, errors
    
    @classmethod
    def validate_config(cls, config: StrategyConfig) -> tuple[bool, List[str]]:
        """
        Validate complete configuration.
        
        Args:
            config: StrategyConfig to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        all_errors = []
        
        # Validate basic structure
        if not config.validate():
            all_errors.append("Basic configuration validation failed")
        
        # Validate parameters
        params_valid, param_errors = cls.validate_parameters(config.parameters)
        all_errors.extend(param_errors)
        
        # Validate risk limits
        limits_valid, limit_errors = cls.validate_risk_limits(config.risk_limits)
        all_errors.extend(limit_errors)
        
        # Validate symbols
        if not config.symbols:
            all_errors.append("At least one symbol is required")
        
        for symbol in config.symbols:
            if not isinstance(symbol, str) or not symbol:
                all_errors.append(f"Invalid symbol: {symbol}")
        
        return len(all_errors) == 0, all_errors
