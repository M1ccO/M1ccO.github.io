// Scroll-To-Top.js

function scrollToTop() {
    // Function to scroll to the top of the page
    function smoothScrollToTop() {
        if (document.body.scrollTop !== 0 || document.documentElement.scrollTop !== 0) {
            window.scrollBy(0, -50);
            setTimeout(smoothScrollToTop, 10);
        }
    }

    // Add event listener once the DOM is fully loaded
    document.addEventListener('DOMContentLoaded', (event) => {
        var backToTopBtn = document.getElementById("button");

        // Set the click event for the button
        backToTopBtn.onclick = smoothScrollToTop;

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

// Export the scrollToTop function
export { scrollToTop };


