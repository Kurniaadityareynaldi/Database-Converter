"""
===============================================================================
QR DATABASE CONVERTER
main.py

Program Orchestrator

Author  : Kurnia Project
Version : 1.0.0

Description
-----------
Entry point program. Menjalankan seluruh pipeline konversi CSV -> Binary.

Alur
----

Program Start
      |
      v
Load Config
      |
      v
Cari file CSV
      |
      v
CSVDatabase.load()
      |
      v
Validator.run()
      |
      +-- gagal --> Stop Program
      |
      v
BuildDatabase.build()
      |
      v
database.bin / brand.bin / material.bin / use_to.bin / size.bin / metadata.bin
      |
      v
Print Summary
      |
      v
Done

Usage
-----
    python main.py                  # auto-cari file .csv di folder saat ini
    python main.py path/ke/file.csv # pakai file csv tertentu
===============================================================================
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List, Optional

import config
from builder import BuildDatabase, BuildResult
from database import CSVDatabase
from validator import ValidationError, Validator


# =============================================================================
# LOGGER (print ke console + log file)
# =============================================================================

class Logger:
    """
    Duplikasi seluruh output print() ke console dan ke file log.

    Aktif hanya jika config.ENABLE_LOG = True.
    """

    def __init__(self, log_file: Path, enabled: bool):

        self.enabled = enabled

        self.terminal = sys.stdout

        self.log = None

        if self.enabled:

            self.log = open(log_file, "a", encoding="utf-8")

    def write(self, message: str) -> None:

        self.terminal.write(message)

        if self.log is not None:

            self.log.write(message)

    def flush(self) -> None:

        self.terminal.flush()

        if self.log is not None:

            self.log.flush()

    def close(self) -> None:

        if self.log is not None:

            self.log.close()


# =============================================================================
# STEP 1 : LOAD CONFIG
# =============================================================================

def load_config() -> None:

    print()
    print("#" * 70)
    print(f"# {config.APP_NAME} - v{config.VERSION}")
    print("#" * 70)
    print()

    print(f"Output Folder : {config.OUTPUT_FOLDER.resolve()}")
    print(f"Log Folder    : {config.LOG_FOLDER.resolve()}")
    print()


# =============================================================================
# STEP 2 : CARI FILE CSV
# =============================================================================

def find_csv(argv: List[str]) -> Path:
    """
    Mencari file CSV yang akan diproses.

    Prioritas:

    1. Argument command line   (python main.py file.csv)
    2. Folder "input/"         (jika ada)
    3. Folder kerja saat ini   (current directory)
    """

    print("=" * 70)
    print("CARI FILE CSV")
    print("=" * 70)
    print()

    # -- 1. Argument command line --------------------------------------------

    if len(argv) > 1:

        candidate = Path(argv[1])

        if not candidate.exists():

            raise FileNotFoundError(

                f"File CSV tidak ditemukan : {candidate}"
            )

        print(f"Menggunakan file dari argument : {candidate}")
        print()

        return candidate

    # -- 2. Folder input/ -----------------------------------------------------

    search_dirs = []

    input_dir = Path("input")

    if input_dir.is_dir():

        search_dirs.append(input_dir)

    search_dirs.append(Path("."))

    found: List[Path] = []

    for directory in search_dirs:

        found = sorted(

            directory.glob(f"*{config.SUPPORTED_EXTENSION}")
        )

        if found:

            break

    if not found:

        raise FileNotFoundError(

            f"Tidak ada file {config.SUPPORTED_EXTENSION} ditemukan. "
            f"Letakkan file CSV di folder 'input/' atau folder ini, "
            f"atau jalankan: python main.py <file.csv>"
        )

    if len(found) > 1:

        print("Ditemukan beberapa file CSV :")

        for item in found:

            print(f"  - {item}")

        print()

        print(f"Menggunakan file pertama : {found[0]}")

    else:

        print(f"File CSV ditemukan : {found[0]}")

    print()

    return found[0]


# =============================================================================
# STEP 3 : PROGRESS CALLBACK
# =============================================================================

def make_progress_callback():

    if not config.ENABLE_PROGRESS:

        return None

    def callback(current: int, total: int) -> None:

        if current == total or current % config.PROGRESS_STEP == 0:

            print(

                f"\r  Progress : {current:,} / {total:,}",

                end="" if current != total else "\n",

                flush=True,
            )

    return callback


# =============================================================================
# STEP 4 : BUILD
# =============================================================================

def build_database(products, output_dir: Path) -> BuildResult:

    builder = BuildDatabase()

    return builder.build(products, output_dir)


# =============================================================================
# STEP 5 : PRINT SUMMARY
# =============================================================================

def print_summary(

    csv_path: Path,

    database: CSVDatabase,

    build_result: BuildResult,

    elapsed: float,

) -> None:

    if not config.PRINT_SUMMARY:

        return

    stat = database.statistics()

    print()
    print("=" * 70)
    print("RINGKASAN")
    print("=" * 70)

    print(f"File Sumber       : {csv_path}")
    print(f"Total Record      : {stat['total_record']:,}")
    print(f"Brand             : {stat['brand']}")
    print(f"Material          : {stat['material']}")
    print(f"Use To            : {stat['use_to']}")
    print(f"Size              : {stat['size']}")

    print("-" * 70)

    print(f"Output Folder     : {build_result.output_dir.resolve()}")

    for name, path in (

        ("database.bin", config.DATABASE_BIN),

        ("brand.bin", config.BRAND_BIN),

        ("material.bin", config.MATERIAL_BIN),

        ("use_to.bin", config.USE_TO_BIN),

        ("size.bin", config.SIZE_BIN),

        ("metadata.bin", config.METADATA_BIN),

    ):

        full_path = build_result.output_dir / path.name

        size = full_path.stat().st_size if full_path.exists() else 0

        print(f"  {name:<15}: {size:,} bytes")

    print("-" * 70)

    print(f"CRC32             : {build_result.crc32:#010x}")
    print(f"Record Ditulis    : {build_result.record_count:,}")
    print(f"Waktu Proses      : {elapsed:.2f} detik")

    print("=" * 70)
    print()
    print("DONE.")
    print()


# =============================================================================
# MAIN
# =============================================================================

def main(argv: Optional[List[str]] = None) -> int:

    argv = argv if argv is not None else sys.argv

    start_time = time.time()

    logger = Logger(config.LOG_FILE, config.ENABLE_LOG)

    original_stdout = sys.stdout

    sys.stdout = logger

    try:

        # -- Step 1 : Load Config --------------------------------------------

        load_config()

        # -- Step 2 : Cari file CSV ------------------------------------------

        csv_path = find_csv(argv)

        # -- Step 3 : CSVDatabase.load() --------------------------------------

        database = CSVDatabase(csv_path)

        database.set_progress_callback(make_progress_callback())

        database.load()

        database.validate_basic()

        database.sort_by_bottle()

        database.print_statistics()

        # -- Step 4 : Validator.run() -----------------------------------------

        validator = Validator(database)

        try:

            validator.run(raise_on_error=True)

        except ValidationError as err:

            print()
            print("!" * 70)
            print("VALIDASI GAGAL - PROGRAM DIHENTIKAN")
            print("!" * 70)
            print(str(err))
            print()

            return 1

        # -- Step 5 : BuildDatabase.build() -------------------------------------

        build_result = build_database(

            database.get_records(),

            config.OUTPUT_FOLDER,
        )

        # -- Step 6 : Print Summary ---------------------------------------------

        elapsed = time.time() - start_time

        print_summary(

            csv_path,

            database,

            build_result,

            elapsed,
        )

        return 0

    except FileNotFoundError as err:

        print()
        print("ERROR :", err)
        print()

        return 1

    except Exception as err:  # noqa: BLE001

        print()
        print("=" * 70)
        print("UNEXPECTED ERROR")
        print("=" * 70)
        print(f"{type(err).__name__}: {err}")
        print("=" * 70)
        print()

        return 1

    finally:

        sys.stdout = original_stdout

        logger.close()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    sys.exit(main())
