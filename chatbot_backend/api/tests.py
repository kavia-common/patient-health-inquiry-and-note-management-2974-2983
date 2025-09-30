from rest_framework.test import APITestCase
from django.urls import reverse


class HealthTests(APITestCase):
    def test_health(self):
        url = reverse('Health')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body.get("status"), "success")
        self.assertEqual(body.get("theme"), "ocean-professional")
        self.assertIn("data", body)
        self.assertEqual(body["data"].get("message"), "Server is up!")
