// PageTransitions.js

function initializePageTransitions() {
    document.addEventListener("DOMContentLoaded", function() {
        document.body.classList.add("fade-in");

        document.querySelectorAll("a").forEach(link => {
            link.addEventListener("click", function(e) {
                const href = this.getAttribute("href");

                // Check if the href is not null and is a relative URL (internal link)
                if (href && !href.startsWith('http') && !href.startsWith('#')) {
                    e.preventDefault();
                    document.body.classList.add("fade-out");

                    setTimeout(() => {
                        window.location.href = href;
                    }, 150); // Duration adjusted to match 0.15s CSS transition
                }
            });
        });
    });
}

export { initializePageTransitions };
