/* The app shell: one Tabulator grid re-pointed at each tab's columns, filters
 * evaluated in the browser from the specs the server rendered into the page,
 * and a sidebar tree whose counts come from /api/summary. */
(function () {
  "use strict";

  var specs = JSON.parse(document.getElementById("tab-specs").textContent);
  var tabsById = {};
  specs.forEach(function (tab) { tabsById[tab.id] = tab; });

  var pages = [];
  var external = [];
  var summary = null;
  var current = { tab: specs[0].id, filter: "all", search: "" };
  var loadedSource = null;

  var el = {
    strip: document.querySelector("[data-tabstrip]"),
    filter: document.querySelector("[data-filter]"),
    search: document.querySelector("[data-grid-search]"),
    count: document.querySelector("[data-grid-count]"),
    download: document.querySelector("[data-grid-download]"),
    grid: document.getElementById("grid"),
    issues: document.getElementById("issues-panel"),
    tree: document.querySelector("[data-tree]"),
  };

  // ------------------------------------------------------------ helpers
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fetchJson(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (!r.ok) { throw new Error(url + " -> " + r.status); }
      return r.json();
    });
  }

  function matches(row, f) {
    if (!f || !f.op) { return true; }
    var cell = row[f.column];
    switch (f.op) {
      case "eq": return cell === f.value;
      case "ne": return cell !== f.value;
      case "has": {
        var tokens = Array.isArray(cell) ? cell : String(cell || "").split(/\s+/);
        return tokens.indexOf(f.value) !== -1;
      }
      case "gt": return typeof cell === "number" && cell > f.value;
      case "truthy": return !!cell;
      case "falsy": return !cell;
      default: return true;
    }
  }

  function searchMatch(row, needle) {
    return Object.keys(row).some(function (key) {
      var value = row[key];
      return value !== null && value !== undefined && String(value).toLowerCase().indexOf(needle) !== -1;
    });
  }

  function filterSpec(tab, id) {
    for (var i = 0; i < tab.filters.length; i++) {
      if (tab.filters[i].id === id) { return tab.filters[i]; }
    }
    return tab.filters[0];
  }

  function sourceRows(tab) {
    return tab.source === "external" ? external : pages;
  }

  function countFor(tabId, filterId) {
    if (!summary || !summary.tabs[tabId]) { return null; }
    var n = summary.tabs[tabId][filterId];
    return n === undefined ? null : n;
  }

  // --------------------------------------------------------------- grid
  function pageLink(cell) {
    var url = cell.getValue();
    if (url === null || url === undefined || url === "") { return ""; }
    return '<a href="/page?url=' + encodeURIComponent(url) + '" data-url="' + escapeHtml(url) + '">' + escapeHtml(url) + "</a>";
  }

  function listCell(cell) {
    var value = cell.getValue();
    return Array.isArray(value) ? escapeHtml(value.join(", ")) : escapeHtml(value === null || value === undefined ? "" : value);
  }

  function column(name) {
    var spec = { title: name, field: name, headerFilter: "input", headerFilterLiveFilter: true };
    if (name === "url" || name === "final_url" || name === "found_on" || name === "canonical" || name === "first_found_on") {
      spec.width = 360;
    }
    if (name === "url" && current.tab !== "external") {
      spec.formatter = pageLink;
    } else {
      spec.formatter = listCell;
    }
    return spec;
  }

  var table = new Tabulator(el.grid, {
    index: "url",
    layout: "fitDataStretch",
    height: "100%",
    columns: [],
    data: [],
    placeholder: "No rows",
  });

  function showCount(rows) {
    el.count.textContent = rows.length + " rows";
    el.count.dataset.rows = String(rows.length);
  }
  table.on("dataFiltered", function (filters, rows) { showCount(rows); });

  function applyFilter() {
    var tab = tabsById[current.tab];
    var f = filterSpec(tab, current.filter);
    var needle = current.search;
    table.setFilter(function (row) {
      return matches(row, f) && (!needle || searchMatch(row, needle));
    });
  }

  // ---------------------------------------------------------------- tabs
  function selectTab(tabId, filterId) {
    var tab = tabsById[tabId] || specs[0];
    current.tab = tab.id;
    current.filter = filterSpec(tab, filterId || "all").id;
    Array.prototype.forEach.call(el.strip.querySelectorAll("[data-tab]"), function (button) {
      button.setAttribute("aria-selected", button.dataset.tab === tab.id ? "true" : "false");
    });
    var isIssues = tab.source === "issues";
    el.grid.hidden = isIssues;
    el.issues.hidden = !isIssues;
    el.filter.disabled = isIssues;
    el.search.disabled = isIssues;
    el.download.disabled = isIssues;
    if (!isIssues) {
      table.setColumns(tab.columns.map(column));
      if (loadedSource !== tab.source) {
        loadedSource = tab.source;
        table.replaceData(sourceRows(tab)).then(applyFilter);
      } else {
        applyFilter();
      }
    }
    renderFilterOptions(tab);
    renderTree();
    var hash = "#" + tab.id + "/" + current.filter;
    if (location.hash !== hash) { history.replaceState(null, "", hash); }
  }

  function renderFilterOptions(tab) {
    el.filter.innerHTML = tab.filters.map(function (f) {
      var n = countFor(tab.id, f.id);
      var label = f.label + (n === null ? "" : " (" + n + ")");
      return '<option value="' + escapeHtml(f.id) + '">' + escapeHtml(label) + "</option>";
    }).join("");
    el.filter.value = current.filter;
  }

  function renderTree() {
    el.tree.innerHTML = specs.map(function (tab) {
      var open = " open";
      var items = tab.filters.map(function (f) {
        var n = countFor(tab.id, f.id);
        var active = tab.id === current.tab && f.id === current.filter ? ' class="active"' : "";
        return '<li><a href="#' + escapeHtml(tab.id) + "/" + escapeHtml(f.id) + '" data-tab="' + escapeHtml(tab.id) + '" data-filter="' + escapeHtml(f.id) + '"' + active + ">" +
          '<span class="label">' + escapeHtml(f.label) + '</span><span class="num" data-count>' + (n === null ? "" : n) + "</span></a></li>";
      }).join("");
      var total = countFor(tab.id, "all");
      return "<details" + open + '><summary><span class="label">' + escapeHtml(tab.label) + '</span><span class="num">' + (total === null ? "" : total) + "</span></summary><ul>" + items + "</ul></details>";
    }).join("");
  }

  function renderSummary() {
    if (!summary) { return; }
    var issues = 0;
    Object.keys(summary.issues).forEach(function (k) { issues += summary.issues[k]; });
    var stats = { pages: summary.pages, indexable: summary.indexable, non_indexable: summary.non_indexable, issues: issues };
    Object.keys(stats).forEach(function (key) {
      var node = document.querySelector('[data-stat="' + key + '"]');
      if (node) { node.textContent = String(stats[key]); }
    });
  }

  // ---------------------------------------------------------------- data
  function loadAll() {
    return fetchJson("/api/rows?since=0&rev=0").then(function (page) {
      pages = page.rows;
      return fetchJson("/api/external");
    }).then(function (rows) {
      external = rows;
      return fetchJson("/api/summary");
    }).then(function (s) {
      summary = s;
      renderSummary();
    });
  }

  function parseHash() {
    var parts = location.hash.replace(/^#/, "").split("/");
    return { tab: parts[0] || specs[0].id, filter: parts[1] || "all" };
  }

  // -------------------------------------------------------------- events
  el.strip.addEventListener("click", function (event) {
    var button = event.target.closest("[data-tab]");
    if (button) { selectTab(button.dataset.tab, "all"); }
  });
  el.filter.addEventListener("change", function () {
    selectTab(current.tab, el.filter.value);
  });
  el.search.addEventListener("input", function () {
    current.search = el.search.value.trim().toLowerCase();
    applyFilter();
  });
  el.download.addEventListener("click", function () {
    table.download("csv", current.tab + "-" + current.filter + ".csv");
  });
  el.tree.addEventListener("click", function (event) {
    var link = event.target.closest("[data-tab]");
    if (link) {
      event.preventDefault();
      selectTab(link.dataset.tab, link.dataset.filter);
    }
  });
  window.addEventListener("hashchange", function () {
    var h = parseHash();
    if (h.tab !== current.tab || h.filter !== current.filter) { selectTab(h.tab, h.filter); }
  });

  table.on("tableBuilt", function () {
    loadAll().then(function () {
      var h = parseHash();
      selectTab(h.tab, h.filter);
    });
  });

  window.sitecrawler = { selectTab: selectTab, reload: loadAll, table: table };
})();
