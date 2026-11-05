"""

Required measurement types:
    Nominal: shoe_category
    Ordinal: quality_grade, ordered C < B < A
    Interval: production_year
    Ratio: sole_thickness_mm and defect_count

Tables:
    shoe_models:       60 rows
    materials:         25 rows
    model_materials:  180 rows
    factories:         12 rows
    production_runs:  300 rows
    quality_tests:  3,030 rows

Deliberate imperfections:
    2 missing factory emails
    90 missing thickness measurements and associated grades
    30 extra duplicate inspection events

Composite primary keys:
    model_materials: (model_id, component)
    quality_tests: (run_id, test_sequence)
"""

import math
import random
import sqlite3
import tempfile

from datetime import datetime, timedelta
from pathlib import Path
from google.colab import files


# ============================================================
# 1. Reproducible configuration
# ============================================================

SEED = 3398
rng = random.Random(SEED)

MODEL_COUNT = 60
MATERIAL_COUNT = 25
FACTORY_COUNT = 12
RUN_COUNT = 300
TESTS_PER_RUN = 10

BASE_TEST_COUNT = RUN_COUNT * TESTS_PER_RUN

MISSING_EMAIL_COUNT = 2
MISSING_THICKNESS_COUNT = 90
DUPLICATE_COUNT = 30

# A fresh folder prevents overwriting previous databases.
OUTPUT_DIR = Path(
    tempfile.mkdtemp(prefix="shoe_quality_", dir="/content")
)
DATABASE_PATH = OUTPUT_DIR / "shoe_quality.db"


# ============================================================
# 2. Helper functions
# ============================================================

def valid_date(column):
    """SQL expression requiring a valid ISO calendar date."""
    return f"""
        length({column}) = 10
        AND {column} GLOB
            '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date({column}, '+0 days') IS NOT NULL
        AND date({column}, '+0 days') = {column}
    """


def classify_grade(defects, sample_size, thickness, target, tolerance):
    """
    Fictional inspection thresholds, not industry standards.

    Missing thickness means assessment is incomplete.

    A:
        defective proportion <= 2%
        AND thickness deviation <= tolerance

    B:
        defective proportion <= 5%
        AND thickness deviation <= twice tolerance

    C:
        otherwise
    """
    if thickness is None:
        return None

    defect_rate = defects / sample_size
    deviation = abs(thickness - target)

    if defect_rate <= 0.02 and deviation <= tolerance:
        return "A"

    if defect_rate <= 0.05 and deviation <= 2 * tolerance:
        return "B"

    return "C"


# ============================================================
# 3. Schema and attribute constraints
# ============================================================

