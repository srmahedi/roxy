if (typeof window === 'undefined') {
    var window = self;
}

window.browser = (function ()
{
  return window.msBrowser ||
    window.browser ||
    window.chrome;
})();

window.browserName = (function()
{
    if (window.msBrowser)
        return "Edge";
    if (window.browser && typeof InstallTrigger !== 'undefined')
        return "Firefox";
    if (window.navigator.userAgent.toLowerCase().includes('firefox'))
        return "Firefox";
    return "Chrome";
})();

window.chromeVersion = (function()
{
    if (window.browserName === "Chrome")
      return parseInt(/Chrome\/([0-9.]+)/.exec(navigator.userAgent)[1]);
    return 0;
})();

var browser = window.browser;

async function startTimerAlarm(name, delayInMsec, callback) {
    if (delayInMsec >= 30000) {
        await browser.alarms.create(name, { when: (Date.now() + delayInMsec) }, callback);
    } else {
        await browser.alarms.create(name, { when: (Date.now() + delayInMsec) });
    }
}

function manifestV2BlockingArray(a)
{
    if (browser.runtime.getManifest().manifest_version > 2)
        return a;
    
    a.push("blocking");
    
    return a;
}

// Basic extension utilities
var roxyExtUtils = {
    getHostFromUrl: function (url) {
        return url.toString().replace(/^.*\/\/(www\.)?([^\/?#:]+).*$/, '$2').toLowerCase();
    },
    
    normalizeRedirectURL: function (urlRedirect, url) {
        if (urlRedirect.indexOf('//') === 0 && urlRedirect.indexOf('.') > 0){
            var protocolPos = url.indexOf('//');
            return url.substring(0, protocolPos) + urlRedirect;
        }

        if (urlRedirect.lastIndexOf('.') > 0)
        {
            var protocolPos = url.indexOf('//');
            return url.substring(0, protocolPos + 2) + urlRedirect;
        }

        var redirectRequest = urlRedirect.indexOf('?');

        if (redirectRequest === 0){
            var urlQuery = url.indexOf('?');
            if (urlQuery >= 0)
                return url.substring(0, urlQuery) + urlRedirect;
            else
                return url + urlRedirect;
        }

        var lastDot = url.lastIndexOf('.');

        var baseUrl = url;
        var firstSlash = url.indexOf('/', lastDot);
        if (firstSlash >= 0)
            baseUrl = url.substring(0, firstSlash);

        var firstRequestSlash = urlRedirect.indexOf('/');

        if (firstRequestSlash === 0)
            return baseUrl + urlRedirect;
        else
            return baseUrl + '/' + urlRedirect;
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
    },
    
    addUrlToSkipServers: function (skipServers, url) {
        if (roxyExtUtils.urlInSkipServers(skipServers, url)) {
            return skipServers;
        }
        var host = roxyExtUtils.getHostFromUrl(url);
        skipServers.push(host);
        return skipServers;
    },
    
    removeUrlFromSkipServers: function (skipServers, url) {
        if (typeof skipServers === 'object' && typeof skipServers.forEach === "function") {
            var host = roxyExtUtils.getHostFromUrl(url);
            for (var i = skipServers.length - 1; i >= 0; i--) {
                var hostToSkip = skipServers[i];
                var domainWithSubdomains = new RegExp('^(?:[\\w\\d\\.]*\\.)?' + hostToSkip + '$', 'i');
                if (domainWithSubdomains.test(host)) {
                    skipServers.splice(i,1);
                }
            }
        }
        return skipServers;
    }
};