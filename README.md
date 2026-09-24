# Database-Converter
Python-based CSV to binary database converter for ESP32, featuring FNV-1a hashing, dictionary compression, sorting, CRC32 validation, and optimized Binary Search support.

# QR Database Converter

**QR Database Converter** is a Python-based tool for converting QR/bottle database files from **CSV format** into optimized **binary (`.bin`) files** designed for use with an **ESP32**.

The converter processes and validates the input data, generates a **64-bit FNV-1a hash** from each `bottle_no`, creates compact dictionaries for repeated values, sorts records by `bottle_hash`, and generates binary database files that can be efficiently searched by the ESP32 using **Binary Search**.

---

## Features

* Convert CSV database files into binary `.bin` files
* Generate **64-bit FNV-1a hashes** from `bottle_no`
* Normalize bottle numbers before hashing
* Detect potential **hash collisions**
* Generate compact dictionaries for:

  * Brand
  * Material
  * Use To
  * Size
* Remove repeated string data through dictionary IDs
* Sort database records by `bottle_hash`
* Validate duplicate hashes
* Generate CRC32 for database integrity checking
* Generate database metadata
* Designed for efficient database access on ESP32

---

## Processing Flow

```text
CSV
 │
 ▼
Validation
 │
 ▼
Builder
 │
 ├── Generate Bottle Hash
 │
 ├── Build Dictionaries
 │
 ├── Build Binary Records
 │
 ├── Sort by Bottle Hash
 │
 └── Validate Database
 │
 ▼
Binary Database
 │
 ├── database.bin
 ├── brand.bin
 ├── material.bin
 ├── use_to.bin
 ├── size.bin
 └── metadata.bin
```

The generated database is sorted by `bottle_hash`, allowing the ESP32 to perform **Binary Search** instead of scanning the entire database.

---

# Requirements

* Python **3.10+**
* Windows, Linux, or macOS
* CSV database file

Check your Python installation:

```bash
python --version
```

On Windows, you can also use:

```bash
py --version
```

---

# Installation

Clone the repository:

```bash
git clone https://github.com/USERNAME/qr-database-converter.git
```

Navigate to the project directory:

```bash
cd qr-database-converter
```

Install the required Python packages:

```bash
py -m pip install -r requirements.txt
```

If you are using Linux or macOS:

```bash
python3 -m pip install -r requirements.txt
```

---

# Project Structure

A recommended repository structure is:

```text
qr-database-converter/
│
├── config.py
├── builder.py
├── validator.py
├── main.py
├── requirements.txt
├── README.md
│
├── database/
│   └── database.csv
│
├── output/
│   ├── database.bin
│   ├── brand.bin
│   ├── material.bin
│   ├── use_to.bin
│   ├── size.bin
│   └── metadata.bin
│
└── logs/
    ├── converter.log
    ├── invalid.csv
    └── duplicate.csv
```

`builder.py` is the database-building module and uses `config.py` for the global configuration. It also works with validated `ProductRecord` data.

---

# Input CSV Format

The input CSV must contain the following columns:

```csv
bottle_no,bottle_code,material_type,use_to,size_type,cashback
```

Example:

```csv
bottle_no,bottle_code,material_type,use_to,size_type,cashback
PE500XYSH,AQUA,PET,BOTTLE,500ML,5000
PE250ABCD,CLEO,PET,BOTTLE,250ML,2500
HD100XYZ,LEMINERAL,HDPE,BOTTLE,100ML,1000
```

The required column names are defined in `config.py`.

## Column Description

| Column          | Description              |
| --------------- | ------------------------ |
| `bottle_no`     | Unique bottle identifier |
| `bottle_code`   | Bottle brand/code        |
| `material_type` | Bottle material type     |
| `use_to`        | Intended use/category    |
| `size_type`     | Bottle size              |
| `cashback`      | Cashback value           |

---

# Usage

## 1. Prepare the CSV

Place your CSV database in the appropriate input directory.

For example:

```text
database/
└── database.csv
```

Make sure the CSV header matches:

