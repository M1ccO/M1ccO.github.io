// Scroll-To-Top.js

function scrollToChapter() {
    document.addEventListener('DOMContentLoaded', (event) => {
        var backToTopBtn = document.getElementById("button");

        // Find the first h3 element on the page
        var firstH3 = document.querySelector('h3');

        // Function to scroll to the first h3 element
        function smoothScrollToChapter() {
            if (firstH3) {
                firstH3.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }

        // Set the click event for the button
        backToTopBtn.onclick = smoothScrollToChapter;
        // Add touchend event listener for mobile devices
        backToTopBtn.addEventListener('touchend', smoothScrollToChapter);

        // Check the scroll position at regular intervals
        setInterval(function() {
            if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                backToTopBtn.classList.add('show');
            } else {
                backToTopBtn.classList.remove('show');
            }
        }, 100);
    });
}

// Export the scrollToChapter function
export { scrollToChapter };

