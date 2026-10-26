# お題投稿ボット（1日2回・ランダム・Buffer無料枠）

`odai_list.json` の `themes` からお題をランダムに選び、お題画像を生成して Buffer 経由で X に予約投稿します（返信に参加ルール付き）。
リポストは手動（目視確認）です。

## ファイル
| ファイル | 役割 |
|---|---|
| `odai_poster.py` | 画像生成 / Buffer投稿 / チャンネル確認 |
| `commit_history.py` | 画像と履歴(outputs/)のcommit＆push（競合は自動マージ） |
| `odai_list.json` | お題の配列とハッシュタグ（ここを編集） |
| `outputs/odai_state.json` | 直近に使ったお題（自動更新） |
| `.github/workflows/odai_post.yml` | GitHub Actions |

## セットアップ
1. **リポジトリは public にする**（BufferがGitHub上の画像URLを取得するため）
2. Buffer に新アカウントのXを接続し、https://publish.buffer.com/settings/api で API Key を発行
3. Settings → Secrets and variables → Actions → **Secrets** に登録
   - `BUFFER_API_KEY` : 手順2のキー
   - `BUFFER_CHANNEL_ID` : 手順4で確認
4. Actions → 「お題投稿」→ Run workflow → `list_channels` にチェック → 実行。ログの `[twitter]` の `channelId` を手順3に登録
5. Run workflow（`dry_run` ON）で画像と本文を確認（Artifacts の `odai-preview` から画像を取得）
6. `dry_run` を OFF にして1回実行 → Buffer に予約されたことを確認
7. 以降は毎日 12:00 / 20:00 JST 頃に自動実行

## 調整
- お題の追加・変更: `odai_list.json`
- 投稿文・参加ルール: `odai_poster.py` 上部の `POST_TEMPLATE` / `RULE_REPLY`
- 時刻: ワークフローの cron（UTC。JST-9時間）
- 自動実行の停止: ワークフローの `schedule` をコメントアウト