SCHEMA = """
CREATE TABLE shoe_models (
    model_id INTEGER PRIMARY KEY,

    model_name TEXT NOT NULL UNIQUE
        CHECK (length(trim(model_name)) > 0),

    shoe_category TEXT NOT NULL
        CHECK (
            shoe_category IN ('Trainer', 'Formal', 'Boot', 'Sandal')
        ),

    target_sole_thickness_mm REAL NOT NULL
        CHECK (
            typeof(target_sole_thickness_mm) IN ('integer', 'real')
            AND target_sole_thickness_mm BETWEEN 3 AND 60
        ),

    tolerance_mm REAL NOT NULL
        CHECK (
            typeof(tolerance_mm) IN ('integer', 'real')
            AND tolerance_mm > 0
            AND tolerance_mm < target_sole_thickness_mm
        )
);

CREATE TABLE materials (
    material_id INTEGER PRIMARY KEY,

    material_name TEXT NOT NULL UNIQUE
        CHECK (length(trim(material_name)) > 0),

    material_category TEXT NOT NULL
        CHECK (
            material_category IN ('Textile', 'Leather', 'Foam', 'Rubber')
        ),

    cost_pence_per_m2 INTEGER NOT NULL
        CHECK (
            typeof(cost_pence_per_m2) = 'integer'
            AND cost_pence_per_m2 > 0
        )
);

CREATE TABLE model_materials (
    model_id INTEGER NOT NULL,

    component TEXT NOT NULL
        CHECK (component IN ('Upper', 'Lining', 'Outsole')),

    material_id INTEGER NOT NULL,

    area_m2_per_pair REAL NOT NULL
        CHECK (
            typeof(area_m2_per_pair) IN ('integer', 'real')
            AND area_m2_per_pair > 0
            AND area_m2_per_pair <= 1
        ),

    PRIMARY KEY (model_id, component),

    FOREIGN KEY (model_id)
        REFERENCES shoe_models(model_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,

    FOREIGN KEY (material_id)
        REFERENCES materials(material_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE factories (
    factory_id INTEGER PRIMARY KEY,

    factory_name TEXT NOT NULL UNIQUE
        CHECK (length(trim(factory_name)) > 0),

    country TEXT NOT NULL
        CHECK (
            country IN ('India', 'Vietnam', 'Portugal', 'Indonesia')
        ),

    annual_capacity_pairs INTEGER NOT NULL
        CHECK (
            typeof(annual_capacity_pairs) = 'integer'
            AND annual_capacity_pairs > 0
        ),

    contact_email TEXT
        CHECK (
            contact_email IS NULL
            OR contact_email LIKE '%@example.com'
        )
);

CREATE TABLE production_runs (
    run_id INTEGER PRIMARY KEY,

    model_id INTEGER NOT NULL,
    factory_id INTEGER NOT NULL,

    production_year INTEGER NOT NULL
        CHECK (
            typeof(production_year) = 'integer'
            AND production_year BETWEEN 2020 AND 2030
        ),

    started_on TEXT NOT NULL
        CHECK (__START_DATE__),

    completed_on TEXT NOT NULL
        CHECK (
            __END_DATE__
            AND completed_on >= started_on
        ),

    quantity_produced_pairs INTEGER NOT NULL
        CHECK (
            typeof(quantity_produced_pairs) = 'integer'
            AND quantity_produced_pairs > 0
        ),

    CHECK (
        production_year = CAST(substr(started_on, 1, 4) AS INTEGER)
        AND production_year = CAST(substr(completed_on, 1, 4) AS INTEGER)
    ),

    FOREIGN KEY (model_id)
        REFERENCES shoe_models(model_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,

    FOREIGN KEY (factory_id)
        REFERENCES factories(factory_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE quality_tests (
    run_id INTEGER NOT NULL,

    test_sequence INTEGER NOT NULL
        CHECK (
            typeof(test_sequence) = 'integer'
            AND test_sequence > 0
        ),

    tested_at TEXT NOT NULL
        CHECK (
            length(tested_at) = 19
            AND tested_at GLOB
                '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'
            AND datetime(tested_at, '+0 days') IS NOT NULL
            AND datetime(tested_at, '+0 days') = tested_at
        ),

    sample_size_pairs INTEGER NOT NULL
        CHECK (
            typeof(sample_size_pairs) = 'integer'
            AND sample_size_pairs > 0
        ),

    defect_count INTEGER NOT NULL
        CHECK (
            typeof(defect_count) = 'integer'
            AND defect_count BETWEEN 0 AND sample_size_pairs
        ),

    sole_thickness_mm REAL
        CHECK (
            sole_thickness_mm IS NULL
            OR (
                typeof(sole_thickness_mm) IN ('integer', 'real')
                AND sole_thickness_mm > 0
                AND sole_thickness_mm <= 100
            )
        ),

    quality_grade TEXT
        CHECK (
            quality_grade IS NULL
            OR quality_grade IN ('A', 'B', 'C')
        ),

    notes TEXT
        CHECK (notes IS NULL OR length(trim(notes)) > 0),

    CHECK (
        (
            sole_thickness_mm IS NULL
            AND quality_grade IS NULL
        )
        OR
        (
            sole_thickness_mm IS NOT NULL
            AND quality_grade IS NOT NULL
        )
    ),

    PRIMARY KEY (run_id, test_sequence),

    FOREIGN KEY (run_id)
        REFERENCES production_runs(run_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX idx_run_model ON production_runs(model_id);
CREATE INDEX idx_run_factory ON production_runs(factory_id);
CREATE INDEX idx_material_reference ON model_materials(material_id);
CREATE INDEX idx_test_date ON quality_tests(tested_at);
"""

SCHEMA = (
    SCHEMA
    .replace("__START_DATE__", valid_date("started_on"))
    .replace("__END_DATE__", valid_date("completed_on"))
)


# ============================================================
# 4. Cross-table business rules
# ============================================================

