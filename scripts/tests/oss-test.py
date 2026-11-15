#!/usr/bin/env python3
"""Unit tests for scripts/lib/oss.py and the --oss prompt appendix."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
LIB = os.path.join(ROOT, "scripts", "lib", "oss.py")
spec = importlib.util.spec_from_file_location("oss", LIB)
oss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oss)

GIT = ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]


def repo(files):
    d = tempfile.mkdtemp()
    subprocess.run(GIT + ["init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "config", "commit.gpgsign", "false"], check=True)
    subprocess.run(["git", "-C", d, "config", "tag.gpgsign", "false"], check=True)
    for rel, text in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)
    return d


def cli(*args):
    return subprocess.run([sys.executable, "-I", LIB] + list(args),
                          capture_output=True, text=True)


class Discovery(unittest.TestCase):
    def test_sources_and_kinds(self):
        d = repo({"CONTRIBUTING.md": "# Hi\nAll commits need Signed-off-by.\n"
                  "Commit message must follow Conventional Commits.\n"
                  "PR title must include an issue number.\n"})
        g = oss.discover(d)["guidelines"]
        self.assertEqual({(e["kind"], e["source"]) for e in g},
                         {("dco", "CONTRIBUTING.md:2"),
                          ("commit-format", "CONTRIBUTING.md:3"),
                          ("pr-title-format", "CONTRIBUTING.md:4")})
        self.assertTrue(oss.dco_required(g))
        self.assertEqual(len(oss.commit_format(g)), 1)
        self.assertEqual(len(oss.pr_title_format(g)), 1)

    def test_empty_fixture_reports_unknown(self):
        r = oss.discover(repo({"README.md": "x\n"}))
        self.assertEqual(r["guidelines"], [])
        self.assertEqual(oss.ai_policy(r["guidelines"]), "unknown")
        self.assertIn("no contributing guidance", r["unknown"][0]["reason"])

    def test_symlink_outside_root_unread(self):
        out = tempfile.mkdtemp()
        with open(os.path.join(out, "x.md"), "w") as f:
            f.write("SECRET-MARKER AI-generated code is not allowed.\n")
        d = repo({})
        os.symlink(os.path.join(out, "x.md"), os.path.join(d, "CONTRIBUTING.md"))
        r = oss.discover(d)
        self.assertEqual(r["guidelines"], [])
        self.assertEqual(r["unknown"][0]["path"], "CONTRIBUTING.md")
        self.assertNotIn("SECRET-MARKER", json.dumps(r))

    def test_symlink_inside_root_read(self):
        d = repo({"docs/real.md": "Contributions must be signed-off-by the author.\n"})
        os.symlink(os.path.join(d, "docs", "real.md"), os.path.join(d, "CONTRIBUTING.md"))
        self.assertTrue(oss.dco_required(oss.discover(d)["guidelines"]))


class Policy(unittest.TestCase):
    def kinds(self, text):
        return oss.ai_policy(oss.discover(repo({"CONTRIBUTING.md": text}))["guidelines"])

    def test_prohibited(self):
        self.assertEqual(self.kinds("AI-generated code is not allowed.\n"), "prohibited")
        self.assertEqual(self.kinds("We do not accept LLM generated patches.\n"), "prohibited")

    def test_prohibition_beats_permissive(self):
        d = repo({"CONTRIBUTING.md": "AI-assisted contributions are welcome.\n",
                  "AI_POLICY.md": "AI-generated code is prohibited.\n"})
        self.assertEqual(oss.ai_policy(oss.discover(d)["guidelines"]), "prohibited")
        r = cli("check-publish", "--root", d)
        self.assertEqual(r.returncode, 3)
        self.assertIn("AI_POLICY.md:1", r.stderr)

    def test_disclose_allow_silent(self):
        self.assertEqual(self.kinds("You must disclose AI assistance.\n"), "disclose")
        self.assertEqual(self.kinds("AI-assisted contributions are welcome.\n"), "allowed")
        self.assertEqual(self.kinds("Please write tests.\n"), "unknown")
        self.assertEqual(cli("check-publish", "--root",
                             repo({"CONTRIBUTING.md": "Please write tests.\n"})).returncode, 0)


class Claimable(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(oss.claimable({"state": "open", "labels": [{"name": "bug"}]}), (True, []))
        ok, why = oss.claimable({"state": "closed"})
        self.assertFalse(ok)
        ok, why = oss.claimable({"state": "open", "assignees": [{"login": "bob"}]})
        self.assertIn("bob", why[0])
        ok, why = oss.claimable({"state": "open", "labels": [{"name": "Needs Discussion"}]})
        self.assertFalse(ok)

    def test_cli_exit(self):
        p = os.path.join(tempfile.mkdtemp(), "i.json")
        with open(p, "w") as f:
            json.dump({"state": "open", "assignee": {"login": "z"}}, f)
        r = cli("claimable", "--issue", p)
        self.assertEqual(r.returncode, 4)
        self.assertIn("assigned", r.stdout)


class Rendering(unittest.TestCase):
    def test_template_filled_and_disclosure_appended(self):
        b = oss.render_pr_body("## Summary\n\n## Testing\n", "SUM", "TST")
        self.assertIn("SUM", b)
        self.assertIn("TST", b)
        self.assertIn(oss.DISCLOSURE, b)

    def test_template_with_disclosure_not_duplicated(self):
        t = "## Summary\n\n## AI disclosure\nUsed AI.\n"
        self.assertEqual(oss.render_pr_body(t, "S", "T").count("disclos"), 1)

    def test_no_template(self):
        b = oss.render_pr_body("", "SUM", "TST")
        self.assertIn("SUM", b)
        self.assertIn(oss.DISCLOSURE, b)

    def test_signoff(self):
        m = oss.signoff("feat: x", "A B", "a@b.c")
        self.assertTrue(m.endswith("\n\nSigned-off-by: A B <a@b.c>\n"))
        self.assertEqual(oss.signoff(m, "A B", "a@b.c"), m)
        t = oss.signoff("feat: x\n\nbody\n\nCo-Authored-By: C <c@d.e>\n", "A", "a@b.c")
        self.assertIn("Co-Authored-By: C <c@d.e>\nSigned-off-by: A <a@b.c>", t)


class Prompt(unittest.TestCase):
    def test_appendix_contents(self):
        t = open(os.path.join(ROOT, "prompts", "change", "oss-guidelines.md")).read()
        for needle in ("file:line", "Unknown", "inferred", "not run", "Conflicts",
                       "commit-message", "PR-title", "human approval gate"):
            self.assertIn(needle, t, needle)


class Wiring(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel)) as f:
            return f.read()

    def test_launcher_flag(self):
        u = self.read("uncle")
        self.assertIn("--oss) ", u)
        self.assertIn("UNCLE_OSS=1 UNCLE_NO_FOOTPRINT=1", u)
        self.assertIn("--no-footprint --oss --application", u)  # typo hints
        self.assertIn("|--noinput|--no-footprint|--oss)", u)
        self.assertIn("--oss (or UNCLE_OSS=1)", u)

    def resolve(self, journal, env):
        """Run change_oss_resolve from change-workflow.sh in a temp cwd."""
        src = self.read("scripts/change-workflow.sh")
        start = src.index("change_oss_resolve() {")
        fn = src[start:src.index("\n}\n", start) + 3]
        d = tempfile.mkdtemp()
        if journal is not None:
            os.makedirs(os.path.join(d, ".uncle/workflow/pr"))
            with open(os.path.join(d, ".uncle/workflow/pr/journal.json"), "w") as f:
                json.dump(journal, f)
        e = {k: v for k, v in os.environ.items() if not k.startswith("UNCLE_")}
        e.update(env)
        r = subprocess.run(["bash", "-c", fn + '\nchange_oss_resolve; echo "O=${UNCLE_OSS:-} N=${UNCLE_NO_FOOTPRINT:-}"'],
                           cwd=d, env=e, capture_output=True, text=True)
        return r

    def test_resume_precedence(self):
        r = self.resolve({"oss": True}, {})
        self.assertIn("O=1 N=1", r.stdout)
        r = self.resolve({"oss": False}, {"UNCLE_OSS": "1"})
        self.assertEqual(r.returncode, 2)
        r = self.resolve({"phase": "started"}, {"UNCLE_OSS": "1"})  # legacy journal
        self.assertEqual(r.returncode, 2)
        r = self.resolve({"phase": "started"}, {})
        self.assertIn("O= N=", r.stdout)
        r = self.resolve(None, {"UNCLE_OSS": "1"})
        self.assertIn("O=1 N=1", r.stdout)
        r = self.resolve(None, {})
        self.assertIn("O= N=", r.stdout)

    def test_appendix_bound_only_for_oss(self):
        src = self.read("scripts/change-workflow.sh")
        self.assertIn('[[ "${UNCLE_OSS:-}" != 1 ]] || oss_appendix=', src)
        self.assertIn("prompts/change/oss-guidelines.md", src)


class PublishEntry(unittest.TestCase):
    """Runs the real change-pr.sh engine in a disposable repo with recording git/gh shims."""

    def engine_code(self):
        with open(os.path.join(ROOT, "scripts", "lib", "change-pr.sh")) as f:
            src = f.read()
        a = src.index("<<'PY' || true\n", src.index("change_pr_engine()")) + len("<<'PY' || true\n")
        return src[a:src.index("\nPY\n", a)]

    def shims(self):
        b = tempfile.mkdtemp()
        log = os.path.join(b, "calls.log")
        for n in ("gh", "git-write-shim"):
            pass
        with open(os.path.join(b, "gh"), "w") as f:
            f.write('#!/bin/sh\necho "gh $*" >> "%s"\nexit 1\n' % log)
        os.chmod(os.path.join(b, "gh"), 0o755)
        real = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
        with open(os.path.join(b, "git"), "w") as f:
            f.write('#!/bin/sh\ncase "$1" in commit|push|branch|checkout|switch|tag|read-tree|update-ref|commit-tree|worktree)'
                    ' echo "git $*" >> "%s";; esac\nexec %s "$@"\n' % (log, real))
        os.chmod(os.path.join(b, "git"), 0o755)
        return b, log

    def journal(self, d, **extra):
        j = dict(version=2, owner="a" * 32, origin="", audit_hash="", reviewed_tree="", commit_tree="",
                 original_head="", intended_head="", original_branch="main", head_branch="x",
                 base_repo="", head_repo="", base_branch="", phase="prepared", url="", number=None,
                 verdict_run="", early_ref=False)
        j.update(extra)
        os.makedirs(os.path.join(d, ".uncle/workflow/pr"), exist_ok=True)
        with open(os.path.join(d, ".uncle/workflow/pr/journal.json"), "w") as f:
            json.dump(j, f)

    def run_engine(self, d, action, bindir, env_extra=None):
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
                   UNCLE_LIB_DIR=os.path.join(ROOT, "scripts", "lib"))
        env.pop("UNCLE_OSS", None)
        env.update(env_extra or {})
        return subprocess.run([sys.executable, "-I", "-c", self.engine_code(), action], cwd=d,
                              env=env, capture_output=True, text=True)

    def test_prohibition_refuses_before_any_write(self):
        d = repo({"AI_POLICY.md": "AI-generated code is not allowed.\n"})
        self.journal(d, oss=True)
        b, log = self.shims()
        r = self.run_engine(d, "handoff", b)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("AI_POLICY.md:1", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(log), open(log).read() if os.path.exists(log) else "")

    def test_environment_cannot_turn_check_on_or_off(self):
        # journal says not oss: the prohibition is not consulted even with UNCLE_OSS=1 in the environment
        d = repo({"AI_POLICY.md": "AI-generated code is not allowed.\n"})
        self.journal(d, oss=False)
        b, log = self.shims()
        r = self.run_engine(d, "handoff", b, {"UNCLE_OSS": "1"})
        self.assertNotIn("AI_POLICY.md:1", r.stdout + r.stderr)

    def test_compose_signs_off_and_fills_template(self):
        d = repo({".github/pull_request_template.md": "## Summary\n\n## Testing\n",
                  "CONTRIBUTING.md": "All commits need Signed-off-by.\n"})
        subprocess.run(["git", "-C", d, "config", "user.name", "Dev One"], check=True)
        subprocess.run(["git", "-C", d, "config", "user.email", "dev@example.invalid"], check=True)
        code = self.engine_code().split("\ntry:\n    main()")[0]
        probe = code + "\nb, m = oss_compose('SUMMARY-TEXT', 'MANUAL-TEXT', 'ORIGINAL-BODY', 'feat: x')\n" \
                       "print(json.dumps([b, m]))\n"
        env = dict(os.environ, UNCLE_LIB_DIR=os.path.join(ROOT, "scripts", "lib"))
        r = subprocess.run([sys.executable, "-I", "-c", probe, "none"], cwd=d, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        body, msg = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertIn("SUMMARY-TEXT", body)
        self.assertIn("MANUAL-TEXT", body)
        self.assertNotIn("ORIGINAL-BODY", body)
        self.assertIn(oss.DISCLOSURE, body)
        self.assertTrue(msg.rstrip().endswith("Signed-off-by: Dev One <dev@example.invalid>"))

    def test_journal_records_oss(self):
        src = open(os.path.join(ROOT, "scripts", "lib", "change-pr.sh")).read()
        self.assertIn("j['oss'] = True", src)
        self.assertLess(src.index("def handoff(j):"), src.index("oss_lib().check_publish('.')"))
        self.assertLess(src.index("oss_lib().check_publish('.')"), src.index("if j.get('phase') == 'handoff-attested'"))

    def test_readme_documents_oss(self):
        txt = open(os.path.join(ROOT, "README.md")).read()
        for needle in ("`--oss`", "implies `--no-footprint`", "file:line", "Unknown", "Signed-off-by",
                       "Forks are not automated", "wiki", "never inferred", "prohibits AI"):
            self.assertIn(needle, txt)


class GateAndFormat(unittest.TestCase):
    def test_conflicts_listed_and_missing_section_flagged(self):
        plan = "# P\n## 5. Conflicts\n- CONTRIBUTING says squash; issue says keep commits\n- none\n## 6. Next\n- x\n"
        self.assertEqual(oss.plan_conflicts(plan), ["CONTRIBUTING says squash; issue says keep commits"])
        self.assertEqual(oss.plan_conflicts("## Conflicts\n- None\n"), [])
        self.assertEqual(oss.plan_conflicts("# no section"), ["plan has no Conflicts section"])

    def test_gate_reasons_combine_plan_and_issue(self):
        d = repo({})
        r = oss.gate_reasons("## Conflicts\n- A vs B\n", {"state": "open", "assignee": "bob"}, d)
        self.assertIn("A vs B", r)
        self.assertTrue(any("assigned to bob" in x for x in r))
        self.assertEqual(oss.gate_reasons("## Conflicts\nnone\n", {"state": "open"}, d), [])

    def test_gate_cli_exit_and_wiring_before_gate(self):
        d = repo({})
        with open(os.path.join(d, "plan.md"), "w") as f:
            f.write("## Conflicts\n- A vs B\n")
        cli = os.path.join(ROOT, "scripts", "lib", "oss.py")
        r = subprocess.run([sys.executable, "-I", cli, "gate-reasons", "--plan", "plan.md", "--root", d],
                           cwd=d, capture_output=True, text=True)
        self.assertEqual(r.returncode, 4)
        self.assertIn("A vs B", r.stdout)
        src = open(os.path.join(ROOT, "scripts", "change-workflow.sh")).read()
        self.assertLess(src.index("gate-reasons"), src.index("set_state WAIT_ANALYSIS_APPROVAL", src.index("gate-reasons")))
        self.assertLess(src.index("gate-reasons"), src.index("WAIT_ANALYSIS_APPROVAL)\n"))

    def test_format_conflict_listed(self):
        e = [{"kind": "commit-format", "text": "Commit messages follow Conventional Commits", "source": "C:1"},
             {"kind": "pr-title-format", "text": "PR title must start with a ticket prefix [ABC-1]", "source": "C:2"}]
        self.assertEqual(len(oss.format_conflicts(e)), 1)
        self.assertEqual(oss.format_conflicts(e[:1]), [])

    def test_title_format_applied(self):
        e = [{"kind": "commit-format", "text": "Commit messages follow Conventional Commits", "source": "C:1"}]
        self.assertEqual(oss.apply_title_format("Fix crash on empty input", e), "fix: fix crash on empty input")
        self.assertEqual(oss.apply_title_format("Add widget", e), "feat: add widget")
        self.assertEqual(oss.apply_title_format("feat(x): ok", e), "feat(x): ok")
        self.assertEqual(oss.apply_title_format("Add widget", []), "Add widget")

    def test_defects_rejected(self):
        # defect injection: overbroad matching must not flag neutral text; a prohibition must not be missed
        self.assertEqual(oss.ai_policy(oss.discover(repo({"CONTRIBUTING.md": "Please do not break the build. Use tabs.\n"}))["guidelines"]), "unknown")
        self.assertEqual(oss.ai_policy(oss.discover(repo({"CONTRIBUTING.md": "We do not accept AI-generated patches.\n"}))["guidelines"]), "prohibited")
        self.assertFalse(oss.claimable({"state": "open", "labels": [{"name": "good first issue"}]})[0] is False)
        self.assertFalse(oss.claimable({"state": "open", "labels": ["needs discussion"]})[0])


if __name__ == "__main__":
    unittest.main()
