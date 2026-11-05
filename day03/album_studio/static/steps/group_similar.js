// Step 1 page: settings for grouping, all groups by day, and fixing groups by hand.
import { api, esc, fmtDay, fmtTime, openLightbox } from "../ui.js";

const TIME_OPTIONS = [[30, "30 s"], [120, "2 min"], [600, "10 min"], [3600, "1 hour"], [null, "Any time"]];
const PROBLEM_LABELS = { blurry: "Blurry", blank: "Too dark or bright", dark: "Too dark", unfocused: "Out of focus", overexposed: "Overexposed" };

export async function render(el, ctx) {
  const url = `/api/steps/${ctx.step.id}`;
  const photos = ctx.photos;
  let data = await api(url);
  let seconds = data.settings.seconds;
  let filter = "all";
  const selected = new Set();  // groups ticked for merging (indexes into data.groups)
  const allDays = [...new Set(photos.map(p => p.taken.slice(0, 10)))];

  el.innerHTML = `
    <div class="step-head">
      <div class="eyebrow">Step ${ctx.number}</div>
      <h1>${esc(ctx.step.title)}</h1>
      <p>${esc(ctx.step.description)}</p>
    </div>
    <div class="panel controls">
      <div class="control">
        <label for="sim">How similar must photos be? <output id="sim-out"></output></label>
        <input type="range" id="sim" min="0.80" max="0.98" step="0.01">
        <div class="range-labels"><span>Looser: bigger groups</span><span>Stricter: only near-identical</span></div>
      </div>
      <div class="control">
        <label>Taken within</label>
        <div class="segmented" id="time">
          ${TIME_OPTIONS.map(([s, label]) => `<button data-s="${s}">${label}</button>`).join("")}
        </div>
        <div class="hint">A burst is taken seconds apart. "Any time" also stacks the same view shot hours later.</div>
      </div>
    </div>
    <div class="stats" id="stats"></div>
    <div class="toolbar">
      <div class="tabs" id="tabs">
        <button data-f="all">All</button><button data-f="stacks">Stacks</button><button data-f="singles">Single photos</button>
      </div>
      <div class="filter-toggle">
        <label class="switch"><input type="checkbox" id="hide-bad" role="switch"> Hide blurry and bad photos</label>
        <span class="hint" id="bad-info"></span>
      </div>
      <label class="size-control">Size <input type="range" id="size" min="120" max="340" step="10"></label>
    </div>
    <div id="groups"></div>
    <div class="step-foot">
      <span id="foot-text"></span>
      <button class="btn primary" id="next">${ctx.nextStep ? `Next: ${esc(ctx.nextStep.title)} →` : "Finish"}</button>
    </div>
    <div class="action-bar" id="merge-bar" hidden>
      <span id="merge-count"></span>
      <button class="btn" id="merge-clear">Clear</button>
      <button class="btn primary" id="merge">Merge into one group</button>
    </div>`;

  const $ = sel => el.querySelector(sel);
  const groupsEl = $("#groups");
  const sim = $("#sim");

  // ---------- Blurry and bad photos ----------
  // Flagged: found by the checks, or hidden by the user ("rejected")
  const isRejected = id => data.rejected.includes(id);
  const flagged = () => photos.filter(p => p.problem || isRejected(p.id)).map(p => p.id);
  const isBad = id => (photos[id].problem && !data.kept.includes(id)) || isRejected(id);
  const isHidden = id => data.hide_problems && isBad(id);
  const hideBad = $("#hide-bad");

  async function reject(id, on) {
    data = await api(`${url}/reject`, { photo: id, on });
    draw();
    ctx.refreshNav();
    ctx.toast(!on ? "The photo is shown again"
      : data.hide_problems ? "Photo hidden · undo it in “review”" : "Photo marked as bad · hidden while the switch is on");
  }
  // The full-screen viewer's button for the shown photo
  const rejectAction = {
    key: "h",
    label: id => (isRejected(id) ? "Hidden · show again" : "Hide this photo"),
    on: isRejected,
    run: id => reject(id, !isRejected(id)),
  };
  hideBad.onchange = async () => {
    data = await api(`${url}/hide_problems`, { hide: hideBad.checked });
    selected.clear();
    draw();
    ctx.toast(hideBad.checked ? "Blurry and bad photos are hidden" : "All photos are shown");
  };

  // ---------- Grouping settings ----------
  function showSettings() {
    sim.value = data.settings.similarity;
    seconds = data.settings.seconds;
    showSimilarity();
    el.querySelectorAll("#time button").forEach(b => b.classList.toggle("on", String(seconds) === b.dataset.s));
  }

  function showSimilarity() {
    const v = Number(sim.value);
    $("#sim-out").textContent = `${Math.round(v * 100)}% · ${v < 0.86 ? "loose" : v <= 0.93 ? "balanced" : "strict"}`;
  }

  async function regroup(askFirst = true) {
    if (askFirst && data.edited && !confirm("Re-grouping replaces the changes you made by hand. Continue?")) {
      return showSettings();
    }
    groupsEl.style.opacity = 0.5;
    data = await api(`${url}/regroup`, { similarity: Number(sim.value), seconds });
    groupsEl.style.opacity = "";
    selected.clear();
    draw();
    ctx.refreshNav();
  }

  let regroupTimer;
  sim.oninput = () => {
    showSimilarity();
    clearTimeout(regroupTimer);
    regroupTimer = setTimeout(regroup, 350);
  };
  el.querySelectorAll("#time button").forEach(b => {
    b.onclick = () => {
      seconds = b.dataset.s === "null" ? null : Number(b.dataset.s);
      el.querySelectorAll("#time button").forEach(x => x.classList.toggle("on", x === b));
      regroup();
    };
  });

  // ---------- View options ----------
  el.querySelectorAll("#tabs button").forEach(b => {
    b.onclick = () => { filter = b.dataset.f; draw(); };
  });
  const size = $("#size");
  try { size.value = localStorage.getItem("thumbSize") || 180; } catch { size.value = 180; }
  el.style.setProperty("--thumb", `${size.value}px`);
  size.oninput = () => {
    el.style.setProperty("--thumb", `${size.value}px`);
    try { localStorage.setItem("thumbSize", size.value); } catch { /* not important */ }
  };

  // ---------- Drawing ----------
  function caption(id) {
    const p = photos[id];
    const problem = p.problem ? ` · ${PROBLEM_LABELS[p.problem]}` : isRejected(id) ? " · Hidden by you" : "";
    return `${p.file} · ${fmtDay(p.taken)} ${fmtTime(p.taken, true)} · ${p.megapixels} MP${problem}`;
  }

  function timeSpan(ids) {
    const first = photos[ids[0]].taken, last = photos[ids[ids.length - 1]].taken;
    return ids.length > 1 && fmtTime(first) !== fmtTime(last) ? `${fmtTime(first)}–${fmtTime(last)}` : fmtTime(first);
  }

  const bestOf = ids => ids.reduce((a, b) => (photos[b].quality > photos[a].quality ? b : a));

  // Groups as shown: without hidden photos, and without groups that had only hidden photos
  function shownGroups() {
    return data.groups.map((g, k) => {
      const ids = g.photos.filter(id => !isHidden(id));
      return { k, photos: ids, cover: ids.length ? bestOf(ids) : null };
    }).filter(g => g.photos.length);
  }

  function card(g) {
    const n = g.photos.length;
    return `
      <div class="card ${n > 1 ? "stack" : ""} ${selected.has(g.k) ? "selected" : ""}" data-k="${g.k}">
        <button class="check" title="Select (to merge groups)">✓</button>
        <div class="frame"><div class="clip"><img loading="lazy" src="/api/thumb/${g.cover}" alt=""></div>
          ${n > 1 ? `<span class="count">${n} photos</span>` : ""}</div>
        <div class="meta"><span>${timeSpan(g.photos)}</span></div>
      </div>`;
  }

  let shown = [];
  function draw() {
    shown = shownGroups();
    const nShown = shown.reduce((n, g) => n + g.photos.length, 0);
    const stacks = shown.filter(g => g.photos.length > 1).length;
    const hiddenCount = photos.length - nShown;
    $("#stats").innerHTML = `
      <div class="stat"><b>${nShown}</b><span>photos${hiddenCount ? ` (${hiddenCount} hidden)` : ""}</span></div>
      <div class="stat arrow">→</div>
      <div class="stat"><b>${shown.length}</b><span>groups</span></div>
      <div class="stat"><b>${stacks}</b><span>stacks of similar photos</span></div>
      <div class="stat"><b>${shown.length - stacks}</b><span>single photos</span></div>
      <div class="stat"><b>${nShown - shown.length}</b><span>near-duplicates tucked away</span></div>
      ${data.edited ? `<div class="edited-note">Includes your changes by hand · <button id="undo">undo them</button></div>` : ""}`;
    const undo = $("#undo");
    if (undo) undo.onclick = () => { if (confirm("Undo all changes you made by hand?")) regroup(false); };

    // The switch and how many photos it hides
    hideBad.checked = data.hide_problems;
    const bad = flagged().filter(isBad).length + data.broken.length;
    $("#bad-info").innerHTML = bad
      ? `${bad} ${data.hide_problems ? "hidden" : "found"} · <button class="link" id="review">review</button>`
      : "none found";
    const review = $("#review");
    if (review) review.onclick = openReview;

    el.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.f === filter));
    const list = shown.filter(g => filter === "all" || (filter === "stacks") === (g.photos.length > 1));
    const byDay = new Map();
    for (const g of list) {
      const day = photos[g.photos[0]].taken.slice(0, 10);
      if (!byDay.has(day)) byDay.set(day, []);
      byDay.get(day).push(g);
    }
    groupsEl.innerHTML = list.length ? [...byDay].map(([day, gs]) => `
      <div class="day"><h2>Day ${allDays.indexOf(day) + 1} · ${fmtDay(day)}</h2>
        <span>${gs.length} groups · ${gs.reduce((n, g) => n + g.photos.length, 0)} photos</span></div>
      <div class="grid">${gs.map(card).join("")}</div>`).join("")
      : `<div class="empty">No ${filter === "stacks" ? "stacks" : "single photos"} with these settings.</div>`;
    $("#foot-text").textContent = `${nShown} photos are now ${shown.length} groups. Happy with them?`;
    updateMergeBar();
  }

  // ---------- Clicking groups: open, view, select for merging ----------
  groupsEl.onclick = e => {
    const cardEl = e.target.closest(".card");
    if (!cardEl) return;
    const k = Number(cardEl.dataset.k);
    if (e.target.closest(".check") || selected.size) {  // while selecting, a click toggles
      selected.has(k) ? selected.delete(k) : selected.add(k);
      cardEl.classList.toggle("selected", selected.has(k));
      return updateMergeBar();
    }
    const g = shown.find(x => x.k === k);
    if (g.photos.length > 1) return openGroup(g);
    const singles = shown.filter(x => x.photos.length === 1);
    openLightbox(singles.map(x => x.cover), singles.findIndex(x => x.k === k), caption, rejectAction);
  };

  function updateMergeBar() {
    $("#merge-bar").hidden = selected.size === 0;
    groupsEl.classList.toggle("selecting", selected.size > 0);
    $("#merge-count").textContent = `${selected.size} ${selected.size === 1 ? "group" : "groups"} selected`;
    $("#merge").disabled = selected.size < 2;
  }
  $("#merge-clear").onclick = () => { selected.clear(); draw(); };
  $("#merge").onclick = async () => {
    const n = selected.size;
    data = await api(`${url}/merge`, { groups: [...selected] });
    selected.clear();
    draw();
    ctx.refreshNav();
    ctx.toast(`Merged ${n} groups into one`);
  };

  // ---------- Sheets (panels sliding up over the page) ----------
  function openSheet(title, subtitle, tools, body) {
    const sheet = document.createElement("div");
    sheet.className = "sheet-backdrop";
    sheet.innerHTML = `
      <div class="sheet" role="dialog" aria-modal="true">
        <header><h2>${title}</h2><span>${subtitle}</span><button class="close" aria-label="Close (Esc)">×</button></header>
        <div class="sheet-tools">${tools}</div>
        <div class="sheet-body">${body}</div>
      </div>`;
    document.body.append(sheet);
    const close = () => { sheet.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = e => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    sheet.querySelector(".close").onclick = close;
    sheet.onclick = e => { if (e.target === sheet) close(); };
    return { sheet, close };
  }

  // A group opened to see all its photos, best first
  function openGroup(g) {
    // Best photos first; quality combines sharpness and resolution (see analysis.py)
    const order = [...g.photos].sort((a, b) => photos[b].quality - photos[a].quality);
    const hiddenHere = data.groups[g.k].photos.length - g.photos.length;
    const ticked = new Set();  // positions in `order`
    const rejectButton = id => isRejected(id)
      ? `<button class="btn small reject on" data-id="${id}" title="Show this photo again">Hidden</button>`
      : `<button class="btn small reject" data-id="${id}" title="Hide this photo (a bad photo the checks missed)">Hide</button>`;
    const { sheet, close } = openSheet(
      `${order.length} similar photos`,
      `${fmtDay(photos[g.photos[0]].taken)} · ${timeSpan(g.photos)}${hiddenHere ? ` · ${hiddenHere} bad photos hidden` : ""}`,
      `<button class="btn" data-act="split" disabled>Move ticked photos to a new group</button>
       <button class="btn" data-act="ungroup" disabled>Make ticked photos single</button>
       <span class="hint">Best photos first · click a photo to see it large · tick photos that don't belong here · “Hide” bad photos</span>`,
      `<div class="grid">
        ${order.map((id, n) => `
          <div class="card" data-n="${n}">
            <button class="check" title="Tick">✓</button>
            <div class="frame"><div class="clip"><img loading="lazy" src="/api/thumb/${id}" alt=""></div>
              ${n === 0 ? '<span class="badge">Best quality</span>' : ""}</div>
            <div class="meta"><span>${fmtTime(photos[id].taken, true)} · ${photos[id].megapixels} MP</span>${rejectButton(id)}</div>
          </div>`).join("")}
      </div>`);

    // Hiding a photo here only dims it, so it can be undone right away
    const showRejected = () => sheet.querySelectorAll(".card").forEach(tile => {
      const id = order[Number(tile.dataset.n)];
      tile.classList.toggle("rejected", isRejected(id));
      tile.querySelector(".reject").outerHTML = rejectButton(id);
    });
    const groupAction = { ...rejectAction, run: async id => { await rejectAction.run(id); showRejected(); } };

    sheet.querySelector(".grid").onclick = async e => {
      const tile = e.target.closest(".card");
      if (!tile) return;
      const n = Number(tile.dataset.n);
      if (e.target.closest(".reject")) {
        await reject(order[n], !isRejected(order[n]));
        return showRejected();
      }
      if (!e.target.closest(".check")) return openLightbox(order, n, caption, groupAction);
      ticked.has(n) ? ticked.delete(n) : ticked.add(n);
      tile.classList.toggle("selected", ticked.has(n));
      const usable = ticked.size > 0 && ticked.size < order.length;
      sheet.querySelectorAll("[data-act]").forEach(b => { b.disabled = !usable; });
    };
    sheet.querySelectorAll("[data-act]").forEach(b => {
      b.onclick = async () => {
        data = await api(`${url}/${b.dataset.act}`, { photos: [...ticked].map(n => order[n]) });
        close();
        draw();
        ctx.refreshNav();
        ctx.toast(b.dataset.act === "split" ? `Moved ${ticked.size} photos to a new group` : `${ticked.size} photos are now single`);
      };
    });
  }

  // All photos flagged as bad, to check them and keep any that are fine after all
  function openReview() {
    const ids = flagged();
    // Found by the checks: Keep. Hidden by the user: Show again (taken back by clicking again).
    const button = id => {
      const byUser = !photos[id].problem;
      const on = byUser ? !isRejected(id) : data.kept.includes(id);
      const label = byUser ? (on ? "✓ Shown" : "Show again") : (on ? "✓ Kept" : "Keep");
      return `<button class="btn small keep ${on ? "on" : ""}" data-id="${id}">${label}</button>`;
    };
    const { sheet } = openSheet(
      "Blurry and bad photos",
      `${ids.length} photos · hidden while the switch is on, unless you keep them`,
      `<span class="hint">Click a photo to see it large · “Keep” and “Show again” show a photo again if it is fine after all</span>`,
      `${ids.length ? `<div class="grid">
        ${ids.map((id, n) => `
          <div class="card" data-n="${n}">
            <div class="frame"><div class="clip"><img loading="lazy" src="/api/thumb/${id}" alt=""></div>
              <span class="badge warn">${photos[id].problem ? PROBLEM_LABELS[photos[id].problem] : "Hidden by you"}</span></div>
            <div class="meta"><span>${esc(photos[id].file)}</span>${button(id)}</div>
          </div>`).join("")}
      </div>` : ""}
      ${data.broken.length ? `
        <h3 class="sheet-section">Couldn't be opened (${data.broken.length})</h3>
        <p class="hint">These files may be damaged or are not photos. They are never shown.</p>
        <ul class="broken-list">${data.broken.map(f => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}`);

    sheet.querySelector(".sheet-body").onclick = async e => {
      const toggle = e.target.closest(".keep");
      if (toggle) {
        const id = Number(toggle.dataset.id);
        if (photos[id].problem) data = await api(`${url}/keep`, { photo: id, on: !data.kept.includes(id) });
        else data = await api(`${url}/reject`, { photo: id, on: !isRejected(id) });
        toggle.outerHTML = button(id);
        ctx.refreshNav();
        return draw();
      }
      const tile = e.target.closest(".card");
      if (tile) openLightbox(ids, Number(tile.dataset.n), caption);
    };
  }

  $("#next").onclick = ctx.next;
  showSettings();
  draw();
}
