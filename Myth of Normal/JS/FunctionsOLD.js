<script>
function scrollToElement(elementId) {
    var element = document.getElementById(elementId);
    if (element) {
        // Delay the execution of scrollIntoView
        setTimeout(() => {
            element.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100); // Delay of 100 milliseconds
    } else {
        console.error('Element not found:', elementId);
    }
}


document.addEventListener('DOMContentLoaded', (event) => {
    var backToTopBtn = document.getElementById("button");
    var inactivityTimeoutId; // Variable to store the inactivity timeout ID

    function hideButton() {
        backToTopBtn.style.opacity = 0;
        backToTopBtn.style.transform = 'translateY(100%)'; // Slide out of view
    }

    function resetInactivityTimer() {
        clearTimeout(inactivityTimeoutId); // Clear any existing inactivity timeout
        inactivityTimeoutId = setTimeout(hideButton, 3000); // Set a new inactivity timeout
    }

    setInterval(function() {
        if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
            backToTopBtn.style.opacity = 1;
            backToTopBtn.style.transform = 'translateY(0)'; // Slide into view
            resetInactivityTimer(); // Start or reset the inactivity timer
        } else {
            hideButton(); // Hide the button immediately when scrolled to the top
        }
    }, 100);

    // Add a scroll event listener to reset the inactivity timer
    window.addEventListener('scroll', resetInactivityTimer);

    backToTopBtn.onclick = function() {
        var headingElement = document.querySelector(".heading");
        if (headingElement) {
            headingElement.scrollIntoView({
                behavior: 'smooth'
            });
        }
    };
});





	
let viewState = 'chapterList';

// JavaScript function to toggle visibility of chapter summaries and the scrollable area
function toggleChapter(chapterId) {
    const allChapterSummaries = document.getElementsByClassName("summary");
    for (let i = 0; i < allChapterSummaries.length; i++) {
        const chapter = allChapterSummaries[i];
        if (chapter.id === chapterId) {
            chapter.style.display = "block";
        } else {
            chapter.style.display = "none";
        }
    }

    const scrollableArea = document.querySelector(".scrollable-area");
    scrollableArea.style.display = "none"; // Hide the scrollable area when a chapter summary is displayed.
    
    // Hide the search bar when a chapter summary is displayed
    const searchBarContainer = document.getElementById("searchContainer");
    searchBarContainer.classList.remove("active");
    searchBarContainer.classList.add("closed");
}

// JavaScript function to toggle visibility of individual chapter summary and show the scrollable area
function toggleSummary(chapterId) {
    const chapter = document.getElementById(chapterId);
    chapter.style.display = chapter.style.display === "none" ? "block" : "none";

    const scrollableArea = document.querySelector(".scrollable-area");
    scrollableArea.style.display = "block"; // Show the scrollable area when a chapter summary is toggled.
    
    // Show the search bar when a chapter summary is toggled off
    const searchBarContainer = document.getElementById("searchContainer");
    searchBarContainer.classList.add("active");
    searchBarContainer.classList.remove("closed");
}


// Existing code for opening and closing behavior of the search bar
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





// Transition animation for toggling between Chapter List and Chapter Summaries
function toggleChapter(chapterId) {
    const chapter = document.getElementById(chapterId);
    const chapterList = document.querySelector('.scrollable-area');

    // Move chapterList to the right
    chapterList.style.opacity = 0;
    chapterList.style.transform = 'translateX(100%)';

    setTimeout(() => {
        chapterList.style.display = 'none';

        // Start chapter off-screen to the left
        chapter.style.display = 'grid';
        chapter.style.opacity = 0;
        chapter.style.transform = 'translateX(-100%)';  // Initial state, off to the left
        
        // Fade-in and slide-in effect for the chapter summary
        setTimeout(() => {
            chapter.style.opacity = 1;
            chapter.style.transform = 'translateX(0)';
        }, 50);  
    }, 300);  
}

