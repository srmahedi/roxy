// Roxy Download Manager Settings Page

function RoxySettings(){
    this.settings = {};
    this.skipHosts = [];
    this.activeTabInSkipList = false;
    this.pauseCatchingForAllSites = false;
}

RoxySettings.prototype.initialize = function () {
    window.browser.runtime.sendMessage({type: "get_settings_for_page"}, this.onGotSettings.bind(this));
    window.browser.runtime.sendMessage({type: "get_pause_on_all_sites_flag"}, this.onGotPauseOnAllSites.bind(this));
    this.addEventListeners();
};

RoxySettings.prototype.onGotSettings = function (settings) {
    this.settings = settings;
    this.skipServersEnabled = this.settings.browser.monitor.skipServersEnabled === "1";
    this.skipHosts = roxyExtUtils.skipServers2array(this.settings.browser.monitor.skipServers);
    this.checkCurrentUrlInSkipList();
    this.populateForm();
};

RoxySettings.prototype.onGotPauseOnAllSites = function (paused_on_all_sites) {
    this.pauseCatchingForAllSites = paused_on_all_sites;
    this.populateForm();
};

RoxySettings.prototype.addEventListeners = function () {
    document.getElementById('pauseCatchingForAllSites').addEventListener('change', this.onPauseCatchingChange.bind(this));
    document.getElementById('allowBrowserDownload').addEventListener('change', this.onAllowBrowserDownloadChange.bind(this));
    document.getElementById('skipSmallerThan').addEventListener('change', this.onSkipSmallerThanChange.bind(this));
    document.getElementById('skipExtensions').addEventListener('change', this.onSkipExtensionsChange.bind(this));
    document.getElementById('catchExtensions').addEventListener('change', this.onCatchExtensionsChange.bind(this));
    document.getElementById('activeTabInSkipList').addEventListener('change', this.onActiveTabInSkipListChange.bind(this));
    
    // Context menu options
    document.getElementById('menuDlThis').addEventListener('change', this.onMenuDlThisChange.bind(this));
    document.getElementById('menuDlAll').addEventListener('change', this.onMenuDlAllChange.bind(this));
    document.getElementById('menuDlSelected').addEventListener('change', this.onMenuDlSelectedChange.bind(this));
    document.getElementById('menuDlPage').addEventListener('change', this.onMenuDlPageChange.bind(this));
    document.getElementById('menuDlVideo').addEventListener('change', this.onMenuDlVideoChange.bind(this));
    
    // Action buttons
    document.getElementById('saveSettings').addEventListener('click', this.onSaveSettings.bind(this));
    document.getElementById('resetSettings').addEventListener('click', this.onResetSettings.bind(this));
};

RoxySettings.prototype.populateForm = function () {
    document.getElementById('roxy_loading').style.display = "none";
    document.getElementById('roxy_settings').style.display = "block";
    
    // Download monitoring settings
    document.getElementById('pauseCatchingForAllSites').checked = this.pauseCatchingForAllSites;
    document.getElementById('allowBrowserDownload').checked = this.settings.browser.monitor.allowDownload != "0";
    document.getElementById('skipSmallerThan').value = this.settings.browser.monitor.skipSmallerThan || "1024";
    document.getElementById('skipExtensions').value = this.settings.browser.monitor.skipExtensions || "";
    document.getElementById('catchExtensions').value = this.settings.browser.monitor.catchExtensions || "";
    
    // Current site settings
    document.getElementById('activeTabInSkipList').checked = this.activeTabInSkipList;
    
    // Context menu settings
    document.getElementById('menuDlThis').checked = this.settings.browser.menu.dllink != "0";
    document.getElementById('menuDlAll').checked = this.settings.browser.menu.dlall != "0";
    document.getElementById('menuDlSelected').checked = this.settings.browser.menu.dlselected != "0";
    document.getElementById('menuDlPage').checked = this.settings.browser.menu.dlpage != "0";
    document.getElementById('menuDlVideo').checked = this.settings.browser.menu.dlvideo != "0";
};

RoxySettings.prototype.onPauseCatchingChange = function () {
    this.pauseCatchingForAllSites = document.getElementById('pauseCatchingForAllSites').checked;
    window.browser.runtime.sendMessage({type: "set_pause_on_all_sites_flag", pause: this.pauseCatchingForAllSites});
};

RoxySettings.prototype.onAllowBrowserDownloadChange = function () {
    this.settings.browser.monitor.allowDownload = document.getElementById('allowBrowserDownload').checked ? "1" : "0";
};

