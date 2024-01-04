// Scroll-To-Top.js

function scrollToTop() {
    document.addEventListener('DOMContentLoaded', (event) => {
        var backToTopBtn = document.getElementById("button");

        setInterval(function() {
            if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                backToTopBtn.classList.add('show');
            } else {
                backToTopBtn.classList.remove('show');
            }
        }, 100);

        backToTopBtn.onclick = function() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        };
    });
}

// Export the function
export { scrollToTop };

