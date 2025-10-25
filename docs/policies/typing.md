# Typing Policy

This repository aims for precise, low-friction type safety. When adding or updating
code, keep the following guidelines in mind:

1. **Prefer protocols and structural typing for ports.** Domain ports are
   declared as `Protocol`s; concrete adapters should rely on structural typing
   rather than inheritance. This keeps runtime dependency graphs lean and avoids
   leaking adapter details into the domain layer.
2. **Validate protocol conformance via `TYPE_CHECKING` stubs.** When you need to
   guarantee that a class satisfies a protocol, add a short block such as
   ```python
   if TYPE_CHECKING:
       _stub: SomeProtocol = ConcreteImplementation(...)
   ```
   instead of subclassing the protocol. This documents intent without imposing
   runtime inheritance and gives type checkers a single place to flag
   mismatches.
3. **Use targeted casts or library typing helpers at boundaries.** When dealing
   with libraries that don’t expose precise typing (e.g., SQLAlchemy class-level
   attributes on dataclasses), use narrow `typing.cast` expressions or the
   corresponding library typing helpers to keep Pyright satisfied. Document the
   reason for each cast so future contributors understand the constraint.
4. **Keep runtime imports minimal.** If a type is only needed for static
   analysis, import it inside a `TYPE_CHECKING` block. When a type is used only
   for protocol-conformance stubs, prefer a dedicated TYPE_CHECKING block near
   the bottom of the file so those imports stay isolated from runtime code.
   This keeps startup time low and prevents accidental runtime dependencies on
   heavy libraries.

When adding new typing conventions, extend this document so the expectations
stay discoverable.
