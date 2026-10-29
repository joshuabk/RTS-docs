from django.test import TestCase
from django.urls import reverse

# Create your tests here.


class ManageAdminGateTests(TestCase):
    """The clinics & machines pages require the separate admin sign-in."""

    def test_manage_redirects_to_admin_login(self):
        resp = self.client.get(reverse("reports:manage"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith(reverse("reports:manage_login")))

    def test_add_pages_redirect_to_admin_login(self):
        for name in ("reports:clinic_create", "reports:machine_create"):
            resp = self.client.post(reverse(name), {"name": "x"})
            self.assertEqual(resp.status_code, 302, name)
            self.assertTrue(resp["Location"].startswith(reverse("reports:manage_login")), name)

    def test_wrong_password_rejected(self):
        resp = self.client.post(
            reverse("reports:manage_login"),
            {"username": "RTSadmin", "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Please try again.")
        self.assertEqual(self.client.get(reverse("reports:manage")).status_code, 302)

    def test_correct_login_grants_access_and_logout_revokes(self):
        resp = self.client.post(
            reverse("reports:manage_login") + "?next=" + reverse("reports:manage"),
            {"username": "RTSadmin", "password": "northsiderts", "next": reverse("reports:manage")},
        )
        self.assertRedirects(resp, reverse("reports:manage"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("reports:manage")).status_code, 200)
        self.client.post(reverse("reports:manage_logout"))
        self.assertEqual(self.client.get(reverse("reports:manage")).status_code, 302)
