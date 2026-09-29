# Liar paradox: an optional semantic profile

This note preserves the repository's original distinction-based treatment of
the liar paradox. It is a named philosophical hypothesis, not a universal
Onto4 rule.

## Canonical typed profile

Self-reference is not automatically a category error. In an ordinary typed
semantic profile:

```text
a = a                         -> T
SelfReference(a)              -> T, F or U depending on the predicate/context
```

The liar sentence

```text
L := "This statement is false"
```

requires a truth predicate whose domain, typing and fixed-point policy are
specified by the selected `SemanticProfile`. If that profile admits the truth
predicate and a fixed-point construction, the result is handled by that
profile's logic; it is not silently converted to `C` merely because the
sentence refers to itself.

`C` is appropriate only when the checked formalization fails a concrete
semantic requirement—for example, when the selected profile explicitly
forbids the truth predicate's self-application or leaves its argument type
undefined. The diagnostic must name that failed requirement.

## Historical distinction profile

The earlier essay proposed an additional axiom:

```text
compare(a, b) is meaningful iff a != b
```

Under that **DistinctionProfile**, `compare(L, L)` is inadmissible and the
formalization may project to `C`. This is a coherent optional profile for
exploring one philosophical view, but it must be named and pinned in the
`ContextFrame`; it must not be presented as the base Onto4 semantics.

The distinction profile therefore explains one possible diagnosis of the liar
paradox while the canonical typed profile keeps ordinary reflexive equality and
self-reference available when their semantic contracts permit them.
