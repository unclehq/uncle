"""Run independent gate integration groups without duplicating other suites."""
import os
import sys
import cpu_jobs
from suite_split import expand
from process_tree import bash_executable
from shell_suites import run_commands

def gate_commands(script):
    """The independent gate groups as named commands, for this runner and for all_suites.py's single pool."""
    completion_only = os.environ.get('UNCLE_TEST_COMPLETION_ONLY') == '1'
    first = 10 if completion_only else 1
    names = ['diff-review', 'green-check', 'baseline', 'application-review',
             'repair', 'verification-integrity', 'document-budgets', 'compaction',
             'review-cache', 'delivery', 'delivery-resume', 'waivers',
             'waiver-integrity', 'driver-syntax']
    commands = {}
    def add(name, group):
        # A group the table splits runs as several pieces, each taking its share of the group's cases.
        commands.update(expand(name, 'shell', script, [bash_executable(), script, '--group', str(group)], ['--group', str(group)]))
    for group in range(first, 15):
        add(f'gates-{names[group - 1]}', group)
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
            add(f'gates-{name}', group)
    return commands


if __name__ == '__main__':
    commands = gate_commands(sys.argv[1])
    # Up to 16 workers by default (32 at most, WORKFLOW_TEST_JOBS). Measured at 32 workers the suite was no faster and less
    # stable; the measurement below was taken when the default was one worker per available core, not one per group: measured
    # directly, "one thread per group" made this slower, not faster, once
    # the rebalance above grew the group count past this machine's core
    # count (22 groups on 14 cores: 429% average CPU and 3:06 wall-clock,
    # against 783% and 1:35 at a 14-worker cap on the same groups). Each
    # group is a real subprocess doing real CPU and disk work -- git init, a
    # driver run against a scratch repo -- so past the core count, more
    # concurrent workers means more contention switching between them, not
    # more throughput. Capped at the group count only so a future, smaller
    # rebalance still runs in one wave instead of an unnecessary queue.
    jobs = int(os.environ.get('WORKFLOW_TEST_JOBS') or min(len(commands), cpu_jobs.default_jobs()))
    raise SystemExit(run_commands(jobs, commands))
