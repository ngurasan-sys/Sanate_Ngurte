import re

with open('frontend/src/views/TrendingOiCrossover.tsx', 'r') as f:
    content = f.read()

# Fix the broken replacement
content = content.replace("tickFormatter={(val) => { const d = new Date(val); return ; }}",
                          "tickFormatter={(val) => { const d = new Date(val); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`; }}")

with open('frontend/src/views/TrendingOiCrossover.tsx', 'w') as f:
    f.write(content)