// Transition animation for hiding Chapter Summaries and showing Chapter List
function toggleSummary(chapterId) {
    const chapter = document.getElementById(chapterId);
    const chapterList = document.querySelector('.scrollable-area');

    // Hide the chapter summary with a fade-out and slide-out effect to the left
    chapter.style.opacity = 0;
    chapter.style.transform = 'translateX(-100%)';

    setTimeout(() => {
        chapter.style.display = 'none';

        chapterList.style.display = 'block';
        chapterList.style.opacity = 0;  
        chapterList.style.transform = 'translateX(100%)';  // Initial state, off to the right

        // Fade-in and slide-in effect for the chapter list
        setTimeout(() => {
            chapterList.style.opacity = 1;
            chapterList.style.transform = 'translateX(0)';
        }, 50);  
    }, 300);  
}






// Function to search through summaries
function searchSummaries() {
    // Get the user's input from the search bar
    let input = document.getElementById("search-input").value.toLowerCase();
    let keywords = input.split(',').map(k => k.trim());  // Split the input by comma and trim each keyword


    // Get all the chapter-summary elements
    let summaries = document.getElementsByClassName("summary");
    let hasSummaryIds = Array.from(summaries).map(summary => summary.id);

    let chapters = document.querySelectorAll('li a');
    for(let chapter of chapters) {
        let onclickAttribute = chapter.getAttribute('onclick');
        if(onclickAttribute) {
            let chapterId = onclickAttribute.replace('toggleChapter(\'', '').replace('\')', '');

            if (hasSummaryIds.includes(chapterId)) {
                let summaryContent = document.getElementById(chapterId).innerText.toLowerCase();
                
                // Check if all keywords match
                let hasAllKeywords = keywords.every(keyword => summaryContent.includes(keyword));

                if (hasAllKeywords || input === "") {
                    chapter.parentNode.style.display = "block";
                } else {
                    chapter.parentNode.style.display = "none";
                }
            } else {
                chapter.parentNode.style.display = "none";
            }
        }
    }
}


// Function to reset the visibility of all chapters
function resetChapterVisibility() {
    const chapters = document.querySelectorAll('.scrollable-area li');
    for (let chapter of chapters) {
        chapter.style.display = 'block';
    }
}

// Add an input event listener to the search input to detect when it's cleared
document.getElementById("search-input").addEventListener('input', function() {
    if (this.value === '') {
        resetChapterVisibility();
    }
});

// Event listener for real-time search as user types
document.getElementById("search-input").addEventListener("keyup", searchSummaries);

document.getElementById("search-input").addEventListener("keyup", function(event) {
    // Check for the "Enter" key
    if (event.keyCode === 13) {
        event.preventDefault();  // Prevent any default behavior (like form submission)

        const keyword = document.getElementById('search-input').value;
        
        // If the search results are already visible, use the update transition
        if (document.getElementById('searchResults').style.display === 'block') {
            updateSearchResults(() => {
                displaySearchResults(keyword);  // Display the updated search results
            });
        } else {
            // Otherwise, use the original transition function
            showSearchResults();
            displaySearchResults(keyword);
        }

        // Set the searchContainer to active
        document.getElementById("searchContainer").classList.add('active');
    } else {
        // If it's not the "Enter" key, continue with the real-time search
        searchSummaries();
    }
});



const searchInput = document.getElementById('search-input');

searchInput.addEventListener('keydown', function(e) {
    if (e.keyCode === 13 || e.key === 'Enter') {
        e.preventDefault(); // Prevent the default action (like form submission)

        // Execute your search logic (same as what you have for the search button)
        const keyword = searchInput.value;

        // If the search results are already visible, use the update transition
        if (document.getElementById('searchResults').style.display === 'block') {
            updateSearchResults(() => {
                displaySearchResults(keyword);  // Display the updated search results
            });
        } else {
            // Otherwise, use the original transition function
            showSearchResults();
            displaySearchResults(keyword);
        }

        // Set the searchContainer to active
        document.getElementById("searchContainer").classList.add('active');

        // If on a mobile device, blur the input to close the keyboard
        if (window.innerWidth < 768) {
            searchInput.blur();
        }
    }
});




// Event listener for ESC button to close the searchbar
searchBar.addEventListener('input', function() {
    escPressCount = 0;
});

let escPressCount = 0;  // Counter to keep track of the number of ESC key presses

