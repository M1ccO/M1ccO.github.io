// Scroll-To-Top.js

function scrollToChapter() {
    document.addEventListener('DOMContentLoaded', () => {
        var backToTopBtn = document.getElementById("button");
        var buttonClicked = false; // Flag to track if the button was clicked

        backToTopBtn.onclick = () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
            hideButton();

            // Change the button's background color on click
            backToTopBtn.style.backgroundColor = '#555';

            // Revert the color back after a short delay
            setTimeout(() => {
                backToTopBtn.style.backgroundColor = '#ff0000'; // Original color
            }, 300);
        };

        function hideButton() {
            backToTopBtn.style.opacity = 0;
            backToTopBtn.style.transform = 'translateY(100%)'; // Hide button
            buttonClicked = true; // Set flag to indicate button was clicked
        }

        window.addEventListener('scroll', () => {
            if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                if (!buttonClicked) { // Only show button if it wasn't clicked
                    backToTopBtn.style.opacity = 1;
                    backToTopBtn.style.transform = 'translateY(0)'; // Slide into view
                }
            } else {
                buttonClicked = false; // Reset flag when at the top
                backToTopBtn.style.opacity = 0;
                backToTopBtn.style.transform = 'translateY(100%)'; // Slide out of view
            }
        });
    });
}

export { scrollToChapter };
