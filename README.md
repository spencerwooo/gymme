**`gymme`**

> /ˈɡɪmi/ (gymme == gimme!) -- 百丽宫中关村羽毛球捡漏王

![screenshot](https://github.com/user-attachments/assets/d4b627e9-4c28-45cd-9fe2-eaa275ceab56)

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
uv run gymme
```

Available command line options:

```console
$ uv run gymme --help
usage: gymme [-h] [--days DAYS [DAYS ...]] [--req-interval REQ_INTERVAL] [--interval INTERVAL] [--eager-interval EAGER_INTERVAL] [--concurrency CONCURRENCY] [--refresh-time REFRESH_TIME] [--max-retries MAX_RETRIES] [--consider-solo-fields]

gymme daemon -- 百丽宫中关村羽毛球捡漏王已开启！

options:
  -h, --help            show this help message and exit
  --days DAYS [DAYS ...]
                        Days offset to monitor (e.g., --days 0 1 2)
  --req-interval REQ_INTERVAL
                        Interval between requests to avoid rate limits
  --interval INTERVAL   Interval between checks
  --eager-interval EAGER_INTERVAL
                        Interval for eager checking
  --concurrency CONCURRENCY
                        Concurrent order attempts during eager mode
  --refresh-time REFRESH_TIME
                        Schedule refresh time (HH:MM format)
  --max-retries MAX_RETRIES
                        Retry attempts for server errors
  --consider-solo-fields
                        Consider solo fields (1 hour)
```
