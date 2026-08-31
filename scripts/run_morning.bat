@echo off
cd /d "C:\Users\81908\OneDrive\デスクトップ\RakutenRoom自動化"
"C:\Users\81908\AppData\Roaming\npm\claude.cmd" -p "CLAUDE.mdの指示に従い、本日朝の分の商品選定〜投稿文生成〜一覧ページ作成〜Artifact公開〜PushNotification通知までを実行してください。data/posted_history.jsonの更新とgit commit・pushも忘れずに行ってください。" --permission-mode bypassPermissions --allowedTools Bash Read Write Edit Glob Grep Artifact PushNotification