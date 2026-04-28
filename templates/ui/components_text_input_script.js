// Prevent Enter key and hide InputInstructions
const inputs = window.parent.document.querySelectorAll('input');
inputs.forEach(input => {
    input.addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
        }
    });
});

// Remove InputInstructions divs that appear dynamically
const removeInputInstructions = () => {
    const instructionDivs = window.parent.document.querySelectorAll('div[data-testid="InputInstructions"]');
    instructionDivs.forEach(div => {
        div.remove();
    });
};

// Remove on page load
removeInputInstructions();

// Watch for new InputInstructions divs being added
const observer = new MutationObserver(removeInputInstructions);
observer.observe(window.parent.document.body, {
    childList: true,
    subtree: true
});
