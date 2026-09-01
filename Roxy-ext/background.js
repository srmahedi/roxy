chrome.runtime.onInstalled.addListener(() => {
  console.log("Roxy Download Manager extension installed");
});

// Function to send URL to Python launcher server
async function sendUrlToLauncher(url, filename) {
  try {
    const response = await fetch('http://localhost:12579/api/download', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url: url, filename: filename })
    });

    if (response.ok) {
      console.log('URL sent to Roxy launcher successfully:', url);
      return true;
    } else {
      console.error('Failed to send URL to launcher:', response.status);
      return false;
    }
  } catch (error) {
    console.error('Error sending URL to launcher:', error);
    return false;
  }
}

// Intercept downloads when Chrome's download manager is used
chrome.downloads.onCreated.addListener(async (downloadItem) => {
  console.log('Download created:', downloadItem.url, 'ID:', downloadItem.id);
  
  // Only intercept actual file downloads (not chrome extensions, etc.)
  if (!downloadItem.url.startsWith('http://') && !downloadItem.url.startsWith('https://')) {
    console.log('Skipping non-HTTP download');
    return;
  }
  
  // Only intercept if not already cancelled
  if (downloadItem.state === 'cancelled') {
    console.log('Download already cancelled, skipping');
    return;
  }
  
  // Wait for Chrome to determine the filename
  // The filename might not be available immediately on onCreated
  await new Promise(resolve => setTimeout(resolve, 500));
  
  // Try to get the actual filename from the download item
  let filename = 'download';
  try {
    const updatedItem = await chrome.downloads.search({id: downloadItem.id});
    if (updatedItem && updatedItem.length > 0) {
      const item = updatedItem[0];
      if (item.filename) {
        // Extract just the filename from the full path
        filename = item.filename.split(/[/\\]/).pop();
        console.log('Got filename from Chrome:', filename);
      } else if (item.finalUrl) {
        // Try to extract from final URL if filename not available
        filename = item.finalUrl.split('/').pop().split('?')[0] || 'download';
        console.log('Got filename from final URL:', filename);
      }
    }
  } catch (error) {
    console.log('Error getting filename:', error);
    // Fallback to URL-based extraction
    filename = downloadItem.url.split('/').pop().split('?')[0] || 'download';
  }
  
  // If still no proper filename, try to get it from URL
  if (!filename || filename === 'download' || filename.length < 3) {
    filename = downloadItem.url.split('/').pop().split('?')[0] || 'download';
  }
  
  console.log('Final filename to use:', filename);
  
  // Cancel the Chrome download
  try {
    await chrome.downloads.cancel(downloadItem.id);
    console.log('Chrome download cancelled:', downloadItem.id);
  } catch (error) {
    console.log('Download cancel error:', error);
  }
  
  // Wait a moment for Chrome to process the cancellation before removing
  await new Promise(resolve => setTimeout(resolve, 500));
  
  // Remove the canceled download from Chrome's download manager
  try {
    await chrome.downloads.remove(downloadItem.id);
    console.log('Chrome download removed from history:', downloadItem.id);
  } catch (error) {
    console.log('Download removal error:', error);
    // Try alternative approach - erase the download
    try {
      await chrome.downloads.erase({id: downloadItem.id});
      console.log('Chrome download erased using erase():', downloadItem.id);
    } catch (eraseError) {
      console.log('Download erase error:', eraseError);
    }
  }
  
  // Send the URL to the Python launcher server
  const success = await sendUrlToLauncher(downloadItem.url, filename);
  if (!success) {
    console.log('Failed to send URL to launcher, allowing Chrome to handle download');
    // If launcher fails, we could optionally let Chrome continue with the download
    // But for now, we've already cancelled it
  }
});