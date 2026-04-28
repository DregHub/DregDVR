/* Searchable Selectbox Script - Client-side filtering for selectbox options */
/* Lightweight, no external dependencies */

(function() {
  'use strict';

  // Find all search inputs
  const searchInputs = document.querySelectorAll('.selectbox-search-input');

  searchInputs.forEach((searchInput) => {
    const wrapper = searchInput.closest('.enhanced-selectbox-wrapper');
    if (!wrapper) return;

    const optionsContainer = wrapper.querySelector('.selectbox-dropdown-container');
    const selectbox = optionsContainer?.querySelector('[role="listbox"], select');
    
    if (!selectbox) return;

    // Store original options
    const originalOptions = Array.from(selectbox.querySelectorAll('option, [role="option"]'));
    let currentFilter = '';

    /**
     * Filter options based on search term
     * @param {string} searchTerm - The search query
     */
    function filterOptions(searchTerm) {
      currentFilter = searchTerm.toLowerCase().trim();
      let visibleCount = 0;

      originalOptions.forEach((option) => {
        const text = option.textContent.toLowerCase();
        const isMatch = text.includes(currentFilter) || currentFilter === '';
        
        if (isMatch) {
          option.style.display = '';
          visibleCount++;
        } else {
          option.style.display = 'none';
        }
      });

      // Update search state
      updateSearchState(visibleCount, originalOptions.length);
    }

    /**
     * Update search state message
     * @param {number} visibleCount - Number of visible options
     * @param {number} totalCount - Total number of options
     */
    function updateSearchState(visibleCount, totalCount) {
      let stateEl = wrapper.querySelector('.selectbox-search-state');
      
      if (visibleCount === 0 && currentFilter) {
        if (!stateEl) {
          stateEl = document.createElement('div');
          stateEl.className = 'selectbox-search-state selectbox-no-results';
          stateEl.setAttribute('role', 'status');
          stateEl.textContent = `No options match "${currentFilter}"`;
          optionsContainer?.appendChild(stateEl);
        } else {
          stateEl.textContent = `No options match "${currentFilter}"`;
          stateEl.classList.add('selectbox-no-results');
        }
      } else if (stateEl) {
        stateEl.remove();
      }
    }

    /**
     * Handle search input changes
     */
    function onSearchInput(event) {
      filterOptions(event.target.value);
    }

    /**
     * Handle Enter key to select first visible option
     */
    function onSearchKeyDown(event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        const firstVisible = originalOptions.find(opt => opt.style.display !== 'none');
        if (firstVisible) {
          firstVisible.click();
          searchInput.value = '';
          filterOptions('');
        }
      } else if (event.key === 'Escape') {
        searchInput.value = '';
        filterOptions('');
      }
    }

    /**
     * Clear search on selection
     */
    function onOptionSelect() {
      searchInput.value = '';
      filterOptions('');
    }

    // Attach event listeners
    searchInput.addEventListener('input', onSearchInput);
    searchInput.addEventListener('keydown', onSearchKeyDown);

    // Listen for option selection
    originalOptions.forEach((option) => {
      option.addEventListener('click', onOptionSelect);
    });

    // Handle selectbox change to clear search
    selectbox?.addEventListener('change', onOptionSelect);

    // Initial state
    filterOptions('');

    // Expose filter function for external use
    wrapper.filterOptions = filterOptions;
  });
})();
