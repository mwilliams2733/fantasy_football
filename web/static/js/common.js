/** Make a table sortable by clicking column headers. */
function makeSortable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const headers = table.querySelectorAll("th[data-sort]");
    headers.forEach(header => {
        header.style.cursor = "pointer";
        header.addEventListener("click", () => {
            const col = header.dataset.sort;
            const tbody = table.querySelector("tbody");
            const rows = Array.from(tbody.querySelectorAll("tr"));
            const isNum = header.dataset.type === "number";
            const asc = header.dataset.dir !== "asc";
            rows.sort((a, b) => {
                const aVal = a.querySelector(`td[data-col="${col}"]`)?.textContent || "";
                const bVal = b.querySelector(`td[data-col="${col}"]`)?.textContent || "";
                if (isNum) return asc ? parseFloat(aVal) - parseFloat(bVal) : parseFloat(bVal) - parseFloat(aVal);
                return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            });
            header.dataset.dir = asc ? "asc" : "desc";
            // Update sort indicators
            headers.forEach(h => h.classList.remove("sort-asc", "sort-desc"));
            header.classList.add(asc ? "sort-asc" : "sort-desc");
            rows.forEach(row => tbody.appendChild(row));
        });
    });
}

/** Filter table rows by search text. */
function filterTable(tableId, searchText) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const rows = table.querySelectorAll("tbody tr");
    const lower = searchText.toLowerCase();
    rows.forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(lower) ? "" : "none";
    });
}

/** POST JSON to a route and return parsed response. */
async function postJSON(url, data) {
    const res = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data),
    });
    return res.json();
}

/** Show a loading spinner in a container. */
function showLoading(containerId) {
    const el = document.getElementById(containerId);
    if (el) el.innerHTML = '<div class="loading-spinner"></div>';
}

/** Toggle sidebar visibility on mobile. */
document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("sidebar");
    if (toggle && sidebar) {
        toggle.addEventListener("click", () => {
            sidebar.classList.toggle("open");
        });
    }
});
