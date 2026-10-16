"""Inspect ZIPs before reading allowlisted components; never extract to disk."""

import io
import ntpath
import stat
import zipfile
from pathlib import PurePosixPath

from app.core.uploads import UploadSettings
from app.services.import_records import ParseFailure

EXTENSIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}


def shapefile_members(data: bytes, limits: UploadSettings) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > limits.max_zip_files:
                raise ParseFailure("ZIP_TOO_MANY_FILES")
            total = 0
            selected: dict[str, zipfile.ZipInfo] = {}
            stems: set[str] = set()
            names: set[str] = set()
            for item in entries:
                name = item.orig_filename
                path = PurePosixPath(name)
                mode = item.external_attr >> 16
                if (
                    "\x00" in name
                    or "\\" in name
                    or path.is_absolute()
                    or ".." in path.parts
                    or ntpath.splitdrive(name)[0]
                    or stat.S_ISLNK(mode)
                    or item.flag_bits & 1
                ):
                    raise ParseFailure("UNSAFE_ZIP")
                if name.casefold() in names:
                    raise ParseFailure("DUPLICATE_ZIP_ENTRY")
                names.add(name.casefold())
                total += item.file_size
                if total > limits.max_expanded_bytes:
                    raise ParseFailure("ZIP_EXPANDED_LIMIT")
                if item.file_size > max(1, item.compress_size) * limits.max_zip_ratio:
                    raise ParseFailure("ZIP_RATIO_LIMIT")
                if item.is_dir() or path.suffix.lower() not in EXTENSIONS:
                    continue
                stems.add(str(path.with_suffix("")).casefold())
                suffix = path.suffix.lower()
                if suffix in selected:
                    raise ParseFailure("MULTIPLE_SHAPEFILE_LAYERS")
                selected[suffix] = item
            if len(stems) != 1 or not {".shp", ".shx", ".dbf"} <= selected.keys():
                raise ParseFailure("SHAPEFILE_COMPONENTS_REQUIRED")
            result = {}
            for suffix, item in selected.items():
                with archive.open(item) as stream:
                    value = stream.read(min(item.file_size, limits.max_expanded_bytes) + 1)
                if len(value) != item.file_size:
                    raise ParseFailure("ZIP_SIZE_MISMATCH")
                result[suffix] = value
            return result
    except ParseFailure:
        raise
    except Exception:
        raise ParseFailure("INVALID_ZIP") from None
