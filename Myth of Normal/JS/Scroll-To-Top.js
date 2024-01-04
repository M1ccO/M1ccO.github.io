// Scroll-To-Top.js

function scrollToTop() {
    document.addEventListener('DOMContentLoaded', (event) => {
        var backToTopBtn = document.getElementById("button");

        setInterval(function() {
            if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                backToTopBtn.style.opacity = 1;
                backToTopBtn.style.transform = 'translateY(0)'; // Slide into view
            } else {
                backToTopBtn.style.opacity = 0;
                backToTopBtn.style.transform = 'translateY(100%)'; // Slide out of view
            }
        }, 100);

        backToTopBtn.onclick = function() {
            // Scroll the page to the top immediately
            window.scrollTo(0, 0);
        };
    });
}

// Export the function
export { scrollToTop };

