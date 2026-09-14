// Roxy Download Manager Extension - FDM-like Architecture
// Comprehensive background script with advanced download interception

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

// Extension utilities
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

// DownloadInfo class
function DownloadInfo(url, redirectUrl, referrer, postData, documentUrl)
{
    if (url && redirectUrl)
    {
        this.url = redirectUrl;
        this.originalUrl = url;
    }
    else
    {
        this.url = url || "";
        this.originalUrl = this.url;
    }
    
    this.httpReferer = referrer;
    this.httpPostData = postData;
    this.documentUrl = documentUrl;
    this.userAgent = navigator.userAgent;
    this.httpCookies = "";
    this.suggestedName = "";
}

// CookieManager class
function CookieManager()
{

}

CookieManager.prototype.getCookiesForUrl = function(
    url, callback)
{
    var urls = [url];
    try {
        var lower = (url || "").toLowerCase();
        if (lower.includes('google.com') || lower.includes('googleusercontent.com')) {
            if (!urls.includes('https://drive.google.com/'))
                urls.push('https://drive.google.com/');
            if (!urls.includes('https://google.com/'))
                urls.push('https://google.com/');
        }
    } catch (e) {}

    this.getCookiesForUrls(urls, function (results)
    {
        var cookieMap = new Map();
        for (var i = 0; i < results.length; i++) {
            if (!results[i]) continue;
            var parts = results[i].split(';');
            for (var j = 0; j < parts.length; j++) {
                var p = parts[j].trim();
                if (!p) continue;
                var eqIdx = p.indexOf('=');
                if (eqIdx > 0) {
                    var k = p.substring(0, eqIdx).trim();
                    var v = p.substring(eqIdx + 1).trim();
                    if (!cookieMap.has(k)) {
                        cookieMap.set(k, v);
                    }
                }
            }
        }
        var merged = [];
        cookieMap.forEach(function (val, key) {
            merged.push(key + "=" + val + ";");
        });
        callback(merged.join(' '));
    });
}

CookieManager.prototype.getCookiesForUrls = function(
    urls, callback)
{
    var remained = urls.length;
    var result = [];

    for (var i = 0; i < urls.length; ++i)
    {
        let details = { 'url': urls[i] };
        if (!window.chromeVersion || window.chromeVersion >= 110)
          details.partitionKey = {};
        browser.cookies.getAll(
            details,
            function (resultIndex, cookies)
            {
                var cookiesString = "";
                if (cookies)
                {
                    cookiesString = cookies.map(function (cookie) {
                        return cookie.name + "=" + cookie.value + ";";
                    }).join(' ');
                }
                result[resultIndex] = cookiesString;
                if (!--remained)
                    callback(result);
            }.bind(this, i));
    }
}

// RequestsManager class
function RequestsManager ()
{
    this.idsAsStrings = true;
    this.nextReqId = 1;
    this.requestsInProgress = new Map;
    
    this.assignRequestId = function (req)
    {
        req.id = this.nextReqId++;
        if (this.idsAsStrings)
            req.id = req.id.toString();		
    };
    
    this.performRequest = function (req, callback)
    {
        if (!req.id || req.id == "0")
            this.assignRequestId (req);
            
        if (callback)
            this.requestsInProgress.set(req.id, callback);
            
        this.sendRequest (req);
    };
    
    this.sendRequest = function (req)
    {
        throw "pure function call";
    };
    
    this.onRequestResponse = function (resp)
    {
        var callback = this.requestsInProgress.get (resp.id);
        this.requestsInProgress.delete(resp.id);
        if (callback)
            callback(resp);
    };
    
    this.closeRequestsInProgress = function (callback)
    {
        this.requestsInProgress.forEach (function (val, key, map)
        {
            map.delete (key);
            if (callback)
                callback (key, val);
        });
    };
}

// Roxy HTTP Manager (replaces Native Host Manager for HTTP communication)
function RoxyHttpManager()
{
    this.ready = false;
    this.scheduledRequests = new Array;
    this.baseUrl = 'http://localhost:12579';
    this.initialized = false;
}

RoxyHttpManager.prototype.initialize = function()
{
    // Prevent initializing multiple times
    if (this.initialized) {
        return;
    }
    this.initialized = true;

    this.ready = true;
    this.onReady();
    for (var i = 0; i < this.scheduledRequests.length; i++)
        this.postMessage(this.scheduledRequests[i].task, this.scheduledRequests[i].callback);
    this.scheduledRequests = [];
};

RoxyHttpManager.prototype.onReady = function()
{
    console.log("Roxy HTTP Manager ready");
};

RoxyHttpManager.prototype.postMessage = function(task, callback)
{
    if (this.ready)
    {
        this.performRequest(task, callback);
    }
    else
    {
        var o = new Object;
        o.task = task;
        o.callback = callback;
        this.scheduledRequests.push(o);
    }
};

RoxyHttpManager.prototype.performRequest = async function(task, callback)
{
    try {
        let endpoint = '';
        let body = {};
        
        if (task.type === "create_downloads") {
            endpoint = '/api/download';
            if (task.create_downloads && task.create_downloads.downloads && task.create_downloads.downloads.length > 0) {
                const download = task.create_downloads.downloads[0];
                // Build a clean fallback filename: strip query strings and fragments
                // so we never send something like "download?id=abc&export=..." as the name.
                const rawBasename = (download.originalUrl || download.url).split('?')[0].split('#')[0].split('/').pop();
                body = {
                    url: download.url,
                    filename: download.suggestedName || rawBasename || "",
                    referrer: download.httpReferer,
                    cookies: download.httpCookies,
                    userAgent: download.userAgent,
                    postData: download.httpPostData,
                    documentUrl: download.documentUrl
                };
            }
        } else if (task.type === "query_settings") {
            endpoint = '/api/settings';
        } else if (task.type === "post_settings") {
            endpoint = '/api/settings';
            body = task.post_settings;
        }
        
        // Try main Roxy app port 12580 first, fallback to launcher port 12579
        const baseUrls = ['http://localhost:12580', 'http://localhost:12579'];
        let response = null;
        let lastError = null;

        for (const base of baseUrls) {
            try {
                const r = await fetch(base + endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(body)
                });
                if (r && r.ok) {
                    response = r;
                    break;
                }
            } catch (err) {
                lastError = err;
            }
        }

        if (response && response.ok) {
            const result = await response.json();
            if (callback) {
                callback({
                    id: task.id || "1",
                    error: "",
                    result: result
                });
            }
        } else {
            const errMsg = lastError ? lastError.message : (response ? 'HTTP error ' + response.status : 'Cannot connect to Roxy');
            console.error('HTTP request failed:', errMsg);
            if (callback) {
                callback({
                    id: task.id || "1",
                    error: errMsg,
                    result: "0"
                });
            }
        }
    } catch (error) {
        console.error('HTTP request error:', error);
        if (callback) {
            callback({
                id: task.id || "1",
                error: error.message,
                result: "0"
            });
        }
    }
};

