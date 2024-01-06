// Scroll-Top-Top.js


function scrollToChapter() {
    document.addEventListener('DOMContentLoaded', () => {
        var backToTopBtn = document.getElementById("button");

        backToTopBtn.onclick = () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
            // Hide the button after clicking
            backToTopBtn.style.opacity = 0;
            backToTopBtn.style.transform = 'translateY(100%)'; // Slide out of view
        };

        window.addEventListener('scroll', () => {
            if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                backToTopBtn.style.opacity = 1;
                backToTopBtn.style.transform = 'translateY(0)'; // Slide into view
            } else {
                backToTopBtn.style.opacity = 0;
                backToTopBtn.style.transform = 'translateY(100%)'; // Slide out of view
            }
        });
    });
}

export { scrollToChapter };

