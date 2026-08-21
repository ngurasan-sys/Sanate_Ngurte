## 2024-08-15 - React Component Memoization
**Learning:** Found opportunities to memoize simple stateless presentational React components like `MetricCard` and `StatusBadge` that are used very heavily across the application (e.g. 19 times in `App.tsx` alone). This prevents unnecessary re-renders of these leaf components when parent state changes.
**Action:** Use `React.memo()` for pure functional components that rely entirely on props and are rendered frequently, to skip unnecessary virtual DOM comparisons.
## 2024-08-21 - Optimize hot path hasattr checks
**Learning:** In performance-critical loops such as tick ingestion or order flow parsing, calling `hasattr()` carries significant CPython interpreter overhead (due to internal exception handling).
**Action:** Replace `hasattr()` with `try...except AttributeError` blocks for exception-based flow control, or use `isinstance(obj, dict)` when trying to differentiate between Pydantic models and dictionaries. This micro-optimization is crucial on paths processing hundreds of thousands of ticks per second.
