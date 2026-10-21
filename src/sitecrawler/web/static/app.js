/* Grids: every [data-grid] element becomes a Tabulator table fed from its URL.
 * The toolbar around it (search, row count, CSV download) is wired by attribute,
 * so a new tab needs only the template, no JavaScript. */
(function () {
  "use strict";

  function matchesAnyColumn(data, params) {
    var needle = params.value;
    return Object.keys(data).some(function (key) {
      var value = data[key];
      return value !== null && value !== undefined && String(value).toLowerCase().indexOf(needle) !== -1;
    });
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pageLink(cell) {
    var url = cell.getValue();
    if (url === null || url === undefined || url === "") {
      return "";
    }
    return '<a href="/page?url=' + encodeURIComponent(url) + '">' + escapeHtml(url) + "</a>";
  }

  function column(name) {
    var spec = { title: name, field: name, headerFilter: "input", headerFilterLiveFilter: true };
    if (name === "url" || name === "final_url" || name === "found_on" || name === "canonical") {
      spec.width = 320;
    }
    if (name === "url") {
      spec.formatter = pageLink;
    }
    return spec;
  }

  function buildGrid(section) {
    var holder = section.querySelector("[data-grid]");
    var columns = JSON.parse(holder.dataset.columns);
    var count = section.querySelector("[data-grid-count]");
    var search = section.querySelector("[data-grid-search]");
    var download = section.querySelector("[data-grid-download]");

    var table = new Tabulator(holder, {
      ajaxURL: holder.dataset.grid,
      layout: "fitDataStretch",
      height: "calc(100vh - 140px)",
      columns: columns.map(column),
      placeholder: "No rows",
    });

    function showCount(rows) {
      if (count) {
        count.textContent = rows.length + " rows";
        count.dataset.rows = String(rows.length);
      }
    }
    table.on("dataLoaded", showCount);
    table.on("dataFiltered", function (filters, rows) { showCount(rows); });

    if (search) {
      search.addEventListener("input", function () {
        var value = search.value.trim().toLowerCase();
        if (value) {
          table.setFilter(matchesAnyColumn, { value: value });
        } else {
          table.clearFilter(false);
        }
      });
    }
    if (download) {
      download.addEventListener("click", function () {
        table.download("csv", holder.dataset.download || "export.csv");
      });
    }
  }

  document.querySelectorAll("section.grid").forEach(buildGrid);
})();
