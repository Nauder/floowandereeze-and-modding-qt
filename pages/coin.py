import re
from io import BytesIO
from os.path import join
from typing import Optional

from PIL import Image, ImageDraw
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QSize, QSettings, QTimer
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
)
from UnityPy import load as unity_load
from pyqttoast import ToastPreset

from database.models import CoinModel
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.coin_list_model import CoinListModel
from pages.ui.coin import Ui_Coin
from services.coin_service import CoinService
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles


class Coin(ResponsivePageMixin, QtWidgets.QWidget, Ui_Coin):
    """
    Coin modding page.

    This page allows users to modify the head and tail textures of the game's coin.
    It searches for coin assets in the CoinModel and provides separate
    controls for head and tail image replacement.
    """

    RESULT_ITEM_SIZE = QSize(116, 132)
    RESULT_ICON_SIZE = QSize(96, 96)
    RESULTS_MIN_HEIGHT = 315

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        # Configure responsive coin images (4 circular images)
        self.setup_responsive_coin_images(
            self.current_head,
            self.current_tail,
            self.preview_head,
            self.preview_tail,
        )

        self.service = CoinService()
        self.model = CoinListModel()
        self.selected: Optional[CoinModel] = None
        self._settings = QSettings("Floowandereeze", "FloowandereezeAndModding")
        configure_editor_chrome(
            self,
            file_edits=(self.headEdit, self.tailEdit),
            list_views=(self.coin_list,),
            helper_after=self.bundle,
        )
        set_button_roles(self)
        self._setup_coin_list()
        self._configure_split_layout()
        self._set_editor_context("Select a Coin")
        self._configure_results_grid()
        self._queue_initial_layout_update()

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()
        self._load_coin_data()

    def _create_circular_preview(
        self, image_path: str, size: tuple = (100, 100)
    ) -> QPixmap:
        """Create a circular preview of an image."""
        try:
            # Load and resize the image
            img = Image.open(image_path).convert("RGBA")
            img = img.resize(size, Image.Resampling.LANCZOS)

            # Create circular mask
            mask = Image.new("L", size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, size[0], size[1]), fill=255)

            # Apply circular mask
            circular_img = Image.new("RGBA", size, (0, 0, 0, 0))
            circular_img.paste(img, (0, 0))
            circular_img.putalpha(mask)

            # Convert to QPixmap
            img_bytes = BytesIO()
            circular_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.getvalue())

            return pixmap
        except Exception as e:
            print(f"Error creating circular preview: {e}")
            return QPixmap()

    def _pil_to_circular_pixmap(self, pil_image: Image.Image) -> QPixmap:
        """Convert a PIL image to a circular QPixmap."""
        try:
            # Ensure RGBA mode
            if pil_image.mode != "RGBA":
                pil_image = pil_image.convert("RGBA")

            # Create circular mask
            mask = Image.new("L", pil_image.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, pil_image.size[0], pil_image.size[1]), fill=255)

            # Apply circular mask
            circular_img = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
            circular_img.paste(pil_image, (0, 0))
            circular_img.putalpha(mask)

            # Convert to QPixmap
            img_bytes = BytesIO()
            circular_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.getvalue())

            return pixmap
        except Exception as e:
            print(f"Error converting PIL to circular pixmap: {e}")
            return QPixmap()

    def _setup_coin_list(self) -> None:
        """Set up the coin thumbnail list for selection."""
        # Set the model and connect the clicked signal
        self.coin_list.setModel(self.model)
        self.coin_list.clicked.connect(self._on_coin_selected_index)

    def resizeEvent(self, event: QtCore.QEvent) -> None:
        super().resizeEvent(event)
        self._update_results_grid()

    def showEvent(self, event: QtCore.QEvent) -> None:
        super().showEvent(event)
        self._queue_initial_layout_update()

    def _configure_split_layout(self) -> None:
        self.verticalLayout.setSpacing(8)
        self.verticalLayout.setContentsMargins(12, 8, 12, 12)
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.bundle.hide()

        for label in (
            self.current_label,
            self.preview_label,
            self.head_label,
            self.tail_label,
            self.preview_head_label,
            self.preview_tail_label,
        ):
            label.setStyleSheet("font-weight: 600; color: #ffffff;")

        for layout in (
            self.main_content,
            self.controls_layout,
            self.horizontalLayout,
        ):
            self.verticalLayout.removeItem(layout)

        self._configure_editor_controls()

        self.editorPanel = QtWidgets.QWidget(self)
        self.editorPanel.setObjectName("coinEditorPanel")
        self.editorPanel.setMinimumHeight(230)
        editor_layout = QVBoxLayout(self.editorPanel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addLayout(self.main_content)

        self.resultsPanel = QtWidgets.QWidget(self)
        self.resultsPanel.setObjectName("coinResultsPanel")
        self.resultsPanel.setMinimumHeight(self.RESULTS_MIN_HEIGHT)
        results_layout = QVBoxLayout(self.resultsPanel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(6)
        results_layout.addLayout(self._build_results_header())
        results_layout.addWidget(self.coin_list, 1)

        self.coinSplitter = QSplitter(QtCore.Qt.Orientation.Vertical, self)
        self.coinSplitter.setObjectName("coinSplitter")
        self.coinSplitter.setChildrenCollapsible(False)
        self.coinSplitter.setOpaqueResize(True)
        self.coinSplitter.addWidget(self.editorPanel)
        self.coinSplitter.addWidget(self.resultsPanel)
        self.coinSplitter.setStretchFactor(0, 3)
        self.coinSplitter.setStretchFactor(1, 2)
        self.coinSplitter.splitterMoved.connect(self._persist_splitter_state)
        self.coinSplitter.splitterMoved.connect(lambda *_: self._queue_layout_update())

        stored_state = self._settings.value("coins/splitter_state")
        if stored_state:
            self.coinSplitter.restoreState(stored_state)
        else:
            self.coinSplitter.setSizes([520, 360])

        self.verticalLayout.addWidget(self.coinSplitter, 1)

    def _configure_editor_controls(self) -> None:
        self.head_file_label.setText("Head image")
        self.tail_file_label.setText("Tail image")
        for label in (self.head_file_label, self.tail_file_label):
            label.setStyleSheet("font-weight: 600; color: #ffffff;")

        for edit in (self.headEdit, self.tailEdit):
            edit.setMinimumWidth(210)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        for layout, widget in (
            (self.head_file_row, self.head_file_label),
            (self.head_file_row, self.headEdit),
            (self.head_file_row, self.selectHeadButton),
            (self.tail_file_row, self.tail_file_label),
            (self.tail_file_row, self.tailEdit),
            (self.tail_file_row, self.selectTailButton),
            (self.buttons_layout, self.replaceHeadButton),
            (self.buttons_layout, self.replaceTailButton),
            (self.buttons_layout, self.extractButton),
            (self.buttons_layout, self.restoreButton),
        ):
            layout.removeWidget(widget)

        controls_layout = QVBoxLayout()
        controls_layout.setObjectName("coinEditorControls")
        controls_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        controls_layout.setSpacing(8)
        controls_layout.setContentsMargins(0, 26, 0, 0)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.head_file_label)
        controls_layout.addWidget(self.headEdit)
        controls_layout.addWidget(self.selectHeadButton)
        controls_layout.addSpacing(4)
        controls_layout.addWidget(self.tail_file_label)
        controls_layout.addWidget(self.tailEdit)
        controls_layout.addWidget(self.selectTailButton)
        controls_layout.addSpacing(6)

        replace_actions = QHBoxLayout()
        replace_actions.setSpacing(6)
        replace_actions.addWidget(self.replaceHeadButton)
        replace_actions.addWidget(self.replaceTailButton)
        controls_layout.addLayout(replace_actions)
        controls_layout.addWidget(self.restoreButton)

        secondary_actions = QHBoxLayout()
        secondary_actions.setSpacing(6)
        secondary_actions.addWidget(self.extractButton)
        controls_layout.addLayout(secondary_actions)
        controls_layout.addStretch(1)

        self.main_content.insertItem(
            2,
            QtWidgets.QSpacerItem(
                20,
                20,
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            ),
        )
        self.main_content.insertLayout(3, controls_layout)
        self.main_content.insertItem(
            4,
            QtWidgets.QSpacerItem(
                20,
                20,
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            ),
        )
        self.main_content.setStretch(0, 1)
        self.main_content.setStretch(1, 3)
        self.main_content.setStretch(2, 1)
        self.main_content.setStretch(3, 1)
        self.main_content.setStretch(4, 1)
        self.main_content.setStretch(5, 3)
        self.main_content.setStretch(6, 1)

    def _build_results_header(self):
        self.resultsLabel = QLabel("Results", self)
        self.resultsLabel.setObjectName("resultsLabel")
        self.resultsLabel.setStyleSheet("font-weight: 600; color: #ffffff;")

        self.horizontalLayout.removeItem(self.horizontalSpacer_6)
        self.horizontalLayout.removeItem(self.horizontalSpacer_8)
        self.horizontalLayout.insertWidget(0, self.resultsLabel)
        self.horizontalLayout.setSpacing(8)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        return self.horizontalLayout

    def _configure_results_grid(self) -> None:
        self.coin_list.setFlow(QListView.Flow.TopToBottom)
        self.coin_list.setWrapping(True)
        self.coin_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.coin_list.setMovement(QListView.Movement.Static)
        self.coin_list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.coin_list.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.coin_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.coin_list.setUniformItemSizes(True)
        self.coin_list.setWordWrap(True)
        self.coin_list.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.coin_list.setIconSize(self.RESULT_ICON_SIZE)
        self.coin_list.setGridSize(self.RESULT_ITEM_SIZE)
        self.coin_list.setStyleSheet("""
            QListView::item {
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
            }
            QListView::item:selected {
                background: rgba(21, 160, 111, 0.24);
                border: 2px solid #15a06f;
            }
            QListView::item:focus {
                border: 2px solid #15a06f;
            }
            """)
        self._update_results_grid()

    def _update_results_grid(self) -> None:
        if not hasattr(self, "coin_list"):
            return

        self.coin_list.setIconSize(self.RESULT_ICON_SIZE)
        self.coin_list.setGridSize(self.RESULT_ITEM_SIZE)
        self.coin_list.doItemsLayout()

    def _adjust_image_sizes(self) -> None:
        if not hasattr(self, "editorPanel"):
            super()._adjust_image_sizes()
            return

        if self.editorPanel.width() <= 0 or self.editorPanel.height() <= 0:
            return

        available_height = max(100, self.editorPanel.height() - 86)
        available_width = max(100, self.editorPanel.width() // 7)
        target_size = max(
            100,
            min(200, available_height, available_width),
        )
        for label in (
            self.current_head,
            self.current_tail,
            self.preview_head,
            self.preview_tail,
        ):
            label.setFixedSize(QSize(target_size, target_size))
            label.updateGeometry()

    def _queue_initial_layout_update(self) -> None:
        for delay in (0, 50, 150):
            QTimer.singleShot(delay, self._refresh_layout_after_show)

    def _queue_layout_update(self) -> None:
        QTimer.singleShot(0, self._refresh_layout_after_show)
        QTimer.singleShot(25, self._refresh_layout_after_show)

    def _refresh_layout_after_show(self) -> None:
        self.coinSplitter.updateGeometry()
        self.editorPanel.updateGeometry()
        self.resultsPanel.updateGeometry()
        self._adjust_image_sizes()
        self._update_results_grid()

    def _persist_splitter_state(self) -> None:
        self._settings.setValue("coins/splitter_state", self.coinSplitter.saveState())

    def _set_editor_context(self, text: str) -> None:
        self.bundle.setText(text)
        self.label.setText(f"Coins · {text}")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accepts drag and drop of image files."""
        if event.mimeData().hasUrls():
            # Check if the dragged file is an image
            for url in event.mimeData().urls():
                if (
                    url.toLocalFile()
                    .lower()
                    .endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif"))
                ):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handles the drop event of an image file."""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                # For now, set as head image - could be enhanced to detect drop target
                self.headEdit.setText(file_path)
                circular_pixmap = self._create_circular_preview(file_path)
                self.preview_head.setPixmap(circular_pixmap)
                self.service.head_image_path = file_path
                self._check_replace_buttons()
                break

    def _connect_callbacks(self) -> None:
        """Connect UI callbacks to their respective methods."""
        self.selectHeadButton.clicked.connect(self._select_head_image)
        self.selectTailButton.clicked.connect(self._select_tail_image)
        self.replaceHeadButton.clicked.connect(self._replace_head)
        self.replaceTailButton.clicked.connect(self._replace_tail)
        self.extractButton.clicked.connect(self._extract_texture)
        self.restoreButton.clicked.connect(self._restore)

    def _on_coin_selected_index(self, index) -> None:
        """Handle coin selection from the thumbnail list using QModelIndex."""
        if index.isValid():
            coin_index = index.row()
            if 0 <= coin_index < len(self.model.assets):
                self.selected = self.model.assets[coin_index]
                self.service.coin_metadata = self.selected
                self._set_editor_context(f"Editing {self.selected.bundle}")

                # Enable buttons
                self.extractButton.setEnabled(True)
                self.restoreButton.setEnabled(True)
                hide_selection_helper(self)

                # Load current coin display
                self._load_current_coin_display()

    def _load_coin_data(self) -> None:
        """Load coin data and populate the thumbnail list."""
        # The model will handle thumbnail creation automatically
        if self.model.assets:
            # Select the first coin by default
            if len(self.model.assets) > 0:
                first_index = self.model.index(0, 0)
                self.coin_list.setCurrentIndex(first_index)
                self._on_coin_selected_index(first_index)
        else:
            self._set_editor_context("No coin data found - update database first")

    def _load_current_coin_display(self) -> None:
        """Load and display the current coin texture regions directly from game files."""
        try:
            if not self.service.coin_metadata:
                self.current_head.setText("Current Head")
                self.current_tail.setText("Current Tail")
                return

            # Read coin texture directly from the game bundle
            bundle_path = join(
                APP_CONFIG.game_path,
                "0000",
                self.service.coin_metadata.bundle[:2],
                self.service.coin_metadata.bundle,
            )

            # Load the Unity bundle
            env = unity_load(bundle_path)
            coin_img = None

            # Find and extract the coin texture
            for obj in env.objects:
                if obj.type.name == "Texture2D":
                    data = obj.read()

                    # Look for the coin texture
                    if re.search(re.compile(r"coin\d\dtex"), data.m_Name.lower()) or (
                        "cointoss" in data.m_Name.lower()
                        and "icon" not in data.m_Name.lower()
                    ):

                        coin_img = data.image.convert("RGBA")
                        break

            if coin_img:
                # Get head and tail regions
                head_region, tail_region = self.service.get_coin_regions(coin_img.size)

                # Extract head region
                head_img = coin_img.crop(
                    (
                        head_region[0],
                        head_region[1],
                        head_region[0] + head_region[2],
                        head_region[1] + head_region[3],
                    )
                )

                # Extract tail region
                tail_img = coin_img.crop(
                    (
                        tail_region[0],
                        tail_region[1],
                        tail_region[0] + tail_region[2],
                        tail_region[1] + tail_region[3],
                    )
                )

                # Convert PIL images to circular QPixmaps for display
                head_pixmap = self._pil_to_circular_pixmap(head_img)
                self.current_head.setPixmap(head_pixmap)

                tail_pixmap = self._pil_to_circular_pixmap(tail_img)
                self.current_tail.setPixmap(tail_pixmap)

            else:
                self.current_head.setText("Coin texture not found")
                self.current_tail.setText("Coin texture not found")

        except Exception as e:
            print(f"Error loading current coin display: {e}")
            self.current_head.setText("Error loading coin")
            self.current_tail.setText("Error loading coin")

    def _select_head_image(self) -> None:
        """Select head image file."""
        file, _ = QFileDialog.getOpenFileUrl(
            self, "Select Head Image", "", IMAGE_FILTER
        )

        self._select_image(file)

    def _select_tail_image(self) -> None:
        """Select tail image file."""
        file, _ = QFileDialog.getOpenFileUrl(
            self, "Select Tail Image", "", IMAGE_FILTER
        )

        self._select_image(file)

    def _select_image(self, file):
        """Select image file and update UI."""
        if file and file.url() != "":
            local_file = file.toLocalFile()
            self.tailEdit.setText(local_file)
            circular_pixmap = self._create_circular_preview(local_file)
            self.preview_tail.setPixmap(circular_pixmap)
            self.service.tail_image_path = local_file
            self._check_replace_buttons()

    def _check_replace_buttons(self) -> None:
        """Enable replace buttons based on selected images."""
        has_head = bool(self.service.head_image_path)
        has_tail = bool(self.service.tail_image_path)
        has_selection = bool(self.selected)
        self.replaceHeadButton.setEnabled(has_head and has_selection)
        self.replaceTailButton.setEnabled(has_tail and has_selection)

    def _extract_texture(self) -> None:
        """Extract coin textures to the images folder."""
        if not self.selected:
            show_toast(
                self,
                "Extract",
                "No coin selected",
                ToastPreset.WARNING_DARK,
            )
            return

        self.service.extract_texture(self.selected.bundle)
        show_toast(
            self,
            "Coin Extraction",
            'Coin textures extracted to the "coins" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _restore(self) -> None:
        """Restore coin from backup."""
        if not self.selected:
            show_toast(
                self,
                "Restore",
                "No coin selected",
                ToastPreset.WARNING_DARK,
            )
            return

        if self.service.restore_asset(self.selected.bundle):
            # Refresh the current display to show the restored coin
            self._load_current_coin_display()
            show_toast(
                self,
                "Backup",
                "Coin restored successfully",
                ToastPreset.SUCCESS_DARK,
            )
        else:
            show_toast(
                self,
                "Backup",
                "Coin backup not found",
                ToastPreset.WARNING_DARK,
            )

    def _replace_head(self) -> None:
        """Replace coin head texture with the selected image."""
        if not self.selected:
            show_toast(
                self,
                "Replace Head",
                "No coin selected",
                ToastPreset.WARNING_DARK,
            )
            return

        if not self.service.head_image_path:
            show_toast(
                self,
                "Replace Head",
                "Please select a head image first",
                ToastPreset.WARNING_DARK,
            )
            return

        try:
            # Create backup if enabled
            if APP_CONFIG.create_backup:
                self.service.create_backup(self.selected.bundle)

            # Temporarily clear tail image to replace only head
            temp_tail = self.service.tail_image_path
            self.service.tail_image_path = None

            # Replace the coin head region
            self.service.replace_bundle()

            # Restore tail image path
            self.service.tail_image_path = temp_tail

            # Refresh the current display to show the updated coin
            self._load_current_coin_display()

            # Refresh the coin list model to update thumbnails
            self.model.refresh()

            show_toast(
                self,
                "Coin Head",
                "Head replacement successful",
                ToastPreset.SUCCESS_DARK,
            )

        except Exception as e:
            show_toast(
                self,
                "Coin Head",
                f"Head replacement failed: {str(e)}",
                ToastPreset.ERROR_DARK,
            )

    def _replace_tail(self) -> None:
        """Replace coin tail texture with selected image."""
        if not self.selected:
            show_toast(
                self,
                "Replace Tail",
                "No coin selected",
                ToastPreset.WARNING_DARK,
            )
            return

        if not self.service.tail_image_path:
            show_toast(
                self,
                "Replace Tail",
                "Please select a tail image first",
                ToastPreset.WARNING_DARK,
            )
            return

        try:
            # Create backup if enabled
            if APP_CONFIG.create_backup:
                self.service.create_backup(self.selected.bundle)

            # Temporarily clear head image to replace only tail
            temp_head = self.service.head_image_path
            self.service.head_image_path = None

            # Replace the coin tail region
            self.service.replace_bundle()

            # Restore head image path
            self.service.head_image_path = temp_head

            # Refresh the current display to show the updated coin
            self._load_current_coin_display()

            show_toast(
                self,
                "Coin Tail",
                "Tail replacement successful",
                ToastPreset.SUCCESS_DARK,
            )

        except Exception as e:
            show_toast(
                self,
                "Coin Tail",
                f"Tail replacement failed: {str(e)}",
                ToastPreset.ERROR_DARK,
            )
