# Versioned releases

Use `vMAJOR.MINOR.PATCH`, or `vMAJOR.MINOR.PATCH-preview.N` for previews. Tags identify the tested commit; package metadata describes the app version. Never move a published tag or replace an existing asset.

1. Merge changes and wait for the exact commit's push CI to pass.
2. Run **Prepare source release** in Actions with the chosen version. It refuses pending/failed CI and has read-only permissions: it cannot tag or publish.
3. Download the artifact; verify `SHA256SUMS` (`shasum -a 256 -c SHA256SUMS` on macOS, `sha256sum -c SHA256SUMS` on Linux), inspect provenance and amend release notes with changes/limitations.
4. Create a GitHub release draft targeting the provenance commit, attach the archive and manifest, review readiness, then publish. This is source code, not an installer. Do not include configs, credentials, user data or dependency directories.
5. Roll back by returning users to the previous version and its saved artifacts; don't overwrite assets or rewrite history.

Local preparation after tests: `python3 scripts/prepare-release.py --version v0.1.0-preview.2 --output ../source-release`. Existing output directories are rejected. Local preparation does not certify CI or application behavior.

## Mac Apple Silicon installer

Run **Build unsigned Mac preview** manually. The Mac arm64 runner uses a clean build virtual environment, installs declared requirements and the existing PyInstaller build tool, records resolved dependencies, runs tests and the npm high-severity audit, builds the bundled backend/app, checks DMG integrity and starts the packaged backend in a disposable HOME. Failed steps prevent artifact upload. Artifacts include hashes, source commit and limitations; no automatic public release occurs. Python requirements are currently ranges, so recorded resolution is provenance, not a promise of bit-for-bit reproducibility. Review the app interactively on a clean Mac before publishing a new preview. Signing remains separate and needs your own Apple Developer resources.
