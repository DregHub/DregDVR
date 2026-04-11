() => {
    // Block video and audio loading
    const originalVideoLoad = HTMLVideoElement.prototype.load;
    HTMLVideoElement.prototype.load = function() {
        this.src = '';
        this.removeAttribute('src');
    };
    const originalAudioLoad = HTMLAudioElement.prototype.load;
    HTMLAudioElement.prototype.load = function() {
        this.src = '';
        this.removeAttribute('src');
    };
    Object.defineProperty(HTMLMediaElement.prototype, 'autoplay', {
        set: () => {},
        get: () => false
    });
    HTMLMediaElement.prototype.play = function() {
        return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function() {};
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
        set: () => {},
        get: () => ''
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'currentSrc', {
        get: () => ''
    });
    const originalAppendChild = Element.prototype.appendChild;
    Element.prototype.appendChild = function(node) {
        if (node.tagName === 'SOURCE' && (node.type?.includes('video') || node.type?.includes('audio'))) {
            node.src = '';
            node.removeAttribute('src');
        }
        return originalAppendChild.call(this, node);
    };
    const originalSetAttribute = Element.prototype.setAttribute;
    Element.prototype.setAttribute = function(name, value) {
        if ((this.tagName === 'VIDEO' || this.tagName === 'AUDIO' || this.tagName === 'SOURCE') && name === 'src') {
            return;
        }
        return originalSetAttribute.call(this, name, value);
    };
}