from PySide6.QtGui import Qt
from typing_extensions import override

from database.models import FaceModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import batch_fetch_unity3d_images


class FaceListModel(AssetListModel):

    def __init__(self, faces=None):
        super().__init__(faces or [], FaceModel)
        self.refresh()

    @override
    def refresh(self):
        self.assets = session.query(FaceModel).all()

        if self.assets:
            # Create a mapping of key to bundle for batch fetching
            key_to_bundle = {face.key: str(face.key) for face in self.assets}

            # Fetch all thumbnails in batch
            thumbnails = batch_fetch_unity3d_images(
                [face.key for face in self.assets],
                (128, 181)
            )

            # Assign thumbnails to faces
            for face in self.assets:
                if face.key in thumbnails:
                    face.thumb = thumbnails[face.key]

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return ""

        if role == Qt.DecorationRole:
            return self.assets[index.row()].thumb
