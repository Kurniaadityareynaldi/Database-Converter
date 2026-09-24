"""
===============================================================================
QR DATABASE CONVERTER
verify_bin.py

Binary Verification Test (Production Tool)

Author  : Kurnia Project
Version : 2.0.0

Description
-----------
Tool verifikasi lengkap untuk memastikan database.bin (+ dictionary .bin)
100% identik dengan data sumber di CSV, sebelum file dikirim ke ESP32.

Alur inti (per record)
-----------------------

Database_Alner.csv
        |
        +-- Record ke-N
        |      bottle_no, bottle_code, material_type,
        |      use_to, size_type, cashback
        |
        v
    bottle_hash = FNV1A64(bottle_no)
        |
        v
    Binary Search di database.bin   <- persis seperti ESP32
        |
        v
    Decode brand_id / material_id / use_to_id / size_id -> Nama
        |
        v
    Bandingkan field per field terhadap CSV
        |
        v
    PASS / FAIL

Fitur
-----
1. Verify record tertentu / rentang / gabungan     (--row)
2. Verify N record acak                            (--sample)
3. Verify SELURUH database + progress bar & ETA    (--all)
4. CRC32 Integrity Check                           (--crc-check)
5. Dictionary Integrity Check (semua ID valid)      (--dict-check)
6. Sorted Check (database.bin terurut by hash)      (--sorted-check)
7. Binary Search Stress Test (simulasi ESP32)       (--stress N)
8. Full Report (semua test sekaligus)               (--full)
9. Menu interaktif + ekspor log                     (jalankan tanpa argumen)

Usage
-----
    python verify_bin.py                       # menu interaktif
    python verify_bin.py --full                # semua test, sekali jalan
    python verify_bin.py --row 1                # record ke-1 saja
    python verify_bin.py --row 1,50-60,105298    # kombinasi
    python verify_bin.py --sample 500 --seed 7
    python verify_bin.py --all
    python verify_bin.py --crc-check
    python verify_bin.py --dict-check
    python verify_bin.py --sorted-check
    python verify_bin.py --stress 5000
    python verify_bin.py --full --log            # simpan seluruh output ke logs/
===============================================================================
"""

from __future__ import annotations

import argparse
import bisect
import random
import struct
import sys
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config
from builder import (
    MetadataWriter,
    RECORD_SIZE,
    RECORD_STRUCT,
    make_bottle_hash,
)
from database import CSVDatabase, ProductRecord


# =============================================================================
# LOGGER (tee print() ke console + file log, opsional)
# =============================================================================

class TeeLogger:
    """
    Duplikasi seluruh output print() ke console dan (opsional) ke file log.
    """

    def __init__(self, enabled: bool):

        self.enabled = enabled

        self.terminal = sys.stdout

        self.buffer: List[str] = []

        self.log_path: Optional[Path] = None

        self.log_handle = None

        if self.enabled:

            config.LOG_FOLDER.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            self.log_path = config.LOG_FOLDER / f"verify_{timestamp}.log"

            self.log_handle = open(self.log_path, "a", encoding="utf-8")

    def write(self, message: str) -> None:

        self.terminal.write(message)

        if self.log_handle is not None:

            self.log_handle.write(message)

    def flush(self) -> None:

        self.terminal.flush()

        if self.log_handle is not None:

            self.log_handle.flush()

    def close(self) -> None:

        if self.log_handle is not None:

            self.log_handle.close()


# =============================================================================
# PROGRESS BAR
# =============================================================================

class ProgressBar:
    """
    Progress bar sederhana dengan estimasi waktu (ETA).
    """

    def __init__(self, total: int, prefix: str = "Progress", width: int = 36):

        self.total = max(total, 1)

        self.prefix = prefix

        self.width = width

        self.start_time = time.time()

        self.last_render = 0.0

    def update(self, current: int) -> None:

        now = time.time()

        # Batasi refresh maksimal ~20x/detik supaya tidak membebani I/O.

        if current != self.total and (now - self.last_render) < 0.05:

            return

        self.last_render = now

        fraction = current / self.total

        filled = int(self.width * fraction)

        bar = "#" * filled + "-" * (self.width - filled)

        elapsed = now - self.start_time

        rate = current / elapsed if elapsed > 0 else 0

        remaining = (self.total - current) / rate if rate > 0 else 0

        sys.stdout.write(

            f"\r  {self.prefix} [{bar}] "
            f"{current:,}/{self.total:,} ({fraction*100:5.1f}%) "
            f"| {rate:,.0f} rec/s | ETA {remaining:5.1f}s   "
        )

        sys.stdout.flush()

        if current >= self.total:

            sys.stdout.write("\n")

    def finish(self) -> float:

        self.update(self.total)

        return time.time() - self.start_time