```csv
bottle_no,bottle_code,material_type,use_to,size_type,cashback
```

---

## 2. Run the Converter

Run the main program:

```bash
py main.py
```

or:

```bash
python main.py
```

The converter will process the database through the following stages:

```text
Read CSV
   ↓
Validate Data
   ↓
Generate Bottle Hash
   ↓
Build Dictionary
   ↓
Build Binary Records
   ↓
Sort Records
   ↓
Check Hash Collision
   ↓
Write Binary Files
   ↓
Generate Metadata
```

> The exact entry-point filename should match the executable/main script included in the repository.

---

# Output Files

After a successful conversion, the `output/` directory will contain:

```text
output/
│
├── database.bin
├── brand.bin
├── material.bin
├── use_to.bin
├── size.bin
└── metadata.bin
```

These output filenames are defined in `config.py`.

---

## `database.bin`

`database.bin` contains the main binary database records.

Each record contains:

```text
bottle_hash
brand_id
material_id
use_to_id
size_id
cashback
```

The binary record format is:

```text
<QHHHHI
```

with a total record size of **18 bytes**.

### Record Layout

| Field         | Type   |         Size |
| ------------- | ------ | -----------: |
| `bottle_hash` | uint64 |      8 bytes |
| `brand_id`    | uint16 |      2 bytes |
| `material_id` | uint16 |      2 bytes |
| `use_to_id`   | uint16 |      2 bytes |
| `size_id`     | uint16 |      2 bytes |
| `cashback`    | uint32 |      4 bytes |
| **Total**     |        | **18 bytes** |

---

## `brand.bin`

Contains the brand dictionary.

For example:

```text
0 → AQUA
1 → CLEO
2 → LEMINERAL
```

Repeated strings are stored only once and referenced through numeric IDs.

---

## `material.bin`

Contains the material dictionary.

Example:

```text
0 → PET
1 → HDPE
```

---

## `use_to.bin`

Contains the dictionary for the `use_to` field.

---

## `size.bin`

Contains the size dictionary.

Example:

```text
0 → 100ML
1 → 250ML
2 → 500ML
3 → 1000ML
```

---

## `metadata.bin`

Contains metadata required to describe the generated database, including:

* Database magic
* Database version
* Record count
* Record size
* CRC32
* Brand dictionary count
* Material dictionary count
* Use To dictionary count
* Size dictionary count

The metadata is generated after the binary database and dictionaries are written.

---

# Hashing

The converter uses **FNV-1a 64-bit** to generate a hash from `bottle_no`.

The process is:

```text
bottle_no
    │
    ▼
Normalize
    │
    ▼
FNV-1a 64-bit
    │
    ▼
bottle_hash
```

Before hashing, the bottle number is:

1. Trimmed using `strip()`
2. Converted to uppercase using `upper()`

For example:

```text
" PE500XYSH "
```

becomes:

```text
"PE500XYSH"
```

before the hash is generated.

### Important

The FNV-1a implementation on the ESP32 **must match the implementation used by this converter**.

Otherwise, the same `bottle_no` will generate a different hash and the ESP32 will not be able to find the corresponding database record.

---

# Binary Search

The generated `database.bin` is sorted according to:

```text
bottle_hash
```

The sorting process ensures that the database can be searched efficiently using **Binary Search**.

Conceptually:

```text
CSV
 │
 ├── Bottle A
 ├── Bottle C
 ├── Bottle B
 └── Bottle D
       │
       ▼
Generate Hash
       │
       ▼
Sort by Hash
       │
       ▼
database.bin
```

On the ESP32:

```text
Scan QR
   ↓
Get bottle_no
   ↓
Generate FNV-1a Hash
   ↓
Binary Search database.bin
   ↓
Find Matching Record
   ↓
Read Cashback
```

This allows the ESP32 to search the database without sequentially reading every record.

---

# Dictionary System

The converter uses dictionaries to avoid storing identical strings repeatedly.

Instead of storing:

```text
AQUA
AQUA
AQUA
AQUA
CLEO
CLEO
```

