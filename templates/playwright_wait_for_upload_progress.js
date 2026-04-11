() => {
    const selector = '{selector}';
    const el = document.querySelector(selector);
    if (!el) return false;

    // Set up logging if not already done
    if (!window.widthLogInterval) {
        window.widthLogInterval = setInterval(() => {
            const width = el.style.width || window.getComputedStyle(el).getPropertyValue('width');
            const percentEl = document.querySelector('h2.num_percent');
            if (percentEl) {
                const percentText = percentEl.textContent.trim();
                console.log(`${percentText}`);
            }
        }, 20000);
    }

    const isComplete = el.style.width === '100%' ||
                       window.getComputedStyle(el).getPropertyValue('width') === '100%';
    if (isComplete) {
        clearInterval(window.widthLogInterval);
    }
    return isComplete;
}
