import argparse
import asyncio
import logging
import os
import re
from datetime import datetime

import httpx
from dotenv import load_dotenv
from rich.logging import RichHandler

from client import GymClient, GymField, GymRequestError, GymServerError

load_dotenv()
SEND_KEY = os.getenv("SEND_KEY", "")

logging.basicConfig(level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)])
log = logging.getLogger("rich")


def parse_args():
    parser = argparse.ArgumentParser(description="gymy daemon -- 百丽宫中关村羽毛球捡漏王已开启！")
    parser.add_argument("--days", nargs="+", type=int, default=[0], help="Days offset to monitor (e.g., --days 0 1 2)")
    parser.add_argument("--interval", type=int, default=600, help="Interval between checks (default: 600 secs)")
    parser.add_argument("--req-interval", type=int, default=10, help="Interval between requests (default: 10 secs)")
    parser.add_argument("--max-retries", type=int, default=3, help="Retry attempts for server errors (default: 3)")
    return parser.parse_args()


def fields_repr(fields: list[list[GymField]] | list[GymField]) -> str:
    """Format list of fields for logging."""
    if not fields:
        return ""

    # Handle single layer list (available fields)
    if isinstance(fields[0], GymField):
        field_descs = [f.field_desc for f in fields[:3]]
        suffix = "; ..." if len(fields) > 3 else ""
        return "; ".join(field_descs) + suffix

    # Handle list of lists (preferred field scenes)
    scene_descs = [str([f.field_desc for f in scene]) for scene in fields[:6]]
    suffix = "; ..." if len(fields) > 6 else ""
    return "; ".join(scene_descs) + suffix


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
    log.info(f"Notification server response: {resp.json()}")


async def start_normal_monitor(
    gym: GymClient,
    offsets: list[int],
    max_retries: int,
    req_interval: int,
) -> bool:
    """Normal monitoring strategy for 8:00-24:00 period."""

    days: list[str] = [gym.create_relative_date(offset) for offset in offsets]
    log.info(f"Checking field schedule for days: {days}")

    # Loop over each day offset via date
    for day, offset in zip(days, offsets):
        # Get available fields for the day
        fields_available: list[GymField] = await gym.get_available_fields(offset)

        # Create field scene candidates, sorted by preference
        field_candidates: list[list[GymField]] = gym.create_field_scenes_candidate(fields_available)
        if not field_candidates:
            log.info(f"No preferred fields available for {day}. Skipping...")
            continue

        log.info(f"{len(fields_available)} available fields for {day}:\n{fields_repr(fields_available)}")
        for field in field_candidates:
            # Try to create an order with preferred fields sequentially
            order_attempt_details: str = f"{day} {[f.field_desc for f in field]}"
            log.info(f"Attempting to create order for {order_attempt_details} ...")

            # Retry logic for server errors
            payment_url: str | None = None
            for i in range(max_retries):
                try:
                    payment_url = await gym.create_order(offset, day, field)
                    log.info(f"Success! Order created, continue to payment ->\n{payment_url}")
                    sc_send(
                        title="百丽宫羽毛球订单创建成功！",
                        desp=f"订单 **{order_attempt_details}** 已创建！\n"
                        f"请在10分钟内完成支付：\n\n[{payment_url}]({payment_url})",
                    )
                    return True

                # For known exceptions, make full use of retries
                except (GymServerError, GymRequestError) as e:
                    if i < max_retries - 1:
                        log.warning(f"Attempt {i + 1}/{max_retries} failed with: {e}. Retrying...")
                        await asyncio.sleep(req_interval if isinstance(e, GymRequestError) else 0.5)
                        continue
                    else:
                        log.error(f"Failed to create order after {max_retries} attempts: {e}")
                        sc_send(
                            title="百丽宫羽毛球订单创建失败",
                            desp=f"订单 **{order_attempt_details}** 创建失败：\n\n> {e}",
                        )
                        break

                # Catch all other unexpected exceptions and break out of the retry loop
                except Exception as e:
                    log.error(f"Unexpected error during order creation: {e}")
                    break

            else:
                # This else clause executes if the for loop completed without breaking
                # (i.e., all retries failed due to GymServerError)
                await asyncio.sleep(req_interval)
                continue

            # If we successfully created an order, break out of the field candidates loop
            if payment_url:
                return True

            await asyncio.sleep(req_interval)

    return False


async def start_eager_order(
    gym: GymClient,
    offsets: list[int],
    max_retries: int,
    req_interval: int,
) -> bool:
    """Proactive ordering strategy for 7:00-8:00 period."""
    log.info("Proactive ordering strategy is not implemented yet.")
    return False  # Placeholder for future implementation


async def start_daemon():
    args = parse_args()
    gym = GymClient()
    log.info("Starting daemon ... 百丽宫中关村羽毛球捡漏王已开启！")

    while True:
        try:
            await gym.setup()

            now = datetime.now().time()
            order_created = False

            # Hibernate period: 0:00 - 6:57
            if now.hour < 6 or (now.hour == 6 and now.minute < 58):
                log.info(f"Current time {now:%H:%M:%S}. Hibernating until 6:58.")
                # Calculate sleep duration until 6:58
                sleep_secs = ((6 - now.hour - 1) * 3600 + (58 - now.minute - 1) * 60 + (60 - now.second)) % (24 * 3600)
                if now.hour == 6:  # if current now.hour is 6, adjust sleep time
                    sleep_secs = (58 - now.minute - 1) * 60 + (60 - now.second)
                if sleep_secs <= 0:  # handle edge case if it's exactly 6:58 or a bit past
                    sleep_secs = 1  # sleep for a short duration and re-evaluate
                log.info(f"Sleeping for {sleep_secs} seconds.")
                await asyncio.sleep(sleep_secs)
                continue  # Re-evaluate time after waking up

            # Proactive ordering period: 6:58 - 7:59
            elif (now.hour == 6 and now.minute >= 58) or now.hour == 7:
                log.info(f"Current time {now:%H:%M:%S}. Starting proactive ordering strategy.")
                order_created = await start_eager_order(
                    gym=gym,
                    offsets=args.days,
                    max_retries=args.max_retries,
                    req_interval=args.req_interval,
                )
            # Normal monitoring period: 8:00 - 23:59
            elif now.hour >= 8:
                log.info(f"Current time {now:%H:%M:%S}. Starting normal monitoring strategy.")
                order_created = await start_normal_monitor(
                    gym=gym,
                    offsets=args.days,
                    max_retries=args.max_retries,
                    req_interval=args.req_interval,
                )
            else:
                # This case should ideally not be reached if logic is correct
                # but as a fallback, sleep for a bit and re-evaluate
                log.info(f"Current time {now:%H:%M:%S}. In an unexpected time slot. Sleeping for a short while.")
                await asyncio.sleep(60)
                continue

            # If order was created successfully, we can break or continue monitoring
            if order_created:
                break

            # Wait before the next check
            await asyncio.sleep(args.interval)

        except KeyboardInterrupt:
            log.info("Gracefully shutting down ...")
            break
        except Exception as e:
            log.exception(f"An error occurred in the daemon:\n{e}")
            await asyncio.sleep(args.interval)
            continue


if __name__ == "__main__":
    try:
        asyncio.run(start_daemon())
    except KeyboardInterrupt:
        log.info("Gracefully shutting down ...")
