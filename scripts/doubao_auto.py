#!/usr/bin/env python3
"""豆包桌面应用自动化 — 使用 CGEvent API 模拟键盘操作。

工作流：
  1. 将 prompt 复制到剪贴板
  2. 激活豆包应用
  3. Cmd+V 粘贴 → Enter 提交
  4. 等待 LLM 生成回复
  5. Cmd+A → Cmd+C 复制回复
  6. 读取剪贴板返回
"""

import subprocess
import time
import json
import sys
import os

# ═══════════════════════════════════
# CGEvent 键盘模拟（不依赖 Accessibility）
# ═══════════════════════════════════

import ctypes
import ctypes.util
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    kCGHIDEventTap,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskShift,
)

# 加载 Carbon 框架获取虚拟键码
_carbon = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Carbon"))

def key_code(char):
    """字符 → macOS 虚拟键码映射。"""
    mapping = {
        'a': 0, 's': 1, 'd': 2, 'f': 3, 'h': 4, 'g': 5, 'z': 6, 'x': 7,
        'c': 8, 'v': 9, 'b': 11, 'q': 12, 'w': 13, 'e': 14, 'r': 15,
        'y': 16, 't': 17, '1': 18, '2': 19, '3': 20, '4': 21, '5': 23,
        '6': 22, '7': 26, '8': 28, '9': 25, '0': 29,
        'return': 36, 'enter': 76, 'space': 49,
        'tab': 48, 'escape': 53, 'delete': 51,
        'up': 126, 'down': 125, 'left': 123, 'right': 124,
    }
    return mapping.get(char.lower(), 0)


def press_key(key_name, with_command=False, with_shift=False):
    """发送单个按键事件。"""
    code = key_code(key_name)
    if code == 0 and key_name not in ('a',):
        return False

    flags = 0
    if with_command:
        flags |= kCGEventFlagMaskCommand
    if with_shift:
        flags |= kCGEventFlagMaskShift

    # Key down
    event = CGEventCreateKeyboardEvent(None, code, True)
    if flags:
        event.setIntegerValueField_(kCGEventFlagMaskCommand, flags)
    CGEventPost(kCGHIDEventTap, event)

    time.sleep(0.02)

    # Key up
    event = CGEventCreateKeyboardEvent(None, code, False)
    CGEventPost(kCGHIDEventTap, event)

    time.sleep(0.05)
    return True


def paste_and_submit():
    """Cmd+V 粘贴 + Enter 提交。"""
    press_key('v', with_command=True)
    time.sleep(0.3)
    press_key('return')
    return True


def select_all_and_copy():
    """Cmd+A 全选 + Cmd+C 复制。"""
    press_key('a', with_command=True)
    time.sleep(0.2)
    press_key('c', with_command=True)
    time.sleep(0.3)


def activate_doubao():
    """激活豆包应用。"""
    subprocess.run(
        ['osascript', '-e', 'tell application "Doubao" to activate'],
        timeout=3, capture_output=True,
    )
    time.sleep(0.8)


def copy_to_clipboard(text):
    """复制文本到剪贴板。"""
    proc = subprocess.run(['pbcopy'], input=text.encode('utf-8'), timeout=3)
    return proc.returncode == 0


def read_clipboard():
    """读取剪贴板内容。"""
    try:
        result = subprocess.run(['pbpaste'], capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""


# ═══════════════════════════════════
# 主流程
# ═══════════════════════════════════

def send_prompt_and_get_response(prompt_text, wait_seconds=25):
    """发送 prompt 到豆包，等待回复，返回响应文本。"""
    print(f"  [1/5] 复制 Prompt ({len(prompt_text)} chars)...")
    copy_to_clipboard(prompt_text)
    time.sleep(0.3)

    print("  [2/5] 激活豆包 + 粘贴提交...")
    activate_doubao()
    paste_and_submit()

    print(f"  [3/5] 等待豆包回复 ({wait_seconds}s)...")
    time.sleep(wait_seconds)

    # 尝试点击回复区域然后全选复制
    # 先点一下页面确保焦点在内容区
    print("  [4/5] 选择并复制回复...")
    # 多试几种选择策略
    # 方法1: 点一下空白区域 → Cmd+A 全选 → Cmd+C
    # 方法2: Shift+Cmd+End 选到最后 → Cmd+C
    # 使用 Cmd+A 最简单
    press_key('a', with_command=True)
    time.sleep(0.2)
    press_key('c', with_command=True)
    time.sleep(0.5)

    print("  [5/5] 读取回复...")
    response = read_clipboard()

    if response:
        print(f"  ✅ 获取到回复 ({len(response)} chars)")
    else:
        print("  ⚠️ 剪贴板为空，尝试备用方法...")
        # 备用: Shift+Cmd+End 然后 Cmd+C
        press_key('end', with_command=True, with_shift=True)
        time.sleep(0.2)
        press_key('c', with_command=True)
        time.sleep(0.3)
        response = read_clipboard()

    return response


# ═══════════════════════════════════
# CLI
# ═══════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: doubao_auto.py <prompts.json> [start_index] [count]")
        sys.exit(1)

    prompts_file = sys.argv[1]
    start_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    count = int(sys.argv[3]) if len(sys.argv) > 3 else None

    with open(prompts_file, 'r', encoding='utf-8') as f:
        all_prompts = json.load(f)

    prompts = all_prompts[start_idx:]
    if count:
        prompts = prompts[:count]

    results = []

    print(f"\n{'='*60}")
    print(f"豆包自动化 — 共 {len(prompts)} 条 Prompt")
    print(f"预计耗时: ~{len(prompts) * 30}s ({len(prompts) * 0.5:.0f} 分钟)")
    print(f"{'='*60}\n")

    # 先激活豆包确保窗口在前台
    print(">>> 请确认豆包已打开并处于'专业模式'的聊天界面")
    print(">>> 确认后豆包窗口会闪烁，准备好后自动开始\n")
    activate_doubao()
    time.sleep(1)

    print(">>> 3 秒后开始第一条...")
    time.sleep(3)

    for i, p in enumerate(prompts):
        print(f"\n--- [{i+1}/{len(prompts)}] {p['city']} {p['title'][:40]} ---")
        response = send_prompt_and_get_response(p['prompt'], wait_seconds=25)

        results.append({
            **p,
            'response': response,
            'success': len(response) > 10 if response else False,
        })

        # 保存中间结果
        with open('/tmp/doubao_results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        if i < len(prompts) - 1:
            print(f"  ⏳ 等待 2 秒后继续下一条...")
            time.sleep(2)

    # 保存最终结果
    with open('/tmp/doubao_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    success = sum(1 for r in results if r['success'])
    print(f"\n{'='*60}")
    print(f"完成! {success}/{len(results)} 条获取成功")
    print(f"结果保存在 /tmp/doubao_results.json")
    print(f"{'='*60}")
