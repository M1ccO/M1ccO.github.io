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


// Event listener for keyup to detect comma press and filter chapters
searchBar.addEventListener("keyup", function(event) {
    if (event.key === ',') {
        const searchQuery = this.value;
        filterChapters(searchQuery);
    }
});

// Function to filter chapters based on search input
function filterChapters(query) {
    const keywords = query.split(',').map(k => k.trim().toLowerCase());
    const chapterLinks = document.querySelectorAll('.h3 a'); // Select all chapter links

    chapterLinks.forEach(link => {
        const chapterTitle = link.textContent.toLowerCase();
        const isMatch = keywords.some(keyword => chapterTitle.includes(keyword));

        if (isMatch || query.trim() === '') {
            link.closest('.h3').style.display = 'block'; // Show the chapter if it matches
        } else {
            link.closest('.h3').style.display = 'none'; // Hide the chapter if it does not match
        }
    });


// Event listener for ENTER key to execute search
searchBar.addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        event.preventDefault(); // Prevent default form submission
        const searchQuery = this.value;
        if (searchQuery) {
            performSearch(searchQuery); // Execute search based on current input
        }
    }
});

// Event listener for the search button click
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

// Redirect to search-results.html with query and type as URL parameters
function redirectToSearchResults(query, type) {
    window.location.href = 'Content/search-results.html?query=' + encodeURIComponent(query) + '&type=' + type;
}


