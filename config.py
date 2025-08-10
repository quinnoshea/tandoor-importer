"""
Configuration management for Tandoor Recipe Importer.

Handles loading, parsing, and validation of configuration files.
"""

import sys
import configparser
from typing import Tuple
from pathlib import Path

from exceptions import ConfigurationError


def load_config() -> Tuple[str, str, int]:
    """Load configuration from config.conf file with comprehensive error handling."""
    config = configparser.ConfigParser()
    config_path = Path(__file__).parent / 'config.conf'

    try:
        if not config_path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {config_path}\n"
                "Please copy config.conf.example to config.conf and configure it."
            )

        if not config_path.is_file():
            raise ConfigurationError(f"Configuration path exists but is not a file: {config_path}")

        # Read configuration with error handling
        try:
            config.read(config_path, encoding='utf-8')
        except (UnicodeDecodeError, configparser.Error) as e:
            raise ConfigurationError(f"Failed to parse configuration file: {e}")

        # Validate required sections exist
        required_sections = {'tandoor', 'import'}
        missing_sections = required_sections - set(config.sections())
        if missing_sections:
            raise ConfigurationError(f"Missing required sections in config: {missing_sections}")

        # Extract and validate configuration values
        try:
            tandoor_url = config.get('tandoor', 'url', fallback='').strip().rstrip('/')
            api_token = config.get('tandoor', 'api_token', fallback='').strip()
            delay = config.getint('import', 'delay_between_requests', fallback=30)
        except (ValueError, configparser.NoOptionError) as e:
            raise ConfigurationError(f"Invalid configuration value: {e}")

        # Validate configuration values
        if not tandoor_url or tandoor_url == 'https://your-tandoor-instance.com':
            raise ConfigurationError(
                "Please configure your Tandoor URL in config.conf\n"
                "Set 'url' under [tandoor] section to your Tandoor instance URL."
            )

        if not api_token or api_token == 'your_api_token_here':  # nosec B105
            raise ConfigurationError(
                "Please configure your API token in config.conf\n"
                "Set 'api_token' under [tandoor] section to your Tandoor API token."
            )

        if delay < 1 or delay > 3600:
            raise ConfigurationError(f"Invalid delay value: {delay}. Must be between 1 and 3600 seconds.")

        # Validate URL format
        if not tandoor_url.startswith(('http://', 'https://')):
            raise ConfigurationError(
                f"Invalid Tandoor URL format: {tandoor_url}. "
                "Must start with http:// or https://"
            )

        return tandoor_url, api_token, delay

    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(f"Unexpected error loading configuration: {e}") from e