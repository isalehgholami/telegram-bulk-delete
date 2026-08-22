# Telegram Manager

Bulk leave channels and block bots via web dashboard.

## Setup

1. Get API credentials from https://my.telegram.org/apps
2. Set env vars:

```bash
export TG_API_ID=12345
export TG_API_HASH=your_hash_here
```

3. (If Telegram is blocked) Set proxy:

```bash
export TG_PROXY=socks5://user:pass@host:port
# or
export TG_PROXY=http://host:port
```

4. Run:

```bash
cd telegram-manager
source venv/bin/activate
python main.py
```

4. Open http://127.0.0.1:8686
5. First run asks for phone number + code to login (session saved locally)

## Features

- **Leave Channels**: view all joined channels/groups, select multiple, bulk leave
- **Block Bots**: view all bot contacts, select multiple, bulk block
- **Leave All Channels**: one-click nuke all channels (not groups)
- Dark Telegram-style UI
