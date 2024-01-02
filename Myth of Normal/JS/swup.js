// swup.js

const swup = new Swup({
    linkSelector: 'a:not([href^="#"])'
});

swup.on('contentReplaced', () => {
    initializeSearchIndex();  // Reinitialize search functionalities
});

// Also call it on initial page load
initializeSearchIndex();






