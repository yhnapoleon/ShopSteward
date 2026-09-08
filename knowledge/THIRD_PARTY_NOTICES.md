# Knowledge parsing and storage provenance

The B2 parsing, chunking, parent expansion, and local blob adapter are original
ShopSteward implementations. No source code was copied or imported from IH or
RAilG. The existing research reuse manifest remains a candidate inventory; no
destination/hash entry has been changed to imply copying.

The regression scenario of hit 55 in a 60-chunk parent comes from the project's
K0 report and approved B2 plan. Tests read the frozen K0 original files without
modifying them. Canonical/gold section text is used only as a test assertion
oracle; it is never supplied to the parser or chunker as input.

Optional dependencies are imported normally, not vendored here. The following
versions and licenses were verified from installed distribution metadata during
B2 validation:

| Distribution | Tested version | License |
| --- | --- | --- |
| pypdf | 6.17.0 | BSD-3-Clause |
| python-docx | 1.2.0 | MIT |
| openpyxl | 3.1.5 | MIT |
| lxml (python-docx dependency) | 6.1.3 | BSD-3-Clause |

Redistributors must retain these distributions' own copyright and license files,
including any bundled native-library notices. This inventory does not replace
their full notices. Dependency declarations and lockfiles are maintained by the
package/controller owner. No OCR engine, tokenizer, embedding model, or remote
model client is installed or downloaded by this implementation.
