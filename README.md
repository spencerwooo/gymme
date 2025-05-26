**`gymy`**

> 百丽宫中关村羽毛球捡漏王
>
> ![image](https://github.com/user-attachments/assets/b5f7ca1d-f3c9-4da4-bdbe-2e53418ed4fa)


Use uv to manage this project.

<https://docs.astral.sh/uv/>

First, fill out `.env` environment variables (use Charles to find these tokens within the request headers). Get the notification service key (`SEND_KEY`) at <https://sct.ftqq.com/>.

```env
TOKEN={TOKEN}
OPEN_ID={WECHAT_OPEN_ID}
SEND_KEY={SERVER_CHAN_SEND_KEY}
```

Then, install dependencies.

```bash
uv sync
```

Finally, start daemon.

```bash
uv run daemon.py
```
