// Scroll-Top-Top.js


function scrollToChapter() {
    document.addEventListener('DOMContentLoaded', (event) => {
        var backToTopBtn = document.getElementById("button");
        var firstH3 = document.querySelector('h3');
        var buttonClicked = false; // Flag to track button click

        function smoothScrollToChapter() {
            if (firstH3) {
                firstH3.scrollIntoView({ behavior: 'smooth', block: 'start' });
                hideButton();
            }
        }

        function hideButton() {
            backToTopBtn.style.opacity = 0;
            backToTopBtn.style.transform = 'translateY(100%)';
            buttonClicked = true; // Set flag to true after hiding the button
        }

        backToTopBtn.onclick = smoothScrollToChapter;
        backToTopBtn.addEventListener('touchend', smoothScrollToChapter);

        setInterval(function() {
            if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                if (!buttonClicked) {
                    backToTopBtn.style.opacity = 1;
                    backToTopBtn.style.transform = 'translateY(0)'; // Slide into view
                }
            } else {
                buttonClicked = false; // Reset flag when at top of page
                backToTopBtn.style.opacity = 0;
                backToTopBtn.style.transform = 'translateY(100%)'; // Slide out of view
            }
        }, 100);
    });
}

export { scrollToChapter };