BUSINESS_RULES = """
CREATE VIEW business_rule_violations AS

SELECT 'Annual factory capacity exceeded' AS violation
FROM production_runs r
JOIN factories f ON f.factory_id = r.factory_id
GROUP BY r.factory_id, r.production_year
HAVING SUM(r.quantity_produced_pairs) > f.annual_capacity_pairs

UNION ALL

SELECT 'Inspection outside production period'
FROM quality_tests q
JOIN production_runs r ON r.run_id = q.run_id
WHERE date(q.tested_at) < r.started_on
   OR date(q.tested_at) > r.completed_on

UNION ALL

SELECT 'Inspection sample exceeds production quantity'
FROM quality_tests q
JOIN production_runs r ON r.run_id = q.run_id
WHERE q.sample_size_pairs > r.quantity_produced_pairs

UNION ALL

SELECT 'Incorrect quality grade'
FROM quality_tests q
JOIN production_runs r ON r.run_id = q.run_id
JOIN shoe_models m ON m.model_id = r.model_id
WHERE q.sole_thickness_mm IS NOT NULL
  AND q.quality_grade !=
      CASE
          WHEN 1.0 * q.defect_count / q.sample_size_pairs <= 0.02
           AND abs(
               q.sole_thickness_mm - m.target_sole_thickness_mm
           ) <= m.tolerance_mm
          THEN 'A'

          WHEN 1.0 * q.defect_count / q.sample_size_pairs <= 0.05
           AND abs(
               q.sole_thickness_mm - m.target_sole_thickness_mm
           ) <= 2 * m.tolerance_mm
          THEN 'B'

          ELSE 'C'
      END

UNION ALL

SELECT 'Incompatible component material'
FROM model_materials mm
JOIN materials m ON m.material_id = mm.material_id
WHERE (
    mm.component = 'Upper'
    AND m.material_category NOT IN ('Textile', 'Leather')
)
OR (
    mm.component = 'Lining'
    AND m.material_category NOT IN ('Textile', 'Foam')
)
OR (
    mm.component = 'Outsole'
    AND m.material_category != 'Rubber'
);
"""


def create_business_triggers(connection):
    """
    Check cross-table rules after inserts and updates.
    Parent changes are covered as well as child changes.
    """
    for table in (
        "shoe_models",
        "materials",
        "model_materials",
        "factories",
        "production_runs",
        "quality_tests"
    ):
        for operation in ("INSERT", "UPDATE"):
            connection.execute(f"""
                CREATE TRIGGER check_{table}_{operation.lower()}
                AFTER {operation} ON {table}
                BEGIN
                    SELECT CASE WHEN EXISTS (
                        SELECT 1 FROM business_rule_violations
                    )
                    THEN RAISE(
                        ABORT,
                        'Shoe quality business rule violated'
                    )
                    END;
                END;
            """)


# ============================================================
# 5. Generate shoe models
# ============================================================

# Categories have different target thickness ranges.
category_ranges = {
    "Trainer": (20, 35),
    "Formal": (7, 14),
    "Boot": (15, 28),
    "Sandal": (8, 18)
}

models = []

for model_id in range(1, MODEL_COUNT + 1):
    # First four guarantee representation of every category.
    category = (
        list(category_ranges)[model_id - 1]
        if model_id <= 4
        else rng.choices(
            list(category_ranges),
            weights=[45, 20, 20, 15],
            k=1
        )[0]
    )

    low, high = category_ranges[category]

    models.append((
        model_id,
        f"SimShoe-{model_id:03d}",
        category,
        round(rng.uniform(low, high), 2),
        round(rng.uniform(0.6, 1.2), 2)
    ))

model_lookup = {row[0]: row for row in models}


# ============================================================
# 6. Generate materials and component specifications
# ============================================================

materials = []

for material_id in range(1, MATERIAL_COUNT + 1):
    if material_id <= 8:
        category = "Textile"
        median_cost = 900
    elif material_id <= 14:
        category = "Leather"
        median_cost = 2600
    elif material_id <= 19:
        category = "Foam"
        median_cost = 700
    else:
        category = "Rubber"
        median_cost = 1100

    cost = max(
        100,
        min(
            10000,
            int(rng.lognormvariate(math.log(median_cost), 0.3))
        )
    )

    materials.append((
        material_id,
        f"SimMaterial-{material_id:02d}",
        category,
        cost
    ))

