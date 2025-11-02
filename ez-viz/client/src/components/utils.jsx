export function formatDuration(ms) {
    if (!ms) return '0ms';
    if (ms < 1) return `${(ms * 1000).toFixed(0)}µs`;
    if (ms < 1000) return `${ms.toFixed(2)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
}

export function getStatusText(test) {
    if (test.failed) return '✗ FAILED';
    if (test.forced) return '⚠ FORCED';
    return '✓ PASSED';
}