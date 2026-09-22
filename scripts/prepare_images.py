"""Prepare 1024-pixel task images from legitimately acquired, extracted local sources.

No downloads, credential handling, mirror fallback, or license acceptance is performed.
Transforms follow RadRead's original fetch_images.py for the five published sources.
"""

from __future__ import annotations

import argparse
import io
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "envs" / "radread-public"

try:
    import numpy as np
    from PIL import Image
except ImportError as error:
    raise SystemExit(
        f"Image preparation dependencies are missing: {error}. "
        f"Install them with: python -m pip install -r \"{ROOT / 'requirements.txt'}\""
    ) from error

SOURCES = ("nih-chestxray14", "chestdet", "vindr", "rsna", "graz")
PREFIXES = {
    "nih-chestxray14": "nih_",
    "chestdet": "chestdet_",
    "vindr": "vindr_",
    "rsna": "rsna_",
    "graz": "graz_",
}


def prepare(source: Path, target: Path, kind: str) -> None:
    """Apply the historical source-specific rendering, never annotations or window guesses."""
    data = source.read_bytes()
    if kind == "rsna":
        if data[128:132] != b"DICM":
            raise ValueError("RSNA input must be a DICOM file with a DICM preamble")
        try:
            import pydicom
        except ImportError as error:
            raise ValueError(
                "RSNA preparation requires pydicom. Install image dependencies with: "
                f"python -m pip install -r \"{ROOT / 'requirements.txt'}\""
            ) from error

        dataset = pydicom.dcmread(io.BytesIO(data))
        if str(dataset.file_meta.TransferSyntaxUID) == "1.2.840.10008.1.2.4.50":
            # Preserve the original helper's JPEG-baseline frame decode, without VOI,
            # rescale, or photometric inversion.
            start = data.index(struct.pack("<HH", 0x7FE0, 0x0010))
            soi = data.index(b"\xff\xd8\xff", start)
            eoi = data.rindex(b"\xff\xd9") + 2
            image = Image.open(io.BytesIO(data[soi:eoi]))
            image.load()
        elif not dataset.file_meta.TransferSyntaxUID.is_compressed:
            # The official distribution can contain raw 8-bit NIH pixels instead.
            # No normalization/windowing is introduced; reject incompatible encodings.
            pixels = dataset.pixel_array
            if pixels.dtype != np.uint8 or pixels.ndim != 2:
                raise ValueError(
                    "RSNA requires raw uint8 grayscale pixels or a JPEG-baseline frame"
                )
            image = Image.fromarray(pixels)
        else:
            raise ValueError(
                "RSNA requires JPEG-baseline or uncompressed uint8 DICOM; no guessed conversion"
            )
        if image.size != (1024, 1024) or image.mode != "L":
            raise ValueError(f"Unexpected RSNA frame {image.size} {image.mode}")
    else:
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(
                "Expected an original source PNG, not a renamed DICOM or JPEG"
            )
        image = Image.open(io.BytesIO(data))
        image.load()
        if kind == "vindr":
            if image.mode != "L":
                raise ValueError(
                    "VinDr requires an equivalent original-resolution L-mode PNG; DICOM rendering is unspecified"
                )
        elif kind == "graz":
            if image.mode != "L":
                image = Image.fromarray((np.asarray(image) >> 8).astype(np.uint8), "L")
        elif kind in ("nih-chestxray14", "chestdet"):
            if image.mode == "L" and image.size == (1024, 1024):
                target.write_bytes(
                    data
                )  # The original helper preserves exact PNG bytes.
                return
            image = image.convert("L")
        else:
            raise ValueError(f"Unknown source: {kind}")
        if image.size != (1024, 1024):
            image = image.resize((1024, 1024), Image.Resampling.LANCZOS)
    image.save(target)


def main() -> None:
    """Resolve source filenames below per-source directories and prepare requested studies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="Extracted files under <root>/<source>/ (recursive)",
    )
    parser.add_argument(
        "--sources", type=Path, default=BUNDLE / "environment" / "sources.jsonl"
    )
    parser.add_argument(
        "--output", type=Path, default=BUNDLE / "environment" / "images"
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=SOURCES,
        help="Prepare only these sources; repeatable",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace generated image files explicitly",
    )
    args = parser.parse_args()
    selected = set(args.source or SOURCES)
    try:
        rows = [
            json.loads(line)
            for line in args.sources.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        rows = [row for row in rows if row["source"] in selected]
        if not rows:
            raise ValueError("No requested sources in the manifest")
        indices: dict[str, dict[str, list[Path]]] = {}
        for kind in selected:
            directory = args.input_root / kind
            index: dict[str, list[Path]] = {}
            if directory.is_dir():
                for path in directory.rglob("*"):
                    if path.is_file() and path.suffix.lower() in (
                        ".png",
                        ".dcm",
                        ".dicom",
                    ):
                        index.setdefault(path.name, []).append(path)
            indices[kind] = index
        jobs = []
        errors = []
        seen = set()
        for row in rows:
            kind, study_id = row["source"], row["study_id"]
            stem = study_id.removeprefix(PREFIXES[kind])
            if not stem or any(
                c
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for c in study_id
            ):
                raise ValueError(f"Unsafe study ID: {study_id!r}")
            if study_id in seen:
                raise ValueError(f"Duplicate study ID: {study_id}")
            seen.add(study_id)
            names = [
                stem + suffix
                for suffix in ((".dcm", ".dicom") if kind == "rsna" else (".png",))
            ]
            matches = [path for name in names for path in indices[kind].get(name, [])]
            target = args.output / (study_id.replace(":", "_") + ".png")
            if len(matches) != 1:
                errors.append(
                    f"{study_id}: expected exactly one of {names} below {args.input_root / kind}; found {len(matches)}"
                )
            elif matches[0].resolve() == target.resolve():
                errors.append(f"{study_id}: source and output must be different files")
            elif target.exists() and not args.overwrite:
                errors.append(
                    f"{target}: exists; use --overwrite to replace generated images"
                )
            else:
                jobs.append((matches[0], target, kind))
        if errors:
            raise ValueError("\n".join(errors))
        args.output.mkdir(parents=True, exist_ok=True)
        failures = []
        for source, target, kind in jobs:
            try:
                prepare(source, target, kind)
                print(f"{kind}: {source.name} -> {target.name}")
            except (OSError, ValueError, TypeError, KeyError) as error:
                failures.append(f"{target.name}: {error}")
        if failures:
            raise ValueError(
                "Preparation incomplete; successful files remain local:\n"
                + "\n".join(failures)
            )
        print(
            f"Prepared {len(jobs)} images. Do not commit or redistribute source pixels."
        )
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Image preparation failed: {error}\n")


if __name__ == "__main__":
    main()
