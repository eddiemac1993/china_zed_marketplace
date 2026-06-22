from django.db import models
from django.contrib.auth.models import User


class EventPoster(models.Model):
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=255, blank=True)
    poster_image = models.ImageField(upload_to="event_posters/")
    description = models.TextField(blank=True)
    event_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class EventRegistration(models.Model):
    event = models.ForeignKey(EventPoster, on_delete=models.CASCADE, related_name="registrations")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    church_name = models.CharField(max_length=150, blank=True)
    location = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name