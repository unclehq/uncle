#!/usr/bin/env python3
"""The artifact graph a build runs on: which producers could start now, and may their result be kept?

Pure: no files, no processes, no model. The bash driver (stagegate.sh) walks a fixed list of stages; this module
states the same work as nodes with declared inputs, outputs and approvals, so that a scheduler can start whatever
is ready instead of whatever is next, and so that the critical path of a real build can be read off the data.

A node is ready when every artifact it reads exists and every approval it needs is recorded. A node that
`writes_source` must be gated, directly or through an input, on the approval named in SOURCE_APPROVAL: CLAUDE.md
forbids source-writing work before the updated plan is approved, and `validate()` refuses a graph that breaks it.

A speculative result is kept only if every input it read still has the hash it had when the node started.
"""
from dataclasses import dataclass
import hashlib

SOURCE_APPROVAL = 'UPDATED_PROJECT_PLAN'


@dataclass(frozen=True)
class Node:
    name: str
    inputs: tuple = ()
    outputs: tuple = ()
    approvals: tuple = ()
    writes_source: bool = False
    speculative_ok: bool = False


class GraphError(ValueError):
    pass


class Graph:
    def __init__(self, nodes, external=()):
        """`external` names artifacts that exist before any node runs (the user's brief, the project tree)."""
        self.nodes = {}
        self.producer = {}
        self.external = set(external)
        for node in nodes:
            if node.name in self.nodes:
                raise GraphError('duplicate node %s' % node.name)
            self.nodes[node.name] = node
            for out in node.outputs:
                if out in self.producer or out in self.external:
                    raise GraphError('artifact %s has two producers' % out)
                self.producer[out] = node.name
        self.validate()

    def validate(self):
        for node in self.nodes.values():
            for need in node.inputs:
                if need not in self.producer and need not in self.external:
                    raise GraphError('%s reads %s, which nothing produces' % (node.name, need))
        self.order()
        for node in self.nodes.values():
            if node.writes_source and SOURCE_APPROVAL not in self._approvals_behind(node.name):
                raise GraphError('%s writes source without the %s approval behind it' % (node.name, SOURCE_APPROVAL))

    def _approvals_behind(self, name, seen=None):
        """Every approval the node needs, directly or through the producers of its inputs."""
        seen = set() if seen is None else seen
        if name in seen:
            return set()
        seen.add(name)
        node = self.nodes[name]
        found = set(node.approvals)
        for need in node.inputs:
            if need in self.producer:
                found |= self._approvals_behind(self.producer[need], seen)
        return found

    def upstream(self, name):
        node = self.nodes[name]
        return {self.producer[n] for n in node.inputs if n in self.producer}

    def order(self):
        """Node names, producers before consumers. Raises GraphError on a cycle."""
        placed, out, remaining = set(), [], dict(self.nodes)
        while remaining:
            batch = sorted(n for n in remaining if self.upstream(n) <= placed)
            if not batch:
                raise GraphError('cycle among %s' % ', '.join(sorted(remaining)))
            for n in batch:
                out.append(n)
                placed.add(n)
                del remaining[n]
        return out

    def ready(self, artifacts, granted, started=()):
        """Names of nodes that could start now. A node needing an approval not yet granted is held back
        unless it is `speculative_ok`, which may run ahead of the approval but is adopted only after it."""
        artifacts, granted, started = set(artifacts) | self.external, set(granted), set(started)
        out = []
        for name in self.order():
            node = self.nodes[name]
            if name in started or not set(node.inputs) <= artifacts:
                continue
            if set(node.approvals) <= granted or (node.speculative_ok and not node.writes_source):
                out.append(name)
        return out

    def critical_path(self, seconds):
        """(total, [names]): the longest chain by `seconds`, a mapping of node name to duration."""
        best = {}
        for name in self.order():
            ups = self.upstream(name)
            prev = max(ups, key=lambda u: best[u][0]) if ups else None
            base = best[prev] if prev else (0.0, [])
            best[name] = (base[0] + seconds.get(name, 0.0), base[1] + [name])
        return max(best.values(), key=lambda v: v[0]) if best else (0.0, [])


def digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


class Ledger:
    """What a speculative node read when it started, so its result can be checked before it is used."""

    def __init__(self):
        self._read = {}

    def record(self, node, inputs):
        """`inputs` maps each artifact the node read to the bytes it read."""
        self._read[node] = {name: digest(data) for name, data in inputs.items()}

    def adoptable(self, node, current):
        """True only if the node was recorded and every input still has the hash it was read with."""
        was = self._read.get(node)
        if was is None or set(current) != set(was):
            return False
        return all(digest(current[name]) == h for name, h in was.items())

    def discard(self, node):
        self._read.pop(node, None)
