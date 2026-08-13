from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CertificationReport:
    results: list[TestResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = ""):
        self.results.append(TestResult(name, passed, detail))
        label = "PASS" if passed else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"{label:4} {name}{suffix}")

    @property
    def failed(self):
        return [r for r in self.results if not r.passed]

    @property
    def passed(self):
        return [r for r in self.results if r.passed]

    def summary(self):
        print()
        print("=" * 64)
        print("FarmAI Stock Manager V7.2 — B6 Certification Summary")
        print("=" * 64)
        print(f"Passed : {len(self.passed)}")
        print(f"Failed : {len(self.failed)}")
        print(f"Total  : {len(self.results)}")
        print()

        if self.failed:
            print("Backend Certification: FAIL")
            print("Resolve failed tests before RC1.")
            return 1

        print("Backend Certification: PASS")
        print("Proceed to GPT behavior certification and cleanup.")
        return 0
