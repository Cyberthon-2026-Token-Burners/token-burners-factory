Feature: Core Math Engine & Prime Validation
Domain: Cryptography Support

Business Context:
We require a new mathematical utility module to support the cryptography service's hashing algorithms. The foundational feature is strict prime number validation.

Acceptance Criteria:
1. Initialize the logical structure for a mathematical utility subsystem.
2. Implement a validation function that takes an integer and returns `True` if it is a prime number.
3. Return `False` for all non-primes and any integer less than 2 (including negative numbers).
4. Safety constraint: The function must explicitly reject `float`, `str`, and `bool` types by raising a `TypeError`.