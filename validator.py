"""
===============================================================================
QR DATABASE CONVERTER
validator.py

Duplicate & Integrity Validator

Author  : Kurnia Project
Version : 2.0.0

Description
-----------
Module untuk memvalidasi integritas ProductRecord yang sudah dimuat oleh
CSVDatabase (database.py), sebelum data diteruskan ke builder.py.

Semua pengecekan dilakukan dalam SATU KALI iterasi (single pass, O(n)).

Fitur
-----
Core:
    Single Pass
    O(n)
    Set Duplicate
    Statistics

Validation:
    Duplicate Bottle
    Empty Bottle
    Empty Brand
    Empty Material
    Empty UseTo
    Empty Size
    Cashback
    Bottle Length     (harus tepat 7 karakter)
    Illegal Character (bottle_no hanya boleh A-Z dan 0-9)

Validator TIDAK melakukan:
------------------------
- Dictionary Builder
- Hashing
- Binary Writing

Semua proses tersebut akan dilakukan oleh builder.py & writer.py
===============================================================================
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from dataclasses import field
from typing import Dict
from typing import List
from typing import Set

from database import CSVDatabase


# =============================================================================
# CONSTANTS
# =============================================================================

BOTTLE_LENGTH: int = 7

BOTTLE_PATTERN = re.compile(r"^[A-Z0-9]+$")


# =============================================================================
# EXCEPTION
# =============================================================================

class ValidationError(RuntimeError):
    """
    Exception yang dilempar ketika validasi database gagal.
    """
    pass


# =============================================================================
# DATA CLASS
# =============================================================================

@dataclass(slots=True)
class DuplicateGroup:
    """
    Menyimpan satu kelompok bottle_no yang duplikat.
    """

    bottle_no: str

    rows: List[int]


@dataclass(slots=True)
class ValidationResult:
    """
    Menyimpan hasil validasi database secara keseluruhan.
    """

    total_record: int = 0

    total_duplicate: int = 0

    duplicate_groups: List[DuplicateGroup] = field(default_factory=list)

    invalid_rows: List[str] = field(default_factory=list)

    # -- Statistics ---------------------------------------------------------

    brand_set: Set[str] = field(default_factory=set)

    material_set: Set[str] = field(default_factory=set)

    use_to_set: Set[str] = field(default_factory=set)

    size_set: Set[str] = field(default_factory=set)

    @property
    def is_valid(self) -> bool:
        """
        True jika tidak ada duplikat dan tidak ada record invalid.
        """

        return (

            self.total_duplicate == 0

            and len(self.invalid_rows) == 0

        )

    @property
    def statistics(self) -> dict:
        """
        Ringkasan statistik hasil validasi (dihitung selama single pass).
        """

        return {

            "total_record": self.total_record,

            "brand": len(self.brand_set),

            "material": len(self.material_set),

            "use_to": len(self.use_to_set),

            "size": len(self.size_set),

        }


# =============================================================================
# VALIDATOR
# =============================================================================

class Validator:
    """
    Validator untuk CSVDatabase.

    Dipanggil oleh builder.py setelah CSVDatabase.load() berhasil,
    sebelum proses hashing / dictionary building dimulai.

    Semua validasi dan pengumpulan statistik dilakukan dalam satu kali
    iterasi (single pass) terhadap seluruh record.
    """

    # -------------------------------------------------------------------------

    def __init__(self, database: CSVDatabase):

        self.database = database

        self.result = ValidationResult()

    # -------------------------------------------------------------------------

    def run(self, raise_on_error: bool = True) -> ValidationResult:
        """
        Menjalankan validasi single-pass.

        Langkah:

        1. Iterasi seluruh record satu kali:
           - Cek duplicate bottle_no (via dict tracking / set semantics)
           - Cek empty field (bottle, brand, material, use_to, size)
           - Cek cashback
           - Cek bottle length
           - Cek illegal character
           - Kumpulkan statistics
        2. Cetak laporan
        3. Raise ValidationError jika gagal (opsional)
        """

        print()

        print("=" * 70)

        print("VALIDATE DATABASE")

        print("=" * 70)

        print()

        self.result = ValidationResult(

            total_record=len(self.database)

        )

        self.__validate_single_pass()

        self.__print_report()

        if raise_on_error and not self.result.is_valid:

            raise ValidationError(

                "Validasi gagal. Database mengandung duplikat "

                "dan/atau record invalid. Lihat laporan di atas."

            )

        return self.result

    # -------------------------------------------------------------------------

    def __validate_single_pass(self) -> None:
        """
        Melakukan seluruh pengecekan dalam satu kali iterasi (O(n)).
        """

        print("Validating database (single pass)...")

        seen_bottle: Dict[str, List[int]] = {}

        invalid: List[str] = []

        for row_index, record in enumerate(self.database, start=1):

            errors: List[str] = []

            # -- Set Duplicate ---------------------------------------------

            bottle_no = record.bottle_no

            if bottle_no in seen_bottle:

                seen_bottle[bottle_no].append(row_index)

            else:

                seen_bottle[bottle_no] = [row_index]

            # -- Empty Field --------------------------------------------------

            if record.bottle_no == "":

                errors.append("bottle_no kosong")

            if record.bottle_code == "":

                errors.append("bottle_code kosong")

            if record.material_type == "":

                errors.append("material_type kosong")

            if record.use_to == "":

                errors.append("use_to kosong")

            if record.size_type == "":

                errors.append("size_type kosong")

            # -- Cashback -----------------------------------------------------

            if record.cashback < 0:

                errors.append("cashback negatif")

            # -- Bottle Length & Illegal Character ----------------------------

            if record.bottle_no != "":

                if len(record.bottle_no) != BOTTLE_LENGTH:

                    errors.append(

                        f"bottle_no harus {BOTTLE_LENGTH} karakter "

                        f"(didapat {len(record.bottle_no)})"

                    )

                if not BOTTLE_PATTERN.fullmatch(record.bottle_no):

                    errors.append(

                        "bottle_no mengandung karakter ilegal "

                        "(hanya A-Z dan 0-9 yang diizinkan)"

                    )

            if errors:

                label = bottle_no if bottle_no else "(?)"

                invalid.append(

                    f"[Row {row_index}] {label} -> "

                    f"{', '.join(errors)}"

                )

            # -- Statistics -----------------------------------------------------

            self.result.brand_set.add(record.bottle_code)

            self.result.material_set.add(record.material_type)

            self.result.use_to_set.add(record.use_to)

            self.result.size_set.add(record.size_type)

        groups = [

            DuplicateGroup(bottle_no=key, rows=rows)

            for key, rows in seen_bottle.items()

            if len(rows) > 1

        ]

        groups.sort(

            key=lambda item: item.bottle_no

        )

        self.result.duplicate_groups = groups

        self.result.total_duplicate = sum(

            len(item.rows)

            for item in groups

        )

        self.result.invalid_rows = invalid

        print(f"Duplicate group found : {len(groups)}")

        print(f"Invalid record found  : {len(invalid)}")

        print()

    # -------------------------------------------------------------------------

    def __print_report(self) -> None:
        """
        Mencetak laporan hasil validasi, termasuk statistik.
        """

        stat = self.result.statistics

        print("=" * 70)

        print("VALIDATION REPORT")

        print("=" * 70)

        print(f"Total Record     : {stat['total_record']:,}")

        print(f"Duplicate Group  : {len(self.result.duplicate_groups)}")

        print(f"Duplicate Record : {self.result.total_duplicate}")

        print(f"Invalid Record   : {len(self.result.invalid_rows)}")

        print("-" * 70)

        print("STATISTICS")

        print("-" * 40)

        print(f"Brand    : {stat['brand']}")

        print(f"Material : {stat['material']}")

        print(f"Use To   : {stat['use_to']}")

        print(f"Size     : {stat['size']}")

        print("-" * 70)

        if self.result.duplicate_groups:

            print()

            print("DUPLICATE BOTTLE_NO")

            print("-" * 40)

            for group in self.result.duplicate_groups:

                rows_str = ", ".join(

                    str(row) for row in group.rows

                )

                print(

                    f"  {group.bottle_no}  -> rows: {rows_str}"

                )

            print("-" * 40)

        if self.result.invalid_rows:

            print()

            print("INVALID RECORD")

            print("-" * 40)

            for line in self.result.invalid_rows:

                print(f"  {line}")

            print("-" * 40)

        print()

        status = "PASSED" if self.result.is_valid else "FAILED"

        print(f"VALIDATION STATUS : {status}")

        print("=" * 70)

        print()

    # -------------------------------------------------------------------------

    def __repr__(self) -> str:

        return (

            f"<Validator "

            f"total_record={self.result.total_record:,} "

            f"is_valid={self.result.is_valid}>"

        )
