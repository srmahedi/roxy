if (typeof roxyExtUtils === "undefined")
    roxyExtUtils = {};

roxyExtUtils.findYoutubeChannelVideosUrl = function() {
    if (!roxyExtUtils.isYoutubeDomain()) {
        return '';
    }

    var pathname = (new URL(window.location.href)).pathname;

    if (pathname === '/watch') {
        var videosUrl = '';
        var r_select = document.querySelector('#top-row > ytd-video-owner-renderer > a');
        if (typeof r_select === 'object' && r_select !== null) {
            var relative_url = r_select.getAttribute('href');
            if (relative_url) {
                videosUrl = 'https://www.youtube.com' + relative_url + '/videos';
            }
        }
        return videosUrl;
    }

    var dirs = pathname.split('/');

    if ((dirs[1] === 'user' || dirs[1] === 'channel' || dirs[1] === 'c')) {
        if (typeof dirs[2] === 'undefined' || dirs[2].length === 0) {
            return '';
        } else {
            videosUrl = 'https://www.youtube.com' + '/' + dirs[1] + '/' + dirs[2] + '/videos';
            return videosUrl;
        }
    } else {
        return '';
    }
};

roxyExtUtils.youtubeChannelInfoLoading = function() {
    if (!roxyExtUtils.isYoutubeDomain()) {
        return false;
    }
    if (roxyExtUtils.findYoutubeChannelVideosUrl().length) {
        return false;
    }
    var pathname = (new URL(window.location.href)).pathname;
    if (pathname === '/watch') {
        var r_select = document.querySelector('#top-row > #video-owner');
        if (typeof r_select === 'object' && r_select !== null) {
            return true;
        }
    }
    return false;
};

roxyExtUtils.isYoutubeDomain = function() {
    var hostname = (new URL(window.location.href)).hostname;
    return hostname.endsWith('youtube.com');
};

roxyExtUtils.findYoutubePlaylist = function() {
    if (!roxyExtUtils.isYoutubeDomain()) {
        return '';
    }
    var url = window.location.href;
    if (url.length < 10) {
        return '';
    }
    var urlObj = new URL(url);
    var hostname = urlObj.hostname;
    var protocol = urlObj.protocol;

    if (protocol !== 'https:') {
        return false;
    }
    if (hostname.endsWith('youtube.com')) {
        var reg = /^.*((youtu.be\/)|(v\/)|(\/u\/\w\/)|(embed\/)|(watch\?))\??v?=?([^#&?]*).*list=([^#&?]*).*/;
        var m = url.match(reg);
        if (!m || m.length < 9) {
            var reg2 = /^.*www.youtube.com\/playlist\?.*list=([^#&?]*).*/;
            var m2 = url.match(reg2);
            if (!m2 || m2.length < 2) {
                return '';
            } else {
                return url;
            }
        } else {
            return url;
        }
    }
    return false;
};