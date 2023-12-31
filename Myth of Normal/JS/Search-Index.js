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

// Function to filter chapters based on search input (same as before)
// ...

// Modify the event listener for the search input for comma press
document.getElementById("search-input").addEventListener("keyup", function(event) {
    if (event.key === ',') {
        const searchQuery = this.value;
        filterChapters(searchQuery);
    }
});

// Event listener for ENTER key to execute search
searchBar.addEventListener("keyup", function(event) {
    if (event.key === "Enter") {
        event.preventDefault(); // Prevent default form submission
        performSearch(this.value); // Execute search based on current input
    }
});

// Event listener for ESC key to close and clear the search bar
document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") {
        searchBar.value = ''; // Clear the search input
        searchContainer.classList.add('closed'); // Close the search bar
        searchButton.disabled = true; // Disable the search button
    }
});
