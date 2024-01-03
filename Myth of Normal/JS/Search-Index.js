// Search-Index.js

function initializeSearchIndex() {
    const searchBar = document.querySelector('#searchContainer input');
    const searchContainer = document.querySelector('#searchContainer');
    const searchButton = document.querySelector('#searchContainer .search-btn');

    if (searchBar && searchContainer && searchButton) {
        searchBar.addEventListener('focus', function() {
            searchContainer.classList.remove('closed');
            searchButton.removeAttribute('disabled');  // Enable the button
        });

        searchBar.addEventListener('blur', function() {
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
            if (!searchContainer.contains(event.target)) {
                searchBar.value = '';
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
                    searchBar.value = '';
                } else if (escPressCount === 2) {
                    searchBar.blur();
                    searchContainer.classList.add('closed');
                    searchButton.disabled = true;
                    escPressCount = 0;
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
            const searchResultsUrl = 'Content/search-results.html?query=' + encodeURIComponent(query) + '&type=' + type;
            swup.loadPage({
            url: searchResultsUrl,
            method: 'GET'
            });
            }
        }
    }
