# -*- coding: utf-8 -*-
"""
outputs/（お題画像・使用履歴）をコミット＆pushする補助スクリプト。

・push が他の更新と競合して拒否された場合は、取り込み直して再試行する
・outputs/odai_state.json が競合した場合は、両方の履歴をマージして解決する
  （履歴が失われると、同じお題が続いて出やすくなるため）

使い方: python commit_history.py [コミットメッセージ用ラベル]
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys

STATE_PATH = 'outputs/odai_state.json'
_RECENT_KEEP = 20
_MAX_PUSH_ATTEMPTS = 3


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *args], check=check, text=True, capture_output=True, encoding='utf-8')


def _merge_state(remote_json: str, ours_json: str) -> str:
    def load(text: str) -> dict:
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    a, b = load(remote_json), load(ours_json)
    recent = list(a.get('recent', []))
    recent += [t for t in b.get('recent', []) if t not in recent]
    merged = {**a, **b, 'recent': recent[-_RECENT_KEEP:]}
    return json.dumps(merged, ensure_ascii=False, indent=2)


def _rebase_onto_remote(branch: str) -> None:
    _git('fetch', 'origin', branch)
    result = _git('rebase', f'origin/{branch}', check=False)
    while result.returncode != 0:
        conflicted = _git('diff', '--name-only', '--diff-filter=U').stdout.split()
        if conflicted != [STATE_PATH]:
            _git('rebase', '--abort', check=False)
            raise RuntimeError(f'履歴JSON以外で競合したため中断しました: {conflicted}\n{result.stderr}')
        remote_side = _git('show', f':2:{STATE_PATH}').stdout   # origin側
        our_side = _git('show', f':3:{STATE_PATH}').stdout      # 今回の更新
        with open(STATE_PATH, 'w', encoding='utf-8') as f:
            f.write(_merge_state(remote_side, our_side))
        _git('add', STATE_PATH)
        print('履歴JSONの競合をマージで解決しました。')
        result = subprocess.run(['git', '-c', 'core.editor=true', 'rebase', '--continue'],
                                text=True, capture_output=True, encoding='utf-8')


def main() -> int:
    label = f' {sys.argv[1]}' if len(sys.argv) > 1 else ''
    branch = os.environ.get('GITHUB_REF_NAME', 'main')
    os.makedirs('outputs', exist_ok=True)
    try:
        _git('config', 'user.name', 'github-actions[bot]')
        _git('config', 'user.email', 'github-actions[bot]@users.noreply.github.com')
        _git('add', '-A', 'outputs/')
        if _git('diff', '--staged', '--quiet', check=False).returncode == 0:
            print('コミットする変更はありません。')
            return 0

        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        _git('commit', '-m', f'お題投稿{label} ({stamp})')

        for attempt in range(1, _MAX_PUSH_ATTEMPTS + 1):
            _rebase_onto_remote(branch)
            push = _git('push', 'origin', f'HEAD:{branch}', check=False)
            if push.returncode == 0:
                print('コミットしてpushしました。')
                return 0
            print(f'push失敗（{attempt}/{_MAX_PUSH_ATTEMPTS}）。再試行します: {push.stderr.strip()[:200]}')
        print('エラー: pushが繰り返し失敗しました。')
        return 1
    except subprocess.CalledProcessError as e:
        _git('rebase', '--abort', check=False)
        print(f'エラー: git {" ".join(e.cmd[1:])} に失敗\n{e.stdout}\n{e.stderr}')
        return 1
    except RuntimeError as e:
        print(f'エラー: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
