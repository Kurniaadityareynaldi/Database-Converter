"""
===============================================================================
QR DATABASE CONVERTER
config.py

Global Configuration

Author  : Kurnia Project
Version : 1.0.0
===============================================================================
"""

from pathlib import Path

# =============================================================================
# APPLICATION
# =============================================================================

APP_NAME = "QR Database Converter"
VERSION = "1.0.0"

# =============================================================================
# INPUT
# =============================================================================

SUPPORTED_EXTENSION = ".csv"
DEFAULT_ENCODING = "utf-8-sig"

# =============================================================================
# FOLDER
# =============================================================================

OUTPUT_FOLDER = Path("output")
LOG_FOLDER = Path("logs")

OUTPUT_FOLDER.mkdir(exist_ok=True)
LOG_FOLDER.mkdir(exist_ok=True)

# =============================================================================
# OUTPUT FILE
# =============================================================================

DATABASE_BIN = OUTPUT_FOLDER / "database.bin"

BRAND_BIN = OUTPUT_FOLDER / "brand.bin"

MATERIAL_BIN = OUTPUT_FOLDER / "material.bin"

USE_TO_BIN = OUTPUT_FOLDER / "use_to.bin"

SIZE_BIN = OUTPUT_FOLDER / "size.bin"

METADATA_BIN = OUTPUT_FOLDER / "metadata.bin"

INVALID_CSV = LOG_FOLDER / "invalid.csv"

DUPLICATE_CSV = LOG_FOLDER / "duplicate.csv"

LOG_FILE = LOG_FOLDER / "converter.log"

# =============================================================================
# CSV COLUMN
# =============================================================================

COL_BOTTLE = "bottle_no"

COL_BRAND = "bottle_code"

COL_MATERIAL = "material_type"

COL_USE_TO = "use_to"

COL_SIZE = "size_type"

COL_CASHBACK = "cashback"

CSV_COLUMNS = [

    COL_BOTTLE,

    COL_BRAND,

    COL_MATERIAL,

    COL_USE_TO,

    COL_SIZE,

    COL_CASHBACK

]

# =============================================================================
# VALIDATION
# =============================================================================

BOTTLE_LENGTH = 7

MIN_CASHBACK = 0

MAX_CASHBACK = 65535

PROGRESS_STEP = 1000

# =============================================================================
# DATABASE FORMAT
# =============================================================================

DATABASE_VERSION = 1

DATABASE_VERSION = 0

MAGIC = b"ALNR"

RECORD_SIZE = 18

SORT_COLUMN = COL_BOTTLE

# =============================================================================
# HASH (FNV1A 64-bit)
# =============================================================================

HASH_NAME = "FNV1A64"

FNV_OFFSET = 14695981039346656037

FNV_PRIME = 1099511628211

# =============================================================================
# DICTIONARY
# =============================================================================

MAX_BRAND = 65535

MAX_MATERIAL = 65535

MAX_USE_TO = 65535

MAX_SIZE = 65535

# =============================================================================
# WRITER
# =============================================================================

WRITE_BUFFER = 8192

# =============================================================================
# CRC32
# =============================================================================

CRC_POLYNOMIAL = 0xEDB88320

# =============================================================================
# METADATA
# =============================================================================

METADATA_VERSION = 1

HEADER_SIZE = 32

# =============================================================================
# BINARY FIELD SIZE (Byte)
# =============================================================================

HASH_SIZE = 8

BRAND_ID_SIZE = 2

MATERIAL_ID_SIZE = 2

USE_TO_ID_SIZE = 2

SIZE_ID_SIZE = 2

CASHBACK_SIZE = 4

# =============================================================================
# DEBUG
# =============================================================================

ENABLE_LOG = True

ENABLE_PROGRESS = True

PRINT_SUMMARY = True