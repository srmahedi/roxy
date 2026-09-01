// Get the toggle element
const enableToggle = document.getElementById('enableToggle');
const statusElement = document.getElementById('status');

// Load the current state from storage
chrome.storage.local.get(['extensionEnabled'], (result) => {
  const isEnabled = result.extensionEnabled !== false; // Default to true
  enableToggle.checked = isEnabled;
  updateStatus(isEnabled);
  updateBadge(isEnabled);
});

// Handle toggle changes
enableToggle.addEventListener('change', (event) => {
  const isEnabled = event.target.checked;
  
  // Save the state to storage
  chrome.storage.local.set({ extensionEnabled: isEnabled }, () => {
    updateStatus(isEnabled);
    updateBadge(isEnabled);
  });
});

function updateStatus(isEnabled) {
  if (isEnabled) {
    statusElement.textContent = 'Extension is enabled';
  } else {
    statusElement.textContent = 'Extension is disabled - Chrome will handle downloads';
  }
}

function updateBadge(isEnabled) {
  if (isEnabled) {
    chrome.action.setBadgeText({ text: '' });
    chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });
  } else {
    chrome.action.setBadgeText({ text: 'off' });
    chrome.action.setBadgeBackgroundColor({ color: '#f44336' });
  }
}
