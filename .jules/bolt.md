## 2024-08-15 - React Component Memoization
**Learning:** Found opportunities to memoize simple stateless presentational React components like `MetricCard` and `StatusBadge` that are used very heavily across the application (e.g. 19 times in `App.tsx` alone). This prevents unnecessary re-renders of these leaf components when parent state changes.
**Action:** Use `React.memo()` for pure functional components that rely entirely on props and are rendered frequently, to skip unnecessary virtual DOM comparisons.

## 2024-08-16 - UI Leaf Component Memoization
**Learning:** Found opportunities to memoize simple stateless presentational React components like `EmptyState`, `LoadingState`, and `ErrorState` that are pure functions of their props. While they might not be rendered as often as `MetricCard`, wrapping them in `React.memo()` prevents unnecessary React VDOM diffing when parent components re-render with unrelated state changes.
**Action:** Always consider `React.memo()` for pure stateless components, especially those imported heavily across views, to prune the React component tree diffing process.
