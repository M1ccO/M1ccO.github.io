// swup.js

const swup = new Swup({
    linkSelector: 'a:not([href^="#"])'
});

swup.on('contentReplaced', () => {
    initializeSearchIndex();  // Reinitialize search functionalities
    initializeButton();       // Reinitialize button functionalities
});

// Also call them on initial page load
initializeSearchIndex();
initializeButton();

