import os
import re
import urllib.parse
from dataclasses import dataclass, fields
from datetime import datetime, timedelta

import hishel
import httpx
from dotenv import load_dotenv
from rich import box, print
from rich.table import Table

from config import field_pref_scores, fields_cfg, hour_pref_scores, hours_cfg, prices_cfg

load_dotenv()

TOKEN = os.getenv("TOKEN", "")
OPEN_ID = os.getenv("OPEN_ID", "")


@dataclass
class GymResponse:
    """Response type from the API."""

    code: int
    msg: str
    time: str
    data: dict | list | str | None

    @classmethod
    def from_json(cls, data):
        return cls(*[data.get(f.name) for f in fields(GymResponse)])


@dataclass
class GymField:
    """Internal representation of a gym field."""

    field_id: str
    hour_id: int
    day_type: str
    field_desc: str
    pref_score: int = 0  # Preference score for sorting, default is 0


class GymServerError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"Server returned error with status code: {status_code}")
        self.status_code = status_code


class GymRequestError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(f"Request failed with code {code}: {msg}")
        self.msg = msg


class GymClient:
    def __init__(self) -> None:
        self.token = TOKEN
        self.open_id = OPEN_ID
        self.headers = {
            "Host": "gym.dazuiwl.cn",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 "
            "NetType/WIFI MicroMessenger/6.8.0(0x16080000) MacWechat/3.8.10(0x13080a11) XWEB/1227 Flue",
            "token": self.token,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "*/*",
            "Origin": "http://gym.dazuiwl.cn",
            "Referer": "http://gym.dazuiwl.cn/h5/",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        }
        self.client = hishel.AsyncCacheClient(headers=self.headers)
        self.fields = None
        self.hours = None

    @staticmethod
    def create_relative_date(offset: int = 0) -> str:
        return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")

    @staticmethod
    async def parse_json_resp(resp: httpx.Response) -> dict | list | str | None:
        if resp.status_code != 200:
            raise GymServerError(resp.status_code)
        data = resp.json()
        data = GymResponse.from_json(data)
        if data.code != 1:
            raise GymRequestError(data.code, data.msg)
        return data.data

    async def setup(self) -> None:
        """Initial setup to fetch fields and hours."""
        try:
            fields = await self._get_sport_events_field()
            hours = await self._get_sport_events_hour()
            self.fields = fields
            self.hours = hours
        except Exception:
            # During peak hours, the server will fail to respond. Use hard-coded values if setup fails.
            print("Setup failed as server is overloaded, falling back to hard-coded values.")
        if self.fields is None:
            self.fields = fields_cfg
        if self.hours is None:
            self.hours = hours_cfg

    async def _create_gym_request(
        self,
        url: str,
        method: str = "GET",
        params: httpx._types.QueryParamTypes | None = None,
        data: httpx._types.RequestData | None = None,
        cache: bool = True,
    ):
        extensions = {"force_cache": True} if cache else {"cache_disabled": True}
        resp = await self.client.request(method, url, data=data, params=params, extensions=extensions)
        return await self.parse_json_resp(resp)

    async def _get_sport_events_field(self) -> dict:
        """
        Field ids: [220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231]
        Field names: [主馆1, 主馆2, 主馆3, 主馆4, 主馆5, 主馆6, 主馆7, 主馆8, 副馆9, 副馆10, 副馆11, 副馆12]
        """
        url = "http://gym.dazuiwl.cn/api/sport_events/field/id/51"
        data = await self._create_gym_request(url)
        return {k: v["name"] for k, v in data.items()}

    async def _get_sport_events_hour(self) -> dict:
        """
        Hour ids: [328228, 328229, 328230, 328231, 328232, 328233, 328234, 328235,
                328236, 328237, 328238, 328239, 328240, 328241]
        Hour names: [8-9, 9-10, 10-11, 11-12, 12-13, 13-14, 14-15, 15-16,
                    16-17, 17-18, 18-19, 19-20, 20-21, 21-22]
        Day types: [morning, day, night]
        """
        url = "http://gym.dazuiwl.cn/api/sport_events/hour/id/51"
        data = await self._create_gym_request(url)
        return {
            d["id"]: {
                "begin": d["begintime_text"],
                "end": d["endtime_text"],
                "create": d["createtime"],
                "daytype": d["daytype"],
            }
            for d in data
        }

    async def _get_sport_events_price(self, week: int, day: str) -> dict:
        """
        Day types: morning: 08:00 - 14:00, day: 14:00 - 18:00, night: 18:00 - 22:00
        Price (on weekdays): 10, 20, 50
        Price (on weekends): 20, 50, 50
        """
        url = "http://gym.dazuiwl.cn/api/sport_events/price/id/51"
        params = {"week": week, "day": day}
        return await self._create_gym_request(url, params=params)

    async def get_sport_schedule_booked(self, day: str) -> dict:
        """
        Schedule: {'<field_id>-<hour_id>': <status_id>, ...}
        Status: 0 - available, others - booked
        """
        url = "http://gym.dazuiwl.cn/api/sport_schedule/booked/id/51"
        return await self._create_gym_request(url, params={"day": day}, cache=False)

    async def get_prices(self, week: int, day: str) -> dict:
        """
        Wrapper around #_get_sport_events_price. Should this request fail, get stored
        prices immediately to fulfill the order at peak hours. Attempt order eagerly.
        """
        try:
            prices = await self._get_sport_events_price(week, day)
        except Exception:
            print("Prices are not available as server is overloaded, falling back to hard-coded values.")
            # Only difference is weekend v.s. weekday prices, perform check to see if target date is weekend
            prices = prices_cfg["weekend" if datetime.strptime(day, "%Y-%m-%d").weekday() >= 5 else "weekday"]
        return prices

    async def create_order(self, week: int, day: str, fields: list[GymField]) -> str:
        assert len(fields) > 0, "At least 1 field must be selected"
        assert len(fields) <= 2, "No more than 2 fields can be booked"
        field_ids = [f.field_id for f in fields]
        if len(field_ids) > 1:
            assert field_ids[0] == field_ids[1], "Fields must be the same for 2 bookings"
        field_id = field_ids[0]
        hour_ids = [f.hour_id for f in fields]
        if len(hour_ids) > 1:
            assert hour_ids[0] + 1 == hour_ids[1], "2 bookings must have consecutive hours"
        prices = await self.get_prices(week, day)
        money = [prices[f.day_type]["price"] for f in fields]
        money = sum(money)  # Total price for the booking

        url = "http://gym.dazuiwl.cn/api/order/submit"
        scene = [{"day": day, "fields": {field_id: hour_ids}}]
        # print(f"scene={scene}")
        # print(f"Creating order for day={day}, field_id={field_id}, hour_ids={hour_ids}, price={money}")

        # Construct order data
        data = {
            "orderid": "",
            "card_id": "",
            "sport_events_id": "51",
            "money": money,
            "ordertype": "makeappointment",
            "paytype": "bitpay",
            "scene": scene,
            "openid": OPEN_ID,
        }
        # Encode for legacy PHP compatibility
        data = urllib.parse.urlencode(data, quote_via=urllib.parse.quote, safe="", encoding="utf-8")
        data = data.replace("%27", "%22")  # Convert single quotes to double quotes

        resp = await self._create_gym_request(url, method="POST", data=data, cache=False)
        # Order response example:
        # <form id='alipaysubmit' name='wechatsubmit' action='https://pay.info.bit.edu.cn/pay/prepay' method='POST'>
        #   <input type='hidden' name='productBody' value='羽毛球'/>
        #   <input type='hidden' name='productDetail' value='中关村校区体育馆-羽毛球'/>
        #   <input type='hidden' name='spbillCreateIp' value='114.246.203.229'/>
        #   <input type='hidden' name='tenant' value='124012'/>
        #   <input type='hidden' name='tenantRedirectUrl' value='http://gym.dazuiwl.cn/api/order/epay/type/notify/paytype/bitpay'/>
        #   <input type='hidden' name='tenantTradeNumber' value='20250526105041351958'/>
        #   <input type='hidden' name='tenantUserCode' value='17778'/>
        #   <input type='hidden' name='tenantUserName' value='Spencer Woo'/>
        #   <input type='hidden' name='timestamp' value='1748227841'/>
        #   <input type='hidden' name='totalFee' value='1000'/>
        #   <input type='hidden' name='sign' value='EAD31E8013AA4C0E57D0C1407AA2ABD7'/>
        #   <input type='submit' value='ok' style='display:none;'>
        # </form>
        # <script>document.forms['wechatsubmit'].submit();</script>

        # Parse trade number from response and construct redirect URL for payment
        pattern = re.search(r"name='tenantTradeNumber' value='([^']+)'", resp)
        if pattern:
            trade_number = pattern.group(1)
            return f"http://gym.dazuiwl.cn/h5/#/pages/myBookingDetails/myBookingDetails?id={trade_number}"
        else:
            raise ValueError("Could not extract trade number from response")

    async def get_available_fields(self, offset: int = 0) -> list[GymField]:
        """Get available fields for booking on a specific day."""
        if self.fields is None or self.hours is None:
            await self.setup()

        day = self.create_relative_date(offset)
        schedule_booked = await self.get_sport_schedule_booked(day)

        available_fields = []
        for field_id, field_name in self.fields.items():
            for hour_id, hour in self.hours.items():
                # A non-0 schedule status means the field is not bookable
                if schedule_booked.get(f"{field_id}-{hour_id}", -1) != 0:
                    continue
                available_fields.append(
                    GymField(
                        field_id,
                        hour_id,
                        day_type=hour["daytype"],
                        field_desc=f"{field_name} ({hour['begin']}-{hour['end']})",
                    )
                )
        return available_fields

    @staticmethod
    def create_field_scenes_candidate(
        available_fields: list[GymField], consider_solo_fields: bool = False
    ) -> list[list[GymField]]:
        """Select and sort field scenes by preference scores, prepare for booking."""
        field_candidates = []
        for f in available_fields:
            field_pref = field_pref_scores.get(f.field_id, 0)
            hour_pref = hour_pref_scores.get(str(f.hour_id), 0)

            # Only consider fields with positive preferences
            if field_pref > 0 and hour_pref > 0:
                f.pref_score = field_pref + hour_pref
                field_candidates.append(f)

        # Check for consecutive hours (2 hours at most), and group them as tuples
        field_candidate_pairs = []

        for i, field1 in enumerate(field_candidates):
            for field2 in field_candidates[i + 1 :]:
                # Same field and consecutive hours
                if field1.field_id == field2.field_id and field2.hour_id == field1.hour_id + 1:
                    field_candidate_pairs.append([field1, field2])

        # Single fields are still considered if no pairs are found
        if not field_candidate_pairs and consider_solo_fields:
            # If no pairs found, add single fields as candidates
            # This allows booking single fields if no pairs are available
            field_candidate_pairs.extend([[f] for f in field_candidates])

        # Sort candidates by preference score
        field_candidate_pairs.sort(key=lambda x: sum(f.pref_score for f in x), reverse=True)
        return field_candidate_pairs


def show_schedule_table(day: str, schedule_booked: dict, fields: dict, hours: dict) -> None:
    table = Table(title=f"Schedule [{day}]", box=box.SQUARE)
    table.add_column("Field", justify="left", style="cyan", no_wrap=True)
    for hour_id, hour in hours.items():
        time_label = f"{hour['begin']}"
        table.add_column(time_label, justify="center", style="magenta", no_wrap=True)

    for field_id, field_name in fields.items():
        row = [field_name]
        for hour_id, hour in hours.items():
            status = schedule_booked.get(f"{field_id}-{hour_id}", -1)
            row.append(" " if status == 0 else "X")
        table.add_row(*row)

    print(table)


async def main():
    gym = GymClient()

    # today = 0, tomorrow = 1, day after tomorrow = 2
    offset = 1
    day = gym.create_relative_date(offset)
    await gym.setup()

    # Print schedule table
    schedule_booked = await gym.get_sport_schedule_booked(day)
    show_schedule_table(day, schedule_booked, gym.fields, gym.hours)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
