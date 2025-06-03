import argparse
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

import httpx
from dotenv import load_dotenv
from rich.logging import RichHandler

from gymme.client import GymClient, GymField
from gymme.errors import GymOverbookedError, GymRequestError, GymRequestRateLimitedError, GymServerError


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


class GymDaemon:
    def __init__(
        self,
        days: list[int],
        req_interval: int,
        interval: int,
        eager_interval: int,
        concurrency: int,
        refresh_time: str,
        max_retries: int,
        consider_solo_fields: bool,
        config_path: str | None = None,
        token: str = "",
        open_id: str = "",
        send_key: str = "",
        log: logging.Logger = None,
    ):
        """Gymme Daemon for monitoring and eagerly creating orders for gym fields.

        Strategy Modes:
        - Hibernate mode (休眠模式): 00:00-06:54 - Daemon sleeps to conserve resources during inactive hours.
        - Eager mode (抢单模式): 06:55-07:29 - Aggressively attempts to create orders at schedule refresh time (07:00).
        - Normal mode (捡漏模式): 07:30-23:59 - Monitors available fields and attempts to create orders based on preferences.

        Args:
            days (list[int]): List of day offsets to monitor (e.g., [0, 1, 2] for today, tomorrow, day after).
            req_interval (int): Time interval between API requests in seconds to avoid rate limits.
            interval (int): Time interval between monitoring cycles in normal mode (seconds).
            eager_interval (int): Time interval between attempts in eager mode (seconds).
            concurrency (int): Maximum number of concurrent booking attempts during eager mode.
            refresh_time (str): Time when new bookings become available (format: "HH:MM").
            max_retries (int): Maximum number of retry attempts for failed requests.
            consider_solo_fields (bool): Whether to consider single-person fields for booking.
            token (str, optional): Authentication token for gym API. Defaults to "".
            open_id (str, optional): OpenID for user identification. Defaults to "".
            send_key (str, optional): Key for sending notifications via ServerChan. Defaults to "".
            log (logging.Logger, optional): Custom logger instance. Defaults to None.
        """

        self.days = days
        self.req_interval = req_interval
        self.interval = interval
        self.eager_interval = eager_interval
        self.concurrency = concurrency
        self.refresh_time = refresh_time
        self.max_retries = max_retries
        self.consider_solo_fields = consider_solo_fields
        self.config_path = config_path
        self.send_key = send_key
        self.log = log or logging.getLogger(__name__)
        self.gym = GymClient(token, open_id, sport_id=51)
        self.banner = """

      ___       ___          ___          ___          ___     
     /\\  \\     |\\__\\        /\\__\\        /\\__\\        /\\  \\    
    /::\\  \\    |:|  |      /::|  |      /::|  |      /::\\  \\   
   /:/\\:\\  \\   |:|  |     /:|:|  |     /:|:|  |     /:/\\:\\  \\  
  /:/  \\:\\  \\  |:|__|__  /:/|:|__|__  /:/|:|__|__  /::\\~\\:\\  \\ 
 /:/__/_\\:\\__\\ /::::\\__\\/:/ |::::\\__\\/:/ |::::\\__\\/:/\\:\\ \\:\\__\\
 \\:\\  /\\ \\/__//:/~~/~   \\/__/~~/:/  /\\/__/~~/:/  /\\:\\~\\:\\ \\/__/
  \\:\\ \\:\\__\\ /:/  /           /:/  /       /:/  /  \\:\\ \\:\\__\\  
   \\:\\/:/  / \\/__/           /:/  /       /:/  /    \\:\\ \\/__/  
    \\::/  /                 /:/  /       /:/  /      \\:\\__\\    
     \\/__/                  \\/__/        \\/__/        \\/__/    

"""

    @staticmethod
    def _fields_repr(fields: list[list[GymField]] | list[GymField]) -> str:
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

    def _sc_send(self, title: str, desp: str = "") -> None:
        """Send notification using ServerChan."""
        if not self.send_key:
            return

        if self.send_key.startswith("sctp"):
            match = re.match(r"sctp(\d+)t", self.send_key)
            if match:
                num = match.group(1)
                url = f"https://{num}.push.ft07.com/send/{self.send_key}.send"
            else:
                raise ValueError("Invalid sendkey format for sctp")
        else:
            url = f"https://sctapi.ftqq.com/{self.send_key}.send"
        params = {"title": title, "desp": desp}
        headers = {"Content-Type": "application/json;charset=utf-8"}
        resp = httpx.post(url, json=params, headers=headers)
        self.log.info(f"Notification server response: {resp.json()}")

    async def _request_with_retry(
        self, request_fn: Callable[[Any], Any], max_retries: int, req_interval: float = None
    ) -> Any:
        """Retry wrapper for requests to handle rate limits and server errors."""
        for i in range(max_retries):
            try:
                return await request_fn()
            except GymRequestRateLimitedError as e:
                if i < max_retries - 1:
                    delay = req_interval or 0.5
                    self.log.warning(f"Rate limited: {e}. Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    continue
                raise
            except (GymRequestError, GymServerError, httpx.HTTPError) as e:
                if i < max_retries - 1:
                    self.log.warning(f"Attempt {i + 1}/{max_retries} failed: {e}. Retrying immediately...")
                    await asyncio.sleep(0.5)  # Short delay before retrying
                    continue
                raise
        raise Exception(f"Request failed after {max_retries} attempts")

    async def _make_order_attempt(self, offset: int, day: str, field: list[GymField]) -> bool:
        """Attempt to create an order for a specific field on a given day with retries enabled."""
        order_attempt_details = f"{day} {[f.field_desc for f in field]}"
        self.log.info(f"Attempting to create order for {order_attempt_details} ...")

        async def _make_order_fn():
            return await self.gym.create_order(offset, day, field)

        try:
            payment_url = await self._request_with_retry(_make_order_fn, self.max_retries, self.req_interval)

            self.log.info(f"Success! Order created, continue to payment ->\n{payment_url}")
            self._sc_send(
                title="百丽宫羽毛球订单创建成功！",
                desp=f"订单 **{order_attempt_details}** 已创建！\n请在10分钟内完成支付：\n\n[{payment_url}]({payment_url})",
            )
            return True

        except GymOverbookedError as e:
            self.log.warning(f"Attempting to recover latest order: {e}.")
            return await self._recover_latest_order()

        except Exception as e:
            self.log.error(f"Failed to create order for {order_attempt_details}: {e}")
            return False

    async def _recover_latest_order(self) -> bool:
        """Attempt to recover the latest created order if the server responded with user overbooked error."""
        orders = await self.gym.get_orders(status="created", limit=1)

        if not orders:
            self.log.error("No created orders found. Unable to recover latest order.")
            return False

        order_id = orders[0]["orderid"]
        payment_url = f"http://gym.dazuiwl.cn/h5/#/pages/myBookingDetails/myBookingDetails?id={order_id}"
        self.log.info(f"Successfully recovered order ({order_id}). Continue to payment ->\n{payment_url}")
        self._sc_send(
            title="百丽宫羽毛球订单创建成功！",
            desp=f"订单 **{order_id}** 已创建！\n请在10分钟内完成支付：\n\n[{payment_url}]({payment_url})",
        )
        return True

    async def start_normal_monitor(self) -> bool:
        """Normal monitoring strategy -- 捡漏模式

        This strategy checks available fields for the next few days and attempts to create orders
        based on field preferences and availability.

        1. Iterates over specified days to look at the booking schedules.
        2. For each day, retrieves available fields and creates candidates based on preferences.
        3. Attempts to create orders for each candidate field sequentially.
        4. If an order is successfully created, exits the loop.

        Returns:
            bool: True if an order was successfully created, False otherwise.
        """

        offsets = self.days
        days = [self.gym.create_relative_date(offset) for offset in offsets]
        self.log.info(f"Checking field schedule for days: {days}")

        # Loop over each day offset via date
        for day, offset in zip(days, offsets):
            # Get available fields for the day
            fields_available = await self.gym.get_available_fields(offset)
            if fields_available:
                self.log.info(
                    f"{len(fields_available)} available fields for {day}:\n{self._fields_repr(fields_available)}"
                )

            # Create field scene candidates, sorted by preference
            field_candidates = self.gym.create_field_scenes_candidate(
                self.config_path, fields_available, self.consider_solo_fields
            )
            if not field_candidates:
                self.log.info(f"No preferred fields available for {day}. Skipping...")
                continue

            # Sequentially attempt to create orders for each field scene
            for field in field_candidates:
                order_succeeded = await self._make_order_attempt(offset, day, field)

                if order_succeeded:
                    return True  # Exit if an order was successfully created
                else:
                    await asyncio.sleep(self.req_interval)

        return False

    async def start_eager_monitor(self) -> bool:
        """Eager ordering strategy for peak hours -- 抢单模式

        This strategy is designed to quickly attempt to create orders for the day after tomorrow (offset=2)
        at the specified refresh time (default: 7:00 AM) when new fields become available.

        1. Only activates for the day after tomorrow (offset=2).
        2. Retrieves available fields for that day and creates candidates based on preferences.
        3. Waits until the specified refresh time to start making order attempts.
        4. Processes field candidates in batches based on concurrency.
        5. Attempts to create orders concurrently for each batch of field candidates.
        6. If an order is successfully created, attempts to notify the user before exiting the loop.

        Returns:
            bool: True if an order was successfully created, False otherwise.
        """

        # Only activate for day with offset=2 (day after tomorrow)
        offset = 2
        day = self.gym.create_relative_date(offset)

        # (Warm up) Load available fields for the day and create candidates used for the entire period
        fields_available = await self.gym.get_available_fields(offset)
        field_candidates = self.gym.create_field_scenes_candidate(
            self.config_path, fields_available, self.consider_solo_fields
        )
        if not field_candidates:
            self.log.info(f"No preferred fields available for {day}.")
            return False

        self.log.info(f"{len(fields_available)} available fields for {day}:\n{self._fields_repr(fields_available)}")

        # Fire off at exactly target_time (default: 7:00 AM)
        now = datetime.now().time()
        target_time = datetime.strptime(self.refresh_time, "%H:%M").time()
        if now < target_time:
            delay = (datetime.combine(datetime.now().date(), target_time) - datetime.now()).total_seconds()
            self.log.info(f"Warmed up. Waiting {delay:.0f} seconds until 7:00 AM...")
            await asyncio.sleep(delay)

        # Process field candidates in batches based on concurrency
        for i in range(0, len(field_candidates), self.concurrency):
            batch = field_candidates[i : i + self.concurrency]

            # Create tasks for concurrent order attempts
            tasks = []
            for field in batch:
                task = self._make_order_attempt(offset, day, field)
                tasks.append(task)

            # Execute batch concurrently and wait for any successful order
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check if any order in the batch succeeded
            for result in results:
                if isinstance(result, bool) and result:
                    return True

            # If no order succeeded in this batch, continue to next batch
            if i + self.concurrency < len(field_candidates):
                await asyncio.sleep(self.req_interval)

        return False

    async def daemon_sleep(self, mode: StrategyMode, eager_start: str = "06:55") -> None:
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
                interval = self.eager_interval

            case StrategyMode.NORMAL:
                interval = self.interval

            case _:
                interval = 60  # Default fallback interval (1 minute)

        await asyncio.sleep(interval)

    async def start(self) -> None:
        self.log.info("百丽宫中关村羽毛球捡漏王已开启！")
        self.log.info(self.banner)

        while True:
            # Resolve strategy mode based on current time first
            now = datetime.now().time()
            strategy = StrategyMode.from_time(now)

            # Only setup connection if not hibernating to avoid unnecessary requests
            if strategy != StrategyMode.HIBERNATE:
                await self.gym.setup()

            order_created = False
            try:
                match strategy:
                    # Hibernate period: 0:00 - 6:54
                    case StrategyMode.HIBERNATE:
                        self.log.info(f"Current time [{now:%H:%M:%S}]. Daemon hibernating ...")

                    # Eager ordering period: 6:55 - 7:29
                    case StrategyMode.EAGER:
                        self.log.info(f"Current time [{now:%H:%M:%S}]. Starting eager ordering strategy.")
                        order_created = await self.start_eager_monitor()

                    # Normal monitoring period: 7:30 - 23:59
                    case StrategyMode.NORMAL:
                        self.log.info(f"Current time [{now:%H:%M:%S}]. Starting normal monitoring strategy.")
                        order_created = await self.start_normal_monitor()

                # Break the loop if an order was successfully created
                if order_created:
                    break

            except (GymRequestError, GymServerError, httpx.HTTPError) as e:
                retry_interval = self.req_interval if isinstance(e, GymRequestRateLimitedError) else 0.5
                self.log.error(f"Strategy execution failed: {e}. Retrying in {retry_interval} seconds.")
                await asyncio.sleep(retry_interval)
                continue

            except Exception as e:
                self.log.exception(f"Unexpected error in daemon loop: {e}")
                await asyncio.sleep(self.req_interval)
                continue

            # Wait before the next check
            await self.daemon_sleep(strategy)


def parse_args():
    parser = argparse.ArgumentParser(description="gymme daemon -- 百丽宫中关村羽毛球捡漏王已开启！")
    parser.add_argument("--days", nargs="+", type=int, default=[0], help="Days offset to monitor (e.g., --days 0 1 2)")
    parser.add_argument("--req-interval", type=int, default=10, help="Interval between requests to avoid rate limits")
    parser.add_argument("--interval", type=int, default=600, help="Interval between checks")
    parser.add_argument("--eager-interval", type=int, default=60, help="Interval for eager checking")
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent order attempts during eager mode")
    parser.add_argument("--refresh-time", type=str, default="07:00", help="Schedule refresh time (HH:MM format)")
    parser.add_argument("--max-retries", type=int, default=5, help="Retry attempts for server errors")
    parser.add_argument("--consider-solo-fields", action="store_true", help="Consider solo fields (1 hour)")
    return parser.parse_args()


async def start_daemon():
    load_dotenv()
    token = os.getenv("TOKEN", "")
    open_id = os.getenv("OPEN_ID", "")
    send_key = os.getenv("SEND_KEY", "")

    args = parse_args()
    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    log = logging.getLogger(__name__)

    daemon = GymDaemon(
        days=args.days,
        req_interval=args.req_interval,
        interval=args.interval,
        eager_interval=args.eager_interval,
        concurrency=args.concurrency,
        refresh_time=args.refresh_time,
        max_retries=args.max_retries,
        consider_solo_fields=args.consider_solo_fields,
        token=token,
        open_id=open_id,
        send_key=send_key,
        log=log,
    )
    await daemon.start()


def main():
    try:
        asyncio.run(start_daemon())
    except KeyboardInterrupt:
        print("Gracefully shutting down ...")


if __name__ == "__main__":
    main()