# =============================================================================
# BINARY DATABASE READER
# =============================================================================

@dataclass(slots=True)
class DecodedRecord:

    bottle_hash: int

    brand_id: int

    material_id: int

    use_to_id: int

    size_id: int

    cashback: int


class BinaryDatabase:
    """
    Membaca database.bin, metadata.bin, dan seluruh tabel dictionary
    langsung dari disk. Independen dari builder.py -- murni membaca hasil
    akhir, supaya verifikasi benar-benar menguji output final.
    """

    def __init__(self, output_dir: Path):

        self.output_dir = Path(output_dir)

        self.records: List[DecodedRecord] = []

        self.hashes: List[int] = []

        self.brand_list: List[str] = []

        self.material_list: List[str] = []

        self.use_to_list: List[str] = []

        self.size_list: List[str] = []

        self.metadata: Dict[str, int] = {}

    # -------------------------------------------------------------------------

    def load(self) -> None:

        self.metadata = self.__read_metadata(

            self.output_dir / config.METADATA_BIN.name
        )

        self.records = self.__read_database(

            self.output_dir / config.DATABASE_BIN.name
        )

        self.hashes = [record.bottle_hash for record in self.records]

        self.brand_list = self.__read_table(self.output_dir / config.BRAND_BIN.name)

        self.material_list = self.__read_table(self.output_dir / config.MATERIAL_BIN.name)

        self.use_to_list = self.__read_table(self.output_dir / config.USE_TO_BIN.name)

        self.size_list = self.__read_table(self.output_dir / config.SIZE_BIN.name)

    # -------------------------------------------------------------------------

    @staticmethod
    def __read_metadata(path: Path) -> Dict[str, int]:

        raw = path.read_bytes()

        (
            magic, version, record_count, record_size, crc32,
            n_brand, n_material, n_use_to, n_size,

        ) = MetadataWriter.STRUCT.unpack(raw)

        return {

            "magic": magic,
            "version": version,
            "record_count": record_count,
            "record_size": record_size,
            "crc32": crc32,
            "n_brand": n_brand,
            "n_material": n_material,
            "n_use_to": n_use_to,
            "n_size": n_size,
        }

    # -------------------------------------------------------------------------

    @staticmethod
    def __read_database(path: Path) -> List[DecodedRecord]:

        data = path.read_bytes()

        count = len(data) // RECORD_SIZE

        records: List[DecodedRecord] = []

        for i in range(count):

            chunk = data[i * RECORD_SIZE: (i + 1) * RECORD_SIZE]

            (

                bottle_hash, brand_id, material_id,
                use_to_id, size_id, cashback,

            ) = RECORD_STRUCT.unpack(chunk)

            records.append(

                DecodedRecord(

                    bottle_hash=bottle_hash,
                    brand_id=brand_id,
                    material_id=material_id,
                    use_to_id=use_to_id,
                    size_id=size_id,
                    cashback=cashback,
                )
            )

        return records

    # -------------------------------------------------------------------------

    @staticmethod
    def __read_table(path: Path) -> List[str]:
        """
        Format tabel (lihat GenericBinaryWriter.write_table) :

            uint16 count
            [ uint16 length, bytes (utf-8) ] * count
        """

        data = path.read_bytes()

        offset = 0

        (count,) = struct.unpack_from("<H", data, offset)

        offset += 2

        values: List[str] = []

        for _ in range(count):

            (length,) = struct.unpack_from("<H", data, offset)

            offset += 2

            text = data[offset: offset + length].decode("utf-8")

            offset += length

            values.append(text)

        return values

    # -------------------------------------------------------------------------

    def find(self, bottle_hash: int) -> Optional[DecodedRecord]:
        """
        Binary search berdasarkan bottle_hash -- simulasi cara ESP32 mencari data.
        """

        idx = bisect.bisect_left(self.hashes, bottle_hash)

        if idx < len(self.hashes) and self.hashes[idx] == bottle_hash:

            return self.records[idx]

        return None

    # -------------------------------------------------------------------------

    def find_manual(self, bottle_hash: int) -> Tuple[bool, int]:
        """
        Binary search manual (loop eksplisit), dipakai oleh Stress Test agar
        jumlah perbandingan (comparisons) bisa dihitung, meniru algoritma
        yang akan dipakai di firmware C/C++ ESP32.
        """

        low, high = 0, len(self.hashes) - 1

        comparisons = 0

        while low <= high:

            comparisons += 1

            mid = (low + high) // 2

            value = self.hashes[mid]

            if value == bottle_hash:

                return True, comparisons

            if value < bottle_hash:

                low = mid + 1

            else:

                high = mid - 1

        return False, comparisons

    # -------------------------------------------------------------------------

    def file_crc32(self) -> int:

        data = (self.output_dir / config.DATABASE_BIN.name).read_bytes()

        return zlib.crc32(data) & 0xFFFFFFFF

    # -------------------------------------------------------------------------

    def is_sorted(self) -> bool:

        return all(

            self.hashes[i] <= self.hashes[i + 1]

            for i in range(len(self.hashes) - 1)
        )

    # -------------------------------------------------------------------------

    def duplicate_hashes(self) -> List[int]:
        """
        Mencari bottle_hash yang muncul lebih dari sekali (indikasi hash
        collision atau data terduplikasi yang lolos validasi).
        """

        duplicates = []

        for i in range(1, len(self.hashes)):

            if self.hashes[i] == self.hashes[i - 1]:

                duplicates.append(self.hashes[i])

        return duplicates

    # -------------------------------------------------------------------------

    def __len__(self) -> int:

        return len(self.records)


