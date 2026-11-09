from schemas import SandboxConfig, ExecutionResult, ExecutionStatus
from executor import SandboxExecutor


config = SandboxConfig()
test_cases = [
{
    "name": "Small memory allocation",
    "code": 'import math',
    "expected": ExecutionStatus.SUCCESS,
},
{
    "name": "Large memory allocation",
    "code": 'data = []\nwhile True:\n    data.append("A" * (10 * 1024 * 1024))',
    "expected": ExecutionStatus.MEMORY_LIMIT_EXCEEDED,
},
]
executor = SandboxExecutor(config)
# passed = 0

# for test in test_cases:
#     answer = executor.execute_code(test["code"])

#     success = answer.status_code == test["expected"]

#     if success:
#         passed += 1

#     print(f"\n--- {test['name']} ---")
#     print(f"Expected: {test['expected']}")
#     print(f"Actual:   {answer.status_code}")
#     print(f"Passed:   {success}")

# print(f"\nGrade: {passed}/{len(test_cases)}")


for test in test_cases:
    answer = executor.execute_code(test["code"])
    print(answer)