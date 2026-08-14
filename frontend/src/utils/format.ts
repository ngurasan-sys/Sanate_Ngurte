export function formatIndianNumber(num: number | null | undefined, decimals = 0): string {
  if (num === null || num === undefined || isNaN(num) || !isFinite(num)) {
    return '0';
  }
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}
