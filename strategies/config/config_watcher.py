"""
Hot-reload configuration file watcher.

Monitors configuration files for changes and triggers
automatic reload of strategy configurations.
"""

import logging
import time
from threading import Thread, Event
from typing import Dict, Callable, Optional
from pathlib import Path
from datetime import datetime


logger = logging.getLogger(__name__)


class ConfigWatcher:
    """
    Watch configuration files for changes and trigger reload.
    
    Features:
    - Monitor multiple configuration files
    - Trigger callbacks on file changes
    - Configurable polling interval
    - Thread-safe operation
    - Graceful shutdown
    
    Example:
        >>> def on_config_change(filename):
        ...     print(f"Config changed: {filename}")
        ...     # Reload strategy configuration
        >>> 
        >>> watcher = ConfigWatcher("strategies/config")
        >>> watcher.watch_file("bollinger_bands.yaml", on_config_change)
        >>> watcher.start()
        >>> 
        >>> # Later...
        >>> watcher.stop()
    """
    
    def __init__(self, config_dir: str, poll_interval: float = 2.0):
        """
        Initialize configuration watcher.
        
        Args:
            config_dir: Directory containing configuration files
            poll_interval: How often to check for changes (seconds)
        """
        self.config_dir = Path(config_dir)
        self.poll_interval = poll_interval
        
        # File monitoring
        self._watched_files: Dict[str, float] = {}  # filename -> last_mtime
        self._callbacks: Dict[str, list[Callable]] = {}  # filename -> callbacks
        
        # Threading
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._running = False
        
        logger.info(f"ConfigWatcher initialized for {self.config_dir}")
    
    def watch_file(self, filename: str, callback: Callable[[str], None]):
        """
        Add a file to watch and register callback.
        
        Args:
            filename: Configuration filename to watch
            callback: Function to call when file changes (receives filename)
        """
        filepath = self.config_dir / filename
        
        if not filepath.exists():
            logger.warning(f"File does not exist: {filename}")
            return
        
        # Initialize watched file
        if filename not in self._watched_files:
            self._watched_files[filename] = filepath.stat().st_mtime
            self._callbacks[filename] = []
        
        # Add callback
        if callback not in self._callbacks[filename]:
            self._callbacks[filename].append(callback)
            logger.info(f"Watching file: {filename}")
    
    def unwatch_file(self, filename: str, callback: Optional[Callable] = None):
        """
        Remove a file from watch list or remove specific callback.
        
        Args:
            filename: Configuration filename
            callback: Specific callback to remove (if None, removes all)
        """
        if filename not in self._watched_files:
            return
        
        if callback is None:
            # Remove all callbacks for this file
            del self._watched_files[filename]
            del self._callbacks[filename]
            logger.info(f"Stopped watching file: {filename}")
        else:
            # Remove specific callback
            if callback in self._callbacks[filename]:
                self._callbacks[filename].remove(callback)
                
                # Remove file if no callbacks left
                if not self._callbacks[filename]:
                    del self._watched_files[filename]
                    del self._callbacks[filename]
                    logger.info(f"Stopped watching file: {filename}")
    
    def start(self):
        """Start watching for file changes"""
        if self._running:
            logger.warning("ConfigWatcher already running")
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._thread = Thread(target=self._watch_loop, daemon=True, name="ConfigWatcher")
        self._thread.start()
        
        logger.info("ConfigWatcher started")
    
    def stop(self):
        """Stop watching for file changes"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        
        logger.info("ConfigWatcher stopped")
    
    def _watch_loop(self):
        """Main watch loop (runs in separate thread)"""
        logger.debug("ConfigWatcher thread started")
        
        while not self._stop_event.is_set():
            try:
                self._check_files()
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
            
            # Wait for next poll (with early exit on stop)
            self._stop_event.wait(self.poll_interval)
        
        logger.debug("ConfigWatcher thread stopped")
    
    def _check_files(self):
        """Check all watched files for changes"""
        for filename, last_mtime in list(self._watched_files.items()):
            filepath = self.config_dir / filename
            
            # Check if file still exists
            if not filepath.exists():
                logger.warning(f"Watched file disappeared: {filename}")
                continue
            
            # Check if modified
            current_mtime = filepath.stat().st_mtime
            
            if current_mtime != last_mtime:
                logger.info(f"Configuration changed: {filename}")
                
                # Update timestamp
                self._watched_files[filename] = current_mtime
                
                # Trigger callbacks
                self._trigger_callbacks(filename)
    
    def _trigger_callbacks(self, filename: str):
        """
        Trigger all callbacks for a changed file.
        
        Args:
            filename: Name of changed file
        """
        if filename not in self._callbacks:
            return
        
        for callback in self._callbacks[filename]:
            try:
                callback(filename)
            except Exception as e:
                logger.error(f"Error in callback for {filename}: {e}")
    
    def get_watched_files(self) -> list[str]:
        """
        Get list of currently watched files.
        
        Returns:
            List of filenames being watched
        """
        return list(self._watched_files.keys())
    
    def is_running(self) -> bool:
        """Check if watcher is running"""
        return self._running
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()
    
    def __del__(self):
        """Cleanup on deletion"""
        if self._running:
            self.stop()


class ConfigManager:
    """
    High-level configuration manager with hot-reload support.
    
    Combines ConfigLoader and ConfigWatcher to provide automatic
    configuration reloading when files change.
    
    Example:
        >>> from strategies.config import ConfigManager
        >>> 
        >>> manager = ConfigManager("strategies/config")
        >>> 
        >>> # Register reload callback
        >>> def on_reload(config):
        ...     print(f"Config reloaded: {config.name}")
        ...     strategy.reload_config(config)
        >>> 
        >>> manager.enable_hot_reload("bollinger_bands.yaml", on_reload)
        >>> manager.start_watching()
    """
    
    def __init__(self, config_dir: str, poll_interval: float = 2.0):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory containing configuration files
            poll_interval: How often to check for changes (seconds)
        """
        from .config_loader import ConfigLoader
        
        self.config_dir = config_dir
        self.loader = ConfigLoader(config_dir)
        self.watcher = ConfigWatcher(config_dir, poll_interval)
        
        # Track reload callbacks
        self._reload_callbacks: Dict[str, list[Callable]] = {}
        
        logger.info(f"ConfigManager initialized for {config_dir}")
    
    def enable_hot_reload(self, filename: str, callback: Callable):
        """
        Enable hot-reload for a configuration file.
        
        Args:
            filename: Configuration filename
            callback: Function to call when config reloads (receives StrategyConfig)
        """
        # Track callback
        if filename not in self._reload_callbacks:
            self._reload_callbacks[filename] = []
        
        self._reload_callbacks[filename].append(callback)
        
        # Create wrapper that loads config and calls user callback
        def on_file_change(changed_filename):
            try:
                # Reload configuration
                config = self.loader.reload_config(changed_filename)
                
                # Call user callbacks
                if changed_filename in self._reload_callbacks:
                    for cb in self._reload_callbacks[changed_filename]:
                        try:
                            cb(config)
                        except Exception as e:
                            logger.error(f"Error in reload callback: {e}")
            
            except Exception as e:
                logger.error(f"Failed to reload config {changed_filename}: {e}")
        
        # Register with watcher
        self.watcher.watch_file(filename, on_file_change)
        
        logger.info(f"Hot-reload enabled for {filename}")
    
    def disable_hot_reload(self, filename: str):
        """
        Disable hot-reload for a configuration file.
        
        Args:
            filename: Configuration filename
        """
        if filename in self._reload_callbacks:
            del self._reload_callbacks[filename]
        
        self.watcher.unwatch_file(filename)
        
        logger.info(f"Hot-reload disabled for {filename}")
    
    def start_watching(self):
        """Start the configuration watcher"""
        self.watcher.start()
    
    def stop_watching(self):
        """Stop the configuration watcher"""
        self.watcher.stop()
    
    def load_config(self, filename: str):
        """
        Load configuration file.
        
        Args:
            filename: Configuration filename
            
        Returns:
            StrategyConfig object
        """
        return self.loader.load_config(filename)
    
    def load_all_configs(self):
        """Load all configuration files"""
        return self.loader.load_all_configs()
    
    def is_watching(self) -> bool:
        """Check if watcher is active"""
        return self.watcher.is_running()
    
    def __enter__(self):
        """Context manager entry"""
        self.start_watching()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_watching()
