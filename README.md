**`gymme`**

> /ˈɡɪmi/ (gymme == gimme!) - 百丽宫中关村羽毛球捡漏王

![screenshot](https://github.com/user-attachments/assets/d4b627e9-4c28-45cd-9fe2-eaa275ceab56)

使用 uv 管理、安装此项目。

<https://docs.astral.sh/uv/>

首先，使用 Charles 抓包工具在请求头中找到必要的变量，即 `token` 和 `open_id`。可选择在 <https://sct.ftqq.com/> 获取通知服务密钥 (`send_key`)，需关注微信公众号“方糖”。

之后，根据自己的配置和偏好修改 `conf/pref.yaml` 配置文件。

```yaml
# 偏好设置定义（[0, 10] 分值定义，按需修改！）：
# * 0: 完全忽略，不予考虑
# * 1-3: 可接受范围，优先级较低
# * 4-6: 比较偏好，优先级中等
# * 7-9: 非常偏好，优先级较高
# * 10: 必须预订，最高优先级

field_pref_scores:
  "220": 1 # 主馆1
  "221": 1 # 主馆2
  "222": 1 # 主馆3
  "223": 1 # 主馆4
  "224": 1 # 主馆5
  "225": 1 # 主馆6
  "226": 1 # 主馆7
  "227": 1 # 主馆8
  "228": 1 # 副馆9
  "229": 1 # 副馆10
  "230": 1 # 副馆11
  "231": 1 # 副馆12

hour_pref_scores:
  "328228": 1 # 8:00-9:00
  "328229": 1 # 9:00-10:00
  "328230": 1 # 10:00-11:00
  "328231": 1 # 11:00-12:00
  "328232": 1 # 12:00-13:00
  "328233": 1 # 13:00-14:00
  "328234": 1 # 14:00-15:00
  "328235": 1 # 15:00-16:00
  "328236": 1 # 16:00-17:00
  "328237": 1 # 17:00-18:00
  "328238": 1 # 18:00-19:00
  "328239": 1 # 19:00-20:00
  "328240": 1 # 20:00-21:00
  "328241": 1 # 21:00-22:00

# 抓包获得以下两个重要变量
token: "ENTER_YOUR_TOKEN_HERE"
open_id: "ENTER_YOUR_OPENID_HERE"

# 可选设置微信服务号“方糖”推送通知
send_key: "ENTER_YOUR_SEND_KEY_HERE"
```

然后，安装依赖。

```bash
uv sync
```

最后，启动守护进程，开启捡漏与抢场模式。

```bash
uv run gymme --config-path conf/pref.yaml --days 0 1 2
```

可用的命令行选项：

```console
$ uv run gymme --help
usage: gymme [-h] [--config-path CONFIG_PATH] [--days DAYS [DAYS ...]] [--req-interval REQ_INTERVAL] [--interval INTERVAL]
             [--eager-interval EAGER_INTERVAL] [--concurrency CONCURRENCY] [--refresh-time REFRESH_TIME]
             [--max-retries MAX_RETRIES] [--consider-solo-fields]

gymme daemon -- 百丽宫中关村羽毛球捡漏王已开启！

options:
  -h, --help            show this help message and exit
  --config-path CONFIG_PATH
                        Path to gymme config file
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

| 选项                     | 说明                                                 | 示例                           |
| ------------------------ | ---------------------------------------------------- | ------------------------------ |
| `--config-path`          | 配置文件路径                                         | `--config-path conf/pref.yaml` |
| `--days`                 | 监控天数偏移量（0=今天，1=明天，以此类推）           | `--days 0 1 2`                 |
| `--req-interval`         | 请求间隔时间（秒），避免触发频率限制                 | `--req-interval 0.5`           |
| `--interval`             | 常规监控间隔时间（秒）                               | `--interval 30`                |
| `--eager-interval`       | 抢夺模式检查间隔时间（秒）                           | `--eager-interval 5`           |
| `--concurrency`          | 抢夺模式下并发订单尝试数                             | `--concurrency 3`              |
| `--refresh-time`         | 计划刷新时间（HH:MM 格式）                           | `--refresh-time 07:00`         |
| `--max-retries`          | 请求重试次数                                         | `--max-retries 3`              |
| `--consider-solo-fields` | 是否考虑单次场地（即 1 小时场，默认只考虑 2 小时场） | `--consider-solo-fields`       |