// Task classes for HTTP communication
function RoxyHttpTask(id, type)
{
    this.id = id || "1";
    this.type = type || "";
}

function RoxyCreateDownloadsTask(id)
{
    RoxyHttpTask.call(this, id, "create_downloads");
    this.create_downloads = new Object;
    this.create_downloads.downloads = [];

    this.addDownload = function (download)
    {
        if (!download instanceof DownloadInfo)
            throw "invalid type";
        this.create_downloads.downloads.push (download);
    };
    
    this.hasDownloads = function ()
    {
        return this.create_downloads.downloads.length != 0;
    };
}

function RoxyQuerySettingsTask(id)
{
    RoxyHttpTask.call(this, id, "query_settings");
}

function RoxyPostSettingsTask(id)
{
    RoxyHttpTask.call(this, id, "post_settings");

    this.setSettings = function(s)
    {
        this.post_settings = s;
    };
}

// ResponseDetails and RequestDetails classes
class ResponseDetails {
    responseHeaders = null;
    contentType = "";
    contentLength = -1;
}

class RequestDetails {
    initiator = "";
    requestHeaders = [];
    cookies = "";
    url = "";
    time = 0;
    documentUrl = "";
    postData = "";
    tabId = -1;
    responseDetails = null;
}

// DownloadsInterceptManager class
function DownloadsInterceptManager()
{
    this.enable = false;
    this.pauseCatchingForAllSites = false;
    this.skipSmaller = 0;
    this.skipExts = "";
    this.catchExts = "";
    this.skipHosts = [];
    this.returningDownloads = [];
    this.requestDetailsByRequestId = new Map;
    this.requestDetailsByRequestUrl = [];
    this.supportsDeterminingFilename =
        browser.downloads &&
        browser.downloads.onDeterminingFilename;

    this.lastDownload = false;
    this.allowBrowserDownload = true;
    this.skipIfKeyPressed = false;
    this.skipKeyPressed = false;
}

DownloadsInterceptManager.prototype.initialize = function()
{
    // Prevent adding listeners multiple times
    if (this.initialized) {
        return;
    }
    this.initialized = true;

    if (this.supportsDeterminingFilename)
    {
        browser.downloads.onDeterminingFilename.addListener(
            this.onDeterminingFilename.bind(this));
    }
    browser.webRequest.onBeforeSendHeaders.addListener(
        this.onBeforeSendHeaders.bind(this),
        { urls: ["<all_urls>"] },
        manifestV2BlockingArray(["requestHeaders"]));
    browser.webRequest.onBeforeRequest.addListener(
        this.onBeforeRequest.bind(this),
        { urls: ["<all_urls>"] },
        ["requestBody"]);
    browser.webRequest.onSendHeaders.addListener(
        this.onSendHeaders.bind(this),
        { urls: ["<all_urls>"] },
        ["requestHeaders"]);
    browser.webRequest.onHeadersReceived.addListener(
        this.onHeadersReceived.bind(this),
        { urls: ["<all_urls>"] },
        manifestV2BlockingArray(["responseHeaders"]));
    browser.webRequest.onCompleted.addListener(
        this.onCompleted.bind(this),
        { urls: ["<all_urls>"] });
    browser.webRequest.onErrorOccurred.addListener(
        this.onErrorOccurred.bind(this),
        { urls: ["<all_urls>"] });
};

