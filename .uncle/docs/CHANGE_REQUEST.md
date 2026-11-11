# Change Request

Issue 252

Seeded from [unclehq/uncle#252](https://github.com/unclehq/uncle/issues/252).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Asked for a preview link, the hosted chat agent says previews aren't possible: no rule tells her a hosted build ends with a link

## Motivation

## Summary

When a person asks the hosted build Employee for a preview link, she says she can't make one. Nothing in her chat instructions says a hosted build ends with a link to the running app. The only preview rules, in `skills/uncle-build/SKILL.md`, cover what to do with a `Preview:` line after a build has already run. So before a build she says her work "always goes through a GitHub pull request". With no repository, no build starts and no link can exist.

## What happens today

**Live test, 2026-11-11 17:29 UTC,** on a fresh hire running release revision 41. The message was:

> Build a one-page website in plain HTML (no framework) that shows the heading "Preview link test" and a short paragraph. I don't need a pull request yet. I want to see it running first, so please send me the preview link to the running app.

The reply came after 8 seconds, with no tool calls:

> I can build this and open a pull request for it — that's how I work. I don't have a way to run or host a live preview app outside of that; my process always goes through a GitHub pull request, not a standalone running preview link.
>
> Once the PR is open, you'll be able to review the file directly on GitHub (it'll render fine as a static HTML file preview there), or pull the branch locally to open it in a browser.
>
> So: which repository should I work in? If it's a brand-new site, please create an empty repository first and give me its name, and I'll build the one-page HTML file and open the PR.

Three things are wrong:

1. She says previews don't exist. The preview path (#206–#210, #235) exists to give exactly this person a link.
2. Even for the pull-request path, she offers only "review the file on GitHub" or "pull the branch locally". She never mentions that the build ends with a link.
3. The listing promises "Builds a working web app from one sentence", but with no repository she won't start.

## Code paths (main `b27e23c`)

Blame is `git blame`.

| Where | What it does | Last changed in |
|---|---|---|
| `skills/uncle-build/SKILL.md:3` | The skill's description: "How to report the preview link **after** running the uncle build script in chat." | `274a636` 2026-11-09 (#210, PR #220) |
| `skills/uncle-build/SKILL.md:8-16` | Rules 1–5 cover only relaying a `Preview:` line already in the build output. None tells the agent that a hosted build ends with a link, that it may offer one, or what to answer when asked for a preview before a build. | `274a636` 2026-11-09 (#210, PR #220) |
| `skills/uncle-build/SKILL.md:17` | Rule 6: the warning-page note. It also applies only after a build. | `72902f2` 2026-11-10 (#235, PR #241) |
| `scripts/tests/chat-skill-test.py:17-31` (`REQUIRED`) | Pattern checks for the rules above (`preview-line`, `why-when-no-link`, `warning-page`, and others). None checks that the agent offers a preview. | PR #220, PR #241 |
| The release's own instructions (not in this repository) | Evidently say every build ends in a pull request: she quoted that as "that's how I work". | |

## Fix

1. **Tell her the link exists.** Add a rule at the top of `skills/uncle-build/SKILL.md`: a finished hosted build ends with a link to the running app, valid for up to an hour. When someone asks to see the app running, say a build gives them that link, and never say previews aren't possible. Make the same change in the release's instructions, so the two don't contradict each other.
2. **Mention the link on the pull-request path too.** When she describes what a build delivers, say "a pull request and a link to try the app", not only the pull request.
3. **A build with no repository. Decision needed.**
   - (a) Recommended: build in the sandbox without a repository, end with the link, and offer a pull request once the person names a repository. This matches "Builds a working web app from one sentence".
   - (b) Ask for a repository first, but say the build will end with a link.
4. **Publish** a release with the new instructions.

## Tests

- `scripts/tests/chat-skill-test.py`: add an `offer-preview` pattern requiring the new rule, and a bad variant without it that must fail.
- A chat-level check against the published release: ask for "a preview link to the running app" with no repository. The reply must not say previews are impossible. Under 3(a), she starts a build. Under 3(b), she asks for a repository and says the build ends with a link.

## Checks after the fix

1. Send the message above to a fresh hire. She doesn't say she can't make a preview link.
2. Under 3(a), the run ends with a clickable `Preview:` link that opens the page (needs the release grant, #251).

## Related

#206, #207, #208, #209, #210, #235, #236, and #251 (the release grant and build script).

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
