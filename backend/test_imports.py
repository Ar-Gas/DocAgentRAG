import sys
print('Python version:', sys.version)

print('\n--- Testing imports ---')
try:
    from config import API_PREFIX, DATA_DIR
    print('✓ config imported successfully')
except Exception as e:
    print('✗ config import failed:', e)
    import traceback
    traceback.print_exc()

try:
    from utils.search_query_parser import SearchQueryParser
    print('✓ search_query_parser imported successfully')
    parser = SearchQueryParser()
    result = parser.parse('"测试" -排除词 filetype:pdf')
    print('✓ Parser test passed:', result)
except Exception as e:
    print('✗ search_query_parser test failed:', e)
    import traceback
    traceback.print_exc()

try:
    from main import app
    print('✓ main.py imported successfully')
except Exception as e:
    print('✗ main.py import failed:', e)
    import traceback
    traceback.print_exc()

print('\n--- All tests completed ---')
