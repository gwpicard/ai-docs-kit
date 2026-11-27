# Contributing

ai-docs-kit uses the Developer Certificate of Origin (DCO) instead of a contributor license agreement. By signing off a pull request, you certify that you wrote the change or have the right to submit it under the project's license. The full text is at <https://developercertificate.org>.

## Pull requests

Nothing is committed directly to `main`. Every change arrives through a pull request.

The pull request description must contain a sign-off line with your name and email:

```
Signed-off-by: Your Name <you@example.com>
```

This one line certifies the Developer Certificate of Origin for every commit in the pull request. Individual commits do not need a sign-off.

Signing each commit with `git commit -s` is optional. Use it if you prefer, but the check reads only the line in the pull request description.

Maintainers listed in `MAINTAINERS` are exempt, because they hold the copyright.

To check a pull request event locally:

```
python scripts/check_dco.py --pr-event event.json --maintainers MAINTAINERS
```

The script prints `signed off` or `maintainer: <login>` and exits 0, or prints the missing sign-off message and exits 1.

## Cutting a release

The first release is `0.1.0`, tagged `v0.1.0`. For each release:

1. Update the version in `pyproject.toml`, `.claude-plugin/plugin.json` and
   `__version__` in `src/ai_docs_kit/__init__.py` to the same `X.Y.Z`.
   Run `uv lock` to regenerate the project's version in `uv.lock`; do not edit
   the lockfile by hand or upgrade dependencies as part of the release.
2. Add a new top entry headed `## X.Y.Z` to `CHANGELOG.md`. Record changes to the
   surfaces in PLAN.md, including command output and exit codes, working-file
   and version formats, review readers and editable copies. Use the changelog's
   section format and mark incompatible changes `Breaking:`, with migration
   instructions. The public Python API will be documented when it lands.
3. Run `uv run python -m pytest tests/test_release_contract.py` to check version
   agreement, including rejection of a mismatched changelog heading. Run the
   project's required checks, sign off the commits with `git commit -s` and open
   a pull request. Do not push directly to `main`.
4. After the pull request is merged, the owner updates their local `main` to the
   merged commit and checks it out. On that up-to-date `main`, the owner runs
   `git tag -s vX.Y.Z -m "vX.Y.Z"`, then `git push origin vX.Y.Z`.
   For the first release, replace `X.Y.Z` with `0.1.0`.
5. The owner creates and publishes a GitHub release for that tag, using the
   matching changelog entry as its release notes. Check that the tag is on
   GitHub and the release page lists the recorded surfaces.

Tagging and publishing are the owner's post-merge steps. This process does not
publish to PyPI or a plugin marketplace.