DownloadsInterceptManager.prototype.inSkipList = function(
    url, isOriginUrl, filename)
{
    if (this.skipIfKeyPressed && this.skipKeyPressed)
        return true;

    if (!isOriginUrl)
    {
        if (this.catchExts)
        {
            var str = filename ? filename : url;
            var rgx = filename ? /(\.([\w\d]+))$/ : /(?:[^\/]+)(\.(\w+))(?:\?.+)?(?:#.+)?$/;
            var match = rgx.exec(str);
            if (match && match.length === 3)
            {
                if (this.catchExts.indexOf(match[1].toLowerCase()) == -1 && 
                    this.catchExts.indexOf(match[2].toLowerCase()) == -1)
                {
                    return true;
                }
            }
        }
        else if (this.skipExts)
        {
            var str = filename ? filename : url;
            var rgx = filename ? /(\.([\w\d]+))$/ : /(?:[^\/]+)(\.(\w+))(?:\?.+)?(?:#.+)?$/;
            var match = rgx.exec(str);
            if (match && match.length === 3)
            {
                if (this.skipExts.indexOf(match[1].toLowerCase()) != -1 || 
                    this.skipExts.indexOf(match[2].toLowerCase()) != -1)
                {
                    return true;
                }
            }
        }
    }

    if (url)
    {
        if (url.toLowerCase().indexOf("filesystem:") == 0
            || url.toLowerCase().indexOf("blob:") == 0
            || url.toLowerCase().indexOf("data:") == 0)
        {
            return true;
        }

        if (this.skipHosts.length > 0 && roxyExtUtils.urlInSkipServers(this.skipHosts, url)) {
            return true;
        }
    }

    return false;
};

DownloadsInterceptManager.prototype.buildRequestDetails = function(details)
{
    let requestDetails = new RequestDetails;

    requestDetails.url = details.url;
    requestDetails.time = + new Date;
    requestDetails.tabId = details.tabId;
    requestDetails.initiator = details.initiator;

    requestDetails.documentUrl = details.documentUrl;
    if (!requestDetails.documentUrl && this.tabsMgr && details.tabId !== -1 && this.tabsMgr.tabExists(details.tabId))
        requestDetails.documentUrl = this.tabsMgr.tabs[details.tabId].url;

    if (details.method == "POST")
    {
        requestDetails.postData = "&";

        if (undefined != details.requestBody && undefined != details.requestBody.formData)
        {
            for (var field in details.requestBody.formData)
            {
                for (var i = 0; i < details.requestBody.formData[field].length; ++i)
                {
                    requestDetails.postData += field + "=" +
                        encodeURIComponent(details.requestBody.formData[field][i]) +
                        "&";
                }
            }
        }
    }

    return requestDetails;
};

DownloadsInterceptManager.prototype.onBeforeRequest = function(details)
{
    if (!this.enable || this.pauseCatchingForAllSites || this.inSkipList(details.url, false))
        return;

    let requestDetails = this.buildRequestDetails(details);

    this.requestDetailsByRequestId.set(details.requestId, requestDetails);

    if (browser.runtime.getManifest().manifest_version < 3)
        setTimeout(this.requestDetailsByRequestId.delete.bind(this.requestDetailsByRequestId, details.requestId), 120000);
    else
        startTimerAlarm('NRMRequestDetailsByRequestId', 120000, () => this.requestDetailsByRequestId.delete.bind(this.requestDetailsByRequestId, details.requestId));

    this.requestDetailsByRequestUrl.push(requestDetails);

    if (browser.runtime.getManifest().manifest_version < 3)
        setTimeout(this.removeRequestDetailsByOriginalUrl.bind(this, details.url, requestDetails.time), 120000);
    else
        startTimerAlarm('NRMRemoveRequestDetailsByOriginalUrl', 120000, () => this.removeRequestDetailsByOriginalUrl.bind(this, details.url, requestDetails.time));
};

DownloadsInterceptManager.prototype.removeRequestDetailsByOriginalUrl = function(
    url, time)
{
    var index = this.requestDetailsByRequestUrl.findIndex(item => (item.time === time && item.url === url));
    if (index !== -1) {
        this.requestDetailsByRequestUrl.splice(index, 1);
    }
};

DownloadsInterceptManager.prototype.onSendHeaders = function(
    details)
{
    if (!this.enable || this.pauseCatchingForAllSites || this.inSkipList(details.url, false))
        return;

    let rd = this.requestDetailsByRequestId.get(details.requestId);
    if (!rd)
        return;

    if (details.method == "POST" ||
        !this.supportsDeterminingFilename)
    {
        rd.requestHeaders = details.requestHeaders;
    }
};

DownloadsInterceptManager.prototype.onBeforeSendHeaders = function(
    details)
{
    if (!this.enable || this.pauseCatchingForAllSites || this.inSkipList(details.url, false))
        return;

    if (this.requestDetailsByRequestId.has(details.requestId))
    {
        let cookies = "";

        for (let h of details.requestHeaders)
        {
            if (h.name.toLowerCase() === "cookie")
            {
                if (cookies)
                    cookies += "; ";
                cookies += h.value;
            }
        }

        this.requestDetailsByRequestId.get(details.requestId).cookies = cookies;
    }
};

DownloadsInterceptManager.prototype.buildResponseDetails = function(
    headers)
{
    let result = new ResponseDetails;

    result.responseHeaders = this.responseHeadersToMap(headers);

    if (result.responseHeaders.has("content-type"))
        result.contentType = result.responseHeaders.get("content-type").toLowerCase();

    if (result.responseHeaders.has("content-length"))
        result.contentLength = parseInt(result.responseHeaders.get("content-length"));

    return result;
};

DownloadsInterceptManager.prototype.responseHeadersToMap = function(responseHeadersArr)
{
    if (!responseHeadersArr || !responseHeadersArr.length)
        return new Map();

    var headers_map = new Map();

    for (var i = 0; i < responseHeadersArr.length; i++)
    {
        headers_map.set(responseHeadersArr[i].name.toLowerCase(), responseHeadersArr[i].value);
    }

    return headers_map;
};

DownloadsInterceptManager.prototype.onHeadersReceived = function(
    details)
{
    let rd = this.requestDetailsByRequestId.get(details.requestId);
    if (!rd)
        return;

    rd.responseDetails = this.buildResponseDetails(details.responseHeaders);

    if (!this.supportsDeterminingFilename)
        return this.interceptIfRequiredByHeaders(details);
};

DownloadsInterceptManager.prototype.onCompleted = function(
    details)
{
    this.onDoneWithRequest(details);
};

DownloadsInterceptManager.prototype.onErrorOccurred = function(
    details)
{
    this.onDoneWithRequest(details);
};

DownloadsInterceptManager.prototype.onDoneWithRequest = function (
    details)
{
    this.requestDetailsByRequestId.delete(details.requestId);
};

DownloadsInterceptManager.prototype.interceptIfRequiredByHeaders = function(
    details)
{
    var result;

    if (details.tabId < 0)
        return;

    var requestDetails = this.requestDetailsByRequestId.get(details.requestId);

    var in_skip_list = false;
    if (this.inSkipList(details.url, false)) {
        in_skip_list = true;
    } else if (details.originUrl && this.inSkipList(details.originUrl, true)) {
        in_skip_list = true;
    }

    if (this.enable && !this.pauseCatchingForAllSites &&
        !in_skip_list)
    {
        var file = false;
        var noContentLengthLimits = false;

        if (details.type != "xmlhttprequest" && 
            (details.method == "POST" || details.type == 'main_frame' || details.type == 'sub_frame'))
        {
            details.responseHeadersMap = requestDetails.responseDetails.responseHeaders;

            if (requestDetails.responseDetails.responseHeaders.has("content-disposition"))
            {
                file = true;
            }

            if (requestDetails.responseDetails.contentType)
            {
                if (requestDetails.responseDetails.contentType.indexOf("json") != -1 ||
                    requestDetails.responseDetails.contentType.indexOf("image/") != -1 ||
                    (requestDetails.responseDetails.contentType.indexOf("text") != -1 && requestDetails.responseDetails.contentType.indexOf("text/x-sql") == -1) ||
                    requestDetails.responseDetails.contentType.indexOf("javascript") != -1 ||
                    requestDetails.responseDetails.contentType.indexOf("application/x-protobuf") != -1 ||
                    requestDetails.responseDetails.contentType.indexOf("application/binary") != -1 ||
                    requestDetails.responseDetails.contentType.indexOf("application/pdf") != -1)
                {
                    file = false;
                }
                else if (requestDetails.responseDetails.contentType.indexOf("application/x-bittorrent") != -1) 
                {
                    file = true;
                    noContentLengthLimits = true;
                }
                else if (details.method != "POST" && requestDetails.responseDetails.contentType.indexOf("application") != -1)
                {
                    file = true;
                }
            }

            if (file && !this.supportsDeterminingFilename)
            {
                if (requestDetails.responseDetails.contentLength !== -1)
                {
                    if (!noContentLengthLimits) {
                        if (requestDetails.responseDetails.contentLength < 1024 * 1024)
                            file = false;
                        else if (requestDetails.responseDetails.contentLength < this.skipSmaller)
                            file = false;
                    }
                }
                else
                {
                    file = false;
                }
            }
        }

        if (file)
        {
            var referrer = "";
            for (let j = 0; j < requestDetails.requestHeaders.length; ++j)
            {
                let rheader = requestDetails.requestHeaders[j];
                if (rheader.name.toLowerCase() == "referrer" ||
                    rheader.name.toLowerCase() == "referer")
                    referrer = rheader.value;
            }

            var downloadInfo = new DownloadInfo(
                details.url,
                "",
                referrer,
                requestDetails ? requestDetails.postData : "",
                requestDetails ? requestDetails.documentUrl : "");

            downloadInfo.httpCookies = requestDetails.cookies;

            this.onDownloadIntercepted(downloadInfo, details);

            if (details.method === "POST")
            {
                if (referrer)
                {
                    browser.tabs.update(details.tabId, { 'url': referrer });
                }
                result = { 'redirectUrl': "javascript:" };
            }
            else
            {
                result = { 'cancel': true };
            }
        }
    }

    return result;
};

DownloadsInterceptManager.prototype.onDeterminingFilename = function(
    downloadItem, suggest)
{
    if (!this.enable || this.pauseCatchingForAllSites || this.inSkipList(downloadItem.url, false))
        return false;

    // Simple implementation - send to Roxy and cancel Chrome download
    this.continueDeterminingFilename(downloadItem, suggest, null, false);

    return true;
};

DownloadsInterceptManager.prototype.continueDeterminingFilename = function(
    downloadItem, suggest, details, detailsBetter)
{
    if (downloadItem.totalBytes != 0 && downloadItem.totalBytes != -1 && downloadItem.totalBytes < this.skipSmaller) {
        suggest();
        return;
    }

    if (this.inSkipList(downloadItem.url, false, downloadItem.filename)) {
        suggest();
        return;
    }

    browser.downloads.cancel(downloadItem.id, function() {
        browser.downloads.erase({ id: downloadItem.id })
    });

    let info = new DownloadInfo(
        detailsBetter ? details.url : downloadItem.url,
        detailsBetter ? details.url : downloadItem.finalUrl,
        downloadItem.referrer,
        details ? details.postData : "",
        details ? details.documentUrl : "");

    // Always capture Chrome's resolved filename (from Content-Disposition or URL).
    // Chrome's downloadItem.filename is already the best available name at this point.
    if (downloadItem.filename)
        info.suggestedName = downloadItem.filename;

    this.onDownloadIntercepted(info);
};

DownloadsInterceptManager.prototype.onDownloadIntercepted = function(
    downloadInfo, details, callbackFn)
{
    downloadInfo.userAgent = navigator.userAgent;

    if (downloadInfo.httpCookies)
    {
        this.passDownloadToRoxy(downloadInfo, details, callbackFn);
    }
    else
    {
        var cm = new CookieManager;
        cm.getCookiesForUrl(
            downloadInfo.url,
            function (cookies)
            {
                downloadInfo.httpCookies = cookies;
                this.passDownloadToRoxy(downloadInfo, details, callbackFn);
            }.bind(this));
    }
};

DownloadsInterceptManager.prototype.passDownloadToRoxy = function(
    downloadInfo, details, callbackFn)
{
    var task = new RoxyCreateDownloadsTask;
    task.create_downloads.catchedDownloads = "1";
    task.create_downloads.waitResponse = "1";
    task.addDownload(downloadInfo);
    this.httpManager.postMessage(
        task,
        function (resp)
        {
            var cancelled = resp.result == "0";
            if (resp.error || (cancelled && this.allowBrowserDownload))
                this.returnDownload(downloadInfo, details);
        }.bind(this)
    );
};

DownloadsInterceptManager.prototype.returnDownload = function(
    downloadInfo, details)
{
    console.log("Returning download to browser:", downloadInfo.url);
    // Implementation for returning download to browser if needed
};

// ContextMenuManager class
function ContextMenuManager()
{
    this.handlerRegistered = false;
    this.m_dlAllExists = false;
    this.m_dlthisExists = false;
    this.m_dlselectedExists = false;
    this.m_dlpageExists = false;
    this.m_dlvideoExists = false;
    this.m_dlchannelVideosExists = false;
    this.m_dlplaylistVideosExists = false;
}

ContextMenuManager.prototype.onUserDownloadLinks = function(
    links, pageUrl, youtubeVideosFlag)
{
    console.log("Download links:", links);
    var task = new RoxyCreateDownloadsTask;
    for (var i = 0; i < links.length; ++i)
    {
        var downloadInfo = new DownloadInfo(links[i], "", pageUrl);
        downloadInfo.userAgent = navigator.userAgent;
        task.addDownload(downloadInfo);
    }
    this.httpManager.postMessage(task);
};

ContextMenuManager.prototype.onUserDownloadPage = function(
    pageUrl)
{
    console.log("Download page:", pageUrl);
    this.onUserDownloadLinks([pageUrl], pageUrl);
};

ContextMenuManager.prototype.onUserDownloadVideo = function(
    pageUrl)
{
    console.log("Download video:", pageUrl);
    this.onUserDownloadLinks([pageUrl], pageUrl);
};

ContextMenuManager.prototype.createMenu = function (
    dlthis, dlall, dlselected, dlpage, dlvideo, dlchannelvideos, dlplaylistvideos)
{
    if (dlthis)
        this.createDlThisMenu();
    else
        this.removeDlThisMenu();

    if (dlall)
        this.createDlAllMenu();
    else
        this.removeDlAllMenu();

    if (dlselected)
        this.createDlSelectedMenu();
    else
        this.removeDlSelectedMenu();

    if (dlpage)
        this.createDlPageMenu();
    else
        this.removeDlPageMenu();

    if (dlvideo)
        this.createDlVideoMenu();
    else
        this.removeDlVideoMenu();
    
    if(dlchannelvideos)
        this.createDlChannelVideosMenu();
    else 
        this.removeDlChannelVideosMenu();

    if(dlplaylistvideos)
        this.createDlPlaylistVideosMenu();
    else
        this.removeDlPlaylistVideosMenu();

    if (!this.handlerRegistered)
    {
        browser.contextMenus.onClicked.addListener(this.onClicked.bind(this));
        this.handlerRegistered = true;
    }
};

ContextMenuManager.prototype.createDlThisMenu = function()
{
    if (this.m_dlthisExists)
        return;

    this.m_dlthisExists = true;
    
    let o = {
        "id": "dlthis",
        "title": "Download with Roxy",
        "contexts": ["image", "link"],
    };

    browser.contextMenus.create(o);
};

ContextMenuManager.prototype.createDlAllMenu = function()
{
    if (this.m_dlAllExists)
        return;

    this.m_dlAllExists = true;

    browser.contextMenus.create(
    {
        "id": "dlall",
        "title": "Download all links with Roxy",
        "contexts": ["page"]
    });
};

ContextMenuManager.prototype.createDlSelectedMenu = function()
{
    if (this.m_dlselectedExists)
        return;

    this.m_dlselectedExists = true;

    browser.contextMenus.create(
    {
        "id": "dlselected",
        "title": "Download selected links with Roxy",
        "contexts": ["selection"]
    });
};

ContextMenuManager.prototype.createDlPageMenu = function()
{
    if (this.m_dlpageExists)
        return;

    this.m_dlpageExists = true;

    browser.contextMenus.create(
    {
        "id": "dlpage",
        "title": "Download page with Roxy",
        "contexts": ["page"]
    });
};

ContextMenuManager.prototype.createDlVideoMenu = function()
{
    if (this.m_dlvideoExists)
        return;

    this.m_dlvideoExists = true;

    browser.contextMenus.create(
    {
        "id": "dlvideo",
        "title": "Download video with Roxy",
        "contexts": ["page"]
    });
};

ContextMenuManager.prototype.createDlChannelVideosMenu = function()
{
    if (this.m_dlchannelVideosExists)
        return;
    
    this.m_dlchannelVideosExists = true;  
    
    browser.contextMenus.create(
    {
        "id": "dlchanelvideos",
        "title": "Download channel videos with Roxy",
        "contexts": ["page"]
    });    
};

ContextMenuManager.prototype.createDlPlaylistVideosMenu = function()
{
    if (this.m_dlplaylistVideosExists)
        return;

    this.m_dlplaylistVideosExists = true;

    browser.contextMenus.create(
    {
        "id": "dlplaylistvideos",
        "title": "Download playlist videos with Roxy",
        "contexts": ["page"]
    });
};

ContextMenuManager.prototype.removeDlThisMenu = function()
{
    if (!this.m_dlthisExists)
        return;

    this.m_dlthisExists = false;

    browser.contextMenus.remove("dlthis");
};

ContextMenuManager.prototype.removeDlAllMenu = function()
{
    if (!this.m_dlAllExists)
        return;

    this.m_dlAllExists = false;

    browser.contextMenus.remove("dlall");
};

ContextMenuManager.prototype.removeDlSelectedMenu = function()
{
    if (!this.m_dlselectedExists)
        return;

    this.m_dlselectedExists = false;

    browser.contextMenus.remove("dlselected");
};

ContextMenuManager.prototype.removeDlPageMenu = function()
{
    if (!this.m_dlpageExists)
        return;

    this.m_dlpageExists = false;

    browser.contextMenus.remove("dlpage");
};

ContextMenuManager.prototype.removeDlVideoMenu = function()
{
    if (!this.m_dlvideoExists)
        return;

    this.m_dlvideoExists = false;

    browser.contextMenus.remove("dlvideo");
};

ContextMenuManager.prototype.removeDlChannelVideosMenu = function()
{
    if (!this.m_dlchannelVideosExists)
        return;

    this.m_dlchannelVideosExists = false;

    browser.contextMenus.remove("dlchanelvideos");
};

ContextMenuManager.prototype.removeDlPlaylistVideosMenu = function()
{
    if (!this.m_dlplaylistVideosExists)
        return;

    this.m_dlplaylistVideosExists = false;

    browser.contextMenus.remove("dlplaylistvideos");
};

ContextMenuManager.prototype.onClicked = function(
    info, tab)
{
    switch(info.menuItemId)
    {
        case "dlall": this.onClickedDlAll(info, tab); break;
        case "dlselected": this.onClickedDlSelected(info, tab); break;
        case "dlpage": this.onClickedDlPage(info, tab); break;
        case "dlvideo": this.onClickedDlVideo(info, tab); break;
        case "dlchanelvideos": this.onClickedDlChannelVideos(info, tab); break;
        case "dlplaylistvideos": this.onClickedDlPlaylistVideos(info, tab); break;
        case "dlthis": this.onClickedDlThis(info, tab); break;
    }
};

ContextMenuManager.prototype.onClickedDlThis = function(info, tab)
{
    if (info.linkUrl)
        this.onUserDownloadLinks([info.linkUrl], info.pageUrl);
    else if (info.mediaType == "image")
        this.onUserDownloadLinks([info.srcUrl], info.pageUrl);
};

ContextMenuManager.prototype.onClickedDlAll = function(
    info, tab)
{
    browser.scripting.executeScript(
    {
        "target": {"tabId": tab.id, "frameIds": [info.frameId]},
        "func": () => {return JSON.stringify([].map.call(document.getElementsByTagName('a'), function(n) {return n.href;}).concat([].map.call(document.getElementsByTagName('img'), function(n) {return n.src;})));}
    },
    function(h) {
        let links = [];
        for (let i = 0; i < h.length; i++) {
            try {
                let l = JSON.parse(h[i].result);
                if (l && l.length > 0) {
                    links = links.concat(l.filter(function (el) {
                        return el != '';
                    }));
                }
            } catch (e) {
            }
        }
        this.onUserDownloadLinks(links, tab.url);
    }.bind(this));
};

ContextMenuManager.prototype.onClickedDlSelected = function(
    info, tab)
{
    browser.scripting.executeScript(
    {
        "target": {"tabId": tab.id, "frameIds": [info.frameId] },
        "func": () => {
            let s = window.getSelection();
            let dv = document.createElement('div');
            for (let i = 0; i < s.rangeCount; ++i) {
                dv.appendChild(s.getRangeAt(i).cloneContents());
            }
            return JSON.stringify([].map.call(dv.getElementsByTagName('a'), function(n) {return n.href;}));
        }
    },
    function(h) {
        let links = [];
        for (let i = 0; i < h.length; i++)
        {
            try {
                let l = JSON.parse(h[i].result);
                if (l && l.length > 0) {
                    links = links.concat(l.filter(function (el) {
                        return el != '';
                    }));
                }
            }
            catch (e){}
        }

        this.onUserDownloadLinks(links, tab.url);
    }.bind(this));

    this.createDlThisMenu();
};

ContextMenuManager.prototype.onClickedDlPage = function(
    info, tab)
{
    this.onUserDownloadPage(tab.url);
};

ContextMenuManager.prototype.onClickedDlVideo = function(
    info, tab)
{
    this.onUserDownloadVideo(tab.url);
};

ContextMenuManager.prototype.onClickedDlChannelVideos = function(
    info, tab)
{
    this.onUserDownloadLinks([this.youtubeChannelVideosUrl], this.youtubeChannelVideosUrl, 1);
};

ContextMenuManager.prototype.onClickedDlPlaylistVideos = function(
    info, tab)
{
    this.onUserDownloadLinks([this.youtubePlaylistUrl], this.youtubePlaylistUrl, 2);
};

// RoxyContextMenuManager extends ContextMenuManager
function RoxyContextMenuManager(tabsManager)
{
    this.m_dlthis = false;
    this.m_dlall = false;
    this.m_dlselected = false;
    this.m_dlpage = false;
    this.m_dlvideo = false;
    this.m_dlYtChannel = false;
    this.m_dlYtPlaylist = false;
    this.m_browserHasSelection = false;
    this.m_browserSelectionLinksCount = 0;
    this.tabsManager = tabsManager;

    this.youtubeDomain = false;
    this.youtubeChannelVideosUrl = '';
    this.youtubePlaylistUrl = '';

    this.DownloadAsLinks = new Set();
    this.DownloadAsLinks.add("www.youtube.com");
}

RoxyContextMenuManager.prototype = new ContextMenuManager();

RoxyContextMenuManager.prototype.setHttpManager = function (mgr)
{
    // Prevent adding listeners multiple times
    if (this.httpManager) {
        return;
    }
    
    this.httpManager = mgr;
    browser.runtime.onMessage.addListener(this.onMessage.bind(this));
};

RoxyContextMenuManager.prototype.createMenu = function (
    dlthis, dlall, dlselected, dlpage, dlvideo, dlYtChannel, dlYtPlaylist)
{
    this.m_dlthis = dlthis;
    this.m_dlall = dlall;
    this.m_dlselected = dlselected;
    this.m_dlpage = dlpage;
    this.m_dlvideo = dlvideo;
    this.m_dlYtChannel = dlYtChannel;
    this.m_dlYtPlaylist = dlYtPlaylist;
    this.createMenuImpl();
};

RoxyContextMenuManager.prototype.createMenuImpl = function()
{
    if (this.youtubeDomain) {
        ContextMenuManager.prototype.createMenu.call(
            this, false, false, false, false, false, false, false);
        return true;
    }
    
    ContextMenuManager.prototype.createMenu.call(
        this,
        this.shouldShowDlThis(),
        this.m_dlall, 
        this.shouldShowDlSelected(),
        this.m_dlpage, 
        this.shouldShowDlVideo(),
        this.shouldShowDlChannel(),
        this.shouldShowDlPlaylist());
};

RoxyContextMenuManager.prototype.shouldShowDlThis = function()
{
    return this.m_dlthis && !this.shouldShowDlSelected();
};

RoxyContextMenuManager.prototype.shouldShowDlSelected = function()
{
    return this.m_dlselected
            && this.m_browserHasSelection
            && this.m_browserSelectionLinksCount;
};

RoxyContextMenuManager.prototype.shouldShowDlVideo = function ()
{
    return this.m_dlvideo &&
        this.tabsManager.activeTabHasVideo();
};

RoxyContextMenuManager.prototype.shouldShowDlChannel = function ()
{
    return this.m_dlvideo && this.m_dlYtChannel &&
        this.youtubeChannelVideosUrl !== '';
};

RoxyContextMenuManager.prototype.shouldShowDlPlaylist = function ()
{
    return this.m_dlvideo && this.m_dlYtPlaylist &&
        this.youtubePlaylistUrl !== '';
};

RoxyContextMenuManager.prototype.onMessage = function(request, sender)
{
    if (sender && sender.tab) {
        if (request.type === 'roxy_reset_context_menu' && sender.tab.active) {
            return;
        }
        if (!sender.tab.active && request.type !== 'roxy_reset_context_menu') {
            return;
        }
        if (sender.frameId > 0 && sender.tab.url.indexOf('youtube.com') >= 0) {
            return;
        }
    }

    if (request.type === 'roxy_reset_context_menu' || request.type === 'roxy_reset_context_menu_beforeunload') {
        this.youtubeDomain = false;
        this.youtubeChannelVideosUrl = '';
        this.youtubePlaylistUrl = '';
        this.m_browserSelectionLinksCount = 0;
        this.m_browserHasSelection = 0;
        this.createMenuImpl();
    }

    if (request.type === "roxy_selection_change")
    {
        this.youtubeDomain = false;
        this.youtubeChannelVideosUrl = '';
        this.youtubePlaylistUrl = '';
        try {
            if (request.data) {
                this.youtubeDomain = request.data.youtubeDomain;
            }
        } catch (e) {}
        try {
            if (request.data) {
                this.youtubeChannelVideosUrl = request.data.youtubeChannelVideosUrl;
            }
        } catch (e) {}
        try {
            if (request.data) {
                this.youtubePlaylistUrl = request.data.youtubePlaylistUrl;
            }
        } catch (e) {}

        this.m_browserSelectionLinksCount = request.selectionLinksCount;
        this.m_browserHasSelection = request.hasSelection;
        this.createMenuImpl();
    }

    if (request.type === "roxy_right_mouse_button_clicked")
    {
        this.youtubeDomain = false;
        this.youtubeChannelVideosUrl = '';
        this.youtubePlaylistUrl = '';
        try {
            if (request.data) {
                this.youtubeDomain = request.data.youtubeDomain;
            }
        } catch (e) {}
        try {
            if (request.data) {
                this.youtubeChannelVideosUrl = request.data.youtubeChannelVideosUrl;
            }
        } catch (e) {}
        try {
            if (request.data) {
                this.youtubePlaylistUrl = request.data.youtubePlaylistUrl;
            }
        } catch (e) {}

        this.createMenuImpl();
        setTimeout(function(){
            this.createMenuImpl()
        }.bind(this), 200);
    }

    if (request.type === "roxy_left_mouse_button_clicked")
    {
        this.createMenuImpl();
        setTimeout(function(){
            this.createMenuImpl()
        }.bind(this), 200);
    }
};

// TabsManager class
function TabInfo()
{
    this.hasVideo = false;
}

TabInfo.prototype.update = function(
    tab)
{
    if (tab.hasOwnProperty("url"))
        this.url = tab.url;
}

function TabsManager()
{
}

TabsManager.prototype.initialize = function()
{
    // Prevent adding listeners multiple times
    if (this.initialized) {
        return;
    }
    this.initialized = true;

    browser.tabs.onCreated.addListener(
        this.onTabCreated.bind(this));
    browser.tabs.onUpdated.addListener(
        this.onTabUpdated.bind(this));
    browser.tabs.onRemoved.addListener(
        this.onTabRemoved.bind(this));
    browser.tabs.onActivated.addListener(
        this.onTabActivated.bind(this));
    setInterval(
        this.onTimer.bind(this),
        1000);
};

TabsManager.prototype.tabs = {};

TabsManager.prototype.tabExists = function(
    id)
{
    return this.tabs.hasOwnProperty(id);
};

TabsManager.prototype.onTabCreated = function (
    tab)
{
    if (!tab.hasOwnProperty("id"))
    {
        console.error("onTabCreated: tab has no id", tab.id);
        return;
    }
    this.tabs[tab.id] = new TabInfo();
    this.tabs[tab.id].update(tab);
    this.onTabUrlChanged(tab.id);
};

TabsManager.prototype.onTabUpdated = function (
    id, changeInfo, tab)
{
    if (!this.tabExists(id))
    {
        this.onTabCreated(tab);

        if (!this.tabExists(id))
        {
            console.error("onTabUpdated: unknown tab", id);
            return;
        }
    }

    if (changeInfo.url)
    {
        this.tabs[id].url = changeInfo.url;
        this.onTabUrlChanged(id);
    }
};

TabsManager.prototype.onTabRemoved = function (
    id, removeInfo)
{
    if (this.tabExists(id))
        delete this.tabs[id];
};

TabsManager.prototype.onTabActivated = function (
    activeInfo)
{
    this.activeTabId = activeInfo.tabId;
};

TabsManager.prototype.onTabUrlChanged = function (
    id)
{
    this.tabs[id].hasVideo = false;
    var url = this.tabs[id].url;
    if (!url)
        return;
    var re = new RegExp("^(http[s]?):\\/\\/(www\\.)?youtube\\.com\\/watch\\?(([^v=]+)=([^&]+)&)*v=.+");
    if (url.match(re))
        this.tabs[id].hasVideo = true;
};

TabsManager.prototype.activeTabHasVideo = function()
{
    try 
    {
        return this.tabs[this.activeTabId].hasVideo;
    }
    catch (err)
    {
        return false;
    }
};

TabsManager.prototype.onTimer = function()
{
    browser.tabs.query({ active: true, currentWindow: true }, function(tabs)
    {
        if (tabs.length) {
            this.activeTabId = tabs[0].id;
        } else {
            this.activeTabId = false;
        }
    }.bind(this));
};

// RoxyDownloadsInterceptManager extends DownloadsInterceptManager
function RoxyDownloadsInterceptManager()
{
    this.allowBrowserDownload = true;
}

RoxyDownloadsInterceptManager.prototype = new DownloadsInterceptManager();

RoxyDownloadsInterceptManager.prototype.setHttpManager = function(mgr)
{
    this.httpManager = mgr;
};

RoxyDownloadsInterceptManager.prototype.setTabsManager = function(mgr)
{
    this.tabsMgr = mgr;
};

// Settings helper
function RoxySettingsPageHelper(httpManager, roxyExt)
{
    this.httpManager = httpManager;
    this.roxyExt = roxyExt;
}

RoxySettingsPageHelper.prototype.initialize = function()
{
    // Prevent adding listeners multiple times
    if (this.initialized) {
        return;
    }
    this.initialized = true;

    browser.runtime.onMessage.addListener(this.onMessage.bind(this));
    this.setIcon(this.roxyExt.diManager.pauseCatchingForAllSites);
};

RoxySettingsPageHelper.prototype.onMessage = function(request, sender, sendResponse)
{
    if (request.type === "get_settings_for_page") {
        sendResponse(this.roxyExt.settings);
    }
    if (request.type === "get_pause_on_all_sites_flag") {
        sendResponse(this.roxyExt.diManager.pauseCatchingForAllSites);
    }
    if (request.type === "set_pause_on_all_sites_flag") {
        this.roxyExt.diManager.pauseCatchingForAllSites = request.pause;
        this.setIcon(request.pause);
    }
    if (request.type === "change_active_tab_in_skip_list") {
        this.changeActiveTabInSkipList(request.checked);
    }
    if (request.type === "save_settings") {
        this.roxyExt.settings = request.settings;
        this.applySettings();
        sendResponse({success: true});
    }
};

RoxySettingsPageHelper.prototype.setIcon = function(in_pause)
{
    let action = browser.runtime.getManifest().manifest_version < 3 ? 
        chrome.browserAction : 
        chrome.action;
        
    if (in_pause) {
        action.setBadgeText({ text: 'off' });
        action.setBadgeBackgroundColor({ color: '#f44336' });
    } else {
        action.setBadgeText({ text: '' });
        action.setBadgeBackgroundColor({ color: '#4CAF50' });
    }
};

RoxySettingsPageHelper.prototype.changeActiveTabInSkipList = function(checked)
{
    browser.tabs.query({ active: true, currentWindow: true }, function(tabs) {
        if (tabs.length) {
            var url = tabs[0].url;
            this.changeSkipList(url, checked);
        }
    }.bind(this));
};

RoxySettingsPageHelper.prototype.changeSkipList = function (url, checked) {
    var new_skip_servers;
    if (checked) {
        new_skip_servers = roxyExtUtils.addUrlToSkipServers(this.roxyExt.diManager.skipHosts, url);
    } else {
        new_skip_servers = roxyExtUtils.removeUrlFromSkipServers(this.roxyExt.diManager.skipHosts, url);
    }
    var new_skip_servers_str = roxyExtUtils.skipServers2string(new_skip_servers);

    var s = this.roxyExt.settings;
    s.browser.monitor.skipServers = new_skip_servers_str;
    s.browser.monitor.skipServersEnabled = "1";

    var task = new RoxyPostSettingsTask;
    task.setSettings(s);
    this.httpManager.postMessage(
        task,
        this.onSettingsUpdated.bind(this));
};

RoxySettingsPageHelper.prototype.onSettingsUpdated = function() {
    this.roxyExt.applySettings();
};

// Main Roxy Extension class
function RoxyExtension()
{
    this.httpManager = new RoxyHttpManager;
    this.httpManager.onReady = this.onHttpManagerReady.bind(this);

    this.tabsManager = new TabsManager();

    this.cmManager = new RoxyContextMenuManager(this.tabsManager);
    this.cmManager.setHttpManager(this.httpManager);

    this.settingsPageHlpr = new RoxySettingsPageHelper(this.httpManager, this);

    this.diManager = new RoxyDownloadsInterceptManager();
    this.diManager.setHttpManager(this.httpManager);
    this.diManager.setTabsManager(this.tabsManager);

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
    
    this.initialized = false;
}

RoxyExtension.prototype.initialize = function()
{
    // Prevent initializing multiple times
    if (this.initialized) {
        return;
    }
    this.initialized = true;
    
    this.httpManager.initialize();
};

RoxyExtension.prototype.onHttpManagerReady = function()
{
    this.diManager.initialize();
    this.tabsManager.initialize();
    this.settingsPageHlpr.initialize();
    this.applySettings();
};

RoxyExtension.prototype.applySettings = function()
{
    this.cmManager.createMenu(
        this.settings.browser.menu.dllink != "0",
        this.settings.browser.menu.dlall != "0",
        this.settings.browser.menu.dlselected != "0",
        this.settings.browser.menu.dlpage != "0",
        this.settings.browser.menu.dlvideo != "0",
        this.settings.browser.menu.dlYtChannel != "0",
        this.settings.browser.menu.dlYtPlaylist != "0"
    );

    this.diManager.enable = this.settings.browser.monitor.enable != "0";
    this.diManager.skipSmaller = Number(this.settings.browser.monitor.skipSmallerThan);
    this.diManager.skipExts = this.settings.browser.monitor.skipExtensions.toLowerCase();
    if (this.settings.browser.monitor.hasOwnProperty("catchExtensions"))
        this.diManager.catchExts = this.settings.browser.monitor.catchExtensions.toLowerCase();
    this.diManager.skipHosts = roxyExtUtils.skipServers2array(this.settings.browser.monitor.skipServers);
    this.diManager.allowBrowserDownload = this.settings.browser.monitor.allowDownload != "0";
    this.diManager.skipIfKeyPressed = this.settings.browser.monitor.skipIfKeyPressed != "0";
};

RoxyExtension.prototype.updateSettings = function()
{
    this.applySettings();
};

// Badge update function
function updateBadge(isEnabled) {
  if (isEnabled) {
    chrome.action.setBadgeText({ text: '' });
    chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });
  } else {
    chrome.action.setBadgeText({ text: 'off' });
    chrome.action.setBadgeBackgroundColor({ color: '#f44336' });
  }
}

// Initialize extension
var roxyExt;
var extensionStarted = false;

function startExtension()
{
    if (extensionStarted) {
        return;
    }
    extensionStarted = true;
    
    roxyExt = new RoxyExtension;
    roxyExt.initialize();
}

chrome.runtime.onInstalled.addListener(() => {
  console.log("Roxy Download Manager extension installed");
  
  // Set default enabled state
  chrome.storage.local.get(['extensionEnabled'], (result) => {
    if (result.extensionEnabled === undefined) {
      chrome.storage.local.set({ extensionEnabled: true });
    }
    updateBadge(result.extensionEnabled !== false);
  });
  
  startExtension();
});

// Listen for storage changes to update badge
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === 'local' && changes.extensionEnabled) {
    const isEnabled = changes.extensionEnabled.newValue !== false;
    updateBadge(isEnabled);
    
    if (roxyExt) {
        roxyExt.diManager.enable = isEnabled;
    }
  }
});

// Start extension on startup (for cases where onInstalled doesn't fire)
chrome.runtime.onStartup.addListener(() => {
  startExtension();
});

// Start extension if already installed (fallback)
if (!extensionStarted) {
    startExtension();
}