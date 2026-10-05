Output docs/assets/demo.gif
# Recorded with vhs (https://github.com/charmbracelet/vhs) after two live runs (crm-hygiene,
# site-audit) against the demo company; action ids are from that ledger. Run from the repo root.
Set Shell "bash"
Set FontSize 13
Set Width 1720
Set Height 440
Set Padding 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set WindowBar Colorful

Hide
Type "source .venv/bin/activate && export PS1='$ ' && clear" Enter
Show

Type "# Ten agents. None may read untrusted input, see private data AND act externally." Enter
Sleep 400ms
Type "backoffice agents" Enter
Sleep 4.5s
Type "clear" Enter
Type "# Two scheduled jobs just ran headless, with budgets and an audit trail:" Enter
Type "backoffice runs" Enter
Sleep 3s
Type "# Agents never act - they propose. The human sees the real payload:" Enter
Type "backoffice approvals | head -8" Enter
Sleep 5s
Type "clear" Enter
Type "# Approve: the executor performs it exactly once, outside any agent session." Enter
Type "backoffice approve A-1a32de51 --note 'checked the activity text'" Enter
Sleep 2.5s
Sleep 2.5s
Type "# Every tool call, denial, proposal and approval is hash-chained:" Enter
Type "backoffice audit verify" Enter
Sleep 4s
