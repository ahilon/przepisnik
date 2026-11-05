"use strict";

let shoppingState = { revision: 0, items: [] };
let shoppingBusy = false;

function shoppingMessage(message = "", error = false) {
  $("#shopping-error").hidden = !error;
  $("#shopping-error").textContent = error ? message : "";
  $("#shopping-status").textContent = error ? "" : message;
}
function shoppingBusyState(busy) {
  shoppingBusy = busy;
  $("#shopping").querySelectorAll("input, button:not(#close-shopping)").forEach(control => { control.disabled = busy; });
  $("#clear-shopping").disabled = busy || shoppingState.items.length === 0;
}
async function loadShopping() {
  const result = await request("/api/shopping-list");
  if (result.revision >= shoppingState.revision) shoppingState = result;
  renderShopping();
}
async function openShopping() {
  if (!$("#shopping").open) $("#shopping").showModal();
  shoppingMessage("Wczytywanie listy…");
  try { await loadShopping(); shoppingMessage(); }
  catch (failure) { shoppingMessage(failure.message, true); }
}
async function updateShopping(change) {
  if (shoppingBusy) return false;
  shoppingBusyState(true); shoppingMessage("Zapisywanie…");
  try {
    const proposed = JSON.parse(JSON.stringify(shoppingState));
    change(proposed);
    const response = await fetch("/api/shopping-list", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(proposed)
    });
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 409) await loadShopping();
      throw new Error(result.error || "Nie udało się zapisać listy zakupów.");
    }
    shoppingState = result; renderShopping(); shoppingMessage("Lista zapisana.");
    return true;
  } catch (failure) {
    renderShopping(); shoppingMessage(failure.message, true); return false;
  } finally { shoppingBusyState(false); }
}
function shoppingField(parent, id, title, value, type = "text") {
  const box = element("div", "shopping-field");
  const label = element("label", "", title); label.htmlFor = id;
  const input = element("input"); input.id = id; input.type = type; input.value = value ?? "";
  if (type === "number") { input.min = "0"; input.step = "any"; input.placeholder = "Do ustalenia"; }
  else { input.maxLength = 24; input.setAttribute("list", "shopping-units"); }
  box.append(label, input); parent.append(box); return input;
}
function shoppingRow(item) {
  const row = element("form", `shopping-row${item.checked ? " is-checked" : ""}`); row.dataset.id = item.id;
  const product = element("div", "shopping-product");
  const label = element("label", "shopping-check");
  const checkbox = element("input"); checkbox.type = "checkbox"; checkbox.checked = item.checked;
  checkbox.setAttribute("aria-label", `Mam: ${item.name}`);
  checkbox.addEventListener("change", () => updateShopping(doc => { doc.items.find(entry => entry.id === item.id).checked = checkbox.checked; }));
  label.append(checkbox, element("span", "shopping-product-name", item.name)); product.append(label);
  if (item.source) product.append(element("p", "shopping-source", item.source));
  row.append(product);
  const quantities = element("div", "shopping-quantities");
  const amount = shoppingField(quantities, `amount-${item.id}`, "Ilość", item.amount, "number");
  const unit = shoppingField(quantities, `unit-${item.id}`, "Jednostka", item.unit);
  const actions = element("div", "shopping-row-actions");
  const save = element("button", "secondary", "Zapisz ilość"); save.type = "submit";
  save.setAttribute("aria-label", `Zapisz ilość: ${item.name}`);
  const remove = element("button", "shopping-remove", "Usuń"); remove.type = "button";
  remove.setAttribute("aria-label", `Usuń produkt: ${item.name}`);
  remove.addEventListener("click", () => updateShopping(doc => { doc.items = doc.items.filter(entry => entry.id !== item.id); }));
  actions.append(save, remove); row.append(quantities, actions);
  row.addEventListener("submit", event => {
    event.preventDefault();
    updateShopping(doc => {
      const entry = doc.items.find(entry => entry.id === item.id);
      entry.amount = amount.value === "" ? null : Number(amount.value); entry.unit = unit.value.trim();
    });
  });
  return row;
}
function renderShopping() {
  const items = shoppingState.items;
  $("#shopping-count").textContent = items.filter(item => !item.checked).length;
  const container = $("#shopping-items"); container.replaceChildren();
  if (!items.length) {
    container.append(element("p", "shopping-empty", "Lista jest pusta. Dodaj składniki z przepisu albo wpisz własny produkt poniżej."));
  } else {
    for (const checked of [false, true]) {
      const entries = items.filter(item => item.checked === checked);
      if (!entries.length) continue;
      const section = element("section", "shopping-group");
      section.setAttribute("aria-label", checked ? "Mam już" : "Do kupienia");
      section.append(element("h3", "", `${checked ? "Mam już" : "Do kupienia"} · ${entries.length}`), ...entries.map(shoppingRow));
      container.append(section);
    }
  }
  shoppingBusyState(shoppingBusy);
}
function shoppingId() { return `item-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`; }
function normalizedQuantity(amount, unit) {
  const clean = unit.trim().toLocaleLowerCase("pl-PL");
  if (clean === "kg") return { amount: amount == null ? null : amount * 1000, unit: "g" };
  if (clean === "l") return { amount: amount == null ? null : amount * 1000, unit: "ml" };
  return { amount, unit: clean === "szt" ? "szt." : clean };
}
async function addRecipeToShopping(recipe, kind, servings) {
  try {
    await loadShopping();
    const factor = servings / recipe.variants[kind].servings;
    const success = await updateShopping(doc => {
      for (const ingredient of recipe.variants[kind].ingredients) {
        const metric = ingredient.metric_amount != null;
        const base = metric ? ingredient.metric_amount : ingredient.amount;
        const scaled = base == null ? null : base * factor;
        const quantity = normalizedQuantity(scaled, (metric ? ingredient.metric_unit : ingredient.unit) || "");
        if (quantity.amount != null && !Number.isFinite(quantity.amount)) throw new Error("Nie można przeliczyć ilości tego składnika.");
        const existing = doc.items.find(item => {
          const current = normalizedQuantity(item.amount, item.unit);
          return item.name.trim().toLocaleLowerCase("pl-PL") === ingredient.name.trim().toLocaleLowerCase("pl-PL")
            && current.unit === quantity.unit && (current.amount == null) === (quantity.amount == null);
        });
        if (existing) {
          const current = normalizedQuantity(existing.amount, existing.unit);
          const total = quantity.amount == null ? null : current.amount + quantity.amount;
          if (total != null && !Number.isFinite(total)) throw new Error("Łączna ilość produktu jest zbyt duża.");
          existing.amount = total == null ? null : Number(total.toPrecision(12)); existing.unit = quantity.unit; existing.checked = false;
        } else {
          doc.items.push({ id: shoppingId(), name: ingredient.name, amount: quantity.amount == null ? null : Number(quantity.amount.toPrecision(12)), unit: quantity.unit, checked: false,
            source: `${recipe.title}${base == null && ingredient.raw ? ` · ${ingredient.raw}` : ""}`.slice(0, 300) });
        }
      }
    });
    if (success) { $("#detail").close(); if (!$("#shopping").open) $("#shopping").showModal(); shoppingMessage("Dodano składniki dla wybranej liczby porcji."); }
    else { if (!$("#shopping").open) $("#shopping").showModal(); }
  } catch (failure) {
    if (!$("#shopping").open) $("#shopping").showModal(); shoppingMessage(failure.message, true);
  }
}
$("#open-shopping").addEventListener("click", openShopping);
$("#close-shopping").addEventListener("click", () => $("#shopping").close());
$("#refresh-shopping").addEventListener("click", openShopping);
$("#clear-shopping").addEventListener("click", async () => {
  if (!shoppingState.items.length || shoppingBusy) return;
  if (!window.confirm("Usunąć wszystkie produkty z listy zakupów, również oznaczone jako posiadane?")) return;
  if (await updateShopping(doc => { doc.items = []; })) shoppingMessage("Lista zakupów wyczyszczona.");
});
$("#shopping-add").addEventListener("submit", async event => {
  event.preventDefault();
  const name = $("#shopping-name").value.trim();
  if (!name) { shoppingMessage("Podaj nazwę produktu.", true); return; }
  const amount = $("#shopping-amount").value === "" ? null : Number($("#shopping-amount").value);
  const unit = $("#shopping-unit").value.trim();
  if (await updateShopping(doc => { doc.items.push({ id: shoppingId(), name, amount, unit, checked: false, source: "" }); })) $("#shopping-add").reset();
});
loadShopping().catch(() => { $("#shopping-count").textContent = "—"; });
request("/api/version").then(result => { $("#app-version").textContent = `Przepisnik · wersja ${result.version}`; })
  .catch(() => { $("#app-version").textContent = "Wersja niedostępna"; });