component_categories = {
    "Upper": {"Textile", "Leather"},
    "Lining": {"Textile", "Foam"},
    "Outsole": {"Rubber"}
}

component_areas = {
    "Upper": (0.12, 0.25),
    "Lining": (0.08, 0.18),
    "Outsole": (0.035, 0.065)
}

model_materials = []

for model_id in range(1, MODEL_COUNT + 1):
    for component, allowed_categories in component_categories.items():
        eligible = [
            row[0] for row in materials
            if row[2] in allowed_categories
        ]

        low, high = component_areas[component]

        model_materials.append((
            model_id,
            component,
            rng.choice(eligible),
            round(rng.uniform(low, high), 4)
        ))

# Each component has one material specification in this simplified design.
# Outsole area refers to sheet footprint, not outsole volume.


# ============================================================
# 7. Generate factories
# ============================================================

factory_names = [
    "Alder", "Birch", "Cedar", "Dune",
    "Elm", "Fern", "Grove", "Hazel",
    "Iris", "Juniper", "Linden", "Maple"
]

missing_email_ids = set(
    rng.sample(range(1, FACTORY_COUNT + 1), MISSING_EMAIL_COUNT)
)

factories = []

for factory_id, name in enumerate(factory_names, start=1):
    factories.append((
        factory_id,
        f"Fictional {name} Footwear",
        rng.choices(
            ["India", "Vietnam", "Portugal", "Indonesia"],
            weights=[4, 3, 1, 2],
            k=1
        )[0],
        rng.randint(250000, 500000),
        None if factory_id in missing_email_ids
        else f"quality.{name.lower()}@example.com"
    ))

factory_lookup = {row[0]: row for row in factories}

# Small simulated differences, not claims about real factories.
factory_defect_rates = {
    row[0]: rng.uniform(0.008, 0.035)
    for row in factories
}


# ============================================================
# 8. Generate production runs
# ============================================================

runs = []

model_weights = [
    rng.lognormvariate(0, 0.7)
    for _ in models
]

annual_allocations = {}

for run_id in range(1, RUN_COUNT + 1):
    model_id = (
        run_id if run_id <= MODEL_COUNT
        else rng.choices(
            range(1, MODEL_COUNT + 1),
            weights=model_weights,
            k=1
        )[0]
    )

    factory_id = (
        run_id if run_id <= FACTORY_COUNT
        else rng.choices(
            range(1, FACTORY_COUNT + 1),
            weights=[row[3] for row in factories],
            k=1
        )[0]
    )

    year = rng.choice([2024, 2025])

    # Starting by early November keeps completion within the same year.
    started = datetime(year, 1, 1) + timedelta(
        days=rng.randint(0, 300)
    )
    completed = started + timedelta(days=rng.randint(12, 25))

    quantity = max(
        1500,
        min(
            12000,
            int(rng.lognormvariate(math.log(5000), 0.4))
        )
    )

    key = (factory_id, year)
    previous_quantity = annual_allocations.get(key, 0)
    capacity = factory_lookup[factory_id][3]

    if previous_quantity + quantity > capacity:
        raise RuntimeError(
            "Generated annual production exceeds factory capacity."
        )

    annual_allocations[key] = previous_quantity + quantity

    runs.append((
        run_id,
        model_id,
        factory_id,
        year,
        started.date().isoformat(),
        completed.date().isoformat(),
        quantity
    ))


# ============================================================
# 9. Generate quality inspections
# ============================================================

tests = []

