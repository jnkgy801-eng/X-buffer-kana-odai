# -*- coding: utf-8 -*-
"""
お題投稿ボット（Buffer無料枠 + GitHub Actions）

サブコマンド:
  generate  お題を odai_list.json の配列からランダムに選び、画像を outputs/images/ に生成
  post      生成済み画像の公開URLを使い、Buffer に「画像付き投稿 + 参加ルール返信」を予約
  channels  Bufferのチャンネル一覧を表示（BUFFER_CHANNEL_ID の確認用）

環境変数:
  BUFFER_API_KEY / BUFFER_CHANNEL_ID   post / channels で使用
  GITHUB_REPOSITORY / GITHUB_REF_NAME  Actions が自動設定（画像の公開URL生成用）
  THEME_TEXT      指定するとそのお題を使う（省略時はランダム）
  DRY_RUN         true なら Buffer へ送らず本文の表示のみ
  POST_DELAY_MIN  何分後に投稿するか（既定 5）
"""
from __future__ import annotations

import datetime
import json
import os
import random
import sys
import time

import requests
from PIL import Image, ImageDraw, ImageFont

LIST_FILE = 'odai_list.json'
IMG_DIR = 'outputs/images'
STATE_FILE = 'outputs/odai_state.json'   # 直近に使ったお題（連続重複を避ける）
PENDING_FILE = 'pending.json'            # generate → post の受け渡し（コミットしない）
KEEP_IMAGES = 14                         # 残す画像の枚数（古いものは自動削除）
AVOID_RECENT = 3                         # 直近N件と同じお題は避ける
BUFFER_ENDPOINT = 'https://api.buffer.com'
JST = datetime.timezone(datetime.timedelta(hours=9))

FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
]
SIZE = 1080
ORANGE = (255, 176, 0)

# 本文（1投稿目）と返信（参加ルール）。必要に応じて書き換えてください。
POST_TEMPLATE = '今日のお題はこちら👇\n\n{hashtag} をつけて、画像か動画で投稿してね！\n良い作品はリポストします'
RULE_REPLY = (
    '【参加ルール】\n'
    '・18歳以上の方のみ\n'
    '・ご自身で撮影した（または撮影者本人の同意がある）ものだけ\n'
    '・無修正、未成年、無断撮影、他人の作品の転載は即ブロック＆通報\n'
    '・センシティブ設定を必ずONに'
)


# ---------- 共通 ----------
def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def buffer_graphql(query, variables=None):
    key = os.environ.get('BUFFER_API_KEY', '')
    if not key:
        print('❌ BUFFER_API_KEY が設定されていません。')
        sys.exit(1)
    resp = requests.post(
        BUFFER_ENDPOINT,
        json={'query': query, 'variables': variables or {}},
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'},
        timeout=30,
    ).json()
    if resp.get('errors'):
        print('❌ APIエラー:', '; '.join(e.get('message', str(e)) for e in resp['errors']))
        sys.exit(1)
    return resp.get('data') or {}


# ---------- 画像生成 ----------
def find_font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size, index=0)  # index0 = 日本語(JP)
    raise RuntimeError('日本語フォントが見つかりません（fonts-noto-cjk をインストールしてください）')


def fit_font(draw, text, max_w, start=150, min_size=60):
    size = start
    while size > min_size:
        font = find_font(size)
        if draw.textlength(text, font=font) <= max_w:
            return font
        size -= 4
    return find_font(min_size)


def make_image(theme_text, path):
    img = Image.new('RGB', (SIZE, SIZE), (0, 0, 0))
    d = ImageDraw.Draw(img)

    title = f'「{theme_text}」'
    font = fit_font(d, title, SIZE - 120)
    w = d.textlength(title, font=font)
    d.text(((SIZE - w) / 2, 190), title, font=font, fill='white')

    d.rectangle([195, 520, SIZE - 195, 760], fill=ORANGE)
    f2 = find_font(140)
    w2 = d.textlength('選手権', font=f2)
    d.text(((SIZE - w2) / 2, 555), '選手権', font=f2, fill='black')

    f3 = find_font(66)
    w3 = d.textlength('※画像or動画', font=f3)
    d.text(((SIZE - w3) / 2, 830), '※画像or動画', font=f3, fill='white')
    img.save(path)


def cleanup_old_images():
    if not os.path.isdir(IMG_DIR):
        return
    files = sorted(f for f in os.listdir(IMG_DIR) if f.endswith('.png'))
    for f in files[:-KEEP_IMAGES]:
        os.remove(os.path.join(IMG_DIR, f))


