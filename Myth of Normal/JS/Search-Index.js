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

// Event listener for ENTER key to execute search
searchBar.addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        event.preventDefault(); // Prevent default form submission
        performSearch(this.value); // Execute search based on current input
    }
});

// IndexFunctions.js

// ... [previous code remains the same]

let escPressCount = 0;  // Counter to keep track of the number of ESC key presses

// Event listener for ESC key with multifunctionality
document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") {
        escPressCount++;
        handleEscPress(escPressCount);
    }
});

function handleEscPress(pressCount) {
    switch(pressCount) {
        case 1:
            // First press: Clear the search input
            searchBar.value = '';
            break;
        case 2:
            // Second press: Close the search bar and hide search results
            searchContainer.classList.add('closed');
            searchButton.disabled = true;
            hideSearchResults();  // Assuming this function hides the search results
            break;
        case 3:
            // Third press: Reset the counter and remove focus (for mobile devices)
            if (window.innerWidth < 768) {
                searchBar.blur();
            }
            escPressCount = 0;  // Reset the counter
            break;
    }
}


