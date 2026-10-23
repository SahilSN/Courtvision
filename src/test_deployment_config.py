import unittest

from deployment_config import get_deployment_profile, navigation_modes


class DeploymentConfigTest(unittest.TestCase):
    def test_local_default_preserves_full_navigation(self):
        self.assertEqual(get_deployment_profile({}), "full")
        self.assertEqual(navigation_modes("full"),
                         ["Live", "Season Intelligence", "Historical"])

    def test_published_exposes_only_intelligence(self):
        self.assertEqual(get_deployment_profile(
            {"COURTVISION_DEPLOYMENT_PROFILE": " Published "}), "published")
        self.assertEqual(navigation_modes("published"), ["Season Intelligence"])

    def test_invalid_configuration_fails_closed(self):
        for value in ("", "production", "publshed"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                get_deployment_profile({"COURTVISION_DEPLOYMENT_PROFILE": value})
        with self.assertRaises(ValueError):
            navigation_modes("publshed")


if __name__ == "__main__":
    unittest.main()