the converter creates:

```text
0 → AQUA
1 → CLEO
```

The database records then store:

```text
brand_id = 0
```

instead of storing the complete string `AQUA`.

This approach reduces repeated string data in the binary database.

The same mechanism is used for:

* Brand
* Material
* Use To
* Size

---

# Hash Collision Detection

The converter checks for hash collisions before writing the database.

For example:

```text
BOTTLE_A → HASH_X
BOTTLE_B → HASH_X
```

If `BOTTLE_A` and `BOTTLE_B` are different bottle numbers but produce the same hash, the build process will stop and report the collision.

This check is implemented before the binary database is generated.

---

# Dictionary Limits

Dictionary IDs use `uint16`.

The configured maximum number of entries is:

```text
Brand     : 65,535
Material  : 65,535
Use To    : 65,535
Size      : 65,535
```

These limits are defined in `config.py`.

---

# CRC32

The converter calculates a **CRC32** value while writing `database.bin`.

The CRC32 value is stored in `metadata.bin` and can be used by the ESP32 to verify the integrity of the database.

---

# Logs

The converter provides a log directory:

```text
logs/
```

The configured log files are:

```text
logs/
├── converter.log
├── invalid.csv
└── duplicate.csv
```

These paths are configured in `config.py`.

---

# ESP32 Integration

The generated binary files are intended to be used by an ESP32-based system.

Typical workflow:

```text
                 CSV DATABASE
                      │
                      ▼
            QR Database Converter
                      │
                      ▼
              Binary Database
                      │
                      ▼
                  microSD
                      │
                      ▼
                    ESP32
                      │
                      ▼
                  QR Scanner
                      │
                      ▼
              Read bottle_no
                      │
                      ▼
               FNV-1a Hash
                      │
                      ▼
               Binary Search
                      │
                      ▼
              Database Record
                      │
                      ▼
                 Cashback
```

---

# Example

### Input

```csv
bottle_no,bottle_code,material_type,use_to,size_type,cashback
PE500XYSH,AQUA,PET,BOTTLE,500ML,5000
PE250ABCD,CLEO,PET,BOTTLE,250ML,2500
HD100XYZ,LEMINERAL,HDPE,BOTTLE,100ML,1000
```

### Output

```text
output/
├── database.bin
├── brand.bin
├── material.bin
├── use_to.bin
├── size.bin
└── metadata.bin
```

The ESP32 can then generate the same hash from a scanned `bottle_no` and search the sorted `database.bin` using Binary Search.

---

# Important Notes

### 1. Keep the Hash Algorithm Consistent

Do not change the FNV-1a implementation independently between Python and ESP32.

Both systems must generate the same 64-bit hash.

### 2. Keep the Binary Record Structure Consistent

The current binary record size is:

```text
18 bytes
```

Any change to the binary record format must also be reflected in the ESP32 firmware.

### 3. Keep `bottle_no` Normalization Consistent

The converter currently normalizes the value using:

```python
bottle_no.strip().upper()
```

Therefore:

```text
PE500XYSH
pe500xysh
 PE500XYSH
```

are normalized before hashing.

The ESP32 implementation should perform the same normalization.

---

# Configuration

The main application configuration is located in:

```text
config.py
```

The configuration defines:

* Application name
* Version
* Supported CSV extension
* Input encoding
* Output directory
* Log directory
* Output filenames
* CSV column names
* Cashback limits
* Database format
* Hash algorithm
* Dictionary limits
* CRC32 settings
* Metadata settings
* Debug/progress options

For example:

```python
APP_NAME = "QR Database Converter"
VERSION = "1.0.0"
SUPPORTED_EXTENSION = ".csv"
DEFAULT_ENCODING = "utf-8-sig"
```

---

# Version

**QR Database Converter**

Current application version:

```text
1.0.0
```

The `builder.py` module currently uses:

```text
Builder Version: 2.0.0
```

---

# Author

**Kurnia Project**

QR Database Converter
Python → Binary Database → ESP32
