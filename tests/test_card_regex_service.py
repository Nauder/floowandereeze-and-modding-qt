"""Scoped application tests with in-memory metadata and mocked bundle writes."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import migrations, objects

# Keep model/config initialization and migrations away from the local database.
test_engine = create_engine("sqlite:///:memory:")
objects.base.metadata.create_all(test_engine)
test_session = sessionmaker(bind=test_engine)()
with (
    patch.object(objects, "engine", test_engine),
    patch.object(objects, "session", test_session),
    patch.object(migrations, "run_migrations"),
):
    from database.models import CardModel, CardOcgModel, CardMetadataModel
    from services import card_service


class ScopedRegexServiceTests(unittest.TestCase):
    def setUp(self):
        objects.base.metadata.create_all(test_engine)
        self.session = sessionmaker(bind=test_engine)()
        for table in reversed(objects.base.metadata.sorted_tables):
            self.session.execute(table.delete())
        for model in (CardModel, CardOcgModel):
            self.session.add_all(
                [
                    model(
                        id=index + 1,
                        name="HERO",
                        description="HERO effect",
                        bundle=str(index),
                        data_index=index,
                        favorite=index == 0,
                    )
                    for index in range(2)
                ]
            )
        for name, data in (
            ("card_name.bytes", "['HERO', 'HERO']"),
            ("card_desc.bytes", "['HERO effect', 'HERO effect']"),
            ("card_indx.bytes", "[]"),
        ):
            self.session.add(CardMetadataModel(name=name, data_json=data, bundle=name))
        self.session.commit()
        self.addCleanup(self.session.close)
        for name, value in (
            ("session", self.session),
            ("APP_CONFIG", SimpleNamespace(asset_region="tcg")),
            ("APP_SESSION", SimpleNamespace(fresh_card_metadata=True)),
        ):
            patcher = patch.object(card_service, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = card_service.CardService()

    def test_explicit_scope_matches_preview_and_writes_metadata_once(self):
        cards = self.session.query(CardModel).order_by(CardModel.id).all()
        with (
            patch.object(
                card_service, "merge_data", return_value=(b"n", b"d", b"i")
            ) as merge,
            patch.object(self.service, "replace_card_data") as write,
        ):
            result = self.service.replace_text_with_regex(
                "HERO", "Hero", True, True, cards=[cards[0]]
            )
        self.assertEqual(result, (1, 2))
        self.assertEqual(cards[0].modded_name, "Hero")
        self.assertIsNone(cards[1].modded_name)
        self.assertIsNone(cards[1].modded_description)
        merge.assert_called_once()
        self.assertEqual(write.call_count, 3)
        names = (
            self.session.query(CardMetadataModel)
            .filter_by(name="card_name.bytes")
            .one()
        )
        self.assertEqual(names.data_json, "['Hero', 'HERO']")

    def test_empty_scope_never_falls_back_to_selected_or_all_cards(self):
        card = self.session.query(CardModel).first()
        with patch.object(self.service, "replace_card_data") as write:
            result = self.service.replace_text_with_regex(
                "HERO", "Hero", True, True, card=card, cards=[]
            )
        self.assertEqual(result, (0, 0))
        write.assert_not_called()
        self.assertIsNone(card.modded_name)

    def test_all_cards_uses_current_region(self):
        card_service.APP_CONFIG.asset_region = "ocg"
        with (
            patch.object(card_service, "merge_data", return_value=(b"n", b"d", b"i")),
            patch.object(self.service, "replace_card_data"),
        ):
            result = self.service.replace_text_with_regex("HERO", "Hero", True, False)
        self.assertEqual(result, (2, 2))
        self.assertTrue(
            all(c.modded_name == "Hero" for c in self.session.query(CardOcgModel))
        )
        self.assertTrue(
            all(c.modded_name is None for c in self.session.query(CardModel))
        )


if __name__ == "__main__":
    unittest.main()
