"""反爬工具：随机等待、UA 轮换、行为模拟、重试装饰器。

适配 job51_xbrowser 采集器（xbrowser + xb.cjs）：
  - 人类化随机等待
  - 随机 User-Agent
  - 页面滚动/鼠标模拟（通过 xbrowser JS 注入）
  - 指数退避重试装饰器
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Callable, TypeVar

logger = logging.getLogger("scraping.anti_crawl")

# ── User-Agent 池 ──────────────────────────────────────────

USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """随机选取 User-Agent。"""
    return random.choice(USER_AGENTS)


# ── 随机等待 ──────────────────────────────────────────────

def random_sleep(min_seconds: float = 1.0, max_seconds: float = 3.0) -> float:
    """随机等待，模拟人类浏览行为，返回实际等待秒数。"""
    sleep_time = random.uniform(min_seconds, max_seconds)
    time.sleep(sleep_time)
    return sleep_time


def page_interval_sleep(page: int, base_min: float = 1.5, base_max: float = 4.0) -> float:
    """页间等待：随翻页数适当增加等待，避免匀速被识别。"""
    extra = min(page * 0.2, 2.0)  # 每页多等 0.2s，最多多 2s
    return random_sleep(base_min + extra, base_max + extra)


def keyword_interval_sleep(min_seconds: float = 5.0, max_seconds: float = 12.0) -> float:
    """关键词切换间等待（比页间等待更长）。"""
    return random_sleep(min_seconds, max_seconds)


def city_interval_sleep(min_seconds: float = 60.0, max_seconds: float = 120.0) -> float:
    """城市切换间等待（2分钟以上，降低跨城市被封概率）。"""
    return random_sleep(min_seconds, max_seconds)


# ── xbrowser 行为模拟 JS ──────────────────────────────────

def build_human_behavior_js() -> str:
    """生成在 xbrowser 中模拟人类行为的 JS 代码（同步执行）。

    包含：随机滚动 + 鼠标移动事件，用于 xb_eval 调用。
    """
    return """(function() {
  try {
    var h = document.body.scrollHeight || 1000;
    var positions = [
      Math.floor(Math.random() * h * 0.25),
      Math.floor(Math.random() * h * 0.5) + Math.floor(h * 0.25),
      Math.floor(Math.random() * h * 0.25) + Math.floor(h * 0.5)
    ];
    positions.forEach(function(pos) {
      window.scrollTo(0, pos);
    });
    document.dispatchEvent(new MouseEvent('mousemove', {
      clientX: Math.floor(Math.random() * window.innerWidth),
      clientY: Math.floor(Math.random() * window.innerHeight),
      bubbles: true
    }));
    return JSON.stringify({ok: true, action: "human_behavior"});
  } catch(e) {
    return JSON.stringify({ok: false, error: e.message});
  }
})()"""


# ── 重试装饰器 ────────────────────────────────────────────

F = TypeVar("F", bound=Callable)


def retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 2.0,
    backoff_factor: float = 1.5,
    exceptions: tuple = (Exception,),
) -> Callable[[F], F]:
    """指数退避重试装饰器。

    Args:
        max_retries: 最大重试次数（不含首次）
        base_delay: 首次失败等待秒数
        backoff_factor: 退避乘数
        exceptions: 触发重试的异常类型
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error("all %d retries failed for %s: %s", max_retries, func.__name__, e)
                        raise
                    jitter = delay * random.uniform(0.0, 0.3)
                    wait = delay + jitter
                    logger.warning(
                        "retry %d/%d for %s after %.1fs: %s",
                        attempt + 1, max_retries, func.__name__, wait, e,
                    )
                    time.sleep(wait)
                    delay *= backoff_factor
        return wrapper  # type: ignore[return-value]
    return decorator