RoxySettings.prototype.onSkipSmallerThanChange = function () {
    this.settings.browser.monitor.skipSmallerThan = document.getElementById('skipSmallerThan').value;
};

RoxySettings.prototype.onSkipExtensionsChange = function () {
    this.settings.browser.monitor.skipExtensions = document.getElementById('skipExtensions').value;
};

RoxySettings.prototype.onCatchExtensionsChange = function () {
    this.settings.browser.monitor.catchExtensions = document.getElementById('catchExtensions').value;
};

RoxySettings.prototype.onActiveTabInSkipListChange = function () {
    this.activeTabInSkipList = document.getElementById('activeTabInSkipList').checked;
    window.browser.runtime.sendMessage({type: "change_active_tab_in_skip_list", checked: this.activeTabInSkipList});
};

RoxySettings.prototype.onMenuDlThisChange = function () {
    this.settings.browser.menu.dllink = document.getElementById('menuDlThis').checked ? "1" : "0";
};

RoxySettings.prototype.onMenuDlAllChange = function () {
    this.settings.browser.menu.dlall = document.getElementById('menuDlAll').checked ? "1" : "0";
};

RoxySettings.prototype.onMenuDlSelectedChange = function () {
    this.settings.browser.menu.dlselected = document.getElementById('menuDlSelected').checked ? "1" : "0";
};

RoxySettings.prototype.onMenuDlPageChange = function () {
    this.settings.browser.menu.dlpage = document.getElementById('menuDlPage').checked ? "1" : "0";
};

RoxySettings.prototype.onMenuDlVideoChange = function () {
    this.settings.browser.menu.dlvideo = document.getElementById('menuDlVideo').checked ? "1" : "0";
};

RoxySettings.prototype.onSaveSettings = function () {
    // Send updated settings to background
    window.browser.runtime.sendMessage({
        type: "save_settings",
        settings: this.settings
    }, function(response) {
        if (response && response.success) {
            alert('Settings saved successfully!');
        } else {
            alert('Failed to save settings');
        }
    });
};

RoxySettings.prototype.onResetSettings = function () {
    if (confirm('Are you sure you want to reset all settings to defaults?')) {
        this.settings = {
            browser: {
                menu: {
                    dllink: "1",
                    dlall: "1",
                    dlselected: "1",
                    dlpage: "1",
                    dlvideo: "1",
                    dlYtChannel: "0",
                    dlYtPlaylist: "0"
                },
                monitor: {
                    enable: "1",
                    allowDownload: "1",
                    skipSmallerThan: "1024",
                    skipExtensions: "",
                    skipServers: "",
                    skipServersEnabled: "0",
                    catchExtensions: "",
                    skipIfKeyPressed: "0"
                }
            }
        };
        this.populateForm();
        this.onSaveSettings();
    }
};

RoxySettings.prototype.checkCurrentUrlInSkipList = function () {
    window.browser.tabs.query({ active: true, currentWindow: true }, function(tabs) {
        if (this.skipServersEnabled && tabs.length) {
            this.activeTabInSkipList = roxyExtUtils.urlInSkipServers(this.skipHosts, tabs[0].url);
        } else {
            this.activeTabInSkipList = false;
        }
        this.populateForm();
    }.bind(this));
};

// Extension utilities (if not already loaded)
if (typeof roxyExtUtils === "undefined") {
    var roxyExtUtils = {
        getHostFromUrl: function (url) {
            return url.toString().replace(/^.*\/\/(www\.)?([^\/?#:]+).*$/, '$2').toLowerCase();
        },
        
        skipServers2array: function (skipServers) {
            if (typeof skipServers === 'string') {
                return skipServers.trim().toLowerCase().split(' ');
            }
            return [];
        },
        
        skipServers2string: function (skipServers) {
            if (typeof skipServers === 'object') {
                return skipServers.join(" ");
            }
            return "";
        },
        
        urlInSkipServers: function (skipServers, url) {
            var skip = false;
            if (typeof skipServers === 'object' && typeof skipServers.forEach === "function") {
                var host = roxyExtUtils.getHostFromUrl(url);
                skipServers.forEach(function (hostToSkip) {
                    var domainWithSubdomains = new RegExp('^(?:[\\w\\d\\.]*\\.)?' + hostToSkip + '$', 'i');
                    if (domainWithSubdomains.test(host)) {
                        skip = true;
                    }
                });
            }
            return skip;
        }
    };
}

// Initialize settings page
var roxysettings = new RoxySettings;
roxysettings.initialize();