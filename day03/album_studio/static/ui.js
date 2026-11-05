// Helpers shared by the app shell and every step: talking to the server, formatting,
// the full-screen photo viewer and short notifications.

export async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, options);
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch { /* not JSON, e.g. an error page */ }
  if (!res.ok) throw new Error(data?.error || `The app answered with an error (${res.status}).`);
  return data;
}

export function esc(value) {
  return String(value).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Photo dates come from the server as "YYYY-MM-DD HH:MM:SS"
export function fmtDay(taken) {
  const [y, m, d] = taken.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

export function fmtTime(taken, seconds = false) {
  return taken.slice(11, seconds ? 19 : 16);
}

let toastTimer;
export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
}

// ---------- Full-screen viewer ----------
const lb = document.getElementById("lightbox");
let lbIds = [], lbIndex = 0, lbCaption = () => "", lbAction = null;

// action (optional): a button for the shown photo, { label: id => text, on: id => highlighted?, run: async id => {}, key: "h" }
export function openLightbox(ids, index, caption, action = null) {
  lbIds = ids;
  lbIndex = index;
  lbCaption = caption;
  lbAction = action;
  lb.hidden = false;
  showLightboxPhoto();
}

function showLightboxPhoto() {
  const id = lbIds[lbIndex];
  lb.querySelector("img").src = `/api/photo/${id}`;
  lb.querySelector("figcaption").textContent = `${lbIndex + 1} / ${lbIds.length} · ${lbCaption(id)}`;
  lb.querySelector(".lb-prev").hidden = lbIndex === 0;
  lb.querySelector(".lb-next").hidden = lbIndex === lbIds.length - 1;
  const action = lb.querySelector(".lb-action");
  action.hidden = !lbAction;
  if (lbAction) {
    action.textContent = `${lbAction.label(id)} (${lbAction.key.toUpperCase()})`;
    action.classList.toggle("on", lbAction.on(id));
  }
}

async function runLightboxAction() {
  await lbAction.run(lbIds[lbIndex]);
  showLightboxPhoto();
}

function moveLightbox(step) {
  const next = lbIndex + step;
  if (next >= 0 && next < lbIds.length) {
    lbIndex = next;
    showLightboxPhoto();
  }
}

lb.querySelector(".lb-close").onclick = () => { lb.hidden = true; };
lb.querySelector(".lb-prev").onclick = () => moveLightbox(-1);
lb.querySelector(".lb-next").onclick = () => moveLightbox(1);
lb.querySelector(".lb-action").onclick = runLightboxAction;
lb.onclick = e => { if (e.target === lb) lb.hidden = true; };
// Capture phase: while the viewer is open, its keys win over the page underneath
window.addEventListener("keydown", e => {
  if (lb.hidden) return;
  if (e.key === "Escape") lb.hidden = true;
  else if (e.key === "ArrowLeft") moveLightbox(-1);
  else if (e.key === "ArrowRight") moveLightbox(1);
  else if (lbAction && e.key.toLowerCase() === lbAction.key) runLightboxAction();
  else return;
  e.stopImmediatePropagation();
  e.preventDefault();
}, true);
