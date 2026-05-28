from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from apps.core.models import TimeStampedModel


class Event(TimeStampedModel):
    class EventType(models.TextChoices):
        FUNDRAISING = "fundraising", "Fundraising"
        LECTURE = "lecture", "Lecture"
        NETWORKING = "networking", "Networking"
        RECOGNITION = "recognition", "Recognition"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        GOVERNANCE_APPROVED = "governance_approved", "Governance approved"
        PUBLISHED = "published", "Published"
        REGISTRATION_OPEN = "registration_open", "Registration open"
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"
        CANCELLED = "cancelled", "Cancelled"

    class Jurisdiction(models.TextChoices):
        INDIA = "india", "India"
        US = "us", "United States"
        BOTH = "both", "Both"

    organized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="events_organized"
    )
    linked_project = models.ForeignKey(
        "projects.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    linked_need = models.ForeignKey(
        "needs.Need", on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_type = models.CharField(max_length=32, choices=EventType.choices, default=EventType.FUNDRAISING)
    venue = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    virtual_link = models.URLField(blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    jurisdiction = models.CharField(max_length=16, choices=Jurisdiction.choices, default=Jurisdiction.INDIA)
    fund_pool = models.ForeignKey(
        "funding.FundPool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    target_audience = models.TextField(blank=True)
    is_fundraising = models.BooleanField(default=False)
    details_doc = models.FileField(
        upload_to="event_details/",
        blank=True,
        null=True,
        help_text="Upload event details or agenda documents."
    )
    originated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_originated"
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["start_datetime"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("events:detail", kwargs={"pk": self.pk})


class EventMilestone(TimeStampedModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_milestones_owned",
    )
    due_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    proof = models.FileField(upload_to="event_milestone_proof/%Y/", blank=True, null=True)
    proof_original_filename = models.CharField(max_length=255, blank=True)
    completed = models.BooleanField(default=False)
    sequence = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["sequence", "due_date", "id"]

    def __str__(self):
        return f"{self.event.title}: {self.title}"


class EventMedia(TimeStampedModel):
    class MediaType(models.TextChoices):
        PHOTO = "photo", "Photo"
        VIDEO = "video", "Video"
        DOCUMENT = "document", "Document"
        PRESENTATION = "presentation", "Presentation"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="media_items")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="event_media_uploaded"
    )
    file = models.FileField(upload_to="event_media/%Y/%m/")
    media_type = models.CharField(max_length=32, choices=MediaType.choices, default=MediaType.PHOTO)
    caption = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]


class EventRegistration(TimeStampedModel):
    class Role(models.TextChoices):
        ATTENDEE = "attendee", "Attendee"
        SPEAKER = "speaker", "Speaker"
        ORGANIZER = "organizer", "Organizer"
        VOLUNTEER = "volunteer", "Volunteer"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_regs")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.ATTENDEE)
    registered_at = models.DateTimeField(auto_now_add=True)
    attended = models.BooleanField(default=False)

    class Meta:
        unique_together = [["event", "user"]]
