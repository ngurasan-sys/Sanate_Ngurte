## 2024-08-15 - React Component Memoization
**Learning:** Found opportunities to memoize simple stateless presentational React components like `MetricCard` and `StatusBadge` that are used very heavily across the application (e.g. 19 times in `App.tsx` alone). This prevents unnecessary re-renders of these leaf components when parent state changes.
**Action:** Use `React.memo()` for pure functional components that rely entirely on props and are rendered frequently, to skip unnecessary virtual DOM comparisons.
