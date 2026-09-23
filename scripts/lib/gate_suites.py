"""Run independent gate integration groups without duplicating other suites."""
import os
import sys
from process_tree import bash_executable
from shell_suites import run_commands

if __name__ == '__main__':
    completion_only = os.environ.get('UNCLE_TEST_COMPLETION_ONLY') == '1'
    first = 10 if completion_only else 1
    names = ['diff-review', 'green-check', 'baseline', 'application-review',
             'repair', 'verification-integrity', 'document-budgets', 'compaction',
             'review-cache', 'delivery', 'delivery-resume', 'waivers',
             'waiver-integrity', 'driver-syntax']
    commands = {f'gates-{names[group - 1]}': [bash_executable(), sys.argv[1], '--group', str(group)]
                for group in range(first, 15)}
    # A full-suite rebalance found several groups sized well past what most
    # take -- each group is its own process running a real driver against a
    # scratch git repo, so size tracks wall-clock directly -- and split each
    # into pieces that run concurrently instead of as one long chain.
    # verification-integrity (group 6) alone needed four: it was already
    # split once (group 15), and that first split was still big enough to
    # need splitting again on each side (groups 17 and 18). These extra
    # groups only exist in the full run, matching completion-only mode's
    # existing exclusion of every one of their parent groups (all below 10).
    extra_groups = {
        16: 'repair-2',                    # second half of group 5
        15: 'verification-integrity-2',    # second half of group 6
        17: 'verification-integrity-3',    # second half of (the original) group 6
        18: 'verification-integrity-4',    # second half of group 15
        19: 'review-cache-2',              # second half of group 9
        20: 'diff-review-2',               # second half of group 1
        21: 'compaction-2',                # second half of group 8
        22: 'application-review-2',        # second half of group 4
    }
    if not completion_only:
        for group, name in extra_groups.items():
            commands[f'gates-{name}'] = [bash_executable(), sys.argv[1], '--group', str(group)]
    # Default to one worker per available core, not one per group: measured
    # directly, "one thread per group" made this slower, not faster, once
    # the rebalance above grew the group count past this machine's core
    # count (22 groups on 14 cores: 429% average CPU and 3:06 wall-clock,
    # against 783% and 1:35 at a 14-worker cap on the same groups). Each
    # group is a real subprocess doing real CPU and disk work -- git init, a
    # driver run against a scratch repo -- so past the core count, more
    # concurrent workers means more contention switching between them, not
    # more throughput. Capped at the group count only so a future, smaller
    # rebalance still runs in one wave instead of an unnecessary queue.
    default_jobs = min(len(commands), os.cpu_count() or 8)
    raise SystemExit(run_commands(int(os.environ.get('WORKFLOW_TEST_JOBS', str(default_jobs))), commands))
