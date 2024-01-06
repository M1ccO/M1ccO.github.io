// Scroll-Top-Top.js



function scrollToChapter() {
    document.addEventListener('DOMContentLoaded', (event) => {
        var backToTopBtn = document.getElementById("button");
        var firstH3 = document.querySelector('h3');

        function smoothScrollToChapter() {
            if (firstH3) {
                firstH3.scrollIntoView({ behavior: 'smooth', block: 'start' });
                // Hide the button after scrolling
                backToTopBtn.style.opacity = 0;
                backToTopBtn.style.transform = 'translateY(100%)';
            }
        }

        backToTopBtn.onclick = smoothScrollToChapter;
        backToTopBtn.addEventListener('touchend', smoothScrollToChapter);

        setInterval(function() {
            if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                backToTopBtn.style.opacity = 1;
                backToTopBtn.style.transform = 'translateY(0)'; // Slide into view
            } else {
                backToTopBtn.style.opacity = 0;
                backToTopBtn.style.transform = 'translateY(100%)'; // Slide out of view
            }
        }, 100);
    });
}

export { scrollToChapter };
