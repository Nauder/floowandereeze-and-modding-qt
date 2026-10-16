"""File-based backup inventory and portable ZIP archives."""

import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

CATEGORY_LABELS = {
    "summon_animations": "Summon Animations",
    "cards": "Cards",
    "sleeves": "Sleeves",
    "faces": "Faces",
    "icons": "Player & Card Icons",
    "fields": "Fields",
    "wallpapers": "Wallpapers",
    "coins": "Coins",
    "deck_boxes": "Deck Boxes",
    "background": "Background",
}


@dataclass(frozen=True)
class BackupEntry:
    """A file relative to the application's backups directory."""

    name: str
    size: int

    @property
    def category(self):
        """Group nested files by their top-level backup folder."""
        parts = PurePosixPath(self.name).parts
        return parts[0] if len(parts) > 1 else "background"


class BackupService:
    """Operate on actual files, including backups without database records."""

    MAX_ARCHIVE_SIZE = 4 * 1024**3
    MAX_ARCHIVE_FILES = 100000

    def __init__(self, root="backups"):
        self.root = Path(root).resolve()

    @staticmethod
    def _validate_name(name):
        parts = name.split("/")
        if not name or any(
            part in ("", ".", "..")
            or any(char in part for char in '\\:<>"|?*')
            or part.endswith((".", " "))
            or any(ord(char) < 32 for char in part)
            or part.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *[f"COM{i}" for i in range(10)],
                *[f"LPT{i}" for i in range(10)],
            }
            for part in parts
        ):
            raise ValueError(f"Unsafe backup path: {name}")
        return name

    def _path(self, name):
        self._validate_name(name)
        path = self.root.joinpath(*name.split("/"))
        resolved = path.resolve()
        if self.root not in resolved.parents:
            raise ValueError(f"Backup path leaves the backup directory: {name}")
        return path

    def inventory(self):
        """List actual backup files, including nested and uncatalogued files."""
        entries = []
        if self.root.is_dir():
            for path in self.root.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    name = path.relative_to(self.root).as_posix()
                    self._path(name)
                    entries.append(BackupEntry(name, path.stat().st_size))
        return sorted(entries, key=lambda entry: entry.name.casefold())

    def inspect_archive(self, archive):
        """Validate all member paths before displaying or importing an archive."""
        entries, seen, total = [], set(), 0
        with ZipFile(archive) as source:
            for member in source.infolist():
                if "\\" in member.orig_filename:
                    raise ValueError(f"Unsafe backup path: {member.orig_filename}")
                name = (
                    member.filename.rstrip("/") if member.is_dir() else member.filename
                )
                self._validate_name(name)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Archives cannot contain symbolic links.")
                if member.is_dir():
                    continue
                if name.casefold() in seen:
                    raise ValueError(f"Duplicate backup path: {name}")
                seen.add(name.casefold())
                total += member.file_size
                if total > self.MAX_ARCHIVE_SIZE or len(seen) > self.MAX_ARCHIVE_FILES:
                    raise ValueError("Archive exceeds 4 GiB or 100,000 backup files.")
                entries.append(BackupEntry(name, member.file_size))
        for name in seen:
            if any(parent.as_posix() in seen for parent in PurePosixPath(name).parents):
                raise ValueError(
                    "Archive contains conflicting file and directory paths."
                )
        return sorted(entries, key=lambda entry: entry.name.casefold())

    def export_archive(self, archive, names):
        """Write to a temporary file so failures preserve an existing export."""
        destination = Path(archive).resolve()
        paths = [(name, self._path(name)) for name in dict.fromkeys(names)]
        if not paths:
            raise ValueError("Choose at least one backup.")
        if any(path.resolve() == destination for _, path in paths):
            raise ValueError("The export cannot replace a backup file.")
        temporary = None
        try:
            with NamedTemporaryFile(dir=destination.parent, delete=False) as file:
                temporary = Path(file.name)
            with ZipFile(temporary, "w", ZIP_DEFLATED) as output:
                for name, path in paths:
                    output.write(path, name)
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return len(paths)

    def import_archive(self, archive, names, overwrite=False):
        """Stage and CRC-check selected files before changing local backups."""
        available = {entry.name for entry in self.inspect_archive(archive)}
        names = list(dict.fromkeys(names))
        if not names or not set(names) <= available:
            raise ValueError("Choose backup files from this archive.")
        targets = [(name, self._path(name)) for name in names]
        targets = [
            (name, path) for name, path in targets if overwrite or not path.exists()
        ]
        with TemporaryDirectory() as folder, ZipFile(archive) as source:
            for index, (name, _) in enumerate(targets):
                with (
                    source.open(name) as incoming,
                    open(Path(folder, str(index)), "wb") as output,
                ):
                    shutil.copyfileobj(incoming, output)
            for index, (_, path) in enumerate(targets):
                path.parent.mkdir(parents=True, exist_ok=True)
                with NamedTemporaryFile(dir=path.parent, delete=False) as output:
                    temporary = Path(output.name)
                try:
                    shutil.copyfile(Path(folder, str(index)), temporary)
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
        return len(targets), len(names) - len(targets)

    def delete(self, names):
        """Remove only the requested files after validating all paths."""
        paths = [self._path(name) for name in dict.fromkeys(names)]
        count = 0
        for path in paths:
            if path.is_file():
                path.unlink()
                count += 1
        return count


def sync_backup_flags(service):
    """Update loaded ORM assets from their actual restore-source files."""
    from database import models
    from database.objects import session
    from util.image_utils import slugify

    mappings = (
        (models.CardModel, "cards", ("bundle",)),
        (models.CardOcgModel, "cards", ("bundle",)),
        (models.SleeveModel, "sleeves", ("bundle",)),
        (models.SleeveOcgModel, "sleeves", ("bundle",)),
        (models.CardIconModel, "icons", ("name",)),
        (models.FaceModel, "faces", ("name",)),
        (models.IconModel, "icons", ("bundle_big",)),
        (models.CoinModel, "coins", ("bundle_big",)),
        (models.FieldModel, "fields", ("bundle",)),
        (models.WallpaperModel, "wallpapers", ("bundle_foreground",)),
        (
            models.DeckBoxModel,
            "deck_boxes",
            ("small", "medium", "o_medium", "r_medium", "large", "o_large", "r_large"),
        ),
    )
    existing = {entry.name.casefold() for entry in service.inventory()}
    for model, category, fields in mappings:
        for asset in session.query(model).all():
            asset.has_backup = any(
                f"{category}/{slugify(str(getattr(asset, field)))}.png".casefold()
                in existing
                for field in fields
                if getattr(asset, field)
            )
    session.commit()
