// WikiLens Frontend Application Logic (Polished UI/UX)

let currentPage = 1;
let currentQuery = '';
let currentTotalPages = 1;
let debounceTimer = null;
let currentAcIndex = -1;

const searchSection = document.getElementById('searchSection');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const clearBtn = document.getElementById('clearBtn');
const kbdHint = document.getElementById('kbdHint');
const acDropdown = document.getElementById('autocompleteDropdown');
const resultsContainer = document.getElementById('resultsContainer');
const resultsMeta = document.getElementById('resultsMeta');
const resultsCount = document.getElementById('resultsCount');
const searchLatency = document.getElementById('searchLatency');
const didYouMeanBar = document.getElementById('didYouMeanBar');
const didYouMeanBtn = document.getElementById('didYouMeanBtn');
const fuzzyToggle = document.getElementById('fuzzyToggle');
const paginationBar = document.getElementById('paginationBar');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');
const pageIndicator = document.getElementById('pageIndicator');
const logoBtn = document.getElementById('logoBtn');

// Modal Elements
const articleModal = document.getElementById('articleModal');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const modalArticleName = document.getElementById('modalArticleName');
const modalArticleDesc = document.getElementById('modalArticleDesc');
const modalImgWrap = document.getElementById('modalImgWrap');
const modalImg = document.getElementById('modalImg');
const modalFactsList = document.getElementById('modalFactsList');
const modalAbstract = document.getElementById('modalAbstract');
const modalDateMod = document.getElementById('modalDateMod');
const modalChars = document.getElementById('modalChars');
const modalWikiLink = document.getElementById('modalWikiLink');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  fetchCorpusStats();
  setupEventListeners();

  // Check URL query parameters
  const urlParams = new URLSearchParams(window.location.search);
  const q = urlParams.get('q');
  if (q) {
    searchInput.value = q;
    clearBtn.classList.remove('hidden');
    if (kbdHint) kbdHint.style.display = 'none';
    executeSearch(q, 1);
  }
});

function setupEventListeners() {
  // Global Keyboard Shortcut: '/' to focus search input
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== searchInput && articleModal.classList.contains('hidden')) {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
  });

  // Search Button
  searchBtn.addEventListener('click', triggerSearch);

  // Input Keypress Handling (Arrows, Enter, Escape)
  searchInput.addEventListener('keydown', (e) => {
    const items = acDropdown.querySelectorAll('.ac-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (items.length > 0) {
        currentAcIndex = (currentAcIndex + 1) % items.length;
        updateAcActive(items);
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (items.length > 0) {
        currentAcIndex = (currentAcIndex - 1 + items.length) % items.length;
        updateAcActive(items);
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (currentAcIndex >= 0 && items[currentAcIndex]) {
        items[currentAcIndex].click();
      } else {
        triggerSearch();
      }
    } else if (e.key === 'Escape') {
      hideAutocomplete();
    }
  });

  // Autocomplete debounced input
  searchInput.addEventListener('input', () => {
    const val = searchInput.value.trim();
    if (val.length > 0) {
      clearBtn.classList.remove('hidden');
      if (kbdHint) kbdHint.style.display = 'none';
    } else {
      clearBtn.classList.add('hidden');
      if (kbdHint) kbdHint.style.display = 'block';
      hideAutocomplete();
      return;
    }

    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      fetchAutocomplete(val);
    }, 150);
  });

  // Clear Button
  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearBtn.classList.add('hidden');
    if (kbdHint) kbdHint.style.display = 'block';
    hideAutocomplete();
    searchInput.focus();
  });

  // Hide autocomplete on click outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-box-wrapper')) {
      hideAutocomplete();
    }
  });

  // Quick Chips
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const q = chip.getAttribute('data-query');
      searchInput.value = q;
      clearBtn.classList.remove('hidden');
      if (kbdHint) kbdHint.style.display = 'none';
      triggerSearch();
    });
  });

  // Did You Mean Click
  didYouMeanBtn.addEventListener('click', () => {
    const corrected = didYouMeanBtn.textContent;
    searchInput.value = corrected;
    executeSearch(corrected, 1);
  });

  // Pagination Buttons
  prevPageBtn.addEventListener('click', () => {
    if (currentPage > 1) {
      executeSearch(currentQuery, currentPage - 1);
    }
  });

  nextPageBtn.addEventListener('click', () => {
    if (currentPage < currentTotalPages) {
      executeSearch(currentQuery, currentPage + 1);
    }
  });

  // Reset to Home on Logo Click
  logoBtn.addEventListener('click', resetToHome);
  logoBtn.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      resetToHome();
    }
  });

  // Modal Close Listeners
  modalCloseBtn.addEventListener('click', closeModal);
  articleModal.addEventListener('click', (e) => {
    if (e.target === articleModal) {
      closeModal();
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !articleModal.classList.contains('hidden')) {
      closeModal();
    }
  });
}

