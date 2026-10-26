"use strict";
const $ = (selector) => document.querySelector(selector);
const labels = {
  breakfast: "Śniadanie", lunch: "Obiad", dinner: "Kolacja", snack: "Przekąska",
  female: "Kobieta", male: "Mężczyzna", family: "Rodzina",
  main: "Danie główne", soup: "Zupa", salad: "Sałatka", cake: "Ciasto",
  bread: "Chleb", dessert: "Deser", other: "Inne"
};
const state = { meal: "", collection: "all", page: 1, pages: 1 };
let listingRequest = null;
let detailRequest = null;
let detailRecipe = null;
let selectedVariant = "";
let searchTimer;

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
  if (recipe.favorite) {
    const favorite = element("span", "favorite-mark", "♥");
    favorite.setAttribute("aria-label", "Ulubiony przepis");
    image.append(favorite);
  }
  const body = element("div", "card-body");
  body.append(badges(recipe.meal_types, recipe.dish_types), element("h3", "", recipe.title));
  const meta = element("div", "card-meta");
  meta.append(element("span", "", recipe.variants.map(v => labels[v]).join(" · ")));
  if (recipe.minutes) meta.append(element("span", "", `${recipe.minutes} min`));
  else meta.append(element("span", "", "Zobacz przepis ↗"));
  body.append(meta);
  button.append(image, body);
  button.addEventListener("click", () => openRecipe(recipe.id));
  article.append(button);
  return article;
}
function query() {
  const params = new URLSearchParams({ page: String(state.page) });
  for (const [key, value] of Object.entries({ q: $("#search").value.trim(), meal: state.meal,
    variant: $("#variant").value, dish: $("#dish").value, tag: $("#tag").value,
    favorite: state.collection === "favorites" ? "1" : "",
    uncategorized: state.collection === "uncategorized" ? "1" : "" })) {
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
    const oldTag = $("#tag").value;
    $("#tag").replaceChildren(new Option("Wszystkie tagi", ""), ...result.tags.map(tag => new Option(tag, tag)));
    $("#tag").value = oldTag;
    const params = query();
    if (params.get("page") === "1") params.delete("page");
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
  document.querySelectorAll("[data-meal]").forEach(button => {
    const active = button.dataset.meal === state.meal;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  document.querySelectorAll("[data-collection]").forEach(button => {
    const active = button.dataset.collection === state.collection;
    button.classList.toggle("selected", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("#collection-title").textContent = { all: "Wszystkie przepisy", favorites: "Twoje ulubione", uncategorized: "Bez pory posiłku" }[state.collection];
}
function resetFilters() {
  $("#filters").reset();
  $("#search").value = "";
  state.meal = "";
  state.collection = "all";
  updateControls();
  refresh();
}
function number(value) { return new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 }).format(value); }
function ingredientText(ingredient) {
  if (ingredient.raw) return ingredient.raw;
  const parts = [ingredient.name];
  if (ingredient.amount !== null) parts.push(`${number(ingredient.amount)} ${ingredient.unit || ""}`.trim());
  if (ingredient.metric_amount !== null) parts.push(`${number(ingredient.metric_amount)} ${ingredient.metric_unit}`);
  return parts.join(" — ");
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
  if (!block.childNodes.length) block.textContent = `Źródło: ${source.file || source.url || source.parser}`;
  if (source.page) block.append(document.createTextNode(` · strona ${source.page}`));
  return block;
}
function renderDetail() {
  const recipe = detailRecipe;
  const variant = recipe.variants[selectedVariant];
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
  edit.addEventListener("click", () => openEditor(recipe));
  inner.append(edit);
  const tabs = element("div", "variant-tabs"); tabs.setAttribute("aria-label", "Wariant przepisu");
  for (const key of Object.keys(recipe.variants)) {
    const tab = element("button", key === selectedVariant ? "active" : "", labels[key]);
    tab.setAttribute("aria-pressed", String(key === selectedVariant));
    tab.addEventListener("click", () => { selectedVariant = key; renderDetail(); });
    tabs.append(tab);
  }
  inner.append(tabs);
  inner.append(element("p", "detail-hint", `Składniki i wartości dla ${variant.servings} porcji.${recipe.user.preparation_minutes ? ` Czas przygotowania: ${recipe.user.preparation_minutes} min.` : ""}`));
  if (variant.nutrition) {
    const nutrition = element("div", "nutrition");
    for (const [key, label] of [["kcal", "kcal"], ["protein_g", "białko · g"], ["fat_g", "tłuszcz · g"], ["carbs_g", "węglowodany · g"]]) {
      const item = element("div");
      item.append(element("strong", "", number(variant.nutrition[key])), element("span", "", label));
      nutrition.append(item);
    }
    inner.append(nutrition);
  } else inner.append(element("p", "detail-hint", "Brak wartości odżywczych w źródle."));
  const columns = element("div", "detail-columns");
  const ingredients = element("section");
  ingredients.append(element("h3", "", "Składniki"));
  const list = element("ul", "ingredients");
  let group = null;
  variant.ingredients.forEach(ingredient => {
    if (ingredient.group && ingredient.group !== group) list.append(element("li", "ingredient-group", ingredient.group));
    group = ingredient.group;
    list.append(element("li", "", ingredientText(ingredient)));
  });
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
  if (recipe.user.tags.length) inner.append(element("p", "detail-hint", recipe.user.tags.map(tag => `#${tag}`).join("  ")));
  const source = sourceBlock(variant.source); if (source) inner.append(source);
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
    selectedVariant = recipe.variants[$("#variant").value] ? $("#variant").value : Object.keys(recipe.variants)[0];
    renderDetail();
  } catch (error) {
    if (error.name !== "AbortError") $("#detail-content").replaceChildren(element("p", "error", error.message));
  }
}
$("#filters").addEventListener("submit", event => event.preventDefault());
$("#filters").addEventListener("change", refresh);
$("#search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(refresh, 220); });
document.querySelectorAll("[data-meal]").forEach(button => button.addEventListener("click", () => {
  state.meal = button.dataset.meal;
  if (state.meal && state.collection === "uncategorized") state.collection = "all";
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
$("#variant").value = initial.get("variant") || "";
$("#dish").value = initial.get("dish") || "";
if (initial.get("tag")) $("#tag").append(new Option(initial.get("tag"), initial.get("tag"), true, true));
state.meal = ["breakfast", "lunch", "dinner", "snack"].includes(initial.get("meal")) ? initial.get("meal") : "";
state.collection = initial.get("favorite") === "1" ? "favorites" : initial.get("uncategorized") === "1" ? "uncategorized" : "all";
state.page = /^\d+$/.test(initial.get("page") || "") ? Math.max(1, Number(initial.get("page"))) : 1;
updateControls();
loadRecipes();

let editingRecipe = null;
let previewUrl = null;
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
    const id = `${kind}-ingredient-${crypto.randomUUID()}`;
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
    if (name === original.name && amount === (original.amount ?? null) && unit === (original.unit || null)) return original;
    return { ...original, name, amount, unit, raw: null };
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
    const input = editorField(box, `${kind}-step-${crypto.randomUUID()}`, "Krok", text, "textarea"); input.required = true;
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
function variantFields(form, kind, variant, steps) {
  const fieldset = element("fieldset", "editor-variant");
  fieldset.dataset.kind = kind;
  fieldset.append(element("legend", "", labels[kind]));
  const servings = editorField(fieldset, `${kind}-servings`, "Liczba porcji", variant.servings, "number");
  servings.required = true; servings.min = "1"; servings.step = "1";
  ingredientFields(fieldset, kind, variant.ingredients);
  stepFields(fieldset, kind, variant.steps || steps);
  const nutrition = element("div", "editor-nutrition");
  for (const [key, title] of [["kcal", "Kalorie (kcal)"], ["protein_g", "Białko (g)"], ["fat_g", "Tłuszcz (g)"], ["carbs_g", "Węglowodany (g)"]]) {
    const item = element("div"); editorField(item, `${kind}-${key}`, title, variant.nutrition?.[key], "number"); nutrition.append(item);
  }
  fieldset.append(element("p", "detail-hint", "Wartości odżywcze dla wszystkich porcji: wypełnij wszystkie cztery pola albo zostaw wszystkie puste."), nutrition);
  form.append(fieldset);
}
function openEditor(recipe = null) {
  editingRecipe = recipe;
  const form = $("#recipe-form"); form.replaceChildren();
  $("#editor-title").textContent = recipe ? "Edytuj przepis" : "Dodaj przepis";
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
  editorField(form, "edit-tags", "Tagi (oddziel przecinkami)", recipe?.user.tags.join(", "));
  editorField(form, "edit-notes", "Twoje notatki", recipe?.user.notes, "textarea");
  const favorite = editorField(form, "edit-favorite", "Ulubiony", "", "checkbox"); favorite.checked = recipe?.user.favorite || false;
  const variants = recipe?.variants || { family: { servings: 1, ingredients: [], nutrition: null } };
  for (const [kind, variant] of Object.entries(variants)) variantFields(form, kind, variant, recipe?.steps || []);
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
  const error = element("p", "error"); error.id = "editor-error"; error.hidden = true; error.setAttribute("role", "alert");
  const actions = element("div", "editor-actions");
  const save = element("button", "primary", "Zapisz przepis"); save.type = "submit";
  const cancel = element("button", "secondary", "Anuluj"); cancel.type = "button";
  cancel.addEventListener("click", () => $("#editor").close());
  actions.append(save, cancel); form.append(error, actions);
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
  try {
    const variants = {};
    for (const fieldset of form.querySelectorAll(".editor-variant")) {
      const kind = fieldset.dataset.kind;
      const original = editingRecipe?.variants[kind];
      const ingredients = readIngredients(fieldset);
      const values = ["kcal", "protein_g", "fat_g", "carbs_g"].map(key => [key, $(`#${kind}-${key}`).value]);
      if (values.some(([, value]) => value !== "") && values.some(([, value]) => value === "")) throw new Error("Uzupełnij wszystkie wartości odżywcze lub wyczyść wszystkie cztery pola.");
      const nutrition = values.every(([, value]) => value === "") ? null : Object.fromEntries(values.map(([key, value]) => [key, Number(value)]));
      variants[editingRecipe ? kind : $("#edit-kind").value] = {
        ...original, servings: Number($(`#${kind}-servings`).value), ingredients, nutrition,
        steps: [...fieldset.querySelectorAll(".step-editor textarea")].map(input => input.value.trim())
      };
    }
    const preparationMinutes = Number($("#edit-hours").value) * 60 + Number($("#edit-minutes").value);
    if (($("#edit-hours").value !== "" || $("#edit-minutes").value !== "") && (!Number.isSafeInteger(preparationMinutes) || preparationMinutes <= 0)) throw new Error("Czas przygotowania musi wynosić co najmniej minutę lub pozostać pusty.");
    if (Object.values(variants).some(variant => variant.steps.some(step => !step))) throw new Error("Uzupełnij treść każdego kroku.");
    const recipe = {
      title: $("#edit-title").value.trim(),
      steps: editingRecipe?.steps || Object.values(variants)[0].steps,
      variants,
      user: { ...editingRecipe?.user, favorite: $("#edit-favorite").checked,
        notes: $("#edit-notes").value, tags: $("#edit-tags").value.split(",").map(tag => tag.trim()).filter(Boolean),
        preparation_minutes: preparationMinutes || null,
        meal_types: checked("edit-meals"), dish_types: checked("edit-dishes") }
    };
    const file = $("#edit-image").files[0];
    if (file && file.size > 8000000) throw new Error("Zdjęcie przekracza limit 8 MB.");
    const response = await fetch(editingRecipe ? `/api/recipes/${encodeURIComponent(editingRecipe.id)}` : "/api/recipes", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipe, updated_at: editingRecipe?.updated_at, upload: file ? await readUpload(file) : null })
    });
    const body = await response.json(); if (!response.ok) throw new Error(body.error || "Nie udało się zapisać przepisu.");
    $("#editor").close();
    await loadRecipes(); await openRecipe(body.id);
  } catch (failure) { error.textContent = failure.message; error.hidden = false; }
  finally { save.disabled = false; }
});
