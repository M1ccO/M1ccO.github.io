// Functions.js


function initializeButton() {
    var backToTopBtn = document.getElementById("button");

    // Only proceed if the button element exists
    if (backToTopBtn) {
        // Function to update button appearance based on scroll position
        function updateButtonVisibility() {
            if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                backToTopBtn.style.opacity = 1;
                backToTopBtn.style.transform = 'translateY(0)'; // Slide into view
            } else {
                backToTopBtn.style.opacity = 0;
                backToTopBtn.style.transform = 'translateY(100%)'; // Slide out of view
            }
        }

        // Set up the scroll event listener
        window.addEventListener('scroll', updateButtonVisibility);

        // Update button visibility initially
        updateButtonVisibility();

        // Set up the click event for the button
        backToTopBtn.onclick = function() {
            var headingElement = document.querySelector(".heading"); // Adjust the selector as needed
            if (headingElement) {
                headingElement.scrollIntoView();
            }
        };
    }
}
