
import sys
print('Python version:', sys.version)

print('\n--- Testing numpy directly ---')
try:
    import numpy as np
    print('✓ numpy imported successfully, version:', np.__version__)
    
    # Test basic numpy functionality
    a = np.array([1, 2, 3])
    print('✓ numpy array test passed:', a)
    
    # Test random module specifically
    print('\nTesting numpy.random...')
    from numpy import random
    print('✓ numpy.random imported')
    
    rng = random.default_rng()
    print('✓ default_rng created')
    
    val = rng.random()
    print('✓ random value generated:', val)
    
except Exception as e:
    print('✗ numpy test failed:', e)
    import traceback
    traceback.print_exc()

print('\n--- Done ---')

