"""Main screen: system panel, category sidebar, catalog table, details pane."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, OptionList, Static
from textual.widgets.data_table import ColumnKey
from textual.widgets.option_list import Option

from distroforge import __version__
from distroforge.catalog.models import Item, Method
from distroforge.engine.resolve import Resolver
from distroforge.tui.colors import colour

if TYPE_CHECKING:
    from distroforge.tui.app import DistroForgeApp

SELECTED = "__selected__"
ALL = "__all__"


class MainScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_item", "Select"),
        Binding("m", "cycle_method", "Method"),
        Binding("slash", "search", "Search"),
        Binding("a", "select_visible", "All", show=False),
        Binding("n", "clear_visible", "None", show=False),
        Binding("r", "review", "Review & install"),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._category: str = ALL
        self._visible: list[Item] = []
        self._supported: dict[str, bool] = {}

    @property
    def df(self) -> DistroForgeApp:
        return self.app  # type: ignore[return-value]

    # ── layout ──

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static(id="sysinfo")
                yield OptionList(id="categories")
            with Vertical(id="content"):
                yield Input(placeholder="Search the catalog…   ( / )", id="search")
                yield DataTable(id="items", cursor_type="row", zebra_stripes=True)
                yield Static(id="details")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sysinfo").border_title = "System"
        self.query_one("#categories").border_title = "Categories"
        self.query_one("#details").border_title = "Details"
        table = self.query_one("#items", DataTable)
        table.border_title = "Catalog"
        table.add_column(" ", key="sel", width=2)
        table.add_column("Name", key="name", width=26)
        table.add_column("Description", key="desc", width=40)
        table.add_column("Method", key="method", width=16)
        table.add_column("Status", key="status", width=12)
        resolver = self.df.services.resolver()
        self._supported = {i.id: resolver.supported(i) for i in self.df.services.catalog.items.values()}
        self._render_sysinfo()
        self._render_categories()
        self._render_table()
        self.watch(self.app, "theme", lambda *_: self._render_all(), init=False)
        self.scan_installed()
        table.focus()

    def on_resize(self) -> None:
        self._fit_columns()

    def _fit_columns(self) -> None:
        # Description takes whatever is left so Status never scrolls off-screen.
        table = self.query_one("#items", DataTable)
        fixed = sum(col.width for key, col in table.columns.items() if key.value != "desc")
        padding = 2 * len(table.columns) + 4  # cell padding + border + scrollbar
        available = table.size.width or self.size.width - 40
        desc = table.columns.get(ColumnKey("desc"))
        if desc is not None:
            desc.width = max(12, available - fixed - padding)
            desc.auto_width = False
            table.refresh()

    def on_screen_resume(self) -> None:
        self._render_all()

    def _render_all(self) -> None:
        self._render_sysinfo()
        self._render_categories()
        self._render_table(keep_cursor=True)

    # ── state helpers ──

    @property
    def _resolver(self) -> Resolver:
        return self.df.services.resolver()

    def _method_for(self, item: Item) -> Method | None:
        return self._resolver.choose(item, self.df.selection.get(item.id))

    def _highlighted(self) -> Item | None:
        table = self.query_one("#items", DataTable)
        if not self._visible or table.cursor_row < 0 or table.cursor_row >= len(self._visible):
            return None
        return self._visible[table.cursor_row]

    def _colour(self, name: str) -> str:
        return colour(self.app, name)

    # ── rendering ──

    def _render_sysinfo(self) -> None:
        sysinfo = self.df.services.system
        text = Text()
        rows = [
            ("OS", sysinfo.distro_name),
            ("Family", f"{sysinfo.family.label} ({sysinfo.package_manager})"),
            ("Kernel", sysinfo.kernel),
            ("CPU", sysinfo.cpu),
            ("GPU", sysinfo.gpu_name or "unknown"),
            ("RAM", f"{sysinfo.ram_gb} GB"),
            ("Desktop", f"{sysinfo.desktop or '—'} · {sysinfo.session_type or '—'}"),
            ("AUR", sysinfo.aur_helper or "—"),
        ]
        for label, value in rows:
            text.append(f"{label:<8}", style=f"bold {self._colour('primary')}")
            text.append(f"{value}\n")
        self.query_one("#sysinfo", Static).update(text)

        selected = len(self.df.selection)
        bar = Text()
        bar.append(" ✦ DistroForge ", style=f"bold {self._colour('background')} on {self._colour('primary')}")
        bar.append(f" v{__version__}  ", style="dim")
        bar.append(f"{sysinfo.distro_name}  ", style="bold")
        bar.append(f"{selected} selected", style=f"bold {self._colour('accent')}")
        if self.df.dry_run_default:
            bar.append("   DRY-RUN MODE", style=f"bold {self._colour('warning')}")
        self.query_one("#topbar", Static).update(bar)

    def _render_categories(self) -> None:
        catalog = self.df.services.catalog
        options: list[Option] = [
            Option(f"★ Selected  ({len(self.df.selection)})", id=SELECTED),
            Option(f"◉ Everything  ({len(catalog.items)})", id=ALL),
        ]
        for cid, items in catalog.by_category().items():
            category = catalog.categories[cid]
            chosen = sum(1 for i in items if i.id in self.df.selection)
            label = Text(f"{category.icon} {category.name}")
            label.append(f"  {chosen}/{len(items)}" if chosen else f"  {len(items)}", style="dim")
            options.append(Option(label, id=cid))
        option_list = self.query_one("#categories", OptionList)
        highlighted = option_list.highlighted
        option_list.set_options(options)
        if highlighted is None:
            option_list.highlighted = 1
        else:
            option_list.highlighted = min(highlighted, option_list.option_count - 1)

    def _items_for_view(self) -> list[Item]:
        catalog = self.df.services.catalog
        query = self.query_one("#search", Input).value.strip().lower()
        items = sorted(
            catalog.items.values(), key=lambda i: (catalog.categories[i.category].order, i.name.lower())
        )
        if query:
            terms = query.split()
            return [i for i in items if all(t in i.search_text() for t in terms)]
        if self._category == SELECTED:
            return [i for i in items if i.id in self.df.selection]
        if self._category == ALL:
            return items
        return [i for i in items if i.category == self._category]

    def _row(self, item: Item) -> tuple[Text, Text, Text, Text, Text]:
        supported = self._supported.get(item.id, False)
        selected = item.id in self.df.selection
        installed = self.df.installed.get(item.id)
        muted = "dim" if not supported else ""

        mark = Text("●", style=f"bold {self._colour('accent')}") if selected else Text("○", style="dim")
        name = Text(item.name, style=f"bold {muted}".strip() if selected else muted)
        desc = Text(item.description, style="dim", overflow="ellipsis", no_wrap=True)
        method = self._method_for(item) if supported else None
        if method is not None:
            label = method.label + ("*" if self.df.selection.get(item.id) else "")
            method_text = Text(label, style=self._colour("secondary"))
        elif supported:
            method_text = Text("action", style="dim")
        else:
            method_text = Text("—", style="dim")

        if not supported:
            status = Text("n/a", style="dim")
        elif installed is None:
            status = Text("…", style="dim")
        elif installed:
            status = Text("✓ installed", style=self._colour("success"))
        else:
            status = Text("")
        return mark, name, desc, method_text, status

    def _render_table(self, *, keep_cursor: bool = False) -> None:
        table = self.query_one("#items", DataTable)
        row = table.cursor_row if keep_cursor else 0
        self._visible = self._items_for_view()
        table.clear()
        for item in self._visible:
            table.add_row(*self._row(item), key=item.id)
        if self._visible:
            table.move_cursor(row=min(max(row, 0), len(self._visible) - 1))
        title = self.query_one("#search", Input).value.strip()
        if title:
            table.border_title = f"Search: {title}  ({len(self._visible)})"
        elif self._category in self.df.services.catalog.categories:
            table.border_title = self.df.services.catalog.categories[self._category].name
        else:
            table.border_title = "Selected" if self._category == SELECTED else "Everything"
        self._render_details()

    def _refresh_row(self, item: Item) -> None:
        table = self.query_one("#items", DataTable)
        for key, value in zip(("sel", "name", "desc", "method", "status"), self._row(item), strict=True):
            table.update_cell(item.id, key, value)

    def _render_details(self) -> None:
        details = self.query_one("#details", Static)
        item = self._highlighted()
        if item is None:
            details.update(Text("Nothing here yet — pick a category or search.", style="dim"))
            return
        resolver = self._resolver
        text = Text()
        text.append(item.name, style=f"bold {self._colour('primary')}")
        text.append(f"  [{item.id}]", style="dim")
        if item.kind == "tweak":
            text.append("  tweak", style=self._colour("warning"))
        text.append(f"\n{item.description}\n")
        if item.homepage:
            text.append(f"{item.homepage}\n", style="underline dim")
        if self._supported.get(item.id):
            chosen = self._method_for(item)
            ways = resolver.candidates(item)
            if ways:
                text.append("Methods: ", style="bold")
                for i, method in enumerate(ways):
                    style = f"bold reverse {self._colour('secondary')}" if method is chosen else "dim"
                    text.append(f" {method.label} ", style=style)
                    if i < len(ways) - 1:
                        text.append(" ")
                text.append("   (m to change)\n", style="dim")
            if item.post:
                text.append("Also: ", style="bold")
                text.append("; ".join(ref.describe(self.df.services.system) for ref in item.post) + "\n")
        else:
            text.append(resolver.unsupported_reason(item) + "\n", style=self._colour("warning"))
        if item.requires:
            names = [self.df.services.catalog.items[r].name for r in item.requires]
            text.append("Requires: ", style="bold")
            text.append(", ".join(names) + "\n")
        if item.notes:
            text.append(f"Note: {item.notes}\n", style="italic")
        if item.source != "built-in":
            text.append(f"Source: {item.source}\n", style="dim")
        details.update(text)

    # ── events ──

    @on(OptionList.OptionHighlighted, "#categories")
    def _category_changed(self, event: OptionList.OptionHighlighted) -> None:
        new = event.option.id or ALL
        if new != self._category:
            self._category = new
            search = self.query_one("#search", Input)
            if search.value:
                search.value = ""
            self._render_table()

    @on(Input.Changed, "#search")
    def _search_changed(self) -> None:
        self._render_table()

    @on(Input.Submitted, "#search")
    def _search_submitted(self) -> None:
        self.query_one("#items", DataTable).focus()

    @on(DataTable.RowHighlighted, "#items")
    def _row_highlighted(self) -> None:
        self._render_details()

    @on(DataTable.RowSelected, "#items")
    def _row_selected(self) -> None:
        self.action_toggle_item()

    # ── actions ──

    def _set_selected(self, item: Item, selected: bool) -> bool:
        if selected and not self._supported.get(item.id):
            return False
        if selected:
            self.df.selection.setdefault(item.id, None)
        else:
            self.df.selection.pop(item.id, None)
        return True

    def _after_selection_change(self) -> None:
        self._render_sysinfo()
        self._render_categories()
        if self._category == SELECTED:
            self._render_table(keep_cursor=True)

    def action_toggle_item(self) -> None:
        item = self._highlighted()
        if item is None:
            return
        want = item.id not in self.df.selection
        if not self._set_selected(item, want):
            self.notify(self._resolver.unsupported_reason(item), title=item.name, severity="warning")
            return
        if want and self.df.installed.get(item.id):
            self.notify(
                "Already installed — it will be skipped unless something is missing.", title=item.name
            )
        self._refresh_row(item)
        self._after_selection_change()

    def action_cycle_method(self) -> None:
        item = self._highlighted()
        if item is None or not self._supported.get(item.id):
            return
        ways = self._resolver.candidates(item)
        if len(ways) < 2:
            self.notify("Only one install method is available here.", title=item.name)
            return
        current = self._method_for(item)
        index = next((i for i, m in enumerate(ways) if m is current), -1)
        nxt = ways[(index + 1) % len(ways)]
        self.df.selection[item.id] = nxt.backend
        self._refresh_row(item)
        self._render_details()
        self._after_selection_change()

    def action_select_visible(self) -> None:
        changed = [i for i in self._visible if self._set_selected(i, True)]
        self.notify(f"Selected {len(changed)} item(s)")
        self._render_table(keep_cursor=True)
        self._after_selection_change()

    def action_clear_visible(self) -> None:
        for item in self._visible:
            self._set_selected(item, False)
        self._render_table(keep_cursor=True)
        self._after_selection_change()

    def action_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        if search.value:
            search.value = ""
        self.query_one("#items", DataTable).focus()

    def action_review(self) -> None:
        if not self.df.selection:
            self.notify("Select something first (Space).", severity="warning")
            return
        from distroforge.tui.screens.review import ReviewScreen

        self.app.push_screen(ReviewScreen())

    # ── background ──

    @work(thread=True, exclusive=True, group="scan")
    def scan_installed(self) -> None:
        services = self.df.services
        resolver = services.resolver()
        results: dict[str, bool] = {}
        for item in services.catalog.items.values():
            if self._supported.get(item.id):
                try:
                    results[item.id] = resolver.is_installed(item)
                except Exception:  # a broken probe must never take the UI down
                    results[item.id] = False
        self.app.call_from_thread(self._apply_scan, results)

    def _apply_scan(self, results: dict[str, bool]) -> None:
        self.df.installed.update(results)
        self._render_table(keep_cursor=True)

    def rescan(self) -> None:
        self.df.installed.clear()
        self.df.services.refresh_state()
        self._render_table(keep_cursor=True)
        self.scan_installed()