document.addEventListener("keydown", function(event) {
    const summaries = document.querySelectorAll('.chapter-summary');
    const openSummary = Array.from(summaries).find(summary => summary.style.display !== 'none');
    const searchInput = document.querySelector('#search-input');

    if (event.key === "Escape") {
        if (openSummary) {
            // If a CHAPTER SUMMARY is open, use the ESC key to hide the summary.
            const summaryId = openSummary.getAttribute('id');
            toggleSummary(summaryId);
            escPressCount = 0;  // Reset the counter
        } else {
            if (window.innerWidth < 768) {
                if (escPressCount === 0) {
                    searchInput.focus();  // Refocus on the search bar
                } else if (escPressCount === 1) {
                    searchInput.value = '';  // Clear the search bar
                } else if (escPressCount === 2) {
                    hideSearchResults();
                    document.getElementById("searchContainer").classList.remove('active');
                    searchInput.blur();  // Remove focus
                    escPressCount = -1;  // Reset to -1 so it will become 0 after incrementing
                }
            } else {
                if (escPressCount === 0) {
                    searchInput.value = '';  // Clear the search bar
                } else if (escPressCount === 1) {
                    hideSearchResults();
                    document.getElementById("searchContainer").classList.remove('active');
                    searchInput.blur();  // Remove focus
                    escPressCount = -1;  // Reset to -1 so it will become 0 after incrementing
                }
            }
            escPressCount++;
        }
    }
});






// Add event listener to the entire document
document.addEventListener('click', function(event) {
    const searchContainer = document.getElementById("searchContainer");
    const searchInput = document.getElementById("search-input");
    
    // Check if the click was outside the searchContainer
    if (!searchContainer.contains(event.target)) {
        // Clear the search bar
        searchInput.value = '';
        resetChapterVisibility();

        // Close the search bar (or any other action you want to achieve)
        // Depending on your CSS, you might have a class to toggle its visibility or appearance
        searchContainer.classList.remove('active');  // Assuming 'active' is the class that makes the search bar appear active
    }
});






// Helper function to get all chapter names from the index page
function getAllChapterNames() {
    const chapterLinks = document.querySelectorAll('.scrollable-area a');
    const chapterNames = [];
    
    chapterLinks.forEach(link => {
        // Extract only the chapter name (without "Chapter X - ")
        const chapterName = link.innerText.split('-')[1].trim();
        chapterNames.push(chapterName);
    });

    return chapterNames;
}

// Search for sentences through the chapter summaries and show them in the place of chapter list
function extractSentences(summaryElement, input) {
    let keywords = [];

    // If the input contains commas, split by comma. Otherwise, treat the whole input as a single keyword (or sentence).
    if (input.includes(',')) {
        keywords = input.split(",").map(k => k.trim().toLowerCase());
    } else {
        keywords = [input.toLowerCase()];
    }

    // Set to store unique sentences
    let uniqueSentences = new Set();

    const relevantNodes = Array.from(summaryElement.querySelectorAll('p, ul, td, ol'));

    keywords.forEach(keyword => {
        relevantNodes.forEach(node => {
            const nodeText = node.innerText || "";
            const regex = new RegExp(`([^\.!?]*${keyword}[^\.!?]*[\.!?])`, 'ig');
            const matches = nodeText.match(regex);
            if (matches) {
                matches.forEach(sentence => {
                    uniqueSentences.add(sentence);
                });
            }
        });
    });

    // Convert set back to array
    return [...uniqueSentences];
}

function displaySearchResults(keywords) {
    const resultsContainer = document.getElementById('resultsContainer');
    resultsContainer.innerHTML = '';  // Clear previous results

    // Split the keywords by comma and trim each keyword
    keywords = keywords.split(",").map(k => k.trim().toLowerCase());

    const summaries = document.querySelectorAll('.chapter-summary');
    summaries.forEach(summary => {
        const chapterText = summary.innerText.toLowerCase();

        // Check if all keywords are present in the chapter
        if (keywords.every(keyword => chapterText.includes(keyword))) {
            const chapterDiv = document.createElement('div');
            const chapterTitle = summary.querySelector('h2').innerText;
            const chapterHeading = document.createElement('h3');
            chapterHeading.innerText = chapterTitle;
            chapterDiv.appendChild(chapterHeading);

            const sentencesList = document.createElement('ul');

            // For each keyword, extract sentences containing that keyword
            keywords.forEach(keyword => {
                const sentences = extractSentences(summary, keyword);
                sentences.forEach(sentence => {
                    const highlighted = sentence.replace(new RegExp(`(${keyword})`, 'ig'), '<span class="highlight">$1</span>');
                    const listItem = document.createElement('li');
                    listItem.innerHTML = highlighted;
                    sentencesList.appendChild(listItem);
                });
            });

            chapterDiv.appendChild(sentencesList);
            resultsContainer.appendChild(chapterDiv);
        }
    });

    showSearchResults();  // Show the results area
}






