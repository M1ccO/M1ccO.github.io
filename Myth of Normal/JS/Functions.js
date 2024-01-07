// Functions.js

// Importing functions from other modules
import { scrollToChapter } from './Scroll-To-Top.js';
import { initializeSearch } from './Search-Index.js';
import { displaySearchResults } from './Search-Results.js';
import { initializePageTransitions } from './PageTransitions.js';

// Initialize 'Back to Top' button functionality
scrollToChapter();

// Set up the search functionality on the index page
initializeSearch();

// Process and display search results
displaySearchResults();

// Initialize page transitions
initializePageTransitions();
