from os.path import basename, splitext

from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat
from sqlalchemy import or_
from typing_extensions import override

from database.models import CardModel, CardOcgModel, CardMetadataModel
from database.objects import session
from services.unity_service import UnityService
from services.full_art_service import FullArtService
from unity.unity_utils import prepare_environment

from util.card_text import preview_regex_replacement
from util.constants import APP_CONFIG, APP_SESSION
from util.encoding.card_merge import merge_data
from util.encoding.decrypt_card import decrypt_desc_indx_name
from util.image_utils import convert_image
from util.python_utils import replace_entry


class CardService(UnityService):

    def __init__(self):
        super().__init__("cards")
        self.unity_file: bool = False
        self.full_art = FullArtService()

    def get_art_details(self):
        """Read the art ID and dimensions from the selected texture, not DB IDs."""
        env = unity_load(prepare_environment(self.unity_file, self.bundle))
        for obj in env.objects:
            if obj.type.name == "Texture2D":
                texture = obj.read()
                try:
                    art_id = int(texture.m_Name)
                except ValueError:
                    art_id = None
                if art_id is not None and not 0 < art_id <= 65535:
                    art_id = None
                return art_id, (texture.m_Width, texture.m_Height)
        raise RuntimeError("No card artwork texture found in the selected bundle.")

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
        return [card.name for card in session.query(self._card_model()).all()]

    @staticmethod
    def _card_model():
        """Return the card table for the region selected on the main window."""
        return CardOcgModel if APP_CONFIG.asset_region == "ocg" else CardModel

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
        card_model = self._card_model()
        card = session.query(card_model).where(card_model.bundle == self.bundle).first()

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
        card_model = self._card_model()
        card = session.query(card_model).where(card_model.bundle == self.bundle).first()

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
        cards: list | None = None,
    ) -> tuple[int, int]:
        """Replace matching text on one card, an explicit set, or all cards.

        Returns the number of cards changed and the total number of matches
        replaced. The card metadata files are rebuilt once for the whole batch.
        """
        if cards is None:
            cards = (
                [card] if card is not None else session.query(self._card_model()).all()
            )
        changes = preview_regex_replacement(
            cards, pattern, replacement, replace_names, replace_descriptions
        )
        replacement_count = sum(change.replacements for change in changes)

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

        for change in changes:
            for field, (_, after) in change.fields.items():
                data_file = name_file if field == "name" else description_file
                data_file.data_json = replace_entry(
                    change.card.data_index, data_file.data_json, after
                )
                setattr(change.card, f"modded_{field}", after)

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
