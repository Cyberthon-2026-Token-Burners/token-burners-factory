Feature: Fibonacci Sequence Generator
Domain: Retry Mechanisms (Math Engine)

Business Context:
Our network retry mechanism requires an exponential backoff calculator based on the Fibonacci sequence. This must be integrated into the existing mathematical utility subsystem created in the previous iteration.

Acceptance Criteria:
1. Implement a function to calculate the n-th Fibonacci number (where F(0)=0, F(1)=1).
2. Performance constraint: The calculation must execute in O(n) time. Deep recursion that causes stack overflows for values like n=50 is strictly prohibited. Use memoization or an iterative approach.
3. Type constraint: Accept only non-negative integers. Raise `ValueError` for negative indexes. Raise `TypeError` for non-integers (including booleans).