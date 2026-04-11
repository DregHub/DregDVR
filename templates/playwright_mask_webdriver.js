// === COMPREHENSIVE CLOUDFLARE & BOT DETECTION BYPASS ===
Object.defineProperty(navigator, 'webdriver', {get: () => false, configurable: true});
if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) window.chrome.runtime = {};
window.chrome.loadTimes = function() {};
window.chrome.csi = function() {};
Object.defineProperty(navigator, 'plugins', {get: () => [
    {name: 'Chrome PDF Plugin', description: 'Portable Document Format'},
    {name: 'Chrome PDF Viewer', description: ''},
    {name: 'Native Client Executable', description: ''},
    {name: 'Shockwave Flash', description: 'Shockwave Flash 32.0 r0'}
], configurable: true});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en'], configurable: true});
Object.defineProperty(navigator, 'language', {get: () => 'en-US', configurable: true});
Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.', configurable: true});
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({state: Notification.permission}) :
    originalQuery(parameters)
);
Object.defineProperty(screen, 'availTop', {value: 0});
Object.defineProperty(screen, 'availLeft', {value: 0});
Object.defineProperty(screen, 'availHeight', {value: 1040});
Object.defineProperty(screen, 'availWidth', {value: 1280});
Object.defineProperty(screen, 'colorDepth', {value: 24});
Object.defineProperty(screen, 'pixelDepth', {value: 24});
Object.defineProperty(navigator, 'platform', {get: () => 'Win32', configurable: true});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 4, configurable: true});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8, configurable: true});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 10, configurable: true});
Object.defineProperty(navigator, 'ontouchstart', {value: null, configurable: true});
if (!navigator.connection) {
    Object.defineProperty(navigator, 'connection', {
        value: {downlink: 10, effectiveType: '4g', rtt: 50, saveData: false},
        configurable: true
    });
}
Object.defineProperty(navigator, 'credentials', {get: () => ({get: async () => null, store: async (credential) => {}, create: async (options) => null, preventSilentAccess: async () => {}}), configurable: true});
Object.defineProperty(navigator, 'mimeTypes', {get: () => [
    {type: 'application/pdf', description: 'PDF Plugin', enabledPlugin: {name: 'Chrome PDF Plugin'}},
    {type: 'application/x-google-chrome-extension', description: '', enabledPlugin: {name: 'Chrome PDF Plugin'}},
    {type: 'application/futuresplash', description: 'Shockwave Flash', enabledPlugin: {name: 'Shockwave Flash'}}
], configurable: true});
const originalSetItem = Storage.prototype.setItem;
const originalGetItem = Storage.prototype.getItem;
Storage.prototype.setItem = function(key, value) {
    if (key.includes('WebDriver') || key.includes('bot')) {
        return;
    }
    return originalSetItem.apply(this, arguments);
};
window.__HEADLESS__ = false;
Object.defineProperty(window, '__HEADLESS__', {get: () => false, configurable: true});
const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function() {
    if (this.width === 280 && this.height === 60) {
        const context = this.getContext('2d');
        context.font = '16px Arial';
        context.fillStyle = '#000000';
        context.fillText('CANVAS', 50, 40);
    }
    return originalToDataURL.apply(this, arguments);
};
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Google Inc. (ANGLE)';
    if (parameter === 37446) return 'Google Inc. (ANGLE)';
    if (parameter === 7938) return 'WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)';
    return getParameter.apply(this, arguments);
};
const originalFetch = window.fetch;
window.fetch = function(...args) {
    let url = args[0];
    if (typeof url === 'string' && url.includes('rumble.com')) {
        if (!args[1]) args[1] = {};
        if (!args[1].headers) args[1].headers = {};
        args[1].headers['Accept-Language'] = 'en-US,en;q=0.9';
        args[1].headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8';
        args[1].headers['Sec-Fetch-Dest'] = 'document';
        args[1].headers['Sec-Fetch-Mode'] = 'navigate';
        args[1].headers['Sec-Fetch-Site'] = 'none';
    }
    return originalFetch.apply(this, args);
};
const originalNow = Performance.prototype.now;
Performance.prototype.now = function() {
    return originalNow.apply(this) + Math.random() * 0.1;
};