"""
Persistence manager for saving and loading download state
"""
import json
import os
from typing import List, Dict, Any
from utils.constants import APP_NAME


class PersistenceManager:
    """Manages saving and loading of download state to disk."""
    
    def __init__(self):
        # Use app data directory for persistence
        app_data_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", APP_NAME.replace(" ", "_"))
        if not os.path.exists(app_data_dir):
            try:
                os.makedirs(app_data_dir, exist_ok=True)
            except:
                # Fallback to user home directory
                app_data_dir = os.path.expanduser("~")
        
        self.state_file = os.path.join(app_data_dir, "downloads_state.json")
    
    def save_downloads(self, downloads_data: List[Dict[str, Any]]) -> bool:
        """Save download state to file."""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(downloads_data, f, indent=2, ensure_ascii=False)
            print(f"Saved {len(downloads_data)} downloads to {self.state_file}")
            return True
        except Exception as e:
            print(f"Error saving downloads: {e}")
            return False
    
    def load_downloads(self) -> List[Dict[str, Any]]:
        """Load download state from file."""
        if not os.path.exists(self.state_file):
            print(f"No saved state file found at {self.state_file}")
            return []
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"Loaded {len(data)} downloads from {self.state_file}")
            return data
        except Exception as e:
            print(f"Error loading downloads: {e}")
            return []
    
    def clear_state(self) -> bool:
        """Clear saved download state."""
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
                print(f"Cleared saved state from {self.state_file}")
            return True
        except Exception as e:
            print(f"Error clearing state: {e}")
            return False
