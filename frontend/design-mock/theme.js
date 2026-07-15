/* Scedly — theme + light interactions (mock only) */

// Apply theme ASAP to avoid flash. Default = dark (per spec).
(function () {
  try {
    var saved = localStorage.getItem("scedly-theme");
    var theme = saved || "dark"; // dark default
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();

function toggleTheme() {
  var html = document.documentElement;
  var next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  try { localStorage.setItem("scedly-theme", next); } catch (e) {}
}

document.addEventListener("DOMContentLoaded", function () {
  // wire all theme toggles
  document.querySelectorAll("[data-theme-toggle]").forEach(function (el) {
    el.addEventListener("click", toggleTheme);
  });

  // mock checkbox toggling on the dashboard
  document.querySelectorAll("[data-check]").forEach(function (el) {
    el.addEventListener("click", function () {
      el.classList.toggle("done");
      el.textContent = el.classList.contains("done") ? "✓" : "";
      var item = el.closest("[data-task]");
      if (item) item.classList.toggle("is-complete");
    });
  });

  // mock tab switching (calendar Today/Week, settings nav)
  document.querySelectorAll("[data-tabs]").forEach(function (group) {
    var tabs = group.querySelectorAll("[data-tab]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        var target = tab.getAttribute("data-tab");
        var scope = group.getAttribute("data-tabs");
        document.querySelectorAll('[data-panel="' + scope + '"]').forEach(function (p) {
          p.style.display = p.getAttribute("data-tab-panel") === target ? "" : "none";
        });
      });
    });
  });

  // mock terminal input: echo on Enter (purely visual)
  var ti = document.querySelector("[data-term-input]");
  if (ti) {
    ti.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && ti.value.trim()) {
        var feed = document.querySelector("[data-term-feed]");
        if (feed) {
          var line = document.createElement("div");
          line.className = "feed-block";
          line.innerHTML =
            '<div class="feed-cmd"><span class="usr">[User]:</span> <span class="term-user"></span></div>' +
            '<div class="feed-resp"><span class="bot">scedly&gt;</span> <span class="term-comment">(design mock — connect backend to get a real response)</span></div>';
          line.querySelector(".term-user").textContent = ti.value;
          feed.appendChild(line);
          feed.scrollTop = feed.scrollHeight;
        }
        ti.value = "";
      }
    });
  }
});
