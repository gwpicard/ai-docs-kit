# Ship

Do not stop and do not ask the person anything in this stage unless they have not said who the version goes to.

1. Confirm that the latest version has a look record with no open error. If not, the look stage has already used its two fix rounds, so report what remains instead of sending.
2. Give the person the paths: the PDF, the editable copy (`<name>.docx` or `<name>.pptx`) and the version folder. Say how many pages were looked at, how many warnings remain and in which sections.
3. When the version goes to someone, mark it with `ai-docs-kit sent <version> --to <who>`. This is the only way a version is marked sent; do not edit the version's records by hand. The command refuses a version with an open error or an unlooked page. Do not use `--force` unless the person says so and gives a reason, and then pass it as `--reason`.
4. Tell the person that a reviewed copy of this version comes back through the `review` skill, which compares it with the version marked sent.
