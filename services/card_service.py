import re
from os.path import basename, splitext

from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat
from sqlalchemy import or_
from typing_extensions import override

from database.models import CardModel, CardMetadataModel
from database.objects import session
from services.unity_service import UnityService
from unity.unity_utils import prepare_environment

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

    @staticmethod
    def _script_to_bytes(script: str | bytes | bytearray) -> bytes:
        """Convert a UnityPy TextAsset script to its original binary data."""
        if isinstance(script, str):
            return script.encode("utf-8", "surrogateescape")
        return bytes(script)

    @staticmethod
    def _bytes_to_script(data: bytes | bytearray) -> str:
        """Convert binary card metadata to UnityPy's TextAsset representation."""
        return bytes(data).decode("utf-8", "surrogateescape")

    @staticmethod
    def _text_asset_name(metadata_name: str) -> str:
        """Return the Unity TextAsset name associated with a metadata filename."""
        return splitext(basename(metadata_name))[0].casefold()

    def _get_text_asset(self, env, metadata_name: str):
        """Find the exact TextAsset for a card metadata file.

        Master Duel bundles can contain more than one object.  Matching the
        TextAsset name prevents silently reading or overwriting an unrelated
        object if their order changes after a game update.
        """
        expected_name = self._text_asset_name(metadata_name)

        for obj in env.objects:
            if obj.type.name != "TextAsset":
                continue

            data = obj.read()
            if getattr(data, "m_Name", "").casefold() == expected_name:
                return data

        raise RuntimeError(
            f"Could not find the {metadata_name} TextAsset in its game bundle. "
            "Card text was not changed."
        )

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
            data = self._get_text_asset(env, entry.name)
            entry.data = self._script_to_bytes(data.m_Script)

        session.commit()

        decrypt_desc_indx_name()

    def replace_card_data(self, file: CardMetadataModel, metadata):
        f_path = prepare_environment(False, file.bundle)
        env = unity_load(f_path)
        data = self._get_text_asset(env, file.name)
        data.m_Script = self._bytes_to_script(metadata)
        data.save()

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

            try:
                session.flush()
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
            except Exception:
                session.rollback()
                raise
            session.commit()

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

            try:
                session.flush()
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
            except Exception:
                session.rollback()
                raise
            session.commit()

    def replace_text_with_regex(
        self,
        pattern: str,
        replacement: str,
        replace_names: bool,
        replace_descriptions: bool,
        card: CardModel | None = None,
    ) -> tuple[int, int]:
        """Replace matching text on one card or throughout the card database.

        Returns the number of cards changed and the total number of matches
        replaced. The card metadata files are rebuilt once for the whole batch.
        """
        regex = re.compile(pattern)
        cards = [card] if card else session.query(CardModel).all()
        changes = []
        replacement_count = 0

        for target_card in cards:
            name = None
            description = None

            if replace_names:
                current_name = (
                    target_card.modded_name
                    if target_card.modded_name is not None
                    else target_card.name
                )
                name, name_count = regex.subn(replacement, current_name)
                if name_count == 0:
                    name = None
                replacement_count += name_count

            if replace_descriptions:
                current_description = (
                    target_card.modded_description
                    if target_card.modded_description is not None
                    else target_card.description
                )
                description, description_count = regex.subn(
                    replacement, current_description
                )
                if description_count == 0:
                    description = None
                replacement_count += description_count

            if name is not None or description is not None:
                changes.append((target_card, name, description))

        if not changes:
            return 0, 0

        if not APP_SESSION.fresh_card_metadata:
            self.update_card_files()
            APP_SESSION.fresh_card_metadata = True

        name_file: CardMetadataModel = (
            session.query(CardMetadataModel)
            .filter(CardMetadataModel.name == "card_name.bytes")
            .first()
        )
        description_file: CardMetadataModel = (
            session.query(CardMetadataModel)
            .filter(CardMetadataModel.name == "card_desc.bytes")
            .first()
        )
        index_file: CardMetadataModel = (
            session.query(CardMetadataModel)
            .filter(CardMetadataModel.name == "card_indx.bytes")
            .first()
        )

        for target_card, name, description in changes:
            if name is not None:
                name_file.data_json = replace_entry(
                    target_card.data_index, name_file.data_json, name
                )
                target_card.modded_name = name
            if description is not None:
                description_file.data_json = replace_entry(
                    target_card.data_index, description_file.data_json, description
                )
                target_card.modded_description = description

        try:
            session.flush()
            name_data, description_data, index_data = merge_data()
            self.replace_card_data(name_file, name_data)
            self.replace_card_data(description_file, description_data)
            self.replace_card_data(index_file, index_data)
        except Exception:
            session.rollback()
            raise
        session.commit()

        return len(changes), replacement_count

    def restore_text_edits(self, cards: list[CardModel]) -> int:
        """Restore saved text edits and rebuild card metadata once for the batch."""
        if not cards:
            return 0

        if not APP_SESSION.fresh_card_metadata:
            self.update_card_files()
            APP_SESSION.fresh_card_metadata = True

        name_file: CardMetadataModel = (
            session.query(CardMetadataModel)
            .filter(CardMetadataModel.name == "card_name.bytes")
            .first()
        )
        description_file: CardMetadataModel = (
            session.query(CardMetadataModel)
            .filter(CardMetadataModel.name == "card_desc.bytes")
            .first()
        )
        index_file: CardMetadataModel = (
            session.query(CardMetadataModel)
            .filter(CardMetadataModel.name == "card_indx.bytes")
            .first()
        )

        for card in cards:
            if card.modded_name is not None:
                name_file.data_json = replace_entry(
                    card.data_index, name_file.data_json, card.name
                )
                card.modded_name = None
            if card.modded_description is not None:
                description_file.data_json = replace_entry(
                    card.data_index, description_file.data_json, card.description
                )
                card.modded_description = None

        try:
            session.flush()
            name_data, description_data, index_data = merge_data()
            self.replace_card_data(name_file, name_data)
            self.replace_card_data(description_file, description_data)
            self.replace_card_data(index_file, index_data)
        except Exception:
            session.rollback()
            raise
        session.commit()

        return len(cards)
