// The app shell: welcome screen, analysis progress, and the workspace with the list of steps.
// Each step draws its own page with static/steps/<ui>.js (see steps/group_similar.js).
import { api, esc, toast } from "./ui.js";

const screen = document.getElementById("screen");
let project = null;
let currentStep = null;

function setProjectLabel() {
  const label = document.getElementById("project-label");
  label.innerHTML = project ? `<strong>${esc(project.name)}</strong> · ${project.photo_count} photos` : "";
  document.getElementById("change-folder").hidden = !project;
}

// ---------- Welcome: choose a folder ----------
async function showWelcome(error = "") {
  const [recent, steps] = await Promise.all([api("/api/recent"), api("/api/steps")]);
  screen.innerHTML = `
    <div class="welcome">
      <h1>Make an album from your photos</h1>
      <p class="lead">Choose a folder, for example a whole trip. Album Studio guides you step by step:
        it stacks similar photos, picks the best ones and helps you choose what goes into the album.
        Your original photos are never changed.</p>
      <div class="open-card">
        <button class="btn primary big" id="pick">Choose photo folder…</button>
        <div class="or">or paste the folder path</div>
        <form class="open-row" id="path-form">
          <input type="text" id="path" placeholder="C:\\Users\\me\\Pictures\\Africa 2025" autocomplete="off">
          <button class="btn">Open</button>
        </form>
        <div class="error" ${error ? "" : "hidden"}>${esc(error)}</div>
        ${recent.length ? `
          <div class="recent"><h3>Recent folders</h3>
            ${recent.map(f => `<button data-folder="${esc(f)}"><span class="folder-name">${esc(f.split(/[\\/]/).pop())}</span>
              <span class="folder-path">${esc(f)}</span></button>`).join("")}
          </div>` : ""}
      </div>
      <div class="journey"><h3>The steps</h3>
        <ol>${steps.map((s, i) => `<li><b>${i + 1}. ${esc(s.title)}</b><span>${esc(s.tagline)}</span></li>`).join("")}</ol>
      </div>
    </div>`;

  const pick = document.getElementById("pick");
  pick.onclick = async () => {
    pick.disabled = true;
    pick.textContent = "A folder window opened… (it may be behind this one)";
    const { folder } = await api("/api/pick-folder", {});
    if (folder) openFolder(folder);
    else { pick.disabled = false; pick.textContent = "Choose photo folder…"; }
  };
  document.getElementById("path-form").onsubmit = e => {
    e.preventDefault();
    const folder = document.getElementById("path").value.trim();
    if (folder) openFolder(folder);
  };
  screen.querySelectorAll("[data-folder]").forEach(b => { b.onclick = () => openFolder(b.dataset.folder); });
}

async function openFolder(folder) {
  try {
    await api("/api/open", { folder });
  } catch (err) {
    return showWelcome(err.message);
  }
  showProgress();
}

// ---------- Progress while the photos are analysed ----------
function showProgress() {
  screen.innerHTML = `
    <div class="progress-screen">
      <h2>Getting to know your photos</h2>
      <p>Every photo is read once to measure its sharpness and understand what it shows.
        Next time, this folder opens instantly.</p>
      <div class="bar indeterminate"><div></div></div>
      <div class="progress-detail"><span id="msg">Starting…</span><span id="eta"></span></div>
    </div>`;
  const poll = async () => {
    const job = await api("/api/job");
    if (job.finished) return job.error ? showWelcome(`Analysis failed: ${job.error}`) : showWorkspace();
    document.getElementById("msg").textContent = job.message;
    if (job.total) {
      const bar = screen.querySelector(".bar");
      bar.classList.remove("indeterminate");
      bar.firstElementChild.style.width = `${(100 * job.done) / job.total}%`;
    }
    if (job.eta) document.getElementById("eta").textContent = `about ${formatDuration(job.eta)} left`;
    setTimeout(poll, 700);
  };
  poll();
}

function formatDuration(seconds) {
  return seconds < 90 ? `${Math.max(5, Math.round(seconds / 5) * 5)} seconds` : `${Math.round(seconds / 60)} minutes`;
}

// ---------- Workspace: steps on the left, the current step on the right ----------
async function showWorkspace() {
  project = await api("/api/project");
  setProjectLabel();
  screen.innerHTML = `
    <div class="workspace">
      <nav class="steps-nav"><h3>Your album</h3><ol id="steps"></ol></nav>
      <section class="step-page" id="step-page"></section>
    </div>`;
  const fromUrl = project.steps.find(s => s.id === location.hash.slice(1));
  openStep((fromUrl || project.steps[0]).id);
}

function renderNav() {
  document.getElementById("steps").innerHTML = project.steps.map((s, i) => {
    const planned = s.ui === "planned";
    const classes = [s.id === currentStep ? "current" : "", s.done ? "done" : "", planned ? "planned" : ""].join(" ");
    return `<li><button class="step-link ${classes}" data-step="${s.id}">
      <span class="step-num">${s.done ? "✓" : i + 1}</span>
      <span class="step-text"><b>${esc(s.title)}${planned ? '<span class="soon">soon</span>' : ""}</b>
        <small>${esc(s.summary || "")}</small></span></button></li>`;
  }).join("");
  document.querySelectorAll("[data-step]").forEach(b => { b.onclick = () => openStep(b.dataset.step); });
}

async function refreshNav() {
  project.steps = (await api("/api/project?photos=0")).steps;
  renderNav();
}

async function openStep(id) {
  currentStep = id;
  history.replaceState(null, "", `#${id}`);
  renderNav();
  const index = project.steps.findIndex(s => s.id === id);
  const step = project.steps[index];
  const nextStep = project.steps[index + 1];
  const page = document.getElementById("step-page");
  page.scrollTop = 0;
  page.innerHTML = `<div class="empty">Loading…</div>`;
  const module = await import(`/static/steps/${step.ui}.js`);
  // Everything a step page may use; new steps get the same
  await module.render(page, {
    step, number: index + 1, nextStep, photos: project.photos, refreshNav, toast,
    goToStep: openStep,
    next: async () => {
      await api(`/api/steps/${step.id}/complete`, {});
      await refreshNav();
      if (nextStep) openStep(nextStep.id);
    },
  });
}

// ---------- Start ----------
document.getElementById("change-folder").onclick = () => { project = null; setProjectLabel(); showWelcome(); };
document.getElementById("brand").onclick = e => { e.preventDefault(); if (!project) showWelcome(); };

(async () => {
  const current = await api("/api/project?photos=0");
  if (!current) showWelcome();
  else if (!current.ready) showProgress();
  else showWorkspace();
})();