function resetToHome() {
  searchInput.value = '';
  clearBtn.classList.add('hidden');
  if (kbdHint) kbdHint.style.display = 'block';
  resultsContainer.innerHTML = '';
  resultsMeta.classList.add('hidden');
  didYouMeanBar.classList.add('hidden');
  paginationBar.classList.add('hidden');
  searchSection.classList.remove('compact-hero');
  window.history.pushState({}, '', '/');
}

function updateAcActive(items) {
  items.forEach((item, idx) => {
    if (idx === currentAcIndex) {
      item.classList.add('active');
      searchInput.value = item.getAttribute('data-name');
    } else {
      item.classList.remove('active');
    }
  });
}

async function fetchAutocomplete(prefix) {
  if (prefix.length < 2) {
    hideAutocomplete();
    return;
  }
  try {
    const res = await fetch(`/api/autocomplete?q=${encodeURIComponent(prefix)}&limit=6`);
    const suggestions = await res.json();
    renderAutocomplete(suggestions, prefix);
  } catch (err) {
    console.error('Autocomplete fetch error:', err);
  }
}

function renderAutocomplete(items, queryPrefix) {
  if (!items || items.length === 0) {
    hideAutocomplete();
    return;
  }

  currentAcIndex = -1;
  acDropdown.innerHTML = '';

  items.forEach(item => {
    const div = document.createElement('div');
    div.className = 'ac-item';
    div.setAttribute('data-name', item.name);

    const imgHtml = item.image_url 
      ? `<img class="ac-thumb" src="${escapeHtml(item.image_url)}" alt="" loading="lazy">` 
      : `<div class="ac-thumb-placeholder">📄</div>`;

    // Highlight prefix match inside title
    const regex = new RegExp(`(${escapeRegex(queryPrefix)})`, 'gi');
    const highlightedName = escapeHtml(item.name).replace(regex, '<span class="ac-match">$1</span>');

    div.innerHTML = `
      ${imgHtml}
      <div class="ac-text">
        <div class="ac-title">${highlightedName}</div>
        <div class="ac-desc">${escapeHtml(item.description || 'Wikipedia article')}</div>
      </div>
    `;

    div.addEventListener('click', () => {
      searchInput.value = item.name;
      hideAutocomplete();
      triggerSearch();
    });

    acDropdown.appendChild(div);
  });

  // Footer Tip
  const tipDiv = document.createElement('div');
  tipDiv.className = 'ac-footer-tip';
  tipDiv.innerHTML = `<span>Use <b>↑</b> <b>↓</b> to navigate</span> <span>Press <b>↵</b> to search</span>`;
  acDropdown.appendChild(tipDiv);

  acDropdown.classList.remove('hidden');
}

function hideAutocomplete() {
  acDropdown.classList.add('hidden');
  currentAcIndex = -1;
}

function triggerSearch() {
  hideAutocomplete();
  const q = searchInput.value.trim();
  if (!q) return;
  executeSearch(q, 1);
}

function showSkeletonLoading() {
  // Collapse hero smoothly to give space to results
  searchSection.classList.add('compact-hero');

  // Render 3 skeleton cards
  let skeletonHtml = '';
  for (let i = 0; i < 3; i++) {
    skeletonHtml += `
      <div class="skeleton-card">
        <div class="skeleton-line skeleton-title"></div>
        <div class="skeleton-line skeleton-subtitle"></div>
        <div class="skeleton-line skeleton-text-1"></div>
        <div class="skeleton-line skeleton-text-2"></div>
        <div class="skeleton-line skeleton-text-3"></div>
      </div>
    `;
  }
  resultsContainer.innerHTML = skeletonHtml;
  resultsMeta.classList.add('hidden');
  didYouMeanBar.classList.add('hidden');
  paginationBar.classList.add('hidden');
}

