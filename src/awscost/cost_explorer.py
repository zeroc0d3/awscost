import yaml
import os
from tabulate import tabulate
from datetime import datetime
from collections import OrderedDict
from .logger import get_logger
from .cost_explorer_client import CostExplorerClient
from . import constants
from .date_util import DateUtil


class CostExplorer:
    """
    convert responce data class.
    """

    def __init__(
        self,
        config=None,
        profile=None,
        granularity=None,
        point=None,
        start=None,
        end=None,
        dimensions=None,
        filter=None,
        metrics=None,
        aws_profile=None,
        debug=None,
        total=None,
    ):
        # read profile
        profile = self._read_profile(config, profile)

        self.granularity = (
            granularity or profile.get("granularity") or constants.DEFAULT_GRANULARITY
        )
        self.dimensions = (
            dimensions or profile.get("dimensions") or constants.DEFAULT_DIMENSIONS
        )
        self.metrics = metrics or profile.get("metrics") or constants.DEFAULT_METRICS
        self.total = total or profile.get("total") or constants.DEFAULT_TOTAL
        debug = debug or profile.get("debug") or constants.DEFAULT_DEBUG
        self.logger = get_logger(debug=debug)

        aws_profile = aws_profile or profile.get("aws_profile")
        filter = filter or profile.get("filter")
        point = point or profile.get("point") or constants.DEFAULT_POINT
        start = (
            start or profile.get("start") or DateUtil.get_start(self.granularity, point)
        )
        end = end or profile.get("end") or datetime.today().strftime("%Y-%m-%d")

        self.cost_explorer_client = CostExplorerClient(
            self.granularity,
            start,
            end,
            filter=filter,
            metrics=metrics,
            aws_profile=aws_profile,
            debug=debug,
        )

    def to_tabulate(self, tablefmt=None):
        """
        convert tabulate style.
        """
        data = self.get_cost_and_usage_total_and_group_by()
        converts = []
        for k, amounts in data.items():
            converts.append(dict({"key": k}, **amounts))
        last_time = list(converts[0].keys())[-1]
        converts = sorted(
            converts,
            key=lambda x: 0 if x.get(last_time) is None else x.get(last_time),
            reverse=True,
        )
        return tabulate(converts, headers="keys", tablefmt=tablefmt)

    def get_cost_and_usage_total_and_group_by(self):
        """
        start???end???????????????cost????????????????????????????????????total???group_by???merge??????
        """
        # total?????????
        total = self.get_cost_and_usage_total()

        # group by????????????????????????
        group_by_results = self.get_cost_and_usage_group_by()

        # total???0????????????group by???merge??????
        group_by_results_pad_zero = self.__class__.pad_zero(total, group_by_results)
        if self.total:
            merged = OrderedDict(total, **group_by_results_pad_zero)
            return merged
        return group_by_results_pad_zero

    def get_cost_and_usage_total(self):
        """
        start???end???????????????cost????????????????????????????????????
        """
        # total?????????
        cost_and_usage = self.cost_explorer_client.get_cost_and_usage()
        total = self._convert_results_total(cost_and_usage)
        return total

    def get_cost_and_usage_group_by(self):
        """
        start???end???????????????cost????????????????????????????????????
        """
        cost_and_usage_per_service = self.cost_explorer_client.get_cost_and_usage(
            dimensions=self.dimensions
        )
        results = self._convert_results_group_by(cost_and_usage_per_service)
        return results

    def _convert_results_group_by(self, cost_and_usage_per_service):
        """
        group-by??????????????????????????????????????????parse
        """
        results = OrderedDict()
        for result in cost_and_usage_per_service:
            start_period = result.get("TimePeriod").get("Start")
            time_key = self._convert_period(start_period)
            groups = result.get("Groups")
            for group in groups:
                group_by_key = ",".join(group.get("Keys"))
                if results.get(group_by_key) is None:
                    results[group_by_key] = OrderedDict()
                else:
                    results[group_by_key] = results.get(group_by_key)
                metrics = group.get("Metrics")
                amount = metrics.get(self.metrics).get("Amount")
                results[group_by_key][time_key] = round(float(amount), 2)
        return results

    def _convert_results_total(self, cost_and_usage_per_service):
        """
        Total?????????????????????parse
        """
        results = OrderedDict([("Total", OrderedDict())])
        for result in cost_and_usage_per_service:
            start_period = result.get("TimePeriod").get("Start")
            time_key = self._convert_period(start_period)
            metrics = result.get("Total")
            amount = metrics.get(self.metrics).get("Amount")
            results["Total"][time_key] = round(float(amount), 2)
        return results

    def _convert_period(self, start_period):
        """
        header???????????????????????????monthly???daily???????????????
        """
        if self.granularity == "MONTHLY":
            return datetime.strptime(start_period, "%Y-%m-%d").strftime("%Y-%m")
        return datetime.strptime(start_period, "%Y-%m-%d").strftime("%m-%d")

    def _read_profile(self, config, profile_name):
        config = config or constants.DEFAULT_CONFIG
        profile_name = profile_name or constants.DEFAULT_PROFILE
        if config and os.path.exists(config):
            profile = yaml.safe_load(open(config, encoding="UTF-8").read()).get(
                profile_name
            )
            if profile is None:
                profile = {}
        else:
            profile = {}
        return profile

    @staticmethod
    def pad_zero(total, group_by_results):
        """
        ??????0????????????
        """
        # 0?????????????????????dict?????????
        pad_zero = OrderedDict()
        for k, v in total.get("Total").items():
            pad_zero[k] = 0

        group_by_results_pad_zero = OrderedDict()
        for k, v in group_by_results.items():
            merged = OrderedDict(pad_zero, **v)
            group_by_results_pad_zero[k] = merged
        return group_by_results_pad_zero
