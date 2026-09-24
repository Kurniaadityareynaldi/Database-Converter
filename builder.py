"""
===============================================================================
QR DATABASE CONVERTER
builder.py

Binary Database Builder

Author  : Kurnia Project
Version : 2.0.0

Description
-----------
Module ini bertugas mengubah ProductRecord hasil validasi menjadi database
binary (.bin) yang siap digunakan ESP32.

Tahapan Build

CSV
 ↓
Validator
 ↓
Builder
 ↓
database.bin
brand.bin
material.bin
use_to.bin
size.bin
metadata.bin

Output sudah diurutkan berdasarkan bottleHash sehingga ESP32 cukup melakukan
Binary Search tanpa membaca seluruh file.

===============================================================================
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import config


# =============================================================================
# Binary Format
# =============================================================================

MAGIC_DATABASE = b"QRDB"

DATABASE_VERSION = 1

ENDIAN = "<"          # Little Endian

RECORD_STRUCT = struct.Struct(
    "<QHHHHI"
)

RECORD_FORMAT = "<QHHHHI"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)

# =============================================================================
# Binary Record
# =============================================================================

@dataclass(slots=True)
class BinaryRecord:
    """
    Satu record biner siap ditulis ke database.bin
    """

    bottle_hash: int

    brand_id: int

    material_id: int

    use_to_id: int

    size_id: int

    cashback: int

    def pack(self) -> bytes:
        """
        Convert menjadi bytes.
        """

        return RECORD_STRUCT.pack(
            self.bottle_hash,
            self.brand_id,
            self.material_id,
            self.use_to_id,
            self.size_id,
            self.cashback,
        )


# =============================================================================
# Dictionary Data
# =============================================================================

@dataclass(slots=True)
class DictionaryData:
    """
    Hasil akhir dictionary.

    Tersedia dua bentuk data:

    1. Mapping
       Digunakan saat proses build.

    2. List
       Digunakan saat proses write
       menjadi *.bin.
    """

    brand_to_id: Dict[str, int]

    material_to_id: Dict[str, int]

    use_to_id: Dict[str, int]

    size_to_id: Dict[str, int]

    brand_list: List[str]

    material_list: List[str]

    use_to_list: List[str]

    size_list: List[str]


# =============================================================================
# Build Result
# =============================================================================

@dataclass(slots=True)
class BuildResult:
    """
    Hasil proses build.
    """

    record_count: int

    crc32: int

    output_dir: Path

# =============================================================================
# FNV-1a 64-bit
# =============================================================================

FNV_OFFSET_BASIS = 0xCBF29CE484222325

FNV_PRIME = 0x100000001B3

UINT64_MASK = 0xFFFFFFFFFFFFFFFF


def fnv1a64(text: str) -> int:
    """
    Menghasilkan FNV-1a 64-bit.

    Algoritma ini WAJIB identik dengan implementasi di ESP32.

    Parameter
    ---------
    text : str

    Return
    ------
    uint64 integer
    """

    h = FNV_OFFSET_BASIS

    for b in text.encode("utf-8"):

        h ^= b

        h *= FNV_PRIME

        h &= UINT64_MASK

    return h

def make_bottle_hash(bottle_no: str) -> int:
    """
    Membuat hash bottle_no.

    Semua bottle_no dinormalisasi
    agar hasil hash selalu sama.

    Contoh

    " PE500XYSH "

    menjadi

    "PE500XYSH"
    """

    bottle_no = bottle_no.strip().upper()

    return fnv1a64(bottle_no)

def check_hash_collision(records) -> None:
    """
    Memastikan tidak ada collision hash.

    Collision sangat kecil kemungkinannya,
    tetapi tetap wajib dicek saat proses build.
    """

    seen = {}

    for item in records:

        h = make_bottle_hash(item.bottle_no)

        old = seen.get(h)

        if old is None:

            seen[h] = item.bottle_no

            continue

        if old != item.bottle_no:

            raise ValueError(
                "Hash Collision\n"
                f"{old}\n"
                f"{item.bottle_no}"
            )

# =============================================================================
# Dictionary Builder
# =============================================================================

class DictionaryBuilder:
    """
    Membangun dictionary ID.

    String yang sama hanya akan disimpan satu kali.

    Contoh

    Brand

        AQUA
        AQUA
        AQUA
        CLEO

    menjadi

        AQUA -> 0
        CLEO -> 1
    """

    def __init__(self):

        self.brand: Dict[str, int] = {}

        self.material: Dict[str, int] = {}

        self.use_to: Dict[str, int] = {}

        self.size: Dict[str, int] = {}

    # -------------------------------------------------------------------------

    @staticmethod
    def _normalize(value: str) -> str:
        """
        Normalisasi string.

        Semua dictionary menggunakan format yang sama.
        """

        return value.strip().upper()

    # -------------------------------------------------------------------------

    @staticmethod
    def _get_id(table: Dict[str, int], value: str) -> int:

        value = DictionaryBuilder._normalize(value)

        idx = table.get(value)

        if idx is not None:
            return idx

        idx = len(table)

        table[value] = idx

        return idx

    # -------------------------------------------------------------------------

    def brand_id(self, brand: str) -> int:

        return self._get_id(self.brand, brand)

    # -------------------------------------------------------------------------

    def material_id(self, material: str) -> int:

        return self._get_id(self.material, material)

    # -------------------------------------------------------------------------

    def use_to_id(self, use_to: str) -> int:

        return self._get_id(self.use_to, use_to)

    # -------------------------------------------------------------------------

    def size_id(self, size: str) -> int:

        return self._get_id(self.size, size)

    # -------------------------------------------------------------------------

    @staticmethod
    def _to_list(table: Dict[str, int]) -> List[str]:
        """
        Mengubah

        {
            "AQUA":0,
            "CLEO":1
        }

        menjadi

        [
            "AQUA",
            "CLEO"
        ]
        """

        result = [""] * len(table)

        for text, idx in table.items():

            result[idx] = text

        return result

    # -------------------------------------------------------------------------

    def export(self) -> DictionaryData:

        return DictionaryData(

            brand_to_id=self.brand,

            material_to_id=self.material,

            use_to_id=self.use_to,

            size_to_id=self.size,

            brand_list=self._to_list(self.brand),

            material_list=self._to_list(self.material),

            use_to_list=self._to_list(self.use_to),

            size_list=self._to_list(self.size),
        )

# =============================================================================
# Record Builder
# =============================================================================

class RecordBuilder:
    """
    Mengubah ProductRecord menjadi BinaryRecord.
    """

    def __init__(self):

        self.dictionary = DictionaryBuilder()

    # -------------------------------------------------------------------------

    def build_record(self, product) -> BinaryRecord:
        """
        Convert satu ProductRecord menjadi BinaryRecord.

        Parameter
        ---------
        product
            ProductRecord dari validator.py
        """

        bottle_hash = make_bottle_hash(product.bottle_no)

        brand_id = self.dictionary.brand_id(product.bottle_code)

        material_id = self.dictionary.material_id(product.material_type)

        use_to_id = self.dictionary.use_to_id(product.use_to)

        size_id = self.dictionary.size_id(product.size_type)

        cashback = int(product.cashback)

        return BinaryRecord(

            bottle_hash=bottle_hash,

            brand_id=brand_id,

            material_id=material_id,

            use_to_id=use_to_id,

            size_id=size_id,

            cashback=cashback,
        )

    # -------------------------------------------------------------------------

    def build_records(self, products) -> List[BinaryRecord]:
        """
        Build seluruh ProductRecord.
        """

        records: List[BinaryRecord] = []

        for product in products:

            record = self.build_record(product)

            records.append(record)

        return records

    # -------------------------------------------------------------------------

    def validate_dictionary_size(self) -> None:
        """
        Memastikan seluruh ID masih muat
        di uint16.
        """

        MAX_UINT16 = 65535

        tables = {

            "Brand": self.dictionary.brand,

            "Material": self.dictionary.material,

            "UseTo": self.dictionary.use_to,

            "Size": self.dictionary.size,
        }

        for name, table in tables.items():

            if len(table) > MAX_UINT16:

                raise ValueError(

                    f"{name} Dictionary melebihi uint16 "
                    f"({len(table)})"
                )

    # -------------------------------------------------------------------------

    def export_dictionary(self) -> DictionaryData:

        return self.dictionary.export()

# =============================================================================
# Record Sorter
# =============================================================================

class RecordSorter:
    """
    Mengurutkan BinaryRecord berdasarkan bottle_hash.

    Database wajib diurutkan agar ESP32 dapat melakukan
    Binary Search dengan sangat cepat.
    """

    @staticmethod
    def sort(records: List[BinaryRecord]) -> List[BinaryRecord]:

        records.sort(key=lambda record: record.bottle_hash)

        return records

    # -------------------------------------------------------------------------

    @staticmethod
    def validate(records: List[BinaryRecord]) -> None:
        """
        Setelah sorting selesai,
        pastikan tidak ada bottle_hash yang sama.
        """

        if not records:
            return

        previous = records[0].bottle_hash

        for current in records[1:]:

            if current.bottle_hash == previous:

                raise ValueError(

                    "Duplicate bottle_hash ditemukan.\n"
                    "Kemungkinan terjadi hash collision "
                    "atau duplicate bottle_no."
                )

            previous = current.bottle_hash

    # -------------------------------------------------------------------------

    @staticmethod
    def is_sorted(records: List[BinaryRecord]) -> bool:
        """
        Memastikan record benar-benar
        sudah terurut.
        """

        if len(records) < 2:
            return True

        previous = records[0].bottle_hash

        for current in records[1:]:

            if current.bottle_hash < previous:

                return False

            previous = current.bottle_hash

        return True

    # -------------------------------------------------------------------------

    @classmethod
    def build(cls, records: List[BinaryRecord]) -> List[BinaryRecord]:
        """
        Sorting lengkap.
        """

        cls.sort(records)

        cls.validate(records)

        if not cls.is_sorted(records):

            raise RuntimeError(
                "Sorting gagal."
            )

        return records

# =============================================================================
# Binary Writer
# =============================================================================

class BinaryWriter:
    """
    Menulis seluruh file binary.

    Output

        database.bin
        brand.bin
        material.bin
        use_to.bin
        size.bin
    """

    STRING_ENCODING = "utf-8"

    # -------------------------------------------------------------------------

    @staticmethod
    def write_database(
        path: Path,
        records: List[BinaryRecord],
    ) -> int:
        """
        Menulis database.bin

        Format

        Record
        Record
        Record
        ...

        Return
        ------
        CRC32
        """

        crc = 0

        with path.open("wb") as fp:

            for record in records:

                raw = record.pack()

                fp.write(raw)

                crc = zlib.crc32(raw, crc)

        return crc & 0xFFFFFFFF

    # -------------------------------------------------------------------------

    @classmethod
    def write_all(
        cls,
        output_dir: Path,
        records: List[BinaryRecord],
        dictionary: DictionaryData,
    ) -> int:

        output_dir.mkdir(

            parents=True,

            exist_ok=True,
        )

        crc = cls.write_database(

            output_dir / config.DATABASE_BIN.name,

            records,
        )

        GenericBinaryWriter.write_dictionary(

            output_dir,

            dictionary,
        )

        MetadataWriter.write(

            output_dir / config.METADATA_BIN.name,

            len(records),

            crc,

            dictionary,
        )

        return crc

# =============================================================================
# Metadata Writer
# =============================================================================

class MetadataWriter:
    """
    Menulis metadata.bin

    File ini dibaca pertama kali oleh ESP32
    sebelum membuka database.bin.
    """

    MAGIC = b"QRDB"

    VERSION = 1

    STRUCT = struct.Struct(
        "<4sHIIIHHHH"
    )

    # -------------------------------------------------------------------------

    @classmethod
    def write(
        cls,
        path: Path,
        record_count: int,
        crc32: int,
        dictionary: DictionaryData,
    ) -> None:

        raw = cls.STRUCT.pack(

            cls.MAGIC,

            cls.VERSION,

            record_count,

            RECORD_SIZE,

            crc32,

            len(dictionary.brand_list),

            len(dictionary.material_list),

            len(dictionary.use_to_list),

            len(dictionary.size_list),
        )

        with path.open("wb") as fp:

            fp.write(raw)

# =============================================================================
# Generic Binary Writer
# =============================================================================

class GenericBinaryWriter:
    """
    Generic writer untuk seluruh file binary.

    Semua file dictionary menggunakan format yang sama.

    Tidak hanya brand.bin,
    tetapi juga:

        material.bin
        use_to.bin
        size.bin

    bahkan dictionary baru di masa depan.
    """

    STRING_ENCODING = "utf-8"

    LENGTH_STRUCT = struct.Struct("<H")

    # -------------------------------------------------------------------------

    @classmethod
    def write_table(
        cls,
        path: Path,
        values: List[str],
    ) -> None:
        """
        Format

        uint16 count

        [
            uint16 length
            bytes
        ]
        """

        with path.open("wb") as fp:

            fp.write(

                cls.LENGTH_STRUCT.pack(
                    len(values)
                )
            )

            for text in values:

                raw = text.encode(
                    cls.STRING_ENCODING
                )

                fp.write(

                    cls.LENGTH_STRUCT.pack(
                        len(raw)
                    )
                )

                fp.write(raw)

    # -------------------------------------------------------------------------

    @classmethod
    def write_dictionary(
        cls,
        output_dir: Path,
        dictionary: DictionaryData,
    ) -> None:

        tables = (

            (
                config.BRAND_BIN,
                dictionary.brand_list,
            ),

            (
                config.MATERIAL_BIN,
                dictionary.material_list,
            ),

            (
                config.USE_TO_BIN,
                dictionary.use_to_list,
            ),

            (
                config.SIZE_BIN,
                dictionary.size_list,
            ),
        )

        for filename, values in tables:

            cls.write_table(

                output_dir / filename.name,

                values,
            )

# =============================================================================
# Build Database
# =============================================================================

class BuildDatabase:
    """
    Orchestrator utama builder.

    Seluruh proses build dilakukan dari sini.
    """

    def __init__(self):

        self.record_builder = RecordBuilder()

    # -------------------------------------------------------------------------

    def build(
        self,
        products,
        output_dir: Path,
    ) -> BuildResult:
        """
        Build seluruh database.
        """

        print()

        print("========== BUILD DATABASE ==========")

        print()

        print("Building records...")

        records = self.record_builder.build_records(
            products
        )

        print(f"Records : {len(records)}")

        print("Checking hash collision...")

        check_hash_collision(products)

        print("Checking dictionary...")

        self.record_builder.validate_dictionary_size()

        dictionary = self.record_builder.export_dictionary()

        print("Sorting database...")

        RecordSorter.build(records)

        print("Writing binary...")

        crc = BinaryWriter.write_all(

            output_dir,

            records,

            dictionary,
        )

        print()

        print("Database build completed.")

        print()

        return BuildResult(

            record_count=len(records),

            crc32=crc,

            output_dir=output_dir,
        )

    # -------------------------------------------------------------------------

    def build_to(
        self,
        products,
        output_dir: Path,
    ) -> BuildResult:
        """
        Alias build().
        """

        return self.build(
            products,
            output_dir,
        )

