import unittest
import pandas as pd
from player_leaderboard_display import leaderboard_display


class PlayerTableDisplayTest(unittest.TestCase):
    def test_dashboard_season_change_is_numeric_from_100(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'dashboard/app.py').read_text())
        insertion = next(node for node in ast.walk(tree)
                         if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                         and isinstance(node.value.func, ast.Attribute)
                         and node.value.func.attr == 'insert'
                         and any(isinstance(arg, ast.Constant) and arg.value == 'Season Δ'
                                 for arg in node.value.args))
        frame = pd.DataFrame({'Rating': [134.2, 100.0, 89.7], 'Status': ['Provisional'] * 3})
        exec(compile(ast.Module(body=[insertion], type_ignores=[]), '<season-change>', 'exec'),
             {'leaderboard': frame})
        self.assertEqual(frame['Season Δ'].tolist(), [34.2, 0.0, -10.3])
        self.assertTrue(pd.api.types.is_numeric_dtype(frame['Season Δ']))
        self.assertEqual(list(frame), ['Rating', 'Season Δ', 'Status'])

    def test_ranks_and_metrics_remain_numeric_for_frontend_sorting(self):
        original=pd.DataFrame({'NBA Rank':[100,10,2,1],'NBA Value Rank':[100,10,2,1],
                               'Player':['A','B','C','D'],'Team':['DEN']*4,'Games':[3,4,10,65],'Status':['Qualified']*4,
                               'Rating':[99.1,110,120,153],'Season Value':[1.2,3.4,5.6,39.93],
                               'Reliability':[.74,.9,.95,.95]})
        before=original.copy(deep=True)
        result=leaderboard_display(original)
        self.assertEqual(list(result),['NBA Rank','Player','Team','Games','Rating','Status'])
        for name in ('NBA Rank','Games','Rating'):
            self.assertTrue(pd.api.types.is_numeric_dtype(result[name]))
        self.assertEqual(result.sort_values('NBA Rank')['NBA Rank'].tolist(),[1,2,10,100])
        self.assertEqual(result.iloc[-1]['Rating'],153)
        pd.testing.assert_frame_equal(original,before)
        partial=leaderboard_display(original,partial=True)
        self.assertEqual(partial.sort_values('Sample Rank')['Sample Rank'].tolist(),[1,2,10,100])

    def test_missing_rank_stays_missing_not_a_string(self):
        frame=pd.DataFrame({'NBA Rank':[None,2],'NBA Value Rank':[None,10],
                            'Player':['A','B'],'Team':['DEN']*2,'Games':[3,4],'Status':['Provisional']*2,
                            'Rating':[100,101],'Season Value':[0,1],'Reliability':[0,.5]})
        result=leaderboard_display(frame)
        self.assertTrue(pd.isna(result['NBA Rank'].iloc[0]))
        self.assertEqual(str(result['NBA Rank'].dtype),'Int64')


if __name__=='__main__':unittest.main()
