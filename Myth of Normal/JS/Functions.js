// Functions.js

// Importing functions from other modules
import { scrollToTop } from './Scroll-To-Top.js';
import { initializeSearch } from './Search-Index.js';
import { displaySearchResults } from './Search-Results.js';

// Initialize 'Back to Top' button functionality
scrollToTop();

// Set up the search functionality on the index page
initializeSearch();

// Process and display search results
displaySearchResults();


