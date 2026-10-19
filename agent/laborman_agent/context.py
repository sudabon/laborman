from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, TextIO

from laborman_agent.api_client import LabormanClient
from laborman_agent.config import AgentConfig

logger = logging.getLogger("laborman_agent")


class SupportsNotify(Protocol):
    def notify(self, message: str) -> None: ...


@dataclass
class Context:
    """コマンドの実行に必要なもの（設定・API クライアント・通知・出力先）。"""

    config: AgentConfig
    client: LabormanClient
    notifier: SupportsNotify
    out: TextIO
    err: TextIO

    def say(self, message: str) -> None:
        print(message, file=self.out)
        logger.info(message)

    def warn(self, message: str, *, notify: bool = True) -> None:
        print(message, file=self.err)
        logger.warning(message)
        if notify:
            self.notifier.notify(message)