# =============================================================================
# CHECK RESULT
# =============================================================================

@dataclass(slots=True)
class CheckResult:

    name: str

    passed: bool

    detail: str = ""


# =============================================================================
# STRUCTURAL CHECKS (4, 5, 6)
# =============================================================================

class StructuralChecker:
    """
    Berisi test No. 4 (CRC32), No. 5 (Dictionary Integrity),
    dan No. 6 (Sorted Check).
    """

    def __init__(self, bin_db: BinaryDatabase):

        self.bin_db = bin_db

    # -------------------------------------------------------------------------

    def crc_check(self) -> CheckResult:

        print()
        print("=" * 70)
        print("4. CRC32 INTEGRITY CHECK")
        print("=" * 70)

        actual = self.bin_db.file_crc32()

        expected = self.bin_db.metadata["crc32"]

        ok = actual == expected

        print(f"CRC32 dihitung ulang dari database.bin : {actual:#010x}")

        print(f"CRC32 tercatat di metadata.bin         : {expected:#010x}")

        print(f"STATUS : {'OK - identik' if ok else 'FAIL - tidak cocok, file mungkin korup/berubah'}")

        return CheckResult(

            "CRC32 Integrity",

            ok,

            f"actual={actual:#010x} expected={expected:#010x}",
        )

    # -------------------------------------------------------------------------

    def dictionary_check(self) -> CheckResult:

        print()
        print("=" * 70)
        print("5. DICTIONARY INTEGRITY CHECK")
        print("=" * 70)

        n_brand = len(self.bin_db.brand_list)

        n_material = len(self.bin_db.material_list)

        n_use_to = len(self.bin_db.use_to_list)

        n_size = len(self.bin_db.size_list)

        print(f"Jumlah entri brand.bin    : {n_brand}")

        print(f"Jumlah entri material.bin : {n_material}")

        print(f"Jumlah entri use_to.bin   : {n_use_to}")

        print(f"Jumlah entri size.bin     : {n_size}")

        print()

        invalid: List[str] = []

        for idx, record in enumerate(self.bin_db.records):

            if not (0 <= record.brand_id < n_brand):

                invalid.append(

                    f"record#{idx} (hash={record.bottle_hash:#x}) "
                    f"brand_id={record.brand_id} di luar batas [0,{n_brand})"
                )

            if not (0 <= record.material_id < n_material):

                invalid.append(

                    f"record#{idx} (hash={record.bottle_hash:#x}) "
                    f"material_id={record.material_id} di luar batas [0,{n_material})"
                )

            if not (0 <= record.use_to_id < n_use_to):

                invalid.append(

                    f"record#{idx} (hash={record.bottle_hash:#x}) "
                    f"use_to_id={record.use_to_id} di luar batas [0,{n_use_to})"
                )

            if not (0 <= record.size_id < n_size):

                invalid.append(

                    f"record#{idx} (hash={record.bottle_hash:#x}) "
                    f"size_id={record.size_id} di luar batas [0,{n_size})"
                )

        ok = len(invalid) == 0

        if ok:

            print(f"Semua {len(self.bin_db):,} record memiliki ID dictionary yang valid.")

        else:

            print(f"Ditemukan {len(invalid)} ID tidak valid :")

            print("-" * 70)

            for line in invalid[:30]:

                print(f"  {line}")

            if len(invalid) > 30:

                print(f"  ... dan {len(invalid) - 30} lainnya")

        print(f"STATUS : {'OK' if ok else 'FAIL'}")

        return CheckResult(

            "Dictionary Integrity",

            ok,

            f"{len(invalid)} id tidak valid dari {len(self.bin_db):,} record",
        )

    # -------------------------------------------------------------------------

    def sorted_check(self) -> CheckResult:

        print()
        print("=" * 70)
        print("6. DATABASE SORTED CHECK")
        print("=" * 70)

        ok_sorted = self.bin_db.is_sorted()

        print(

            f"database.bin terurut ascending berdasarkan bottle_hash : "
            f"{'YA' if ok_sorted else 'TIDAK'}"
        )

        duplicates = self.bin_db.duplicate_hashes()

        if duplicates:

            print(

                f"[WARNING] Ditemukan {len(duplicates)} bottle_hash duplikat "
                f"(kemungkinan hash collision) :"
            )

            for h in duplicates[:10]:

                print(f"  hash = {h:#018x}")

            if len(duplicates) > 10:

                print(f"  ... dan {len(duplicates) - 10} lainnya")

        else:

            print("Tidak ada bottle_hash duplikat / hash collision.")

        ok = ok_sorted and not duplicates

        print(f"STATUS : {'OK' if ok else 'FAIL'}")

        print(

            "(Catatan: jika TIDAK terurut, binary search di ESP32 "
            "akan menghasilkan pencarian yang salah / gagal.)"
        )

        return CheckResult(

            "Sorted Check",

            ok,

            f"sorted={ok_sorted} duplicates={len(duplicates)}",
        )


