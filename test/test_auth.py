import unittest

from rbac import (
    ALL_PERMISSION_KEYS,
    DEFAULT_ROLE_PERMISSIONS,
    PRIVILEGED_ROLES,
    VALID_ROLES,
)


class RoleAndPermissionTests(unittest.TestCase):
    def test_expected_project_roles_are_defined(self):
        expected_roles = {
            "Administrator",
            "Operations Manager",
            "Shipping & Fleet Operator",
            "Cold-Chain Monitoring Operator",
            "Inventory & Warehouse Operator",
            "Quality & Compliance Operator",
            "Delivery Operator",
            "Viewer / Auditor",
        }
        self.assertTrue(expected_roles.issubset(set(VALID_ROLES)))

    def test_privileged_roles_are_valid_roles(self):
        self.assertTrue(set(PRIVILEGED_ROLES).issubset(set(VALID_ROLES)))

    def test_default_permissions_use_known_permission_keys(self):
        known_permissions = set(ALL_PERMISSION_KEYS)
        for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
            with self.subTest(role=role):
                self.assertTrue(set(permissions).issubset(known_permissions))

    def test_every_valid_role_has_default_permissions(self):
        for role in VALID_ROLES:
            with self.subTest(role=role):
                self.assertIn(role, DEFAULT_ROLE_PERMISSIONS)


if __name__ == "__main__":
    unittest.main()