async function executeSearch(query, page = 1) {
  currentQuery = query;
  currentPage = page;

  // Update URL history without reload
  window.history.pushState({}, '', `/?q=${encodeURIComponent(query)}`);

  // Show shimmer skeleton loaders
  showSkeletonLoading();

  const startTime = performance.now();
  const enableFuzzy = fuzzyToggle.checked;

  try {
    const url = `/api/search?q=${encodeURIComponent(query)}&page=${page}&limit=10&fuzzy=${enableFuzzy}`;
    const res = await fetch(url);
    const data = await res.json();
    const duration = Math.round(performance.now() - startTime);

    renderResults(data, duration);
  } catch (err) {
    resultsContainer.innerHTML = `
      <div class="no-results">
        <div class="no-results-icon">⚠️</div>
        <h3>Search Error</h3>
        <p>${escapeHtml(err.message || 'Unable to connect to search service.')}</p>
      </div>
    `;
  }
}

function renderResults(data, durationMs) {
  // Update Meta Stats
  resultsCount.textContent = `${data.total_results.toLocaleString()} result${data.total_results === 1 ? '' : 's'}`;
  searchLatency.textContent = `${durationMs}ms`;
  resultsMeta.classList.remove('hidden');

  // Did You Mean Banner
  if (data.did_you_mean && data.did_you_mean.toLowerCase() !== data.query.toLowerCase()) {
    didYouMeanBtn.textContent = data.did_you_mean;
    didYouMeanBar.classList.remove('hidden');
  } else {
    didYouMeanBar.classList.add('hidden');
  }

  // Handle 0 results
  if (!data.results || data.results.length === 0) {
    resultsContainer.innerHTML = `
      <div class="no-results">
        <div class="no-results-icon">🔍</div>
        <h3>No matching articles found</h3>
        <p>We couldn't find any results matching "<b>${escapeHtml(data.query)}</b>". Try checking spelling, using more general keywords, or enabling fuzzy matching.</p>
        <div class="no-results-tips">
          <button class="chip" onclick="searchFor('Chubasco')">🌪️ Chubasco</button>
          <button class="chip" onclick="searchFor('mountain pass')">⛰️ Mountain Pass</button>
          <button class="chip" onclick="searchFor('footballer')">🏉 Footballer</button>
        </div>
      </div>
    `;
    paginationBar.classList.add('hidden');
    return;
  }

  // Render Result Cards with Staggered Entrance
  resultsContainer.innerHTML = '';
  data.results.forEach((r, idx) => {
    const card = document.createElement('div');
    card.className = 'result-card';
    card.style.setProperty('--stagger-index', idx);

    // Infobox Preview Pills
    let factsHtml = '';
    if (r.infobox_facts && Object.keys(r.infobox_facts).length > 0) {
      const entries = Object.entries(r.infobox_facts).slice(0, 3);
      factsHtml = `
        <div class="facts-preview">
          ${entries.map(([k, v]) => `
            <span class="fact-pill"><strong>${escapeHtml(k)}:</strong> ${escapeHtml(String(v))}</span>
          `).join('')}
        </div>
      `;
    }

    // Thumbnail Preview
    const thumbHtml = r.image_url 
      ? `
        <div class="card-thumb-wrap">
          <img class="card-thumb" src="${escapeHtml(r.image_url)}" alt="${escapeHtml(r.name)}" loading="lazy" onerror="this.parentElement.style.display='none'">
        </div>
      `
      : '';

    // Badges
    const sectionBadge = r.matched_in === 'sections' 
      ? `<span class="badge badge-section" title="Query matched deep section text">In Section</span>` 
      : '';

    card.innerHTML = `
      <div class="card-top">
        <div class="card-headline">
          <a href="#" class="card-title" data-id="${r.id}">${escapeHtml(r.name)}</a>
          ${r.description ? `<div class="card-desc">${escapeHtml(r.description)}</div>` : ''}
        </div>
        <div class="card-badges">
          ${sectionBadge}
          <span class="badge badge-score" title="BM25 Relevance Score">BM25 ${r.bm25_score}</span>
        </div>
      </div>

      <div class="card-main">
        ${thumbHtml}
        <div class="card-body">
          <div class="card-snippet">${r.snippet}</div>
          ${factsHtml}
        </div>
      </div>

      <div class="card-footer">
        <span class="card-date">Updated: ${escapeHtml(r.date_modified ? r.date_modified.split(' ')[0] : 'N/A')}</span>
        <div class="footer-actions">
          <button class="btn-sm btn-facts" data-id="${r.id}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
            </svg>
            Quick View
          </button>
          <a href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer" class="btn-sm">
            Wikipedia
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
          </a>
        </div>
      </div>
    `;

    // Click handler for title and Quick View
    card.querySelector('.card-title').addEventListener('click', (e) => {
      e.preventDefault();
      openArticleModal(r.id);
    });

    card.querySelector('.btn-facts').addEventListener('click', () => {
      openArticleModal(r.id);
    });

    resultsContainer.appendChild(card);
  });

  // Pagination Logic
  currentTotalPages = data.total_pages;
  if (currentTotalPages > 1) {
    paginationBar.classList.remove('hidden');
    pageIndicator.textContent = `Page ${data.page} of ${currentTotalPages}`;
    prevPageBtn.disabled = data.page <= 1;
    nextPageBtn.disabled = data.page >= currentTotalPages;
  } else {
    paginationBar.classList.add('hidden');
  }

  // Smooth scroll back to top if paginated
  if (currentPage > 1) {
    window.scrollTo({ top: resultsMeta.offsetTop - 80, behavior: 'smooth' });
  }
}