# =============================================================================
# RECORD-LEVEL VERIFY RESULT
# =============================================================================

@dataclass(slots=True)
class FieldCheck:

    name: str

    expected: str

    actual: str

    ok: bool


@dataclass(slots=True)
class VerifyResult:

    row: int

    bottle_no: str

    bottle_hash: int

    found: bool

    fields: List[FieldCheck] = field(default_factory=list)

    @property
    def is_pass(self) -> bool:

        return self.found and all(item.ok for item in self.fields)


# =============================================================================
# RECORD VERIFIER (fitur 1, 2, 3)
# =============================================================================

class RecordVerifier:

    def __init__(self, bin_db: BinaryDatabase):

        self.bin_db = bin_db

    # -------------------------------------------------------------------------

    @staticmethod
    def __normalize(value: str) -> str:
        """
        Harus sama persis dengan DictionaryBuilder._normalize di builder.py.
        """

        return value.strip().upper()

    # -------------------------------------------------------------------------

    @staticmethod
    def __safe_get(table: List[str], idx: int, label: str) -> str:

        if 0 <= idx < len(table):

            return table[idx]

        return f"<ID TIDAK VALID:{label}#{idx}>"

    # -------------------------------------------------------------------------

    def verify(self, row: int, product: ProductRecord) -> VerifyResult:

        bottle_hash = make_bottle_hash(product.bottle_no)

        decoded = self.bin_db.find(bottle_hash)

        if decoded is None:

            return VerifyResult(

                row=row, bottle_no=product.bottle_no,
                bottle_hash=bottle_hash, found=False,
            )

        brand_name = self.__safe_get(self.bin_db.brand_list, decoded.brand_id, "BRAND")

        material_name = self.__safe_get(self.bin_db.material_list, decoded.material_id, "MATERIAL")

        use_to_name = self.__safe_get(self.bin_db.use_to_list, decoded.use_to_id, "USE_TO")

        size_name = self.__safe_get(self.bin_db.size_list, decoded.size_id, "SIZE")

        fields = [

            FieldCheck(
                "bottle_code",
                self.__normalize(product.bottle_code),
                brand_name,
                self.__normalize(product.bottle_code) == brand_name,
            ),

            FieldCheck(
                "material_type",
                self.__normalize(product.material_type),
                material_name,
                self.__normalize(product.material_type) == material_name,
            ),

            FieldCheck(
                "use_to",
                self.__normalize(product.use_to),
                use_to_name,
                self.__normalize(product.use_to) == use_to_name,
            ),

            FieldCheck(
                "size_type",
                self.__normalize(product.size_type),
                size_name,
                self.__normalize(product.size_type) == size_name,
            ),

            FieldCheck(
                "cashback",
                str(product.cashback),
                str(decoded.cashback),
                product.cashback == decoded.cashback,
            ),
        ]

        return VerifyResult(

            row=row, bottle_no=product.bottle_no,
            bottle_hash=bottle_hash, found=True, fields=fields,
        )


# =============================================================================
# STRESS TEST (fitur 7)
# =============================================================================

