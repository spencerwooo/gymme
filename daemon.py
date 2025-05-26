import argparse
import asyncio
import logging
import os
import re

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
    data = resp.json()
    log.info(f"Notification server response: {data}")


async def start_daemon():
    args = parse_args()
    gym = GymClient()
    await gym._setup()
    log.info("Starting daemon ... 百丽宫中关村羽毛球捡漏王已开启！")

    while True:
        try:
            # Loop over each day offset via date
            days = [gym.create_relative_date(offset) for offset in args.days]
            log.info(f"Checking field schedule for days: {days}")

            for day, offset in zip(days, args.days):
                # Get available fields for the day
                fields_available = await gym.get_available_fields(offset)

                # Create field scene candidates, sorted by preference
                field_candidates = gym.create_field_scenes_candidate(fields_available)
                if not field_candidates:
                    log.info(f"No preferred fields available for {day}. Skipping...")
                    continue

                log.info(f"{len(fields_available)} available fields for {day}:\n{fields_repr(fields_available)}")
                for field in field_candidates:
                    # Try to create an order with preferred fields sequentially
                    order_attempt_details = f"{day} {[f.field_desc for f in field]}"
                    log.info(f"Attempting to create order for {order_attempt_details} ...")

                    # Retry logic for server errors
                    payment_url = None
                    for i in range(args.max_retries):
                        try:
                            payment_url = await gym.create_order(offset, day, field)
                            log.info(f"Success! Order created, continue to payment ->\n{payment_url}")
                            sc_send(
                                title="Order created successfully! 😊",
                                desp=f"Order **{order_attempt_details}** created!\n"
                                f"Please complete the payment within 10 minutes:\n\n[{payment_url}]({payment_url})",
                            )
                            break

                        # For known exceptions, make full use of retries
                        except (GymServerError, GymRequestError) as e:
                            if i < args.max_retries - 1:
                                log.warning(f"Attempt {i + 1}/{args.max_retries} failed with: {e}. Retrying...")
                                await asyncio.sleep(args.req_interval if isinstance(e, GymRequestError) else 0.5)
                                continue
                            else:
                                log.error(f"Failed to create order after {args.max_retries} attempts: {e}")
                                sc_send(
                                    title="Order creation failed 😥",
                                    desp=f"Order **{order_attempt_details}** failed to create:\n\n> {e}",
                                )
                                break

                        # Catch all other unexpected exceptions and break out of the retry loop
                        except Exception as e:
                            log.error(f"Unexpected error during order creation: {e}")
                            break

                    else:
                        # This else clause executes if the for loop completed without breaking
                        # (i.e., all retries failed due to GymServerError)
                        await asyncio.sleep(args.req_interval)
                        continue

                    # If we successfully created an order, break out of the field candidates loop
                    if payment_url:
                        break

                    await asyncio.sleep(args.req_interval)

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
