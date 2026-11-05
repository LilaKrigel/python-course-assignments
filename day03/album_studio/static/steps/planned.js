// Page for a step that is designed but not built yet.
import { esc } from "../ui.js";

export async function render(el, ctx) {
  el.innerHTML = `
    <div class="step-head">
      <div class="eyebrow">Step ${ctx.number}</div>
      <h1>${esc(ctx.step.title)}</h1>
    </div>
    <div class="panel planned-box">
      <span class="tag">Coming soon</span>
      <p>${esc(ctx.step.description)}</p>
      <p class="hint">This step is planned but not built yet.</p>
      <button class="btn" id="back">← Back to step 1</button>
    </div>`;
  el.querySelector("#back").onclick = () => ctx.goToStep("group");
}
