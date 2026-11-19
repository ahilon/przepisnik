"""Reusable browser actions for recipes, tags and the shopping list."""

from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Page

_SHOPPING_LOADING_MESSAGE = "Wczytywanie listy…"


class ApplicationActions:
    """Perform UI actions on one test-owned page, leaving scenario assertions to tests."""

    def __init__(self, page: Page) -> None:
        """Use an existing isolated page without navigating or changing test data.

        Args:
            page: Playwright page owned by the calling test or fixture.

        Returns:
            None: The page is retained for subsequent actions.
        """
        self._page = page
        return None

    def search_product(self, query: str) -> None:
        """Search the recipe catalogue and wait for the requested results to render.

        Args:
            query: Recipe search text; an empty string clears the search.

        Returns:
            None: Matching results or the empty-state message are rendered.
        """
        search_query = query.strip()
        with self._page.expect_response(
            lambda response: (
                response.request.method == "GET"
                and urlsplit(response.url).path == "/api/recipes"
                and parse_qs(urlsplit(response.url).query).get("q", [""])[0] == search_query
            )
        ):
            self._page.get_by_role("searchbox").fill(query)
        self._page.locator('#grid[aria-busy="false"]').wait_for(state="attached")
        return None

    def open_recipe(self, title: str) -> None:
        """Open a recipe already visible in the current collection.

        Args:
            title: Exact recipe title displayed on its collection card.

        Returns:
            None: The selected recipe's detail dialog is visible.
        """
        self._page.get_by_role("button", name=f"Otwórz przepis: {title}", exact=True).click()
        self._page.get_by_role("dialog", name=title, exact=True).wait_for(state="visible")
        return None

    def open_shopping_list(self) -> None:
        """Open the shopping list from the application's main navigation.

        Returns:
            None: The shopping dialog has finished its loading state.
        """
        self._page.locator("#open-shopping").click()
        self._wait_for_shopping_list()
        return None

    def add_product(self, name: str, amount: str, unit: str) -> None:
        """Add one product through the already open shopping-list form.

        Args:
            name: Product name displayed in the shopping list.
            amount: Quantity as entered in the amount input.
            unit: Unit as entered in the unit input.

        Returns:
            None: The product's shopping checkbox is visible.
        """
        self._page.get_by_label("Produkt", exact=True).fill(name)
        self._page.locator("#shopping-amount").fill(amount)
        self._page.locator("#shopping-unit").fill(unit)
        self._page.get_by_role("button", name="Dodaj produkt", exact=True).click()
        checkbox = self._page.get_by_role("checkbox", name=f"Mam: {name}", exact=True)
        checkbox.wait_for(state="visible")
        return None

    def set_servings(self, value: str) -> None:
        """Enter a serving count in the open recipe and trigger its validation.

        Args:
            value: Input text, including invalid values for validation scenarios.

        Returns:
            None: The serving input has lost focus and triggered its change event.
        """
        field = self._page.get_by_label("Liczba porcji", exact=True)
        field.fill(value)
        field.press("Tab")
        return None

    def add_recipe_to_shopping(self) -> None:
        """Add the open recipe's selected variant and servings to the shopping list.

        Returns:
            None: Shopping feedback is visible; the recipe dialog remains open.
        """
        self._page.get_by_role("button", name="Dodaj do listy zakupów", exact=True).click()
        self._page.locator(".shopping-notice").wait_for(state="visible")
        return None

    def show_shopping_list(self) -> None:
        """Follow the shopping-list link displayed in an open recipe.

        Returns:
            None: The shopping dialog is visible and has finished loading.
        """
        self._page.get_by_role("button", name="Pokaż listę", exact=True).click()
        self._wait_for_shopping_list()
        return None

    def add_tag(self, tag_name: str) -> None:
        """Submit a tag in the currently open recipe's detail view.

        Args:
            tag_name: Tag text accepted by the detail form, including comma-separated tags.

        Returns:
            None: Tag submission has finished and the detail input is usable again.
        """
        detail = self._page.locator("#detail")
        detail.locator("#detail-tags").fill(tag_name)
        detail.get_by_role("button", name="Dodaj tag", exact=True).click()
        detail.locator("#detail-tags:not(:disabled)").wait_for(state="visible")
        return None

    def _wait_for_shopping_list(self) -> None:
        """Wait for the shopping dialog and the end of its loading message.

        Returns:
            None: The visible list is ready for interactions or scenario assertions.
        """
        dialog = self._page.get_by_role("dialog", name="Lista zakupów", exact=True)
        dialog.wait_for(state="visible")
        status = self._page.locator("#shopping-status")
        status.filter(has_not_text=_SHOPPING_LOADING_MESSAGE).wait_for(state="attached")
        return None
