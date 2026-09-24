"""
===============================================================================
QR DATABASE CONVERTER
database.py

Professional CSV Loader

Author  : OpenAI + Kurnia Project
Version : 1.0.0

Description
-----------
Module untuk membaca database CSV dan mengubahnya menjadi object Python
yang siap diproses oleh Builder.

Tahap pada file ini:

✓ Membaca CSV
✓ Validasi struktur
✓ Auto Detect Encoding
✓ Membersihkan Data
✓ Membuat ProductRecord
✓ Statistik Database
✓ Progress Callback

Belum pada Part 1:
------------------
- Duplicate Validation
- Dictionary Builder
- Hashing
- Binary Builder

===============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from typing import List
from typing import Optional

import pandas as pd

from config import (
    COL_BOTTLE,
    COL_BRAND,
    COL_MATERIAL,
    COL_USE_TO,
    COL_SIZE,
    COL_CASHBACK,
    CSV_COLUMNS,
)

# =============================================================================
# DATA CLASS
# =============================================================================

@dataclass(slots=True)
class ProductRecord:
    """
    Satu record produk hasil pembacaan CSV.
    """

    bottle_no: str

    bottle_code: str

    material_type: str

    use_to: str

    size_type: str

    cashback: int


# =============================================================================
# CSV DATABASE
# =============================================================================

class CSVDatabase:
    """
    Loader database CSV.

    Class ini hanya bertugas membaca CSV.

    Tidak melakukan:
        - Duplicate Validation
        - Hashing
        - Dictionary
        - Binary Writing

    Semua proses tersebut akan dilakukan oleh module lain.
    """

    # -------------------------------------------------------------------------

    def __init__(self, csv_path: Path):

        self.csv_path = Path(csv_path)

        self.records: List[ProductRecord] = []

        self.total_record: int = 0

        self.encoding: str = ""

        self.progress_callback: Optional[Callable[[int, int], None]] = None

    # -------------------------------------------------------------------------

    def set_progress_callback(

        self,

        callback: Callable[[int, int], None]

    ) -> None:
        """
        Progress callback.

        callback(current,total)
        """

        self.progress_callback = callback

    # -------------------------------------------------------------------------

    def load(self) -> None:
        """
        Load CSV.

        Langkah:

        1. Detect Encoding
        2. Read CSV
        3. Validate Column
        4. Convert Record
        """

        print()

        print("=" * 70)

        print("READ CSV")

        print("=" * 70)

        print()

        self.encoding = self.__detect_encoding()

        print(f"Encoding : {self.encoding}")

        print()

        dataframe = pd.read_csv(

            self.csv_path,

            encoding=self.encoding,

            sep=";",

            keep_default_na=False

        )

        print(dataframe.columns.tolist())

        self.__validate_columns(dataframe)

        self.__convert_dataframe(dataframe)

        self.total_record = len(self.records)

        print()

        print("CSV Loaded Successfully")

        print(f"Total Record : {self.total_record:,}")

        print()

    # -------------------------------------------------------------------------

    def get_records(self) -> List[ProductRecord]:

        return self.records

    # -------------------------------------------------------------------------

    def get_total_record(self) -> int:

        return self.total_record

    # -------------------------------------------------------------------------

    def clear(self) -> None:

        self.records.clear()

        self.total_record = 0

    # -------------------------------------------------------------------------

    def __detect_encoding(self) -> str:
        """
        Auto Detect Encoding.

        Prioritas:

        UTF-8
        UTF-8-SIG
        CP1252
        LATIN1
        """

        candidate = [

            "utf-8-sig",

            "utf-8",

            "cp1252",

            "latin1"

        ]

        for enc in candidate:

            try:

                pd.read_csv(

                    self.csv_path,

                    encoding=enc,

                    sep=";",

                    nrows=5

                )

                return enc

            except Exception:

                pass

        raise RuntimeError(

            "Unable to detect CSV encoding."

        )

    # -------------------------------------------------------------------------

    def __validate_columns(

        self,

        dataframe: pd.DataFrame

    ) -> None:
        """
        Pastikan semua kolom wajib tersedia.
        """

        required = [

            COL_BOTTLE,

            COL_BRAND,

            COL_MATERIAL,

            COL_SIZE,

            COL_CASHBACK

        ]

        missing = []

        for column in CSV_COLUMNS:

            if column not in dataframe.columns:

                missing.append(column)

        if missing:

            print()

            print("ERROR")

            print("-" * 40)

            for item in missing:

                print(item)

            print("-" * 40)

            raise RuntimeError("Required column missing.")

    # -------------------------------------------------------------------------

    def __convert_dataframe(
        self,
        dataframe: pd.DataFrame
    ) -> None:
        """
        Convert seluruh DataFrame menjadi ProductRecord.

        Tahapan:

        1. Bersihkan string
        2. Konversi cashback
        3. Simpan ke records
        4. Progress callback
        """

        total = len(dataframe)

        self.records.clear()

        for index, row in enumerate(dataframe.itertuples(index=False), start=1):

            record = self.__create_record(row)

            self.records.append(record)

            if self.progress_callback is not None:

                self.progress_callback(index, total)

        if self.progress_callback is not None:

            self.progress_callback(total, total)

    # -------------------------------------------------------------------------

    def __create_record(
        self,
        row
    ) -> ProductRecord:
        """
        Membuat ProductRecord dari satu baris CSV.
        """

        bottle = self.__clean_string(

            getattr(row, COL_BOTTLE)

        )

        brand = self.__clean_string(

            getattr(row, COL_BRAND)

        )

        material = self.__clean_string(

            getattr(row, COL_MATERIAL)

        )

        use_to = self.__clean_string(

            getattr(row, COL_USE_TO)

        )

        size = self.__clean_string(

            getattr(row, COL_SIZE)

        )

        cashback = self.__convert_cashback(

            getattr(row, COL_CASHBACK)

        )

        return ProductRecord(

            bottle_no=bottle,

            bottle_code=brand,

            material_type=material,

            use_to=use_to,

            size_type=size,

            cashback=cashback

        )

    # -------------------------------------------------------------------------

    @staticmethod
    def __clean_string(value) -> str:
        """
        Membersihkan data string.
        """

        if value is None:

            return ""

        text = str(value)

        text = text.strip()

        text = text.replace("\t", " ")

        while "  " in text:

            text = text.replace("  ", " ")

        return text

    # -------------------------------------------------------------------------

    @staticmethod
    def __convert_cashback(value) -> int:
        """
        Mengubah cashback menjadi integer.
        """

        if value is None:

            return 0

        if isinstance(value, int):

            return value

        if isinstance(value, float):

            return int(value)

        text = str(value)

        text = text.replace(",", "")

        text = text.strip()

        if text == "":

            return 0

        try:

            return int(float(text))

        except Exception:

            raise RuntimeError(

                f"Invalid cashback value : {value}"

            )

    # -------------------------------------------------------------------------

    def get_brand_set(self) -> set[str]:
        """
        Mengambil seluruh Brand unik.
        """

        return {

            item.bottle_code

            for item in self.records

        }

    # -------------------------------------------------------------------------

    def get_material_set(self) -> set[str]:
        """
        Mengambil seluruh Material unik.
        """

        return {

            item.material_type

            for item in self.records

        }


    # -------------------------------------------------------------------------


    def get_use_to_set(self) -> set[str]:

        """
        Mengambil seluruh Use To unik.
        """
    
        return {

            item.use_to

            for item in self.records
            
        }

    # -------------------------------------------------------------------------

    def get_size_set(self) -> set[str]:
        """
        Mengambil seluruh Size unik.
        """

        return {

            item.size_type

            for item in self.records

        }

    # -------------------------------------------------------------------------

    def print_summary(self) -> None:
        """
        Ringkasan database.
        """

        print()

        print("=" * 60)

        print("DATABASE SUMMARY")

        print("=" * 60)

        print(f"Total Record : {len(self.records):,}")

        print(f"Brand        : {len(self.get_brand_set())}")

        print(f"Material     : {len(self.get_material_set())}")

        print(f"Size         : {len(self.get_size_set())}")

        print("=" * 60)

        print()

    # -------------------------------------------------------------------------

    def validate_basic(self) -> None:
        """
        Validasi dasar database.

        Hanya melakukan validasi yang bersifat umum.
        Duplicate akan diperiksa oleh validator.py
        """

        print()

        print("=" * 70)
        print("BASIC VALIDATION")
        print("=" * 70)

        invalid = 0

        for index, record in enumerate(self.records, start=1):

            try:

                self.__validate_record(record)

            except Exception as err:

                invalid += 1

                print(

                    f"[Row {index}] {err}"

                )

        print()

        print(f"Invalid Record : {invalid}")

        print()

    # -------------------------------------------------------------------------

    def __validate_record(
        self,
        record: ProductRecord
    ) -> None:
        """
        Validasi satu record.
        """

        if record.bottle_no == "":

            raise RuntimeError(

                "Bottle Number kosong"

            )

        if record.bottle_code == "":

            raise RuntimeError(

                "Bottle Code kosong"

            )

        if record.material_type == "":

            raise RuntimeError(

                "Material kosong"
            )

        if record.use_to == "":

            raise RuntimeError(

                "Use To kosong"

            )

        if record.size_type == "":

            raise RuntimeError(

                "Size kosong"

            )

        if record.cashback < 0:

            raise RuntimeError(

                "Cashback tidak boleh negatif"

            )

    # -------------------------------------------------------------------------

    def sort_by_bottle(self) -> None:
        """
        Sort berdasarkan bottle_no.

        Digunakan sebelum hashing.
        """

        print()

        print("Sorting bottle number...")

        self.records.sort(

            key=lambda item: item.bottle_no

        )

        print("Done")

    # -------------------------------------------------------------------------

    def statistics(self) -> dict:
        """
        Menghasilkan statistik database.
        """

        return {

            "total_record": len(self.records),

            "brand": len(self.get_brand_set()),

            "material": len(self.get_material_set()),

            "use_to": len(

                {

                    r.use_to

                    for r in self.records

                }

            ),

            "size": len(self.get_size_set())

        }

    # -------------------------------------------------------------------------

    def print_statistics(self) -> None:
        """
        Menampilkan statistik database.
        """

        stat = self.statistics()

        print()

        print("=" * 70)

        print("DATABASE STATISTICS")

        print("=" * 70)

        print(

            f"Total Record : "

            f"{stat['total_record']:,}"

        )

        print(

            f"Brand        : "

            f"{stat['brand']}"

        )

        print(

            f"Material     : "

            f"{stat['material']}"

        )

        print(

            f"Use To       : "

            f"{stat['use_to']}"

        )

        print(

            f"Size         : "

            f"{stat['size']}"

        )

        print("=" * 70)

        print()

    # -------------------------------------------------------------------------

    def __len__(self) -> int:

        return len(

            self.records

        )

    # -------------------------------------------------------------------------

    def __iter__(self):

        return iter(

            self.records

        )

    # -------------------------------------------------------------------------

    def __getitem__(

        self,

        index

    ):

        return self.records[index]

    # -------------------------------------------------------------------------

    def __repr__(self):

        return (

            f"<CSVDatabase "

            f"records={len(self.records):,}>"

        )