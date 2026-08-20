## 2024-08-15 - React Component Memoization
**Learning:** Found opportunities to memoize simple stateless presentational React components like `MetricCard` and `StatusBadge` that are used very heavily across the application (e.g. 19 times in `App.tsx` alone). This prevents unnecessary re-renders of these leaf components when parent state changes.
**Action:** Use `React.memo()` for pure functional components that rely entirely on props and are rendered frequently, to skip unnecessary virtual DOM comparisons.

## $(date +%Y-%m-%d) - O(N) Array Iteration Optimization on the Hot Path
**Learning:** Using `hasattr()` in a tight loop inside high-frequency processing paths like the `OrderFlowEngine` creates significant CPU overhead compared to simple `try/except AttributeError`. Also, calculating attributes iteratively where values are already available in identical arrays creates unnecessary O(N*M) loop nesting.
**Action:** Always favor EAFP (`try/except`) over LBYL (`hasattr`) for property extraction in tight Python loops. If an analysis function is repeatedly iterating over the same arrays for varying parameters (like depth imbalance calculation for levels 1, 3, 5, 10...), replace it with a single O(N) pass that calculates and extracts all necessary values concurrently.
