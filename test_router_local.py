import sys
sys.path.insert(0, '.')

from app.core.router import SmartRouter

router = SmartRouter()

# Test with a fetch request to see what local returns
result = router.ask('Fetch https://httpbin.org/get')
print(f'Result: {result[:500]}')