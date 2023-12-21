// Functions.js

document.addEventListener('DOMContentLoaded', function() {
    window.scrollToElement = function(elementId) {
        var element = document.getElementById(elementId);
        if (element) {
            element.scrollIntoView({ behavior: 'auto' });
        }
    };
});







