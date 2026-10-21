# GitHub settings prepared for the next release

These files are local preparation. Committing or pushing them does not configure
GitHub. No workflow applies them automatically. Apply the settings separately with
`gh` during the next authorized release.

| File | Intended configuration |
| --- | --- |
| `about.json` | Repository description and DotSuite homepage |
| `topics.json` | Complete desired topic list |
| `main-ruleset.json` | Prevent deletion/force-push and require verified signed commits on `main` |
| `release-tags-ruleset.json` | Prevent deletion or updates of existing `v*` tags; allow new tags |

## Protection behavior

Signed direct pushes remain possible. These rules add no mandatory PR reviews or
required CI gate; tests continue to run on pushes. No bypass actors are configured.
An administrator can edit a ruleset separately if emergency maintenance is needed.

Tag protection covers refs, including existing version tags. It does not validate
OpenPGP tag signatures or protect release asset replacements. Continue to sign tags
and verify their signatures with GitHub, and verify all uploaded asset digests.

## Apply with the next release

Run from the repository root with a GitHub account that administers
`kareem2099/DotGhostBoard`. Inspect existing settings first and save any values that
should be preserved. The topics request replaces the entire list.

```sh
gh api repos/kareem2099/DotGhostBoard --jq '{description,homepage,topics}'
gh api repos/kareem2099/DotGhostBoard/rulesets --jq '.[] | {id,name,target,enforcement}'

gh api --method PATCH repos/kareem2099/DotGhostBoard --input .github/repository-settings/about.json
gh api --method PUT repos/kareem2099/DotGhostBoard/topics --input .github/repository-settings/topics.json
```

Publish the next signed release and confirm CI success before enabling the protection
rules. For each ruleset below, create it only if no ruleset with that name exists:

```sh
gh api --method POST repos/kareem2099/DotGhostBoard/rulesets --input .github/repository-settings/main-ruleset.json
gh api --method POST repos/kareem2099/DotGhostBoard/rulesets --input .github/repository-settings/release-tags-ruleset.json
```

If it already exists, use `PUT repos/kareem2099/DotGhostBoard/rulesets/ID` with the
same input file and the ID returned by the inspection. Update matching rulesets
instead of creating duplicates; preserve unrelated rulesets.

Before enabling signed-commit enforcement, verify that the release commit is signed
with the maintainer's registered GitHub key and verified email. Future commits must
also be signed. Keep private signing material outside the repository.

Check the applied settings and tag protections after the update:

```sh
gh api repos/kareem2099/DotGhostBoard --jq '{description,homepage,topics}'
gh api repos/kareem2099/DotGhostBoard/rules/branches/main
gh api repos/kareem2099/DotGhostBoard/rulesets --jq '.[] | {id,name,target,enforcement}'
```

Inspect each returned ruleset ID with `GET repos/kareem2099/DotGhostBoard/rulesets/ID`
and compare its conditions and rules with the corresponding local JSON file.

## Documentation

- [Repository settings API](https://docs.github.com/en/rest/repos/repos?apiVersion=2026-03-10#update-a-repository)
- [Topics API](https://docs.github.com/en/rest/repos/repos#replace-all-repository-topics)
- [Rulesets API](https://docs.github.com/en/rest/repos/rules#create-a-repository-ruleset)
