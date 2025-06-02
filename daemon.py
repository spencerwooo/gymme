import argparse
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from enum import Enum

import httpx
from dotenv import load_dotenv
from rich.logging import RichHandler

from client import GymClient, GymField
from errors import GymOverbookedError, GymRequestError, GymRequestRateLimitedError, GymServerError

load_dotenv()
SEND_KEY = os.getenv("SEND_KEY", "")

logging.basicConfig(level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)])
log = logging.getLogger("rich")


def parse_args():
    parser = argparse.ArgumentParser(description="gymy daemon -- 百丽宫中关村羽毛球捡漏王已开启！")
    parser.add_argument("--days", nargs="+", type=int, default=[0], help="Days offset to monitor (e.g., --days 0 1 2)")
    parser.add_argument("--req-interval", type=int, default=10, help="Interval between requests to avoid rate limits")
    parser.add_argument("--interval", type=int, default=600, help="Interval between checks")
    parser.add_argument("--eager-interval", type=int, default=60, help="Interval for eager checking")
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent order attempts during eager mode")
    parser.add_argument("--refresh-time", type=str, default="07:00", help="Schedule refresh time (HH:MM format)")
    parser.add_argument("--max-retries", type=int, default=5, help="Retry attempts for server errors")
    parser.add_argument("--consider-solo-fields", action="store_true", help="Consider solo fields (1 hour)")
    return parser.parse_args()


def banner_repr() -> str:
    return (
        "\n"
        "      ___           ___           ___           ___     \n"
        "     /\\  \\         |\\__\\         /\\__\\         |\\__\\    \n"
        "    /::\\  \\        |:|  |       /::|  |        |:|  |   \n"
        "   /:/\\:\\  \\       |:|  |      /:|:|  |        |:|  |   \n"
        "  /:/  \\:\\  \\      |:|__|__   /:/|:|__|__      |:|__|__ \n"
        " /:/__/_\\:\\__\\     /::::\\__\\ /:/ |::::\\__\\     /::::\\__\\\n"
        " \\:\\  /\\ \\/__/    /:/~~/~    \\/__/~~/:/  /    /:/~~/~   \n"
        "  \\:\\ \\:\\__\\     /:/  /            /:/  /    /:/  /     \n"
        "   \\:\\/:/  /     \\/__/            /:/  /     \\/__/      \n"
        "    \\::/  /                      /:/  /                 \n"
        "     \\/__/                       \\/__/                  \n"
        "\n"
    )


def fields_repr(fields: list[list[GymField]] | list[GymField]) -> str:
    """Format list of fields for logging."""
    if not fields:
        return ""

    # Handle single layer list (available fields)
    if isinstance(fields[0], GymField):
        field_descs = [f.field_desc for f in fields[:8]]  # Cut-off on first 8 fields
        suffix = ", ..." if len(fields) > 8 else ""
        return ", ".join(field_descs) + suffix

    # Handle list of lists (preferred field scenes)
    scene_descs = [str([f.field_desc for f in scene]) for scene in fields[:16]]
    suffix = ", ..." if len(fields) > 16 else ""
    return ", ".join(scene_descs) + suffix


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


