// IndexFunctions.js

const searchBar = document.querySelector('#searchContainer input');
const searchContainer = document.querySelector('#searchContainer');
const searchButton = document.querySelector('#searchContainer .search-btn');

// Open search bar on focus
searchBar.addEventListener('focus', function() {
    searchContainer.classList.remove('closed');
    searchButton.disabled = false;
});

// Close search bar when it loses focus and no search query is entered
searchBar.addEventListener('blur', function() {
    if (!searchBar.value.trim()) {
        searchContainer.classList.add('closed');
        searchButton.disabled = true;
    }
});

// Event listener for the search button click
searchButton.addEventListener('click', function() {
    var searchQuery = searchBar.value;
    if (searchQuery) {
        performSearch(searchQuery);
    }
});

// Perform the search and redirect to results page
function performSearch(query) {
    var isKeywordSearch = query.includes(',');
    var searchType = isKeywordSearch ? 'keywords' : 'sentence';
    redirectToSearchResults(query, searchType);
}

// Redirect to search-results.html with query and type as URL parameters
function redirectToSearchResults(query, type) {
    window.location.href = 'Content/search-results.html?query=' + encodeURIComponent(query) + '&type=' + type;
}

// Function to filter chapters based on search input
function filterChapters(input) {
    const chapters = document.querySelectorAll('.chapter-link'); // Adjust the selector as needed
    const searchTerms = input.split(',').map(term => term.trim().toLowerCase());
    let promises = [];

    chapters.forEach(chapter => {
        let chapterFile = chapter.getAttribute('href'); // Assuming this gets the correct file path
        let promise = fetch(chapterFile)
            .then(response => response.text())
            .then(content => {
                return { chapter: chapter, isMatch: searchTerms.some(term => content.toLowerCase().includes(term)) };
            })
            .catch(error => console.error('Error fetching chapter:', error));

        promises.push(promise);
    });

    Promise.all(promises).then(results => {
        results.forEach(result => {
            result.chapter.style.display = result.isMatch ? "block" : "none";
        });
    });
}

// Modify the event listener for the search input
document.getElementById("search-input").addEventListener("keyup", function(event) {
    if (event.key === ',') {
        const searchQuery = this.value;
        filterChapters(searchQuery);
    }
});