for run in runs:
    run_id, model_id, factory_id = run[0], run[1], run[2]
    started = datetime.fromisoformat(run[4])
    completed = datetime.fromisoformat(run[5])

    model = model_lookup[model_id]
    target = model[3]
    tolerance = model[4]

    # A consistent run-level offset creates related measurements.
    thickness_offset = rng.gauss(0, tolerance * 0.45)

    defect_probability = min(
        0.12,
        max(
            0.002,
            factory_defect_rates[factory_id]
            * rng.uniform(0.6, 1.6)
        )
    )

    period_seconds = int((completed - started).total_seconds())

    for sequence in range(1, TESTS_PER_RUN + 1):
        # Distinct, increasing timestamps within each run.
        tested_at = started + timedelta(
            seconds=int(
                period_seconds * sequence / (TESTS_PER_RUN + 1)
            )
        )

        sample_size = rng.randint(30, 80)

        # Binomial simulation: count defective pairs, not individual faults.
        defective_pairs = sum(
            rng.random() < defect_probability
            for _ in range(sample_size)
        )

        measured_thickness = round(
            max(
                0.5,
                rng.gauss(
                    target + thickness_offset,
                    tolerance * 0.65
                )
            ),
            2
        )

        grade = classify_grade(
            defective_pairs,
            sample_size,
            measured_thickness,
            target,
            tolerance
        )

        note = (
            None if grade == "A"
            else "Review required under fictional inspection thresholds."
        )

        tests.append((
            run_id,
            sequence,
            tested_at.strftime("%Y-%m-%d %H:%M:%S"),
            sample_size,
            defective_pairs,
            measured_thickness,
            grade,
            note
        ))

# Each inspection measures one representative thickness and inspects
# a sample for defective pairs. Samples may overlap between inspections;
# sample totals are not treated as separate manufactured stock.


# ============================================================
# 10. Deliberately insert missing and duplicate records
# ============================================================

duplicate_sources = rng.sample(
    range(len(tests)),
    DUPLICATE_COUNT
)
duplicate_source_set = set(duplicate_sources)

missing_candidates = [
    index for index in range(len(tests))
    if index not in duplicate_source_set
]

missing_indices = rng.sample(
    missing_candidates,
    MISSING_THICKNESS_COUNT
)

for index in missing_indices:
    record = list(tests[index])

    # Missing gauge measurement prevents a complete quality grade.
    record[5] = None
    record[6] = None
    record[7] = "Thickness gauge unavailable; assessment incomplete."

    tests[index] = tuple(record)

next_sequence = {
    run_id: TESTS_PER_RUN
    for run_id in range(1, RUN_COUNT + 1)
}

for source_index in duplicate_sources:
    record = list(tests[source_index])
    run_id = record[0]

    # Preserve the business event but assign a fresh primary key.
    next_sequence[run_id] += 1
    record[1] = next_sequence[run_id]

    tests.append(tuple(record))


# ============================================================
# 11. Create and populate the database
# ============================================================

connection = sqlite3.connect(DATABASE_PATH)

