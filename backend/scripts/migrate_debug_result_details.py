from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).resolve().parents[1] / "ovrin.db"


def column_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def ensure_column(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> None:
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} INTEGER")
        print(f"Added {table_name}.{column_name}")


def get_worst_result_pair(
    cursor: sqlite3.Cursor,
    baseline_run_id: int,
    current_run_id: int,
) -> tuple[int | None, int | None, int | None]:
    cursor.execute(
        "SELECT id, test_case_id, wer, cer FROM evaluation_results WHERE run_id = ?",
        (baseline_run_id,),
    )
    baseline_rows = cursor.fetchall()

    cursor.execute(
        "SELECT id, test_case_id, wer, cer FROM evaluation_results WHERE run_id = ?",
        (current_run_id,),
    )
    current_rows = cursor.fetchall()

    if not current_rows:
        return None, None, None

    baseline_by_test_case_id = {row[1]: row for row in baseline_rows}

    def priority(current_row: tuple) -> tuple[float, float, float]:
        _, test_case_id, current_wer, current_cer = current_row
        baseline_row = baseline_by_test_case_id.get(test_case_id)

        current_wer_value = current_wer if current_wer is not None else -1.0
        current_cer_value = current_cer if current_cer is not None else -1.0

        if baseline_row and baseline_row[2] is not None and current_wer is not None:
            wer_delta = current_wer - baseline_row[2]
        else:
            wer_delta = current_wer_value

        return wer_delta, current_wer_value, current_cer_value

    current_result = max(current_rows, key=priority)
    current_result_id, test_case_id, _, _ = current_result
    baseline_result = baseline_by_test_case_id.get(test_case_id)
    baseline_result_id = baseline_result[0] if baseline_result else None

    return baseline_result_id, current_result_id, test_case_id


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    ensure_column(cursor, "debug_cases", "test_case_id")
    ensure_column(cursor, "debug_cases", "baseline_result_id")
    ensure_column(cursor, "debug_cases", "current_result_id")

    cursor.execute(
        """
        SELECT id, baseline_run_id, current_run_id
        FROM debug_cases
        WHERE baseline_run_id IS NOT NULL
          AND current_run_id IS NOT NULL
        """
    )

    debug_cases = cursor.fetchall()

    for debug_case_id, baseline_run_id, current_run_id in debug_cases:
        baseline_result_id, current_result_id, test_case_id = get_worst_result_pair(
            cursor=cursor,
            baseline_run_id=baseline_run_id,
            current_run_id=current_run_id,
        )

        cursor.execute(
            """
            UPDATE debug_cases
            SET baseline_result_id = COALESCE(baseline_result_id, ?),
                current_result_id = COALESCE(current_result_id, ?),
                test_case_id = COALESCE(test_case_id, ?)
            WHERE id = ?
            """,
            (baseline_result_id, current_result_id, test_case_id, debug_case_id),
        )

    connection.commit()
    connection.close()

    print("Debug result details migration complete.")


if __name__ == "__main__":
    main()
