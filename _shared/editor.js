// README-only editing. Source and old revisions always use value/textContent.
(function () {
  "use strict";
  var tools = document.querySelector("[data-readme-path]");
  if (!tools) return;
  var path = tools.getAttribute("data-readme-path");
  var editor = document.getElementById("readme-editor");
  var source = document.getElementById("readme-source");
  var save = document.getElementById("readme-save");
  var cancel = document.getElementById("readme-cancel");
  var status = document.getElementById("readme-editor-status");
  var history = document.getElementById("readme-history-dialog");
  var historyList = document.getElementById("readme-history-list");
  var historyStatus = document.getElementById("readme-history-status");
  var more = document.getElementById("readme-history-more");
  var original = null, revision = null, saving = false, nextBefore = null;
  var editorSession = 0, historySession = 0, newline = "\n";

  async function request(endpoint, options) {
    var response = await fetch("/_editor/" + endpoint +
      (endpoint.indexOf("?") < 0 ? "?" : "&") + "path=" + encodeURIComponent(path),
      Object.assign({ cache: "no-store", credentials: "same-origin" }, options));
    var data;
    try { data = await response.json(); } catch (e) {
      throw new Error("The README editor is unavailable. Try again shortly.");
    }
    if (!response.ok) throw new Error(data.error || "The request failed. Try again.");
    return data;
  }

  function message(element, text, error) {
    element.textContent = text;
    element.classList.toggle("error", !!error);
  }

  function dirty() { return original !== null && source.value !== original; }

  function closeEditor() {
    if (saving) return;
    if (dirty() && !window.confirm("Discard your unsaved README changes?")) return;
    editorSession++;
    editor.close();
  }

  document.getElementById("readme-edit").addEventListener("click", async function () {
    var session = ++editorSession;
    original = revision = null;
    source.value = "";
    source.disabled = save.disabled = true;
    message(status, "Loading…");
    editor.showModal();
    try {
      var data = await request("document");
      if (session !== editorSession) return;
      revision = data.revision;
      newline = data.content.indexOf("\r\n") >= 0 ? "\r\n" : "\n";
      source.value = data.content;
      original = source.value;
      source.disabled = false;
      message(status, "Editor " + data.editor_ip + " · Changes are saved to this site's README.md.");
      source.setSelectionRange(0, 0);
      source.focus({ preventScroll: true });
      source.scrollTop = 0;
    } catch (error) { if (session === editorSession) message(status, error.message, true); }
  });

  source.addEventListener("input", function () { save.disabled = saving || !dirty(); });
  cancel.addEventListener("click", closeEditor);
  editor.addEventListener("cancel", function (event) { event.preventDefault(); closeEditor(); });
  window.addEventListener("beforeunload", function (event) {
    if (editor.open && dirty()) { event.preventDefault(); event.returnValue = ""; }
  });

  async function saveChanges() {
    if (save.disabled || saving) return;
    saving = true;
    save.disabled = cancel.disabled = source.disabled = true;
    message(status, "Saving…");
    try {
      await request("document", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: source.value.replace(/\n/g, newline), revision: revision })
      });
      original = source.value;
      editor.close();
      // Reload the current URL so relative links and Caddy's Markdown rendering stay intact.
      window.location.reload();
    } catch (error) {
      message(status, error.message, true);
      save.disabled = false;
    } finally {
      saving = false;
      cancel.disabled = source.disabled = false;
    }
  }
  save.addEventListener("click", saveChanges);
  source.addEventListener("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault(); saveChanges();
    }
  });

  function renderDiff(data) {
    var view = document.createElement("div");
    view.className = "readme-diff-view";
    var counts = document.createElement("p");
    counts.className = "readme-diff-counts";
    [["add", "+" + data.additions + " added"], ["delete", "−" + data.deletions + " removed"]].forEach(function (count) {
      var label = document.createElement("span");
      label.className = "readme-diff-count-" + count[0];
      label.textContent = count[1];
      counts.appendChild(label);
    });
    view.appendChild(counts);
    if (!data.hunks.length) {
      var notice = document.createElement("p");
      notice.className = "readme-status";
      notice.textContent = data.notice || "No line changes.";
      view.appendChild(notice);
      return view;
    }
    var diff = document.createElement("div");
    diff.className = "readme-diff";
    diff.setAttribute("role", "region");
    diff.setAttribute("aria-label", "Line changes, with old and new line numbers");
    data.hunks.forEach(function (hunk) {
      var header = document.createElement("div");
      header.className = "readme-diff-hunk";
      header.textContent = "@@ −" + hunk.old_start + "," + hunk.old_count +
        " +" + hunk.new_start + "," + hunk.new_count + " @@";
      diff.appendChild(header);
      hunk.lines.forEach(function (line) {
        var row = document.createElement("div");
        row.className = "readme-diff-line readme-diff-" + line.kind;
        [["Old", line.old_line], ["New", line.new_line]].forEach(function (number) {
          var gutter = document.createElement("span");
          gutter.className = "readme-diff-number";
          gutter.textContent = number[1] === null ? "" : number[1];
          if (number[1] !== null) gutter.setAttribute("aria-label", number[0] + " line " + number[1]);
          row.appendChild(gutter);
        });
        var marker = document.createElement("span");
        marker.className = "readme-diff-marker";
        marker.textContent = line.kind === "add" ? "+" : line.kind === "delete" ? "−" : " ";
        var text = document.createElement("span");
        text.className = "readme-diff-text";
        text.textContent = line.text || " ";
        row.append(marker, text);
        diff.appendChild(row);
      });
    });
    view.appendChild(diff);
    return view;
  }

  function appendEntry(entry) {
    var item = document.createElement("li");
    var details = document.createElement("details");
    details.setAttribute("name", "readme-history-entry");
    var summary = document.createElement("summary");
    var date = new Date(entry.created_at);
    summary.textContent = "Editor " + entry.editor_ip + " · " + date.toLocaleString();
    var label = document.createElement("span");
    label.className = "readme-revision-id";
    label.textContent = "Edit #" + entry.id;
    summary.appendChild(label);
    details.appendChild(summary);
    var loaded = false;
    details.addEventListener("toggle", async function () {
      if (!details.open) return;
      // Also covers browsers without native named-details accordion support.
      historyList.querySelectorAll("details[open]").forEach(function (other) {
        if (other !== details) other.open = false;
      });
      if (loaded) return;
      loaded = true;
      var loading = document.createElement("p");
      loading.textContent = "Loading changes…";
      details.appendChild(loading);
      try {
        var data = await request("diff?id=" + entry.id);
        details.appendChild(renderDiff(data));
        loading.remove();
      } catch (error) {
        message(loading, error.message, true);
        // Reopening retries failed requests.
        loaded = false;
        details.addEventListener("toggle", function retry() {
          if (!details.open) { loading.remove(); details.removeEventListener("toggle", retry); }
        });
      }
    });
    item.appendChild(details);
    historyList.appendChild(item);
  }

  async function loadHistory() {
    var session = historySession;
    more.disabled = true;
    message(historyStatus, "Loading…");
    try {
      var data = await request("history" + (nextBefore ? "?before=" + nextBefore : ""));
      if (session !== historySession) return;
      data.edits.forEach(appendEntry);
      nextBefore = data.next_before;
      more.hidden = !nextBefore;
      message(historyStatus, historyList.children.length ?
        "Saved edits, newest first. Open an entry to see changed lines and nearby context." : "No saved edits yet.");
    } catch (error) {
      if (session === historySession) { message(historyStatus, error.message, true); more.hidden = false; }
    } finally { if (session === historySession) more.disabled = false; }
  }

  document.getElementById("readme-history").addEventListener("click", function () {
    historySession++;
    historyList.replaceChildren();
    nextBefore = null;
    more.hidden = true;
    history.showModal();
    loadHistory();
  });
  more.addEventListener("click", loadHistory);
  history.addEventListener("close", function () { historySession++; });
  document.getElementById("readme-history-close").addEventListener("click", function () { history.close(); });
})();
