// Functions.js

function fetchChapterContent(chapterUrl) {
    return fetch(chapterUrl)
        .then(response => response.text())
        .then(data => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(data, 'text/html');
            return doc; // Returns the parsed HTML document
        });
}
async function searchChapters(query) {
    const chapterUrls = ["Content/chapter-1.html", "Content/chapter-2.html", ...]; // List all chapter URLs
    const searchResults = [];

    for (const url of chapterUrls) {
        const chapterContent = await fetchChapterContent(url);
        // Perform search in chapterContent
        if (/* condition to check if query is found in chapterContent */) {
            searchResults.push({ url, /* other relevant data */ });
        }
    }

    displaySearchResults(searchResults);
}
function displaySearchResults(results) {
    const resultsContainer = document.getElementById('resultsContainer');
    resultsContainer.innerHTML = ''; // Clear previous results
    results.forEach(result => {
        const resultElement = document.createElement('a');
        resultElement.href = result.url;
        resultElement.textContent = "Relevant info about the result";
        resultsContainer.appendChild(resultElement);
    });
}
document.getElementById("search-input").addEventListener("keyup", function(event) {
    if (event.key === "Enter") {
        searchChapters(this.value);
    }
});













