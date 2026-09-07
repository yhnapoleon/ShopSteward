# Third-party attribution

`src/shopsteward_agent/memory/hermes_policy.py` adapts entry mutation semantics from
NousResearch/hermes-agent commit `693641aa8b4359c602283bdbbc14041e03bc47bc`,
`tools/memory_tool_store.py`: `_find_unique_match`, `MemoryStore.add`, `_edit`,
and `apply_batch`. Source: https://github.com/NousResearch/hermes-agent/tree/693641aa8b4359c602283bdbbc14041e03bc47bc

Changes: pure copied-list policy; target names USER/NOTES; exceptions; no disk,
global session, frozen prompts, approval machinery, or threat-pattern module.
Database ownership, provenance, revisions, authorization and content eligibility
are the integrating application's responsibility.

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