def cmd_generate():
    data = load_json(LIST_FILE, {})
    themes = [t.strip() for t in data.get('themes', []) if isinstance(t, str) and t.strip()]
    if not themes:
        print('❌ odai_list.json の themes が空です。')
        sys.exit(1)

    forced = os.environ.get('THEME_TEXT', '').strip()
    if forced:
        theme = forced
    else:
        recent = load_json(STATE_FILE, {}).get('recent', [])
        n = min(AVOID_RECENT, len(themes) - 1)
        pool = [t for t in themes if t not in recent[-n:]] if n > 0 else themes
        theme = random.choice(pool or themes)

    os.makedirs(IMG_DIR, exist_ok=True)
    fname = f'odai_{datetime.datetime.now(JST):%Y%m%d_%H%M%S}.png'
    make_image(theme, os.path.join(IMG_DIR, fname))
    cleanup_old_images()
    save_json(PENDING_FILE, {'theme': theme, 'file': fname})
    print(f'✅ 画像生成: {IMG_DIR}/{fname}（お題: {theme}）')


# ---------- Buffer投稿 ----------
CREATE_POST = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id status dueAt } }
    ... on MutationError { message }
  }
}
"""


def wait_url(url, timeout=90):
    """pushした画像が raw.githubusercontent.com で見えるまで待つ。最後のHTTP状態を返す。"""
    status = None
    for _ in range(timeout // 5):
        try:
            r = requests.get(url, timeout=10, stream=True)
            status = r.status_code
            r.close()
            if status == 200:
                return True, status
        except requests.RequestException as e:
            status = type(e).__name__
        time.sleep(5)
    return False, status


def cmd_post():
    pending = load_json(PENDING_FILE, None)
    if not pending:
        print('❌ pending.json がありません。先に generate を実行してください。')
        sys.exit(1)
    data = load_json(LIST_FILE, {})
    text1 = POST_TEMPLATE.format(hashtag=data.get('hashtag', '#お題選手権'))

    if os.environ.get('DRY_RUN', 'false').lower() == 'true':
        print('🧪 DRY_RUN: Bufferへは送信しません')
        print(f"お題: {pending['theme']}\n---\n{text1}\n---\n{RULE_REPLY}")
        return

    channel = os.environ.get('BUFFER_CHANNEL_ID', '')
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    branch = os.environ.get('GITHUB_REF_NAME', 'main')
    if not (channel and repo):
        print('❌ BUFFER_CHANNEL_ID / GITHUB_REPOSITORY が必要です。')
        sys.exit(1)

    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{IMG_DIR}/{pending['file']}"
    ok, status = wait_url(url)
    if not ok:
        print(f'❌ 画像URLに到達できません（最後のHTTP状態: {status}）: {url}')
        if status == 404:
            print('   → 404 はリポジトリが private の可能性が高いです。public のリポジトリで実行してください。')
        sys.exit(1)

    due = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=int(os.environ.get('POST_DELAY_MIN', '5')))
    input_obj = {
        'text': text1,
        'channelId': channel,
        'schedulingType': 'automatic',
        'mode': 'customScheduled',
        'dueAt': due.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        'metadata': {'twitter': {'thread': [
            {'text': text1, 'assets': [{'image': {'url': url}}]},
            {'text': RULE_REPLY},
        ]}},
    }
    result = buffer_graphql(CREATE_POST, {'input': input_obj}).get('createPost') or {}
    if result.get('message') or not result.get('post'):
        print('❌ 投稿失敗:', result.get('message', '不明なエラー'))
        sys.exit(1)

    state = load_json(STATE_FILE, {'recent': []})
    state['recent'] = (state.get('recent', []) + [pending['theme']])[-20:]
    save_json(STATE_FILE, state)
    print(f"✅ Buffer予約完了: {result['post'].get('dueAt')}（お題: {pending['theme']}）")


# ---------- チャンネル確認 ----------
def cmd_channels():
    orgs = (buffer_graphql('query { account { organizations { id name } } }').get('account') or {}) \
        .get('organizations') or []
    if not orgs:
        print('❌ Organizationが見つかりません。')
        sys.exit(1)
    for org in orgs:
        print(f"🏢 Organization: {org.get('name')}")
        chs = buffer_graphql(
            'query($o: OrganizationId!) { channels(input: { organizationId: $o }) '
            '{ id name displayName service } }', {'o': org['id']}).get('channels') or []
        for ch in chs:
            mark = '👉' if ch.get('service') == 'twitter' else '  '
            print(f"  {mark} [{ch.get('service')}] {ch.get('displayName') or ch.get('name')}")
            print(f"       channelId = {ch.get('id')}")
    print('\n✅ X（twitter）の channelId を Secret「BUFFER_CHANNEL_ID」に登録してください。')


if __name__ == '__main__':
    cmds = {'generate': cmd_generate, 'post': cmd_post, 'channels': cmd_channels}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        print('usage: python odai_poster.py [generate|post|channels]')
        sys.exit(1)
    cmds[sys.argv[1]]()
