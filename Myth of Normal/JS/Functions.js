// Functions.js

// Combined Search and Results Script

// Function to initialize search index functionality
function initializeSearchIndex() {
    const searchBar = document.querySelector('#searchContainer input');
    const searchContainer = document.querySelector('#searchContainer');
    const searchButton = document.querySelector('#searchContainer .search-btn');

    if (searchBar && searchContainer && searchButton) {
        setupEventListeners(searchBar, searchContainer, searchButton);
    }

    // Check if on search results page and display results
    displaySearchResults();
}

// Function to set up event listeners for search functionality
function setupEventListeners(searchBar, searchContainer, searchButton) {
    searchBar.addEventListener('focus', function() {
        searchContainer.classList.remove('closed');
        searchButton.removeAttribute('disabled');
    });

    searchBar.addEventListener('blur', function() {
        if (!searchBar.value.trim()) {
            searchContainer.classList.add('closed');
            searchButton.setAttribute('disabled', '');
        }
    });

    searchBar.addEventListener("keyup", function(event) {
        if (event.key === ',') {
            // Replace 'filterChapters' with your actual filtering function
            const searchQuery = this.value;
            filterChapters(searchQuery);
        }
    });

    searchBar.addEventListener("keydown", function(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            const searchQuery = this.value;
            if (searchQuery) {
                performSearch(searchQuery);
            }
        }
    });

    document.addEventListener('click', function(event) {
        if (!searchContainer.contains(event.target)) {
            searchBar.value = '';
            searchBar.blur();
            searchContainer.classList.add('closed');
            searchButton.disabled = true;
        }
    });

    let escPressCount = 0;
    document.addEventListener("keydown", function(event) {
        if (event.key === "Escape") {
            escPressCount++;
            if (escPressCount === 1) {
                searchBar.value = '';
            } else if (escPressCount === 2) {
                searchBar.blur();
                searchContainer.classList.add('closed');
                searchButton.disabled = true;
                escPressCount = 0;
            }
        }
    });

    searchBar.addEventListener('input', function() {
        escPressCount = 0;
    });

    searchButton.addEventListener('click', function() {
        const searchQuery = searchBar.value;
        if (searchQuery) {
            performSearch(searchQuery);
        }
    });

    // Perform the search and redirect to results page
    function performSearch(query) {
        const isKeywordSearch = query.includes(',');
        const searchType = isKeywordSearch ? 'keywords' : 'sentence';
        redirectToSearchResults(query, searchType);
    }

    function redirectToSearchResults(query, type) {
        const searchResultsUrl = `Content/search-results.html?query=${encodeURIComponent(query)}&type=${type}`;
        swup.loadPage({ url: searchResultsUrl, method: 'GET' });
    }
}

// Fetch and display search results
function displaySearchResults() {
    const urlParams = new URLSearchParams(window.location.search);
    const query = urlParams.get('query');
    const type = urlParams.get('type');

    if (query && type) {
        const searchTerms = type === 'keywords' ? query.split(',').map(term => term.trim()) : [query];
        searchChapters(searchTerms, type === 'keywords');
    }

    function searchChapters(searchTerms, isKeywordSearch) {
        // Assuming 'chapter-1.html' is a placeholder for actual content URLs
        fetch('../Content/chapter-1.html')
            .then(response => response.text())
            .then(content => {
                const matchingSentences = extractSentences(content, searchTerms, isKeywordSearch);
                displayResults(matchingSentences);
            })
            .catch(error => {
                console.error('Error fetching chapter:', error);
            });
    }

    function extractSentences(content, searchTerms, isKeywordSearch) {
        const uniqueSentences = new Set();
        const tempDiv = document.createElement('div');
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

    function displayResults(sentences) {
        const resultsContainer = document.getElementById('resultsContainer');
        resultsContainer.innerHTML = '';

        sentences.forEach(sentence => {
            const sentenceElement = document.createElement('p');
            sentenceElement.textContent = sentence;
            resultsContainer.appendChild(sentenceElement);
        });
    }
}

// Call the function to initialize the search index
initializeSearchIndex();







