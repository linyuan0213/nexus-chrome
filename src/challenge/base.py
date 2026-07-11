"""挑战解析器基类。"""

from abc import ABC, abstractmethod

from DrissionPage._pages.chromium_tab import ChromiumTab


class ChallengeResolver(ABC):
    @abstractmethod
    def detect(self, tab: "ChromiumTab") -> bool:
        """检测页面是否属于此类型的挑战。"""
        ...

    @abstractmethod
    def resolve(self, tab: "ChromiumTab", timeout: int = 30) -> bool:
        """尝试解析挑战。返回是否成功。"""
        ...

    @property
    @abstractmethod
    def challenge_type(self) -> str:
        ...

    def verify(self, tab: "ChromiumTab") -> bool:
        try:
            return not self.detect(tab)
        except Exception:
            return True
