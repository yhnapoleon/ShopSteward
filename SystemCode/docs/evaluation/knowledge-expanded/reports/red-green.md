# RED/GREEN evidence

Executed with the existing repository `.venv/Scripts/python.exe` and the plan's pytest config.
No dependency files were changed.

1. Initial A1/A2/A3 contract collection failed because `tools.knowledge_corpus` did not exist.
   After implementation: 16 passed.
2. Added renderer, public alias, substantive-duplicate and full-builder tests: six missing
   implementation failures, with 16 existing tests passing. Implemented the missing interfaces.
3. Full repeat-build test exposed changing XLSX hashes: 21 passed, one failed. Investigation
   found `openpyxl` rewrote `docProps/core.xml` modified time. Normalized that internal timestamp
   as well as ZIP entry timestamps. All 22 then passed in 61.10 seconds.
4. Frozen-original mutation protection and empty-result scoring tests both failed before their
   implementations, then both passed. Frozen protection covers originals/facts/public snapshots,
   not just query text.
5. A raw public archive mutation with intact normalized text failed to be detected. Added raw
   provenance hash checking to manifest validation; the targeted test passed. All 25 passed in
   58.06 seconds before the final pilot-stage consistency check.
6. Pilot-only validity initially ended at the calendar month boundary instead of the scheduled
   sixteenth-day revision boundary. The new test failed with actual `2026-02-01` versus required
   `2026-01-16`. Pilot construction now declares the planned revision interval while emitting
   only base originals. The targeted test passed; full document bytes/gold were unaffected.

The suite uses actual temporary files and rendered documents. It covers family/source split
leakage, missing/invalid dates, reference-only quota exclusion, protected writes and traversal,
version counting, nested gold rejection, corrupted file bytes/counts, real evidence extraction,
empty and partial retrieval denominators, corpus counts, frozen rebuilds, corrupt locators,
raw/normalized public provenance, and pilot/full metadata consistency.

Final command and result are recorded in `test-result.txt`; Ruff is restricted to the owned
corpus tools and unit test. The actual corpus/evaluation verification reports are separate
from pytest fixture results and contain no claimed retrieval score.

Subsequent authorized integration changes:

7. Four relation-intake tests initially failed for missing explicit metadata/condition handling
   and refused annotation migration. They passed after adding bounded scalar conditions,
   exact-source quote spans, declared SKU-to-document discovery edges and protected v1.1
   migration. False/missing states and unresolved quotes remain nonexecutable.
8. Current-Agent subset test failed before implementation, then passed. It checks that expired
   documents are excluded without changing the source documents or 300-question input.
9. Two CSV repair tests failed: the title/marker was incorrectly treated as the header, and no
   scoped format migration existed. They passed after three-column header/metadata repair and
   v1.2 migration restricted to CSV originals and their byte/hash references. Service-parser
   checks additionally verified all 183 repaired CSV versions as COMPLETE without warnings.
10. Concurrent public acquisition added files during an otherwise identical rebuild. A new
    test first failed for missing snapshot comparison and then passed after distinguishing
    additions from modified/deleted preexisting files. All modifications/deletions still fail.

The expanded suite passed 33 tests in 55.80 seconds before the final snapshot-specific test;
see `test-result.txt` for the final complete run. Questions and dates were never revised.
