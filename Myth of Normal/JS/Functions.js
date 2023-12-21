// Functions.js

document.addEventListener('DOMContentLoaded', (event) => {
    // You can safely call scrollToElement or any DOM manipulation functions here
    scrollToElement('someElementId');

    // More DOM manipulations or event listener attachments can go here
});

function scrollToElement(elementId) {
    var element = document.getElementById(elementId);
    if (element) {
        var topPosition = element.getBoundingClientRect().top + window.pageYOffset;
        window.scrollTo({ top: topPosition, behavior: 'auto' });
    }
}






