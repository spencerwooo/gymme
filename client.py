import os
import re
import urllib.parse
from dataclasses import dataclass, fields
from datetime import datetime, timedelta

import hishel
from dotenv import load_dotenv
from rich import box, print
from rich.table import Table

from config import field_preference, hour_preference

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
        return cls(*[data.get(fld.name) for fld in fields(GymResponse)])


@dataclass
class GymField:
    """Internal representation of a gym field."""

    field_id: str
    hour_id: int
    day_type: str
    field_desc: str
    pref_score: int = 0  # Preference score for sorting, default is 0


class GymClient:
    def __new__(cls):
        """GymClient is a singleton."""

        if not hasattr(cls, "_instance"):
            cls._instance = super(GymClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.token = TOKEN
        self.open_id = OPEN_ID
        self.headers = {
            "Host": "gym.dazuiwl.cn",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 NetType/WIFI MicroMessenger/6.8.0(0x16080000) "
            "MacWechat/3.8.10(0x13080a11) XWEB/1227 Flue",
            "token": self.token,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "*/*",
            "Origin": "http://gym.dazuiwl.cn",
            "Referer": "http://gym.dazuiwl.cn/h5/",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Cache-Control": "max-stale=3600",  # Defaults to cache for 1 hour
        }
        self.client = hishel.AsyncCacheClient(headers=self.headers, timeout=10)  # Timeout set to 10 seconds
        self.fields = None
        self.hours = None

    @staticmethod
    def create_relative_date(offset=0):
        return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")

    @staticmethod
    async def parse_json_resp(resp):
        if resp.status_code != 200:
            raise Exception(f"Request failed with status code {resp.status_code}")
        data = resp.json()
        data = GymResponse.from_json(data)
        if data.code != 1:
            raise ValueError(f"Request failed with code {data.code}: {data.msg}")
        return data.data

    async def _setup(self):
        """Initial setup to fetch fields and hours (cached for 1 hour)."""
        fields = await self._get_sport_events_field()
        hours = await self._get_sport_events_hour()
        self.fields = fields
        self.hours = hours

    async def _create_gym_request(self, url, method="GET", params=None, data=None, cache=True):
        extensions = {} if cache else {"cache_disabled": True}
        resp = await self.client.request(method, url, data=data, params=params, extensions=extensions)
        return await self.parse_json_resp(resp)

    async def _get_sport_events_field(self):
        """
        Field ids: [220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231]
        Field names: [主馆1, 主馆2, 主馆3, 主馆4, 主馆5, 主馆6, 主馆7, 主馆8, 副馆9, 副馆10, 副馆11, 副馆12]
        """
        url = "http://gym.dazuiwl.cn/api/sport_events/field/id/51"
        data = await self._create_gym_request(url)
        return {k: v["name"] for k, v in data.items()}

    async def _get_sport_events_hour(self):
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

    async def _get_sport_events_price(self, week, day):
        """
        Day types: morning: 08:00 - 14:00, day: 14:00 - 18:00, night: 18:00 - 22:00
        Price (on weekdays): 10, 20, 50
        Price (on weekends): 20, 50, 50
        """
        url = "http://gym.dazuiwl.cn/api/sport_events/price/id/51"
        params = {"week": week, "day": day}
        return await self._create_gym_request(url, params=params)

    async def get_sport_schedule_booked(self, day):
        """
        Schedule: {'<field_id>-<hour_id>': <status_id>, ...}
        Status: 0 - available, others - booked
        """
        url = "http://gym.dazuiwl.cn/api/sport_schedule/booked/id/51"
        return await self._create_gym_request(url, params={"day": day}, cache=False)

    async def create_order(self, week, day, fields):
        assert len(fields) > 0, "At least 1 field must be selected"
        assert len(fields) <= 2, "No more than 2 fields can be booked"
        field_ids = [f.field_id for f in fields]
        if len(field_ids) > 1:
            assert field_ids[0] == field_ids[1], "Fields must be the same for 2 bookings"
        field_id = field_ids[0]
        hour_ids = [f.hour_id for f in fields]
        if len(hour_ids) > 1:
            assert hour_ids[0] + 1 == hour_ids[1], "2 bookings must have consecutive hours"
        prices = await self._get_sport_events_price(week, day)
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

    async def get_available_fields(self, offset):
        if self.fields is None or self.hours is None:
            await self._setup()

        day = self.create_relative_date(offset)
        # price = await self._get_sport_events_price(offset, day)
        schedule_booked = await self.get_sport_schedule_booked(day)

        available_fields = []
        for field_id, field_name in self.fields.items():
            for hour_id, hour in self.hours.items():
                status = schedule_booked.get(f"{field_id}-{hour_id}", -1)
                if status == 0:
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
    def create_field_scenes_candidate(available_fields):
        """Select and sort field scenes by preference scores, prepare for booking."""
        field_candidates = []
        for f in available_fields:
            field_pref = field_preference.get(f.field_id, 0)
            hour_pref = hour_preference.get(str(f.hour_id), 0)

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

        # Single fields are still considered
        field_candidate_pairs.extend([[f] for f in field_candidates])

        # Sort both pairs and singles by preference score
        field_candidate_pairs.sort(key=lambda x: sum(f.pref_score for f in x), reverse=True)
        return field_candidate_pairs


def show_schedule_table(day, schedule_booked, fields, hours):
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
    await gym._setup()
    schedule_booked = await gym.get_sport_schedule_booked(day)

    # Print schedule table
    show_schedule_table(day, schedule_booked, gym.fields, gym.hours)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
