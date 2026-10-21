// lantern — small progressive enhancements shared by all pages. No dependencies.
(function () {
  "use strict";

  // Copy button on every code block. navigator.clipboard only exists in secure
  // contexts (https / localhost); over plain http on the LAN fall back to execCommand.
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { /* ignore */ }
      document.body.removeChild(ta);
      ok ? resolve() : reject(new Error("copy failed"));
    });
  }

  function addCopyButtons() {
    document.querySelectorAll("pre").forEach(function (pre) {
      if (pre.classList.contains("mermaid") || pre.querySelector(".copy-btn")) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-btn";
      btn.textContent = "Copy";
      btn.addEventListener("click", function () {
        var code = pre.querySelector("code") || pre;
        copyText(code.innerText.replace(/\n$/, "")).then(
          function () { flash(btn, "Copied"); },
          function () { flash(btn, "Press Ctrl+C"); selectNode(code); }
        );
      });
      pre.appendChild(btn);
    });
  }

  function flash(btn, text) {
    btn.textContent = text;
    btn.classList.add("done");
    setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1500);
  }

  function selectNode(node) {
    var range = document.createRange();
    range.selectNodeContents(node);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  // Hover "#" links on headings that have ids (Caddy's markdown adds them).
  function addAnchors() {
    document.querySelectorAll(".doc :is(h1, h2, h3, h4)[id]").forEach(function (h) {
      var a = document.createElement("a");
      a.className = "anchor";
      a.href = "#" + h.id;
      a.setAttribute("aria-label", "Link to this section");
      a.textContent = "#";
      h.prepend(a);
    });
  }

  // ```mermaid blocks -> diagrams, only when the page loaded vendor/mermaid.min.js.
  function renderMermaid() {
    if (!window.mermaid) return;
    var blocks = document.querySelectorAll("pre > code.language-mermaid");
    if (!blocks.length) return;
    blocks.forEach(function (code) {
      var pre = document.createElement("pre");
      pre.className = "mermaid";
      pre.textContent = code.textContent;
      code.parentNode.replaceWith(pre);
    });
    var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    window.mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "default" });
    window.mermaid.run({ querySelector: "pre.mermaid" });
  }

  // Elements with data-app-status="/_status/name" get an up/down badge. That route
  // (Caddyfile) proxies a HEAD to the app; with nothing behind it Caddy answers 502,
  // so any status below 500 means "up" (401 included: the app asks for a login).
  function checkApps() {
    document.querySelectorAll("[data-app-status]").forEach(function (el) {
      fetch(el.getAttribute("data-app-status"), { method: "HEAD", cache: "no-store", redirect: "manual" })
        .then(function (r) { return r.type === "opaqueredirect" || r.status < 500; })
        .catch(function () { return false; })
        .then(function (up) {
          el.textContent = up ? "up" : "down";
          el.className = "badge " + (up ? "up" : "down");
        });
    });
  }

  // <time datetime> elements (directory listings) are rendered in UTC; show local time.
  function localTimes() {
    document.querySelectorAll("time[datetime]").forEach(function (t) {
      var d = new Date(t.getAttribute("datetime"));
      if (isNaN(d)) return;
      var pad = function (n) { return String(n).padStart(2, "0"); };
      t.textContent = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
        " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
      t.title = d.toString();
    });
  }

  function init() {
    renderMermaid();
    addCopyButtons();
    addAnchors();
    checkApps();
    localTimes();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
