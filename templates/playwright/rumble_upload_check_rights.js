document.querySelectorAll('input[name="crights"]').forEach(cb => {
    cb.checked = true;
    cb.dispatchEvent(new Event('change', { bubbles: true }));
    cb.dispatchEvent(new Event('input', { bubbles: true }));
});