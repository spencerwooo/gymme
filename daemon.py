import argparse
import asyncio
import logging
import os
import re

import httpx
from dotenv import load_dotenv
from rich.logging import RichHandler

from client import GymClient, GymField

load_dotenv()
SEND_KEY = os.getenv("SEND_KEY", "")

logging.basicConfig(level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)])
log = logging.getLogger("rich")


def parse_args():
    parser = argparse.ArgumentParser(description="gymy daemon -- 百丽宫中关村羽毛球捡漏王已开启！")
    parser.add_argument("--days", nargs="+", type=int, default=[0], help="Days offset to monitor (e.g., --days 0 1 2)")
    parser.add_argument("--interval", type=int, default=600, help="Interval between checks (default: 600 secs)")
    parser.add_argument("--req-interval", type=int, default=10, help="Interval between requests (default: 10 secs)")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level (default: INFO)")
    return parser.parse_args()


def list_fields(fields: list[list[GymField]] | list[GymField]) -> str:
    """Format list of fields for logging."""
    if not fields:
        return ""

    # Handle single layer list (available fields)
    if fields and isinstance(fields[0], GymField):
        repr = "; ".join(f.field_desc for f in fields[:3])
        return repr + ("; ..." if len(fields) > 3 else "")

    # Handle list of lists (preferred field scenes)
    repr = "; ".join(str([i.field_desc for i in f]) for f in fields[:6])
    return repr + ("; ..." if len(fields) > 6 else "")


def sc_send(title: str, desp: str = "", sendkey: str = SEND_KEY) -> None:
    """Send notification using ServerChan."""
    if sendkey.startswith("sctp"):
        match = re.match(r"sctp(\d+)t", sendkey)
        if match:
            num = match.group(1)
            url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
        else:
            raise ValueError("Invalid sendkey format for sctp")
    else:
        url = f"https://sctapi.ftqq.com/{sendkey}.send"
    params = {"title": title, "desp": desp}
    headers = {"Content-Type": "application/json;charset=utf-8"}
    resp = httpx.post(url, json=params, headers=headers)
    data = resp.json()
    log.info(f"Notification server response: {data}")


async def start_daemon():
    args = parse_args()
    gym = GymClient()
    log.info("Starting daemon ... 百丽宫中关村羽毛球捡漏王已开启！")

    days = [gym.create_relative_date(offset) for offset in args.days]
    log.info(f"Checking available fields for days {', '.join(days)}")

    while True:
        try:
            for day, offset in zip(days, args.days):
                available_fields = await gym.get_available_fields(offset)
                pref_fields = gym.generate_preferred_field_scenes(available_fields)
                if not pref_fields:
                    log.info(f"No preferred fields available for {day}. Skipping...")
                    continue

                log.info(f"{len(available_fields)} available fields for {day}:\n{list_fields(available_fields)}")
                for pref_field in pref_fields:
                    order_attempt_details = f"{day} {[f.field_desc for f in pref_field]}"
                    try:
                        payment_url = await gym.create_order(offset, day, pref_field)
                        log.info(f"Success! Order created, continue to payment ->\n{payment_url}")
                        sc_send(
                            title=f"Order created for {order_attempt_details}",
                            desp=f"Please complete the payment within 10 minutes:\n\n[{payment_url}]({payment_url})",
                            sendkey=SEND_KEY,
                        )
                        break
                    except Exception as e:
                        log.error(f"Failed to create order for {order_attempt_details}: {e}")
                        await asyncio.sleep(args.req_interval)
                        continue

            await asyncio.sleep(args.interval)
        except KeyboardInterrupt:
            log.info("Gracefully shutting down ...")
            break
        except Exception as e:
            log.exception(e)
            continue


if __name__ == "__main__":
    try:
        asyncio.run(start_daemon())
    except KeyboardInterrupt:
        log.info("Gracefully shutting down ...")
