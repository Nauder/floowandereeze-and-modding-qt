from threading import Thread

from PySide6 import QtCore
from PySide6.QtGui import Qt

from database.models import FieldModel
from database.objects import session
from unity.unity_utils import fetch_field_thumb


class FieldListModel(QtCore.QAbstractListModel):

    def __init__(self, fields=None):
        super().__init__()
        self.fields: list[FieldModel] = fields or []
        self.thumbs = None
        self.refresh()

    def refresh(self):
        self.fields = session.query(FieldModel).all()

        refresh_threads = [
            Thread(target=lambda field=fields_field: self.refresh_field(field))
            for fields_field in self.fields
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def refresh_field(self, field):
        field.thumb = fetch_field_thumb(field)

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return ""

        if role == Qt.DecorationRole:
            return self.fields[index.row()].thumb

    def rowCount(self, index):
        return len(self.fields)
