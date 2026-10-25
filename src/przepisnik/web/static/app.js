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
  const placeholder = () => holder.replaceChildren(element("span", "image-placeholder", "P."));
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
    image.addEventListener("error", () => image.remove(), { once: true });
    content.append(image);
  }
  const inner = element("div", "detail-inner");
  inner.append(badges(recipe.effective_meal_types, recipe.effective_dish_types));
  const title = element("h2", "", recipe.title); title.id = "detail-title";
  inner.append(title);
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
  if (event.key === "/" && !$("#detail").open && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { event.preventDefault(); $("#search").focus(); }
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
