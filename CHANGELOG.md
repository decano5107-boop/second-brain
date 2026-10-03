# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- The board is now written to `maps/_BOARD.md` (was `maps/_NOW.md`). An old `_NOW.md` is left
  in place and can be deleted by hand.
- `lookup` ships English stopwords and acknowledgements only. Other languages are added through
  `lookup.extra_stopwords` and the new `lookup.extra_acknowledgements`.

## [0.1.0] - 2026-09-30

### Added
- Initial public release.
