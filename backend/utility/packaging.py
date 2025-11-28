from pathlib import Path
import zipfile
from typing import Iterable


def collect_files_to_zip(file_paths: Iterable[str | Path], zip_path: str | Path) -> Path:
    """
    Collects the given files into a single zip archive.

    Args:
        file_paths: Paths to files that should be zipped.
        zip_path: Destination path for the output zip file.

    Returns:
        Path to the created zip archive.

    Raises:
        FileNotFoundError: If any of the provided paths is not a file.
    """
    destination = Path(zip_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in file_paths:
            path_obj = Path(file_path)
            if not path_obj.is_file():
                raise FileNotFoundError(f"File not found: {path_obj}")
            archive.write(path_obj, arcname=path_obj.name)

    return destination
