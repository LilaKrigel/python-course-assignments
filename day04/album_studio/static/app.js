// The pages are made by Flask (templates/) and every button is a plain HTML form, so the app
// works without this file. It only adds what a server can't do on its own:
//   - buttons (and a message's Undo) update the page in place (no reload, no jump to the top)
//   - send a form as soon as a slider, switch or option changes, and ask before risky changes
//   - the thumbnail size slider
//   - the full-screen photo viewer (← → to browse, Esc to close, and the page's own keys:
//     H hides a photo, P picks one in step 2; zoom; ↑ ↓ to the group before/after)
// Everything is set up once on the document, so it keeps working after the page is updated.

// ---------- Forms ----------
document.addEventListener("change", (event) => {
  const form = event.target.closest("form[data-autosubmit]");
  if (form && event.target.type !== "text") form.requestSubmit();
});

let sending = Promise.resolve();  // forms are sent one after the other, in the order they were used

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.dataset.confirm && !confirm(form.dataset.confirm)) {
    event.preventDefault();
    form.reset();  // put the slider or option back where it was
    showPercent();
    return;
  }
  if (form.method !== "post" || !form.closest(".step-page, .toasts")) {
    rememberScroll();
    return;
  }
  // Send it in the background; the server answers with the page to show next
  event.preventDefault();
  const data = new FormData(form, event.submitter);
  const action = event.submitter?.getAttribute("formaction") || form.getAttribute("action");
  sending = sending.then(() => send(action, data)).catch(() => location.reload());
});

async function send(action, data) {
  const response = await fetch(action, { method: "POST", body: data });
  const url = new URL(response.url);
  const page = new DOMParser().parseFromString(await response.text(), "text/html");
  if (!response.ok || !page.querySelector(".step-page")) {
    location.assign(response.url);  // not a step page: load it normally
    return;
  }
  const moved = url.pathname + url.search !== location.pathname + location.search;
  if (moved) {
    // another page (e.g. back to all groups): show the one received, with its message
    history.pushState(null, "", url.pathname + url.search);
    shownPage = url.pathname + url.search;
    document.title = page.title;
    scrollTo(0, 0);
    close();
  }
  // keyboard users stay on the button they pressed (e.g. the ♡ of a photo)
  const focused = document.activeElement;
  const refocus = focused?.name && focused.value
    ? `${focused.tagName}[name="${focused.name}"][value="${CSS.escape(focused.value)}"]` : null;
  for (const selector of [".step-page", ".steps-nav"]) {
    document.querySelector(selector)?.replaceWith(page.querySelector(selector));
  }
  document.querySelector(".toasts")?.remove();
  const toasts = page.querySelector(".toasts");
  if (toasts) document.querySelector(".topbar").after(toasts);
  applySize();
  refreshViewer();
  // e.g. the viewer hid the last photo of a group: go on in the next group's photos
  const back = String(data.get("back") || "");
  if (moved && back.includes("#view-")) openFromHash(back.slice(back.indexOf("#")));
  if (refocus && lightbox.hidden) document.querySelector(`.step-page ${refocus}`)?.focus({ preventScroll: true });
}

function rememberScroll() {
  try { sessionStorage.setItem("scroll", JSON.stringify({ page: location.pathname, y: scrollY })); } catch { /* optional */ }
}

// Back/Forward after a page was shown in place: load that page fresh from the server
// (only when the address really changed; a change of #… alone stays on the page)
let shownPage = location.pathname + location.search;
addEventListener("popstate", () => {
  if (location.pathname + location.search !== shownPage) location.reload();
});

// After a page reload (without the in-place update) scroll to where it was
try {
  const saved = JSON.parse(sessionStorage.getItem("scroll") || "null");
  sessionStorage.removeItem("scroll");
  if (saved && saved.page === location.pathname && !location.hash.startsWith("#g-")) scrollTo(0, saved.y);
} catch { /* optional */ }

// A slider that shows its value as a percentage while it is moved
function showPercent() {
  for (const range of document.querySelectorAll("input[data-percent]")) {
    const value = Number(range.value);
    document.getElementById(range.dataset.percent).textContent =
      `${Math.round(value * 100)}% · ${value < 0.86 ? "loose" : value <= 0.93 ? "balanced" : "strict"}`;
  }
}
document.addEventListener("input", (event) => {
  if (event.target.matches("input[data-percent]")) showPercent();
  if (event.target.id === "size") {
    try { localStorage.setItem("thumbSize", event.target.value); } catch { /* optional */ }
    applySize();
  }
});

