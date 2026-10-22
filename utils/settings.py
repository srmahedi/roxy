"""
Settings manager for saving/loading user preferences
"""
import json
import os
from typing import Dict, Any
from utils.constants import APP_NAME


class SettingsManager:
    """Manages saving and loading of user settings to disk."""

    def __init__(self):
        # Use app data directory for settings
        app_data_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", APP_NAME.replace(" ", "_"))
        if not os.path.exists(app_data_dir):
            try:
                os.makedirs(app_data_dir, exist_ok=True)
            except:
                # Fallback to user home directory
                app_data_dir = os.path.expanduser("~")

        self.settings_file = os.path.join(app_data_dir, "settings.json")

        # Default settings
        self.defaults = {
            'default_download_path': '',
            'max_concurrent_downloads': 3
        }

    def save_setting(self, key: str, value: Any) -> bool:
        """Save a single setting to file."""
        try:
            settings = self.load_all_settings()
            settings[key] = value

            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving setting: {e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a single setting value."""
        settings = self.load_all_settings()
        return settings.get(key, default or self.defaults.get(key))

    def load_all_settings(self) -> Dict[str, Any]:
        """Load all settings from file."""
        if not os.path.exists(self.settings_file):
            return self.defaults.copy()

        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Merge with defaults to ensure all keys exist
            merged = self.defaults.copy()
            merged.update(data)
            return merged
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self.defaults.copy()

    def clear_settings(self) -> bool:
        """Clear all settings (reset to defaults)."""
        try:
            if os.path.exists(self.settings_file):
                os.remove(self.settings_file)
            return True
        except Exception as e:
            print(f"Error clearing settings: {e}")
            return False
