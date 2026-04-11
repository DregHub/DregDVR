(selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    // Clone and remove all <span> children
    const clone = el.cloneNode(true);
    clone.querySelectorAll('span').forEach(s => s.remove());
    return clone.textContent.trim();
}