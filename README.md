**`gymme`**

> /ˈɡɪmi/ (gymme == gimme!) - 百丽宫中关村羽毛球捡漏王

![image](https://github.com/user-attachments/assets/53bb1b19-bc7c-441f-a005-b179c44a5189)

## 抓包准备

为了模拟微信中对体育馆服务的请求，`gymme` 需要抓包工具来获取必要的请求头信息。推荐使用 [Charles](https://www.charlesproxy.com/) 或 [Fiddler](https://www.telerik.com/fiddler) 等抓包工具。下文以 Charles 为例。

1. 使用 Charles 代理电脑流量，并在 **微信电脑版** 中，用 **微信浏览器** 打开体育馆预约页面。
2. **选择中关村体育馆，选择任何球类运动、场地和时间段，点击“提交订单”，并在“确认订单”界面点击“提交并支付订单”，无需支付。**
3. 回到 Charles，寻找请求路径为 `/api/order/submit` 的 POST 请求。
4. 在请求头（Headers）中找到 `token` 并记录：

   ![PixPin_2025-06-03_12-00-00](https://github.com/user-attachments/assets/b76db2ef-a46e-4b66-b033-47b3686c3d14)

6. 在请求内容（Contents）中找到 `open_id` 并记录：

   ![PixPin_2025-06-03_12-00-40](https://github.com/user-attachments/assets/7d8994c8-db59-41a3-b3d7-6e019c2ddbe8)

此外，可选择在 <https://sct.ftqq.com/> 获取通知服务密钥 (`send_key`)，需关注微信公众号“方糖”。

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

## 安装依赖

使用 uv 管理、安装此项目。首先，安装 uv：<https://docs.astral.sh/uv/>

然后，安装依赖。

```bash
uv sync
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

命令行选项定义如下：

| 选项                     | 说明                                                 | 示例                           |
| ------------------------ | ---------------------------------------------------- | ------------------------------ |
| `--config-path`          | 配置文件路径                                         | `--config-path conf/pref.yaml` |
| `--days`                 | 监控天数偏移量（0=今天，1=明天，以此类推）           | `--days 0 1 2`                 |
| `--req-interval`         | 请求间隔时间（秒），避免触发频率限制                 | `--req-interval 0.5`           |
| `--interval`             | 常规监控间隔时间（秒）                               | `--interval 30`                |
| `--eager-interval`       | 抢场模式检查间隔时间（秒）                           | `--eager-interval 5`           |
| `--concurrency`          | 抢场模式下并发订单尝试数                             | `--concurrency 3`              |
| `--refresh-time`         | 计划刷新时间（HH:MM 格式）                           | `--refresh-time 07:00`         |
| `--max-retries`          | 请求重试次数                                         | `--max-retries 3`              |
| `--consider-solo-fields` | 是否考虑单次场地（即 1 小时场，默认只考虑 2 小时场） | `--consider-solo-fields`       |

最后，启动 gymme 守护进程，开启捡漏与抢场模式。

```bash
uv run gymme --config-path conf/pref.yaml --days 0 1 2
```

gymme 将：

1. 对指定天数（0=今天，1=明天，2=后天）进行监控。
2. 在常规监控模式（捡漏）下（07:30 - 23:59）每隔指定时间（`--interval`）检查可用场地，如发现符合偏好设置的场地，将尝试下单。
3. 在抢场模式下（00:00 - 07:29）每隔指定时间（`--eager-interval`）检查可用场地，并按偏好顺序尝试下单，支持并发请求。
4. 在其余时间休眠（00:00 - 06:54）。

祝，打球愉快。
