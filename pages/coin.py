import re
from io import BytesIO
from os.path import join
from typing import Optional

from PIL import Image, ImageDraw
from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog
from UnityPy import load as unity_load
from pyqttoast import ToastPreset

from database.models import CoinModel
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.coin_list_model import CoinListModel
from pages.ui.coin import Ui_Coin
from services.coin_service import CoinService
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast


class Coin(ResponsivePageMixin, QtWidgets.QWidget, Ui_Coin):
    """
    Coin modding page.

    This page allows users to modify the head and tail textures of the game's coin.
    It searches for coin assets in the CoinModel and provides separate
    controls for head and tail image replacement.
    """

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        # Configure responsive coin images (4 circular images)
        self.setup_responsive_coin_images(
            self.current_head,
            self.current_tail,
            self.preview_head,
            self.preview_tail
        )

        self.service = CoinService()
        self.model = CoinListModel()
        self.selected: Optional[CoinModel] = None

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._setup_coin_list()
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
                self.bundle.setText(f"Editing Coin ({self.selected.bundle})")

                # Enable buttons
                self.extractButton.setEnabled(True)
                self.restoreButton.setEnabled(True)

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
            self.bundle.setText("No coin data found - update database first")

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
        self.replaceHeadButton.setEnabled(has_head)
        self.replaceTailButton.setEnabled(has_tail)

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