try:
    connection.execute("PRAGMA foreign_keys = ON")

    if connection.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0] != 1:
        raise RuntimeError("Foreign keys could not be enabled.")

    connection.executescript(SCHEMA)
    connection.executescript(BUSINESS_RULES)
    create_business_triggers(connection)

    with connection:
        connection.executemany(
            "INSERT INTO shoe_models VALUES (?, ?, ?, ?, ?)",
            models
        )

        connection.executemany(
            "INSERT INTO materials VALUES (?, ?, ?, ?)",
            materials
        )

        connection.executemany(
            "INSERT INTO factories VALUES (?, ?, ?, ?, ?)",
            factories
        )

        connection.executemany(
            "INSERT INTO model_materials VALUES (?, ?, ?, ?)",
            model_materials
        )

        connection.executemany(
            "INSERT INTO production_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            runs
        )

        connection.executemany(
            "INSERT INTO quality_tests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tests
        )


    # ========================================================
    # 12. Validate counts, columns and relationships
    # ========================================================

    def scalar(sql, parameters=()):
        return connection.execute(sql, parameters).fetchone()[0]


    expected_counts = {
        "shoe_models": 60,
        "materials": 25,
        "model_materials": 180,
        "factories": 12,
        "production_runs": 300,
        "quality_tests": 3030
    }

    composite_keys = {}

    print("TABLE COUNTS AND STRUCTURES\n")

    for table, expected in expected_counts.items():
        count = scalar(f"SELECT COUNT(*) FROM {table}")

        if count != expected:
            raise RuntimeError(f"Incorrect row count: {table}")

        columns = connection.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()

        primary_key = [
            column[1]
            for column in sorted(columns, key=lambda item: item[5])
            if column[5] > 0
        ]

        if not primary_key:
            raise RuntimeError(f"No primary key: {table}")

        if len(primary_key) > 1:
            composite_keys[table] = primary_key

            if any(
                column[5] > 0 and column[3] != 1
                for column in columns
            ):
                raise RuntimeError("Nullable composite key component.")

        print(f"{table}: {count:,} rows")
        print(
            "Columns:",
            ", ".join(
                f"{column[1]} ({column[2]})"
                for column in columns
            )
        )
        print("Primary key:", ", ".join(primary_key))

        for fk in connection.execute(
            f"PRAGMA foreign_key_list({table})"
        ):
            print(f"Foreign key: {fk[3]} → {fk[2]}.{fk[4]}")

        print()

    if len(composite_keys) != 2:
        raise RuntimeError("Expected two composite primary keys.")

    if len(connection.execute(
        "PRAGMA table_info(quality_tests)"
    ).fetchall()) < 7:
        raise RuntimeError("Seven-column requirement not met.")

    if scalar("SELECT COUNT(*) FROM quality_tests") < 1000:
        raise RuntimeError("Thousand-row requirement not met.")

    if scalar("SELECT COUNT(*) FROM business_rule_violations"):
        raise RuntimeError("Cross-table business-rule violation found.")

    # Confirm complete component specifications.
    incomplete_models = scalar("""
        SELECT COUNT(*)
        FROM shoe_models m
        WHERE (
            SELECT COUNT(*)
            FROM model_materials mm
            WHERE mm.model_id = m.model_id
        ) != 3
    """)

    if incomplete_models:
        raise RuntimeError("Incomplete component specifications.")

    for parent, child, key in [
        ("shoe_models", "production_runs", "model_id"),
        ("factories", "production_runs", "factory_id"),
        ("production_runs", "quality_tests", "run_id")
    ]:
        missing_children = scalar(f"""
            SELECT COUNT(*)
            FROM {parent} p
            WHERE NOT EXISTS (
                SELECT 1 FROM {child} c
                WHERE c.{key} = p.{key}
            )
        """)

        if missing_children:
            raise RuntimeError(f"Missing related records: {parent}")


    # ========================================================
    # 13. Validate deliberate imperfections
    # ========================================================

    missing_thickness = scalar("""
        SELECT COUNT(*) FROM quality_tests
        WHERE sole_thickness_mm IS NULL
    """)

    missing_grades = scalar("""
        SELECT COUNT(*) FROM quality_tests
        WHERE quality_grade IS NULL
    """)

    missing_emails = scalar("""
        SELECT COUNT(*) FROM factories
        WHERE contact_email IS NULL
    """)

    missing_notes = scalar("""
        SELECT COUNT(*) FROM quality_tests
        WHERE notes IS NULL
    """)

    duplicate_groups, duplicate_extra_rows = connection.execute("""
        SELECT COUNT(*), COALESCE(SUM(copies - 1), 0)
        FROM (
            SELECT COUNT(*) AS copies
            FROM quality_tests
            GROUP BY run_id, tested_at, sample_size_pairs,
                     defect_count, sole_thickness_mm,
                     quality_grade, notes
            HAVING COUNT(*) > 1
        )
    """).fetchone()

    if missing_thickness != MISSING_THICKNESS_COUNT:
        raise RuntimeError("Incorrect missing thickness count.")

    if missing_grades != MISSING_THICKNESS_COUNT:
        raise RuntimeError("Incorrect incomplete grade count.")

    if missing_emails != MISSING_EMAIL_COUNT:
        raise RuntimeError("Incorrect missing email count.")

    if (
        duplicate_groups != DUPLICATE_COUNT
        or duplicate_extra_rows != DUPLICATE_COUNT
    ):
        raise RuntimeError("Incorrect duplicate count.")

    present_grades = {
        row[0]
        for row in connection.execute("""
            SELECT DISTINCT quality_grade
            FROM quality_tests
            WHERE quality_grade IS NOT NULL
        """)
    }

    if present_grades != {"A", "B", "C"}:
        raise RuntimeError("Not all ordinal grades are represented.")

    total_tests = expected_counts["quality_tests"]

    print("MISSING AND DUPLICATE DATA\n")

    print(
        f"Missing thickness: {missing_thickness}/{BASE_TEST_COUNT} "
        f"({missing_thickness / BASE_TEST_COUNT * 100:.2f}% "
        "of original tests)"
    )

    print(
        f"Missing thickness: {missing_thickness}/{total_tests} "
        f"({missing_thickness / total_tests * 100:.2f}% "
        "of final records)"
    )

    print(f"Associated incomplete grades: {missing_grades}")

    print(
        f"Missing factory emails: {missing_emails}/{FACTORY_COUNT} "
        f"({missing_emails / FACTORY_COUNT * 100:.2f}%)"
    )

    print(
        f"Optional notes without comments: {missing_notes}/{total_tests} "
        f"({missing_notes / total_tests * 100:.2f}%)"
    )

    print(f"Duplicate event groups: {duplicate_groups}")

    print(
        f"Extra duplicate rows: {duplicate_extra_rows}/{total_tests} "
        f"({duplicate_extra_rows / total_tests * 100:.2f}%)"
    )


    # ========================================================
    # 14. Test rejection of invalid data
    # ========================================================

    def expect_rejection(name, sql, parameters=()):
        connection.execute("SAVEPOINT constraint_test")

        try:
            connection.execute(sql, parameters)

        except sqlite3.IntegrityError:
            print(f"PASS: {name}")

        else:
            raise RuntimeError(
                f"Invalid operation unexpectedly accepted: {name}"
            )

        finally:
            connection.execute("ROLLBACK TO constraint_test")
            connection.execute("RELEASE constraint_test")


    print("\nCONSTRAINT TESTS\n")

    expect_rejection(
        "Missing required factory name",
        """
        INSERT INTO factories
        VALUES (9999, NULL, 'India', 100000, NULL)
        """
    )

    expect_rejection(
        "Duplicate model name",
        """
        INSERT INTO shoe_models
        SELECT 9999, model_name, shoe_category,
               target_sole_thickness_mm, tolerance_mm
        FROM shoe_models WHERE model_id = 1
        """
    )

    expect_rejection(
        "Invalid foreign key",
        """
        INSERT INTO quality_tests
        VALUES (
            9999, 1, '2025-01-01 12:00:00',
            50, 0, 20, 'A', NULL
        )
        """
    )

    expect_rejection(
        "Duplicate component composite key",
        """
        INSERT INTO model_materials
        SELECT * FROM model_materials LIMIT 1
        """
    )

    expect_rejection(
        "Duplicate inspection composite key",
        """
        INSERT INTO quality_tests
        SELECT * FROM quality_tests LIMIT 1
        """
    )

    expect_rejection(
        "Negative defect count",
        """
        UPDATE quality_tests
        SET defect_count = -1
        WHERE run_id = 1 AND test_sequence = 1
        """
    )

    expect_rejection(
        "Defective pairs exceed sample size",
        """
        UPDATE quality_tests
        SET defect_count = sample_size_pairs + 1
        WHERE run_id = 1 AND test_sequence = 1
        """
    )

    expect_rejection(
        "Non-positive thickness",
        """
        UPDATE quality_tests
        SET sole_thickness_mm = -2
        WHERE run_id = 1 AND test_sequence = 1
        """
    )

    expect_rejection(
        "Invalid ordinal category",
        """
        UPDATE quality_tests
        SET quality_grade = 'Excellent'
        WHERE run_id = 1 AND test_sequence = 1
        """
    )

    expect_rejection(
        "Impossible calendar date",
        """
        UPDATE production_runs
        SET started_on = '2025-02-30'
        WHERE run_id = 1
        """
    )

    expect_rejection(
        "Completion before production start",
        """
        UPDATE production_runs
        SET completed_on = '2020-01-01'
        WHERE run_id = 1
        """
    )

    expect_rejection(
        "Production year inconsistent with dates",
        """
        UPDATE production_runs
        SET production_year = 2020
        WHERE run_id = 1
        """
    )

    expect_rejection(
        "Factory capacity below production",
        """
        UPDATE factories
        SET annual_capacity_pairs = 1
        WHERE factory_id = 1
        """
    )

    expect_rejection(
        "Inspection outside production period",
        """
        UPDATE quality_tests
        SET tested_at = '2020-01-01 12:00:00'
        WHERE run_id = 1 AND test_sequence = 1
        """
    )

    expect_rejection(
        "Inspection sample exceeds run quantity",
        """
        UPDATE quality_tests
        SET sample_size_pairs = 999999
        WHERE run_id = 1 AND test_sequence = 1
        """
    )

    completed_test = connection.execute("""
        SELECT run_id, test_sequence, quality_grade
        FROM quality_tests
        WHERE quality_grade IS NOT NULL
        LIMIT 1
    """).fetchone()

    wrong_grade = "C" if completed_test[2] != "C" else "A"

    expect_rejection(
        "Grade inconsistent with measurements",
        """
        UPDATE quality_tests
        SET quality_grade = ?
        WHERE run_id = ? AND test_sequence = ?
        """,
        (wrong_grade, completed_test[0], completed_test[1])
    )

    expect_rejection(
        "Rubber required for outsole",
        """
        UPDATE model_materials
        SET material_id = 1
        WHERE model_id = 1 AND component = 'Outsole'
        """
    )


    # ========================================================
    # 15. Final integrity checks
    # ========================================================

    integrity = [
        row[0]
        for row in connection.execute("PRAGMA integrity_check")
    ]

    foreign_key_errors = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if integrity != ["ok"]:
        raise RuntimeError(f"Integrity check failed: {integrity}")

    if foreign_key_errors:
        raise RuntimeError("Foreign-key violations detected.")

    for table, expected in expected_counts.items():
        if scalar(f"SELECT COUNT(*) FROM {table}") != expected:
            raise RuntimeError("Constraint tests changed the dataset.")

    if scalar("SELECT COUNT(*) FROM business_rule_violations"):
        raise RuntimeError("Business-rule validation failed.")

    print("\nFINAL VALIDATION\n")
    print("Integrity check: ok")
    print("Foreign-key violations: 0")
    print("Business-rule violations: 0")
    print("Quality tests: 8 columns and 3,030 rows")
    print("Composite primary keys: 2")
    print("All four measurement types represented")
    print("Deliberate missing and duplicate data retained")
    print("All 17 invalid-operation tests rejected")


    # ========================================================
    # 16. Example retrieval — exclude repeated ingestion
    # ========================================================

    print("\nQUALITY GRADES IN STORED RECORDS\n")

    for grade, count in connection.execute("""
        SELECT COALESCE(quality_grade, 'Incomplete'), COUNT(*)
        FROM quality_tests
        GROUP BY quality_grade
        ORDER BY CASE quality_grade
            WHEN 'A' THEN 1
            WHEN 'B' THEN 2
            WHEN 'C' THEN 3
            ELSE 4
        END
    """):
        print(f"{grade}: {count:,}")

    print("\nOBSERVED SAMPLE DEFECT RATES BY FACTORY\n")

    # Distinct events avoid inflating results through duplicate ingestion.
    # These are inspected-sample rates, not whole-factory defect estimates.
    results = connection.execute("""
        WITH distinct_tests AS (
            SELECT DISTINCT
                   run_id, tested_at, sample_size_pairs,
                   defect_count, sole_thickness_mm,
                   quality_grade, notes
            FROM quality_tests
        )
        SELECT f.factory_name,
               SUM(q.defect_count) AS defective_pairs,
               SUM(q.sample_size_pairs) AS inspected_pairs,
               ROUND(
                   100.0 * SUM(q.defect_count)
                   / SUM(q.sample_size_pairs), 2
               ) AS observed_defect_percent
        FROM distinct_tests q
        JOIN production_runs r ON r.run_id = q.run_id
        JOIN factories f ON f.factory_id = r.factory_id
        GROUP BY f.factory_id
        ORDER BY observed_defect_percent DESC
    """).fetchall()

    for name, defects, inspected, percentage in results:
        print(
            f"{name}: {defects:,}/{inspected:,} "
            f"sample observations ({percentage:.2f}%)"
        )

    connection.commit()

finally:
    connection.close()


# ============================================================
# 17. Verify the saved database and download only the DB
# ============================================================

with sqlite3.connect(DATABASE_PATH) as saved_connection:
    saved_connection.execute("PRAGMA foreign_keys = ON")

    saved_count = saved_connection.execute(
        "SELECT COUNT(*) FROM quality_tests"
    ).fetchone()[0]

    saved_integrity = saved_connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    saved_foreign_key_errors = saved_connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if (
        saved_count != 3030
        or saved_integrity != "ok"
        or saved_foreign_key_errors
    ):
        raise RuntimeError("Saved database verification failed.")

print("\nDatabase saved and reopened successfully.")
print("Downloading shoe_quality.db ...")

files.download(str(DATABASE_PATH))