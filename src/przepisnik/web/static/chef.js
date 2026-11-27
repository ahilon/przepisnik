"use strict";
(() => {
  const panel = $("#chef");
  const log = $("#chef-log");
  const intro = $("#chef-intro");
  const input = $("#chef-text");
  const firstPrompt = input.placeholder;
  let draft = null;
  let clarification = "";
  let busy = false;
  const dollars = value => (value / 1_000_000).toLocaleString("pl-PL", {
    style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4
  });
  async function refreshBudget() {
    const response = await fetch("/api/chef");
    if (!response.ok) throw new Error("Nie udało się pobrać budżetu.");
    const settings = await response.json();
    $("#chef-tab").hidden = !settings.enabled;
    if (!settings.enabled) return;
    $("#chef-budget").textContent = `Pozostało ${dollars(settings.budget.available)}`;
    $("#chef-image").textContent = `Ilustracja · do ${dollars(settings.image_max)}`;
  }
  async function post(action, payload) {
    const response = await fetch("/api/chef/" + action, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Nie udało się wykonać operacji.");
    return result;
  }
  async function run(action) {
    if (busy) return;
    busy = true;
    panel.querySelectorAll("button, textarea").forEach(node => node.disabled = true);
    $("#chef-status").textContent = "Chwileczkę…";
    try {
      const message = await action();
      $("#chef-status").textContent = message || "";
    } catch (error) {
      $("#chef-status").textContent = error.message;
    } finally {
      busy = false;
      panel.querySelectorAll("button, textarea").forEach(node => node.disabled = false);
      await refreshBudget().catch(() => { $("#chef-budget").textContent = "Budżet chwilowo niedostępny."; });
    }
  }
  function addMessage(text, author) {
    const style = author === "user" ? "chef-bubble chef-bubble-user" : "chef-bubble";
    const message = element("p", style, text);
    log.append(message);
    log.scrollTop = log.scrollHeight;
    return message;
  }
  function showDraft(result) {
    const recipe = result.recipe;
    const variant = Object.values(recipe.variants)[0];
    const card = element("article", "chef-bubble");
    card.append(element("h3", "", recipe.title), element("p", "", `Liczba porcji: ${variant.servings}`));
    const ingredients = element("ul");
    for (const line of variant.ingredients) ingredients.append(element("li", "", [line.group, ingredientText(line)].filter(Boolean).join(" · ")));
    const steps = element("ol");
    recipe.steps.forEach(step => steps.append(element("li", "", step)));
    card.append(ingredients, steps);
    recipe.notes.forEach(note => card.append(element("p", "", note)));
    const photo = element("img");
    photo.alt = "Ilustracja wygenerowana przez AI";
    photo.hidden = true;
    card.append(photo);
    draft = {id: result.draft_id, recipe, jpeg: null, photo};
    log.append(card);
    log.scrollTop += card.getBoundingClientRect().top - log.getBoundingClientRect().top;
    $("#chef-actions").hidden = false;
    input.placeholder = "Np. Zamiast kurczaka użyj tofu.";
  }
  async function discard() {
    if (draft) await post("discard", {draft_id: draft.id});
    draft = null;
    clarification = "";
    log.replaceChildren(intro);
    $("#chef-actions").hidden = true;
    $("#chef-discard").hidden = true;
    input.value = "";
    input.placeholder = firstPrompt;
  }
  async function generate() {
    const text = input.value.trim();
    if (!text) return "Wpisz wiadomość.";
    const old = draft;
    const message = addMessage(text, "user");
    let result;
    try {
      result = await post("generate", {
        mode: old ? "revise" : "chat", text,
        ...(old ? {draft_id: old.id} : {}),
        ...(clarification ? {context: clarification} : {})
      });
    } catch (error) {
      message.remove();
      throw error;
    }
    input.value = "";
    $("#chef-discard").hidden = false;
    if (result.message) {
      addMessage(result.message, "chef");
      if (result.needs_details) {
        clarification = [clarification, text].filter(Boolean).join("\n").slice(-input.maxLength);
      }
      return;
    }
    clarification = "";
    showDraft(result);
    if (old) await post("discard", {draft_id: old.id}).catch(() => {});
  }
  $("#chef-form").addEventListener("submit", event => {
    event.preventDefault();
    run(generate).then(() => input.focus());
  });
  $("#chef-image").onclick = () => run(async () => {
    const result = await post("image", {draft_id: draft.id});
    draft.jpeg = result.jpeg;
    draft.photo.src = "data:image/jpeg;base64," + draft.jpeg;
    draft.photo.hidden = false;
    draft.photo.scrollIntoView({block: "nearest"});
  });
  $("#chef-discard").onclick = () => run(discard).then(() => input.focus());
  $("#chef-edit").onclick = () => {
    const recipe = draft.recipe;
    panel.close();
    openEditor({...recipe, effective_meal_types: recipe.meal_types, effective_dish_types: recipe.dish_types,
      image_url: draft.jpeg ? "data:image/jpeg;base64," + draft.jpeg : null}, draft);
  };
  document.addEventListener("chef-saved", () => run(discard));
  $("#chef-close").onclick = () => panel.close();
  panel.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  $("#chef-tab").onclick = () => { panel.showModal(); refreshBudget().catch(() => {}); };
  refreshBudget().catch(() => {});
})();
