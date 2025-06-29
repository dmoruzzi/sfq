# tests/conftest.py

executed_tests = 0

def pytest_runtest_logreport(report):
    global executed_tests
    if report.when == "call" and report.passed:
        executed_tests += 1
    elif report.when == "call" and report.failed:
        executed_tests += 1

def pytest_sessionfinish(session, exitstatus):
    if session.testscollected > 0 and executed_tests == 0:
        print("❌ Pytest collected tests, but all were skipped. Failing the run.")
        session.exitstatus = 1
