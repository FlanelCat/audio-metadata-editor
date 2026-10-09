# Roadmap

This is a tentative roadmap for **Audio Metadata Editor v0.2.0**. It is a living document, not a commitment to a fixed feature set or release date.

The immediate priority after the v0.1.0 public alpha release is **real-world use and observation**. New ideas, bugs, and workflow friction should be recorded here as they arise. We will evaluate and prioritize them before implementing v0.2.0.

## v0.2.0 — tentative

### Investigate audio-file attributes and write permissions

**Status:** Proposed for investigation; behavior and implementation undecided.

Explore how the application should inspect and communicate relevant audio-file attributes, particularly when an MP3 or M4B file is read-only or otherwise cannot be written.

Questions to investigate:

- How should the application display file writability and explain why a save cannot proceed?
- Should it offer an explicit user action to enable write permission for a file, where permitted?
- How should it handle Linux ownership, permission bits, ACLs, network shares, and read-only filesystems?
- How should it behave when permissions change after a directory is loaded or while editing?
- How should the application preserve original permissions and avoid unintended changes to files or directories?

**Safety and product constraints:**

- Never change file permissions automatically when loading, inspecting, or editing metadata.
- Any permission change must be explicit, understandable, and limited to the intended file(s).
- Do not attempt privilege escalation or bypass filesystem restrictions.
- Retain the existing explicit-save model and metadata-preservation guarantees.
- Investigate and document the desired behavior before deciding whether to implement it.

### Findings from everyday use

**Status:** Open for observations.

Record issues and possible improvements discovered while using v0.1.0. For each item, capture the observed behavior, the desired behavior, and—when useful—steps to reproduce it. Separate confirmed bugs from enhancement ideas before prioritizing work.

_No additional items recorded yet._

## Planning and release criteria

Before implementing v0.2.0, review the accumulated observations, decide what belongs in scope, and update this roadmap accordingly. Continue using focused changes and regression tests. Verify changes manually on Linux and through the existing CI matrix. Release only after the selected scope is tested and documented.

The v0.1.0 tag remains the baseline for the first public alpha release.
