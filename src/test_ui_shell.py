import unittest
from streamlit.testing.v1 import AppTest
from ui_shell import feature_label, workspace_label, time_label


class ShellTest(unittest.TestCase):
    def test_labels_do_not_change_underlying_navigation_values(self):
        script='''import streamlit as st
from ui_shell import apply_shell, sidebar_brand, feature_label, workspace_label
apply_shell()
sidebar_brand()
st.sidebar.radio('Workspace',['Season Intelligence','Live Beta'],format_func=workspace_label,key='workspace')
st.sidebar.radio('Explore',['Teams','Players','Player Career','Replay Pilot'],format_func=feature_label,key='feature')
'''
        app=AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        app.sidebar.radio(key='feature').set_value('Player Career').run()
        self.assertEqual(app.sidebar.radio(key='feature').value,'Player Career')
        self.assertIn('Player careers',app.sidebar.radio(key='feature').options)
        app.sidebar.radio(key='workspace').set_value('Live Beta').run()
        self.assertEqual(app.sidebar.radio(key='workspace').value,'Live Beta')
        self.assertEqual(feature_label('Replay Pilot'),'Replay collection')
        self.assertEqual(workspace_label('Live Beta'),'Live · Game Center')

    def test_headings_escape_content_and_keep_semantic_title(self):
        app=AppTest.from_string("from ui_shell import page_heading\npage_heading('<script>','A & B','2026–27')").run()
        self.assertFalse(app.exception)
        html=app.markdown[0].value
        self.assertIn('<h1>&lt;script&gt;</h1>',html)
        self.assertIn('A &amp; B',html)

    def test_times_are_short_pacific_and_never_invented(self):
        self.assertEqual(time_label('2026-10-27T05:20:00+00:00'),'Oct 26 · 10:20 PM PT')
        for invalid in ('not-a-time',None,'2026-10-26T22:20:00'):
            self.assertEqual(time_label(invalid),'Unknown')


if __name__=='__main__':
    unittest.main()