async def request_with_retry(request_fn, max_retries: int, req_interval: float = None):
    for i in range(max_retries):
        try:
            return await request_fn()
        except GymRequestRateLimitedError as e:
            if i < max_retries - 1:
                delay = req_interval or 0.5
                log.warning(f"Rate limited: {e}. Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
                continue
            raise
        except (GymRequestError, GymServerError, httpx.HTTPError) as e:
            if i < max_retries - 1:
                log.warning(f"Attempt {i + 1}/{max_retries} failed: {e}. Retrying immediately...")
                await asyncio.sleep(0.5)  # Short delay before retrying
                continue
            raise
    raise Exception(f"Request failed after {max_retries} attempts")


async def make_order_attempt(
    gym: GymClient,
    offset: int,
    day: str,
    field: list[GymField],
    max_retries: int,
    req_interval: int,
) -> bool:
    order_attempt_details = f"{day} {[f.field_desc for f in field]}"
    log.info(f"Attempting to create order for {order_attempt_details} ...")

    async def _make_order_fn():
        return await gym.create_order(offset, day, field)

    try:
        payment_url = await request_with_retry(_make_order_fn, max_retries, req_interval)

        log.info(f"Success! Order created, continue to payment ->\n{payment_url}")
        sc_send(
            title="百丽宫羽毛球订单创建成功！",
            desp=f"订单 **{order_attempt_details}** 已创建！\n请在10分钟内完成支付：\n\n[{payment_url}]({payment_url})",
        )
        return True

    except GymOverbookedError as e:
        log.warning(f"Attempting to recover latest order: {e}.")
        return await recover_latest_order(gym)

    except Exception as e:
        log.error(f"Failed to create order for {order_attempt_details}: {e}")
        return False


async def recover_latest_order(gym: GymClient) -> bool:
    orders = await gym.get_orders(status="created", limit=1)

    if not orders:
        log.error("No created orders found. Unable to recover latest order.")
        return False

    order_id = orders[0]["orderid"]
    payment_url = f"http://gym.dazuiwl.cn/h5/#/pages/myBookingDetails/myBookingDetails?id={order_id}"
    log.info(f"Successfully recovered order ({order_id}). Continue to payment ->\n{payment_url}")
    sc_send(
        title="百丽宫羽毛球订单创建成功！",
        desp=f"订单 **{order_id}** 已创建！\n请在10分钟内完成支付：\n\n[{payment_url}]({payment_url})",
    )
    return True


async def start_normal_monitor(
    gym: GymClient,
    offsets: list[int],
    max_retries: int,
    req_interval: int,
    consider_solo_fields: bool = False,
) -> bool:
    """Normal monitoring strategy."""
    days = [gym.create_relative_date(offset) for offset in offsets]
    log.info(f"Checking field schedule for days: {days}")

    # Loop over each day offset via date
    for day, offset in zip(days, offsets):
        # Get available fields for the day
        fields_available = await gym.get_available_fields(offset)
        if fields_available:
            log.info(f"{len(fields_available)} available fields for {day}:\n{fields_repr(fields_available)}")

        # Create field scene candidates, sorted by preference
        field_candidates = gym.create_field_scenes_candidate(fields_available, consider_solo_fields)
        if not field_candidates:
            log.info(f"No preferred fields available for {day}. Skipping...")
            continue

        # Sequentially attempt to create orders for each field scene
        for field in field_candidates:
            order_succeeded = await make_order_attempt(
                gym=gym,
                offset=offset,
                day=day,
                field=field,
                max_retries=max_retries,
                req_interval=req_interval,
            )

            if order_succeeded:
                return True  # Exit if an order was successfully created
            else:
                await asyncio.sleep(req_interval)

    return False


async def start_eager_monitor(
    gym: GymClient,
    max_retries: int,
    req_interval: int,
    concurrency: int = 3,
    target_time: str = "07:00",
) -> bool:
    """Eager ordering strategy for peak hours."""
    # Only activate for day with offset=2 (day after tomorrow)
    offset = 2
    day = gym.create_relative_date(offset)

    # (Warm up) Load available fields for the day and create candidates used for the entire period
    fields_available = await gym.get_available_fields(offset)
    field_candidates = gym.create_field_scenes_candidate(fields_available)
    if not field_candidates:
        log.info(f"No preferred fields available for {day}.")
        return False

    log.info(f"{len(fields_available)} available fields for {day}:\n{fields_repr(fields_available)}")

    # Fire off at exactly target_time (default: 7:00 AM)
    now = datetime.now().time()
    target_time = datetime.strptime(target_time, "%H:%M").time()
    if now < target_time:
        delay = (datetime.combine(datetime.now().date(), target_time) - datetime.now()).total_seconds()
        log.info(f"Warmed up. Waiting {delay:.0f} seconds until 7:00 AM...")
        await asyncio.sleep(delay)

    # Process field candidates in batches based on concurrency
    for i in range(0, len(field_candidates), concurrency):
        batch = field_candidates[i : i + concurrency]

        # Create tasks for concurrent order attempts
        tasks = []
        for field in batch:
            task = make_order_attempt(
                gym=gym,
                offset=offset,
                day=day,
                field=field,
                max_retries=max_retries,
                req_interval=req_interval,
            )
            tasks.append(task)

        # Execute batch concurrently and wait for any successful order
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check if any order in the batch succeeded
        for result in results:
            if isinstance(result, bool) and result:
                return True

        # If no order succeeded in this batch, continue to next batch
        if i + concurrency < len(field_candidates):
            await asyncio.sleep(req_interval)

    return False


class StrategyMode(Enum):
    NORMAL = "normal"
    EAGER = "eager"
    HIBERNATE = "hibernate"

    @classmethod
    def from_time(
        cls,
        now: datetime.time,
        eager_time: tuple[str, str] = ("6:55", "7:29"),
        normal_time: tuple[str, str] = ("7:30", "23:59"),
    ) -> "StrategyMode":
        """Resolve strategy mode based on current time."""

        def parse_time(time_str: str) -> datetime.time:
            """Parse time string in HH:MM format to datetime.time object."""
            return datetime.strptime(time_str, "%H:%M").time()

        eager_start = parse_time(eager_time[0])
        eager_end = parse_time(eager_time[1])
        normal_start = parse_time(normal_time[0])
        normal_end = parse_time(normal_time[1])

        if eager_start <= now <= eager_end:
            return cls.EAGER
        elif normal_start <= now <= normal_end:
            return cls.NORMAL
        else:
            return cls.HIBERNATE


async def daemon_sleep(
    mode: StrategyMode,
    eager_interval: int,
    normal_interval: int,
    eager_start: str = "06:55",
) -> None:
    """Automatically resolve sleep interval based on the current time and strategy mode."""
    match mode:
        case StrategyMode.HIBERNATE:
            now = datetime.now()

            # Parse target eager start time
            eager_start_time = datetime.strptime(eager_start, "%H:%M").time()
            target_datetime = datetime.combine(now.date(), eager_start_time)

            # If current time is past today's eager start, target tomorrow's start time
            if now.time() >= eager_start_time:
                target_datetime += timedelta(days=1)

            # Time to sleep until the next eager start time, minimum 1 second
            interval = max(int((target_datetime - now).total_seconds()), 1)

        case StrategyMode.EAGER:
            interval = eager_interval

        case StrategyMode.NORMAL:
            interval = normal_interval

        case _:
            interval = 60  # Default fallback interval (1 minute)

    await asyncio.sleep(interval)


async def start_daemon():
    args = parse_args()
    gym = GymClient()
    log.info("百丽宫中关村羽毛球捡漏王已开启！")
    log.info(banner_repr())

    while True:
        # Resolve strategy mode based on current time first
        now = datetime.now().time()
        strategy = StrategyMode.from_time(now)

        # Only setup connection if not hibernating to avoid unnecessary requests
        if strategy != StrategyMode.HIBERNATE:
            await gym.setup()

        order_created = False
        try:
            match strategy:
                # Hibernate period: 0:00 - 6:54
                case StrategyMode.HIBERNATE:
                    log.info(f"Current time [{now:%H:%M:%S}]. Daemon hibernating ...")

                # Eager ordering period: 6:55 - 7:29
                case StrategyMode.EAGER:
                    log.info(f"Current time [{now:%H:%M:%S}]. Starting eager ordering strategy.")
                    order_created = await start_eager_monitor(
                        gym=gym,
                        max_retries=args.max_retries,
                        req_interval=args.req_interval,
                        concurrency=args.concurrency,
                        target_time=args.refresh_time,
                    )

                # Normal monitoring period: 7:30 - 23:59
                case StrategyMode.NORMAL:
                    log.info(f"Current time [{now:%H:%M:%S}]. Starting normal monitoring strategy.")
                    order_created = await start_normal_monitor(
                        gym=gym,
                        offsets=args.days,
                        max_retries=args.max_retries,
                        req_interval=args.req_interval,
                        consider_solo_fields=args.consider_solo_fields,
                    )

            # Break the loop if an order was successfully created
            if order_created:
                break

        except (GymRequestError, GymServerError, httpx.HTTPError) as e:
            retry_interval = args.req_interval if isinstance(e, GymRequestRateLimitedError) else 0.5
            log.error(f"Strategy execution failed: {e}. Retrying in {retry_interval} seconds.")
            await asyncio.sleep(retry_interval)
            continue

        except Exception as e:
            log.exception(f"Unexpected error in daemon loop: {e}")
            await asyncio.sleep(args.req_interval)
            continue

        # Wait before the next check
        await daemon_sleep(strategy, args.eager_interval, args.interval)


if __name__ == "__main__":
    try:
        asyncio.run(start_daemon())
    except KeyboardInterrupt:
        log.info("Gracefully shutting down ...")
