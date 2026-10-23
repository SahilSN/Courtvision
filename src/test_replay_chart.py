import unittest

from replay_chart import build_replay_chart
from replay_collection import load_collection


class ReplayChartTest(unittest.TestCase):
    def test_legend_is_above_chart_and_lines_have_redundant_identity(self):
        for data, timeline in load_collection().values():
            chart = build_replay_chart(data, timeline, 0)
            self.assertGreater(chart.layout.legend.y, 1)
            self.assertEqual(chart.layout.legend.yanchor, "bottom")
            self.assertGreaterEqual(chart.layout.margin.b, 50)
            self.assertEqual([trace.line.dash for trace in chart.data], ["solid", "dash"])
            self.assertEqual([trace.name for trace in chart.data], [data["home"]["tricode"], data["away"]["tricode"]])
            self.assertAlmostEqual(chart.data[0].y[0] + chart.data[1].y[0], 100)
            self.assertEqual(chart.layout.shapes[0].x0, float(timeline.iloc[0].elapsedGameTime) / 60)
