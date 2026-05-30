# Roadmap

Honest forward look. Items here are candidates, not commitments — nothing is
scheduled for a specific version until it ships.

## Recently shipped

- **v0.3.0 — automatic beatgrid alignment for MP3 outputs.**
  ffmpeg's libmp3lame advances the PTS by the encoder delay (~25 ms at
  44.1 kHz) but leaves the LAME info-tag delay subfield empty. Rekordbox
  can't compensate, so the grid visibly drifted ahead of the audio for
  FLAC → MP3 conversions. The converter now probes the encoded output's
  `start_time` and shifts every `TEMPO.Inizio` and `POSITION_MARK.Start/End`
  by that amount. Zero-op for FLAC/AIFF (lossless = no encoder delay) and
  for MP3 → MP3 passthrough (byte-identical to source).
- **v0.2.2 — Location URIs are absolute.** Fixed a relative-`-o` bug that
  produced unimportable XML; details in commit history.
- **v0.2.1 — explicit `[tool.setuptools] py-modules`** so the multi-module
  layout actually packages.

## Candidate: direct Rekordbox library writes (`--write-library`)

**Goal.** Skip the manual "export XML → run converter → re-enable rekordbox xml
view → drag tracks into collection" dance. Converted tracks would appear in
the user's live Rekordbox library directly, with no import step.

**Approach.** Add an opt-in `--write-library` flag that uses
[pyrekordbox](https://github.com/dylanljones/pyrekordbox) to unlock the
SQLCipher-encrypted `master.db` and insert tracks + playlist into the live
library. Default behavior stays the safe XML-export path; nothing about the
current flow changes.

**Why it's not default.** Direct database writes carry real risk:
- Library corruption is one-way without a backup.
- Rekordbox tightens encryption and rearranges schema between major versions;
  pyrekordbox lags releases by some amount.
- Rekordbox holds `master.db` open while running; concurrent writes would
  conflict.
- Users reasonably distrust a third-party tool writing to their main library.

**Safety guards before this ships.**
1. Force-backup `master.db` to a timestamped sibling file before any write.
   Refuse to proceed if the backup fails.
2. Detect a running Rekordbox process and refuse with a clear error.
3. Maintain a tested-compat allowlist of Rekordbox versions; refuse to write
   if the detected version isn't on it.
4. Print a confirmation prompt summarising what will be written, requiring
   explicit `--yes` or interactive confirmation.
5. Use a transaction so a partial write rolls back cleanly.
6. Ship behind `--write-library` AND a clearly labelled "experimental"
   note in the help text and README until it's been battle-tested.

**Risk we accept.** Even with all the guards, a sufficiently weird local
setup could still produce a broken library. The backup-first guarantee
means recovery is always `cp master.db.bak.<timestamp> master.db`, which
is acceptable.

**Not in scope (yet).** Editing ANLZ analysis files (beatgrid/cue binaries
that live alongside tracks). The XML import path doesn't need them and the
current conversion preserves sample-exact timing for FLAC/AIFF; cues line up
without ANLZ rewrites.

## Maybe later

- **`--from-library` (read-side counterpart).** Read tracks directly from
  `master.db` instead of requiring the user to export an XML first. Lower
  risk than `--write-library` since it's read-only; same dependency footprint
  (pyrekordbox + SQLCipher), so probably ships together if at all.
- **Tiny real-audio integration fixture.** A ~50KB WAV in `tests/fixtures/`
  to drive one true end-to-end run through `convert_track` + ffmpeg. Lifts
  coverage past 90% and catches ffmpeg-version regressions pure mocks miss.
  Cost: CI needs `apt install ffmpeg`; the fixture lives in the repo.
- **CHANGELOG.md.** Once releases get more frequent than "whenever I
  remember", a human-curated changelog helps users decide whether to upgrade.

## Explicitly out of scope

- **Plugin architecture for formats.** Three formats, all stable. Premature.
- **Async/await rewrite.** ffmpeg subprocess is the bottleneck; threads are
  the right shape.
- **Cloud / streaming integrations.** Different product.
