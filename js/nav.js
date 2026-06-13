/* Loads the shared nav from _includes/nav.html and wires up the active state. */
(function () {
    "use strict";

    var placeholder = document.getElementById("nav");
    if (!placeholder) return;

    var src = placeholder.dataset.navSrc;
    var prefix = placeholder.dataset.navPrefix || "";

    fetch(src, { cache: "no-cache" })
        .then(function (r) { return r.text(); })
        .then(function (html) {
            var wrapper = document.createElement("div");
            wrapper.innerHTML = html.trim();
            var nav = wrapper.querySelector("nav") || wrapper.firstElementChild;
            if (!nav) return;

            // Resolve data-href -> href (with the per-page prefix) and detect
            // the active link based on the current pathname.
            var currentFile = (location.pathname.split("/").pop() || "index.html").toLowerCase();
            // file:// URLs sometimes have a trailing empty segment; default to index
            if (!currentFile || currentFile === "") currentFile = "index.html";

            nav.querySelectorAll("a[data-href]").forEach(function (a) {
                var target = a.dataset.href;
                a.setAttribute("href", prefix + target);
                if (target.toLowerCase() === currentFile) {
                    a.classList.add("active");
                    var dropdown = a.closest(".topnav-dropdown");
                    if (dropdown) dropdown.classList.add("active");
                }
            });

            // If we're inside a writeup subdirectory, mark the matching
            // category link active in the dropdown too.
            var dirToCategory = {
                "htb-writeups":      "hackthebox.html",
                "thm-writeups":      "tryhackme.html",
                "vulnhub-writeups":  "vulnhub.html",
                "bugforge-writeups": "bugforge.html",
                "webverse-writeups": "webverse.html",
                "gensec":            "general.html"
            };
            for (var dir in dirToCategory) {
                if (location.pathname.indexOf("/" + dir + "/") !== -1) {
                    var slug = dirToCategory[dir];
                    var link = nav.querySelector('a[data-href="' + slug + '"]');
                    if (link) {
                        link.classList.add("active");
                        var dd = link.closest(".topnav-dropdown");
                        if (dd) dd.classList.add("active");
                    }
                    break;
                }
            }

            placeholder.replaceWith(nav);
        })
        .catch(function (e) {
            console.error("Failed to load nav:", e);
            placeholder.innerHTML =
                '<nav class="topnav"><a href="' + prefix + 'index.html">home</a></nav>';
        });
})();
