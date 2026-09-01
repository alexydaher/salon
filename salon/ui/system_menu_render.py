# SPDX-License-Identifier: GPL-3.0-or-later
"""Rendering and selection publication for :mod:`system_menu`."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402


class SystemMenuRenderer:
    def _render_frame(self) -> None:
        for row in self._rows:
            self._items_box.remove(row)
        self._rows = []
        if not self._frames:
            return
        frame = self._frames[-1]
        frame.selected = max(0, min(frame.selected, len(frame.items) - 1)) if frame.items else 0
        enriched = len(self._frames) == 1
        self._header.set_content(
            frame.title,
            self._header_subtitle if enriched else "",
            self._header_icon_name if enriched else "",
        )
        self._header_separator.set_visible(bool(frame.title))
        self.update_property([Gtk.AccessibleProperty.LABEL], [frame.title or "Menu"])
        for index, item in enumerate(frame.items):
            row = Gtk.Button()
            row.add_css_class("salon-system-menu-item")
            row.set_accessible_role(Gtk.AccessibleRole.MENU_ITEM)
            row.update_property(
                [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
                [item.label, item.detail],
            )
            if item.danger:
                row.add_css_class("danger")
                row.add_css_class("salon-system-menu-danger")
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            content.add_css_class("salon-system-menu-item-content")
            icon = Gtk.Image.new_from_icon_name(item.icon_name or "image-missing-symbolic")
            icon.add_css_class("salon-system-menu-icon")
            icon.set_opacity(1.0 if item.icon_name else 0.0)
            content.append(icon)
            label = Gtk.Label(label=item.label)
            label.set_halign(Gtk.Align.START)
            label.set_xalign(0.0)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(30)
            content.append(label)
            tail = Gtk.Label(label="›" if item.submenu is not None else item.trailing)
            tail.add_css_class("salon-system-menu-trailing")
            tail.set_visible(bool(tail.get_label()))
            content.append(tail)
            row.set_child(content)
            row.connect("clicked", lambda _btn, i=index: self._activate(i))
            controller = Gtk.EventControllerMotion()
            controller.connect("motion", lambda *_, i=index: self._on_hover(i))
            row.add_controller(controller)
            self._items_box.append(row)
            self._rows.append(row)
        self._style_rows()
        self._update_selection()

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._card.set_spacing(scale.px(6.0))
        self._card.set_size_request(scale.px(560.0), -1)
        self._apply_content_insets()
        self._scroller.set_max_content_height(scale.px(600.0))
        self._items_box.set_spacing(scale.px(4.0))
        self._description.set_margin_start(scale.px(24.0))
        self._description.set_margin_end(scale.px(24.0))
        self._description.set_margin_top(scale.px(8.0))
        self._legend.set_scale(scale)
        self._header.set_scale(scale)
        self._style_rows()

    def set_content_insets(self, left: float = 0.0, right: float = 0.0) -> None:
        self._content_insets = (left, right) if left or right else None
        self._apply_content_insets()

    def _apply_content_insets(self) -> None:
        margin = self._scale.safe_margin_px
        left, right = self._content_insets or (margin, margin)
        self._card.set_margin_start(round(left))
        self._card.set_margin_end(round(right))
        self._card.set_margin_top(margin)
        self._card.set_margin_bottom(margin)

    def _style_rows(self) -> None:
        scale = self._scale
        for row in self._rows:
            child = row.get_child()
            if isinstance(child, Gtk.Box):
                child.set_spacing(scale.px(16.0))
                icon = child.get_first_child()
                if isinstance(icon, Gtk.Image):
                    icon.set_pixel_size(scale.px(28.0))

    def _update_selection(self) -> None:
        if not self._frames:
            return
        selected = self._frames[-1].selected
        for index, row in enumerate(self._rows):
            is_selected = index == selected
            row.update_state([Gtk.AccessibleState.SELECTED], [1 if is_selected else 0])
            if is_selected:
                row.add_css_class("selected")
            else:
                row.remove_css_class("selected")
        item = self.selected_item
        self._description.set_label(item.detail if item is not None else "")
        self._description.set_visible(bool(item is not None and item.detail))
        row = self.selected_row
        if row is not None:
            self.update_relation([Gtk.AccessibleRelation.ACTIVE_DESCENDANT], [row])
            if self.get_visible():
                row.grab_focus()
            GLib.idle_add(self._reveal_selected)
        if self._on_selection_changed is not None:
            self._on_selection_changed()

    def _reveal_selected(self) -> bool:
        row = self.selected_row
        if row is None:
            return GLib.SOURCE_REMOVE
        ok, bounds = row.compute_bounds(self._items_box)
        if not ok:
            return GLib.SOURCE_REMOVE
        adjustment = self._scroller.get_vadjustment()
        top = bounds.get_y()
        bottom = top + bounds.get_height()
        value = adjustment.get_value()
        page = adjustment.get_page_size()
        if top < value:
            adjustment.set_value(top)
        elif page > 0 and bottom > value + page:
            adjustment.set_value(bottom - page)
        return GLib.SOURCE_REMOVE