class StressTester:
    """
    Menguji ribuan pencarian binary search acak, seperti yang akan
    dilakukan ESP32 saat scan QR berulang kali.
    """

    def __init__(self, bin_db: BinaryDatabase):

        self.bin_db = bin_db

    def run(self, n: int, records: List[ProductRecord], seed: Optional[int] = None) -> CheckResult:

        print()
        print("=" * 70)
        print("7. BINARY SEARCH STRESS TEST")
        print("=" * 70)

        total_records = len(records)

        rng = random.Random(seed)

        sample_rows = [rng.randrange(total_records) for _ in range(n)]

        # Sisipkan sedikit hash acak yang PASTI tidak ada, untuk menguji
        # jalur "not found" (mensimulasikan QR palsu / rusak).

        n_missing = max(1, n // 100)

        print(f"Jumlah pencarian valid   : {n:,}")

        print(f"Jumlah pencarian invalid : {n_missing:,} (hash acak yang tidak ada)")

        print()

        durations_ns: List[int] = []

        comparisons_list: List[int] = []

        found_count = 0

        progress = ProgressBar(n + n_missing, prefix="Stress Test")

        for i, row in enumerate(sample_rows, start=1):

            product = records[row]

            target_hash = make_bottle_hash(product.bottle_no)

            start = time.perf_counter_ns()

            found, comparisons = self.bin_db.find_manual(target_hash)

            elapsed = time.perf_counter_ns() - start

            durations_ns.append(elapsed)

            comparisons_list.append(comparisons)

            if found:

                found_count += 1

            progress.update(i)

        missing_found = 0

        for i in range(n_missing):

            fake_hash = rng.getrandbits(64)

            start = time.perf_counter_ns()

            found, comparisons = self.bin_db.find_manual(fake_hash)

            elapsed = time.perf_counter_ns() - start

            durations_ns.append(elapsed)

            comparisons_list.append(comparisons)

            if found:

                missing_found += 1

            progress.update(n + i + 1)

        total_time = progress.finish()

        avg_ns = sum(durations_ns) / len(durations_ns)

        max_ns = max(durations_ns)

        min_ns = min(durations_ns)

        avg_cmp = sum(comparisons_list) / len(comparisons_list)

        max_cmp = max(comparisons_list)

        ops_per_sec = len(durations_ns) / total_time if total_time > 0 else 0

        print()

        print(f"Total pencarian         : {len(durations_ns):,}")

        print(f"Waktu total             : {total_time:.3f} detik")

        print(f"Throughput              : {ops_per_sec:,.0f} pencarian/detik (di mesin ini)")

        print(f"Waktu rata-rata/lookup  : {avg_ns/1000:.2f} us  (min {min_ns/1000:.2f} us, max {max_ns/1000:.2f} us)")

        print(f"Rata-rata perbandingan  : {avg_cmp:.2f} kali  (max {max_cmp}, teori log2(N) = {__import__('math').log2(max(len(self.bin_db),1)):.2f})")

        print(f"Valid ditemukan         : {found_count:,} / {n:,}")

        print(f"Invalid ditemukan       : {missing_found:,} / {n_missing:,} (HARUS 0)")

        ok = (found_count == n) and (missing_found == 0)

        print(f"STATUS : {'OK' if ok else 'FAIL'}")

        print(

            "(Catatan: waktu di ESP32 akan berbeda -- CPU jauh lebih lambat -- "
            "tapi jumlah perbandingan/log2(N) mencerminkan kompleksitas yang sama.)"
        )

        return CheckResult(

            "Binary Search Stress Test",

            ok,

            f"found={found_count}/{n} false_positive={missing_found}/{n_missing} "
            f"avg={avg_ns/1000:.2f}us throughput={ops_per_sec:,.0f}/s",
        )


# =============================================================================
# ROW SPEC PARSER
# =============================================================================

def parse_row_spec(spec: str, total: int) -> List[int]:

    rows: set[int] = set()

    for part in spec.split(","):

        part = part.strip()

        if not part:

            continue

        if "-" in part:

            start_str, end_str = part.split("-", 1)

            start, end = int(start_str), int(end_str)

            if start > end:

                start, end = end, start

            rows.update(range(start, end + 1))

        else:

            rows.add(int(part))

    out_of_range = [r for r in rows if r < 1 or r > total]

    if out_of_range:

        print(

            f"[WARNING] {len(out_of_range)} nomor baris di luar rentang "
            f"1-{total} diabaikan : {sorted(out_of_range)[:10]}"
            + (" ..." if len(out_of_range) > 10 else "")
        )

    return sorted(r for r in rows if 1 <= r <= total)


# =============================================================================
# PRINTING (record level)
# =============================================================================

def print_detail(result: VerifyResult) -> None:

    print()
    print("=" * 70)
    print(f"RECORD KE-{result.row}   (bottle_no = {result.bottle_no})")
    print("=" * 70)
    print(f"bottle_hash (FNV1A64) : {result.bottle_hash:#018x}")
    print("-" * 70)

    if not result.found:

        print("Bottle hash TIDAK DITEMUKAN di database.bin")

        print("-" * 70)

        print("STATUS : FAIL")

        print("=" * 70)

        return

    print(f"{'FIELD':<15}{'CSV':<20}{'BINARY (decoded)':<20}{'STATUS'}")

    print("-" * 70)

    for item in result.fields:

        status = "OK" if item.ok else "MISMATCH"

        print(f"{item.name:<15}{item.expected:<20}{item.actual:<20}{status}")

    print("-" * 70)

    print(f"STATUS : {'PASS' if result.is_pass else 'FAIL'}")

    print("=" * 70)


def print_compact(result: VerifyResult) -> None:

    status = "PASS" if result.is_pass else "FAIL"

    if not result.found:

        print(f"  [{status}] Row {result.row:<8} {result.bottle_no:<12} -> NOT FOUND in database.bin")

        return

    if result.is_pass:

        print(f"  [{status}] Row {result.row:<8} {result.bottle_no}")

    else:

        mismatch = ", ".join(

            f"{f.name}({f.expected}!={f.actual})"

            for f in result.fields

            if not f.ok
        )

        print(f"  [{status}] Row {result.row:<8} {result.bottle_no:<12} -> {mismatch}")


def print_records_summary(results: List[VerifyResult]) -> Tuple[int, int, int]:

    total_tested = len(results)

    total_pass = sum(1 for r in results if r.is_pass)

    total_fail = total_tested - total_pass

    total_not_found = sum(1 for r in results if not r.found)

    print()
    print("-" * 70)
    print("RINGKASAN RECORD")
    print("-" * 70)

    print(f"Total Diuji : {total_tested:,}")

    print(f"PASS        : {total_pass:,}")

    print(f"FAIL        : {total_fail:,}")

    print(f"  - Tidak Ditemukan : {total_not_found:,}")

    print(f"  - Field Mismatch  : {total_fail - total_not_found:,}")

    if total_fail > 0:

        print()

        print("DAFTAR RECORD GAGAL (maks 30 ditampilkan) :")

        print("-" * 70)

        shown = 0

        for r in results:

            if not r.is_pass:

                if not r.found:

                    print(f"  Row {r.row:<8} {r.bottle_no:<12} -> NOT FOUND")

                else:

                    mismatch = ", ".join(

                        f"{f.name}: CSV='{f.expected}' BIN='{f.actual}'"

                        for f in r.fields

                        if not f.ok
                    )

                    print(f"  Row {r.row:<8} {r.bottle_no:<12} -> {mismatch}")

                shown += 1

                if shown >= 30:

                    print(f"  ... dan {total_fail - shown} lainnya")

                    break

    return total_tested, total_pass, total_fail


# =============================================================================
# HIGH LEVEL ACTIONS
# =============================================================================

def action_verify_rows(

    csv_db: CSVDatabase,

    bin_db: BinaryDatabase,

    rows: List[int],

    mode_label: str,

    max_detail: int = 20,

    verbose: bool = False,

) -> CheckResult:

    print()
    print("=" * 70)
    print(f"VERIFY RECORD - MODE : {mode_label}")
    print("=" * 70)
    print(f"Jumlah record diuji : {len(rows):,}")

    verifier = RecordVerifier(bin_db)

    records = csv_db.get_records()

    results: List[VerifyResult] = []

    show_detail = verbose or len(rows) <= max_detail

    progress = None if show_detail else ProgressBar(len(rows), prefix="Verifying")

    for i, row in enumerate(rows, start=1):

        product = records[row - 1]

        result = verifier.verify(row, product)

        results.append(result)

        if show_detail:

            print_detail(result)

        else:

            progress.update(i)

    if progress is not None:

        elapsed = progress.finish()

        print(f"  Selesai dalam {elapsed:.2f} detik.")

    total, passed, failed = print_records_summary(results)

    return CheckResult(

        f"Record Verification ({mode_label})",

        failed == 0,

        f"{passed}/{total} PASS",
    )


def action_full_report(

    csv_db: CSVDatabase,

    bin_db: BinaryDatabase,

    stress_n: int,

    seed: Optional[int],

) -> bool:

    checker = StructuralChecker(bin_db)

    results: List[CheckResult] = []

    results.append(checker.crc_check())

    results.append(checker.dictionary_check())

    results.append(checker.sorted_check())

    total = csv_db.get_total_record()

    results.append(

        action_verify_rows(

            csv_db, bin_db, list(range(1, total + 1)),

            "ALL", max_detail=0,
        )
    )

    stress = StressTester(bin_db)

    results.append(

        stress.run(stress_n, csv_db.get_records(), seed=seed)
    )

    print()
    print("#" * 70)
    print("# FULL REPORT SUMMARY")
    print("#" * 70)

    for r in results:

        status = "PASS" if r.passed else "FAIL"

        print(f"  [{status}] {r.name:<32} {r.detail}")

    overall = all(r.passed for r in results)

    print("#" * 70)

    print()

    if overall:

        print("HASIL AKHIR : PASS  -  database.bin AMAN dipakai ESP32")

    else:

        print("HASIL AKHIR : FAIL  -  JANGAN gunakan database.bin ini di ESP32")

    print()

    return overall


# =============================================================================
# CSV RESOLVER
# =============================================================================

def resolve_csv(csv_arg: Optional[str]) -> Path:

    if csv_arg:

        path = Path(csv_arg)

        if not path.exists():

            raise FileNotFoundError(f"File CSV tidak ditemukan : {path}")

        return path

    search_dirs = []

    input_dir = Path("input")

    if input_dir.is_dir():

        search_dirs.append(input_dir)

    search_dirs.append(Path("."))

    for directory in search_dirs:

        found = sorted(directory.glob(f"*{config.SUPPORTED_EXTENSION}"))

        if found:

            return found[0]

    raise FileNotFoundError(

        f"Tidak ada file {config.SUPPORTED_EXTENSION} ditemukan. Gunakan --csv <path>."
    )


# =============================================================================
# INTERACTIVE MENU
# =============================================================================

def run_menu(csv_db: CSVDatabase, bin_db: BinaryDatabase) -> None:

    total = csv_db.get_total_record()

    checker = StructuralChecker(bin_db)

    stress = StressTester(bin_db)

    while True:

        print()
        print("=" * 70)
        print(" BINARY VERIFICATION TEST - MENU")
        print("=" * 70)

        print(f" Total Record CSV     : {total:,}")

        print(f" Total Record Binary  : {len(bin_db):,}")

        print("-" * 70)

        print(" 1. Verify record tertentu (nomor / rentang / gabungan)")

        print(" 2. Verify N record acak (random sample)")

        print(" 3. Verify SELURUH database (all records)")

        print(" 4. CRC32 Integrity Check")

        print(" 5. Dictionary Integrity Check")

        print(" 6. Sorted Check")

        print(" 7. Binary Search Stress Test (simulasi ESP32)")

        print(" 8. FULL REPORT (jalankan semua test 1-7)")

        print(" 0. Keluar")

        print("=" * 70)

        choice = input(" Pilih menu : ").strip()

        if choice == "1":

            spec = input(f" Nomor record (1-{total}), contoh 1,50-60,{total} : ").strip()

            if not spec:

                continue

            rows = parse_row_spec(spec, total)

            if rows:

                action_verify_rows(csv_db, bin_db, rows, f"ROW({spec})")

        elif choice == "2":

            raw = input(" Jumlah record acak : ").strip()

            try:

                n = int(raw)

            except ValueError:

                print(" Input tidak valid.")

                continue

            n = min(n, total)

            rows = sorted(random.sample(range(1, total + 1), n))

            action_verify_rows(csv_db, bin_db, rows, f"SAMPLE({n})")

        elif choice == "3":

            confirm = input(

                f" Ini akan menguji SEMUA {total:,} record, lanjutkan? (y/n) : "
            ).strip().lower()

            if confirm == "y":

                action_verify_rows(

                    csv_db, bin_db, list(range(1, total + 1)), "ALL", max_detail=0
                )

        elif choice == "4":

            checker.crc_check()

        elif choice == "5":

            checker.dictionary_check()

        elif choice == "6":

            checker.sorted_check()

        elif choice == "7":

            raw = input(" Jumlah pencarian stress test [default 5000] : ").strip()

            n = int(raw) if raw else 5000

            stress.run(n, csv_db.get_records())

        elif choice == "8":

            raw = input(" Jumlah pencarian stress test [default 5000] : ").strip()

            n = int(raw) if raw else 5000

            action_full_report(csv_db, bin_db, n, seed=None)

        elif choice == "0":

            print(" Keluar.")

            break

        else:

            print(" Pilihan tidak dikenal.")


# =============================================================================
# ARGUMENT PARSER
# =============================================================================

def build_arg_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(

        description="Binary Verification Test (Production Tool) - QR Database Converter"
    )

    parser.add_argument("--csv", type=str, default=None, help="Path file CSV sumber")

    parser.add_argument(

        "--output-dir", type=str, default=str(config.OUTPUT_FOLDER),
        help="Folder berisi database.bin dkk (default: output/)",
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument("--row", type=str, default=None, help="Contoh: 1 / 1,5,10 / 1-100 / 1,50-60,105298")

    mode.add_argument("--sample", type=int, default=None, help="Verifikasi N record acak")

    mode.add_argument("--all", action="store_true", help="Verifikasi SEMUA record")

    mode.add_argument("--crc-check", action="store_true", help="Hanya CRC32 Integrity Check")

    mode.add_argument("--dict-check", action="store_true", help="Hanya Dictionary Integrity Check")

    mode.add_argument("--sorted-check", action="store_true", help="Hanya Sorted Check")

    mode.add_argument("--stress", type=int, default=None, metavar="N", help="Binary Search Stress Test dengan N pencarian (mode berdiri sendiri)")

    mode.add_argument("--full", action="store_true", help="Jalankan SEMUA test (full report)")

    parser.add_argument("--stress-count", type=int, default=5000, metavar="N", help="Jumlah pencarian stress test saat memakai --full (default: 5000)")

    parser.add_argument("--seed", type=int, default=None, help="Seed random (untuk --sample / --stress)")

    parser.add_argument("--verbose", action="store_true", help="Selalu tampilkan detail per-record")

    parser.add_argument("--max-detail", type=int, default=20, help="Batas jumlah record sebelum output ringkas (default: 20)")

    parser.add_argument("--log", action="store_true", help="Simpan seluruh output ke logs/verify_<timestamp>.log")

    return parser


# =============================================================================
# MAIN
# =============================================================================

def main(argv: Optional[List[str]] = None) -> int:

    argv = argv if argv is not None else sys.argv[1:]

    args = build_arg_parser().parse_args(argv)

    interactive = len(argv) == 0

    logger = None

    original_stdout = sys.stdout

    if args.log or interactive:

        # Di mode interaktif, log tetap opsional -- default aktif supaya
        # sesi menu selalu bisa diaudit ulang.

        logger = TeeLogger(enabled=True)

        sys.stdout = logger

    try:

        print()
        print("#" * 70)
        print("# BINARY VERIFICATION TEST")
        print(f"# {config.APP_NAME} - v{config.VERSION}")
        print("#" * 70)

        csv_path = resolve_csv(args.csv)

        print(f"\nCSV Sumber    : {csv_path}")

        csv_db = CSVDatabase(csv_path)

        csv_db.load()

        output_dir = Path(args.output_dir)

        print(f"Output Folder : {output_dir.resolve()}")

        print()
        print("Membaca database.bin dan dictionary...")

        bin_db = BinaryDatabase(output_dir)

        bin_db.load()

        print(f"Total Record CSV     : {csv_db.get_total_record():,}")

        print(f"Total Record Binary  : {len(bin_db):,}")

        if logger is not None and logger.log_path is not None:

            print(f"Log disimpan ke      : {logger.log_path}")

        if interactive:

            run_menu(csv_db, bin_db)

            return 0

        total = csv_db.get_total_record()

        if args.full:

            n_stress = args.stress_count

            overall = action_full_report(csv_db, bin_db, n_stress, args.seed)

            return 0 if overall else 1

        if args.crc_check:

            result = StructuralChecker(bin_db).crc_check()

            return 0 if result.passed else 1

        if args.dict_check:

            result = StructuralChecker(bin_db).dictionary_check()

            return 0 if result.passed else 1

        if args.sorted_check:

            result = StructuralChecker(bin_db).sorted_check()

            return 0 if result.passed else 1

        if args.stress is not None:

            result = StressTester(bin_db).run(args.stress, csv_db.get_records(), seed=args.seed)

            return 0 if result.passed else 1

        if args.all:

            rows = list(range(1, total + 1))

            mode_label = "ALL"

        elif args.sample:

            random.seed(args.seed)

            n = min(args.sample, total)

            rows = sorted(random.sample(range(1, total + 1), n))

            mode_label = f"SAMPLE({n})"

        elif args.row:

            rows = parse_row_spec(args.row, total)

            mode_label = f"ROW({args.row})"

        else:

            rows = [1]

            mode_label = "DEFAULT(row 1)"

        result = action_verify_rows(

            csv_db, bin_db, rows, mode_label,
            max_detail=args.max_detail, verbose=args.verbose,
        )

        print()

        if result.passed:

            print("HASIL AKHIR : PASS  -  database.bin AMAN dipakai ESP32")

        else:

            print("HASIL AKHIR : FAIL  -  JANGAN gunakan database.bin ini di ESP32")

        print()

        return 0 if result.passed else 1

    except FileNotFoundError as err:

        print()
        print("ERROR :", err)
        print()

        return 1

    finally:

        sys.stdout = original_stdout

        if logger is not None:

            logger.close()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    sys.exit(main())