document.querySelector('.search-btn').addEventListener('click', function() {
    const keyword = document.getElementById('search-input').value;

    // If the search results are already visible, use the update transition
    if (document.getElementById('searchResults').style.display === 'block') {
        updateSearchResults(() => {
            displaySearchResults(keyword);  // Display the updated search results
        });
    } else {
        // Otherwise, use the original transition function
        showSearchResults();
        displaySearchResults(keyword);
    }

    // Set the searchContainer to active
    document.getElementById("searchContainer").classList.add('active');

    // Blur the input to close the keyboard
    document.getElementById('search-input').blur();
});




// Event delegation for the 'backToChapters' button
document.body.addEventListener('click', function(event) {
    if (event.target.id === 'backToChapters') {
        console.log("Back to Chapter list button clicked");
        
        // Use the transition function to hide the search results and show the chapter list
        hideSearchResults();

        // Remove the active class from searchContainer
        document.getElementById("searchContainer").classList.remove('active');
    }
});





// Transition animation for showing the Search Results and hiding Chapter List/Chapter Summaries
function showSearchResults() {
    const searchResults = document.getElementById('searchResults');
    const chapterList = document.querySelector('.scrollable-area');

    // Check if the search results are already displayed
    if (searchResults.style.display === 'grid') {
        // If they are, simply return to avoid the transition
        return;
    }

    chapterList.style.opacity = 0;
    chapterList.style.transform = 'translateX(-100%)';

    // Listen for the end of the chapterList's transition
    chapterList.addEventListener('transitionend', function transitionEndHandler() {
        chapterList.removeEventListener('transitionend', transitionEndHandler);  // Remove the event listener

        chapterList.style.display = 'none';

        searchResults.style.display = 'grid';
        searchResults.style.opacity = 0;
        searchResults.style.transform = 'translateX(100%)';

        setTimeout(() => {
            searchResults.style.opacity = 1;
            searchResults.style.transform = 'translateX(0)';
        }, 50);
    });
}




// Transition animation for hiding Search Results and showing Chapter List
function hideSearchResults() {
    const searchResults = document.getElementById('searchResults');
    const chapterList = document.querySelector('.scrollable-area');
    
    searchResults.style.opacity = 0;
    searchResults.style.transform = 'translateX(100%)';

    setTimeout(() => {
        searchResults.style.display = 'none';

        chapterList.style.display = 'block';
        chapterList.style.opacity = 0;
        chapterList.style.transform = 'translateX(-100%)';

        setTimeout(() => {
            chapterList.style.opacity = 1;
            chapterList.style.transform = 'translateX(0)';
        }, 50);
    }, 300);
}


function updateSearchResults(callback) {
    const searchResults = document.getElementById('searchResults');
    
    // Reset any transform property to ensure there's no slide effect
    searchResults.style.transform = 'none';

    // Fade out the current search results
    searchResults.style.opacity = 0;
    
    setTimeout(() => {
        // After the fade-out, call the provided callback (which will update the content)
        callback();

        // Reset any transform again before fading in
        searchResults.style.transform = 'none';

        // Fade in the updated search results
        searchResults.style.opacity = 1;
    }, 300); // Assuming a 300ms duration, adjust as needed
}


document.getElementById('searchForm').addEventListener('submit', function(e) {
    e.preventDefault(); // Prevent the default form submission behavior

    const keyword = document.getElementById('search-input').value;

    // If the search results are already visible, use the update transition
    if (document.getElementById('searchResults').style.display === 'block') {
        updateSearchResults(() => {
            displaySearchResults(keyword);  // Display the updated search results
        });
    } else {
        // Otherwise, use the original transition function
        showSearchResults();
        displaySearchResults(keyword);
    }

    // Set the searchContainer to active
    document.getElementById("searchContainer").classList.add('active');

    // Blur the input to close the keyboard
    document.getElementById('search-input').blur();
});


</script>