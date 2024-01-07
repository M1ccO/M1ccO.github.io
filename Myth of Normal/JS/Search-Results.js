// Search-Results.js


function displaySearchResults(results) {
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
    fetch('../Content/chapter-1.html')
        .then(response => response.text())
        .then(content => {
            let matchingSentences = extractSentences(content, searchTerms, isKeywordSearch);
            if (matchingSentences.length > 0) {
                displayResults([{ chapter: 1, content: matchingSentences }], searchTerms);
            } else {
                displayResults([], searchTerms);
            }
        })
        .catch(error => {
            console.error('Error fetching chapter:', error);
            displayResults([], searchTerms);
        });
}



function extractSentences(content, searchTerms, isKeywordSearch) {
    let uniqueSentences = new Set();
    var tempDiv = document.createElement('div');
    tempDiv.innerHTML = content;
    const relevantNodes = Array.from(tempDiv.querySelectorAll('p, ul, td, ol'));

    searchTerms.forEach(term => {
        relevantNodes.forEach(node => {
            const nodeText = node.innerText || "";
            const regex = isKeywordSearch ? 
                new RegExp(`([^\.!?]*${term}[^\.!?]*[\.!?])`, 'ig') :
                new RegExp(`([^\.!?]*${searchTerms[0]}[^\.!?]*[\.!?])`, 'ig');
            const matches = nodeText.match(regex);
            if (matches) {
                matches.forEach(sentence => uniqueSentences.add(sentence));
            }
        });
    });

    return [...uniqueSentences];
}




function displayResults(results, searchTerms) {
    var resultsContainer = document.getElementById('resultsContainer');
    resultsContainer.innerHTML = '';

    results.forEach(result => {
        var chapterElement = document.createElement('div');
        chapterElement.innerHTML = `<h3>Chapter ${result.chapter}</h3>`;

        result.content.forEach(sentence => {
            var sentenceElement = document.createElement('p');
            let highlightedSentence = sentence;
            searchTerms.forEach(term => {
                const highlightSpan = `<span class="highlight">${term}</span>`;
                highlightedSentence = highlightedSentence.replace(new RegExp(term, 'gi'), highlightSpan);
            });
            sentenceElement.innerHTML = highlightedSentence;
            chapterElement.appendChild(sentenceElement);
        });

        resultsContainer.appendChild(chapterElement);
    });
  }
}


export { displaySearchResults };
