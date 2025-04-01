from UnityPy.enums import TextureFormat
from sqlalchemy import or_
from typing_extensions import override

from database.models import CardModel, CardMetadataModel
from database.objects import session
from services.unity_service import UnityService
from unity.unity_utils import prepare_environment
from UnityPy import load as unity_load

from util.constants import APP_CONFIG, APP_SESSION
from util.encoding.card_merge import merge_data
from util.encoding.decrypt_card import decrypt_desc_indx_name
from util.image_utils import convert_image
from util.python_utils import replace_entry


class CardService(UnityService):

    def __init__(self):
        super().__init__("cards")
        self.unity_file: bool = False

    @override
    def replace_bundle(self) -> None:

        if not self.bundle or not self.image_path:
            return

        f_path = prepare_environment(self.unity_file, self.bundle)
        env = unity_load(f_path)

        for obj in env.objects:
            if obj.type.name == "Texture2D":

                data = obj.read()

                img = convert_image(self.image_path)

                data.m_Width, data.m_Height = img.size

                data.set_image(
                    img=img,
                    target_format=TextureFormat.RGBA32,
                    mipmap_count=APP_CONFIG.mipmap_count,
                )

                data.save()
                break

        with open(f_path, "wb") as f:
            f.write(env.file.save(packer=APP_CONFIG.packer))

    def get_names(self) -> list[str]:
        return [card.name for card in session.query(CardModel).all()]

    def update_card_files(self) -> None:

        metadata: list[CardMetadataModel] = (
            session.query(CardMetadataModel)
            .filter(
                or_(
                    CardMetadataModel.name == "card_indx.bytes",
                    CardMetadataModel.name == "card_desc.bytes",
                    CardMetadataModel.name == "card_name.bytes",
                )
            )
            .all()
        )

        for entry in metadata:
            f_path = prepare_environment(False, entry.bundle)
            env = unity_load(f_path)
            for obj in env.objects:
                if obj.type.name == "TextAsset":
                    data = obj.read()
                    if hasattr(data, "m_Script"):
                        entry.data = data.m_Script

        session.commit()

        decrypt_desc_indx_name()

    def replace_card_data(self, file: CardMetadataModel, metadata):
        f_path = prepare_environment(False, file.bundle)
        env = unity_load(f_path)
        for obj in env.objects:
            if obj.type.name == "TextAsset":
                data = obj.read()
                if hasattr(data, "m_Script"):
                    data.m_Script = metadata
                    data.save()

                    break

        with open(f_path, "wb") as f:
            f.write(env.file.save(packer=APP_CONFIG.packer))

    def replace_name(self, name) -> None:
        card = session.query(CardModel).where(CardModel.bundle == self.bundle).first()

        if card:

            if not APP_SESSION.fresh_card_metadata:
                self.update_card_files()
                APP_SESSION.fresh_card_metadata = True

            data_file: CardMetadataModel = (
                session.query(CardMetadataModel)
                .filter(CardMetadataModel.name == "card_name.bytes")
                .first()
            )

            data_file.data_json = replace_entry(
                card.data_index, data_file.data_json, name
            )
            card.modded_name = name

            session.commit()

            name_data, desc_data, indx_data = merge_data()

            self.replace_card_data(data_file, name_data)
            self.replace_card_data(
                session.query(CardMetadataModel)
                .filter(CardMetadataModel.name == "card_desc.bytes")
                .first(),
                desc_data,
            )
            self.replace_card_data(
                session.query(CardMetadataModel)
                .filter(CardMetadataModel.name == "card_indx.bytes")
                .first(),
                indx_data,
            )

    def replace_description(self, description) -> None:
        card = session.query(CardModel).where(CardModel.bundle == self.bundle).first()

        if card:
            if not APP_SESSION.fresh_card_metadata:
                self.update_card_files()
                APP_SESSION.fresh_card_metadata = True

            data_file: CardMetadataModel = (
                session.query(CardMetadataModel)
                .filter(CardMetadataModel.name == "card_desc.bytes")
                .first()
            )

            data_file.data_json = replace_entry(
                card.data_index, data_file.data_json, description
            )
            card.modded_description = description

            session.commit()

            name_data, desc_data, indx_data = merge_data()

            self.replace_card_data(data_file, desc_data)
            self.replace_card_data(
                session.query(CardMetadataModel)
                .filter(CardMetadataModel.name == "card_name.bytes")
                .first(),
                name_data,
            )
            self.replace_card_data(
                session.query(CardMetadataModel)
                .filter(CardMetadataModel.name == "card_indx.bytes")
                .first(),
                indx_data,
            )
