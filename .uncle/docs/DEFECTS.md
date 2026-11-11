# Defects

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** The checklist row has no depends_on and no exclusive resources, and its action requires an external hosted release. No hosted URL or credentials were supplied to this worker.
- **Expected result:** The agent explains the preview is valid up to an hour, builds without a repository, and offers a PR only after a repository is named and publishing is authorized. The reply has a clickable Preview: link and expiry matching the build output, the link shows the running counter app, and the agent never says previews are impossible or promises automatic tab opening.
- **Actual result:** Not executed. There is no hosted release, no grant #251 and no hosted chat session to start a hire in.
