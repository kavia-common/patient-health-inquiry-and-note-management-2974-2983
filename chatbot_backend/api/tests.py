from rest_framework.test import APITestCase
from django.urls import reverse
from api.models import Conversation, Message
import uuid


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


class SendMessageTests(APITestCase):
    def setUp(self):
        self.send_url = reverse('SendMessage')

    def test_send_message_existing_conversation(self):
        convo = Conversation.objects.create(patient_id="p1", metadata={})
        payload = {
            "conversation_id": str(convo.id),
            "sender": "patient",
            "text": "Hello doctor"
        }
        res = self.client.post(self.send_url, data=payload, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "success")
        self.assertEqual(res.data["data"]["conversation_id"], str(convo.id))
        self.assertEqual(res.data["data"]["appended"], 1)
        self.assertFalse(res.data["data"]["created_new_conversation"])
        self.assertEqual(Message.objects.filter(conversation=convo).count(), 1)

    def test_send_message_create_if_missing_with_patient_id(self):
        # Non-existent conversation id
        missing_id = uuid.uuid4()
        payload = {
            "conversation_id": str(missing_id),
            "sender": "patient",
            "text": "Start with new convo",
            "patient_id": "p2"
        }
        res = self.client.post(self.send_url, data=payload, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "success")
        self.assertTrue(res.data["data"]["created_new_conversation"])
        new_convo_id = res.data["data"]["conversation_id"]
        # Ensure it was actually created and message added
        convo = Conversation.objects.get(id=new_convo_id)
        self.assertEqual(convo.patient_id, "p2")
        self.assertEqual(Message.objects.filter(conversation=convo).count(), 1)

    def test_send_message_missing_conversation_without_patient_id(self):
        missing_id = uuid.uuid4()
        payload = {
            "conversation_id": str(missing_id),
            "sender": "patient",
            "text": "No patient id provided"
        }
        res = self.client.post(self.send_url, data=payload, format="json")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data["status"], "error")
        self.assertEqual(res.data["error"]["code"], "not_found")
        self.assertIn("hint", res.data["error"]["details"])
