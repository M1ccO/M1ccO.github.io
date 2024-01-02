// IndexFunctions.js
 
const searchBar = document.querySelector('#searchContainer input');
const searchContainer = document.querySelector('#searchContainer');
const searchButton = document.querySelector('#searchContainer .search-btn');

searchBar.addEventListener('focus', function() {
    searchContainer.classList.remove('closed');
    searchButton.removeAttribute('disabled');  // Enable the button
});

searchBar.addEventListener('blur', function() {
    // Only disable the button and close the search bar if there's no value in the search bar
    if (!searchBar.value.trim()) {
        searchContainer.classList.add('closed');
        searchButton.setAttribute('disabled', '');  // Disable the button
    }
});


// Event listener for keyup to detect comma press and filter chapters
searchBar.addEventListener("keyup", function(event) {
    if (event.key === ',') {
        const searchQuery = this.value;
        filterChapters(searchQuery);
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

document.addEventListener('click', function(event) {
    const searchContainer = document.getElementById("searchContainer");
    const searchInput = document.getElementById("search-input");
    const searchButton = document.getElementById("searchContainer .search-btn");

    // Check if the click was outside the searchContainer
    if (!searchContainer.contains(event.target)) {
        // Mimic the first ESC press: Clear the search input
        searchInput.value = '';

        // Mimic the second ESC press: Remove focus from the search bar and revert to default form
        searchBar.blur();
        searchContainer.classList.add('closed');
        searchButton.disabled = true;
    }
});


let escPressCount = 0;

// Event listener for ESC key
document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") {
        escPressCount++;

        if (escPressCount === 1) {
            // First press: Clear the search input
            searchBar.value = '';
        } else if (escPressCount === 2) {
            // Second press: Remove focus from the search bar and revert to default form
            searchBar.blur();
            searchContainer.classList.add('closed'); // Assuming this class change handles reverting to default form
            searchButton.disabled = true; // Optionally disable the search button
            escPressCount = 0;  // Reset the counter
        }
    }
});

// Reset the ESC press counter when input is changed
searchBar.addEventListener('input', function() {
    escPressCount = 0;
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
