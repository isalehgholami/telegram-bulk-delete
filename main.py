"""Telegram session manager - leave channels, block bots."""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.contacts import BlockRequest
from telethon.tl.functions.messages import DeleteHistoryRequest
from telethon.tl.types import User, Chat, Channel
from python_socks.async_.asyncio import Proxy

from config import API_ID, API_HASH, SESSION_NAME, HOST, PORT, PROXY_URL

log = logging.getLogger("tg-manager")


def build_proxy(url: str):
    """Parse socks5://user:pass@host:port or http://host:port into Telethon proxy tuple.

    Telethon expects: (python_socks.ProxyType, host, port, rdns, username, password)
    """
    if not url:
        return None
    u = urlparse(url)
    scheme = u.scheme.lower()

    from python_socks import ProxyType
    type_map = {
        "socks4": ProxyType.SOCKS4,
        "socks5": ProxyType.SOCKS5,
        "http": ProxyType.HTTP,
    }
    if scheme not in type_map:
        raise ValueError(f"Unsupported proxy scheme: {scheme}. Use socks4, socks5, or http.")

    proxy_type = type_map[scheme]
    host = u.hostname
    port = u.port
    rdns = True
    username = u.username or None
    password = u.password or None

    log.info("Proxy: %s %s:%s", scheme, host, port)
    return (proxy_type, host, port, rdns, username, password)


proxy = build_proxy(PROXY_URL)
client: TelegramClient | None = None
templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH, proxy=proxy)
    await client.start()
    yield
    await client.disconnect()


app = FastAPI(lifespan=lifespan)


# ── Pages ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    me = await client.get_me()
    return templates.TemplateResponse(request, "index.html", {"me": me})


@app.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request):
    return templates.TemplateResponse(request, "channels.html")


@app.get("/bots", response_class=HTMLResponse)
async def bots_page(request: Request):
    return templates.TemplateResponse(request, "bots.html")


# ── API: fetch data ────────────────────────────────────────────

@app.get("/api/channels")
async def api_channels():
    """Return all dialogs that are channels/groups (not users, not self)."""
    me = await client.get_me()
    result = []
    async for d in client.iter_dialogs():
        e = d.entity
        if isinstance(e, User):
            continue
        if isinstance(e, Channel):
            result.append({
                "id": e.id,
                "title": e.title,
                "type": "channel" if e.broadcast else "group",
                "members": getattr(e, "participants_count", None),
            })
        elif isinstance(e, Chat):
            result.append({
                "id": e.id,
                "title": e.title,
                "type": "legacy_group",
                "members": e.participants_count,
            })
    return result


@app.get("/api/bots")
async def api_bots():
    """Return all bot dialogs."""
    result = []
    async for d in client.iter_dialogs():
        e = d.entity
        if isinstance(e, User) and e.bot and not e.is_self:
            result.append({
                "id": e.id,
                "username": e.username or "",
                "name": f"{e.first_name or ''} {e.last_name or ''}".strip(),
                "bot_mutual": getattr(e, "mutual_contact", False),
            })
    return result


@app.get("/api/self")
async def api_self():
    me = await client.get_me()
    return {"id": me.id, "name": f"{me.first_name} {me.last_name}".strip()}


# ── API: actions ───────────────────────────────────────────────

@app.post("/api/leave")
async def api_leave(ids: str = Form(...)):
    """Leave multiple channels/groups. Comma-separated IDs."""
    target_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    results = []
    for tid in target_ids:
        try:
            await client(LeaveChannelRequest(tid))
            results.append({"id": tid, "ok": True})
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
            try:
                await client(LeaveChannelRequest(tid))
                results.append({"id": tid, "ok": True})
            except Exception as e2:
                results.append({"id": tid, "ok": False, "error": str(e2)})
        except Exception as e:
            results.append({"id": tid, "ok": False, "error": str(e)})
    return results


@app.post("/api/bots/action")
async def api_bots_action(ids: str = Form(...), action: str = Form(...)):
    """Perform action on multiple bots. action: block, delete, block_delete."""
    target_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    results = []
    for tid in target_ids:
        try:
            entity = await client.get_entity(tid)
            # delete before block, because blocking makes entity unresolvable
            if action in ("delete", "block_delete"):
                await client(DeleteHistoryRequest(
                    peer=entity,
                    max_id=0,
                    revoke=False,
                ))
            if action in ("block", "block_delete"):
                await client(BlockRequest(entity))
            results.append({"id": tid, "ok": True})
        except FloodWaitError as e:
            log.warning("Flood wait %ds for %d", e.seconds, tid)
            await asyncio.sleep(e.seconds + 1)
            # retry once after wait
            try:
                if action in ("block", "block_delete"):
                    await client(BlockRequest(entity))
                results.append({"id": tid, "ok": True})
            except Exception as e2:
                results.append({"id": tid, "ok": False, "error": str(e2)})
        except Exception as e:
            results.append({"id": tid, "ok": False, "error": str(e)})
    return results


@app.post("/api/leave-all-channels")
async def api_leave_all_channels():
    """Leave ALL channels (not supergroups)."""
    me = await client.get_me()
    results = []
    async for d in client.iter_dialogs():
        e = d.entity
        if isinstance(e, Channel) and e.broadcast:
            try:
                await client(LeaveChannelRequest(e.id))
                results.append({"id": e.id, "title": e.title, "ok": True})
            except FloodWaitError as ex:
                await asyncio.sleep(ex.seconds + 1)
                try:
                    await client(LeaveChannelRequest(e.id))
                    results.append({"id": e.id, "title": e.title, "ok": True})
                except Exception as ex2:
                    results.append({"id": e.id, "title": e.title, "ok": False, "error": str(ex2)})
            except Exception as ex:
                results.append({"id": e.id, "title": e.title, "ok": False, "error": str(ex)})
    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
