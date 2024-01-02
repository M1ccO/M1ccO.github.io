// swup.js

// In swup.js
const swup = new Swup({
  linkSelector: 'a:not([href^="#"])' // Handles all links except in-page anchors
});


swup.on('contentReplaced', function() {
    if (typeof initializeSearch === 'function') {
        initializeSearch();
    }
});

// Also call it on initial page load
initializeSearch();





