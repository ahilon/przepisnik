"use strict";
const $ = (selector) => document.querySelector(selector);
const COMBINED_VARIANT = "combined";
const NUTRITION_FIELDS = [
  ["kcal", "Kalorie (kcal)", "kcal"],
  ["protein_g", "Białko (g)", "białko · g"],
  ["fat_g", "Tłuszcz (g)", "tłuszcz · g"],
  ["carbs_g", "Węglowodany (g)", "węglowodany · g"]
];
const AI_NUTRITION_LABEL = "Szacunek AI";
const labels = {
  breakfast: "Śniadanie", lunch: "Obiad", dinner: "Kolacja", snack: "Przekąska",
  female: "Kobieta", male: "Mężczyzna", family: "Wspólne", combined: "Dla dwojga",
  main: "Danie główne", soup: "Zupa", salad: "Sałatka", cake: "Ciasto",
  bread: "Chleb", dessert: "Deser", other: "Inne"
};
const state = { meal: "", collection: "all", page: 1, pages: 1 };
let listingRequest = null;
let detailRequest = null;
let detailRecipe = null;
let selectedVariant = "";
let displayedServings = null;
let searchTimer;
let knownTags = [];
let pendingTagSave = Promise.resolve();

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
async function request(url, signal) {
  const response = await fetch(url, { signal });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Nie udało się wczytać przepisów.");
  return body;
}
function badges(meals, dishes) {
  const group = element("div", "badges");
  const values = [...meals, ...dishes];
  if (!values.length) group.append(element("span", "badge neutral", "Bez kategorii"));
  values.forEach(value => group.append(element("span", "badge", labels[value] || value)));
  return group;
}
function photo(url, title, className) {
  const holder = element("div", className);
  const placeholder = () => { const image = element("img"); image.src = "/empty_dish.png"; image.alt = title; holder.replaceChildren(image); };
  if (url) {
    const image = element("img");
    image.src = url;
    image.alt = title;
    image.loading = "lazy";
    image.addEventListener("error", placeholder, { once: true });
    holder.append(image);
  } else placeholder();
  return holder;
}
function card(recipe) {
  const article = element("article", "recipe-card");
  const button = element("button", "card-button");
  button.type = "button";
  button.setAttribute("aria-label", `Otwórz przepis: ${recipe.title}`);
  const image = photo(recipe.image_url, recipe.title, "photo");
  const body = element("div", "card-body");
  body.append(badges(recipe.meal_types, recipe.dish_types), element("h3", "", recipe.title));
  const meta = element("div", "card-meta");
  meta.append(element("span", "", recipe.variants.map(v => labels[v]).join(" · ")));
  if (recipe.minutes) meta.append(element("span", "", `${recipe.minutes} min`));
  else meta.append(element("span", "", "Zobacz przepis ↗"));
  body.append(meta);
  button.append(image, body);
  button.addEventListener("click", () => openRecipe(recipe.id));
  article.append(button, favoriteButton(recipe, true));
  return article;
}
function favoriteButton(recipe, compact = false) {
  return metadataButton(recipe, "favorite", "Usuń z ulubionych", "Dodaj do ulubionych", compact);
}
function metadataButton(recipe, field, activeLabel, inactiveLabel, compact = false) {
  const active = recipe.user?.[field] ?? recipe[field];
  const label = active ? activeLabel : inactiveLabel;
  const button = element("button", compact ? "favorite-toggle" : "secondary", compact ? (active ? "♥" : "♡") : label);
  button.type = "button"; button.title = label;
  button.setAttribute("aria-label", `${label}: ${recipe.title}`);
  button.setAttribute("aria-pressed", String(active));
  let notice = null;
  button.addEventListener("click", async () => {
    button.disabled = true; notice?.remove();
    try {
      const current = await request(`/api/recipes/${encodeURIComponent(recipe.id)}`);
      const response = await fetch(`/api/recipes/${encodeURIComponent(recipe.id)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipe: { user: { ...current.user, [field]: !active } }, updated_at: current.updated_at })
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Nie udało się zapisać zmiany.");
      await loadRecipes();
      if ($("#detail").open && detailRecipe?.id === recipe.id) {
        const updated = await request(`/api/recipes/${encodeURIComponent(recipe.id)}`);
        if ($("#detail").open && detailRecipe?.id === recipe.id) { detailRecipe = updated; renderDetail(); }
      }
    } catch (failure) {
      notice = element("p", "error", failure.message); notice.setAttribute("role", "alert");
      button.insertAdjacentElement("afterend", notice);
    } finally { button.disabled = false; }
  });
  return button;
}
const tagKey = tag => tag.toLocaleLowerCase("pl-PL");
function tagEditor(id, tags, onChange = null) {
  const box = element("div", "tag-editor");
  const label = element("label", "", "Tagi"); label.htmlFor = id;
  const chips = element("ul", "tag-chips"); chips.setAttribute("aria-label", "Przypisane tagi");
  const row = element("div", "tag-add");
  const input = element("input"); input.id = id; input.maxLength = 40; input.autocomplete = "off";
  input.placeholder = "Wpisz własny tag, np. szybkie";
  const options = element("datalist"); options.id = `${id}-options`; input.setAttribute("list", options.id);
  const add = element("button", "secondary", "Dodaj tag"); add.type = "button";
  const error = element("p", "error"); error.hidden = true; error.setAttribute("role", "alert");
  let values = [...tags];
  function render() {
    chips.replaceChildren(...values.map(tag => {
      const chip = element("li", "tag-chip", `#${tag}`);
      const remove = element("button", "tag-remove", "×"); remove.type = "button";
      remove.setAttribute("aria-label", `Usuń tag: ${tag}`);
      remove.addEventListener("click", () => { commit(values.filter(value => value !== tag)); input.focus(); });
      chip.append(remove); return chip;
    }));
    chips.hidden = !values.length;
    const used = new Set(values.map(tagKey));
    options.replaceChildren(...knownTags.filter(tag => !used.has(tagKey(tag))).map(tag => new Option(tag, tag)));
  }
  async function commit(next) {
    const previous = values; values = next; render();
    if (!onChange) return;
    error.hidden = true; box.querySelectorAll("button, input").forEach(control => { control.disabled = true; });
    try { await onChange(values); }
    catch (failure) { values = previous; render(); error.textContent = failure.message; error.hidden = false; }
    finally { box.querySelectorAll("button, input").forEach(control => { control.disabled = false; }); }
  }
  function addFromInput() {
    const seen = new Set(values.map(tagKey)); const next = [...values];
    for (const tag of input.value.split(",").map(text => text.trim().replace(/^#+/, "").trim()).filter(Boolean)) {
      if (!seen.has(tagKey(tag))) { seen.add(tagKey(tag)); next.push(tag); }
    }
    input.value = "";
    if (next.length !== values.length) commit(next);
  }
  input.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === ",") { event.preventDefault(); addFromInput(); } });
  add.addEventListener("click", () => { addFromInput(); input.focus(); });
  row.append(input, add); box.append(label, chips, row, options, error); render();
  box.tags = () => { addFromInput(); return values; };
  return box;
}
function saveRecipeTags(id, tags) {
  pendingTagSave = writeRecipeTags(id, tags);
  return pendingTagSave;
}
async function writeRecipeTags(id, tags) {
  const current = await request(`/api/recipes/${encodeURIComponent(id)}`);
  const response = await fetch(`/api/recipes/${encodeURIComponent(id)}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipe: { user: { ...current.user, tags } }, updated_at: current.updated_at })
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Nie udało się zapisać tagów.");
  const updated = await request(`/api/recipes/${encodeURIComponent(id)}`);
  if (detailRecipe?.id === id) detailRecipe = updated;
  loadRecipes();
}
function query() {
  const params = new URLSearchParams({ page: String(state.page) });
  for (const [key, value] of Object.entries({ q: $("#search").value.trim(), meal: state.meal,
    variant: $("#variant").value, dish: $("#dish").value, tag: $("#tag").value,
    favorite: state.collection === "favorites" ? "1" : "",
    uncategorized: state.collection === "uncategorized" ? "1" : "", hidden: state.collection === "hidden" ? "1" : "" })) {
    if (value) params.set(key, value);
  }
  return params;
}
async function loadRecipes() {
  listingRequest?.abort();
  listingRequest = new AbortController();
  const controller = listingRequest;
  $("#grid").setAttribute("aria-busy", "true");
  $("#error").hidden = true;
  $("#result-count").textContent = "Wczytywanie…";
  $("#empty").hidden = true;
  $("#pagination").hidden = true;
  try {
    const result = await request(`/api/recipes?${query()}`, controller.signal);
    $("#grid").replaceChildren(...result.items.map(card));
    $("#result-count").textContent = `Znaleziono: ${result.total}`;
    $("#empty").hidden = result.total !== 0;
    state.page = result.page;
    state.pages = result.pages;
    $("#pagination").hidden = result.pages <= 1;
    $("#page-label").textContent = `${result.page} / ${result.pages}`;
    $("#previous").disabled = result.page <= 1;
    $("#next").disabled = result.page >= result.pages;
    for (const [name, number] of Object.entries(result.counts)) {
      const target = $(`#count-${name}`);
      if (target) target.textContent = number;
    }
    knownTags = result.tags;
    const oldTag = $("#tag").value;
    $("#tag").replaceChildren(new Option("Wszystkie tagi", ""), ...result.tags.map(tag => new Option(tag, tag)));
    $("#tag").value = oldTag;
    const params = query();
    if (params.get("page") === "1") params.delete("page");
    if (params.get("variant") === COMBINED_VARIANT) params.delete("variant");
    history.replaceState(null, "", params.size ? `/?${params}` : "/");
  } catch (error) {
    if (error.name === "AbortError") return;
    $("#grid").replaceChildren();
    $("#error").textContent = error.message;
    $("#error").hidden = false;
    $("#result-count").textContent = "Nie udało się wczytać";
  } finally {
    if (listingRequest === controller) $("#grid").setAttribute("aria-busy", "false");
  }
}
function refresh() { state.page = 1; loadRecipes(); }
function updateControls() {
  const dishTab = state.meal ? "" : $("#dish").value;
  document.querySelectorAll("[data-dish-tab]").forEach(button => {
    const active = button.dataset.dishTab === dishTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const dishTabActive = Boolean(document.querySelector("[data-dish-tab].active"));
  document.querySelectorAll("[data-meal]").forEach(button => {
    const active = !dishTabActive && button.dataset.meal === state.meal;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  document.querySelectorAll("[data-collection]").forEach(button => {
    const active = button.dataset.collection === state.collection;
    button.classList.toggle("selected", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("#collection-title").textContent = { all: "Wszystkie przepisy", favorites: "Twoje ulubione", uncategorized: "Bez pory posiłku", hidden: "Ukryte przepisy" }[state.collection];
}
function resetFilters() {
  HTMLFormElement.prototype.reset.call($("#filters"));
  $("#variant").value = COMBINED_VARIANT;
  $("#search").value = "";
  state.meal = "";
  state.collection = "all";
  updateControls();
  refresh();
}
function number(value) { return new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 }).format(value); }
function ingredientText(ingredient, factor = 1) {
  const hasQuantity = ingredient.amount != null || ingredient.metric_amount != null;
  if (ingredient.raw && (factor === 1 || !hasQuantity)) return ingredient.raw;
  const parts = [ingredient.name];
  const quantity = value => {
    const scaled = value * factor;
    return scaled > 0 && scaled < 0.001 ? "< 0,001" : new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 3 }).format(scaled);
  };
  if (ingredient.amount != null) parts.push(`${quantity(ingredient.amount)} ${ingredient.unit || ""}`.trim());
  if (ingredient.metric_amount != null) parts.push(`${quantity(ingredient.metric_amount)} ${ingredient.metric_unit}`);
  return parts.join(" — ");
}
function renderIngredientList(list, ingredients, factor) {
  list.replaceChildren();
  let group = null;
  ingredients.forEach(ingredient => {
    if (ingredient.group && ingredient.group !== group) list.append(element("li", "ingredient-group", ingredient.group));
    group = ingredient.group;
    list.append(element("li", "", ingredientText(ingredient, factor)));
  });
}
function sourceBlock(source) {
  if (!source) return null;
  const block = element("p", "source");
  if (source.url) {
    try {
      const url = new URL(source.url);
      if (["https:", "http:"].includes(url.protocol)) {
        const link = element("a", "", "Otwórz źródło przepisu ↗");
        link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
        block.append(link);
      }
    } catch { /* Malformed source URLs are displayed as plain text below. */ }
  }
  if (!block.childNodes.length) block.textContent = `Źródło: ${source.parser === "respo" ? "Respo · " : ""}${source.file || source.url || source.parser}`;
  if (source.page) block.append(document.createTextNode(` · strona ${source.page}`));
  return block;
}
function displayedVariant(recipe, kind) {
  return kind === COMBINED_VARIANT ? recipe.combined_variant : recipe.variants[kind];
}
function variantMergeNotice(recipe) {
  const notice = element("section", "variant-merge-notice");
  notice.setAttribute("aria-label", "Łączenie identycznych wariantów");
  const message = element("p", "", "Warianty kobiety i mężczyzny są identyczne. Możesz je złączyć we Wspólne.");
  message.setAttribute("role", "note");
  const error = element("p", "error"); error.setAttribute("role", "alert"); error.hidden = true;
  const merge = element("button", "secondary", "Złącz"); merge.type = "button";
  merge.addEventListener("click", async () => {
    merge.disabled = true; error.hidden = true;
    try {
      await pendingTagSave;
      if (detailRecipe?.id !== recipe.id) return;
      const response = await fetch(`/api/recipes/${encodeURIComponent(recipe.id)}/merge-variants`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updated_at: detailRecipe.updated_at })
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Nie udało się złączyć wariantów.");
      await loadRecipes();
      if (detailRecipe?.id === recipe.id) await openRecipe(recipe.id);
    } catch (failure) { error.textContent = failure.message; error.hidden = false; }
    finally { merge.disabled = false; }
  });
  notice.append(message, merge, error);
  return notice;
}
function renderDetail() {
  const recipe = detailRecipe;
  const variant = displayedVariant(recipe, selectedVariant);
  const servings = Math.min(displayedServings ?? variant.servings, 20);
  displayedServings = servings;
  const factor = servings / variant.servings;
  const content = $("#detail-content");
  content.replaceChildren();
  if (recipe.image_url) {
    const image = element("img", "detail-hero");
    image.src = recipe.image_url; image.alt = recipe.title;
    image.addEventListener("error", () => { image.src = "/empty_dish.png"; }, { once: true });
    content.append(image);
  }
  const inner = element("div", "detail-inner");
  inner.append(badges(recipe.effective_meal_types, recipe.effective_dish_types));
  const title = element("h2", "", recipe.title); title.id = "detail-title";
  inner.append(title);
  const edit = element("button", "primary", "Edytuj przepis");
  edit.type = "button";
  edit.addEventListener("click", async () => {
    edit.disabled = true;
    try {
      await pendingTagSave.catch(() => {});
      openEditor(await request(`/api/recipes/${encodeURIComponent(recipe.id)}`));
    } catch (failure) {
      const notice = element("p", "error", failure.message); notice.setAttribute("role", "alert");
      actions.insertAdjacentElement("afterend", notice);
    } finally { edit.disabled = false; }
  });
  const actions = element("div", "detail-actions");
  const shoppingButton = element("button", "secondary", "Dodaj do listy zakupów");
  shoppingButton.type = "button";
  let shoppingNotice = null;
  shoppingButton.addEventListener("click", async () => {
    if ($("#detail-servings").getAttribute("aria-invalid") === "true") return;
    shoppingButton.disabled = true; shoppingNotice?.remove();
    const count = displayedServings ?? variant.servings;
    try {
      await addRecipeToShopping(recipe, selectedVariant, count);
      shoppingNotice = element("p", "shopping-notice", `Dodano składniki dla ${number(count)} porcji do listy zakupów. `);
      shoppingNotice.setAttribute("role", "status");
      const show = element("button", "link-button", "Pokaż listę"); show.type = "button";
      show.addEventListener("click", openShopping);
      shoppingNotice.append(show);
    } catch (failure) {
      shoppingNotice = element("p", "error", failure.message); shoppingNotice.setAttribute("role", "alert");
    } finally { shoppingButton.disabled = false; }
    actions.insertAdjacentElement("afterend", shoppingNotice);
  });
  actions.append(edit, favoriteButton(recipe), metadataButton(recipe, "hidden", "Przywróć przepis", "Ukryj przepis"), shoppingButton); inner.append(actions);
  if (recipe.can_merge_variants) inner.append(variantMergeNotice(recipe));
  const tabs = element("div", "variant-tabs"); tabs.setAttribute("aria-label", "Wariant przepisu");
  const storedKinds = Object.keys(recipe.variants);
  const sharedOnly = storedKinds.length === 1 && storedKinds[0] === "family";
  const tabKinds = sharedOnly ? storedKinds : [COMBINED_VARIANT, ...storedKinds];
  for (const key of tabKinds) {
    const tab = element("button", key === selectedVariant ? "active" : "", labels[key]);
    tab.type = "button";
    tab.disabled = key === COMBINED_VARIANT && !recipe.combined_variant;
    tab.setAttribute("aria-pressed", String(key === selectedVariant));
    tab.addEventListener("click", () => {
      selectedVariant = key; displayedServings = displayedVariant(recipe, key).servings; renderDetail();
    });
    tabs.append(tab);
  }
  inner.append(tabs);
  if (!recipe.combined_variant && !sharedOnly) {
    const reason = recipe.variants.male && recipe.variants.female
      ? "różnice w składnikach lub krokach." : "brak wariantu kobiety lub mężczyzny.";
    const warning = element("p", "variant-warning detail-hint", `Dla dwojga niedostępne: ${reason}`);
    warning.setAttribute("role", "note"); inner.append(warning);
  } else if (selectedVariant === COMBINED_VARIANT) {
    inner.append(element("p", "detail-hint", "Dwie porcje to jedna kobiety i jedna mężczyzny. Zmiana liczby porcji skaluje oba warianty proporcjonalnie."));
  }
  const portions = element("div", "portion-controls");
  const portionLabel = element("label", "", "Liczba porcji"); portionLabel.htmlFor = "detail-servings";
  const portionInput = element("input"); portionInput.id = "detail-servings";
  portionInput.type = "number"; portionInput.min = "0"; portionInput.max = "20"; portionInput.step = "any"; portionInput.inputMode = "decimal"; portionInput.value = servings;
  const decrease = element("button", "secondary portion-step", "−"); decrease.type = "button";
  decrease.setAttribute("aria-label", "Zmniejsz liczbę porcji o 0,5"); decrease.disabled = servings <= 0.5;
  const increase = element("button", "secondary portion-step", "+"); increase.type = "button";
  increase.setAttribute("aria-label", "Zwiększ liczbę porcji o 0,5"); increase.disabled = servings >= 20;
  portionInput.setAttribute("aria-describedby", "portion-hint portion-error");
  const portionError = element("p", "error"); portionError.id = "portion-error"; portionError.hidden = true; portionError.setAttribute("role", "alert");
  portionInput.addEventListener("change", () => {
    const value = Number(portionInput.value);
    const ratio = value / variant.servings;
    const amounts = [...variant.ingredients.flatMap(ingredient => [ingredient.amount, ingredient.metric_amount]), ...Object.values(variant.nutrition || {})];
    if (!Number.isFinite(value) || value <= 0 || value > 20 || amounts.some(amount => amount != null && !Number.isFinite(amount * ratio))) {
      portionError.textContent = "Podaj liczbę porcji większą od 0 i nie większą niż 20.";
      portionError.hidden = false; portionInput.setAttribute("aria-invalid", "true"); return;
    }
    displayedServings = value;
    decrease.disabled = value <= 0.5; increase.disabled = value >= 20;
    portionError.hidden = true; portionInput.removeAttribute("aria-invalid");
    servingSummary.textContent = servingDescription(value);
    renderIngredientList(list, variant.ingredients, ratio);
    inner.querySelectorAll(".nutrition strong").forEach((item, index) => {
      item.textContent = number(variant.nutrition[NUTRITION_FIELDS[index][0]] * ratio);
    });
  });
  for (const [button, delta] of [[decrease, -0.5], [increase, 0.5]]) {
    button.addEventListener("click", () => {
      const current = Number(portionInput.value);
      if (Number.isFinite(current) && current > 0 && current <= 20) portionInput.value = Math.min(20, Number((current + delta).toPrecision(12)));
      portionInput.dispatchEvent(new Event("change"));
    });
  }
  portions.append(portionLabel, decrease, portionInput, increase); inner.append(portions, portionError);
  const portionHint = element("p", "detail-hint", "Przeliczenie nie zmienia zapisanego przepisu. Składniki bez podanej ilości dobierz do smaku. Ilości w opisie przygotowania pozostają bez zmian.");
  portionHint.id = "portion-hint"; inner.append(portionHint);
  const servingDescription = count => `Składniki i wartości dla ${count} porcji (przepis bazowy: ${variant.servings}).${recipe.user.preparation_minutes ? ` Czas przygotowania: ${recipe.user.preparation_minutes} min.` : ""}`;
  const servingSummary = element("p", "detail-hint", servingDescription(servings)); inner.append(servingSummary);
  if (variant.nutrition) {
    const nutrition = element("div", "nutrition");
    for (const [key, , label] of NUTRITION_FIELDS) {
      const item = element("div");
      item.append(element("strong", "", number(variant.nutrition[key] * factor)), element("span", "", label));
      nutrition.append(item);
    }
    inner.append(nutrition);
    if (variant.nutrition_estimated) {
      const label = selectedVariant === COMBINED_VARIANT ? "Zawiera wartości szacowane przez AI" : AI_NUTRITION_LABEL;
      inner.append(element("p", "detail-hint", label));
    }
  } else inner.append(element("p", "detail-hint", "Brak wartości odżywczych."));
  const columns = element("div", "detail-columns");
  const ingredients = element("section");
  ingredients.append(element("h3", "", "Składniki"));
  const list = element("ul", "ingredients");
  renderIngredientList(list, variant.ingredients, factor);
  ingredients.append(list);
  const preparation = element("section");
  preparation.append(element("h3", "", "Przygotowanie"));
  const steps = element("ol", "steps");
  (variant.steps || recipe.steps).forEach(step => steps.append(element("li", "", step)));
  preparation.append(steps); columns.append(ingredients, preparation); inner.append(columns);
  if (recipe.suggested_batch_portions) inner.append(element("p", "detail-hint", `Wskazówka ze źródła: przygotuj od razu ${recipe.suggested_batch_portions} porcji.`));
  for (const [heading, texts] of [["Wskazówki", recipe.notes], ["Twoje notatki", recipe.user.notes ? [recipe.user.notes] : []]]) {
    if (!texts.length) continue;
    const notes = element("section", "notes"); notes.append(element("h3", "", heading));
    texts.forEach(text => notes.append(element("p", "", text))); inner.append(notes);
  }
  const tags = element("section", "notes detail-tags");
  tags.append(tagEditor("detail-tags", recipe.user.tags, values => saveRecipeTags(recipe.id, values)));
  inner.append(tags);
  const sources = selectedVariant === COMBINED_VARIANT
    ? [recipe.variants.female.source, recipe.variants.male.source]
    : selectedVariant === "family" ? recipe.shared_sources || [variant.source] : [variant.source];
  for (const value of sources) {
    const source = sourceBlock(value); if (source) inner.append(source);
  }
  content.append(inner);
}
async function openRecipe(id) {
  detailRequest?.abort();
  detailRequest = new AbortController();
  $("#detail-content").replaceChildren(element("p", "loading", "Wczytywanie przepisu…"));
  if (!$("#detail").open) $("#detail").showModal();
  try {
    const recipe = await request(`/api/recipes/${encodeURIComponent(id)}`, detailRequest.signal);
    detailRecipe = recipe;
    const preferred = $("#variant").value;
    selectedVariant = displayedVariant(recipe, preferred) ? preferred : Object.keys(recipe.variants)[0];
    displayedServings = displayedVariant(recipe, selectedVariant).servings;
    renderDetail();
  } catch (error) {
    if (error.name !== "AbortError") $("#detail-content").replaceChildren(element("p", "error", error.message));
  }
}
$("#filters").addEventListener("submit", event => event.preventDefault());
$("#filters").addEventListener("change", () => { updateControls(); refresh(); });
$("#search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(refresh, 220); });
document.querySelectorAll("[data-meal]").forEach(button => button.addEventListener("click", () => {
  state.meal = button.dataset.meal;
  if (state.meal && state.collection === "uncategorized") state.collection = "all";
  if (!state.meal && document.querySelector(`[data-dish-tab="${CSS.escape($("#dish").value)}"]`)) $("#dish").value = "";
  updateControls(); refresh();
}));
document.querySelectorAll("[data-dish-tab]").forEach(button => button.addEventListener("click", () => {
  state.meal = "";
  $("#dish").value = button.dataset.dishTab;
  updateControls(); refresh();
}));
document.querySelectorAll("[data-collection]").forEach(button => button.addEventListener("click", () => {
  state.collection = button.dataset.collection;
  if (state.collection === "uncategorized") state.meal = "";
  updateControls(); refresh();
}));
$("#reset").addEventListener("click", resetFilters);
$("#empty-reset").addEventListener("click", resetFilters);
$("#previous").addEventListener("click", () => { state.page--; loadRecipes(); $("#main").scrollIntoView({ behavior: "smooth" }); });
$("#next").addEventListener("click", () => { state.page++; loadRecipes(); $("#main").scrollIntoView({ behavior: "smooth" }); });
$("#close-detail").addEventListener("click", () => $("#detail").close());
$("#detail").addEventListener("close", () => detailRequest?.abort());
$("#detail").addEventListener("click", event => { if (event.target === $("#detail")) {
  const rect = $("#detail").getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) $("#detail").close();
} });
document.addEventListener("keydown", event => {
  if (event.key === "/" && !$("#detail").open && !$("#editor").open && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { event.preventDefault(); $("#search").focus(); }
});
const initial = new URLSearchParams(location.search);
$("#search").value = initial.get("q") || "";
$("#variant").value = initial.get("variant") || COMBINED_VARIANT;
$("#dish").value = initial.get("dish") || "";
if (initial.get("tag")) $("#tag").append(new Option(initial.get("tag"), initial.get("tag"), true, true));
state.meal = ["breakfast", "lunch", "dinner", "snack"].includes(initial.get("meal")) ? initial.get("meal") : "";
state.collection = initial.get("hidden") === "1" ? "hidden" : initial.get("favorite") === "1" ? "favorites" : initial.get("uncategorized") === "1" ? "uncategorized" : "all";
state.page = /^\d+$/.test(initial.get("page") || "") ? Math.max(1, Number(initial.get("page"))) : 1;
updateControls();
loadRecipes();

let editingRecipe = null;
let previewUrl = null;
let editorFieldSequence = 0;
function editorField(parent, id, title, value = "", type = "text") {
  const label = element("label", "", title); label.htmlFor = id;
  const input = element(type === "textarea" ? "textarea" : "input");
  input.id = id; input.name = id; input.value = value ?? "";
  if (type !== "textarea") input.type = type;
  if (type === "number") { input.min = "0"; input.step = "any"; }
  parent.append(label, input);
  return input;
}
function categoryFields(form, name, title, values, choices) {
  const fieldset = element("fieldset", "editor-checks");
  fieldset.append(element("legend", "", title));
  choices.forEach(value => {
    const label = element("label"); const input = element("input");
    input.type = "checkbox"; input.name = name; input.value = value;
    input.checked = values.includes(value);
    label.append(input, document.createTextNode(labels[value])); fieldset.append(label);
  });
  form.append(fieldset);
}
function rowButton(title, action) {
  const button = element("button", "secondary", title); button.type = "button";
  button.addEventListener("click", action); return button;
}
function ingredientFields(parent, kind, ingredients) {
  parent.append(element("h3", "", "Składniki"));
  const units = element("datalist"); units.id = `${kind}-units`;
  for (const unit of ["g", "ml", "kg", "l", "łyżka", "łyżeczka", "szklanka", "szt.", "szczypta", "opakowanie"]) units.append(new Option(unit, unit));
  const list = element("div", "ingredient-editor"); parent.append(units, list);
  function add(ingredient = {}) {
    const row = element("div", "ingredient-row"); row.originalIngredient = ingredient;
    const id = `${kind}-ingredient-${++editorFieldSequence}`;
    const nameBox = element("div"); const amountBox = element("div"); const unitBox = element("div");
    const name = editorField(nameBox, `${id}-name`, "Nazwa składnika", ingredient.name); name.required = true; name.dataset.field = "name";
    const amount = editorField(amountBox, `${id}-amount`, "Ilość", ingredient.amount, "number"); amount.dataset.field = "amount";
    const unit = editorField(unitBox, `${id}-unit`, "Jednostka", ingredient.unit); unit.dataset.field = "unit"; unit.setAttribute("list", units.id); unit.placeholder = "Wybierz lub wpisz";
    const remove = rowButton("×", () => {
      if (list.children.length > 1) row.remove();
      else { name.value = ""; amount.value = ""; unit.value = ""; row.originalIngredient = {}; row.querySelector(".ingredient-context")?.remove(); name.focus(); }
    });
    remove.className = "remove-ingredient"; remove.title = "Usuń składnik"; remove.setAttribute("aria-label", "Usuń składnik");
    row.append(nameBox, amountBox, unitBox, remove);
    if (ingredient.raw || ingredient.metric_amount != null || ingredient.group) row.append(element("p", "detail-hint ingredient-context", [ingredient.group, ingredientText(ingredient)].filter(Boolean).join(" · ")));
    list.append(row); return name;
  }
  (ingredients.length ? ingredients : [{}]).forEach(add);
  parent.append(rowButton("+ Dodaj składnik", () => add().focus()));
}
function readIngredients(fieldset) {
  return [...fieldset.querySelectorAll(".ingredient-row")].map(row => {
    const original = row.originalIngredient;
    const name = row.querySelector('[data-field="name"]').value.trim();
    const amountText = row.querySelector('[data-field="amount"]').value;
    const amount = amountText === "" ? null : Number(amountText);
    const unit = row.querySelector('[data-field="unit"]').value.trim() || null;
    if (!name) throw new Error("Podaj nazwę każdego składnika.");
    const quantityChanged = amount !== (original.amount ?? null) || unit !== (original.unit || null);
    if (name === original.name && !quantityChanged) return original;
    // An imported metric conversion is tied to the original ingredient and household amount.
    const metric = quantityChanged || amount != null ? { metric_amount: null, metric_unit: null } : {};
    return { ...original, ...metric, name, amount, unit, raw: null };
  });
}
function stepFields(parent, kind, steps) {
  parent.append(element("h3", "", "Przygotowanie"), element("p", "detail-hint", "Przeciągnij uchwyt ⋮⋮, aby zmienić kolejność, lub użyj przycisków ↑ i ↓."));
  const list = element("ol", "step-editor"); list.setAttribute("aria-live", "polite"); parent.append(list);
  let dragged = null;
  function renumber() {
    [...list.children].forEach((row, index) => {
      row.querySelector("label").textContent = `Krok ${index + 1}`;
      row.querySelector('[data-move="up"]').disabled = index === 0;
      row.querySelector('[data-move="down"]').disabled = index === list.children.length - 1;
    });
  }
  function add(text = "") {
    const row = element("li", "step-row");
    const handle = element("span", "drag-handle", "⋮⋮"); handle.draggable = true; handle.title = "Przeciągnij krok";
    handle.addEventListener("dragstart", event => { dragged = row; event.dataTransfer.setData("text/plain", "step"); event.dataTransfer.effectAllowed = "move"; row.classList.add("dragging"); });
    handle.addEventListener("dragend", () => { dragged = null; row.classList.remove("dragging"); });
    const box = element("div", "step-content");
    const input = editorField(box, `${kind}-step-${++editorFieldSequence}`, "Krok", text, "textarea"); input.required = true;
    const controls = element("div", "row-actions");
    const up = rowButton("↑", () => { if (row.previousElementSibling) list.insertBefore(row, row.previousElementSibling); renumber(); up.focus(); }); up.dataset.move = "up"; up.setAttribute("aria-label", "Przesuń krok w górę");
    const down = rowButton("↓", () => { if (row.nextElementSibling) list.insertBefore(row.nextElementSibling, row); renumber(); down.focus(); }); down.dataset.move = "down"; down.setAttribute("aria-label", "Przesuń krok w dół");
    controls.append(up, down, rowButton("Usuń krok", () => { if (list.children.length > 1) row.remove(); else input.value = ""; renumber(); }));
    row.append(handle, box, controls); list.append(row);
    row.addEventListener("dragover", event => { if (dragged && dragged !== row) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } });
    row.addEventListener("drop", event => {
      if (!dragged || dragged === row) return;
      event.preventDefault();
      const after = event.clientY > row.getBoundingClientRect().top + row.getBoundingClientRect().height / 2;
      list.insertBefore(dragged, after ? row.nextElementSibling : row); renumber();
    });
    renumber(); return input;
  }
  (steps.length ? steps : [""]).forEach(add);
  parent.append(rowButton("+ Dodaj krok", () => add().focus()));
}
function readNutritionValues(fieldset) {
  return NUTRITION_FIELDS.map(([key]) => [key, fieldset.querySelector('[data-nutrition="' + key + '"]').value]);
}
function matchesEstimatedNutrition(values, estimate) {
  return estimate != null && values.every(([key, value]) => value !== "" && Number(value) === estimate[key]);
}
function nutritionEstimateInput(fieldset, servings) {
  if (!servings.validity.valid || !Number.isSafeInteger(servings.valueAsNumber)) {
    throw new Error("Podaj prawidłową liczbę porcji.");
  }
  const amounts = fieldset.querySelectorAll('[data-field="amount"]');
  if ([...amounts].some(input => !input.validity.valid)) throw new Error("Sprawdź ilości składników.");
  return JSON.stringify({ servings: servings.valueAsNumber, ingredients: readIngredients(fieldset) });
}
function addNutritionEstimateControls(fieldset, servings, available, updateOrigin) {
  const message = element("p", "detail-hint", available ? "" : "Aby włączyć, ustaw openai_api_key na serwerze.");
  message.id = fieldset.dataset.kind + "-nutrition-status";
  message.setAttribute("role", "status");
  const button = rowButton("Oszacuj wartości odżywcze z AI", async () => {
    button.disabled = true;
    message.textContent = "Szacowanie wartości odżywczych…";
    try {
      const input = nutritionEstimateInput(fieldset, servings);
      const previousValues = JSON.stringify(readNutritionValues(fieldset));
      const response = await fetch("/api/nutrition/estimate", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: input
      });
      const estimate = await response.json();
      if (!response.ok) throw new Error(estimate.error || "Nie udało się oszacować wartości odżywczych.");
      if (!fieldset.closest("dialog")?.open) return;
      if (JSON.stringify(readNutritionValues(fieldset)) !== previousValues || nutritionEstimateInput(fieldset, servings) !== input) {
        message.textContent = "Dane zmieniły się podczas szacowania. Spróbuj ponownie.";
        return;
      }
      for (const field of fieldset.querySelectorAll("[data-nutrition]")) {
        field.value = estimate[field.dataset.nutrition];
      }
      fieldset.estimatedNutrition = estimate;
      updateOrigin();
      message.textContent = "Uzupełniono pola. Zapisz przepis, aby zachować wartości.";
    } catch (failure) {
      message.textContent = failure.message;
    } finally {
      button.disabled = false;
    }
  });
  button.disabled = !available;
  button.setAttribute("aria-describedby", message.id);
  fieldset.append(button, message);
}
function variantFields(form, kind, variant, steps, recipe) {
  const fieldset = element("fieldset", "editor-variant");
  fieldset.dataset.kind = kind;
  fieldset.originalVariant = variant;
  fieldset.estimatedNutrition = variant.nutrition_estimated ? variant.nutrition : null;
  fieldset.append(element("legend", "", labels[kind]));
  const servings = editorField(fieldset, `${kind}-servings`, "Liczba porcji", variant.servings, "number");
  servings.required = true; servings.min = "1"; servings.step = "1";
  ingredientFields(fieldset, kind, variant.ingredients);
  stepFields(fieldset, kind, variant.steps || steps);
  const nutrition = element("div", "editor-nutrition");
  for (const [key, title] of NUTRITION_FIELDS) {
    const item = element("div");
    const field = editorField(item, kind + "-" + key, title, variant.nutrition?.[key], "number");
    field.dataset.nutrition = key;
    nutrition.append(item);
  }
  fieldset.append(element("p", "detail-hint", "Wartości odżywcze dla wszystkich porcji: wypełnij wszystkie cztery pola albo zostaw wszystkie puste."), nutrition);
  const origin = element("p", "detail-hint", AI_NUTRITION_LABEL);
  const updateOrigin = () => {
    origin.hidden = !matchesEstimatedNutrition(readNutritionValues(fieldset), fieldset.estimatedNutrition);
  };
  nutrition.addEventListener("input", updateOrigin);
  fieldset.append(origin);
  updateOrigin();
  if (recipe) addNutritionEstimateControls(fieldset, servings, recipe.nutrition_ai_available, updateOrigin);
  form.append(fieldset);
  return fieldset;
}
function readVariant(fieldset, recipe) {
  const kind = fieldset.dataset.kind;
  const original = fieldset.originalVariant;
  const ingredients = readIngredients(fieldset);
  const values = readNutritionValues(fieldset);
  if (values.some(([, value]) => value !== "") && values.some(([, value]) => value === "")) throw new Error("Uzupełnij wszystkie wartości odżywcze lub wyczyść wszystkie cztery pola.");
  const nutrition = values.every(([, value]) => value === "") ? null : Object.fromEntries(values.map(([key, value]) => [key, Number(value)]));
  const steps = [...fieldset.querySelectorAll(".step-editor textarea")].map(input => input.value.trim());
  if (steps.some(step => !step)) throw new Error("Uzupełnij treść każdego kroku.");
  const unchangedSteps = JSON.stringify(steps) === JSON.stringify(original.steps || recipe?.steps);
  return {
    ...original, servings: Number($(`#${kind}-servings`).value), ingredients, nutrition,
    nutrition_estimated: matchesEstimatedNutrition(values, fieldset.estimatedNutrition),
    steps: unchangedSteps ? original.steps ?? null : steps
  };
}
function addVariantControls(container, recipe) {
  const controls = element("section", "editor-variant-controls");
  controls.setAttribute("aria-label", "Dodawanie wariantów");
  controls.append(element("h3", "", "Dodaj brakujący wariant"));
  const label = element("label", "", "Skopiuj dane z wariantu"); label.htmlFor = "variant-copy-source";
  const source = element("select"); source.id = "variant-copy-source";
  const buttons = element("div", "editor-variant-buttons");
  const kinds = ["family", "female", "male"];
  const refresh = () => {
    const previous = source.value;
    const present = [...container.querySelectorAll(".editor-variant")].map(fieldset => fieldset.dataset.kind);
    source.replaceChildren(...kinds.filter(kind => present.includes(kind)).map(kind => new Option(labels[kind], kind)));
    if (present.includes(previous)) source.value = previous;
    buttons.replaceChildren();
    for (const kind of kinds.filter(kind => !present.includes(kind))) {
      const add = rowButton(`+ Dodaj wariant: ${labels[kind]}`, () => {
        const error = $("#editor-error"); error.hidden = true;
        try {
          const original = container.querySelector(`[data-kind="${source.value}"]`);
          const copied = structuredClone(readVariant(original, recipe));
          const fieldset = variantFields(container, kind, copied, recipe.steps, recipe);
          const remove = rowButton(`Usuń dodawany wariant: ${labels[kind]}`, () => {
            fieldset.remove(); refresh(); source.focus();
          });
          fieldset.append(remove);
          refresh();
          fieldset.querySelector("input").focus();
        } catch (failure) { error.textContent = failure.message; error.hidden = false; }
      });
      buttons.append(add);
    }
    controls.hidden = present.length === kinds.length;
  };
  controls.append(label, source, buttons, element("p", "detail-hint", "Nowy wariant kopiuje dane wybranego wariantu. Możesz je dostosować przed zapisaniem przepisu."));
  container.before(controls);
  refresh();
}
function openEditor(recipe = null, chefDraft = null) {
  editingRecipe = recipe;
  const form = $("#recipe-form"); form.replaceChildren();
  $("#editor-title").textContent = chefDraft ? "Zatwierdź przepis Kucharza" : recipe ? "Edytuj przepis" : "Dodaj przepis";
  form.chefDraft = chefDraft;
  if (chefDraft) {
    form.append(element("p", "detail-hint", "Sprawdź składniki i kroki. Możesz je poprawić przed dodaniem przepisu."));
    recipe.notes.forEach(note => form.append(element("p", "detail-hint", note)));
  }
  editorField(form, "edit-title", "Nazwa przepisu", recipe?.title).required = true;
  categoryFields(form, "edit-meals", "Pora posiłku", recipe?.effective_meal_types || [], ["breakfast", "lunch", "dinner", "snack"]);
  categoryFields(form, "edit-dishes", "Rodzaj potrawy", recipe?.effective_dish_types || [], ["main", "soup", "salad", "cake", "bread", "dessert", "other"]);
  const duration = element("div", "editor-duration");
  const minutes = recipe?.user.preparation_minutes;
  for (const [id, title, value] of [["edit-hours", "Godziny", minutes == null ? "" : Math.floor(minutes / 60)], ["edit-minutes", "Minuty", minutes == null ? "" : minutes % 60]]) {
    const box = element("div"); const input = editorField(box, id, title, value, "number"); input.step = "1";
    if (id === "edit-minutes") input.max = "59";
    duration.append(box);
  }
  form.append(element("h3", "", "Czas przygotowania"), duration);
  const tags = tagEditor("edit-tags", recipe?.user.tags || []); tags.id = "edit-tags-box"; form.append(tags);
  editorField(form, "edit-notes", "Twoje notatki", recipe?.user.notes, "textarea");
  const favorite = editorField(form, "edit-favorite", "Ulubiony", "", "checkbox"); favorite.checked = recipe?.user.favorite || false;
  const variants = recipe?.variants || { family: { servings: 1, ingredients: [], nutrition: null } };
  const variantContainer = element("section", "editor-variants"); form.append(variantContainer);
  for (const [kind, variant] of Object.entries(variants)) variantFields(variantContainer, kind, variant, recipe?.steps || [], recipe);
  if (recipe) addVariantControls(variantContainer, recipe);
  if (!recipe) {
    const label = element("label", "", "Wariant nowego przepisu"); label.htmlFor = "edit-kind";
    const select = element("select"); select.id = "edit-kind";
    for (const kind of ["family", "female", "male"]) select.append(new Option(labels[kind], kind));
    select.addEventListener("change", () => { form.querySelector(".editor-variant legend").textContent = labels[select.value]; });
    form.append(label, select);
  }
  const upload = editorField(form, "edit-image", "Zdjęcie (PNG, JPG, WebP, GIF; maks. 8 MB)", "", "file");
  upload.accept = "image/png,image/jpeg,image/webp,image/gif";
  const preview = element("img", "editor-preview"); preview.alt = "Podgląd zdjęcia";
  preview.src = recipe?.image_url || "/empty_dish.png"; form.append(preview);
  upload.addEventListener("change", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    const file = upload.files[0]; previewUrl = file ? URL.createObjectURL(file) : null;
    preview.src = previewUrl || recipe?.image_url || "/empty_dish.png";
  });
  const footer = element("div", "editor-footer");
  const error = element("p", "error"); error.id = "editor-error"; error.hidden = true; error.setAttribute("role", "alert");
  const actions = element("div", "editor-actions");
  const save = element("button", "primary", chefDraft ? "Dodaj do przepisów" : "Zapisz przepis"); save.type = "submit";
  const cancel = element("button", "secondary", "Anuluj"); cancel.type = "button";
  cancel.addEventListener("click", () => $("#editor").close());
  actions.append(save, cancel); footer.append(error, actions); form.append(footer);
  $("#editor").showModal();
}
function readUpload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(new Error("Nie udało się odczytać zdjęcia."));
    reader.readAsDataURL(file);
  });
}
$("#add-recipe").addEventListener("click", () => openEditor());
$("#editor").addEventListener("close", () => { if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = null; });
$("#recipe-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const save = form.querySelector('[type="submit"]'); const error = $("#editor-error");
  error.hidden = true; save.disabled = true;
  const checked = name => [...form.querySelectorAll(`input[name="${name}"]:checked`)].map(input => input.value);
  const categories = (name, field) => {
    const values = checked(name);
    const effective = editingRecipe?.[`effective_${field}`];
    return effective && values.length === new Set(effective).size && values.every(value => effective.includes(value))
      ? editingRecipe.user[field] : values;
  };
  try {
    const variants = {};
    for (const fieldset of form.querySelectorAll(".editor-variant")) {
      const kind = fieldset.dataset.kind;
      variants[editingRecipe ? kind : $("#edit-kind").value] = readVariant(fieldset, editingRecipe);
    }
    const preparationMinutes = Number($("#edit-hours").value) * 60 + Number($("#edit-minutes").value);
    if (($("#edit-hours").value !== "" || $("#edit-minutes").value !== "") && (!Number.isSafeInteger(preparationMinutes) || preparationMinutes <= 0)) throw new Error("Czas przygotowania musi wynosić co najmniej minutę lub pozostać pusty.");
    const recipe = {
      title: $("#edit-title").value.trim(),
      steps: (form.chefDraft && Object.values(variants)[0].steps) || editingRecipe?.steps || Object.values(variants)[0].steps,
      variants,
      user: { ...editingRecipe?.user, favorite: $("#edit-favorite").checked,
        notes: $("#edit-notes").value, tags: $("#edit-tags-box").tags(),
        preparation_minutes: preparationMinutes || null,
        meal_types: categories("edit-meals", "meal_types"), dish_types: categories("edit-dishes", "dish_types") }
    };
    const file = $("#edit-image").files[0];
    if (file && file.size > 8000000) throw new Error("Zdjęcie przekracza limit 8 MB.");
    const chef = form.chefDraft;
    if (chef) {
      recipe.notes = [...editingRecipe.notes];
      if (chef.jpeg && !file) recipe.notes.push("Ilustracja wygenerowana przez Kucharza AI.");
    }
    const response = await fetch(editingRecipe && !chef ? `/api/recipes/${encodeURIComponent(editingRecipe.id)}` : "/api/recipes", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipe, updated_at: editingRecipe?.updated_at, upload: file ? await readUpload(file) : chef?.jpeg || null,
        ...(chef ? {chef_draft: chef.id} : {}) })
    });
    const body = await response.json(); if (!response.ok) throw new Error(body.error || "Nie udało się zapisać przepisu.");
    $("#editor").close();
    if (chef) document.dispatchEvent(new Event("chef-saved"));
    await loadRecipes(); await openRecipe(body.id);
    if (body.changed === false) {
      const notice = element("p", "detail-hint", "Brak zmian — przepis pozostał bez zmian.");
      notice.setAttribute("role", "status"); $("#detail-content .detail-inner").prepend(notice);
    }
  } catch (failure) { error.textContent = failure.message; error.hidden = false; }
  finally { save.disabled = false; }
});
