// Functions.js


function scrollToElement(elementId) {
    var element = document.getElementById(elementId);
    if (element) {
        var topPosition = element.getBoundingClientRect().top + window.pageYOffset;

        // Scroll to the element
        window.scrollTo({ top: topPosition, behavior: 'auto' });
    }
}




