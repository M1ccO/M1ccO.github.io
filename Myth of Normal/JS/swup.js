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

// Function definitions

function initializeButton() {
    // Your button initialization code here
}

function initializeSearchIndex() {
    // Your search initialization code here
}

