// Guard flag: set to true when the extension is reloaded/invalidated.
// All sendMessage calls and recurring timers check this first.
var roxyContextInvalidated = false;

/**
 * Safe wrapper around browser.runtime.sendMessage.
 * Silently absorbs "Extension context invalidated" errors that occur when the
 * extension is reloaded while a content script is still alive on the page.
 */
function safeSendMessage(msg) {
    if (roxyContextInvalidated) return;
    try {
        browser.runtime.sendMessage(msg);
    } catch (e) {
        if (e && e.message && e.message.includes('Extension context invalidated')) {
            roxyContextInvalidated = true;
        } else {
            // Re-throw unexpected errors so they're still visible in DevTools.
            throw e;
        }
    }
}

document.addEventListener("selectionchange", dealWithSelection, true);

function dealWithSelection()
{
    if (roxyContextInvalidated) return;

    var linksCount = 0;
    var selection = window.getSelection();
    var links = null;
    if (selection && selection.rangeCount)
    {
        var dv = document.createElement('div');
        for (var i = 0; i < selection.rangeCount; ++i)
        {
          dv.appendChild(selection.getRangeAt(i).cloneContents());
        }

        links = [].map.call(dv.getElementsByTagName('a'), function(n) { 
            return n.href;
        });
        linksCount = links.length;
    }

    var youtubeDomain = roxyExtUtils.isYoutubeDomain();
    var youtubeChannelVideosUrl = roxyExtUtils.findYoutubeChannelVideosUrl();
    var youtubePlaylistUrl = roxyExtUtils.findYoutubePlaylist();

    safeSendMessage({
        type: "roxy_selection_change", 
        hasSelection: selection && selection.rangeCount != 0,
        selectionLinksCount: linksCount,
        selectionLinks: links,
        data: {youtubeDomain: youtubeDomain, youtubeChannelVideosUrl: youtubeChannelVideosUrl, youtubePlaylistUrl: youtubePlaylistUrl}
    });
    // Only reschedule if the context is still alive and we're waiting for YouTube info.
    if (!roxyContextInvalidated && !youtubeChannelVideosUrl.length && roxyExtUtils.youtubeChannelInfoLoading()) {
        setTimeout(dealWithSelection, 5000);
    }
}

document.addEventListener("mousedown", function(event){

    if (event.button == 2)
    {
        var youtubeDomain = roxyExtUtils.isYoutubeDomain();
        var youtubeChannelVideosUrl = roxyExtUtils.findYoutubeChannelVideosUrl();
        var youtubePlaylistUrl = roxyExtUtils.findYoutubePlaylist();
        safeSendMessage({
            type: "roxy_right_mouse_button_clicked",
            data: {youtubeDomain: youtubeDomain, youtubeChannelVideosUrl: youtubeChannelVideosUrl, youtubePlaylistUrl: youtubePlaylistUrl}
        });
    }

    if (event.button == 1)
    {
        safeSendMessage({
            type: "roxy_left_mouse_button_clicked",
        });
    }
});

// http://stackoverflow.com/a/19519701
var vis = (function(){
    var stateKey, eventKey, keys = {
        hidden: "visibilitychange",
        webkitHidden: "webkitvisibilitychange",
        mozHidden: "mozvisibilitychange",
        msHidden: "msvisibilitychange"
    };
    for (stateKey in keys) {
        if (stateKey in document) {
            eventKey = keys[stateKey];
            break;
        }
    }
    return function(c) {
        if (c) document.addEventListener(eventKey, c);
        return !document[stateKey];
    }
})();

vis(function(){
    var visible = vis();
    if (visible)
    {
        dealWithSelection();
    }
});

(function() {
    var listener = function () {
        document.removeEventListener('DOMContentLoaded', listener);
        setTimeout(dealWithSelection, 1000);
        //for slow connection
        setTimeout(dealWithSelection, 5000);
        setTimeout(dealWithSelection, 10000);
    };
    if (document.readyState!='loading') {
        dealWithSelection();
    } else if (document.addEventListener) {
        document.addEventListener('DOMContentLoaded', listener);
    }
})();

(function() {
    if (window.addEventListener) {
        window.addEventListener('beforeunload', function(event) {
            safeSendMessage({
                type: "roxy_reset_context_menu_beforeunload",
                t_event: "beforeunload"
            });
        }, false);
        window.addEventListener("blur", function( event ) {
            safeSendMessage({
                type: "roxy_reset_context_menu",
                t_event: "blur"
            });
        }, true);
        window.addEventListener("focus", function( event ) {
            dealWithSelection();
        }, true);
    }
})();