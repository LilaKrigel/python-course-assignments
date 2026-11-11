// The pages are made by Flask (templates/) and every button is a plain HTML form, so the app
// works without this file. It only adds what a server can't do on its own:
//   - send a form as soon as a slider, switch or option changes, and ask before risky changes
//   - keep the scroll position when a button reloads the page
//   - the thumbnail size slider
//   - the full-screen photo viewer (← → to browse, H to hide a photo, Esc to close)

// ---------- Forms ----------
for (const form of document.querySelectorAll("form[data-autosubmit]")) {
  form.addEventListener("change", () => form.requestSubmit());
}
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.dataset.confirm && !confirm(form.dataset.confirm)) {
    event.preventDefault();
    form.reset();  // put the slider or option back where it was
    showPercent();
    return;
  }
  try { sessionStorage.setItem("scroll", JSON.stringify({ page: location.pathname, y: scrollY })); } catch { /* optional */ }
});

// After a button press the server sends the browser back to the same page: scroll to where it was
try {
  const saved = JSON.parse(sessionStorage.getItem("scroll") || "null");
  sessionStorage.removeItem("scroll");
  if (saved && saved.page === location.pathname && !location.hash.startsWith("#g-")) scrollTo(0, saved.y);
} catch { /* optional */ }

// A slider that shows its value as a percentage while it is moved
function showPercent() {
  for (const range of document.querySelectorAll("input[data-percent]")) {
    const output = document.getElementById(range.dataset.percent);
    const value = Number(range.value);
    output.textContent = `${Math.round(value * 100)}% · ${value < 0.86 ? "loose" : value <= 0.93 ? "balanced" : "strict"}`;
  }
}
for (const range of document.querySelectorAll("input[data-percent]")) range.addEventListener("input", showPercent);

// ---------- Thumbnail size ----------
const size = document.getElementById("size");
if (size) {
  const apply = () => document.documentElement.style.setProperty("--thumb", `${size.value}px`);
  try { size.value = localStorage.getItem("thumbSize") || 180; } catch { /* optional */ }
  apply();
  size.addEventListener("input", () => {
    apply();
    try { localStorage.setItem("thumbSize", size.value); } catch { /* optional */ }
  });
}

// ---------- Full-screen photo viewer ----------
// Links with class "view" open it; the photos of the same data-list can be browsed with ← →.
// On pages with a #hide-form, H hides the shown photo (the page reloads and the viewer reopens on it).
const lightbox = document.getElementById("lightbox");
const hideForm = document.getElementById("hide-form");
let list = [], index = 0;

function show(i) {
  index = i;
  const link = list[index];
  lightbox.querySelector("img").src = link.href;
  lightbox.querySelector("figcaption").textContent = `${index + 1} / ${list.length} · ${link.dataset.caption}`;
  lightbox.querySelector(".lb-prev").hidden = index === 0;
  lightbox.querySelector(".lb-next").hidden = index === list.length - 1;
  const action = lightbox.querySelector(".lb-action");
  action.hidden = !hideForm || link.dataset.rejected === undefined;
  const hidden = link.dataset.rejected === "1";
  action.textContent = hidden ? "Hidden · show again (H)" : "Hide this photo (H)";
  action.classList.toggle("on", hidden);
  lightbox.hidden = false;
}

function open(link) {
  list = [...document.querySelectorAll(`a.view[data-list="${link.dataset.list}"]`)];
  show(list.indexOf(link));
}

function close() {
  lightbox.hidden = true;
  lightbox.querySelector("img").removeAttribute("src");
}

function hideShownPhoto() {
  if (lightbox.querySelector(".lb-action").hidden) return;
  const id = list[index].dataset.id;
  hideForm.elements.photo.value = id;
  hideForm.elements.back.value = `${location.pathname}${location.search}#view-${id}`;
  hideForm.requestSubmit();
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a.view");
  if (!link || event.ctrlKey || event.metaKey || event.shiftKey) return;
  event.preventDefault();
  open(link);
});
lightbox.querySelector(".lb-close").addEventListener("click", close);
lightbox.querySelector(".lb-prev").addEventListener("click", () => show(index - 1));
lightbox.querySelector(".lb-next").addEventListener("click", () => show(index + 1));
lightbox.querySelector(".lb-action").addEventListener("click", hideShownPhoto);
lightbox.addEventListener("click", (event) => { if (event.target === lightbox) close(); });
document.addEventListener("keydown", (event) => {
  if (lightbox.hidden) return;
  if (event.key === "Escape") close();
  else if (event.key === "ArrowLeft" && index > 0) show(index - 1);
  else if (event.key === "ArrowRight" && index < list.length - 1) show(index + 1);
  else if (event.key.toLowerCase() === "h") hideShownPhoto();
  else return;
  event.preventDefault();
});

// Reopen the viewer after hiding a photo with H (the address ends with #view-<photo id>)
const reopen = location.hash.match(/^#view-(\d+)$/);
if (reopen) {
  history.replaceState(null, "", location.pathname + location.search);
  const link = document.querySelector(`a.view[data-id="${reopen[1]}"]`);
  if (link) open(link);
}
