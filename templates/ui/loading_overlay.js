// Loading Overlay JavaScript Controller

(function() {
    'use strict';

    // Store reference to overlay elements
    let overlay = null;
    let statusText = null;

    // Initialize overlay elements
    function initOverlay() {
        if (!overlay) {
            overlay = document.getElementById('loading-overlay');
            statusText = document.getElementById('loading-status-text');
        }
        return overlay !== null && statusText !== null;
    }

    // Show loading overlay
    function showLoadingOverlay(message) {
        if (!initOverlay()) {
            console.error('Loading overlay elements not found');
            return;
        }

        // Update status message if provided
        if (message && statusText) {
            statusText.textContent = message;
        }

        // Show overlay
        overlay.classList.add('active');
    }

    // Hide loading overlay
    function hideLoadingOverlay() {
        if (!initOverlay()) {
            console.error('Loading overlay elements not found');
            return;
        }

        // Hide overlay
        overlay.classList.remove('active');
    }

    // Update status message while overlay is visible
    function updateLoadingStatus(message) {
        if (!initOverlay()) {
            console.error('Loading overlay elements not found');
            return;
        }

        if (statusText && message) {
            statusText.textContent = message;
        }
    }

    // Expose functions to global scope for Streamlit Python calls
    window.showLoadingOverlay = showLoadingOverlay;
    window.hideLoadingOverlay = hideLoadingOverlay;
    window.updateLoadingStatus = updateLoadingStatus;

    // Auto-initialize on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initOverlay);
    } else {
        initOverlay();
    }
})();