function addSharedHeading() {
    const headingHtml = `
        <div class="heading">
            <h1>The Myth Of Normal<span>GABOR MATÉ</span></h1>
        </div>`;

    document.body.insertAdjacentHTML('afterbegin', headingHtml);
}

// Call the function to add the heading when the page loads
window.onload = addSharedHeading;
