import unittest
import pandas as pd
from player_table_display import leaderboard_display


class PlayerTableDisplayTest(unittest.TestCase):
    def test_ranks_and_metrics_remain_numeric_for_frontend_sorting(self):
        original=pd.DataFrame({'NBA Rank':[100,10,2,1],'NBA Value Rank':[100,10,2,1],
                               'Rating':[99.1,110,120,153],'Season Value':[1.2,3.4,5.6,39.93],
                               'Reliability':[.74,.9,.95,.95]})
        before=original.copy(deep=True)
        result=leaderboard_display(original)
        for name in ('NBA Rank','NBA Impact Rank','Rating','Total Season Impact','Reliability'):
            self.assertTrue(pd.api.types.is_numeric_dtype(result[name]))
        self.assertEqual(result.sort_values('NBA Impact Rank')['NBA Impact Rank'].tolist(),[1,2,10,100])
        self.assertEqual(result.iloc[-1]['Rating'],153)
        self.assertEqual(result.iloc[-1]['Total Season Impact'],39.93)
        self.assertEqual(result.iloc[-1]['Reliability'],95)
        pd.testing.assert_frame_equal(original,before)
        partial=leaderboard_display(original,partial=True)
        self.assertEqual(partial.sort_values('Sample Impact Rank')['Sample Impact Rank'].tolist(),[1,2,10,100])

    def test_missing_rank_stays_missing_not_a_string(self):
        frame=pd.DataFrame({'NBA Rank':[None,2],'NBA Value Rank':[None,10],
                            'Rating':[100,101],'Season Value':[0,1],'Reliability':[0,.5]})
        result=leaderboard_display(frame)
        self.assertTrue(pd.isna(result['NBA Impact Rank'].iloc[0]))
        self.assertEqual(str(result['NBA Impact Rank'].dtype),'Int64')


if __name__=='__main__':unittest.main()
