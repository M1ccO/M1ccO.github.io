// SearchResultsFunctions.js

window.onload = function() {
    var urlParams = new URLSearchParams(window.location.search);
    var query = urlParams.get('query');
    var type = urlParams.get('type');
    if (query && type) {
        var searchTerms = type === 'keywords' ? query.split(',').map(term => term.trim()) : [query];
        searchChapters(searchTerms, type === 'keywords');
    }
};

function searchChapters(searchTerms, isKeywordSearch) {
    // Fetch the content of chapter-1.html directly
    fetch('../Content/chapter-1.html')
        .then(response => response.text())
        .then(content => {
            if (isContentMatching(content, searchTerms, isKeywordSearch)) {
                // If content matches, display the result
                displayResults([{ chapter: 1, content: content }]);
            } else {
                // If no match, clear the results
                displayResults([]);
            }
        })
        .catch(error => {
            console.error('Error fetching chapter:', error);
            displayResults([]); // Display no results in case of error
        });
}



function isContentMatching(content, searchTerms, isKeywordSearch) {
    // Create a temporary DOM element to parse the HTML content
    var tempDiv = document.createElement('div');
    tempDiv.innerHTML = content;

    // Extract text from <p> and <li> tags
    var texts = [];
    tempDiv.querySelectorAll('p, li').forEach(element => {
        texts.push(element.textContent || element.innerText);
    });

    // Join all extracted texts into a single string
    var allText = texts.join(' ');

    // Check if the search terms are present in the text
    if (isKeywordSearch) {
        // For keyword search, check each term separately
        return searchTerms.every(term => allText.toLowerCase().includes(term.toLowerCase()));
    } else {
        // For sentence search, check the entire phrase
        return allText.toLowerCase().includes(searchTerms[0].toLowerCase());
    }
}


function displayResults(results) {
    var resultsContainer = document.getElementById('resultsContainer');
    resultsContainer.innerHTML = ''; // Clear previous results

    results.forEach(result => {
        var chapterElement = document.createElement('div');
        chapterElement.innerHTML = '<h3>Chapter ' + result.chapter + '</h3><p>' + result.content + '</p>';
        resultsContainer.appendChild(chapterElement);
    });
}
