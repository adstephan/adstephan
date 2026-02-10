/**
 * BK Apartment Finder — frontend logic.
 */

(function () {
    "use strict";

    const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // Auto-reload listings every 5 min

    // DOM references
    const listingsContainer = document.getElementById("listingsContainer");
    const emptyState = document.getElementById("emptyState");
    const loadingIndicator = document.getElementById("loadingIndicator");
    const refreshBtn = document.getElementById("refreshBtn");
    const lastUpdatedEl = document.getElementById("lastUpdated");

    // Stats
    const totalListingsEl = document.getElementById("totalListings");
    const clCountEl = document.getElementById("clCount");
    const seCountEl = document.getElementById("seCount");
    const zilCountEl = document.getElementById("zilCount");

    // Filters
    const filterNeighborhood = document.getElementById("filterNeighborhood");
    const filterSource = document.getElementById("filterSource");
    const filterBedrooms = document.getElementById("filterBedrooms");
    const filterMaxPrice = document.getElementById("filterMaxPrice");
    const priceDisplay = document.getElementById("priceDisplay");
    const filterSort = document.getElementById("filterSort");

    let searchLinks = {};

    // --- Init ---
    async function init() {
        await Promise.all([fetchListings(), fetchStats(), fetchSearchLinks()]);
        attachEventListeners();
        setInterval(fetchListings, REFRESH_INTERVAL_MS);
    }

    function attachEventListeners() {
        filterNeighborhood.addEventListener("change", fetchListings);
        filterSource.addEventListener("change", fetchListings);
        filterBedrooms.addEventListener("change", fetchListings);
        filterSort.addEventListener("change", fetchListings);
        filterMaxPrice.addEventListener("input", function () {
            priceDisplay.textContent =
                "$" + parseInt(this.value).toLocaleString();
        });
        filterMaxPrice.addEventListener("change", fetchListings);

        refreshBtn.addEventListener("click", triggerRefresh);
    }

    // --- Data Fetching ---
    async function fetchListings() {
        showLoading(true);

        const params = new URLSearchParams();
        if (filterNeighborhood.value) params.set("neighborhood", filterNeighborhood.value);
        if (filterSource.value) params.set("source", filterSource.value);
        if (filterBedrooms.value) params.set("bedrooms", filterBedrooms.value);
        params.set("max_price", filterMaxPrice.value);

        const [sortBy, sortOrder] = filterSort.value.split("-");
        params.set("sort_by", sortBy);
        params.set("sort_order", sortOrder);

        try {
            const resp = await fetch("/api/listings?" + params.toString());
            const listings = await resp.json();
            renderListings(listings);
        } catch (err) {
            console.error("Failed to fetch listings:", err);
            listingsContainer.innerHTML =
                '<p class="loading">Failed to load listings. Try refreshing.</p>';
        }
    }

    async function fetchStats() {
        try {
            const resp = await fetch("/api/stats");
            const stats = await resp.json();
            totalListingsEl.textContent = stats.total_listings || 0;
            clCountEl.textContent = stats.by_source?.craigslist || 0;
            seCountEl.textContent = stats.by_source?.streeteasy || 0;
            zilCountEl.textContent = stats.by_source?.zillow || 0;

            if (stats.last_updated) {
                const d = new Date(stats.last_updated);
                lastUpdatedEl.textContent = "Updated: " + d.toLocaleString();
            } else {
                lastUpdatedEl.textContent = "No data yet";
            }
        } catch (err) {
            console.error("Failed to fetch stats:", err);
        }
    }

    async function fetchSearchLinks() {
        try {
            const resp = await fetch("/api/search-links");
            searchLinks = await resp.json();
            updateCraigslistLinks();
        } catch (err) {
            console.error("Failed to fetch search links:", err);
        }
    }

    function updateCraigslistLinks() {
        document.querySelectorAll('[data-source="craigslist"]').forEach(function (el) {
            const hood = el.getAttribute("data-hood");
            if (searchLinks.craigslist && searchLinks.craigslist[hood]) {
                el.href = searchLinks.craigslist[hood];
            }
        });
    }

    async function triggerRefresh() {
        refreshBtn.disabled = true;
        refreshBtn.textContent = "Refreshing...";

        try {
            await fetch("/api/refresh", { method: "POST" });
            // Wait a few seconds then reload data
            setTimeout(async function () {
                await Promise.all([fetchListings(), fetchStats()]);
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = "&#x21bb; Refresh";
            }, 5000);
        } catch (err) {
            console.error("Failed to trigger refresh:", err);
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = "&#x21bb; Refresh";
        }
    }

    // --- Rendering ---
    function showLoading(show) {
        if (loadingIndicator) {
            loadingIndicator.style.display = show ? "block" : "none";
        }
    }

    function renderListings(listings) {
        showLoading(false);
        listingsContainer.innerHTML = "";

        if (!listings || listings.length === 0) {
            emptyState.style.display = "block";
            return;
        }

        emptyState.style.display = "none";

        listings.forEach(function (listing) {
            listingsContainer.appendChild(createListingCard(listing));
        });
    }

    function createListingCard(listing) {
        const card = document.createElement("div");
        card.className = "listing-card";

        const priceStr = listing.price
            ? "$" + listing.price.toLocaleString() + "/mo"
            : "Price N/A";

        const bedroomStr = listing.bedrooms != null
            ? listing.bedrooms + " BR"
            : "";

        const dateStr = listing.first_seen
            ? timeAgo(new Date(listing.first_seen))
            : "";

        const imageHTML = listing.image_url
            ? '<img class="listing-image" src="' +
              escapeHTML(listing.image_url) +
              '" alt="Apartment photo" loading="lazy" onerror="this.outerHTML=\'<div class=listing-image-placeholder>&#x1f3e0;</div>\'">'
            : '<div class="listing-image-placeholder">&#x1f3e0;</div>';

        card.innerHTML =
            imageHTML +
            '<div class="listing-body">' +
                '<div class="listing-header">' +
                    '<span class="listing-price">' + escapeHTML(priceStr) + '</span>' +
                    '<span class="listing-source ' + escapeHTML(listing.source) + '">' +
                        escapeHTML(listing.source) +
                    '</span>' +
                '</div>' +
                '<div class="listing-title">' + escapeHTML(listing.title) + '</div>' +
                '<div class="listing-meta">' +
                    (listing.neighborhood
                        ? '<span class="listing-tag neighborhood">' + escapeHTML(listing.neighborhood) + '</span>'
                        : '') +
                    (bedroomStr
                        ? '<span class="listing-tag bedrooms">' + escapeHTML(bedroomStr) + '</span>'
                        : '') +
                '</div>' +
                '<div class="listing-footer">' +
                    '<span class="listing-date">' + escapeHTML(dateStr) + '</span>' +
                    '<a href="' + escapeHTML(listing.url) + '" target="_blank" rel="noopener" class="listing-link">' +
                        'View Listing &rarr;' +
                    '</a>' +
                '</div>' +
            '</div>';

        return card;
    }

    // --- Helpers ---
    function escapeHTML(str) {
        if (!str) return "";
        var div = document.createElement("div");
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    function timeAgo(date) {
        var seconds = Math.floor((new Date() - date) / 1000);
        if (seconds < 60) return "just now";
        var minutes = Math.floor(seconds / 60);
        if (minutes < 60) return minutes + "m ago";
        var hours = Math.floor(minutes / 60);
        if (hours < 24) return hours + "h ago";
        var days = Math.floor(hours / 24);
        if (days < 7) return days + "d ago";
        return date.toLocaleDateString();
    }

    // --- Start ---
    document.addEventListener("DOMContentLoaded", init);
})();
