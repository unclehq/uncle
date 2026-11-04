#!/usr/bin/env python3
"""Unit tests for housekeeping_policy and housekeeping_config."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import housekeeping_policy as P  # noqa: E402
import housekeeping_config as C  # noqa: E402

DIS = list(P.DEFAULT_DISALLOW)


def op(argv, label, verify, oid="1"):
    return {"id": oid, "op": label, "argv": argv, "expected": "x", "verify": {"argv": verify, "expect": "x"}}


def plan(*ops):
    return {"ops": list(ops)}


def allowed(argv, label, verify, disallow=DIS, ctx=None):
    return P.check_plan(plan(op(argv, label, verify)), disallow, ctx)


GOOD_DEL = (["git", "push", "origin", "--delete", "feat"], "branch-delete-merged",
            ["git", "ls-remote", "origin", "feat"])


class Patterns(unittest.TestCase):
    def m(self, pat, cmd):
        return P.match_pattern(pat, P.tokenize(cmd))

    def test_table(self):
        rows = [
            ("rm -r", ["rm", "-rf", "x"], True),
            ("rm -f", ["rm", "-rf", "x"], True),
            ("rm -r", ["rm", "-fr", "x"], True),
            ("rm -r", ["rm", "--recursive", "x"], True),
            ("rm -r", ["rm", "x"], False),
            ("git push --force", ["git", "push", "--force=yes", "o"], True),
            ("git push --force", ["git", "--no-pager", "push", "--force"], True),  # D-5: flags may precede the subcommand
            ("git push --force", ["git", "push", "origin", "--force", "main"], True),
            ("git push --force --delete", ["git", "push", "--force"], False),
            ("git push --force", ["git", "push", "-v", "--force", "-u"], True),
            ("git clean -f", ["git", "clean", "-fd"], True),
            ("git clean -fd", ["git", "clean", "-f"], False),
            ("mkfs", ["mkfs.ext4", "/dev/x"], True),
            ("dd", ["/bin/dd", "if=a"], True),
            ("gh api -X", ["gh", "api", "-X", "DELETE", "/x"], True),
            ("gh api -X", ["gh", "api", "--method", "GET", "/x"], False),
            ("git branch -D", ["git", "branch", "-D", "x"], True),
            ("git branch -D", ["git", "branch", "-d", "x"], False),
        ]
        for pat, cmd, want in rows:
            with self.subTest(pat=pat, cmd=cmd):
                self.assertEqual(self.m(pat, cmd), want)

    def test_quoted_string_form(self):
        self.assertTrue(self.m("rm -r", "rm -r 'a b'"))
        self.assertTrue(self.m("sudo", 'sudo "ls"'))

    def test_unreadable(self):
        for c in ["a | sh", "echo `x`", "echo $(x)", "a; b", "cat <<EOF", "a > b", "a && b"]:
            with self.subTest(c=c), self.assertRaises(P.Unreadable):
                P.tokenize(c)
        for c in [["--", "x"], ["A=b", "git"], [], [""], "'unterminated"]:
            with self.subTest(c=c), self.assertRaises(P.Unreadable):
                P.tokenize(c)
        with self.assertRaises(P.Unreadable):
            P.tokenize(["git", "push", "--", "x"])


class Floor(unittest.TestCase):
    def test_floor_with_empty_disallow(self):
        bad = [
            ["gh", "repo", "delete", "x"], ["gh", "repo", "archive", "x"], ["sudo", "ls"],
            ["git", "push", "--force", "origin", "main"], ["git", "push", "-f", "origin", "master"],
            ["git", "push", "--force-with-lease", "origin", "main"],
            ["git", "push", "--force-with-lease=main", "origin", "main"],
            ["git", "push", "origin", "+main"], ["git", "push", "origin", "+x:main"],
            ["git", "push", "-f"],
        ]
        for flag in ["-r", "-R", "-f", "-rf", "-fr", "-Rf", "--recursive", "--force"]:
            for t in ["/", "/*", "~", "~/", "~/*", "$HOME", "${HOME}"]:
                bad.append(["rm", flag, t])
        for argv in bad:
            with self.subTest(argv=argv):
                self.assertIsNotNone(P.floor_violation(argv))
                r = P.check_plan(plan(op(argv, "repo-rename", ["gh", "repo", "view"])), [])
                self.assertFalse(r["allow"])
                self.assertTrue(r["rule"].startswith("floor"), r)

    def test_origin_head_default(self):
        self.assertIsNotNone(P.floor_violation(["git", "push", "-f", "origin", "trunk"], {"default_branch": "trunk"}))
        self.assertIsNone(P.floor_violation(["git", "push", "-f", "origin", "feat"]))
        self.assertIsNone(P.floor_violation(["rm", "x"]))
        self.assertIsNone(P.floor_violation(["rm", "-rf", "./build"]))

    def test_floor_constant(self):
        self.assertEqual(P.FLOOR_PATTERNS, ("gh repo delete", "gh repo archive", "sudo"))
        self.assertEqual(len(P.FLOOR_DESCRIPTIONS), 4)

    def test_defaults_cover_request(self):
        for p in ["rm -r", "rm -f", "sudo", "dd", "mkfs", "chmod -R", "chown -R", "git push --force",
                  "git push -f", "git reset --hard", "git clean -f", "git filter-branch", "git branch -D",
                  "gh repo delete", "gh repo archive", "gh repo edit --visibility", "gh release delete",
                  "gh secret", "gh variable", "gh ssh-key", "gh auth", "gh api -X"]:
            self.assertIn(p, P.DEFAULT_DISALLOW)


class Mutants(unittest.TestCase):
    """Defect injection: each mutant of the policy library must be rejected by
    a named behavioural assertion; the unmutated library must pass the same one."""

    SRC = open(os.path.join(os.path.dirname(P.__file__), "housekeeping_policy.py")).read()

    def mutant(self, old, new):
        self.assertEqual(self.SRC.count(old), 1, "mutation site must be unique: %r" % old)
        mod = type(sys)("hk_policy_mutant")
        mod.__file__ = P.__file__
        exec(compile(self.SRC.replace(old, new), "mutant", "exec"), mod.__dict__)
        return mod

    def assert_killed(self, old, new, probe):
        self.assertTrue(probe(P), "probe must pass on the real library")
        self.assertFalse(probe(self.mutant(old, new)), "mutant survived: %s -> %s" % (old, new))

    def test_floor_disabled_is_killed(self):
        probe = lambda m: m.floor_violation(["gh", "repo", "delete", "x"]) is not None
        self.assert_killed('prog == "gh" and words[:2] in (["repo", "delete"]', 'prog == "gh" and words[:2] in ([]', probe)

    def test_force_push_default_branch_floor_is_killed(self):
        probe = lambda m: m.floor_violation(["git", "push", "-f", "origin", "main"]) is not None
        self.assert_killed("if force:", "if False:", probe)

    def test_flag_subset_check_is_killed(self):
        probe = lambda m: m.match_pattern("git push --force", m.tokenize(["git", "push", "origin"])) is False
        self.assert_killed("return pflags <= expanded", "return True", probe)

    def test_flag_alias_is_killed(self):
        probe = lambda m: m.match_pattern("rm -r", m.tokenize(["rm", "--recursive", "x"])) is True
        self.assert_killed("expanded |= FLAG_ALIASES.get(f, set())", "pass", probe)

    def test_subcommand_prefix_is_killed(self):
        probe = lambda m: m.match_pattern("gh repo delete", m.tokenize(["gh", "repo", "view"])) is False
        self.assert_killed("if cwords[:len(psubs)] != psubs:", "if False:", probe)

    def test_disallow_not_consulted_is_killed(self):
        # An allowlisted command refused only because the user's disallow list names it.
        pl = plan(op(["gh", "issue", "close", "5"], "issue-triage", ["gh", "issue", "view", "5"]))
        probe = lambda m: m.check_plan(pl, ["gh issue close"])["allow"] is False
        self.assertTrue(P.check_plan(pl, [])["allow"], "control: allowed without the pattern")
        old = "    if cwords[:len(psubs)] != psubs:\n        return False\n"
        self.assert_killed(old, "    return False\n", probe)


class Allowlist(unittest.TestCase):
    def test_accepts_each_op(self):
        cases = [
            (["gh", "repo", "rename", "new", "--yes"], "repo-rename", ["gh", "repo", "view", "new"]),
            (["git", "worktree", "prune"], "worktree-prune", ["git", "worktree", "list"]),
            (["git", "worktree", "remove", "../wt"], "worktree-remove", ["git", "worktree", "list", "--porcelain"]),
            (["git", "branch", "-d", "feat"], "branch-delete-merged", ["git", "branch", "--list", "feat"]),
            GOOD_DEL,
            (["gh", "label", "delete", "bug"], "label-cleanup", ["gh", "label", "list"]),
            (["gh", "issue", "edit", "5", "--add-label", "x"], "issue-triage", ["gh", "issue", "view", "5"]),
            (["gh", "issue", "edit", "5", "--remove-label=x"], "issue-triage", ["gh", "issue", "view", "5"]),
            (["gh", "issue", "close", "5", "--reason", "completed"], "issue-triage", ["gh", "issue", "view", "5"]),
            (["gh", "issue", "comment", "5", "--body", "hi"], "issue-triage", ["gh", "issue", "view", "5"]),
        ]
        for a, l, v in cases:
            with self.subTest(a=a):
                r = allowed(a, l, v)
                self.assertTrue(r["allow"], r)
                self.assertEqual(r["ops"][0]["argv"], a)

    def test_refusals(self):
        v = ["gh", "repo", "view"]
        rows = [
            (["gh", "repo", "rename", "a", "b"], "repo-rename"),                # arity
            (["gh", "repo", "rename"], "repo-rename"),                          # arity
            (["gh", "-R", "o/r", "repo", "rename", "a"], "repo-rename"),        # global option
            (["gh", "repo", "rename", "a", "--repo", "o/r"], "repo-rename"),    # unlisted flag
            (["git", "-c", "x=y", "worktree", "prune"], "worktree-prune"),
            (["git", "-C", "/", "worktree", "prune"], "worktree-prune"),
            (["git", "worktree", "remove", "--force", "w"], "worktree-remove"),
            (["git", "branch", "-D", "feat"], "branch-delete-merged"),
            (["git", "branch", "-d"], "branch-delete-merged"),
            (["git", "branch", "feat"], "branch-delete-merged"),
            (["git", "push", "origin", "--delete", "a", "b"], "branch-delete-merged"),
            (["git", "push", "upstream", "--delete", "a"], "branch-delete-merged"),
            (["git", "push", "origin", "feat"], "branch-delete-merged"),
            (["gh", "issue", "delete", "5"], "issue-triage"),
            (["gh", "issue", "edit", "5", "--title", "x"], "issue-triage"),
            (["gh", "issue", "edit", "5"], "issue-triage"),
            (["gh", "issue", "edit", "x", "--add-label", "a"], "issue-triage"),
            (["gh", "issue", "comment", "5"], "issue-triage"),
            (["gh", "issue", "close", "5", "--comment", "x"], "issue-triage"),
            (["FOO=1", "git", "worktree", "prune"], "worktree-prune"),
            (["env", "git", "worktree", "prune"], "worktree-prune"),
            (["sh", "-c", "git worktree prune"], "worktree-prune"),
            (["xargs", "rm"], "worktree-prune"),
            (["rm", "x"], "worktree-remove"),
            (["eval", "x"], "worktree-prune"),
            (["git", "worktree", "prune", "--", "x"], "worktree-prune"),
        ]
        for a, l in rows:
            with self.subTest(a=a):
                r = allowed(a, l, v)
                self.assertFalse(r["allow"], r)

    def test_label_mismatch(self):
        r = allowed(["git", "worktree", "prune"], "label-cleanup", ["git", "worktree", "list"])
        self.assertFalse(r["allow"])
        self.assertTrue(r["rule"].startswith("op-label-mismatch"))
        r = allowed(["git", "worktree", "prune"], "branch-delete-merged", ["git", "worktree", "list"])
        self.assertFalse(r["allow"])

    def test_no_shape(self):
        r = allowed(["ls", "-l"], "repo-rename", ["gh", "repo", "view"])
        self.assertTrue(r["rule"].startswith("not-allowlisted"))
        self.assertIn("ls -l", r["command"])

    def test_zero_op_and_schema(self):
        for p in [{"ops": []}, [], {}, {"ops": "x"}]:
            self.assertFalse(P.check_plan(p, DIS)["allow"])
        o = op(["git", "worktree", "prune"], "worktree-prune", ["git", "worktree", "list"])
        self.assertFalse(P.check_plan(plan(o, dict(o)), DIS)["allow"])
        bad = dict(o)
        del bad["expected"]
        self.assertFalse(P.check_plan(plan(bad), DIS)["allow"])

    def test_disallow_beats_allowlist(self):
        r = allowed(["git", "worktree", "prune"], "worktree-prune", ["git", "worktree", "list"],
                    disallow=["git worktree prune"])
        self.assertFalse(r["allow"])
        self.assertTrue(r["rule"].startswith("disallow"))

    def test_one_bad_op_refuses_whole_plan(self):
        good = op(["git", "worktree", "prune"], "worktree-prune", ["git", "worktree", "list"], "1")
        bad = op(["sudo", "x"], "worktree-prune", ["git", "worktree", "list"], "2")
        r = P.check_plan(plan(good, bad), DIS)
        self.assertFalse(r["allow"])
        self.assertEqual(r["op_id"], "2")

    def test_display_escapes(self):
        s = P.display_argv(["a\nb", "c\x1bd"])
        self.assertNotIn("\n", s)
        self.assertNotIn("\x1b", s)
        self.assertIn("\\n", s)
        self.assertIn("\\x1b", s)


class RemoteDelete(unittest.TestCase):
    def test_protected(self):
        for b in ["main", "master", "HEAD", "refs/heads/main", "trunk", "cur"]:
            with self.subTest(b=b):
                r = allowed(["git", "push", "origin", "--delete", b], "branch-delete-merged",
                            ["git", "ls-remote", "origin", b], ctx={"default_branch": "trunk", "current_branch": "cur"})
                self.assertFalse(r["allow"], r)
        for b in [":main", ":feat", "+feat:feat", "a:b"]:
            with self.subTest(b=b):
                self.assertFalse(allowed(["git", "push", "origin", "--delete", b], "branch-delete-merged",
                                         ["git", "ls-remote", "origin"])["allow"])
                self.assertFalse(allowed(["git", "push", "origin", b], "branch-delete-merged",
                                         ["git", "ls-remote", "origin"])["allow"])

    def test_ok_and_merged_check(self):
        self.assertTrue(allowed(*GOOD_DEL)["allow"])
        self.assertEqual(P.merged_check_argv("feat", "main"),
                         ["git", "merge-base", "--is-ancestor", "origin/feat", "origin/main"])


class Verify(unittest.TestCase):
    def test_refused(self):
        a = ["gh", "repo", "rename", "new"]
        rows = [
            ["gh", "repo", "view", "other/repo"],
            ["gh", "repo", "view", "https://github.com/o/r"],
            ["gh", "repo", "view", "--repo", "o/r"],
            ["gh", "repo", "delete", "new"],
            ["gh", "repo", "edit", "new"],
            ["git", "worktree", "list"],              # wrong verify kind for this op
            ["rm", "x"],
            ["gh", "repo", "view", "new", "--web"],
        ]
        for v in rows:
            with self.subTest(v=v):
                self.assertFalse(allowed(a, "repo-rename", v)["allow"])
        self.assertTrue(allowed(a, "repo-rename", ["gh", "repo", "view", "new", "--json", "name"])["allow"])

    def test_scope(self):
        d = ["git", "push", "origin", "--delete", "feat"]
        for v in [["git", "ls-remote", "origin", "other"], ["git", "ls-remote", "https://x/y"],
                  ["git", "ls-remote", "upstream", "feat"], ["git", "branch", "--list", "feat"]]:
            with self.subTest(v=v):
                self.assertFalse(allowed(d, "branch-delete-merged", v)["allow"])
        i = ["gh", "issue", "close", "5"]
        self.assertFalse(allowed(i, "issue-triage", ["gh", "issue", "view", "6"])["allow"])
        self.assertFalse(allowed(i, "issue-triage", ["gh", "issue", "view", "5", "--repo", "o/r"])["allow"])
        self.assertTrue(allowed(i, "issue-triage", ["gh", "issue", "view", "5"])["allow"])

    def test_verify_disallow_and_floor(self):
        a = ["git", "worktree", "prune"]
        self.assertFalse(allowed(a, "worktree-prune", ["git", "worktree", "list"], disallow=["git worktree list"])["allow"])
        self.assertFalse(allowed(a, "worktree-prune", ["sudo", "git", "worktree", "list"], disallow=[])["allow"])


class Config(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.p = os.path.join(self.d, "config")

    def test_missing_and_corrupt_fall_back(self):
        self.assertEqual(C.load(self.p), list(P.DEFAULT_DISALLOW))
        for body in ["housekeeping.disallow {bad\n", "housekeeping.disallow\n", 'housekeeping.disallow "x"\n',
                     'housekeeping.disallow ["*"]\n', "housekeeping.disallow [1]\n"]:
            with self.subTest(body=body):
                open(self.p, "w").write(body)
                self.assertEqual(C.load(self.p), list(P.DEFAULT_DISALLOW))

    def test_reject_invalid(self):
        for bad in ["", "   ", "*", "rm *", "a | b", "-rf", "FOO=1 x", "a\nb", "'x"]:
            with self.subTest(bad=bad), self.assertRaises(C.ConfigError):
                C.add(self.p, bad)
        self.assertEqual(C.load(self.p), list(P.DEFAULT_DISALLOW))
        self.assertFalse(os.path.exists(self.p))

    def test_duplicate_and_floor_equal(self):
        C.add(self.p, "foo bar")
        before = open(self.p).read()
        for bad in ["foo   bar", "sudo", "gh repo delete", "gh  repo archive"]:
            with self.subTest(bad=bad), self.assertRaises(C.ConfigError):
                C.add(self.p, bad)
        with self.assertRaises(C.ConfigError):
            C.add(self.p, "rm -r")  # default already present
        with self.assertRaises(C.ConfigError):
            C.edit(self.p, 1, "sudo")
        self.assertEqual(open(self.p).read(), before)

    def test_crud_and_reset(self):
        C.add(self.p, "foo")
        self.assertEqual(C.load(self.p)[-1], "foo")
        C.edit(self.p, len(C.load(self.p)), "foo2 --x")
        self.assertEqual(C.load(self.p)[-1], "foo2 --x")
        C.remove(self.p, len(C.load(self.p)))
        self.assertEqual(C.load(self.p), list(P.DEFAULT_DISALLOW))
        C.remove(self.p, 1)
        self.assertEqual(C.load(self.p), list(P.DEFAULT_DISALLOW)[1:])
        with self.assertRaises(C.ConfigError):
            C.remove(self.p, 999)
        C.reset(self.p)
        self.assertEqual(C.load(self.p), list(P.DEFAULT_DISALLOW))

    def test_only_key_line_changes(self):
        body = "# comment\nbuild.runner claude\n\nhousekeeping.disallow [\"foo\"]\nplan.effort high\n# tail"
        open(self.p, "w").write(body)
        C.add(self.p, "bar")
        got = open(self.p).read()
        self.assertEqual(got, "# comment\nbuild.runner claude\n\nhousekeeping.disallow [\"foo\", \"bar\"]\nplan.effort high\n# tail")
        open(self.p, "w").write("a.b 1\n# c\nz.y 2")
        C.add(self.p, "bar")
        self.assertEqual(open(self.p).read(), "a.b 1\n# c\nz.y 2\nhousekeeping.disallow %s\n" % json.dumps(list(P.DEFAULT_DISALLOW) + ["bar"]))  # missing key => defaults, then add

    def test_floor_not_stored_and_always_applies(self):
        open(self.p, "w").write("housekeeping.disallow []\n")
        self.assertEqual(C.load(self.p), [])
        eff = C.effective(self.p)
        # Oracle: the D-1 floor list written out literally, not read back from the module.
        self.assertEqual(eff, ["gh repo delete", "gh repo archive", "sudo"])
        r = P.check_plan(plan(op(["gh", "repo", "delete", "x"], "repo-rename", ["gh", "repo", "view"])), eff)
        self.assertFalse(r["allow"])
        open(self.p, "w").write("housekeeping.disallow {corrupt\n")
        self.assertFalse(P.check_plan(plan(op(["sudo", "x"], "repo-rename", ["gh", "repo", "view"])),
                                      C.effective(self.p))["allow"])

    def test_user_patterns_only_add_refusals(self):
        C.add(self.p, "git worktree prune")
        a = op(["git", "worktree", "prune"], "worktree-prune", ["git", "worktree", "list"])
        self.assertFalse(P.check_plan(plan(a), C.effective(self.p))["allow"])
        # a pattern can never permit something off the allowlist
        C.reset(self.p)
        b = op(["ls", "-l"], "repo-rename", ["gh", "repo", "view"])
        self.assertFalse(P.check_plan(plan(b), C.effective(self.p))["allow"])

    def test_cli(self):
        self.assertEqual(C.main([self.p, "add", "foo"]), 0)
        self.assertEqual(C.main([self.p, "add", "*"]), 1)
        self.assertEqual(C.main([self.p, "list"]), 0)


if __name__ == "__main__":
    unittest.main()
