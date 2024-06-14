// Search-Results.js

function displaySearchResults() {
    window.onload = function() {
        var urlParams = new URLSearchParams(window.location.search);
        var query = urlParams.get('query');
        var type = urlParams.get('type');
        if (query && type) {
            var searchTerms = type === 'keywords' ? query.split(',').map(term => term.trim()) : [query];
            var totalChapters = 18; // Update this to the total number of chapters
            searchChapters(searchTerms, type === 'keywords', totalChapters);
        }
    };

    function searchChapters(searchTerms, isKeywordSearch, totalChapters) {
        let fetchPromises = [];

        for (let chapterNumber = 1; chapterNumber <= totalChapters; chapterNumber++) {
            let chapterFile = `../Content/chapter-${chapterNumber}.html`;
            let fetchPromise = fetch(chapterFile)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Chapter ${chapterNumber} not found`);
                    }
                    return response.text();
                })
                .then(content => {
                    return {
                        chapter: chapterNumber,
                        content: extractSentences(content, searchTerms, isKeywordSearch)
                    };
                })
                .catch(error => {
                    console.error(`Error fetching chapter ${chapterNumber}:`, error);
                    return null;
                });

            fetchPromises.push(fetchPromise);
        }

        Promise.all(fetchPromises).then(results => {
            let filteredResults = results.filter(result => result !== null);
            let combinedResults = filteredResults.reduce((acc, result) => {
                if (result.content.sentences.length > 0) {
                    acc.push({ chapter: result.chapter, title: result.content.title, content: result.content.sentences });
                }
                return acc;
            }, []);

            displayResults(combinedResults, searchTerms);
        });
    }

    function extractSentences(content, searchTerms, isKeywordSearch) {
        let uniqueSentences = new Set();
        var tempDiv = document.createElement('div');
        tempDiv.innerHTML = content;
        const chapterTitle = tempDiv.querySelector('h2')?.innerText || "Chapter Title Not Found";

        if (isKeywordSearch) {
            const allText = tempDiv.innerText || "";
            let allTermsPresent = searchTerms.every(term => new RegExp(term, 'i').test(allText));
            if (!allTermsPresent) {
                return { sentences: [], title: chapterTitle };
            }
        }

        const relevantNodes = Array.from(tempDiv.querySelectorAll('p, ul, td, ol'));
        searchTerms.forEach(term => {
            relevantNodes.forEach(node => {
                const nodeText = node.innerText || "";
                const regex = new RegExp(`([^\.!?]*${term}[^\.!?]*[\.!?])`, 'ig');
                const matches = nodeText.match(regex);
                if (matches) {
                    matches.forEach(sentence => uniqueSentences.add(sentence));
                }
            });
        });

        return { sentences: [...uniqueSentences], title: chapterTitle };
    }

    function displayResults(results, searchTerms) {
        var resultsContainer = document.getElementById('resultsContainer');
        resultsContainer.innerHTML = '';

        results.forEach(result => {
            var chapterElement = document.createElement('div');
            chapterElement.innerHTML = `<h3>${result.title}</h3>`;

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
