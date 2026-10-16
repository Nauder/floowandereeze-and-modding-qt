"""Read and change the shared overframe gate without changing other cards."""

from pathlib import Path
from hashlib import sha256
from tempfile import NamedTemporaryFile
import os

from UnityPy import load as unity_load

from util.card_art import decode_full_art_entries, set_full_art_entry


class FullArtService:
    """Use verified live TextAssets; keep the original pairs for per-card undo."""

    KNOWN_BUNDLES = ("22817d01", "a589d3b5")

    def __init__(self):
        self.path = None
        self.game_path = None

    @staticmethod
    def _read(path):
        # Load bytes so UnityPy cannot keep a Windows file handle open during replace.
        env = unity_load(Path(path).read_bytes())
        for obj in env.objects:
            if obj.type.name == "TextAsset":
                asset = obj.read()
                if asset.m_Name.casefold() == "of_card_asset":
                    script = asset.m_Script
                    data = (
                        script.encode("utf-8", "surrogateescape")
                        if isinstance(script, str)
                        else bytes(script)
                    )
                    decode_full_art_entries(data)
                    return env, asset, data
        raise RuntimeError("The bundle does not contain the of_card_asset TextAsset.")

    def locate(self, game_path):
        """Check current and legacy locations, including shipped assets."""
        if self.game_path != game_path:
            self.path = None
            self.game_path = game_path
        if self.path is not None:
            self._read(self.path)
            return self.path
        local = Path(game_path) / "0000"
        streaming = (
            Path(game_path).parent.parent
            / "masterduel_Data"
            / "StreamingAssets"
            / "AssetBundle"
        )
        for bundle in self.KNOWN_BUNDLES:
            for root in (local, streaming):
                path = root / bundle[:2] / bundle
                if path.is_file():
                    try:
                        self._read(path)
                    except (OSError, ValueError, RuntimeError):
                        continue
                    self.path = path
                    return path
        raise RuntimeError(
            "Overframe data could not be located. Use Locate overframe data to "
            "select the game's of_card_asset bundle."
        )

    def select_path(self, path, game_path):
        """Validate a user-selected bundle before remembering its location."""
        self._read(path)
        self.path = Path(path)
        self.game_path = game_path

    def _backup_path(self):
        account = sha256(str(Path(self.game_path).resolve()).encode()).hexdigest()[:16]
        return (
            Path("backups") / "cards" / "full_art" / account / f"{self.path.name}.bytes"
        )

    def status(self, game_path, art_id):
        """Return live membership and whether this texture ID can be edited."""
        self.locate(game_path)
        _, _, data = self._read(self.path)
        full_art = any(t == art_id for t, _ in decode_full_art_entries(data))
        return full_art, isinstance(art_id, int) and 0 < art_id <= 65535

    def set_enabled(self, game_path, art_id, enabled, packer):
        """Re-read live data before each edit and atomically replace the bundle."""
        self.locate(game_path)
        env, asset, data = self._read(self.path)
        backup = self._backup_path()
        saved = backup.read_bytes() if backup.is_file() else b""
        saved_entries = decode_full_art_entries(saved)
        live_entries = decode_full_art_entries(data)
        original = next((e for e in live_entries if e[0] == art_id), None)
        if enabled:
            entry = next(
                (e for e in saved_entries if e[0] == art_id),
                original if original is not None else (art_id, art_id),
            )
            changed = set_full_art_entry(data, art_id, entry)
        else:
            changed = set_full_art_entry(data, art_id)
            if original and not any(e[0] == art_id for e in saved_entries):
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(set_full_art_entry(saved, art_id, original))
        if changed == data:
            return
        asset.m_Script = changed.decode("utf-8", "surrogateescape")
        asset.save()
        payload = env.file.save(packer=packer.casefold())
        temporary = None
        try:
            with NamedTemporaryFile(dir=self.path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(payload)
            _, _, verified = self._read(temporary)
            if verified != changed:
                raise RuntimeError(
                    "Overframe bundle verification failed; no changes saved."
                )
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