// ---------- Thumbnail size ----------
function applySize() {
  const size = document.getElementById("size");
  if (!size) return;
  try { size.value = localStorage.getItem("thumbSize") || size.getAttribute("value"); } catch { /* optional */ }
  document.documentElement.style.setProperty("--thumb", `${size.value}px`);
}
applySize();

// ---------- Full-screen photo viewer ----------
// Links with class "view" open it; the photos of the same data-list can be browsed with ← →.
// Each hidden form.viewer-action on the page becomes a button (and a key, data-key) that acts on
// the shown photo: H hides it, P picks it. Its data-flag names the link attribute that says
// whether that is "on" for the photo (data-hidden="1", data-picked="0"); without that attribute
// the button is not offered (e.g. no Pick for a hidden photo).
// On a page with links rel="prev"/"next" data-group-nav (an opened group in step 2), ↑ ↓ go to
// the group before/after, and → after the last photo goes on to the next group's first photo.
// Click the photo (or Z) to zoom in to full size; drag to look around, click again to zoom out.
const lightbox = document.getElementById("lightbox");
const image = lightbox.querySelector("img");
const figure = lightbox.querySelector("figure");
let list = [], index = 0, listName = "", advanceFrom = null;

const viewerForms = () => [...document.querySelectorAll("form.viewer-action")];
const groupLink = (rel) => document.querySelector(`a[rel="${rel}"][data-group-nav]`);

function show(i) {
  index = i;
  const link = list[index];
  unzoom();
  image.src = link.href;
  const nav = groupLink("prev") || groupLink("next") ? " · ↑ ↓ groups" : "";
  lightbox.querySelector("figcaption").textContent =
    `${index + 1} / ${list.length} · ${link.dataset.caption} · click or Z to zoom${nav}`;
  lightbox.querySelector(".lb-prev").hidden = index === 0 && !groupLink("prev");
  lightbox.querySelector(".lb-next").hidden = index === list.length - 1 && !groupLink("next");
  const buttons = viewerForms().filter((form) => link.dataset[form.dataset.flag] !== undefined).map((form) => {
    const on = link.dataset[form.dataset.flag] === "1";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lb-action" + (on ? " on" : "");
    button.dataset.key = form.dataset.key;  // the colour when on: red for "hidden", orange for "picked"
    button.textContent = `${on ? form.dataset.labelOn : form.dataset.labelOff} (${form.dataset.key.toUpperCase()})`;
    button.addEventListener("click", () => act(form));
    return button;
  });
  lightbox.querySelector(".lb-actions").replaceChildren(...buttons);
  lightbox.hidden = false;
}

function open(link) {
  listName = link.dataset.list;
  list = [...document.querySelectorAll(`a.view[data-list="${listName}"]`)];
  show(list.indexOf(link));
}

function close() {
  unzoom();
  lightbox.hidden = true;
  image.removeAttribute("src");
}

// Previous / next photo; at the ends of an opened group, on to the group before / after it
function step(direction) {
  const next = index + direction;
  if (next >= 0 && next < list.length) return show(next);
  const link = groupLink(direction > 0 ? "next" : "prev");
  if (link) location.assign(link.href + (direction > 0 ? "#view-first" : "#view-last"));
}

// After the page was updated in place: keep showing the same photo (or the next one, if it left
// the list). After hiding a photo that stays in the list (faded), go on to the next one.
function refreshViewer() {
  if (lightbox.hidden) return;
  const id = list[index].dataset.id;
  list = [...document.querySelectorAll(`a.view[data-list="${listName}"]`)];
  if (!list.length) return close();
  let found = list.findIndex((link) => link.dataset.id === id);
  if (found >= 0 && advanceFrom === id && list[found].dataset.hidden === "1" && found < list.length - 1) found += 1;
  advanceFrom = null;
  if (found >= 0 && found === index && zoomed) {  // same photo, still zoomed in: only the buttons change
    const keep = [figure.scrollLeft, figure.scrollTop];
    show(found);
    zoom(null, keep);
    return;
  }
  show(found >= 0 ? found : Math.min(index, list.length - 1));
}

