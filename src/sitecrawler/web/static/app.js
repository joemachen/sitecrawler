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
  function listCell(cell) {
    var value = cell.getValue();
    return Array.isArray(value) ? escapeHtml(value.join(", ")) : escapeHtml(value === null || value === undefined ? "" : value);
  }

  function column(name) {
    var spec = { title: name, field: name, headerFilter: "input", headerFilterLiveFilter: true };
    if (name === "url" || name === "final_url" || name === "found_on" || name === "canonical" || name === "first_found_on") {
      spec.width = 360;
    }
    spec.formatter = listCell;
    return spec;
  }

  var table = new Tabulator(el.grid, {
    index: "url",
    layout: "fitDataStretch",
    height: "100%",
    columns: [],
    data: [],
    placeholder: "No rows",
    selectableRows: 1,
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
  var seq = 0;
  var rev = 0;
  var crawl = { status: document.querySelector(".app").dataset.status };
  var ACTIVE = { running: true, paused: true, stopping: true, finishing: true };
  var ENABLED = {
    idle: ["start"],
    running: ["pause", "stop"],
    paused: ["resume", "stop"],
    stopping: [],
    finishing: [],
    done: ["start", "clear"],
    stopped: ["start", "clear"],
    error: ["start", "clear"],
  };
  var app = document.querySelector(".app");
  var form = document.getElementById("crawl-form");
  var pollTimer = null;

  function formatElapsed(seconds) {
    var s = Math.max(0, Math.round(seconds || 0));
    var m = Math.floor(s / 60);
    return m + ":" + String(s % 60).padStart(2, "0");
  }

  function applyCrawl(c) {
    crawl = c;
    app.dataset.status = c.status;
    document.querySelector("[data-status-badge]").textContent = c.status;
    var total = c.done + c.queued;
    var bar = document.querySelector("[data-progress]");
    bar.max = total || 1;
    bar.value = c.done;
    document.querySelector("[data-progress-text]").textContent =
      c.start_url ? c.done + " done · " + c.queued + " queued · " + formatElapsed(c.elapsed) : "";
    document.querySelector("[data-error]").textContent = c.error || "";
    var dbNode = document.querySelector("[data-db]");
    dbNode.textContent = c.db ? c.db.split(/[\\/]/).pop() : "";
    dbNode.title = c.db || "";
    var ro = document.querySelector("[data-read-only]");
    if (ro) { ro.hidden = !c.read_only; }
    var enabled = ENABLED[c.status] || [];
    Array.prototype.forEach.call(form.querySelectorAll("[data-action]"), function (button) {
      button.disabled = enabled.indexOf(button.dataset.action) === -1;
    });
    form.querySelector("[data-url-input]").disabled = enabled.indexOf("start") === -1;
  }

  function applyPatches(patches) {
    if (!patches.length) { return; }
    var byUrl = {};
    pages.forEach(function (row) { byUrl[row.url] = row; });
    patches.forEach(function (patch) {
      var row = byUrl[patch.url];
      if (row) { Object.keys(patch).forEach(function (key) { row[key] = patch[key]; }); }
    });
  }

  function refreshRows() {
    var url = "/api/rows?since=" + seq + "&rev=" + rev;
    return fetchJson(url).then(function (page) {
      var inGrid = loadedSource === "pages";
      if (page.full || seq === 0) {
        pages = page.rows;
        if (inGrid) { table.replaceData(pages); }
      } else {
        pages = pages.concat(page.rows);
        applyPatches(page.patches);
        if (inGrid) {
          if (page.rows.length) { table.addData(page.rows); }
          if (page.patches.length) { table.updateData(page.patches); }
        }
      }
      var revChanged = page.audit_rev !== rev;
      seq = page.seq;
      rev = page.audit_rev;
      if (revChanged) { document.body.dispatchEvent(new CustomEvent("audit-changed")); }
      return fetchJson("/api/external");
    }).then(function (rows) {
      external = rows;
      if (loadedSource === "external") { table.replaceData(external); }
      return fetchJson("/api/summary");
    }).then(function (s) {
      summary = s;
      renderSummary();
      if (tabsById[current.tab]) {
        renderFilterOptions(tabsById[current.tab]);
        renderTree();
        if (loadedSource) { applyFilter(); }
      }
      return loadDetail();
    });
  }

  function pollOnce() {
    return fetchJson("/api/crawl").then(function (c) {
      var moved = c.seq !== seq || c.audit_rev !== rev || c.status === "idle";
      applyCrawl(c);
      if (c.status === "idle" && seq !== 0) {
        seq = 0; rev = 0; pages = []; external = [];
        table.clearData();
      }
      return moved ? refreshRows() : null;
    });
  }

  function schedule() {
    clearTimeout(pollTimer);
    if (ACTIVE[crawl.status]) {
      pollTimer = setTimeout(function () { pollOnce().then(schedule, schedule); }, 1000);
    }
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: body ? JSON.stringify(body) : null,
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) { throw new Error(data.detail || (url + " -> " + r.status)); }
        return data;
      });
    });
  }

  function showError(err) {
    document.querySelector("[data-error]").textContent = String(err.message || err);
  }

  function startCrawl() {
    var data = new FormData(form);
    var body = {
      url: data.get("url"),
      max_pages: Number(data.get("max_pages")) || 5000,
      delay_seconds: Number(data.get("delay_seconds")),
      workers: Number(data.get("workers")) || 4,
      timeout_seconds: Number(data.get("timeout_seconds")) || 20,
      use_sitemap: data.get("use_sitemap") === "on",
      respect_robots: data.get("respect_robots") === "on",
      keep_query: data.get("keep_query") === "on",
      render: data.get("render") === "on",
    };
    return post("/api/crawl/start", body).then(function (c) {
      seq = 0; rev = 0; pages = []; external = []; summary = null;
      table.clearData();
      applyCrawl(c);
      return refreshRows();
    }).then(schedule).catch(showError);
  }

  // --------------------------------------------------------------- detail
  var detail = {
    pane: document.querySelector("[data-detail]"),
    body: document.querySelector("[data-detail-body]"),
    url: document.querySelector("[data-detail-url]"),
    open: document.querySelector("[data-detail-open]"),
    subtabs: document.querySelector("[data-subtabs]"),
    selected: null,
    sub: "details",
  };

  function loadDetail() {
    if (!detail.selected) { return Promise.resolve(); }
    var url = "/detail/" + detail.sub + "?url=" + encodeURIComponent(detail.selected);
    return fetch(url).then(function (r) { return r.text(); }).then(function (html) {
      detail.body.innerHTML = html;
    });
  }

  function selectUrl(url) {
    detail.selected = url;
    detail.url.textContent = url;
    detail.pane.dataset.url = url;
    detail.open.href = "/page?url=" + encodeURIComponent(url);
    detail.open.hidden = false;
    return loadDetail();
  }

  function selectSub(sub) {
    detail.sub = sub;
    Array.prototype.forEach.call(detail.subtabs.querySelectorAll("[data-sub]"), function (button) {
      button.setAttribute("aria-selected", button.dataset.sub === sub ? "true" : "false");
    });
    return loadDetail();
  }

  detail.subtabs.addEventListener("click", function (event) {
    var button = event.target.closest("[data-sub]");
    if (button) { selectSub(button.dataset.sub); }
  });
  table.on("rowSelected", function (row) {
    if (loadedSource === "pages") { selectUrl(row.getData().url); }
  });
  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-url]");
    if (link && (detail.pane.contains(link) || el.issues.contains(link))) {
      event.preventDefault();
      selectUrl(link.dataset.url);
    }
  });

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

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    startCrawl();
  });
  form.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-action]");
    if (!button || button.dataset.action === "start") { return; }
    event.preventDefault();
    post("/api/crawl/" + button.dataset.action).then(function (c) {
      applyCrawl(c);
      return pollOnce();
    }).then(schedule).catch(showError);
  });

  table.on("tableBuilt", function () {
    pollOnce().then(function () {
      var h = parseHash();
      selectTab(h.tab, h.filter);
      schedule();
    });
  });

  window.sitecrawler = { selectTab: selectTab, poll: pollOnce, table: table };
})();