// Global helper for suggestions click
window.searchFor = function(text) {
  searchInput.value = text;
  clearBtn.classList.remove('hidden');
  if (kbdHint) kbdHint.style.display = 'none';
  triggerSearch();
};

async function openArticleModal(articleId) {
  try {
    const res = await fetch(`/api/article/${articleId}`);
    if (!res.ok) throw new Error('Article not found');
    const art = await res.json();

    modalArticleName.textContent = art.name;
    modalArticleDesc.textContent = art.description || 'Wikipedia Article';
    modalAbstract.textContent = art.abstract || 'No abstract text available.';
    modalDateMod.textContent = art.date_modified || 'N/A';
    modalChars.textContent = art.char_count ? `${art.char_count.toLocaleString()} chars` : 'N/A';
    modalWikiLink.href = art.url;

    if (art.image_url) {
      modalImg.src = art.image_url;
      modalImgWrap.classList.remove('hidden');
    } else {
      modalImgWrap.classList.add('hidden');
    }

    modalFactsList.innerHTML = '';
    const facts = art.infobox_facts;
    if (facts && Object.keys(facts).length > 0) {
      Object.entries(facts).forEach(([k, v]) => {
        const row = document.createElement('div');
        row.className = 'modal-fact-row';
        row.innerHTML = `
          <span class="modal-fact-key">${escapeHtml(k)}</span>
          <span class="modal-fact-val">${escapeHtml(String(v))}</span>
        `;
        modalFactsList.appendChild(row);
      });
    } else {
      modalFactsList.innerHTML = `<span style="color: var(--text-muted); font-size: 0.8rem; font-style: italic;">No infobox facts recorded for this article.</span>`;
    }

    articleModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  } catch (err) {
    alert('Unable to load article details.');
  }
}

function closeModal() {
  articleModal.classList.add('hidden');
  document.body.style.overflow = '';
}

async function fetchCorpusStats() {
  try {
    const res = await fetch('/api/stats');
    const stats = await res.json();
    const statsElem = document.getElementById('corpusStats');
    if (statsElem && stats.total_articles) {
      statsElem.innerHTML = `
        <span class="stat-badge"><span class="pulse-dot"></span> ${stats.total_articles.toLocaleString()} Articles</span>
        <span class="stat-badge subtle">${stats.articles_with_images.toLocaleString()} with Images</span>
        <span class="stat-badge subtle">${stats.articles_with_infobox.toLocaleString()} with Facts</span>
      `;
    }
  } catch (err) {
    console.error('Stats error:', err);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeRegex(string) {
  return string.replace(/[/\-\\^$*+?.()|[\]{}]/g, '\\$&');
}