function act(form) {
  const link = list[index];
  if (link.dataset[form.dataset.flag] === undefined) return;
  form.elements.photo.value = link.dataset.id;
  if (form.dataset.flag === "hidden" && link.dataset.hidden === "0") advanceFrom = link.dataset.id;
  // hiding the last photo shown in a group goes on to the next group (or back to all groups);
  // otherwise back to this page, where (without the in-place update) #view-<id> reopens the viewer
  form.elements.back.value = link.dataset.last && form.dataset.backLast && link.dataset.hidden === "0"
    ? form.dataset.backLast : `${location.pathname}${location.search}#view-${link.dataset.id}`;
  form.requestSubmit();
}

// ---------- Zoom: the photo at full size, dragged around ----------
let zoomed = false, drag = null;

function zoom(event, scroll) {
  const link = list[index];
  const rect = image.getBoundingClientRect();
  // the point clicked stays under the mouse (Z: the middle)
  const fx = event ? (event.clientX - rect.left) / rect.width : 0.5;
  const fy = event ? (event.clientY - rect.top) / rect.height : 0.5;
  zoomed = true;
  lightbox.classList.add("zoomed");
  const place = () => {
    if (scroll) [figure.scrollLeft, figure.scrollTop] = scroll;
    else {
      figure.scrollLeft = fx * image.naturalWidth - (event ? event.clientX : figure.clientWidth / 2);
      figure.scrollTop = fy * image.naturalHeight - (event ? event.clientY : figure.clientHeight / 2);
    }
  };
  const large = `${link.href}${link.href.includes("?") ? "&" : "?"}size=4000`;
  if (image.src.endsWith(large)) return place();
  image.addEventListener("load", place, { once: true });
  image.src = large;
}

function unzoom() {
  if (!zoomed) return;
  zoomed = false;
  lightbox.classList.remove("zoomed");
  if (list[index]) image.src = list[index].href;
}

image.addEventListener("click", (event) => { if (!zoomed) zoom(event); });
figure.addEventListener("pointerdown", (event) => {
  if (!zoomed) return;
  drag = { x: event.clientX, y: event.clientY, left: figure.scrollLeft, top: figure.scrollTop, moved: false };
  figure.setPointerCapture(event.pointerId);
});
figure.addEventListener("pointermove", (event) => {
  if (!drag) return;
  const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
  figure.scrollLeft = drag.left - dx;
  figure.scrollTop = drag.top - dy;
});
figure.addEventListener("pointerup", () => {
  if (drag && !drag.moved) unzoom();  // a click (not a drag) zooms out again
  drag = null;
});

document.addEventListener("click", (event) => {
  const link = event.target.closest("a.view");
  if (!link || event.ctrlKey || event.metaKey || event.shiftKey) return;
  event.preventDefault();
  open(link);
});
lightbox.querySelector(".lb-close").addEventListener("click", close);
lightbox.querySelector(".lb-prev").addEventListener("click", () => step(-1));
lightbox.querySelector(".lb-next").addEventListener("click", () => step(1));
lightbox.addEventListener("click", (event) => { if (event.target === lightbox) close(); });
document.addEventListener("keydown", (event) => {
  if (lightbox.hidden || event.ctrlKey || event.metaKey || event.altKey) return;
  const form = viewerForms().find((f) => f.dataset.key === event.key.toLowerCase());
  if (event.key === "Escape") zoomed ? unzoom() : close();
  else if (event.key === "ArrowLeft") step(-1);
  else if (event.key === "ArrowRight") step(1);
  else if (event.key === "ArrowUp" && groupLink("prev")) location.assign(groupLink("prev").href + "#view-first");
  else if (event.key === "ArrowDown" && groupLink("next")) location.assign(groupLink("next").href + "#view-first");
  else if (event.key.toLowerCase() === "z") zoomed ? unzoom() : zoom(null);
  else if (form) act(form);
  else return;
  event.preventDefault();
});

// Open the viewer from the address: #view-<id> (after a page reload from the viewer's button),
// #view-first / #view-last (from the group before or after, or "Review one by one")
function openFromHash(hash) {
  const match = hash.match(/^#view-(\d+|first|last)$/);
  if (!match) return;
  const links = [...document.querySelectorAll("a.view")].filter((a) => a.dataset.list === "group" || !document.querySelector('a.view[data-list="group"]'));
  const link = match[1] === "first" ? links[0] : match[1] === "last" ? links[links.length - 1]
    : document.querySelector(`a.view[data-id="${match[1]}"]`);
  if (link) open(link);
}
if (location.hash.startsWith("#view-")) {
  const hash = location.hash;
  history.replaceState(null, "", location.pathname + location.search);
  openFromHash(hash);
}
