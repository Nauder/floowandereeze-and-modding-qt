"""Shared UI helpers for editor pages."""

from PySide6 import QtCore, QtWidgets

from widgets.asset_item_delegate import AssetStateBadgeDelegate

DROP_IMAGE_TEXT = "Select or drop an image"


def configure_editor_chrome(
    page,
    *,
    current_widget=None,
    preview_widget=None,
    current_title="Current",
    preview_title="Preview",
    file_edits=(),
    list_views=(),
    helper_after=None,
):
    """Apply consistent editor affordances around existing Designer widgets."""

    del helper_after

    if current_widget:
        _insert_label_above(page, current_widget, current_title)
    if preview_widget:
        _insert_label_above(page, preview_widget, preview_title)

    for edit in file_edits:
        edit.setPlaceholderText(DROP_IMAGE_TEXT)
        edit.setToolTip(DROP_IMAGE_TEXT)

    for list_view in list_views:
        list_view.setItemDelegate(AssetStateBadgeDelegate(list_view))


def hide_selection_helper(page):
    """Compatibility no-op for pages already wired to hide selection helpers."""

    del page


def set_button_roles(page):
    """Set button role properties used by the shared stylesheet."""

    for button in page.findChildren(QtWidgets.QPushButton):
        name = button.objectName().lower()
        role = "neutral"
        if "replace" in name or "applytext" in name or name == "updatebutton":
            role = "primary"
        elif "restore" in name or "clear" in name or "reset" in name:
            role = "warning"
        button.setProperty("buttonRole", role)
        button.style().unpolish(button)
        button.style().polish(button)


def add_section_label(layout, index, text, parent):
    """Insert a compact section label into a layout."""

    label = QtWidgets.QLabel(text, parent)
    label.setObjectName(f"{text.replace(' ', '').lower()}SectionLabel")
    label.setStyleSheet("font-weight: 600; color: #ffffff; margin-top: 10px;")
    layout.insertWidget(index, label)
    return label


def _insert_label_above(page, widget, text):
    label_name = f"{widget.objectName()}HeaderLabel"
    if page.findChild(QtWidgets.QLabel, label_name):
        return

    layout, index = _find_widget_layout(page.layout(), widget)
    if layout is None:
        return

    label = QtWidgets.QLabel(text, page)
    label.setObjectName(label_name)
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("font-weight: 600; color: #ffffff;")

    if isinstance(layout, QtWidgets.QBoxLayout) and layout.direction() in (
        QtWidgets.QBoxLayout.Direction.LeftToRight,
        QtWidgets.QBoxLayout.Direction.RightToLeft,
    ):
        layout.takeAt(index)
        wrapper = QtWidgets.QVBoxLayout()
        wrapper.setObjectName(f"{widget.objectName()}PreviewLayout")
        wrapper.addWidget(label)
        wrapper.addWidget(widget)
        layout.insertLayout(index, wrapper)
    else:
        layout.insertWidget(index, label)


def _insert_label_after(page, widget, label):
    layout, index = _find_widget_layout(page.layout(), widget)
    if layout is None:
        return
    layout.insertWidget(index + 1, label)


def _find_widget_layout(layout, widget):
    if layout is None:
        return None, -1

    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            return layout, index
        child_layout = item.layout()
        if child_layout is not None:
            found_layout, found_index = _find_widget_layout(child_layout, widget)
            if found_layout is not None:
                return found_layout, found_index

    return None, -1
