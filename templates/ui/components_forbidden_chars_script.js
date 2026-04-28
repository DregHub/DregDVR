// Filter forbidden characters
const forbiddenChars = new Set([{FORBIDDEN_CHARS_ARRAY}]);
inputs.forEach(input => {
    input.addEventListener('input', function(event) {
        let originalValue = this.value;
        this.value = Array.from(originalValue)
            .filter(char => !forbiddenChars.has(char))
            .join('');
    }); 
});
