from decimal import Decimal

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from apps.core.models import TimeStampedModel


def _to_usd(amount: Decimal, currency: str) -> Decimal:
    currency = (currency or "USD").upper()
    rates = getattr(settings, "MVP_EXCHANGE_RATES_TO_USD", {"USD": "1", "INR": "0.012"})
    rate = Decimal(str(rates.get(currency, "1")))
    return (amount or Decimal("0")) * rate


def _get_rate(currency: str) -> Decimal:
    currency = (currency or "USD").upper()
    rates = getattr(settings, "MVP_EXCHANGE_RATES_TO_USD", {"USD": "1", "INR": "0.012"})
    return Decimal(str(rates.get(currency, "1")))


class FundPool(TimeStampedModel):
    class Jurisdiction(models.TextChoices):
        INDIA = "india", "India CSR pool"
        US = "us", "US 501(c)(3) pool"

    jurisdiction = models.CharField(max_length=8, choices=Jurisdiction.choices)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["jurisdiction", "name"]

    def __str__(self):
        return self.name

    def total_collected_usd(self) -> Decimal:
        from django.db.models import Sum
        result = self.contributions.filter(
            status__in=["received", "allocated", "utilized"]
        ).aggregate(Sum("amount_usd"))["amount_usd__sum"]
        return result or Decimal("0")

    def total_allocated_usd(self) -> Decimal:
        from django.db.models import Sum
        result = self.expenses.filter(
            status__in=["approved", "disbursed"]
        ).aggregate(Sum("amount_usd"))["amount_usd__sum"]
        return result or Decimal("0")

    def total_remaining_usd(self) -> Decimal:
        return self.total_collected_usd() - self.total_allocated_usd()

    def utilization_percent(self) -> int:
        collected = self.total_collected_usd()
        if collected == 0:
            return 0
        allocated = self.total_allocated_usd()
        return int((allocated / collected) * 100)


class Contribution(TimeStampedModel):
    class JurisdictionOrigin(models.TextChoices):
        INDIA = "india", "India"
        US = "us", "United States"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PLEDGED = "pledged", "Pledged"
        RECEIVED = "received", "Received"
        ALLOCATED = "allocated", "Allocated"
        UTILIZED = "utilized", "Utilized"
        CANCELLED = "cancelled", "Cancelled"

    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="contributions"
    )
    project = models.ForeignKey(
        "projects.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="contributions"
    )
    fund_pool = models.ForeignKey(
        FundPool, on_delete=models.SET_NULL, null=True, blank=True, related_name="contributions"
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="contributions"
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="contributions_recorded"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="USD")
    amount_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    jurisdiction_origin = models.CharField(max_length=16, choices=JurisdictionOrigin.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLEDGED)
    pledge_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    receipt_sent = models.BooleanField(
        default=False,
        help_text="Tax/acknowledgment receipt emailed or posted to donor.",
    )
    receipt_sent_date = models.DateField(
        null=True,
        blank=True,
        help_text="When the receipt was sent (optional).",
    )
    communication_capture_url = models.URLField(
        max_length=2048,
        blank=True,
        help_text="Optional link to stored correspondence (e.g. S3 object URL).",
    )
    volunteer_lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contributions_volunteer_lead",
        help_text="Volunteer or project lead stewarding this donor relationship (e.g. HNI).",
    )
    reference_number = models.CharField(max_length=128, blank=True)
    notes = models.TextField(blank=True)
    exchange_rate_used = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    exchange_rate_date = models.DateField(null=True, blank=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        from django.utils import timezone
        rate = _get_rate(self.currency)
        self.exchange_rate_used = rate
        if not self.exchange_rate_date:
            self.exchange_rate_date = timezone.now().date()
        self.amount_usd = (self.amount or Decimal("0")) * rate
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.donor} — {self.amount} {self.currency}"


class Expense(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PENDING_GOVERNANCE = "pending_governance", "Pending governance"
        APPROVED = "approved", "Approved"
        DISBURSED = "disbursed", "Disbursed"
        REJECTED = "rejected", "Rejected"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="expenses")
    fund_pool = models.ForeignKey(FundPool, on_delete=models.PROTECT, related_name="expenses")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expenses_requested"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_approved",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="INR")
    amount_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    description = models.TextField()
    expense_date = models.DateField()
    receipt_reference = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    requires_governance_approval = models.BooleanField(default=False)
    receipt_pdf = models.FileField(
        upload_to="expenses/receipts/",
        blank=True,
        null=True,
        help_text="PDF or document proving the expense."
    )
    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="owned_expenses",
        help_text="Registered users accountable for this expense / approval thread (e.g. requester + finance).",
    )
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        self.amount_usd = _to_usd(self.amount, self.currency)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-expense_date", "-id"]

    def __str__(self):
        return f"{self.project.title}: {self.amount} {self.currency}"
