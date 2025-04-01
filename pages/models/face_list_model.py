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
            for key, thumb in batch_fetch_unity3d_images(
                [face.key for face in self.assets], (128, 181)
            ).items():
                for face in self.assets:
                    if face.key == key:
                        face.thumb = thumb

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return ""

        if role == Qt.DecorationRole:
            return self.assets[index.row()].thumb
