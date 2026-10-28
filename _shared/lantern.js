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

  // http(s) URLs written in code (inline or blocks) become links: click, Ctrl+click
  // or middle-click them like any other. Chroma may split a URL over several token
  // spans, so match the code's whole text and wrap the range, spans and all.
  var CODE_URL = /\bhttps?:\/\/[\w[][\w\-.~:\/?#[\]@!$&'()*+,;=%]*/g;

  function trimUrl(url) {
    for (;;) {
      var c = url.slice(-1);
      if (c === ")" && url.split("(").length >= url.split(")").length) break;
      if (c === "]" && url.split("[").length >= url.split("]").length) break;
      if (!/[.,;:!?'*)\]]/.test(c)) break;
      url = url.slice(0, -1);
    }
    return url;
  }

  function linkCodeUrls() {
    document.querySelectorAll(".doc code").forEach(function (code) {
      if (code.closest("a")) return;
      var nodes = [], starts = [], text = "";
      var walk = document.createTreeWalker(code, NodeFilter.SHOW_TEXT);
      while (walk.nextNode()) {
        nodes.push(walk.currentNode);
        starts.push(text.length);
        text += walk.currentNode.data;
      }
      var found = [], m;
      CODE_URL.lastIndex = 0;
      while ((m = CODE_URL.exec(text))) {
        // Placeholders (http://host:{port}/, http://localhost:$PORT/) aren't addresses.
        if (/[<{$]/.test(text.charAt(m.index + m[0].length)) || m[0].indexOf("$") >= 0) continue;
        var url = trimUrl(m[0]);
        found.push({ from: m.index, to: m.index + url.length, url: url });
      }
      // Last match first: wrapping only splits nodes at or after it, so the
      // offsets recorded for earlier matches stay valid.
      function point(pos, isEnd) {
        for (var i = 0; i < nodes.length; i++) {
          var off = pos - starts[i], len = nodes[i].data.length;
          if (isEnd ? off > 0 && off <= len : off >= 0 && off < len) return [nodes[i], off];
        }
      }
      found.reverse().forEach(function (f) {
        var range = document.createRange();
        range.setStart.apply(range, point(f.from, false));
        range.setEnd.apply(range, point(f.to, true));
        var a = document.createElement("a");
        a.className = "code-link";
        a.href = f.url;
        a.appendChild(range.extractContents());
        range.insertNode(a);
      });
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
    linkCodeUrls();
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
