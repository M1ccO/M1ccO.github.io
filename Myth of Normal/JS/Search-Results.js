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
    var results = [];
    var chaptersToSearch = 33; // Assuming you have 33 chapters
    for (var i = 1; i <= chaptersToSearch; i++) {
        fetch('../Content/chapter-' + i + '.html') // Adjust the path if necessary
            .then(response => response.text())
            .then(content => {
                if (isContentMatching(content, searchTerms, isKeywordSearch)) {
                    results.push({ chapter: i, content: content });
                }
                if (i === chaptersToSearch) {
                    displayResults(results);
                }
            })
            .catch(error => console.error('Error fetching chapter:', error));
    }
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
