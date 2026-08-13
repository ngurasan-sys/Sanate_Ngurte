import { performance } from 'perf_hooks';

const positions = Array.from({ length: 1000 }, (_, i) => ({
  id: i,
  status: i % 2 === 0 ? 'ACTIVE' : 'CLOSED',
  qty: 100,
  ltp: 1000,
  avgPrice: 900
}));

const ITERATIONS = 1000000;

function benchmarkInline() {
  let count = 0;
  const start = performance.now();
  for (let i = 0; i < ITERATIONS; i++) {
    count += positions.filter(p => p.status === 'ACTIVE').length;
  }
  const end = performance.now();
  return { time: end - start, result: count };
}

function benchmarkMemoized() {
  let count = 0;
  const start = performance.now();
  const memoizedLength = positions.filter(p => p.status === 'ACTIVE').length;
  for (let i = 0; i < ITERATIONS; i++) {
    count += memoizedLength;
  }
  const end = performance.now();
  return { time: end - start, result: count };
}

console.log("Running inline array filtering benchmark...");
const inlineResult = benchmarkInline();
console.log(`Inline: ${inlineResult.time.toFixed(2)}ms`);

console.log("Running memoized array filtering benchmark...");
const memoizedResult = benchmarkMemoized();
console.log(`Memoized: ${memoizedResult.time.toFixed(2)}ms`);

console.log(`Improvement: ${(inlineResult.time / memoizedResult.time).toFixed(2)}x faster`);
